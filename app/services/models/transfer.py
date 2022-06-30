from dataclasses import dataclass


@dataclass
class RuneTransfer:
    from_addr: str
    to_addr: str
    block: int
    tx_hash: str
    amount: float
    usd_per_rune: float = 1.0
    is_native: bool = False
    asset: str = ''
    comment: str = ''

    @property
    def is_synth(self):
        return self.asset != 'rune' and '/' in self.asset

    @property
    def usd_amount(self):
        return self.usd_per_rune * self.amount

    def is_from_or_to(self, address):
        return address and (address == self.from_addr or address == self.to_addr)

    @property
    def is_rune(self):
        return self.asset.lower() == 'rune'


@dataclass
class RuneCEXFlow:
    rune_cex_inflow: float
    rune_cex_outflow: float
    total_transfers: int
    overflow: bool = False
    usd_per_rune: float = 0.0

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
