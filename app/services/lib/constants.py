from typing import NamedTuple

from services.lib.date_utils import MINUTE

BNB_BNB_SYMBOL = 'BNB.BNB'

BNB_BUSD_SYMBOL = 'BNB.BUSD-BD1'
BNB_BUSD_TEST_SYMBOL = 'BNB.BUSD-BAF'
BNB_BUSD_TEST2_SYMBOL = 'BNB.BUSD-74E'

BNB_BTCB_SYMBOL = 'BNB.BTCB-1DE'
BNB_BTCB_TEST_SYMBOL = 'BNB.BTCB-101'
BTC_SYMBOL = 'BTC.BTC'

BCH_SYMBOL = 'BCH.BCH'

NATIVE_CACAO_SYMBOL = 'MAYA.CACAO'
CACAO_SYMBOL = NATIVE_CACAO_SYMBOL

RUNE_SYMBOL_DET = 'RUNE-DET'
RUNE_SYMBOL_POOL = 'RUNE-MARKET'
RUNE_SYMBOL_CEX = 'RUNE-MARKET-CEX'

BNB_ETHB_SYMBOL = 'BNB.ETH-1C9'
BNB_ETHB_TEST_SYMBOL = 'BNB.ETH-D5B'
ETH_SYMBOL = 'ETH.ETH'
AVAX_SYMBOL = 'AVAX.AVAX'
ARB_SYMBOL = 'ARB.ARB-0X912CE59144191C1204E64559FE8253A0E49E6548'

BNB_USDT_SYMBOL = 'BNB.USDT-6D8'
BNB_USDT_TEST_SYMBOL = 'BNB.USDT-DC8'
ETH_USDT_TEST_SYMBOL = 'ETH.USDT-0XA3910454BF2CB59B8B3A401589A3BACC5CA42306'
ETH_USDT_SYMBOL = 'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7'
ETH_USDC_SYMBOL = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'
ETH_DAI_SYMBOL = 'ETH.DAI-0X6B175474E89094C44DA98B954EEDEAC495271D0F'
AVAX_USDC_SYMBOL = 'AVAX.USDC-0XB97EF9EF8734C71904D8002F8B6BC66DD9C48A6E'
BSC_BUSD_SYMBOL = 'BSC.BUSD-0XE9E7CEA3DEDCA5984780BAFC599BD69ADD087D56'
BSC_USDC_SYMBOL = 'BSC.USDC-0X8AC76A51CC950D9822D68B83FE1AD97B32CD580D'
ETH_GUSD_SYMBOL = 'ETH.GUSD-0X056FD409E1D7A124BD7017459DFEA2F387B6D5CD'
ETH_LUSD_SYMBOL = 'ETH.LUSD-0X5F98805A4E8BE255A32880FDEC7F6728C6568BA0'

DOGE_SYMBOL = 'DOGE.DOGE'

CACAO_IDEAL_SUPPLY = 100_000_000
MAYA_IDEAL_SUPPLY = 1_000_000

CACAO_DENOM = 'cacao'
MAYA_DENOM = 'maya'

STABLE_COIN_POOLS_ALL = (
    BNB_BUSD_SYMBOL,
    BSC_BUSD_SYMBOL,
    ETH_USDC_SYMBOL,
    BSC_USDC_SYMBOL,
    AVAX_USDC_SYMBOL,
    ETH_USDT_SYMBOL,
    ETH_DAI_SYMBOL,
    ETH_GUSD_SYMBOL,
    ETH_LUSD_SYMBOL,
)

MAYA_PREFIX = 'maya'

STABLE_COIN_POOLS = STABLE_COIN_POOLS_ALL
# STABLE_COIN_POOLS = STABLE_COIN_BNB_POOLS


DEFAULT_CEX_NAME = 'Binance'
DEFAULT_CEX_BASE_ASSET = 'USDT'


def is_stable_coin(pool):
    return pool in STABLE_COIN_POOLS_ALL


