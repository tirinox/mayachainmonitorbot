import asyncio

from tools.lib.lp_common import LpAppFramework

NAMES = {
    'panda': 'thor1t3mkwu79rftp4uqf3xrpf5qwczp97jg9jul53p',
    'vitalik': 'thor1e5qhhm93j380xksqpamh74mva2ee6c3wmmrrz4'
}


async def run():
    app = LpAppFramework()
    async with app(brief=True):
        ns = app.deps.name_service

        r = await ns.safely_load_thornames_from_address_set([NAMES['vitalik']])
        print(r)
        r1 = await ns.lookup_name_by_address('thor1e5qhhm93j380xksqpamh74mva2ee6c3wmmrrz4')
        print(r1)


if __name__ == '__main__':
    asyncio.run(run())
