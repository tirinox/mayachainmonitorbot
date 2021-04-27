import logging
from datetime import date, datetime, timedelta
from typing import Dict

from aioredis import Redis

from services.lib.constants import THOR_BLOCK_TIME
from services.lib.date_utils import day_to_key, days_ago_noon, DAY, date_parse_rfc
from services.lib.depcont import DepContainer
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import get_url_gen_by_network_id
from services.models.last_block import LastBlock


class DateToBlockMapper:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.midgard_url_gen = get_url_gen_by_network_id(deps.cfg.network_id)
        self.midgard_parser = get_parser_by_network_id(deps.cfg.network_id)
        self.logger = logging.getLogger(self.__class__.__name__)

    async def get_last_blocks(self) -> Dict[str, LastBlock]:
        url_last_block = self.midgard_url_gen.url_last_block()
        self.logger.info(f"get: {url_last_block}")

        async with self.deps.session.get(url_last_block) as resp:
            raw_data = await resp.json()
            last_blocks = self.midgard_parser.parse_last_block(raw_data)
            return last_blocks

    async def get_last_thorchain_block(self) -> int:
        last_blocks = await self.get_last_blocks()
        last_block: LastBlock = list(last_blocks.values())[0]
        return last_block.thorchain

    async def get_timestamp_by_block_height(self, block_height) -> float:
        block_info = await self.deps.thor_connector.query_tendermint_block_raw(block_height)
        rfc_time = block_info['result']['block']['header']['time']
        dt = date_parse_rfc(rfc_time)
        return dt.timestamp()

    DB_KEY_DATE_TO_BLOCK_MAPPER = 'Date2Block:Thorchain'

    async def clear(self):
        r: Redis = await self.deps.db.get_redis()
        await r.delete(self.DB_KEY_DATE_TO_BLOCK_MAPPER)

    async def save_height_to_day_cache(self, day: date, block_height):
        r: Redis = await self.deps.db.get_redis()
        await r.hset(self.DB_KEY_DATE_TO_BLOCK_MAPPER, day_to_key(day), block_height)

    async def load_height_from_day_cache(self, day) -> int:
        r: Redis = await self.deps.db.get_redis()
        data = await r.hget(self.DB_KEY_DATE_TO_BLOCK_MAPPER, day_to_key(day))
        return int(data) if data else None

    async def iterative_block_discovery_by_timestamp(self, ts: float, last_block=None, max_steps=10,
                                                     tolerance_sec=THOR_BLOCK_TIME * 1.5):
        if not last_block:
            last_block = await self.get_last_thorchain_block()

        now = datetime.now()
        total_seconds = now.timestamp() - ts
        assert total_seconds > 0

        estimated_block_height = last_block - total_seconds / THOR_BLOCK_TIME
        estimated_block_height = int(max(0, estimated_block_height))

        self.logger.info(f'Initial guess for {ts = } is #{estimated_block_height}')

        for step in range(max_steps):
            guess_ts = await self.get_timestamp_by_block_height(estimated_block_height)
            seconds_diff = guess_ts - ts
            if abs(seconds_diff) <= tolerance_sec:
                self.logger.info(f'Success. #{estimated_block_height = }!')
                break

            estimated_block_height -= seconds_diff / THOR_BLOCK_TIME
            estimated_block_height = int(max(0, estimated_block_height))

            self.logger.info(f'Step #{step + 1}. {estimated_block_height = }')

        return estimated_block_height

    async def calibrate(self, days=14):
        last_block = await self.get_last_thorchain_block()

        today_beginning = days_ago_noon(0, hour=0)

        blocks = []

        for day_ago in range(days):
            that_day = today_beginning - timedelta(days=day_ago)
            block_no = await self.iterative_block_discovery_by_timestamp(that_day.timestamp(),
                                                                         last_block)
            print(f'{day_ago = }, {that_day = }, {block_no = }')  # fixme: debug
            blocks.append((that_day, block_no))

        print(blocks)  # fixme: debug
        return blocks

    async def get_block_height_by_date(self, d: date) -> int:
        return 0  # todo
