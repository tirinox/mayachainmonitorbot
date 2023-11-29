from dataclasses import dataclass

from services.lib.constants import CACAO_DENOM
from services.lib.date_utils import DAY
from services.lib.money import is_cacao


@dataclass
class TokenTransfer:
    from_addr: str
    to_addr: str
    block: int
    tx_hash: str
    amount: float
    usd_per_asset: float = 1.0
    is_native: bool = False
    asset: str = ''
    comment: str = ''
    memo: str = ''

    @property
    def is_synth(self):
        return self.asset != CACAO_DENOM and '/' in self.asset

    @property
    def usd_amount(self):
        return self.usd_per_asset * self.amount

    def is_from_or_to(self, address):
        return address and (address == self.from_addr or address == self.to_addr)

    @property
    def is_cacao(self):
        return is_cacao(self.asset)

    def rune_amount(self, usd_per_rune):
        return self.usd_amount / usd_per_rune


@dataclass
class TokenCexFlow:
    rune_cex_inflow: float
    rune_cex_outflow: float
    total_transfers: int
    overflow: bool = False
    usd_per_rune: float = 0.0
    period_sec: float = DAY

    @property
    def rune_cex_netflow(self):
        return self.rune_cex_inflow - self.rune_cex_outflow

    @property
    def in_usd(self):
        return self.usd_per_rune * self.rune_cex_inflow

    @property
    def out_usd(self):
        return self.usd_per_rune * self.rune_cex_outflow

    @property
    def netflow_usd(self):
        return self.usd_per_rune * self.rune_cex_netflow
