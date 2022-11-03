import asyncio
import logging

from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.lib.texts import sep
from tools.lib.lp_common import LpAppFramework


async def my_test_fetcher(app):
    sep()
    # for _ in range(3):
    #     r = await get_thorchain_coin_gecko_info(lp_app.deps.session)
    #     print(f'{len(r)=}')

    mf: RuneMarketInfoFetcher = app.deps.rune_market_fetcher
    print(await mf.get_rune_market_info())
    print(await mf.get_rune_market_info())
    print(await mf.get_rune_market_info())
    sep()
    await asyncio.sleep(10)
    print(await mf.get_rune_market_info())

    print('done')


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app():
        await my_test_fetcher(lp_app)
        # await my_test_price_cache(app)


if __name__ == "__main__":
    asyncio.run(main())
