import asyncio
import operator
from collections import defaultdict
from functools import reduce
from typing import List

from localization import LocalizationManager
from services.jobs.fetch.base import INotified
# from services.jobs.fetch.thormon import ThorMonWSSClient
from services.lib.date_utils import HOUR, MINUTE, now_ts, parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.nop_links import SettingsManager
from services.lib.texts import grouper
from services.lib.utils import class_logger
from services.models.node_info import NodeSetChanges, NodeEvent, NodeEventType
from services.models.node_watchers import NodeWatcherStorage
from services.models.thormon import ThorMonAnswer
from services.notify.broadcast import ChannelDescriptor
from services.notify.personal.bond import BondTracker
from services.notify.personal.chain_height import ChainHeightTracker
from services.notify.personal.churning import NodeChurnTracker
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting
from services.notify.personal.ip_addr import IpAddressTracker
from services.notify.personal.node_online import NodeOnlineTracker
from services.notify.personal.presence import PresenceTracker
from services.notify.personal.slashing import SlashPointTracker
from services.notify.personal.telemetry import NodeTelemetryDatabase
from services.notify.personal.user_data import UserDataCache
from services.notify.personal.versions import VersionTracker

MAX_CHANGES_PER_MESSAGE = 10

TELEMETRY_MAX_HISTORY_DURATION = HOUR
TELEMETRY_TOLERANCE = MINUTE
TELEMETRY_MAX_POINTS = 5_000


