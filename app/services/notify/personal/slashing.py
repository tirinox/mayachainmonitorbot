import asyncio
from typing import List

from services.lib.date_utils import MINUTE, parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeEvent, NodeEventType, EventDataSlash
from services.models.thormon import ThorMonAnswer
from services.models.time_series import TimeSeries
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting, STANDARD_INTERVALS
from services.notify.personal.user_data import UserDataCache


class SlashPointTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.series = TimeSeries('SlashPointTracker', self.deps.db)
        self.intervals_sec = [parse_timespan_to_seconds(s) for s in STANDARD_INTERVALS]
        self.logger = class_logger(self)
        self.logger.info(f'{STANDARD_INTERVALS = }')

    @staticmethod
    def _extract_slash_points(last_answer: ThorMonAnswer):
        return {n.node_address: n.slash_points for n in last_answer.nodes if n.node_address}

    async def _save_point(self, last_answer: ThorMonAnswer):
        data = self._extract_slash_points(last_answer)
        if data:
            await self.series.add(**data)

    async def _read_points(self):
        tasks = [
            self.series.get_best_point_ago(ago, tolerance_percent=1, tolerance_sec=20)
            for ago in self.intervals_sec
        ]
        return await asyncio.gather(*tasks)

    async def get_events(self, last_answer: ThorMonAnswer, user_cache: UserDataCache) -> List[NodeEvent]:
        await self._save_point(last_answer)

        points = await self._read_points()
        current_state = self._extract_slash_points(last_answer)

        events = []
        for interval, (data, _) in zip(self.intervals_sec, points):
            if data is None:
                continue
            for address, slash_pts in data.items():
                slash_pts = int(slash_pts)
                current_slash_pts = int(current_state.get(address, 0))
                if slash_pts != current_slash_pts:
                    events.append(NodeEvent(
                        address, NodeEventType.SLASHING,
                        EventDataSlash(slash_pts, current_slash_pts, interval),
                        # todo: thor_node=?
                        tracker=self
                    ))

        return events

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.SLASH_ON, True)):
            return False

        data: EventDataSlash = event.data

        interval = settings.get(NodeOpSetting.SLASH_PERIOD, 5 * MINUTE)
        if interval != data.interval_sec:
            return False

        threshold = settings.get(NodeOpSetting.SLASH_THRESHOLD, 50)
        return data.delta_pts >= threshold
