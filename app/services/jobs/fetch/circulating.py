import asyncio
from typing import NamedTuple, Dict

from services.lib.constants import CACAO_IDEAL_SUPPLY, CACAO_DENOM, cacao_to_float
from services.lib.utils import WithLogger


class ThorRealms:
    RESERVES = 'Reserve'
    STANDBY_RESERVES = 'Standby reserve'

    BONDED = 'Bonded'
    BONDED_NODE = 'Bonded (node)'  # breakdown for every node
    POOLED = 'Pooled'
    CIRCULATING = 'Circulating'

    CEX = 'CEX'
    TREASURY = 'Treasury'

    BURNED = 'Burned'


THOR_ADDRESS_DICT = {
    # Reserves:
    'maya1dheycdevq39qlkxs2a6wuuzyn4aqxhve4hc8sm': (ThorRealms.RESERVES, ThorRealms.RESERVES),

    # Treasury:
    'maya1577sz8j7xnthm3cl3vgfvmdmkrp7dqrhd9tafd': ('MayaFund', ThorRealms.TREASURY),
}


class RuneHoldEntry(NamedTuple):
    address: str
    amount: int
    name: str
    realm: str

    def add_amount(self, amount):
        return self._replace(amount=self.amount + amount)


class CacaoCirculatingSupply(NamedTuple):
    circulating: int
    total: int
    holders: Dict[str, RuneHoldEntry]

    @classmethod
    def zero(cls):
        return cls(0, 0, {})

    def set_holder(self, h: RuneHoldEntry):
        self.holders[h.address] = h

    @property
    def lending_burnt_cacao(self):
        return CACAO_IDEAL_SUPPLY - self.total

    def find_by_realm(self, realms, join_by_name=False):
        if isinstance(realms, str):
            realms = (realms,)
        items = [h for h in self.holders.values() if h.realm in realms]
        if join_by_name:
            name_dict = {}
            for item in items:
                if item.name in name_dict:
                    name_dict[item.name] = name_dict[item.name].add_amount(item.amount)
                else:
                    name_dict[item.name] = item
            return list(name_dict.values())
        return items

    def total_in_realm(self, realms):
        return sum(h.amount for h in self.find_by_realm(realms))

    def __repr__(self) -> str:
        return f"CacaoCirculatingSupply(circulating={self.circulating}, total={self.total}, holders={len(self.holders)})"

    @property
    def in_cex(self):
        return self.total_in_realm(ThorRealms.CEX)

    @property
    def in_cex_percent(self):
        return self.in_cex / self.total * 100

    @property
    def treasury(self):
        return self.total_in_realm(ThorRealms.TREASURY)

    @property
    def treasury_percent(self):
        return self.treasury / self.total * 100

    @property
    def in_reserves(self):
        return self.total_in_realm((ThorRealms.RESERVES, ThorRealms.STANDBY_RESERVES))

    @property
    def bonded(self):
        return self.total_in_realm(ThorRealms.BONDED)

    @property
    def bonded_percent(self):
        return self.bonded / self.total * 100

    @property
    def pooled(self):
        return self.total_in_realm(ThorRealms.POOLED)

    @property
    def pooled_percent(self):
        return self.pooled / self.total * 100

    @property
    def working(self):
        return self.bonded + self.pooled


class CacaoCirculatingSupplyFetcher(WithLogger):
    def __init__(self, session, thor_node, step_sleep=0):
        super().__init__()
        self.session = session
        self.thor_node = thor_node
        self.step_sleep = step_sleep

    async def fetch(self) -> CacaoCirculatingSupply:
        """
        @return: CacaoCirculatingSupply
        """

        cacao_supply = await self.get_cacao_total_supply()
        result = CacaoCirculatingSupply(cacao_supply, cacao_supply, {})

        for address, (wallet_name, realm) in THOR_ADDRESS_DICT.items():
            # No hurry, do it step by step
            await asyncio.sleep(self.step_sleep)

            balance = await self.get_thor_address_balance(address)
            result.set_holder(RuneHoldEntry(address, balance, wallet_name, realm))

        locked_rune = sum(
            [
                w.amount for w in result.holders.values()
                if w.realm in (ThorRealms.RESERVES, ThorRealms.STANDBY_RESERVES)
            ], 0
        )

        return CacaoCirculatingSupply(
            cacao_supply - locked_rune, cacao_supply, result.holders
        )

    @staticmethod
    def get_pure_cacao_from_thor_array(arr):
        if arr:
            thor_rune = next((item['amount'] for item in arr if item['denom'] == CACAO_DENOM), 0)
            return int(cacao_to_float(thor_rune))
        else:
            return 0

    async def get_supply_data(self):
        url_supply = f'{self.thor_node}/cosmos/bank/v1beta1/supply'
        self.logger.debug(f'Get: "{url_supply}"')
        async with self.session.get(url_supply) as resp:
            j = await resp.json()
            items = j['supply']
            return items

    async def get_cacao_total_supply(self):
        items = await self.get_supply_data()
        return self.get_pure_cacao_from_thor_array(items)

    async def get_thor_address_balance(self, address):
        url_balance = f'{self.thor_node}/cosmos/bank/v1beta1/balances/{address}'
        self.logger.debug(f'Get: "{url_balance}"')
        async with self.session.get(url_balance) as resp:
            j = await resp.json()
            return self.get_pure_cacao_from_thor_array(j['balances'])
