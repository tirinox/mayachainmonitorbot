import copy
import dataclasses
import json
import logging
import math
from _operator import attrgetter
from dataclasses import dataclass
from operator import attrgetter
from typing import List, Dict, NamedTuple, Optional

from aiothornode.types import ThorPool

from services.lib.constants import thor_to_float, BLOCKS_PER_YEAR, SAVERS_BEGIN_BLOCK


def pool_share(rune_depth, asset_depth, my_units, pool_total_units):
    if not pool_total_units:
        return 0, 0
    rune_share = (rune_depth * my_units) / pool_total_units
    asset_share = (asset_depth * my_units) / pool_total_units
    return rune_share, asset_share


class PoolUnitsAdjustment(NamedTuple):
    delta_units: int
    new_units: int


@dataclass
class PoolInfo:
    asset: str

    balance_asset: int
    balance_rune: int
    pool_units: int

    status: str

    usd_per_asset: float = 0.0
    pool_apy: float = 0.0
    synth_supply: int = 0
    synth_units: int = 0
    units: int = 0  # synth + pool_units
    volume_24h: int = 0

    savers_depth: int = 0
    savers_units: int = 0

    DEPRECATED_BOOTSTRAP = 'bootstrap'
    DEPRECATED_ENABLED = 'enabled'
    SUSPENDED = 'suspended'
    AVAILABLE = 'available'  # enabled
    STAGED = 'staged'  # bootstrap

    def percent_share(self, runes, correction=0.0):
        full_balance_rune = 2 * thor_to_float(self.balance_rune) + correction
        return runes / full_balance_rune * 100.0

    def get_share_rune_and_asset(self, units: int) -> (float, float):
        r, a = pool_share(self.balance_rune, self.balance_asset, my_units=units, pool_total_units=self.units)
        return thor_to_float(r), thor_to_float(a)

    def total_my_capital_of_pool_in_rune(self, units: int) -> float:
        r, _ = self.get_share_rune_and_asset(units)
        return r * 2.0

    @classmethod
    def dummy(cls):
        return cls('', 1, 1, 1, cls.DEPRECATED_BOOTSTRAP)

    def copy(self):
        return copy.copy(self)

    def fill_usd_per_asset(self, usd_per_rune):
        self.usd_per_asset = self.runes_per_asset / usd_per_rune if usd_per_rune else 0.0

    @property
    def asset_per_rune(self):
        return self.balance_asset / self.balance_rune

    @property
    def runes_per_asset(self):
        return self.balance_rune / self.balance_asset

    @staticmethod
    def is_status_enabled(status):
        return status.lower() in (PoolInfo.DEPRECATED_ENABLED, PoolInfo.AVAILABLE)  # v2 compatibility

    @property
    def is_enabled(self):
        return self.is_status_enabled(self.status)

    def usd_depth(self, usd_per_rune):
        pool_depth_usd = 2 * thor_to_float(self.balance_rune) * usd_per_rune  # note: * 2 as in off. frontend
        return pool_depth_usd

    def calculate_pool_units_rune_asset(self, add_rune: int, add_asset: int) -> PoolUnitsAdjustment:
        r0, a0 = self.balance_rune, self.balance_asset
        r, a = add_rune, add_asset

        if r0 + r == 0 or a0 + a == 0:
            logging.warning(f'total rune or asset is zero: {r0 + r = }, {a0 + a = }!')
            return PoolUnitsAdjustment(0, 0)
        if r0 == 0 or a0 == 0:
            return PoolUnitsAdjustment(add_rune, add_rune)

        slip_adjustment = 1.0 - abs((r0 * a - r * a0) / ((r + r0) * (a + a0)))

        delta_units = int(self.units * (a * r0 + a0 * r) / (2 * r0 * a0) * slip_adjustment)
        new_pool_unit = delta_units + self.units

        return PoolUnitsAdjustment(delta_units, new_pool_unit)

    @classmethod
    def from_dict_brief(cls, j):
        try:
            return cls(**j)
        except TypeError:
            pass

    def as_dict_brief(self):
        return dataclasses.asdict(self)

    @property
    def rune_price(self):
        return self.usd_per_asset / self.runes_per_asset

    @property
    def usd_volume_24h(self):
        """ Used for top_pools """
        return thor_to_float(self.volume_24h) * self.rune_price

    @property
    def total_liquidity(self):
        """ Used for top_pools """
        return 2.0 * thor_to_float(self.balance_rune) * self.rune_price

    def get_synth_cap_in_asset_float(self, max_synth_per_pool_depth=0.15):
        return thor_to_float(self.balance_asset * max_synth_per_pool_depth * 2.0)

    def how_much_savings_you_can_add(self, pool_synth_supply, max_synth_per_asset_ratio=0.3):
        cap = self.get_synth_cap_in_asset_float(max_synth_per_asset_ratio)
        return max(0.0, cap - pool_synth_supply)

    @property
    def savers_depth_float(self):
        return thor_to_float(self.savers_depth)

    @property
    def saver_growth_rune(self):
        return thor_to_float((self.savers_depth - self.savers_units) * self.runes_per_asset)

    def get_savers_apr(self, block_no, blocks_per_year=BLOCKS_PER_YEAR) -> float:
        if not self.savers_units:
            return 0.0
        saver_growth = (self.savers_depth - self.savers_units) / self.savers_depth
        return (saver_growth / (block_no - SAVERS_BEGIN_BLOCK)) * blocks_per_year

    @property
    def synth_asset_name(self):
        return self.asset.replace('.', '/')


