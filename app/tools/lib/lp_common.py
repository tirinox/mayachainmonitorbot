import asyncio
import logging

from aiothornode.connector import ThorConnector

from localization.manager import LocalizationManager
from services.dialog.telegram.telegram import telegram_send_message_basic, TG_TEST_USER, TelegramBot
from services.jobs.fetch.const_mimir import ConstMimirFetcher
from services.jobs.fetch.fair_price import RuneMarketInfoFetcher
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.jobs.fetch.runeyield import AsgardConsumerConnectorBase, get_rune_yield_connector
from services.lib.config import Config
from services.lib.db import DB
from services.lib.depcont import DepContainer
from services.lib.midgard.connector import MidgardConnector
from services.lib.midgard.name_service import NameService
from services.lib.settings_manager import SettingsManager, SettingsProcessorGeneralAlerts
from services.lib.utils import setup_logs
from services.models.mimir import MimirHolder
from services.models.node_watchers import AlertWatchers
from services.notify.broadcast import Broadcaster


class LpAppFramework:
    def __init__(self, rune_yield_class=None, network=None, log_level=logging.DEBUG) -> None:
        self.brief = None

        setup_logs(log_level)
        d = DepContainer()
        d.loop = asyncio.get_event_loop()
        d.cfg = Config()
        if network:
            d.cfg.network_id = network
        d.loc_man = LocalizationManager(d.cfg)
        d.db = DB(d.loop)
        d.settings_manager = SettingsManager(d.db, d.cfg)

        d.alert_watcher = AlertWatchers(d.db)
        d.gen_alert_settings_proc = SettingsProcessorGeneralAlerts(d.db, d.alert_watcher)

        d.telegram_bot = TelegramBot(d.cfg, d.db, d.loop)
        d.broadcaster = Broadcaster(d)

        d.price_pool_fetcher = PoolPriceFetcher(d)
        d.mimir_const_fetcher = ConstMimirFetcher(d)
        d.mimir_const_holder = MimirHolder()

        self.deps = d
        self.rune_yield: AsgardConsumerConnectorBase
        self.rune_yield_class = rune_yield_class

    @property
    def tg_token(self):
        return self.deps.cfg.get('telegram.bot.token')

    async def send_test_tg_message(self, txt, **kwargs):
        return await telegram_send_message_basic(self.tg_token, TG_TEST_USER, txt, **kwargs)

    async def prepare(self, brief=False):
        d = self.deps
        d.make_http_session()
        d.thor_connector = ThorConnector(d.cfg.get_thor_env_by_network_id(), d.session)
        d.thor_env = d.thor_connector.env

        cfg = d.cfg.thor.midgard
        d.midgard_connector = MidgardConnector(
            d.session,
            d.thor_connector,
            int(cfg.get_pure('tries', 3)),
            public_url=cfg.get('public_url', ''),
            use_nodes=bool(cfg.get('use_nodes', True))
        )
        d.rune_market_fetcher = RuneMarketInfoFetcher(d)

        d.name_service = NameService(d.db, d.cfg, d.midgard_connector)
        d.loc_man.set_name_service(d.name_service)

        await d.db.get_redis()

        brief = brief if self.brief is None else self.brief
        if brief:
            return

        d.node_info_fetcher = NodeInfoFetcher(d)
        await d.node_info_fetcher.fetch()  # get nodes beforehand

        d.mimir_const_holder = MimirHolder()
        d.mimir_const_fetcher = ConstMimirFetcher(d)
        await d.mimir_const_fetcher.fetch()  # get constants beforehand

        d.price_pool_fetcher = PoolPriceFetcher(d)

        if self.rune_yield_class:
            self.rune_yield = self.rune_yield_class(d)
        else:
            self.rune_yield = get_rune_yield_connector(d)

        await d.price_pool_fetcher.fetch()

    async def close(self):
        await self.deps.session.close()

    async def __aenter__(self):
        await self.prepare()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __call__(self, brief=False):
        self.brief = brief
        return self


class LpGenerator(LpAppFramework):
    async def get_report(self, addr, pool):
        lp_report = await self.rune_yield.generate_yield_report_single_pool(addr, pool)

        # -------- print out ----------
        redeem_rune, redeem_asset = lp_report.redeemable_rune_asset
        print(f'redeem_rune = {redeem_rune} and redeem_asset = {redeem_asset}')
        print()
        USD, ASSET, RUNE = lp_report.USD, lp_report.ASSET, lp_report.RUNE
        print(f'current_value(USD) = {lp_report.current_value(USD)}')
        print(f'current_value(ASSET) = {lp_report.current_value(ASSET)}')
        print(f'current_value(RUNE) = {lp_report.current_value(RUNE)}')
        print()
        gl_usd, gl_usd_p = lp_report.gain_loss(USD)
        gl_ass, gl_ass_p = lp_report.gain_loss(ASSET)
        gl_rune, gl_rune_p = lp_report.gain_loss(RUNE)
        print(f'gain/loss(USD) = {gl_usd}, {gl_usd_p:.1f} %')
        print(f'gain/loss(ASSET) = {gl_ass}, {gl_ass_p:.1f} %')
        print(f'gain/loss(RUNE) = {gl_rune}, {gl_rune_p:.1f} %')
        print()
        lp_abs, lp_per = lp_report.lp_vs_hold
        apy = lp_report.lp_vs_hold_apy
        print(f'lp_report.lp_vs_hold = {lp_abs}, {lp_per:.1f} %')
        print(f'lp_report.lp_vs_hold_apy = {apy}')

        return lp_report

    async def test_summary(self, address):
        lp_reports, weekly_charts = await self.rune_yield.generate_yield_summary(address, [])
        return lp_reports, weekly_charts
