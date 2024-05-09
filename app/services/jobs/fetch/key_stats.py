import asyncio

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger
from services.models.flipside import FSAffiliateCollectors, FSFees, FSSwapCount, FSLockedValue, FSSwapVolume, \
    FSSwapRoutes, AlertKeyStats

URL_SWAP_PATHS = "https://mayaswap.s3.eu-central-1.amazonaws.com/stats.json?r={r}"


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)

        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        # x3 days (this week + previous week + spare days)
        self.trim_max_days = deps.cfg.as_int('key_metrics.trim_max_days', self.tally_days_period * 3)

    async def fetch(self) -> AlertKeyStats:
        # Load pool data for BTC/ETH value in the pools
        pf: PoolFetcher = self.deps.pool_fetcher
        previous_block = self.deps.last_block_store.block_time_ago(self.tally_days_period * DAY)

        if previous_block < 0:
            raise ValueError(f'Previous block is negative {previous_block}!')

        fresh_pools, old_pools = await asyncio.gather(
            pf.load_pools(),
            pf.load_pools(height=previous_block)
        )

        fresh_pools = pf.convert_pool_list_to_dict(list(fresh_pools.values()))
        old_pools = pf.convert_pool_list_to_dict(list(old_pools.values()))

        # FSFees, FSSwapCount, FSLockedValue, FSSwapVolume, FSAffiliateCollectors, FSSwapRoutes

        routes = []
        results = {}

        # Done. Construct the resulting event
        return AlertKeyStats(
            results, old_pools, fresh_pools,
            routes, [], [],
            days=self.tally_days_period
        )