@dataclass
class LPPosition:
    pool: str
    liquidity_units: int
    liquidity_total: int
    rune_balance: float
    asset_balance: float
    usd_per_rune: float
    usd_per_asset: float
    total_usd_balance: float

    @classmethod
    def create(cls, pool: PoolInfo, my_units: int, usd_per_rune: float):
        usd_per_asset = usd_per_rune / pool.asset_per_rune
        return cls(
            pool=pool.asset,
            liquidity_units=my_units,
            liquidity_total=pool.units if pool.units else pool.pool_units,
            rune_balance=thor_to_float(pool.balance_rune),
            asset_balance=thor_to_float(pool.balance_asset),
            usd_per_rune=usd_per_rune,
            usd_per_asset=usd_per_asset,
            total_usd_balance=thor_to_float(pool.balance_rune) * usd_per_rune * 2.0
        )


@dataclass
class PoolInfoHistoricEntry:
    asset_depth: int = 0
    rune_depth: int = 0
    asset_price: float = 0.0
    asset_price_usd: float = 0.0
    liquidity_units: int = 0
    synth_units: int = 0
    units: int = 0
    timestamp: int = 0

    def to_pool_info(self, asset) -> PoolInfo:
        return PoolInfo(
            asset,
            self.asset_depth,
            self.rune_depth,
            self.liquidity_units,
            PoolInfo.DEPRECATED_ENABLED,
            units=self.liquidity_units,
        )


PoolInfoMap = Dict[str, PoolInfo]


def parse_thor_pools(thor_pools: List[ThorPool]) -> PoolInfoMap:
    """
    Converts a list of ThorPool from THORNode to PoolInfoMap
    @attention ThorPool is missing some high-level stats like APY
    @param thor_pools:
    @return:
    """
    return {
        p.asset: PoolInfo(
            p.asset,
            p.balance_asset, p.balance_rune,
            int(p.lp_units), p.status,
            synth_units=int(p.synth_units),
            units=int(p.pool_units),
            savers_depth=p.savers_depth,
            savers_units=p.savers_units,
        )
        for p in thor_pools
    }


class PoolChange(NamedTuple):
    pool_name: str
    old_status: str
    new_status: str


class PoolChanges(NamedTuple):
    pools_added: List[PoolChange]
    pools_removed: List[PoolChange]
    pools_changed: List[PoolChange]

    @property
    def any_changed(self):
        return self.pools_changed or self.pools_added or self.pools_removed


