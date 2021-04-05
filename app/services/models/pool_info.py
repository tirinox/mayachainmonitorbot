from dataclasses import dataclass

from services.lib.constants import THOR_DIVIDER_INV


@dataclass
class PoolInfo:
    asset: str
    price: float  # assets per 1 rune

    balance_asset: int
    balance_rune: int
    pool_units: int

    status: str

    BOOTSTRAP = 'Bootstrap'
    ENABLED = 'Enabled'

    def percent_share(self, runes):
        return runes / (2 * self.balance_rune * THOR_DIVIDER_INV) * 100.0

    @classmethod
    def dummy(cls):
        return cls('', 1, 1, 1, 1, cls.BOOTSTRAP)

    @property
    def asset_per_rune(self):
        return self.balance_asset / self.balance_rune

    @property
    def runes_per_asset(self):
        return self.balance_rune / self.balance_asset

    @property
    def is_enabled(self):
        return self.status == self.ENABLED

    def usd_depth(self, dollar_per_rune):
        pool_depth_usd = 2 * self.balance_rune * THOR_DIVIDER_INV * dollar_per_rune  # note: * 2 as in off. frontend
        return pool_depth_usd

    @classmethod
    def from_dict(cls, j):
        balance_asset = int(j['balance_asset'])
        balance_rune = int(j['balance_rune'])
        return cls(asset=j['asset'],
                   price=(balance_asset / balance_rune),
                   balance_asset=balance_asset,
                   balance_rune=balance_rune,
                   pool_units=int(j['pool_units']),
                   status=j['status'])

    def as_dict(self):
        return {
            'balance_asset': str(self.balance_asset),
            'balance_rune': str(self.balance_rune),
            'pool_units': str(self.pool_units),
            'asset': self.asset,
            'status': self.status
        }

    def create_lp_position(self, my_units: int, usd_per_rune: float):
        usd_per_asset = usd_per_rune / self.asset_per_rune
        return {
            "pair": self.asset,
            "liquidityTokenBalance": my_units * THOR_DIVIDER_INV,
            "liquidityTokenTotalSupply": self.pool_units * THOR_DIVIDER_INV,
            "reserve0": self.balance_rune * THOR_DIVIDER_INV,
            "reserve1": self.balance_asset * THOR_DIVIDER_INV,
            "reserveUSD": self.balance_rune * THOR_DIVIDER_INV * usd_per_rune * 2.0,
            "token0PriceUSD": usd_per_rune,
            "token1PriceUSD": usd_per_asset,
        }


@dataclass
class PoolInfoHistoricEntry:
    asset_depth: int = 0
    rune_depth: int = 0
    asset_price: float = 0.0
    asset_price_usd: float = 0.0
    liquidity_units: int = 0
