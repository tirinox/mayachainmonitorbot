import asyncio
from typing import Union

from localization.manager import BaseLocalization
from services.dialog.picture.achievement_picture import build_achievement_picture_generator
from services.dialog.picture.block_height_picture import block_speed_chart
from services.dialog.picture.key_stats_picture import KeyStatsPictureGenerator
from services.dialog.picture.nodes_pictures import NodePictureGenerator
from services.dialog.picture.price_picture import price_graph_from_db
from services.dialog.picture.savers_picture import SaversPictureGenerator
from services.jobs.achievement.ach_list import Achievement
from services.lib.constants import THOR_BLOCKS_PER_MINUTE
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.draw_utils import img_to_bio
from services.lib.midgard.name_service import NameService, NameMap
from services.lib.w3.dex_analytics import DexReport
from services.models.flipside import AlertKeyStats
from services.models.last_block import EventBlockSpeed, BlockProduceState
from services.models.loans import AlertLoanOpen, AlertLoanRepayment
from services.models.mimir import AlertMimirChange
from services.models.node_info import AlertNodeChurn
from services.models.pol import AlertPOL
from services.models.pool_info import PoolChanges
from services.models.price import AlertPrice
from services.models.s_swap import AlertSwapStart
from services.models.savers import AlertSaverStats
from services.models.transfer import TokenCexFlow, TokenTransfer
from services.models.tx import EventLargeTransaction
from services.notify.broadcast import Broadcaster
from services.notify.channel import BoardMessage, MessageType
from services.notify.types.chain_notify import AlertChainHalt


