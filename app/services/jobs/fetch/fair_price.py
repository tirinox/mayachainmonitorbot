import asyncio
from typing import Optional

from services.jobs.fetch.circulating import RuneCirculatingSupplyFetcher, RuneCirculatingSupply
from services.jobs.fetch.gecko_price import get_thorchain_coin_gecko_info, gecko_market_cap_rank, gecko_ticker_price, \
    gecko_market_volume
from services.lib.constants import thor_to_float
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import class_logger
from services.models.price import RuneMarketInfo

RUNE_MARKET_INFO_CACHE_TIME = 120
DEFAULT_CEX_NAME = 'HitBTC'
DEFAULT_CEX_BASE_ASSET = 'USDT'


class RuneMarketInfoFetcher:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)
        self.price_holder = deps.price_holder
        self.midgard = deps.midgard_connector
        self._ether_scan_key = deps.cfg.get('thor.circulating_supply.ether_scan_key', '')
        self._cache_time = parse_timespan_to_seconds(
            deps.cfg.as_str('thor.circulating_supply.cache_time', RUNE_MARKET_INFO_CACHE_TIME))
        self._prev_result: Optional[RuneMarketInfo] = None

        self.cex_name = deps.cfg.as_str('price.bep2_reference.cex', DEFAULT_CEX_NAME)
        self.cex_pair = deps.cfg.as_str('price.bep2_reference.pair', DEFAULT_CEX_BASE_ASSET)

        self.logger.info(f'Reference is RUNE/${self.cex_pair} at "{self.cex_name}" CEX.')

        # cache the method
        # self.get_rune_market_info = a_result_cached(ttl=self._cache_time)(retries(5)(self._get_rune_market_info))
        # self.get_rune_market_info = a_result_cached(ttl=self._cache_time)(self._get_rune_market_info)

    async def total_locked_value_all_networks(self):
        j = await self.midgard.request_random_midgard(free_url_gen.url_network())
        total_pooled_rune = j.get('totalStaked', 0)
        if not total_pooled_rune:
            total_pooled_rune = j.get('totalPooledRune', 0)
        return thor_to_float(total_pooled_rune)

    async def _get_rune_market_info(self) -> RuneMarketInfo:
        supply_fetcher = RuneCirculatingSupplyFetcher(self.deps.session,
                                                      ether_scan_key=self._ether_scan_key,
                                                      thor_node=self.deps.cfg.get('thor.node.node_url'))

        supply_info, gecko, total_locked_rune = await asyncio.gather(
            supply_fetcher.fetch(),
            get_thorchain_coin_gecko_info(self.deps.session),
            self.total_locked_value_all_networks()
        )

        supply_info: RuneCirculatingSupply
        circulating_rune = supply_info.overall.circulating
        total_supply = supply_info.overall.total

        if circulating_rune <= 0:
            raise ValueError(f"circulating is invalid ({circulating_rune})")

        price_holder = self.price_holder
        if not price_holder.pool_info_map or not price_holder.usd_per_rune:
            raise ValueError(f"pool_info_map is empty!")

        tlv = total_locked_rune * price_holder.usd_per_rune  # == tlv of non-rune assets

        fair_price = 3 * tlv / circulating_rune  # The main formula of wealth!

        cex_price = gecko_ticker_price(gecko, self.cex_name, self.cex_pair)
        rank = gecko_market_cap_rank(gecko)
        trade_volume = gecko_market_volume(gecko)

        result = RuneMarketInfo(
            circulating=circulating_rune,
            rune_vault_locked=0,
            pool_rune_price=price_holder.usd_per_rune,
            fair_price=fair_price,
            cex_price=cex_price,
            tlv_usd=tlv,
            rank=rank,
            total_trade_volume_usd=trade_volume,
            total_supply=total_supply,
            supply_info=supply_info
        )
        self.logger.info(result)
        return result

    async def get_rune_market_info(self) -> RuneMarketInfo:
        try:
            result = await self._get_rune_market_info()
            if result.is_valid:
                self._prev_result = result
            return result
        except Exception:
            self.logger.exception('Failed to get fresh Rune market info!', exc_info=True)
            return self._prev_result
