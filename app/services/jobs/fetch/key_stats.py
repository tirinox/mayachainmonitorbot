import asyncio
import datetime

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.circulating import CacaoCirculatingSupplyFetcher
from services.jobs.fetch.pool_price import PoolFetcher
from services.lib.constants import MAYA_DENOM, MAYA_DIVIDER_INV
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import WithLogger
from services.models.earnings_history import EarningsData
from services.models.key_stats_model import AlertKeyStats, AffiliateCollectors, MayaDividend, \
    MayaDividends
from services.models.swap_history import SwapHistoryResponse

URL_SWAP_PATHS = "https://mayaswap.s3.eu-central-1.amazonaws.com/stats.json?r={r}"

URL_NETWORK_STATS = "https://midgard.mayachain.info/v2/network"
URL_AFFILIATE_STATS = "https://www.mayascan.org/api/walletStats?period=1w&days=7"
URL_CACAO_DIVIDENDS = "https://mayaswap.s3.eu-central-1.amazonaws.com/rewards.json"


class KeyStatsFetcher(BaseFetcher, WithLogger):
    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.key_metrics.fetch_period)
        super().__init__(deps, sleep_period)

        self.tally_days_period = deps.cfg.as_int('key_metrics.tally_period_days', 7)

        # x3 days (this week + previous week + spare days)
        self.trim_max_days = deps.cfg.as_int('key_metrics.trim_max_days', self.tally_days_period * 3)

    async def _load_json(self, url):
        async with self.deps.session.get(url) as resp:
            return await resp.json()

    async def _load_affiliate_stats(self) -> AffiliateCollectors:
        affiliate_stats = await self._load_json(URL_AFFILIATE_STATS)
        collectors = AffiliateCollectors.from_json(affiliate_stats)
        return collectors

    async def _load_dividends(self):
        supply_loader = CacaoCirculatingSupplyFetcher(self.deps.session, self.deps.thor_connector.first_client_node_url)
        supply_data = await supply_loader.get_supply_data()
        maya_supply = next((item['amount'] for item in supply_data if item['denom'] == MAYA_DENOM), 0)
        maya_supply = int(maya_supply) * MAYA_DIVIDER_INV

        maya_dividends = await self._load_json(URL_CACAO_DIVIDENDS)
        maya_dividends = [MayaDividend.from_json(item) for item in maya_dividends['rewards']]
        return MayaDividends(maya_dividends, maya_supply)

    async def _load_swap_history(self):
        swap_history = await self.deps.midgard_connector.request(free_url_gen.url_swap_history(free_url_gen.WEEK, 2))
        swap_history = SwapHistoryResponse.from_json(swap_history)
        return swap_history

    async def _load_earnings_history(self):
        earnings_history = await self.deps.midgard_connector.request(free_url_gen.url_earnings_history(free_url_gen.WEEK, 2))
        earnings_history = EarningsData.from_json(earnings_history)
        return earnings_history

    async def fetch(self) -> AlertKeyStats:
        # Load pool data for BTC/ETH/RUNE/USD value in the pools
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

        # Load the data
        mdg = self.deps.midgard_connector
        swap_history = await self._load_swap_history()
        earnings_history = await mdg.request(free_url_gen.url_earnings_history(free_url_gen.WEEK, 2))
        affiliate_stats = await self._load_affiliate_stats()

        dividends = await self._load_dividends()

        routes = []

        # Done. Construct the resulting event
        return AlertKeyStats(
            old_pools, fresh_pools,
            bond_usd=0, bond_usd_prev=0,
            pool_usd=0, pool_usd_prev=0,
            protocol_revenue_usd=0, protocol_revenue_usd_prev=0,
            affiliate_revenue_usd=0, affiliate_revenue_usd_prev=0,
            maya_revenue_usd=0, maya_revenue_usd_prev=0,
            maya_revenue_per_unit=0,
            unique_swapper_count=0, unique_swapper_count_prev=0,
            number_of_swaps=0, number_of_swaps_prev=0,
            swap_volume_usd=0, swap_volume_usd_prev=0,
            routes=routes,
            affiliates=affiliate_stats,
            dividends=dividends,
            end_date=datetime.datetime.now(),
        )
