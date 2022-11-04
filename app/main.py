import asyncio
import logging
import os

from aiothornode.connector import ThorConnector

from localization.manager import LocalizationManager
from services.dialog.discord.discord_bot import DiscordBot
from services.dialog.main import init_dialogs
from services.dialog.slack.slack_bot import SlackBot
from services.dialog.telegram.sticker_downloader import TelegramStickerDownloader
from services.dialog.telegram.telegram import TelegramBot
from services.dialog.twitter.twitter_bot import TwitterBot, TwitterBotMock
from services.jobs.fetch.bep2_move import BinanceOrgDexWSSClient
from services.jobs.fetch.cap import CapInfoFetcher
from services.jobs.fetch.chains import ChainStateFetcher
from services.jobs.fetch.const_mimir import ConstMimirFetcher
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.gecko_price import fill_rune_price_from_gecko
from services.jobs.fetch.killed_rune import KilledRuneFetcher, KilledRuneStore
from services.jobs.fetch.last_block import LastBlockFetcher
from services.jobs.fetch.native_scan import NativeScannerBlock
from services.jobs.fetch.net_stats import NetworkStatisticsFetcher
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher, PoolInfoFetcherMidgard
from services.jobs.fetch.queue import QueueFetcher
from services.jobs.fetch.tx import TxFetcher
from services.jobs.ilp_summer import ILPSummer
from services.jobs.node_churn import NodeChurnDetector
from services.jobs.transfer_detector import RuneTransferDetectorTxLogs
from services.jobs.user_counter import UserCounter
from services.jobs.volume_filler import VolumeFillerUpdater
from services.jobs.volume_recorder import VolumeRecorder
from services.lib.config import Config, SubConfig
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.name_service import NameService
from services.lib.money import DepthCurve
from services.lib.settings_manager import SettingsManager, SettingsProcessorGeneralAlerts
from services.lib.utils import setup_logs
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.lib.w3.dex_analytics import DexAnalyticsCollector
from services.models.mimir import MimirHolder
from services.models.node_watchers import AlertWatchers
from services.models.tx import ThorTxType
from services.notify.alert_presenter import AlertPresenter
from services.notify.broadcast import Broadcaster
from services.notify.personal.balance import PersonalBalanceNotifier
from services.notify.personal.personal_main import NodeChangePersonalNotifier
from services.notify.personal.price_divergence import PersonalPriceDivergenceNotifier, SettingsProcessorPriceDivergence
from services.notify.types.best_pool_notify import BestPoolsNotifier
from services.notify.types.block_notify import BlockHeightNotifier
from services.notify.types.cap_notify import LiquidityCapNotifier
from services.notify.types.chain_notify import TradingHaltedNotifier
from services.notify.types.dex_report_notify import DexReportNotifier
from services.notify.types.mimir_notify import MimirChangedNotifier
from services.notify.types.node_churn_notify import NodeChurnNotifier
from services.notify.types.pool_churn_notify import PoolChurnNotifier
from services.notify.types.price_div_notify import PriceDivergenceNotifier
from services.notify.types.price_notify import PriceNotifier
from services.notify.types.queue_notify import QueueNotifier
from services.notify.types.stats_notify import NetworkStatsNotifier
from services.notify.types.supply_notify import SupplyNotifier
from services.notify.types.transfer_notify import RuneMoveNotifier
from services.notify.types.tx_notify import GenericTxNotifier, SwitchTxNotifier, SwapTxNotifier, LiquidityTxNotifier
from services.notify.types.version_notify import VersionNotifier
from services.notify.types.voting_notify import VotingNotifier


