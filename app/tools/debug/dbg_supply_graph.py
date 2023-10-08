import asyncio
import dataclasses
import os
from pprint import pprint

from localization.eng_base import BaseLocalization
from localization.languages import Language
from localization.manager import LocalizationManager
from services.dialog.picture.supply_picture import SupplyPictureGenerator
from services.jobs.fetch.last_block import LastBlockFetcher
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.lib.date_utils import today_str
from services.lib.draw_utils import img_to_bio
from services.lib.utils import json_cached_to_file_async, load_pickle, save_pickle
from services.models.price import RuneMarketInfo
from services.notify.channel import BoardMessage
from services.notify.types.block_notify import LastBlockStore
from tools.debug.dbg_discord import debug_prepare_discord_bot
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


@json_cached_to_file_async("../temp/supply_info_2.json")
async def get_rune_supply(app: LpAppFramework):
    rune_market_info: RuneMarketInfo = await app.deps.rune_market_fetcher.get_rune_market_info()
    return dataclasses.asdict(rune_market_info.supply_info)

#
# @json_cached_to_file_async("../temp/net_stats1.json")
# async def get_network_stats(app: LpAppFramework):
#     ns_fetcher = NetworkStatisticsFetcher(app.deps)
#     data = await ns_fetcher.fetch()
#     return dataclasses.asdict(data)


async def get_supply_pic(app, cached=True):
    loc_man: LocalizationManager = app.deps.loc_man
    loc = loc_man.get_from_lang(Language.ENGLISH)

    if cached:
        cache_path = '../temp/data_for_sup_pic.pickle'
        try:
            net_stats, rune_market_info = load_pickle(cache_path)
        except Exception as e:
            print(e)
            net_stats, rune_market_info = await debug_get_rune_market_data(app)
            save_pickle(cache_path, (net_stats, rune_market_info))
    else:
        net_stats, rune_market_info = await debug_get_rune_market_data(app)

    pic_gen = SupplyPictureGenerator(loc, rune_market_info.supply_info, net_stats)

    return await pic_gen.get_picture()


async def debug_get_rune_market_data(app):
    d = app.deps

    await app.deps.pool_fetcher.fetch()

    # ns_raw = await get_network_stats(app)
    # ns = NetworkStats(**ns_raw)

    d.last_block_fetcher = LastBlockFetcher(d)
    d.last_block_store = LastBlockStore(d)
    d.last_block_fetcher.add_subscriber(d.last_block_store)
    await d.last_block_fetcher.run_once()

    fetcher_stats = NetworkStatisticsFetcher(d)
    d.net_stats = await fetcher_stats.fetch()

    await d.node_info_fetcher.run_once()

    await d.mimir_const_fetcher.fetch()  # get constants beforehand

    rune_market_info: RuneMarketInfo = await d.rune_market_fetcher.get_rune_market_info()
    return d.net_stats, rune_market_info


def save_and_show_supply_pic(pic, show=True):
    filepath = '../temp/supply.png'
    with open(filepath, 'wb') as f:
        pic_bio = img_to_bio(pic, os.path.basename(filepath))
        f.write(pic_bio.getbuffer())

    if show:
        os.system(f'open "{filepath}"')


async def post_supply_to_discord(app: LpAppFramework, pic):
    await debug_prepare_discord_bot(app)

    async def supply_pic_gen(loc: BaseLocalization):
        return BoardMessage.make_photo(pic, loc.SUPPLY_PIC_CAPTION, f'rune_supply_{today_str()}.png')

    await app.deps.broadcaster.notify_preconfigured_channels(supply_pic_gen)

    await asyncio.sleep(10)


async def my_demo_market_info(app: LpAppFramework):
    info = await app.deps.rune_market_fetcher.get_rune_market_info()
    pprint(info)


async def debug_network_stats(app: LpAppFramework):
    ns_fetcher = NetworkStatisticsFetcher(app.deps)
    data = await ns_fetcher.fetch()
    pprint(data)


async def run():
    app = LpAppFramework()
    async with app(brief=True):

        # await app.deps.pool_fetcher.fetch()

        pic, _ = await get_supply_pic(app)
        save_and_show_pic(pic, show=True, name='supply')

        # await post_supply_to_discord(app, pic)
        # await my_demo_market_info(app)

        # await debug_network_stats(app)


if __name__ == '__main__':
    asyncio.run(run())
