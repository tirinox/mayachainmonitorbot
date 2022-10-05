from typing import NamedTuple

from services.lib.utils import load_json
from services.lib.w3.token_list import CONTRACT_DATA_BASE_PATH
from services.lib.w3.web3_helper import Web3Helper


class SwapOutArgs(NamedTuple):
    # address target, address finalAsset, address to, uint256 amountOutMin, string memo) ***
    tc_aggregator: str
    target_token: str
    to_address: str
    amount_out_min: int
    tc_memo: str


class TCRouterContract:
    DEFAULT_ABI_ROUTER = f'{CONTRACT_DATA_BASE_PATH}/tc_router_v3.abi.json'

    def __init__(self, helper: Web3Helper):
        self.helper = Web3Helper
        self.contract = helper.w3.eth.contract(abi=load_json(self.DEFAULT_ABI_ROUTER))

    def decode_input(self, input_str):
        func, args_dic = self.contract.decode_function_input(input_str)
        args = None
        if func.fn_name == 'transferOutAndCall':
            args = SwapOutArgs(
                tc_aggregator=args_dic.get('aggregator'),
                target_token=args_dic.get('finalToken'),
                to_address=args_dic.get('to'),
                amount_out_min=args_dic.get('amountOutMin'),
                tc_memo=args_dic.get('memo'),
            )
        return func.fn_name, args
