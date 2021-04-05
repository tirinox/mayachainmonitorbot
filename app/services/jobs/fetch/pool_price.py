import calendar
import dataclasses
import json
from datetime import date

from typing import Optional, List

from aiothornode.types import ThorPool

from services.jobs.fetch.base import BaseFetcher
from services.jobs.fetch.fair_price import fair_rune_price
from services.jobs.midgard import get_url_gen_by_network_id, get_parser_by_network_id
from services.lib.config import Config
from services.lib.constants import BNB_BUSD_SYMBOL, RUNE_SYMBOL_DET, is_stable_coin, NetworkIdents, \
    ETH_USDT_TEST_SYMBOL, RUNE_SYMBOL_MARKET
from services.lib.datetime import parse_timespan_to_seconds, DAY, HOUR
from services.lib.depcont import DepContainer
from services.models.pool_info import PoolInfo, PoolInfoHistoricEntry
from services.models.time_series import PriceTimeSeries


# todo => block number === date map

class PoolPriceFetcher(BaseFetcher):
    """
    This class queries Midgard and THORNodes to get current and historical pool prices and depths
    """
    def __init__(self, deps: DepContainer):
        cfg: Config = deps.cfg
        period = parse_timespan_to_seconds(cfg.price.fetch_period)
        super().__init__(deps, sleep_period=period)
        self.deps = deps
        self.midgard_url_gen = get_url_gen_by_network_id(cfg.network_id)

    async def fetch(self):
        d = self.deps

        current_pools = await self.get_current_pool_data_full()

        if current_pools and self.deps.price_holder is not None:
            self.deps.price_holder.update(current_pools)

        price = d.price_holder.usd_per_rune
        self.logger.info(f'fresh rune price is ${price:.3f}')

        if price > 0:
            price_series = PriceTimeSeries(RUNE_SYMBOL_MARKET, d.db)
            await price_series.add(price=price)

            fair_price = await fair_rune_price(d.price_holder)
            fair_price.real_rune_price = price

            deterministic_price_series = PriceTimeSeries(RUNE_SYMBOL_DET, d.db)
            await deterministic_price_series.add(price=fair_price.fair_price)

            return fair_price
        else:
            self.logger.warning(f'really ${price:.3f}? that is odd!')

    @staticmethod
    def _parse_thor_pools(thor_pools: List[ThorPool]):
        return {
            p.asset: PoolInfo(p.asset,
                              p.assets_per_rune, p.balance_asset_int, p.balance_rune_int,
                              p.pool_units_int, p.status)
            for p in thor_pools
        }

    async def get_current_pool_data_full(self, height=None, caching=False):
        cache_key = f'ThorNodePool:{height}'

        if caching and height:
            cached_raw = await self.deps.db.redis.get(cache_key)
            if cached_raw:
                try:
                    j = json.loads(cached_raw)
                    thor_pools = [ThorPool.from_json(pool_j) for pool_j in j]
                    return self._parse_thor_pools(thor_pools)
                except ValueError:
                    pass

        thor_pools = await self.deps.thor_connector.query_pools(height)

        if caching and height:
            serialized_thor_pools = json.dumps([dataclasses.asdict(p) for p in thor_pools])
            await self.deps.db.redis.set(cache_key, serialized_thor_pools)

        return self._parse_thor_pools(thor_pools)

    def url_for_historical_pool_state(self, pool, ts):
        from_ts = int(ts - HOUR)
        to_ts = int(ts + DAY + HOUR)
        return self.midgard_url_gen.url_for_pool_depth_history(pool, from_ts, to_ts)

    async def get_asset_per_rune_of_pool_by_day(self, pool: str, day: date, caching=True):
        cache_key = f'MidgardPrice:{pool}:{day.year}.{day.month}.{day.day}' if caching else ''
        if caching:
            cached_raw = await self.deps.db.redis.get(cache_key)
            if cached_raw:
                try:
                    return float(cached_raw)
                except ValueError:
                    pass

        timestamp = calendar.timegm(day.timetuple())
        url = self.url_for_historical_pool_state(pool, timestamp)
        self.logger.info(f"get: {url}")

        parser = get_parser_by_network_id(self.deps.cfg.network_id)

        async with self.deps.session.get(url) as resp:
            raw_data = await resp.json()
            pools_info = parser.parse_historic_pool_items(raw_data)
            if not pools_info:
                self.logger.error(f'there were no historical data returned!')
                return None
            else:
                price = pools_info[0].asset_price
                if caching and price:
                    await self.deps.db.redis.set(cache_key, price)
                return price

    async def get_pool_info_by_day(self, pool: str, day: date, caching=True) -> Optional[PoolInfoHistoricEntry]:
        parser = get_parser_by_network_id(self.deps.cfg.network_id)

        cache_key = ''
        if caching:
            cache_key = f'MidgardPoolInfo:{pool}:{day.year}.{day.month}.{day.day}'
            cached_raw = await self.deps.db.redis.get(cache_key)
            if cached_raw:
                try:
                    j = json.loads(cached_raw)
                    return parser.parse_historic_pool_items(j)[0]
                except ValueError:
                    pass

        timestamp = calendar.timegm(day.timetuple())
        url = self.url_for_historical_pool_state(pool, timestamp)
        self.logger.info(f"get: {url}")

        async with self.deps.session.get(url) as resp:
            raw_data = await resp.json()
            pools_info = parser.parse_historic_pool_items(raw_data)
            if not pools_info:
                self.logger.error(f'there were no historical data returned!')
                return None
            else:
                if caching and raw_data:
                    await self.deps.db.redis.set(cache_key, json.dumps(raw_data))
                pool_info = pools_info[0]
                return pool_info

    # todo: price -> poolInfo full (+ caching)
    async def get_usd_price_of_rune_and_asset_by_day(self, pool, day: date, caching=True):
        network = self.deps.cfg.network_id
        if network == NetworkIdents.CHAOSNET_BEP2CHAIN or network == NetworkIdents.CHAOSNET_MULTICHAIN:
            stable_coin_symbol = BNB_BUSD_SYMBOL  # todo: get price from coin gecko OR from weighted usd price cache
            # todo: Midgard V2 already returns usd price, there is no need to query a stable coin pool
        elif network == NetworkIdents.TESTNET_MULTICHAIN:
            stable_coin_symbol = ETH_USDT_TEST_SYMBOL
        else:
            raise NotImplementedError

        usd_per_rune = await self.get_asset_per_rune_of_pool_by_day(stable_coin_symbol, day, caching=caching)
        if is_stable_coin(pool):
            return usd_per_rune, 1.0
        else:
            asset_per_rune = await self.get_asset_per_rune_of_pool_by_day(pool, day, caching=caching)
            usd_per_asset = usd_per_rune / asset_per_rune
            return usd_per_rune, usd_per_asset
