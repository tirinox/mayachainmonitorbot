from services.lib.constants import NetworkIdents, Chains
from services.lib.money import Asset


def get_explorer_url_to_address(network_id, pool_or_chain: str, address: str):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        return f"https://runescan.io/address/{address}"
    elif chain == Chains.MAYA:
        return f"https://www.mayascan.org/address/{address}"
    elif chain == Chains.ETH:
        return f'https://etherscan.io/address/{address}' if is_live else \
            f'https://ropsten.etherscan.io/address/{address}'
    elif chain == Chains.BTC:
        return f'https://www.blockchain.com/btc/address/{address}' if is_live else \
            f'https://www.blockchain.com/btc-testnet/address/{address}'
    elif chain == Chains.KUJI:
        return f'https://atomscan.com/kujira/accounts/{address}'
    elif chain == Chains.DASH:
        return f'https://explorer.dash.org/insight/address/{address}'
    elif chain == Chains.ARB:
        return f'https://arbiscan.io/address/{address}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'


def add_0x(tx_id: str):
    if not tx_id.startswith('0x') and not tx_id.startswith('0X'):
        tx_id = '0x' + tx_id
    return tx_id


def get_explorer_url_to_tx(network_id, pool_or_chain: str, tx_id: str):
    chain = Asset(pool_or_chain).first_filled_component

    is_live = not NetworkIdents.is_test(network_id)
    if chain == Chains.THOR:
        return f"https://runescan.io/tx/{tx_id}"
    elif chain == Chains.MAYA:
        return f"https://www.mayascan.org/tx/{tx_id}"
    elif chain == Chains.ETH:
        tx_id = add_0x(tx_id)
        return f'https://etherscan.io/tx/{tx_id}' if is_live else \
            f'https://ropsten.etherscan.io/tx/{tx_id}'
    elif chain == Chains.BTC:
        return f'https://www.blockchain.com/btc/tx/{tx_id}' if is_live else \
            f'https://www.blockchain.com/btc-testnet/tx/{tx_id}'
    elif chain == Chains.KUJI:
        return f'https://atomscan.com/kujira/transactions/{tx_id}'
    elif chain == Chains.DASH:
        return f'https://explorer.dash.org/insight/tx/{tx_id}'
    elif chain == Chains.ARB:
        return f'https://arbiscan.io/tx/{tx_id}'
    else:
        url = f'https://www.google.com/search?q={chain}+explorer'
        return url if is_live else f'{url}+test'


def get_explorer_url_for_node(address: str):
    return f'https://www.mayascan.org/network'


def get_pool_url(pool_name):
    return f'https://www.mayascan.org/pools/{pool_name}'


def get_mayacan_address_url(network: str, address: str):
    return f'https://www.mayascan.org/address/{address}'


def get_ip_info_link(ip_address):
    return f'https://www.infobyip.com/ip-{ip_address}.html'