class NodeChangePersonalNotifier(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.watchers = NodeWatcherStorage(deps.db)
        # self.thor_mon = ThorMonWSSClient(deps.cfg.network_id)
        self.telemetry_db = NodeTelemetryDatabase(deps)
        self.settings_man = SettingsManager(self.deps.db, self.deps.cfg)

        # trackers
        self.online_tracker = NodeOnlineTracker(deps)
        self.chain_height_tracker = ChainHeightTracker(deps)
        self.version_tracker = VersionTracker(deps)
        self.ip_address_tracker = IpAddressTracker(deps)
        self.churn_tracker = NodeChurnTracker(deps)
        self.slash_tracker = SlashPointTracker(deps)
        self.bond_tracker = BondTracker(deps)
        self.presence_tracker = PresenceTracker(deps)
        self._last_signal_ts = 0

        watch_dog_cfg = self.deps.cfg.get('node_info.personal.watchdog')
        self._watchdog_enabled = bool(watch_dog_cfg.get('enabled', False))
        self._disconnected_cable_timeout = parse_timespan_to_seconds(
            watch_dog_cfg.as_str('disconnected_cable_timeout', '20s')
        )
        self._cable_disconnected = False

    async def prepare(self):
        if self._watchdog_enabled:
            self.logger.info(f'Starting watchdog timer: timeout = {self._disconnected_cable_timeout} sec')
            asyncio.create_task(self._watchdog_timer())
        # self.thor_mon.subscribe(self)
        # asyncio.create_task(self.thor_mon.listen_forever())

    async def _watchdog_timer(self):
        while True:
            try:
                if self._last_signal_ts > 0:
                    if not self._cable_disconnected and self.last_signal_sec_ago > self._disconnected_cable_timeout:
                        self.logger.warning(f'Cable disconnected!')
                        self._cable_disconnected = True
                        await self._notify_cable_disconnected()
                    elif self._cable_disconnected and self.last_signal_sec_ago < self._disconnected_cable_timeout:
                        self.logger.warning(f'Cable reconnected!')
                        self._cable_disconnected = False
                        await self._notify_cable_disconnected()
            except Exception:
                self.logger.exception(f'Watchdog failed to handle its tick!', exc_info=True)
            await asyncio.sleep(0.5)

    async def _notify_cable_disconnected(self):
        event_type = NodeEventType.CABLE_DISCONNECT if self._cable_disconnected else NodeEventType.CABLE_RECONNECT
        events = [
            NodeEvent(NodeEvent.ANY, event_type, self.last_signal_sec_ago, single_per_user=True)
        ]
        await self._cast_messages_for_events(events)

    async def on_data(self, sender, data):
        self._last_signal_ts = now_ts()
        if isinstance(data, NodeSetChanges):  # from Churn Fetcher
            asyncio.create_task(self._handle_node_churn_bg_job(data))  # long-running job goes to the background!
        elif isinstance(data, ThorMonAnswer):  # from ThorMon
            asyncio.create_task(self._handle_thormon_message_bg_job(data))  # long-running job goes to the background!

    async def _handle_thormon_message_bg_job(self, data: ThorMonAnswer):
        # await self.telemetry_db.write_telemetry(data)

        self.chain_height_tracker.estimate_block_height(data)

        user_cache = await UserDataCache.load(self.deps.db)

        events = sum(
            await asyncio.gather(
                self.online_tracker.get_events(data, user_cache),
                self.chain_height_tracker.get_events(data, user_cache),
                self.slash_tracker.get_events(data, user_cache),
            ), []
        )

        await self._cast_messages_for_events(events)

        await user_cache.save(self.deps.db)

    async def _handle_node_churn_bg_job(self, node_set_change: NodeSetChanges):
        prev_and_curr_node_map = node_set_change.prev_and_curr_node_map

        events = []
        events += await self.churn_tracker.get_all_changes(node_set_change)
        events += await self.version_tracker.get_all_changes(node_set_change)
        events += await self.ip_address_tracker.get_all_changes(prev_and_curr_node_map)
        events += await self.bond_tracker.get_all_changes(prev_and_curr_node_map)
        events += await self.presence_tracker.get_events(node_set_change)

        # # fixme: debug
        # events.append(NodeEvent(
        #     NodeEvent.ANY,
        #     NodeEventType.TEXT_MESSAGE,
        #     'Hellow worold!', single_per_user=True
        # ))

        await self._cast_messages_for_events(events)

    async def _cast_messages_for_events(self, events: List[NodeEvent]):
        if not events:
            return

        broadcasting_events = [e for e in events if e.is_broad]

        self.logger.debug(f'Casting Node changes ({len(events)} items)')

        # 2. get list of changed nodes
        affected_node_addresses = set(c.address for c in events)

        # 3. get list of user who watch those nodes
        node_to_user = await self.watchers.all_users_for_many_nodes(affected_node_addresses)

        all_affected_users = reduce(operator.or_, node_to_user.values()) if node_to_user else []
        if not broadcasting_events and not all_affected_users:
            self.logger.info('No users to receive alerts.')
            return  # nobody is interested in those changes...

        all_users = []
        if broadcasting_events:
            all_users = await self.watchers.all_users()

        user_events = defaultdict(list)
        for event in events:
            users_for_event = all_users if event.is_broad else node_to_user[event.address]

            for user in users_for_event:
                this_user = user_events[user]

                # single_per_user: skip all events of this kind if there was one before!
                if event.single_per_user and any(e.type == event.type for e in this_user):
                    continue

                this_user.append(event)

        loc_man: LocalizationManager = self.deps.loc_man

        # for every user
        for user, event_list in user_events.items():
            loc = await loc_man.get_from_db(user, self.deps.db)

            settings = await self.settings_man.get_settings(user)

            if bool(settings.get(NodeOpSetting.PAUSE_ALL_ON, False)):
                continue  # skip those who paused all the events.

            if user in self.deps.broadcaster.channels_inactive:
                settings[NodeOpSetting.PAUSE_ALL_ON] = True
                await self.settings_man.set_settings(user, settings)
                self.deps.broadcaster.remove_me_from_inactive_channels(user)
                self.logger.warning(f'Auto-pause NodeOp alerts for {user}!')
                continue

            platform = SettingsManager.get_platform(settings)

            # filter changes according to the user's setting
            filtered_change_list = await self._filter_events(event_list, user, settings)

            groups = list(grouper(MAX_CHANGES_PER_MESSAGE, filtered_change_list))  # split to several messages

            if groups:
                self.logger.info(f'Sending personal notifications to user: {user}: '
                                 f'{len(event_list)} changes grouped to {len(groups)} groups...')

            for group in groups:
                messages = [loc.notification_text_for_node_op_changes(c) for c in group]
                text = '\n\n'.join(m for m in messages if m)
                text = text.strip()
                if text:
                    # task = self.deps.broadcaster.safe_send_message_tg(user, text)
                    task = self.deps.broadcaster.safe_send_message(ChannelDescriptor(platform, user), text)
                    asyncio.create_task(task)

    @staticmethod
    async def _filter_events(event_list: List[NodeEvent], user_id, settings: dict) -> List[NodeEvent]:
        results = []
        for event in event_list:
            passes = True

            # noinspection PyTypeChecker
            tracker: BaseChangeTracker = event.tracker
            if tracker:
                passes = await tracker.is_event_ok(event, user_id, settings)

            if passes:
                results.append(event)
        return results

    @property
    def last_signal_sec_ago(self):
        # return self.thor_mon.last_signal_sec_ago
        return now_ts() - self._last_signal_ts