class App:
    def __init__(self, log_level=None):
        d = self.deps = DepContainer()
        d.is_loading = True

        self._init_configuration(log_level)

        d.node_info_fetcher = NodeInfoFetcher(d)
        d.mimir_const_fetcher = ConstMimirFetcher(d)
        d.mimir_const_holder = MimirHolder()
        d.price_pool_fetcher = PoolPriceFetcher(d)

        self._init_settings()
        self._init_messaging()

    def _init_configuration(self, log_level=None):
        d = self.deps
        d.cfg = Config()

        sentry_url = d.cfg.as_str('sentry.url')
        if sentry_url:
            import sentry_sdk
            sentry_sdk.init(
                dsn=sentry_url,
                traces_sample_rate=1.0
            )

        log_level = log_level or d.cfg.get_pure('log_level', logging.INFO)
        setup_logs(log_level)

        # todo: ART logo
        logging.info(f'Starting THORChainMonitoringBot for "{d.cfg.network_id}".')

        d.loop = asyncio.get_event_loop()
        d.db = DB(d.loop)
        d.price_holder.load_stable_coins(d.cfg)

    def _init_settings(self):
        d = self.deps
        d.settings_manager = SettingsManager(d.db, d.cfg)
        d.alert_watcher = AlertWatchers(d.db)
        d.gen_alert_settings_proc = SettingsProcessorGeneralAlerts(d.db, d.alert_watcher)
        d.settings_manager.subscribe(d.gen_alert_settings_proc)
        d.settings_manager.subscribe(SettingsProcessorPriceDivergence(d.alert_watcher))

    def _init_messaging(self):
        d = self.deps
        d.loc_man = LocalizationManager(d.cfg)
        d.broadcaster = Broadcaster(d)
        d.alert_presenter = AlertPresenter(d.broadcaster, d.name_service)
        d.telegram_bot = TelegramBot(d.cfg, d.db, d.loop)
        init_dialogs(d)

    async def create_thor_node_connector(self):
        d = self.deps
        d.thor_env = d.cfg.get_thor_env_by_network_id()
        d.thor_connector = ThorConnector(d.thor_env, d.session)

        # now it is used mostly for historical pool state retrieval
        thor_env_backup = d.cfg.get_thor_env_by_network_id(backup=True)
        d.thor_connector_backup = ThorConnector(thor_env_backup, d.session)

        await d.thor_connector.update_nodes()

        cfg: SubConfig = d.cfg.get('thor.midgard')
        d.midgard_connector = MidgardConnector(
            d.session,
            d.thor_connector,
            int(cfg.get_pure('tries', 3)),
            public_url=d.thor_connector.env.midgard_url,
            use_nodes=bool(cfg.get('use_nodes', True))
        )
        d.rune_market_fetcher = RuneMarketInfoFetcher(d)

        d.name_service = NameService(d.db, d.cfg, d.midgard_connector)
        d.alert_presenter.name_service = d.name_service
        d.loc_man.set_name_service(d.name_service)

    async def _some_sleep(self):
        sleep_interval = self.deps.cfg.as_float('sleep_before_start', 0)
        if sleep_interval > 0:
            logging.info(f'Sleeping before start for {sleep_interval:.1f} sec..')
            await asyncio.sleep(sleep_interval)

    async def _run_background_jobs(self):
        d = self.deps

        await self._some_sleep()

        if 'REPLACE_RUNE_TIMESERIES_WITH_GECKOS' in os.environ:
            await fill_rune_price_from_gecko(d.db)

        # update pools for bootstrap (other components need them)
        current_pools = await d.price_pool_fetcher.reload_global_pools()
        if not current_pools:
            logging.error("No pool data at startup! Halt it!")
            exit(-1)

        await d.node_info_fetcher.fetch()  # get nodes beforehand
        await d.mimir_const_fetcher.fetch()  # get constants beforehand

        tasks = [
            # mandatory tasks:
            d.price_pool_fetcher,
            d.mimir_const_fetcher
        ]

        if d.cfg.get('tx.enabled', True):
            fetcher_tx = TxFetcher(d)

            aggregator = AggregatorDataExtractor(d)
            fetcher_tx.subscribe(aggregator)

            volume_filler = VolumeFillerUpdater(d)
            aggregator.subscribe(volume_filler)

            dex_analytics = DexAnalyticsCollector(d)
            aggregator.subscribe(dex_analytics)

            d.volume_recorder = VolumeRecorder(d)
            volume_filler.subscribe(d.volume_recorder)

            if d.cfg.tx.dex_aggregator_update.get('enabled', True):
                dex_report_notifier = DexReportNotifier(d, dex_analytics)
                volume_filler.subscribe(dex_report_notifier)
                dex_report_notifier.subscribe(d.alert_presenter)

            curve_pts = d.cfg.get_pure('tx.curve', default=DepthCurve.DEFAULT_TX_VS_DEPTH_CURVE)
            curve = DepthCurve(curve_pts)

            if d.cfg.tx.liquidity.get('enabled', True):
                liq_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)
                volume_filler.subscribe(liq_notifier_tx)
                liq_notifier_tx.subscribe(d.alert_presenter)

            if d.cfg.tx.donate.get('enabled', True):
                donate_notifier_tx = GenericTxNotifier(d, d.cfg.tx.donate,
                                                       tx_types=(ThorTxType.TYPE_DONATE,),
                                                       curve=curve)
                volume_filler.subscribe(donate_notifier_tx)
                donate_notifier_tx.subscribe(d.alert_presenter)

            if d.cfg.tx.swap.get('enabled', True):
                swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
                volume_filler.subscribe(swap_notifier_tx)
                swap_notifier_tx.subscribe(d.alert_presenter)

            if d.cfg.tx.refund.get('enabled', True):
                refund_notifier_tx = GenericTxNotifier(d, d.cfg.tx.refund,
                                                       tx_types=(ThorTxType.TYPE_REFUND,),
                                                       curve=curve)
                volume_filler.subscribe(refund_notifier_tx)
                refund_notifier_tx.subscribe(d.alert_presenter)

            if d.cfg.tx.switch.get('enabled', True):
                switch_notifier_tx = SwitchTxNotifier(d, d.cfg.tx.switch,
                                                      tx_types=(ThorTxType.TYPE_SWITCH,),
                                                      curve=curve)
                volume_filler.subscribe(switch_notifier_tx)
                switch_notifier_tx.subscribe(d.alert_presenter)

            # for tracking 24h ILP payouts
            ilp_summer = ILPSummer(d)
            fetcher_tx.subscribe(ilp_summer)
            tasks.append(fetcher_tx)

        if d.cfg.get('cap.enabled', True):
            fetcher_cap = CapInfoFetcher(d)
            notifier_cap = LiquidityCapNotifier(d)
            fetcher_cap.subscribe(notifier_cap)
            tasks.append(fetcher_cap)

        if d.cfg.get('queue.enabled', True):
            fetcher_queue = QueueFetcher(d)
            notifier_queue = QueueNotifier(d)
            fetcher_queue.subscribe(notifier_queue)
            tasks.append(fetcher_queue)

        if d.cfg.get('net_summary.enabled', True):
            fetcher_stats = NetworkStatisticsFetcher(d)
            notifier_stats = NetworkStatsNotifier(d)
            fetcher_stats.subscribe(notifier_stats)
            tasks.append(fetcher_stats)

        d.last_block_fetcher = LastBlockFetcher(d)

        if d.cfg.get('last_block.enabled', True):
            last_block_notifier = BlockHeightNotifier(d)
            d.last_block_fetcher.subscribe(last_block_notifier)
            last_block_notifier.subscribe(d.alert_presenter)
            d.block_notifier = last_block_notifier
            tasks.append(d.last_block_fetcher)

        if d.cfg.get('node_info.enabled', True):
            churn_detector = NodeChurnDetector(d)
            d.node_info_fetcher.subscribe(churn_detector)

            notifier_nodes = NodeChurnNotifier(d)
            churn_detector.subscribe(notifier_nodes)

            tasks.append(d.node_info_fetcher)

            if d.cfg.get('node_info.version.enabled', True):
                notifier_version = VersionNotifier(d)
                churn_detector.subscribe(notifier_version)

            if d.cfg.get('node_op_tools.enabled', True):
                d.node_op_notifier = NodeChangePersonalNotifier(d)
                await d.node_op_notifier.prepare()
                churn_detector.subscribe(d.node_op_notifier)

        if d.cfg.get('killed_rune.enabled', True):
            krf = KilledRuneFetcher(d)
            tasks.append(krf)
            kr_store = KilledRuneStore(d)
            krf.subscribe(kr_store)

        if d.cfg.get('price.enabled', True):
            notifier_price = PriceNotifier(d)
            d.price_pool_fetcher.subscribe(notifier_price)

            if d.cfg.get('price.divergence.enabled', True):
                price_div_notifier = PriceDivergenceNotifier(d)
                d.price_pool_fetcher.subscribe(price_div_notifier)

            if d.cfg.get('price.divergence.personal.enabled', True):
                personal_price_div_notifier = PersonalPriceDivergenceNotifier(d)
                d.price_pool_fetcher.subscribe(personal_price_div_notifier)

        # todo: join PoolChurnNotifier with PoolInfoFetcherMidgard
        if d.cfg.get('pool_churn.enabled', True):
            period = parse_timespan_to_seconds(d.cfg.pool_churn.fetch_period)
            fetcher_pool_info = PoolInfoFetcherMidgard(d, period)
            notifier_pool_churn = PoolChurnNotifier(d)
            fetcher_pool_info.subscribe(notifier_pool_churn)
            tasks.append(fetcher_pool_info)

        if d.cfg.get('best_pools.enabled', True):
            period = parse_timespan_to_seconds(d.cfg.best_pools.fetch_period)
            fetcher_pool_info = PoolInfoFetcherMidgard(d, period)
            d.best_pools_notifier = BestPoolsNotifier(d)
            fetcher_pool_info.subscribe(d.best_pools_notifier)
            tasks.append(fetcher_pool_info)

        if d.cfg.get('chain_state.enabled', True):
            fetcher_chain_state = ChainStateFetcher(d)
            notifier_trade_halt = TradingHaltedNotifier(d)
            fetcher_chain_state.subscribe(notifier_trade_halt)
            tasks.append(fetcher_chain_state)

        if d.cfg.get('constants.mimir_change', True):
            notifier_mimir_change = MimirChangedNotifier(d)
            d.mimir_const_fetcher.subscribe(notifier_mimir_change)

        if d.cfg.get('constants.voting.enabled', True):
            voting_notifier = VotingNotifier(d)
            d.mimir_const_fetcher.subscribe(voting_notifier)

        if d.cfg.get('rune_transfer.enabled', True):
            fetcher_bep2 = BinanceOrgDexWSSClient()
            d.rune_move_notifier = RuneMoveNotifier(d)
            fetcher_bep2.subscribe(d.rune_move_notifier)
            d.rune_move_notifier.subscribe(d.alert_presenter)
            tasks.append(fetcher_bep2)

        if d.cfg.get('native_scanner.enabled', True):
            scanner = NativeScannerBlock(d)
            tasks.append(scanner)
            reserve_address = d.cfg.as_str('native_scanner.reserve_address')
            decoder = RuneTransferDetectorTxLogs(reserve_address)
            scanner.subscribe(decoder)
            balance_notifier = PersonalBalanceNotifier(d)
            decoder.subscribe(balance_notifier)

            user_counter = UserCounter(d)
            scanner.subscribe(user_counter)

            if d.rune_move_notifier is not None:
                decoder.subscribe(d.rune_move_notifier)

        if d.cfg.get('supply.enabled', True):
            supply_notifier = SupplyNotifier(d)
            d.price_pool_fetcher.subscribe(supply_notifier)

        # --- BOTS

        sticker_downloader = TelegramStickerDownloader(d.telegram_bot.dp)

        if d.cfg.get('discord.enabled', False):
            d.discord_bot = DiscordBot(d.cfg, sticker_downloader)
            d.discord_bot.start_in_background()

        if d.cfg.get('slack.enabled', False):
            d.slack_bot = SlackBot(d.cfg, d.db, d.settings_manager, sticker_downloader)
            d.slack_bot.start_in_background()

        if d.cfg.get('twitter.enabled', False):
            if d.cfg.get('twitter.is_mock', False):
                logging.warning('Using Twitter Mock bot! All Tweets will go only to the logs!')
                d.twitter_bot = TwitterBotMock(d.cfg)
            else:
                logging.info('Using real Twitter bot.')
                d.twitter_bot = TwitterBot(d.cfg)

        self.deps.is_loading = False
        await asyncio.gather(*(task.run() for task in tasks))

    async def on_startup(self, _):
        self.deps.make_http_session()  # it is must be inside a coroutine!
        await self.create_thor_node_connector()

        asyncio.create_task(self._run_background_jobs())

    async def on_shutdown(self, _):
        await self.deps.session.close()

    def run_bot(self):
        self.deps.telegram_bot.run(on_startup=self.on_startup, on_shutdown=self.on_shutdown)


if __name__ == '__main__':
    App().run_bot()
