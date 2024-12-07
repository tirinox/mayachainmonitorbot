from typing import NamedTuple

from services.lib.date_utils import MINUTE

BTC_SYMBOL = 'BTC.BTC'

NATIVE_CACAO_SYMBOL = 'MAYA.CACAO'
CACAO_SYMBOL = NATIVE_CACAO_SYMBOL

RUNE_SYMBOL_DET = 'RUNE-DET'
RUNE_SYMBOL_POOL = 'RUNE-MARKET'
RUNE_SYMBOL_CEX = 'RUNE-MARKET-CEX'

ETH_SYMBOL = 'ETH.ETH'
AVAX_SYMBOL = 'AVAX.AVAX'
RUNE_SYMBOL = 'THOR.RUNE'
ARB_SYMBOL = 'ARB.ARB-0X912CE59144191C1204E64559FE8253A0E49E6548'

ETH_USDT_TEST_SYMBOL = 'ETH.USDT-0XA3910454BF2CB59B8B3A401589A3BACC5CA42306'
ETH_USDT_SYMBOL = 'ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7'
ETH_USDC_SYMBOL = 'ETH.USDC-0XA0B86991C6218B36C1D19D4A2E9EB0CE3606EB48'

KUJI_USK_SYMBOL = 'KUJI.USK'

DOGE_SYMBOL = 'DOGE.DOGE'

CACAO_IDEAL_SUPPLY = 100_000_000
MAYA_IDEAL_SUPPLY = 1_000_000

CACAO_DENOM = 'cacao'
MAYA_DENOM = 'maya'

STABLE_COIN_POOLS_ALL = (
    ETH_USDC_SYMBOL,
    ETH_USDT_SYMBOL,
    KUJI_USK_SYMBOL,
)

MAYA_PREFIX = 'maya'

STABLE_COIN_POOLS = STABLE_COIN_POOLS_ALL


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
    XRD = 'XRD'

    META_ALL = (MAYA, THOR, ETH, KUJI, DASH, ARB, XRD)

    @staticmethod
    def detect_chain(orig_address: str) -> str:
        address = orig_address.lower()
        if address.startswith('0x'):
            return Chains.ETH  # or other EVM chain??
        elif address.startswith('maya') or address.startswith('smaya'):
            return Chains.MAYA
        elif address.startswith('thor') or address.startswith('tthor') or address.startswith('sthor'):
            return Chains.THOR
        elif address.startswith('kujira'):
            return Chains.KUJI
        elif address.startswith('account_rdx'):
            return Chains.XRD
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
        elif chain == Chains.KUJI:
            return 2.2
        elif chain == Chains.XRD:
            return 0
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

MAYA_DECIMALS = 4
MAYA_DIVIDER = float(10 ** MAYA_DECIMALS)
MAYA_DIVIDER_INV = 1.0 / MAYA_DIVIDER

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
    if x == '':
        return 0
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
BOND_MODULE = 'maya17gw75axcnr8747pkanye45pnrwk7p9c3chd5xu'
POOL_MODULE = 'maya1g98cy3n9mmjrpn0sxmn63lztelera37n8yyjwl'
SYNTH_MODULE = 'thor1v8ppstuf6e3x0r4glqc68d5jqcs2tf38cg2q6y'
