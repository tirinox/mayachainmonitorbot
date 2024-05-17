import asyncio
from datetime import datetime, timedelta

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.scanner.swap_extractor import SwapExtractorBlock
from services.jobs.scanner.swap_routes import SwapRouteRecorder
from services.jobs.user_counter import UserCounter
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import sep
from services.models.transfer import TokenTransfer
from tools.lib.lp_common import LpAppFramework, Receiver


class ReceiverPublicText(INotified):
    def __init__(self, deps: DepContainer, lang=Language.ENGLISH_TWITTER):
        self.deps = deps
        self.loc: BaseLocalization = self.deps.loc_man.get_from_lang(lang)

    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        for tr in data:
            tr: TokenTransfer
            print(self.loc.notification_text_rune_transfer_public(tr, {}))
            sep()


async def demo_block_scanner_count(app, catch_up_for=0, single_block=0):
    await app.deps.pool_fetcher.reload_global_pools()

    scanner = NativeScannerBlock(app.deps)

    # Just to check stability
    user_counter = UserCounter(app.deps)
    scanner.add_subscriber(user_counter)

    # Extract ThorTx from BlockResult
    swap_extractor = SwapExtractorBlock(app.deps)
    scanner.add_subscriber(swap_extractor)

    # Volume filler
    volume_filler = VolumeFillerUpdater(app.deps)
    swap_extractor.add_subscriber(volume_filler)

    # Swap route recorder
    routers_recorder = SwapRouteRecorder(app.deps.db)
    volume_filler.add_subscriber(routers_recorder)

    swap_extractor.add_subscriber(Receiver('Swap'))

    if catch_up_for > 0:
        await scanner.ensure_last_block()
        scanner.last_block -= catch_up_for
    elif single_block > 0:
        scanner.last_block = single_block
        scanner.one_block_per_run = True
        await scanner.run_once()
        return

    await scanner.run()


async def debug_route_tally(app):
    recorder = SwapRouteRecorder(app.deps.db.redis, key_prefix="_debug")

    await recorder.clear_old_events(0)

    async def put_one_swap_event(from_asset, to_asset, volume, days_ago):
        await recorder.store_swap_event(from_asset, to_asset, volume, datetime.now() - timedelta(days=days_ago))

    # Storing example events
    await put_one_swap_event("BTC", "RUNE", 5542.0, 0)

    await put_one_swap_event("BNB", "ETH", 1.0, 1)
    await put_one_swap_event("BNB", "ETH", 1.42, 1)
    await put_one_swap_event("BTC", "BNB", 3.0, 1)

    await put_one_swap_event("BNB", "ETH", 0.11, 2)
    await put_one_swap_event("BNB", "ETH", 0.22, 2)
    await put_one_swap_event("BTC", "ETH", 5.5, 2)

    await put_one_swap_event("BNB", "ETH", 0.01, 3)
    await put_one_swap_event("BNB", "ETH", 0.02, 3)
    await put_one_swap_event("BTC", "ETH", 0.03, 3)
    await put_one_swap_event("RUNE", "BTC", 100.0, 3)

    await put_one_swap_event("BNB", "ETH", 0.01, 13)
    await put_one_swap_event("BNB", "ETH", 0.02, 13)
    await put_one_swap_event("BTC", "ETH", 0.03, 13)
    await put_one_swap_event("RUNE", "BTC", 100.0, 13)

    # Getting top swap routes by volume for the last 7 days
    top_routes = await recorder.get_top_swap_routes_by_volume(days=1, top_n=3)
    print(f"Top swap routes for the previous 1 days: {top_routes}")

    top_routes = await recorder.get_top_swap_routes_by_volume(days=7, top_n=3)
    print(f"Top swap routes for the previous 7 days: {top_routes}")

    # Clearing old events older than 7 days
    await recorder.clear_old_events(31)


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await debug_route_tally(app)
        # await app.deps.pool_fetcher.run_once()
        # await demo_block_scanner_count(app, single_block=6161871)
        await demo_block_scanner_count(app, catch_up_for=500)


if __name__ == '__main__':
    asyncio.run(main())
