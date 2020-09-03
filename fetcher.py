import asyncio

import aiohttp
from aioredis import Redis

from config import Config, DB


class InfoFetcher:
    SLEEP_PERIOD = 10
    MULT = 10 ** -8

    KEY_OLD_CAP = 'th_old_cap'

    def __init__(self, cfg: Config, db: DB, callback: callable):
        self.cfg = cfg
        self.db = db
        self.callback = callback
        self.r: Redis

    async def fetch_caps(self):
        urls = self.cfg.thorchain.chaosnet.urls

        async with aiohttp.ClientSession() as session:
            async with session.get(urls.network) as resp:
                networks_resp = await resp.json()
                total_staked = int(networks_resp.get('totalStaked', 0))

            async with session.get(urls.mimir) as resp:
                mimir_resp = await resp.json()
                max_staked = int(mimir_resp.get("mimir//MAXIMUMSTAKERUNE", 1))

            return {
                "total_staked": total_staked * self.MULT,
                "max_staked": max_staked * self.MULT
            }

    async def get_old_cap(self):
        try:
            return float(await self.r.get(self.KEY_OLD_CAP))
        except (TypeError, ValueError):
            return 0.0

    async def set_cap(self, cap):
        await self.r.set(self.KEY_OLD_CAP, cap)

    async def fetch_loop(self):
        await asyncio.sleep(3)

        self.r = await self.db.get_redis()

        while True:
            r = await self.fetch_caps()

            max_cap = r['max_staked']

            old_max_cap = await self.get_old_cap()
            if max_cap > old_max_cap:
                staked = r['total_staked']
                await self.callback(old_max_cap, max_cap, staked)
                await self.set_cap(max_cap)

            await asyncio.sleep(self.SLEEP_PERIOD)