class AlertPresenter(INotified):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.broadcaster: Broadcaster = deps.broadcaster
        self.name_service: NameService = deps.name_service

    async def on_data(self, sender, data):
        # noinspection PyAsyncCall
        asyncio.create_task(self._handle_async(data))

    async def _handle_async(self, data):
        if isinstance(data, TokenCexFlow):
            await self._handle_rune_cex_flow(data)
        elif isinstance(data, TokenTransfer):
            await self._handle_rune_transfer(data)
        elif isinstance(data, EventBlockSpeed):
            await self._handle_block_speed(data)
        elif isinstance(data, EventLargeTransaction):
            await self._handle_large_tx(data)
        elif isinstance(data, DexReport):
            await self._handle_dex_report(data)
        elif isinstance(data, AlertSaverStats):
            await self._handle_saver_stats(data)
        elif isinstance(data, PoolChanges):
            await self._handle_pool_churn(data)
        elif isinstance(data, AlertPOL):
            await self._handle_pol(data)
        elif isinstance(data, Achievement):
            await self._handle_achievement(data)
        elif isinstance(data, AlertNodeChurn):
            await self._handle_node_churn(data)
        elif isinstance(data, AlertKeyStats):
            await self._handle_key_stats(data)
        elif isinstance(data, AlertSwapStart):
            await self._handle_streaming_swap_start(data)
        elif isinstance(data, (AlertLoanOpen, AlertLoanRepayment)):
            await self._handle_loans(data)
        elif isinstance(data, AlertPrice):
            await self._handle_price(data)
        elif isinstance(data, AlertMimirChange):
            await self._handle_mimir(data)
        elif isinstance(data, AlertChainHalt):
            await self._handle_chain_halt(data)

    async def load_names(self, addresses) -> NameMap:
        if not (isinstance(addresses, (list, tuple))):
            addresses = (addresses,)

        return await self.name_service.safely_load_thornames_from_address_set(addresses)

        # ---- PARTICULARLY ----

    async def _handle_large_tx(self, txs_event: EventLargeTransaction):
        name_map = await self.load_names(txs_event.transaction.sender_address)

        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_large_single_tx,
            txs_event.transaction, txs_event.usd_per_rune, txs_event.pool_info, txs_event.cap_info,
            name_map,
            txs_event.mimir,
        )

    async def _handle_rune_transfer(self, transfer: TokenTransfer):
        name_map = await self.load_names([
            transfer.from_addr, transfer.to_addr
        ])

        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_rune_transfer_public,
            transfer, name_map)

    async def _handle_rune_cex_flow(self, flow: TokenCexFlow):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_cex_flow, flow)

    @staticmethod
    async def _block_speed_picture_generator(loc: BaseLocalization, points, event):
        chart, chart_name = await block_speed_chart(points, loc,
                                                    normal_bpm=THOR_BLOCKS_PER_MINUTE,
                                                    time_scale_mode='time')

        if event.state in (BlockProduceState.StateStuck, BlockProduceState.Producing):
            caption = loc.notification_text_block_stuck(event)
        else:
            caption = loc.notification_text_block_pace(event)

        return BoardMessage.make_photo(chart, caption=caption, photo_file_name=chart_name)

    async def _handle_block_speed(self, event: EventBlockSpeed):
        await self.broadcaster.notify_preconfigured_channels(self._block_speed_picture_generator, event.points, event)

    async def _handle_dex_report(self, event: DexReport):
        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_dex_report,
            event
        )

    async def _handle_saver_stats(self, event: AlertSaverStats):
        async def _gen(loc: BaseLocalization, event):
            pic_gen = SaversPictureGenerator(loc, event)
            pic, pic_name = await pic_gen.get_picture()

            caption = loc.notification_text_saver_stats(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.notify_preconfigured_channels(_gen, event)

    async def _handle_pool_churn(self, event: PoolChanges):
        await self.broadcaster.notify_preconfigured_channels(BaseLocalization.notification_text_pool_churn, event)

    async def _handle_achievement(self, event: Achievement):
        async def _gen(loc: BaseLocalization, _a: Achievement):
            pic_gen = build_achievement_picture_generator(_a, loc.ach)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.ach.notification_achievement_unlocked(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.notify_preconfigured_channels(_gen, event)

    async def _handle_pol(self, event: AlertPOL):
        # async def _gen(loc: BaseLocalization, _a: EventPOL):
        #     pic_gen = POLPictureGenerator(loc.ach, _a)
        #     pic, pic_name = await pic_gen.get_picture()
        #     caption = loc.ach.notification_pol_stats(event)
        #     return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)
        # await self.broadcaster.notify_preconfigured_channels(_gen, event)

        # simple text so far
        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_pol_utilization, event
        )

    async def _handle_node_churn(self, event: AlertNodeChurn):
        if event.finished:
            await self.broadcaster.notify_preconfigured_channels(
                BaseLocalization.notification_text_node_churn_finish,
                event.changes)

            if event.with_picture:
                async def _gen(loc: BaseLocalization):
                    gen = NodePictureGenerator(event.network_info, event.bond_chart, loc)
                    pic = await gen.generate()
                    bio_graph = img_to_bio(pic, gen.proper_name())
                    caption = loc.PIC_NODE_DIVERSITY_BY_PROVIDER_CAPTION
                    return BoardMessage.make_photo(bio_graph, caption)

                await self.broadcaster.notify_preconfigured_channels(_gen)

        else:
            # started
            await self.broadcaster.notify_preconfigured_channels(
                BaseLocalization.notification_churn_started,
                event.changes
            )

    async def _handle_key_stats(self, event: AlertKeyStats):
        # PICTURE
        async def _gen(loc: BaseLocalization, _a: AlertKeyStats):
            pic_gen = KeyStatsPictureGenerator(loc, _a)
            pic, pic_name = await pic_gen.get_picture()
            caption = loc.notification_text_key_metrics_caption(event)
            return BoardMessage.make_photo(pic, caption=caption, photo_file_name=pic_name)

        await self.broadcaster.notify_preconfigured_channels(_gen, event)

    async def _handle_streaming_swap_start(self, event: AlertSwapStart):
        name_map = await self.load_names(event.from_address)

        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_streaming_swap_started,
            event, name_map
        )

    async def _handle_loans(self, event: Union[AlertLoanOpen, AlertLoanRepayment]):
        name_map = await self.load_names(event.loan.owner)

        if isinstance(event, AlertLoanOpen):
            method = BaseLocalization.notification_text_loan_open
        else:
            method = BaseLocalization.notification_text_loan_repayment

        await self.broadcaster.notify_preconfigured_channels(
            method,
            event, name_map
        )

    async def _handle_price(self, event: AlertPrice):
        async def price_graph_gen(loc: BaseLocalization):
            # todo: fix self.deps reference
            graph, graph_name = await price_graph_from_db(self.deps, loc, event.price_graph_period)
            caption = loc.notification_text_price_update(event)
            return BoardMessage.make_photo(graph, caption=caption, photo_file_name=graph_name)

        if event.is_ath and event.ath_sticker:
            await self.broadcaster.notify_preconfigured_channels(BoardMessage(event.ath_sticker, MessageType.STICKER))

        await self.broadcaster.notify_preconfigured_channels(price_graph_gen)

    async def _handle_chain_halt(self, event: AlertChainHalt):
        await self.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_trading_halted_multi,
            event.changed_chains
        )

    async def _handle_mimir(self, data: AlertMimirChange):
        await self.deps.broadcaster.notify_preconfigured_channels(
            BaseLocalization.notification_text_mimir_changed,
            data.changes,
            data.holder,
        )
