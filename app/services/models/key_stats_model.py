import dataclasses
import operator
from collections import defaultdict
from datetime import datetime
from typing import NamedTuple, List

import dateutil.parser

from services.lib.constants import STABLE_COIN_POOLS_ALL, thor_to_float
from services.lib.date_utils import discard_time
from services.models.pool_info import PoolInfoMap

KEY_DATETIME = "datetime"


class AffiliateCollectorDay(NamedTuple):
    volume_usd: float
    fees_usd: float
    avg_tx_volume_usd: float
    count: int

    @classmethod
    def from_json(cls, j):
        return cls(
            volume_usd=j['volume'],
            fees_usd=j['fees'],
            avg_tx_volume_usd=j['avgTxValue'],
            count=j['txs'],
        )


class AffiliateCollector(NamedTuple):
    code: str
    daily: List[AffiliateCollectorDay]

    @classmethod
    def from_json(cls, day_list, code):
        return cls(
            code=code,
            daily=[AffiliateCollectorDay.from_json(d) for d in day_list]
        )

    def get_summary(self, start_day_index, end_day_index):
        sliced = self.daily[start_day_index:end_day_index]
        return AffiliateCollectorDay(
            volume_usd=sum(day.volume_usd for day in sliced),
            fees_usd=sum(day.fees_usd for day in sliced),
            avg_tx_volume_usd=sum(day.avg_tx_volume_usd for day in sliced) / len(sliced),
            count=sum(day.count for day in sliced)
        )

    @property
    def current_week_summary(self):
        return self.get_summary(0, 7)

    @property
    def previous_week_summary(self):
        return self.get_summary(7, 14)


class AffiliateCollectors(NamedTuple):
    collectors: List[AffiliateCollector]
    dates: List[datetime]

    @classmethod
    def from_json(cls, j):
        date_format = "%a %b %d %Y"
        return cls(
            collectors=[AffiliateCollector.from_json(v, k) for k, v in j['affiliates'].items()],
            dates=[datetime.strptime(d, date_format) for d in j['dates']]
        )

    @property
    def current_week_affiliate_revenue(self):
        return sum(collector.current_week_summary.fees_usd for collector in self.collectors)

    @property
    def previous_week_affiliate_revenue(self):
        return sum(collector.previous_week_summary.fees_usd for collector in self.collectors)

    @property
    def top_affiliate_collectors_this_week(self):
        return list(sorted(self.collectors, key=lambda x: x.current_week_summary.fees_usd, reverse=True))


class FSSwapRoutes(NamedTuple):
    asset_from: str
    asset_to: str
    volume_usd: float
    total_swaps: int


class MayaDividend(NamedTuple):
    date: datetime
    reward: float
    denom: str

    @classmethod
    def from_json(cls, j):
        return cls(
            date=discard_time(dateutil.parser.parse(j['date'])),
            reward=j['reward'],
            denom=j['denom']
        )


class MayaDividends(NamedTuple):
    dividends: List[MayaDividend]
    maya_supply: float

    @classmethod
    def from_json(cls, j: dict, maya_supply: float):
        dividends = [MayaDividend.from_json(d) for d in j['rewards']]
        dividends.sort(key=operator.attrgetter("date"), reverse=True)
        return cls(
            dividends=dividends,
            maya_supply=maya_supply
        )

    @property
    def latest_date(self):
        return self.dividends[0].date

    def get_cacao_sum(self, start_index, end_index) -> float:
        sliced = self.dividends[start_index:end_index]
        return sum(d.reward for d in sliced)


@dataclasses.dataclass
class AlertKeyStats:
    previous_pools: PoolInfoMap
    current_pools: PoolInfoMap

    bond_usd: float
    bond_usd_prev: float

    pool_usd: float
    pool_usd_prev: float

    protocol_revenue_usd: float
    protocol_revenue_usd_prev: float

    affiliate_revenue_usd: float
    affiliate_revenue_usd_prev: float

    maya_revenue_usd: float
    maya_revenue_usd_prev: float

    maya_revenue_per_unit: float

    unique_swapper_count: int
    unique_swapper_count_prev: int

    number_of_swaps: int
    number_of_swaps_prev: int

    swap_volume_usd: float
    swap_volume_usd_prev: float

    routes: List[FSSwapRoutes]
    affiliates: AffiliateCollectors

    dividends: MayaDividends

    end_date: datetime

    days: int = 7

    @property
    def is_valid(self):
        return self.current_pools and self.routes and self.affiliates

    def get_stables_sum(self, previous=False):
        return self.get_sum(STABLE_COIN_POOLS_ALL, previous)

    def get_sum(self, coin_list, previous=False):
        source = self.previous_pools if previous else self.current_pools
        running_sum = 0.0

        for symbol in coin_list:
            pool = source.get(symbol)
            if pool:
                running_sum += pool.balance_asset
        return thor_to_float(running_sum)

    def get_btc(self, previous=False):
        return self.get_sum(('BTC.BTC',), previous)

    def get_eth(self, previous=False):
        return self.get_sum(('ETH.ETH',), previous)

    def get_rune(self, previous=False):
        return self.get_sum(('RUNE.RUNE',), previous)

    @property
    def swap_routes(self):
        collectors = defaultdict(float)
        for obj in self.routes:
            collectors[(obj.asset_from, obj.asset_to)] += obj.swap_volume
        return list(sorted(collectors.items(), key=operator.itemgetter(1), reverse=True))
