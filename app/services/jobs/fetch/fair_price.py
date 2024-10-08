import asyncio
from typing import Optional

from services.jobs.fetch.circulating import CacaoCirculatingSupplyFetcher, CacaoCirculatingSupply, RuneHoldEntry, \
    ThorRealms
from services.jobs.fetch.gecko_price import get_cacao_coin_gecko_info, gecko_market_cap_rank, gecko_ticker_price, \
    gecko_market_volume
from services.lib.constants import DEFAULT_CEX_NAME, DEFAULT_CEX_BASE_ASSET, cacao_to_float
from services.lib.date_utils import MINUTE
from services.lib.depcont import DepContainer
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import a_result_cached, WithLogger, retries
from services.models.price import RuneMarketInfo

CACAO_MARKET_INFO_CACHE_TIME = 3 * MINUTE


class RuneMarketInfoFetcher(WithLogger):
    def __init__(self, deps: DepContainer):
        super().__init__()
        self.deps = deps
        self.price_holder = deps.price_holder

        self._ether_scan_key = deps.cfg.get('thor.circulating_supply.ether_scan_key', '')
        self._prev_result: Optional[RuneMarketInfo] = None

        self.cex_name = deps.cfg.as_str('price.cex_reference.cex', DEFAULT_CEX_NAME)
        self.cex_pair = deps.cfg.as_str('price.cex_reference.pair', DEFAULT_CEX_BASE_ASSET)
        self.step_delay = 1.0

        if self.cex_pair:
            self.logger.info(f'Reference is CACAO/${self.cex_pair} at "{self.cex_name}" CEX.')

    def get_supply_fetcher(self):
        return CacaoCirculatingSupplyFetcher(
            self.deps.session,
            thor_node=self.deps.thor_connector.env.thornode_url,
            step_sleep=self.deps.cfg.sleep_step
        )

    @retries(5)
    async def total_pooled_rune(self):
        try:
            j = await self.deps.midgard_connector.request(free_url_gen.url_network())
            # still "rune" even for Maya. Stay alert!
            total_pooled_rune = j.get('totalPooledRune', 0)
            return cacao_to_float(total_pooled_rune)
        except (TypeError, ValueError):
            return .0

    @retries(5)
    async def _get_circulating_supply(self) -> CacaoCirculatingSupply:
        return await self.get_supply_fetcher().fetch()

    def _enrich_circulating_supply(self, supply: CacaoCirculatingSupply) -> CacaoCirculatingSupply:
        ns = self.deps.net_stats
        if ns:
            supply.set_holder(RuneHoldEntry('bond_module', int(ns.total_bond_rune), 'Bonded', ThorRealms.BONDED))
            supply.set_holder(RuneHoldEntry('pool_module', int(ns.total_rune_pooled), 'Pooled', ThorRealms.POOLED))
        else:
            self.logger.warning('No net stats! Failed to enrich circulating supply data with pool/bonding info!')

        nodes = self.deps.node_holder.nodes
        if nodes:
            for node in nodes:
                if node.bond > 0:
                    supply.set_holder(
                        RuneHoldEntry(node.node_address, int(node.bond), node.status, ThorRealms.BONDED_NODE)
                    )
        else:
            self.logger.warning('No nodes available! Failed to enrich circulating supply data with node info!')
        return supply

    async def get_full_supply(self) -> CacaoCirculatingSupply:
        supply_info = await self._get_circulating_supply()
        supply_info = self._enrich_circulating_supply(supply_info)
        return supply_info

    async def get_cacao_market_info_from_api(self) -> RuneMarketInfo:
        # todo: work from here
        supply_info: CacaoCirculatingSupply = await self.get_full_supply()
        await asyncio.sleep(self.step_delay)

        gecko = await get_cacao_coin_gecko_info(self.deps.session)
        await asyncio.sleep(self.step_delay)

        total_pulled_rune = await self.total_pooled_rune()

        circulating_rune = supply_info.circulating
        total_supply = supply_info.total

        if circulating_rune <= 0:
            raise ValueError(f"circulating is invalid ({circulating_rune})")

        price_holder = self.price_holder
        if not price_holder.pool_info_map or not price_holder.usd_per_rune:
            raise ValueError(f"pool_info_map is empty!")

        tlv_usd = total_pulled_rune * price_holder.usd_per_rune  # == tlv of non-rune assets

        # 1.0 for Maya. Explain this?
        fair_price = 1.0 * tlv_usd / circulating_rune  # The main formula of wealth!

        cex_price = gecko_ticker_price(gecko, self.cex_name, self.cex_pair)
        rank = gecko_market_cap_rank(gecko)
        trade_volume = gecko_market_volume(gecko)

        result = RuneMarketInfo(
            circulating=circulating_rune,
            rune_vault_locked=0,
            pool_rune_price=price_holder.usd_per_rune,
            fair_price=fair_price,
            cex_price=cex_price,
            tlv_usd=tlv_usd,
            rank=rank,
            total_trade_volume_usd=trade_volume,
            total_supply=total_supply,
            supply_info=supply_info
        )
        self.logger.info(result)
        return result

    @a_result_cached(CACAO_MARKET_INFO_CACHE_TIME)
    async def get_rune_market_info_cached(self) -> RuneMarketInfo:
        try:
            result = await self.get_cacao_market_info_from_api()
            if result.is_valid:
                self._prev_result = result
            return result
        except Exception as e:
            self.logger.exception(f'Failed to get fresh Rune market info! {e!r}', exc_info=True)
            return self._prev_result

    async def get_rune_market_info(self) -> RuneMarketInfo:
        data = await self.get_rune_market_info_cached()
        self._enrich_circulating_supply(data.supply_info)
        return data
