from datetime import datetime
from math import ceil

from localization.base import BaseLocalization, kbd, CREATOR_TG
from services.lib.datetime import format_time_ago
from services.models.price import RuneFairPrice, PriceReport, PriceATH
from services.models.pool_info import PoolInfo
from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx, StakePoolStats
from services.lib.utils import link, code, bold, pre, x_ses, ital
from services.lib.money import pretty_dollar, pretty_money, short_address, adaptive_round_to_str, calc_percent_change, \
    emoji_for_percent_change, short_money, short_asset_name


class EnglishLocalization(BaseLocalization):
    # ---- WELCOME ----
    def help_message(self):
        return (
            f"This bot is for {link(self.THORCHAIN_LINK, 'THORChain')} monitoring.\n"
            f"Command list:\n"
            f"/help – this help page\n"
            f"/start – start/restart the bot\n"
            f"/lang – set the language\n"
            f"/cap – the current liquidity cap of Chaosnet\n"
            f"/price – the current Rune price.\n"
            f"<b>⚠️ All notifications are forwarded to @thorchain_alert channel!</b>\n"
            f"🤗 Support and feedback: {CREATOR_TG}."
        )

    def welcome_message(self, info: ThorInfo):
        return (
            f"Hello! <b>{pretty_money(info.stacked)} {self.R}</b> of <b>{pretty_money(info.cap)} {self.R}</b> pooled.\n"
            f"{self._cap_progress_bar(info)}"
            f"The {self.R} price is <code>${info.price:.3f}</code> now.\n"
            f"<b>⚠️ All notifications are forwarded to @thorchain_alert channel!</b>\n"
            f"🤗 Support and feedback: {CREATOR_TG}."
        )

    def unknown_command(self):
        return (
            "🙄 Sorry, I didn't understand that command.\n"
            "Use /help to see available commands."
        )

    # ----- MAIN MENU ------

    BUTTON_MM_MY_ADDRESS = '🏦 Manage my address'
    BUTTON_MM_CAP = '📐 Liquidity cap'
    BUTTON_MM_PRICE = f'💲 {BaseLocalization.R} price info'

    def kbd_main_menu(self):
        return kbd([self.BUTTON_MM_MY_ADDRESS, self.BUTTON_MM_PRICE, self.BUTTON_MM_CAP])

    # ------ STAKE INFO -----

    BUTTON_SM_ADD_ADDRESS = '➕ Add an address'
    BUTTON_BACK = '🔙 Back'
    BUTTON_SM_BACK_TO_LIST = '🔙 Back to list'

    BUTTON_VIEW_RUNESTAKEINFO = '🌎 View it on runestake.info'
    BUTTON_VIEW_VALUE_ON = 'Show value: ON'
    BUTTON_VIEW_VALUE_OFF = 'Show value: OFF'
    BUTTON_REMOVE_THIS_ADDRESS = '❌ Remove this address'

    TEXT_NO_ADDRESSES = "🔆 You have not added any addresses yet. Send me one."
    TEXT_YOUR_ADDRESSES = '🔆 You added addresses:'
    TEXT_INVALID_ADDRESS = code('⛔️ Invalid address!')
    TEXT_SELECT_ADDRESS_ABOVE = 'Select one from above. ☝️ '
    TEXT_SELECT_ADDRESS_SEND_ME = 'If you want to add one more, please send me it. 👇'

    def pic_stake_days(self, total_days, first_stake_ts):
        start_date = datetime.fromtimestamp(first_stake_ts).strftime('%d.%m.%Y')
        return f'{ceil(total_days)} days ({start_date})'

    def text_stake_loading_pools(self, address):
        return f'⏳ <b>Please wait.</b>\n' \
               f'Loading pools information for {pre(address)}...'

    def text_stake_provides_liq_to_pools(self, address, pools):
        pools = pre(', '.join(pools))
        thor_tx = link(self.thor_explore_address(address), 'viewblock.io')
        bnb_tx = link(self.binance_explore_address(address), 'explorer.binance.org')
        return f'🛳️ {pre(address)}\nprovides liquidity to the following pools:\n' \
               f'{pools}.\n\n' \
               f"🔍 Explorers: {thor_tx}; {bnb_tx}.\n\n" \
               f'👇 Click on the button to get a detailed card.'

    def text_stake_today(self):
        today = datetime.now().strftime('%d.%m.%Y')
        return f'Today is {today}'

    # ----- CAP ------
    def notification_text_cap_change(self, old: ThorInfo, new: ThorInfo):
        verb = "has been increased" if old.cap < new.cap else "has been decreased"
        call = "Come on, add more liquidity!\n" if new.cap > old.cap else ''
        message = (
            f'<b>Pool cap {verb} from {pretty_money(old.cap)} to {pretty_money(new.cap)}!</b>\n'
            f'Currently <b>{pretty_money(new.stacked)}</b> {self.R} are in the liquidity pools.\n'
            f"{self._cap_progress_bar(new)}"
            f'The price of {self.R} in the pool is <code>{new.price:.3f} BUSD</code>.\n'
            f'{call}'
            f'https://chaosnet.bepswap.com/'
        )
        return message

    # ------ PRICE -------
    def price_message(self, info: ThorInfo, fair_price: RuneFairPrice):
        return (
            f"Last real price of {self.R} is <code>${info.price:.3f}</code>.\n"
            f"Deterministic price of {self.R} is <code>${fair_price.fair_price:.3f}</code>."
        )

    # ------ TXS -------
    def notification_text_large_tx(self, tx: StakeTx, dollar_per_rune: float, pool: StakePoolStats,
                                   pool_info: PoolInfo):
        msg = ''
        if tx.type == 'stake':
            msg += f'🐳 <b>Whale added liquidity</b> 🟢\n'
        elif tx.type == 'unstake':
            msg += f'🐳 <b>Whale removed liquidity</b> 🔴\n'

        total_usd_volume = tx.full_rune * dollar_per_rune if dollar_per_rune != 0 else 0.0
        pool_depth_usd = pool_info.usd_depth(dollar_per_rune)
        thor_tx = link(self.thor_explore_address(tx.address), short_address(tx.address))
        bnb_tx = link(self.binance_explore_address(tx.address), short_address(tx.address))

        rp, ap = tx.symmetry_rune_vs_asset()

        rune_side_usd = tx.rune_amount * dollar_per_rune
        rune_side_usd_short = short_money(rune_side_usd)
        asset_side_usd_short = short_money(total_usd_volume - rune_side_usd)
        percent_of_pool = pool_info.percent_share(tx.full_rune)

        msg += (
            f"<b>{pretty_money(tx.rune_amount)} {self.R}</b> ({rp:.0f}% = {rune_side_usd_short}) ↔️ "
            f"<b>{pretty_money(tx.asset_amount)} {short_asset_name(tx.pool)}</b> ({ap:.0f}% = {asset_side_usd_short})\n"
            f"Total: <code>${pretty_money(total_usd_volume)}</code> ({percent_of_pool:.2f}% of the whole pool).\n"
            f"Pool depth is <b>${pretty_money(pool_depth_usd)}</b> now.\n"
            f"Thor explorer: {thor_tx} / Binance explorer: {bnb_tx}."
        )

        return msg

    # ------- QUEUE -------

    def notification_text_queue_update(self, item_type, step, value):
        if step == 0:
            return f"☺️ Queue {code(item_type)} is empty again!"
        else:
            return (
                f"🤬 <b>Attention!</b> Queue {code(item_type)} has {value} transactions!\n"
                f"{code(item_type)} transactions may be delayed."
            )

    # ------- PRICE -------

    def notification_text_price_update(self, p: PriceReport, ath=False, last_ath: PriceATH = None):
        title = bold('Price update') if not ath else bold('🚀 A new all-time high has been achieved!')

        c_gecko_url = 'https://www.coingecko.com/en/coins/thorchain'
        c_gecko_link = link(c_gecko_url, 'RUNE')

        message = f"{title} | {c_gecko_link}\n\n"
        price = p.fair_price.real_rune_price

        pr_text = f"${price:.2f}"
        message += f"<b>RUNE</b> price is {code(pr_text)} now.\n"

        if last_ath is not None:
            last_ath_pr = f'{last_ath.ath_price:.2f}'
            message += f"Last ATH was ${pre(last_ath_pr)} ({format_time_ago(last_ath.ath_date)}).\n"

        time_combos = zip(
            ('1h', '24h', '7d'),
            (p.price_1h, p.price_24h, p.price_7d)
        )
        for title, old_price in time_combos:
            if old_price:
                pc = calc_percent_change(old_price, price)
                message += pre(f"{title.rjust(4)}:{adaptive_round_to_str(pc, True).rjust(8)} % "
                               f"{emoji_for_percent_change(pc).ljust(4).rjust(6)}") + "\n"

        fp = p.fair_price
        if fp.rank >= 1:
            message += f"Coin market cap is {bold(pretty_dollar(fp.market_cap))} (#{bold(fp.rank)})\n"

        if fp.tlv_usd >= 1:
            det_link = link(self.DET_PRICE_HELP_PAGE, 'deterministic price')
            message += (f"TVL of non-RUNE assets: ${pre(pretty_money(fp.tlv_usd))}\n"
                        f"So {det_link} of RUNE is {code(pretty_money(fp.fair_price, prefix='$'))}\n"
                        f"Speculative multiplier is {pre(x_ses(fp.fair_price, price))}\n")

        return message.rstrip()

    # ------- POOL CHURN -------

    def notification_text_pool_churn(self, added_pools, removed_pools, changed_status_pools):
        message = bold('🏊 Liquidity pool churn!') + '\n\n'

        def pool_text(pool_name, status, to_status=None):
            t = link(self.pool_link(pool_name), pool_name)
            extra = '' if to_status is None else f' → {ital(to_status)}'
            return f'  • {t} ({ital(status)}{extra})'

        if added_pools:
            message += '✅ Pools added:\n' + '\n'.join([pool_text(*a) for a in added_pools]) + '\n\n'
        if removed_pools:
            message += '❌ Pools removed:\n' + '\n'.join([pool_text(*a) for a in removed_pools]) + '\n\n'
        if changed_status_pools:
            message += '🔄 Pools changed:\n' + '\n'.join([pool_text(*a) for a in changed_status_pools]) + '\n\n'

        return message.rstrip()