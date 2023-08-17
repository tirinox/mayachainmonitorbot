import asyncio
import json

from localization.eng_base import BaseLocalization
from localization.languages import Language
from services.jobs.scanner.native_scan import NativeScannerBlock
from services.jobs.scanner.native_scan_ws import NativeScannerTransactionWS, NativeScannerBlockEventsWS
from services.jobs.scanner.native_actions import NativeActionExtractor
from services.jobs.transfer_detector import RuneTransferDetectorBlockEvents, \
    RuneTransferDetectorFromTxResult, RuneTransferDetectorTxLogs
from services.lib.config import Config
from services.lib.delegates import INotified
from services.lib.depcont import DepContainer
from services.lib.texts import sep
from services.models.transfer import RuneTransfer
from services.notify.types.transfer_notify import RuneMoveNotifier
from tools.lib.lp_common import LpAppFramework, Receiver


class ReceiverPublicText(INotified):
    def __init__(self, deps: DepContainer, lang=Language.ENGLISH_TWITTER):
        self.deps = deps
        self.loc: BaseLocalization = self.deps.loc_man.get_from_lang(lang)

    # noinspection PyTypeChecker
    async def on_data(self, sender, data):
        for tr in data:
            tr: RuneTransfer
            print(self.loc.notification_text_rune_transfer_public(tr, {}))
            sep()


async def t_tx_scanner_ws(url, reserve_address):
    scanner = NativeScannerTransactionWS(url)
    detector = RuneTransferDetectorFromTxResult(reserve_address)
    scanner.add_subscriber(detector)
    # scanner.subscribe(Receiver('TX'))
    detector.add_subscriber(Receiver('Transfer'))
    await scanner.run()


async def t_block_scanner_ws(url):
    scanner = NativeScannerBlockEventsWS(url)
    detector = RuneTransferDetectorBlockEvents()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver())
    await scanner.run()


async def demo_native_block_action_detector(app, start=12033185):
    scanner = NativeScannerBlock(app.deps, last_block=start)
    detector = RuneTransferDetectorTxLogs()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver('Transfer'))
    action_extractor = NativeActionExtractor(app.deps)
    scanner.add_subscriber(action_extractor)
    action_extractor.add_subscriber(Receiver('Action'))
    await scanner.run()


# sic!
async def demo_block_scanner_active(app, send_alerts=False):
    scanner = NativeScannerBlock(app.deps)
    detector = RuneTransferDetectorTxLogs()
    scanner.add_subscriber(detector)
    detector.add_subscriber(Receiver('Transfer'))
    if send_alerts:
        notifier = RuneMoveNotifier(app.deps)
        detector.add_subscriber(notifier)
        notifier.add_subscriber(app.deps.alert_presenter)
    await scanner.run()


async def ws_main():
    cfg = Config()
    url = cfg.as_str('thor.node.rpc_node_url')
    reserve_address = cfg.as_str('native_scanner.reserve_address')
    await t_tx_scanner_ws(url, reserve_address)


async def get_transfers_from_block(app, block_index):
    scanner = NativeScannerBlock(app.deps)
    r = await scanner.fetch_one_block(block_index)
    parser = RuneTransferDetectorTxLogs()
    transfers = parser.process_events(r)
    return transfers


async def demo_rune_transfers_once(app):
    # b = 8783469  # unbond
    # b = 8686955  # bond
    b = 8815564  # crash
    transfers = await get_transfers_from_block(app, b)

    sep()
    for tr in transfers:
        print(tr)
    sep()

    notifier = RuneMoveNotifier(app.deps)
    notifier.add_subscriber(app.deps.alert_presenter)
    await notifier.on_data(None, transfers)

    await asyncio.sleep(3.0)


async def search_out(app):
    scanner = NativeScannerBlock(app.deps)

    block_start = 6230655 - 2
    search = '687522'

    b = block_start
    while True:
        tx_logs = await scanner.fetch_block_results(b)
        if search in json.dumps(tx_logs):
            print(tx_logs)
            print(f'Found a needle in block #{b}!!! ')
            break
        b += 1


async def debug_block_scan_for_swaps(app, start=12033185):
    scanner = NativeScannerBlock(app.deps, last_block=start)
    # await scanner.run()
    blk = await scanner.fetch_one_block(12090456)
    print(blk)


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        # await demo_rune_transfers_once(app)
        # await demo_block_scanner_active(app, send_alerts=True)
        # await active_one(app)
        # await search_out(app)
        # await demo_rune_transfers_once(app)
        # await demo_test_rune_detector(app)
        # await demo_native_block_action_detector(app)
        await debug_block_scan_for_swaps(app)


if __name__ == '__main__':
    asyncio.run(main())
