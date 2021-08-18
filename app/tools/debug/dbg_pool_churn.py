import asyncio
import logging
from copy import deepcopy

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import ParseMode
from aiothornode.connector import ThorConnector
from aiothornode.env import TEST_NET_ENVIRONMENT_MULTI_1

from localization import LocalizationManager
from services.jobs.fetch.pool_price import PoolPriceFetcher, PoolInfoFetcherMidgard
from services.lib.config import Config
from services.lib.constants import get_thor_env_by_network_id
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo
from services.models.price import LastPriceHolder
from services.notify.broadcast import Broadcaster
from services.notify.types.pool_churn import PoolChurnNotifier


async def send_to_channel_test_message(d: DepContainer):
    d.broadcaster = Broadcaster(d)

    async with aiohttp.ClientSession() as d.session:
        d.thor_connector = ThorConnector(get_thor_env_by_network_id(d.cfg.network_id), d.session)
        d.price_holder = LastPriceHolder()
        ppf = PoolInfoFetcherMidgard(d)
        notifier_pool_churn = PoolChurnNotifier(d)

        ppf_old = PoolPriceFetcher(d)
        d.price_holder.pool_info_map = await ppf_old.get_current_pool_data_full()
        await ppf.get_pool_info_midgard()

        # feed original pools
        await notifier_pool_churn.on_data(ppf, None)


        await notifier_pool_churn.on_data(ppf, d.price_holder.pool_info_map)  # must notify about changes above ^^^

        d.price_holder.pool_info_map = deepcopy(d.price_holder.pool_info_map)  # make a copy
        # del lph.pool_info_map['ETH.USDT-0XDAC17F958D2EE523A2206206994597C13D831EC7']  # deleted pool
        del d.price_holder.pool_info_map['ETH.SUSHI-0X6B3595068778DD592E39A122F4F5A5CF09C90FE2']  # deleted pool
        d.price_holder.pool_info_map['BNB.AVA-645'].status = PoolInfo.STAGED
        d.price_holder.pool_info_map['BNB.FTM-A64'].status = PoolInfo.AVAILABLE
        d.price_holder.pool_info_map['DOGE.DOGE'] = PoolInfo('BTC.BTC', 18555, 18555, 100, PoolInfo.STAGED)

        await notifier_pool_churn.on_data(ppf, d.price_holder.pool_info_map)  # no update at this moment!


async def main(d):
    await send_to_channel_test_message(d)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    d = DepContainer()
    d.loop = asyncio.get_event_loop()
    d.cfg = Config()
    d.db = DB(d.loop)

    d.bot = Bot(token=d.cfg.telegram.bot.token, parse_mode=ParseMode.HTML)
    d.dp = Dispatcher(d.bot, loop=d.loop)
    d.loc_man = LocalizationManager(d.cfg)

    asyncio.run(main(d))
