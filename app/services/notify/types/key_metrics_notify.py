from typing import Optional

from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds, DAY, now_ts
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.key_stats_model import AlertKeyStats
from services.models.time_series import TimeSeries


class KeyMetricsNotifier(INotified, WithDelegates, WithLogger):
    MAX_POINTS = 10000
    MAX_DATA_AGE_DEFAULT = '36h'

    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps

        self.data_max_age = deps.cfg.as_interval('key_metrics.data_max_age', self.MAX_DATA_AGE_DEFAULT)

        self.notifications_enabled = deps.cfg.get('key_metrics.notification.enabled', False)

        raw_cd = self.deps.cfg.key_metrics.notification.cooldown
        self.notify_cd_sec = parse_timespan_to_seconds(raw_cd)
        self.notify_cd = Cooldown(self.deps.db, 'KeyMetrics:Notify', self.notify_cd_sec)
        self.logger.info(f"it will notify every {self.notify_cd_sec} sec ({raw_cd})")

        self.series = TimeSeries('KeyMetrics', self.deps.db)
        self._prev_data: Optional[AlertKeyStats] = None

    @property
    def window_in_days(self):
        return int((self.notify_cd_sec + 1) / DAY)

    def is_fresh_enough(self, data: AlertKeyStats):
        return data and now_ts() - data.end_date.timestamp() < self.data_max_age

    async def on_data(self, sender, e: AlertKeyStats):
        if not e.current_pools:
            self.logger.error(f'No pool data! Aborting.')
            return

        if not e.is_valid:
            self.logger.warning(f'AlertKeyStats is invalid')
            return

        if not e.previous_pools:
            self.logger.warning(f'No previous pool data! Go on')

        if not self.is_fresh_enough(e):
            self.logger.error(f'Network data is too old! The most recent date is {e.end_date}!')
            self.deps.emergency.report(
                'WeeklyKeyMetrics',
                'Network data is too old!',
                date=str(e.end_date))
            return

        self._prev_data = e

        if self.notifications_enabled and await self.notify_cd.can_do():
            await self._notify(e)
            await self.notify_cd.do()

    @property
    def last_event(self):
        return self._prev_data

    async def clear_cd(self):
        await self.notify_cd.clear()

    async def _notify(self, event):
        await self.pass_data_to_listeners(event)