class PoolMapPair:
    def __init__(self, curr: PoolInfoMap, prev: PoolInfoMap):
        self.pool_detail_dic: PoolInfoMap = curr or {}
        self.pool_detail_dic_prev: PoolInfoMap = prev or {}

    BY_VOLUME_24h = 'usd_volume_24h'
    BY_DEPTH = 'total_liquidity'
    BY_APY = 'pool_apy'

    @staticmethod
    def bad_value(x: float):
        return math.isinf(x) or math.isnan(x)

    def get_top_pools(self, criterion: str, n=None, descending=True) -> List[PoolInfo]:
        pools = self.pool_detail_dic.values()
        criterion = str(criterion)

        if criterion in (self.BY_APY, self.BY_VOLUME_24h):
            pools = filter(lambda p: p.is_enabled, pools)
        pools = filter(lambda p: not self.bad_value(getattr(p, criterion)), pools)

        pool_list = list(pools)
        pool_list.sort(key=attrgetter(criterion), reverse=descending)
        return pool_list if n is None else pool_list[:n]

    def get_value(self, pool_name, attr_name):
        if pool_name not in self.pool_detail_dic:
            raise KeyError(f'no pool: {pool_name}')

        curr_pool = self.pool_detail_dic[pool_name]
        return float(getattr(curr_pool, attr_name))

    def get_difference_percent(self, pool_name, attr_name):
        curr_value = self.get_value(pool_name, attr_name)

        prev_pool = self.pool_detail_dic_prev.get(pool_name)
        if not prev_pool:
            return None

        prev_value = float(getattr(prev_pool, attr_name))
        if prev_value == 0.0:
            return None

        if attr_name == self.BY_APY:
            return curr_value - prev_value
        else:
            return (curr_value / prev_value - 1.0) * 100.0

    @property
    def empty(self):
        return not self.pool_detail_dic


class SaverVault(NamedTuple):
    asset: str
    number_of_savers: int
    total_asset_saved: float
    total_asset_saved_usd: float
    apr: float
    asset_cap: float  # == 2 * pool.asset_balance
    runes_earned: float
    synth_supply: float

    @property
    def percent_of_cap_filled(self):
        return self.synth_supply / self.asset_cap * 100.0 if self.asset_cap else 0.0

    @property
    def usd_per_asset(self):
        return self.total_asset_saved_usd / self.total_asset_saved

    def calc_asset_earned(self, pool_map: PoolInfoMap):
        if pool_map and (pool := pool_map.get(self.asset)):
            return pool.asset_per_rune * self.runes_earned
        else:
            return 0.0

    @staticmethod
    def calc_total_saved_usd(asset, total_asset_saved, pool_map: PoolInfoMap):
        if pool_map and (pool := pool_map.get(asset)):
            price = pool.usd_per_asset
            result = total_asset_saved * price if price else 0.0
        else:
            result = 0.0
        return result


@dataclass
class AllSavers:
    total_unique_savers: int
    vaults: List[SaverVault]

    def fill_total_usd(self, pool_map: PoolInfoMap):
        self.vaults = [
            v._replace(total_asset_saved_usd=v.calc_total_saved_usd(v.asset, v.total_asset_saved, pool_map))
            for v in self.vaults
        ]

    @property
    def total_usd_saved(self) -> float:
        return sum(s.total_asset_saved_usd for s in self.vaults)

    @property
    def apr_list(self):
        return [s.apr for s in self.vaults]

    @property
    def average_apr(self) -> float:
        if not self.vaults:
            return 0.0
        return sum(self.apr_list) / len(self.vaults)

    @property
    def min_apr(self):
        return min(self.apr_list)

    @property
    def max_apr(self):
        return max(self.apr_list)

    @property
    def as_dict(self):
        d = dataclasses.asdict(self)
        d['vaults'] = [v._asdict() for v in self.vaults]
        return d

    @classmethod
    def load_from_ts_points(cls, point) -> Optional['AllSavers']:
        try:
            j = json.loads(point['json'])
        except (json.JSONDecodeError, KeyError, TypeError):
            return

        try:
            savers = cls(**j)
            # noinspection PyArgumentList
            savers.vaults = [SaverVault(**v) for v in savers.vaults]
            return savers
        except TypeError:
            return

    def sort_vaults(self, key='apr', reverse=False):
        self.vaults.sort(key=attrgetter(key), reverse=reverse)
        return self

    def get_top_vaults(self, criterion: str, n=None, descending=True) -> List[SaverVault]:
        vault_list = list(self.vaults)
        vault_list.sort(key=attrgetter(criterion), reverse=descending)
        return vault_list if n is None else vault_list[:n]

    @property
    def total_rune_earned(self):
        return sum(p.runes_earned for p in self.vaults)

    @property
    def overall_fill_cap_percent(self):
        # fixme
        overall_saved = sum(p.total_asset_saved * p.usd_per_asset for p in self.vaults)
        overall_cap = sum(p.asset_cap * p.usd_per_asset for p in self.vaults)
        return overall_saved / overall_cap * 100.0 if overall_cap else 0.0
