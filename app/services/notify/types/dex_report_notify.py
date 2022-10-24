from services.lib.cooldown import Cooldown
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.delegates import INotified, WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.lib.w3.dex_analytics import DexAnalyticsCollector


class DexReportNotifier(WithDelegates, INotified, WithLogger):
    def __init__(self, deps: DepContainer, dex_analytics: DexAnalyticsCollector):
        super().__init__()
        self.dex_analytics = dex_analytics
        self.deps = deps
        cd = parse_timespan_to_seconds(deps.cfg.tx.dex_aggregator_update.cooldown)
        self.spam_cd = Cooldown(self.deps.db, 'DexReport', cd)

    async def on_data(self, sender, data):
        if self.spam_cd.can_do():
            await self.spam_cd.do()
            report = await self.dex_analytics.get_analytics(self.spam_cd.cooldown)
            # only if there is some data
            if report.total.count > 0:
                await self.pass_data_to_listeners(report)
