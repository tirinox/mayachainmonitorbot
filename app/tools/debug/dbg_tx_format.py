import asyncio
import random
from typing import List

from localization.languages import Language
from localization.manager import BaseLocalization
from services.jobs.affiliate_merge import AffiliateTXMerger, ZERO_HASH
from services.jobs.fetch.tx import TxFetcher
from services.jobs.volume_filler import VolumeFillerUpdater
from services.lib.constants import Chains, thor_to_float
from services.lib.explorers import get_explorer_url_to_address
from services.lib.midgard.name_service import NameMap
from services.lib.midgard.parser import get_parser_by_network_id
from services.lib.midgard.urlgen import free_url_gen
from services.lib.money import DepthCurve
from services.lib.texts import sep
from services.lib.w3.aggregator import AggregatorDataExtractor
from services.models.pool_info import PoolInfo
from services.models.tx import ThorTx
from services.models.tx_type import TxType
from services.notify.types.tx_notify import SwapTxNotifier, LiquidityTxNotifier
from tools.lib.lp_common import LpAppFramework, load_sample_txs, Receiver


async def midgard_test_donate(app, mdg, tx_parser):
    q_path = free_url_gen.url_for_tx(0, 10, types='donate')
    j = await mdg.request(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    await send_tx_notification(app, random.sample(txs, 1)[0])


async def present_one_aff_tx(app, q_path, find_aff=False):
    mdg = app.deps.midgard_connector
    ex_tx = await load_tx(app, mdg, q_path, find_aff)
    await send_tx_notification(app, ex_tx)


async def demo_find_last_savers_additions(app: LpAppFramework):
    d = app.deps
    fetcher_tx = TxFetcher(d, tx_types=(TxType.ADD_LIQUIDITY,))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    txs = await fetcher_tx.fetch_all_tx(liquidity_change_only=True, max_pages=5)
    for tx in txs:
        if tx.first_pool == 'BTC/BTC':
            url = get_explorer_url_to_address(d.cfg.network_id, Chains.MAYA, tx.sender_address)
            amt = thor_to_float(tx.first_input_tx.first_amount)
            print(f'{tx.first_pool} ({url}) amount = {amt} {tx.first_input_tx.first_asset}')
            sep()


async def load_tx(app, mdg, q_path, find_aff=False):
    tx_parser = get_parser_by_network_id(app.deps.cfg.network_id)
    j = await mdg.request(q_path)
    txs = tx_parser.parse_tx_response(j).txs
    txs_merged = AffiliateTXMerger().merge_affiliate_txs(txs)
    tx = next(tx for tx in txs_merged if tx.affiliate_fee > 0) if find_aff else txs_merged[0]
    return tx


async def send_tx_notification(app, ex_tx, loc: BaseLocalization = None):
    await app.deps.pool_fetcher.run_once()
    pool = ex_tx.first_pool_l1
    pool_info: PoolInfo = app.deps.price_holder.pool_info_map.get(pool)
    full_rune = ex_tx.calc_full_rune_amount(app.deps.price_holder.pool_info_map)

    # profit_calc = StreamingSwapVsCexProfitCalculator(app.deps)
    # await profit_calc.get_cex_data_v2(ex_tx)

    print(f'{ex_tx.affiliate_fee = }')
    rune_price = app.deps.price_holder.usd_per_rune
    print(f'{ex_tx.get_affiliate_fee_usd(rune_price) = } $')
    print(f'{full_rune = } R')

    nm = NameMap.empty()

    for lang in [Language.RUSSIAN, Language.ENGLISH, Language.ENGLISH_TWITTER]:
        loc = app.deps.loc_man[lang]
        text = loc.notification_text_large_single_tx(ex_tx, rune_price, pool_info,
                                                     name_map=nm,
                                                     mimir=app.deps.mimir_const_holder)
        await app.send_test_tg_message(text)
        sep()
        print(text)


async def refund_full_rune(app):
    txs = load_sample_txs('./tests/sample_data/refunds.json')
    volume_filler = VolumeFillerUpdater(app.deps)
    await volume_filler.fill_volumes(txs)


async def demo_full_tx_pipeline(app: LpAppFramework, announce=True):
    d = app.deps

    await d.mimir_const_fetcher.run_once()

    fetcher_tx = TxFetcher(d, tx_types=(TxType.ADD_LIQUIDITY, TxType.WITHDRAW, TxType.SWAP))

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    all_accepted_tx_hashes = set()

    async def print_hashes(_, txs: List[ThorTx]):
        hashes = {tx.tx_hash for tx in txs}
        sep()
        print('Accepted hashes = ', hashes)
        print(f'Pending hashes = ({len(fetcher_tx.pending_hash_to_height)}) {fetcher_tx.pending_hash_to_height}')

        if hashes & all_accepted_tx_hashes:
            sep()
            print('Attention! Duplicates found!')
            print('Duplicates found: ', hashes & all_accepted_tx_hashes)
            sep()
        all_accepted_tx_hashes.update(hashes)

    aggregator.add_subscriber(Receiver(callback=print_hashes))

    if announce:
        curve = DepthCurve.default()
        swap_notifier_tx = SwapTxNotifier(d, d.cfg.tx.swap, curve=curve)
        swap_notifier_tx.curve_mult = 0.00001
        swap_notifier_tx.min_usd_total = 5000.0
        swap_notifier_tx.aff_fee_min_usd = 0.3
        volume_filler.add_subscriber(swap_notifier_tx)
        swap_notifier_tx.add_subscriber(app.deps.alert_presenter)

        liq_notifier_tx = LiquidityTxNotifier(d, d.cfg.tx.liquidity, curve=curve)
        liq_notifier_tx.curve_mult = 0.1
        liq_notifier_tx.min_usd_total = 50.0
        liq_notifier_tx.ilp_paid_min_usd = 10.0
        volume_filler.add_subscriber(liq_notifier_tx)
        liq_notifier_tx.add_subscriber(app.deps.alert_presenter)

        # swap_notifier_tx.add_subscriber(Receiver('Swap TX'))
        # liq_notifier_tx.add_subscriber(Receiver('Liq TX'))

    # run the pipeline!
    await fetcher_tx.run()

    # await demo_run_txs_example_file(fetcher_tx, 'swap_with_aff_new.json')
    # await demo_run_txs_example_file(fetcher_tx, 'withdraw_ilp.json')
    # await demo_run_txs_example_file(fetcher_tx, 'swap_synth_synth.json')
    # await demo_run_txs_example_file(fetcher_tx, 'add_withdraw_big.json')
    await asyncio.sleep(10.0)


async def demo_verify_tx_scanner_in_the_past(app: LpAppFramework):
    d = app.deps

    fetcher_tx = TxFetcher(d)

    aggregator = AggregatorDataExtractor(d)
    fetcher_tx.add_subscriber(aggregator)

    volume_filler = VolumeFillerUpdater(d)
    aggregator.add_subscriber(volume_filler)

    page = 0

    n_zeros = 0

    while True:
        batch_txs = await fetcher_tx.fetch_one_batch(page, tx_types=TxType.ALL_EXCEPT_DONATE)
        batch_txs = batch_txs.txs
        batch_txs = fetcher_tx.merge_related_txs(batch_txs)
        for tx in batch_txs:
            if tx.tx_hash == ZERO_HASH:
                n_zeros += 1
                continue

        print(f'TX hash => {n_zeros} zeros')

        await volume_filler.on_data(fetcher_tx, batch_txs)

        page += 1


async def find_affiliate_txs(app: LpAppFramework, desired_count=5, tx_types=None):
    d = app.deps
    fetcher_tx = TxFetcher(d)

    interesting_txs = []
    page = 0
    tx_types = tx_types or (TxType.ADD_LIQUIDITY, TxType.WITHDRAW, TxType.SWAP)
    while len(interesting_txs) < desired_count:
        page_results = await fetcher_tx.fetch_one_batch(page, tx_types=tx_types)
        for tx in page_results.txs:
            if tx.meta_swap and tx.meta_swap.affiliate_address:
                interesting_txs.append(tx)
                print(f'Found interesting tx: {tx}')
        page += 1


async def demo_swap_1(app):
    q_path = free_url_gen.url_for_tx(
        0, 50, tx_type=TxType.SWAP,
        # txid='5C74163486D8A8AB36C3595A25E53C3FE07501D0772201B2F846F676A841DF33',
        txid='3C2CFED5355E5A478B5B9E3D0C4D2CC672870AA7B4F442A56E79C1714800ACBB',
    )
    await present_one_aff_tx(app, q_path)
    # q_path = free_url_gen.url_for_tx(0, 50, address='bnb10gh0p6thzjz54jqy9lg0rv733fnl0vqmc789pp')


async def main():
    app = LpAppFramework()
    await app.prepare(brief=True)

    await demo_swap_1(app)


if __name__ == '__main__':
    asyncio.run(main())