class Chains:
    MAYA = 'MAYA'
    THOR = 'THOR'
    ETH = 'ETH'
    BTC = 'BTC'
    KUJI = 'KUJI'
    DASH = 'DASH'
    ARB = 'ARB'

    META_ALL = (MAYA, THOR, ETH, KUJI, DASH, ARB)

    @staticmethod
    def detect_chain(orig_address: str) -> str:
        address = orig_address.lower()
        if address.startswith('0x'):
            return Chains.ETH  # or other EVM chain??
        elif address.startswith('maya') or address.startswith('smaya'):
            return Chains.MAYA
        elif address.startswith('thor') or address.startswith('tthor') or address.startswith('sthor'):
            return Chains.THOR
        elif address.startswith('kujija'):
            return Chains.KUJI
        return ''

    @staticmethod
    def block_time_default(chain: str) -> float:
        if chain == Chains.MAYA:
            return THOR_BLOCK_TIME
        elif chain == Chains.ETH:
            return 13
        elif chain == Chains.BTC:
            return 10 * MINUTE
        elif chain == Chains.DASH:
            return 2.6 * MINUTE
        elif chain == Chains.THOR:
            return THOR_BLOCK_TIME
        elif chain == Chains.ARB:
            return 0.26
        elif chainn == Chains.KUJI:
            return 2.2
        return 0.01

    @staticmethod
    def web3_chain_id(chain: str) -> int:
        if chain == Chains.ETH:
            return 0x1
        elif chain == Chains.ARB:
            return 42161

    @staticmethod
    def l1_asset(chain: str) -> str:
        assert chain in Chains.META_ALL
        return f'{chain}.{chain}'


class NetworkIdents:
    TESTNET_MULTICHAIN = 'testnet-multi'
    CHAOSNET_MULTICHAIN = 'chaosnet-multi'
    MAINNET = 'mainnet'
    STAGENET_MULTICHAIN = 'stagenet-multi'

    @classmethod
    def is_test(cls, network: str):
        return 'testnet' in network

    @classmethod
    def is_live(cls, network: str):
        return not cls.is_test(network)

    @classmethod
    def is_multi(cls, network: str):
        return 'multi' in network or network == cls.MAINNET


RUNE_DECIMALS = 8
THOR_DIVIDER = float(10 ** RUNE_DECIMALS)
THOR_DIVIDER_INV = 1.0 / THOR_DIVIDER

CACAO_DECIMALS = 10
CACAO_DIVIDER = float(10 ** CACAO_DECIMALS)
CACAO_DIVIDER_INV = 1.0 / CACAO_DIVIDER

THOR_BLOCK_TIME = 6.0  # seconds. 10 blocks / minute
THOR_BLOCK_SPEED = 1 / THOR_BLOCK_TIME
THOR_BLOCKS_PER_MINUTE = MINUTE * THOR_BLOCK_SPEED

THOR_BASIS_POINT_MAX = 10_000


def bp_to_float(bp):
    return int(bp) / THOR_BASIS_POINT_MAX


def bp_to_percent(bp):
    return bp_to_float(bp) * 100.0


def thor_to_float(x) -> float:
    return int(x) * THOR_DIVIDER_INV


def float_to_thor(x: float) -> int:
    return int(x * THOR_DIVIDER)


def cacao_to_float(x) -> float:
    return int(x) * CACAO_DIVIDER_INV


def float_to_cacao(x: float) -> int:
    return int(x * CACAO_DIVIDER)


class THORPort:
    class TestNet(NamedTuple):
        RPC = 26657
        P2P = 26656
        BIFROST = 6040
        BIFROST_P2P = 5040
        NODE = 1317

    class StageNet(NamedTuple):
        RPC = 26657
        P2P = 26656
        BIFROST = 6040
        BIFROST_P2P = 5040
        NODE = 1317

    class MainNet(NamedTuple):
        RPC = 27147
        P2P = 27146
        BIFROST = 6040
        BIFROST_P2P = 5040
        NODE = 1317

    FAMILIES = {
        NetworkIdents.TESTNET_MULTICHAIN: TestNet,
        NetworkIdents.STAGENET_MULTICHAIN: StageNet,
        NetworkIdents.MAINNET: MainNet,
        NetworkIdents.CHAOSNET_MULTICHAIN: MainNet,
    }

    @classmethod
    def get_port_family(cls, network_ident):
        return cls.FAMILIES.get(network_ident, cls.MainNet)


BLOCKS_PER_YEAR = 5_256_000

SAVERS_BEGIN_BLOCK = 8_195_056

HTTP_CLIENT_ID = 'mayainfobot'

# fixme
THORCHAIN_BIRTHDAY = 1618058210955 * 0.001  # 2021-04-10T12:36:50.955991742Z

DEFAULT_RUNE_FEE = 2000000  # fixme!

DEFAULT_RESERVE_ADDRESS = 'maya1dheycdevq39qlkxs2a6wuuzyn4aqxhve4hc8sm'
BOND_MODULE = 'thor17gw75axcnr8747pkanye45pnrwk7p9c3cqncsv'
POOL_MODULE = 'thor1g98cy3n9mmjrpn0sxmn63lztelera37n8n67c0'
SYNTH_MODULE = 'thor1v8ppstuf6e3x0r4glqc68d5jqcs2tf38cg2q6y'
