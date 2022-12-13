import json
import math
from typing import NamedTuple, Optional

from services.lib.date_utils import now_ts, YEAR
from services.lib.db import DB
from services.lib.delegates import WithDelegates, INotified
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.net_stats import NetworkStats


class Achievement:
    TEST = '__test'

    DAU = 'dau'
    MAU = 'mau'
    WALLET_COUNT = 'wallet_count'
    DAILY_TX_COUNT = 'daily_tx_count'
    DAILY_VOLUME = 'daily_volume'
    BLOCK_NUMBER = 'block_number'
    ANNIVERSARY = 'anniversary'

    # every single digit is a milestone
    GROUP_EVERY_1 = {
        BLOCK_NUMBER,
        ANNIVERSARY,
    }

    # this metrics require a bit more complex logic to transform value to milestone
    GROUP_SPECIAL_TRANSFORM = {
        ANNIVERSARY: {
            'forward': lambda x: math.floor(x / YEAR),
            'backward': lambda x: x * YEAR,
        }
    }

    # this metrics only trigger when greater than their minimums
    GROUP_MINIMALS = {
        DAU: 300,
        MAU: 6500,
        WALLET_COUNT: 61000,
    }


class Milestones:
    MILESTONE_DEFAULT_PROGRESSION = [1, 2, 5]

    def __init__(self, progression=None):
        self.progression = progression or self.MILESTONE_DEFAULT_PROGRESSION

    def milestone_nearest(self, x, before: bool):
        progress = self.progression
        x = int(x)
        if x <= 0:
            return self.progression[0]

        mag = 10 ** int(math.log10(x))
        if before:
            delta = -1
            mag *= 10
        else:
            delta = 1
        i = 0

        while True:
            step = progress[i]
            y = step * mag
            if before and x >= y:
                return y
            if not before and x < y:
                return y
            i += delta
            if i < 0:
                i = len(progress) - 1
                mag //= 10
            elif i >= len(progress):
                i = 0
                mag *= 10

    def next(self, x):
        return self.milestone_nearest(x, before=False)

    def previous(self, x):
        return self.milestone_nearest(x, before=True)


class AchievementRecord(NamedTuple):
    key: str
    value: int  # real current value
    milestone: int  # current milestone
    timestamp: float
    prev_milestone: int
    previous_ts: float


class EventAchievement(NamedTuple):
    achievement: AchievementRecord


class AchievementsTracker(WithLogger):
    def __init__(self, db: DB):
        super().__init__()
        self.db = db
        self.milestones = Milestones()
        self.milestones_every = Milestones(list(range(1, 10)))

    def key(self, name):
        return f'Achievements:{name}'

    @staticmethod
    def transform_value(key, value, backward=False):
        transform = Achievement.GROUP_SPECIAL_TRANSFORM.get(key)
        if transform:
            return transform['backward' if backward else 'forward'](value)
        return value

    @staticmethod
    def get_minimum(key):
        return Achievement.GROUP_MINIMALS.get(key, 0)

    def get_previous_milestone(self, key, value):
        if key in Achievement.GROUP_EVERY_1:
            v = self.milestones_every.previous(value)
        else:
            v = self.milestones.previous(value)

        return v

    async def feed_data(self, name: str, value: int) -> Optional[EventAchievement]:
        assert name

        value = self.transform_value(name, value)

        if value < self.get_minimum(name):
            return None

        record = await self.get_achievement_record(name)
        current_milestone = self.get_previous_milestone(name, value)
        if record is None:
            # first time, just write and return
            record = AchievementRecord(
                str(name), value, current_milestone, now_ts(), 0, 0
            )
            await self.set_achievement_record(record)
            self.logger.info(f'New achievement record created {record}')
        else:
            # check if we need to update
            if current_milestone > record.value:
                record = AchievementRecord(
                    str(name), value, current_milestone, now_ts(),
                    prev_milestone=record.milestone, previous_ts=record.timestamp
                )
                await self.set_achievement_record(record)
                self.logger.info(f'Achievement record updated {record}')
                return EventAchievement(record)

    async def get_achievement_record(self, key) -> Optional[AchievementRecord]:
        key = self.key(key)
        data = await self.db.redis.get(key)
        try:
            return AchievementRecord(**json.loads(data))
        except (TypeError, json.JSONDecodeError):
            return None

    async def set_achievement_record(self, record: AchievementRecord):
        key = self.key(record.key)
        await self.db.redis.set(key, json.dumps(record._asdict()))


class AchievementTest(NamedTuple):
    value: int


class AchievementsNotifier(WithLogger, WithDelegates, INotified):
    async def extract_events_by_type(self, data):
        if isinstance(data, NetworkStats):
            kv_events = await self.on_network_stats(data)
        elif isinstance(data, AchievementTest):
            kv_events = [(Achievement.TEST, data.value)]
        else:
            self.logger.warning(f'Unknown data type {type(data)}. Dont know how to handle it.')
            kv_events = []
        return kv_events

    @staticmethod
    async def on_network_stats(data: NetworkStats):
        achievements = [
            (Achievement.DAU, data.users_daily),
            (Achievement.MAU, data.users_monthly),
            # todo: add more handlers
        ]
        return achievements

    async def on_data(self, sender, data):
        kv_events = await self.extract_events_by_type(data)

        for key, value in kv_events:
            event = await self.tracker.feed_data(key, value)
            if event:
                await self.pass_data_to_listeners(event)

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.tracker = AchievementsTracker(deps.db)
