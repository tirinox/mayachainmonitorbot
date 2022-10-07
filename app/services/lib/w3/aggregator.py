import typing
from typing import Optional

from services.lib.constants import Chains
from services.lib.depcont import DepContainer
from services.lib.w3.aggr_contract import AggregatorContract
from services.lib.w3.erc20_contract import ERC20Contract
from services.lib.w3.router_contract import TCRouterContract
from services.lib.w3.token_list import StaticTokenList, TokenListCached
from services.lib.w3.token_record import AVAX_CHAIN_ID, ETH_CHAIN_ID, TokenRecord
from services.lib.w3.web3_helper import Web3HelperCached


class AmountToken(typing.NamedTuple):
    amount: float
    token: TokenRecord


class AggregatorDataExtractor:
    def create_token_list(self, static_list_path, chain_id) -> TokenListCached:
        static_list = StaticTokenList(static_list_path, chain_id)
        return TokenListCached(self.deps.db, self.w3, static_list)

    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.w3 = Web3HelperCached(deps.cfg, deps.db)

        self.token_lists = {
            Chains.AVAX: self.create_token_list(StaticTokenList.DEFAULT_TOKEN_LIST_AVAX_PATH, AVAX_CHAIN_ID),
            Chains.ETH: self.create_token_list(StaticTokenList.DEFAULT_TOKEN_LIST_ETH_PATH, ETH_CHAIN_ID),
            # todo: add more lists in the future here
        }

        self.router = TCRouterContract(self.w3)
        self.aggregator = AggregatorContract(self.w3)

    @staticmethod
    def make_pair(amount, token_info: TokenRecord):
        return AmountToken(
            amount / 10 ** token_info.decimals,
            token_info,
        )

    async def decode_swap_out(self, tx_hash, chain: str) -> Optional[AmountToken]:
        tx = await self.w3.get_transaction(tx_hash)

        swap_out_call = self.router.decode_input(tx['input'])

        token_list: TokenListCached = self.token_lists[chain]

        receipt_data = await self.w3.get_transaction_receipt(tx_hash)
        token = ERC20Contract(self.w3, swap_out_call.target_token, token_list.chain_id)
        transfers = token.get_transfer_events_from_receipt(receipt_data, filter_by_receiver=swap_out_call.to_address)
        final_transfer = transfers[0]
        amount = final_transfer['args']['value']

        token_info = await token_list.resolve_token(swap_out_call.target_token)
        return self.make_pair(amount, token_info)

    async def decode_swap_in(self, tx_hash, chain: str) -> Optional[AmountToken]:
        tx = await self.w3.get_transaction(tx_hash)
        swap_in_call = self.aggregator.decode_input(tx['input'])

        token_list: TokenListCached = self.token_lists[chain]
        token_info = await token_list.resolve_token(swap_in_call.from_token)
        return self.make_pair(swap_in_call.amount, token_info)
