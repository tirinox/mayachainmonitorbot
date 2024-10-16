import asyncio
import datetime
from typing import List

from aionode.types import ThorNodeAccount
from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.pool_price import PoolFetcher
from services.jobs.scanner.swap_routes import SwapRouteRecorder
from services.jobs.user_counter import UserCounter
from services.lib.constants import MAYA_DENOM, MAYA_DIVIDER_INV, cacao_to_float, THOR_BLOCK_TIME
from services.lib.date_utils import parse_timespan_to_seconds, DAY
from services.lib.depcont import DepContainer
from services.lib.midgard.name_service import NameService
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import WithLogger
from services.models.earnings_history import EarningsData
from services.models.key_stats_model import AlertKeyStats, AffiliateCollectors, MayaDividend, \
    MayaDividends
from services.models.pool_info import PoolInfoMap
from services.models.swap_history import SwapHistoryResponse

URL_SWAP_PATHS = "https://mayaswap.s3.eu-central-1.amazonaws.com/stats.json?r={r}"

URL_NETWORK_STATS = "https://midgard.mayachain.info/v2/network"
URL_AFFILIATE_STATS = "https://www.mayascan.org/api/walletStats?period=1d&days=14"
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

        name_service: NameService = self.deps.name_service

        # rewrite code to the real labels
        collectors = collectors._replace(collectors=[collector._replace(
            code=name_service.get_affiliate_name(collector.code)
        ) for collector in collectors.collectors])

        return collectors

    async def _load_dividends(self):
        supply_data = await self.deps.thor_connector.query_supply_raw()
        maya_supply = next((item['amount'] for item in supply_data if item['denom'] == MAYA_DENOM), 0)
        maya_supply = int(maya_supply) * MAYA_DIVIDER_INV

        maya_dividends = await self._load_json(URL_CACAO_DIVIDENDS)
        # maya_dividends = [MayaDividend.from_json(item) for item in maya_dividends['rewards']]
        return MayaDividends.from_json(maya_dividends, maya_supply)

    async def _load_swap_history(self):
        swap_history = await self.deps.midgard_connector.request(free_url_gen.url_swap_history(free_url_gen.WEEK, 2))
        swap_history = SwapHistoryResponse.from_json(swap_history)
        return swap_history

    async def _load_earnings_history(self) -> EarningsData:
        earnings_history = await self.deps.midgard_connector.request(free_url_gen.url_earnings_history(free_url_gen.WEEK, 2))
        earnings_history = EarningsData.from_json(earnings_history)
        return earnings_history

    async def _load_lock_stats(self, days_ago=7):
        thor = self.deps.thor_connector

        last_block = await thor.query_last_blocks()
        last_block = last_block[0].mayachain
        block_ago = last_block - DAY / THOR_BLOCK_TIME

        nodes = await thor.query_node_accounts()
        prev_nodes = await thor.query_node_accounts(block_ago)

        def sum_active_bonds(_nodes: List[ThorNodeAccount]):
            return sum(n.bond for n in _nodes if n.status.lower() == ThorNodeAccount.STATUS_ACTIVE)

        curr_bond = cacao_to_float(sum_active_bonds(nodes))
        prev_bond = cacao_to_float(sum_active_bonds(prev_nodes))

        return prev_bond, curr_bond

    @staticmethod
    def _sum_pool(pools: PoolInfoMap, cacao_price):
        return cacao_to_float(sum(p.balance_rune for p in pools.values())) * cacao_price

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
        swap_history = await self._load_swap_history()
        earnings_history = await self._load_earnings_history()
        affiliate_stats = await self._load_affiliate_stats()
        dividends = await self._load_dividends()

        prev_bond, curr_bond = await self._load_lock_stats()

        usd_per_cacao = earnings_history.intervals[0].cacao_price_usd
        prev_usd_per_cacao = earnings_history.intervals[1].cacao_price_usd

        curr_week_swap = swap_history.intervals[0]
        prev_week_swap = swap_history.intervals[1]

        maya_revenue_per_unit = dividends.current_week_cacao_sum / dividends.maya_supply

        route_recorder: SwapRouteRecorder = self.deps.route_recorder
        top_routes = await route_recorder.get_top_swap_routes_by_volume(days=self.tally_days_period, top_n=4)

        user_counter: UserCounter = self.deps.user_counter
        unique_swapper_count = await user_counter.counter.get_wau()
        unique_swapper_count_prev = await user_counter.counter.get_previous_wau()

        # Done. Construct the resulting event
        return AlertKeyStats(
            old_pools, fresh_pools,
            bond_usd=curr_bond * usd_per_cacao,
            bond_usd_prev=prev_bond * prev_usd_per_cacao,
            pool_usd=self._sum_pool(fresh_pools, usd_per_cacao),
            pool_usd_prev=self._sum_pool(old_pools, prev_usd_per_cacao),
            protocol_revenue_usd=cacao_to_float(earnings_history.current_week.earnings) * usd_per_cacao,
            protocol_revenue_usd_prev=cacao_to_float(earnings_history.previous_week.earnings) * prev_usd_per_cacao,
            affiliate_revenue_usd=affiliate_stats.current_week_affiliate_revenue_usd,
            affiliate_revenue_usd_prev=affiliate_stats.previous_week_affiliate_revenue_usd,
            maya_revenue_usd=dividends.current_week_cacao_sum * usd_per_cacao,
            maya_revenue_usd_prev=dividends.previous_week_cacao_sum * prev_usd_per_cacao,
            maya_revenue_per_unit=maya_revenue_per_unit,
            unique_swapper_count=unique_swapper_count,
            unique_swapper_count_prev=unique_swapper_count_prev,
            number_of_swaps=curr_week_swap.total_count,
            number_of_swaps_prev=prev_week_swap.total_count,
            swap_volume_usd=cacao_to_float(curr_week_swap.total_volume) * usd_per_cacao,
            swap_volume_usd_prev=cacao_to_float(curr_week_swap.total_volume) * prev_usd_per_cacao,
            routes=top_routes,
            affiliates=affiliate_stats,
            dividends=dividends,
            end_date=datetime.datetime.now(),
            price=usd_per_cacao,
        )
