import asyncio

from services.lib.midgard.name_service import NameService
from tools.lib.lp_common import LpAppFramework

NAMES = {
    'panda': 'thor1t3mkwu79rftp4uqf3xrpf5qwczp97jg9jul53p',
    'vitalik': 'thor1e5qhhm93j380xksqpamh74mva2ee6c3wmmrrz4'
}


async def t_names1(lp_app: LpAppFramework):
    ns = lp_app.deps.name_service
    n = await ns.lookup_name_by_address('thor17gw75axcnr8747pkanye45pnrwk7p9c3cqncsv')
    print(n)

    n = await ns.lookup_name_by_address('thorNONAME')
    assert n is None

    n = await ns.lookup_address_by_name('Binance Hot')
    assert n.startswith('thor')
    print(n)


async def t_exists(ns: NameService):
    # r = await ns.safely_load_thornames_from_address_set([NAMES['vitalik']])
    # print(r)
    # r1 = await ns.lookup_name_by_address('thor1e5qhhm93j380xksqpamh74mva2ee6c3wmmrrz4')
    # print(r1)
    r = await ns.lookup_thorname_by_name('panda', forced=True)
    print(r)
    r = await ns.lookup_thorname_by_name('vitalik')
    print(r)


async def t_not_exists(ns: NameService):
    # r = await ns.safely_load_thornames_from_address_set(['fljlfjwljweobo', 'lkelejljjwejlweqq'])
    # print(r)

    r1 = await ns.lookup_name_by_address('thorNOADDRESS')
    print(r1)


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        ns = app.deps.name_service
        await t_exists(ns)
        # await t_not_exists(ns)


if __name__ == '__main__':
    asyncio.run(run())