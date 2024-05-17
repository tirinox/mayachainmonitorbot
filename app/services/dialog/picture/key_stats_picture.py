import asyncio
from datetime import timedelta

from PIL import Image, ImageDraw

from localization.manager import BaseLocalization
from services.dialog.picture.common import BasePictureGenerator
from services.dialog.picture.resources import Resources
from services.lib.constants import BTC_SYMBOL, ETH_SYMBOL, ETH_USDC_SYMBOL, ETH_USDT_SYMBOL, KUJI_USK_SYMBOL, \
    RUNE_SYMBOL
from services.lib.draw_utils import paste_image_masked, result_color, TC_LIGHTNING_BLUE, TC_YGGDRASIL_GREEN, \
    dual_side_rect, COLOR_OF_PROFIT, font_estimate_size
from services.lib.money import pretty_money, short_dollar, short_money, format_percent, Asset, AssetRUNE, short_rune
from services.lib.texts import bracketify
from services.lib.utils import async_wrap
from services.models.key_stats_model import AlertKeyStats


class KeyStatsPictureGenerator(BasePictureGenerator):
    BASE = './data'
    BG_FILE = f'{BASE}/key_weekly_stats_bg.png'

    def __init__(self, loc: BaseLocalization, event: AlertKeyStats):
        super().__init__(loc)
        self.bg = Image.open(self.BG_FILE)
        self.event = event
        self.logos = {}
        self.r = Resources()
        self.btc_logo = None
        self.eth_logo = None
        self.usdt_logo = self.usdc_logo = self.usk_logo = None
        self.rune_logo = None

    FILENAME_PREFIX = 'MayaChain_weekly_stats'

    async def prepare(self):
        self.btc_logo, self.eth_logo, self.usdt_logo, self.usdc_logo, self.usk_logo, self.rune_logo = \
            await asyncio.gather(
                self.r.logo_downloader.get_or_download_logo_cached(BTC_SYMBOL),
                self.r.logo_downloader.get_or_download_logo_cached(ETH_SYMBOL),
                self.r.logo_downloader.get_or_download_logo_cached(ETH_USDT_SYMBOL),
                self.r.logo_downloader.get_or_download_logo_cached(ETH_USDC_SYMBOL),
                self.r.logo_downloader.get_or_download_logo_cached(KUJI_USK_SYMBOL),
                self.r.logo_downloader.get_or_download_logo_cached(RUNE_SYMBOL),
            )

        logo_size_mini = int(self.btc_logo.width * 0.66)
        self.usdc_logo.thumbnail((logo_size_mini, logo_size_mini))
        self.usdt_logo.thumbnail((logo_size_mini, logo_size_mini))
        self.usk_logo.thumbnail((logo_size_mini, logo_size_mini))

        logo_size_norm = int(self.btc_logo.width * 0.75)
        self.btc_logo.thumbnail((logo_size_norm, logo_size_norm))
        self.eth_logo.thumbnail((logo_size_norm, logo_size_norm))
        self.rune_logo.thumbnail((logo_size_norm, logo_size_norm))

    @staticmethod
    def percent_change(old_v, new_v):
        return (new_v - old_v) / old_v * 100.0 if old_v else 0.0

    def text_and_change(self, old_v, new_v, draw, x, y, text, font_main, font_second, fill='#fff',
                        x_shift=20, y_shift=6):
        draw.text((x, y), text, font=font_main, fill=fill, anchor='lm')

        percent = self.percent_change(old_v, new_v)

        size_x, _ = font_estimate_size(font_main, text)
        if abs(percent) > 0.1:
            draw.text(
                (x + size_x + x_shift, y + y_shift),
                bracketify(short_money(percent, postfix='%', signed=True)),
                anchor='lm', fill=result_color(percent), font=font_second
            )

    @async_wrap
    def _get_picture_sync(self):
        # prepare data
        r, loc, e = self.r, self.loc, self.event

        # prepare painting stuff
        image = self.bg.copy()
        draw = ImageDraw.Draw(image)

        # Week dates
        start_date = e.end_date - timedelta(days=e.days)
        period_str = self.loc.text_key_stats_period(start_date, e.end_date)

        x_col_1, x_col_2, x_col_3 = 100, 769, 1423

        draw.text((1900, 120), period_str,
                  fill='#fff', font=r.fonts.get_font_bold(52),
                  anchor='rm')

        # Block subtitles
        subtitle_font = r.fonts.get_font_bold(50)
        for x, caption in [
            (x_col_1, loc.TEXT_PIC_STATS_NATIVE_ASSET_VAULTS),
            (x_col_2, loc.TEXT_PIC_STATS_WEEKLY_REVENUE),
            (x_col_3, loc.TEXT_PIC_STATS_SWAP_INFO)
        ]:
            draw.text((x, 362),
                      caption, fill='#c6c6c6', font=subtitle_font,
                      anchor='ls')  # s stands for "Baseline"

        # ----- Block vaults -----

        font_small_n = r.fonts.get_font(34)
        font_indicator_name = r.fonts.get_font(42)

        vault_contents = [
            (' ₿', self.btc_logo, e.get_sum((BTC_SYMBOL,), previous=True), e.get_sum((BTC_SYMBOL,))),
            (' Ξ', self.eth_logo, e.get_sum((ETH_SYMBOL,), previous=True), e.get_sum((ETH_SYMBOL,))),
            (' R', self.rune_logo, e.get_sum((RUNE_SYMBOL,), previous=True), e.get_sum((RUNE_SYMBOL,))),
            ('usd', self.usdc_logo, e.get_stables_sum(previous=True), e.get_stables_sum()),
        ]

        coin_x = 151
        coin_font = r.fonts.get_font_bold(54)

        v_start_y, v_delta_y = 473, 112
        v_y = v_start_y
        for postfix, logo, old_v, new_v in vault_contents:
            if postfix == 'usd':
                paste_image_masked(image, self.usk_logo, (coin_x - 30, v_y))
            paste_image_masked(image, logo, (coin_x, v_y))
            if postfix == 'usd':
                paste_image_masked(image, self.usdt_logo, (coin_x + 30, v_y))

            if postfix == 'usd':
                text = short_dollar(new_v)
            elif logo == self.rune_logo:
                text = short_money(new_v, postfix=postfix)
            else:
                text = pretty_money(new_v, postfix=postfix)

            text_x = coin_x + 110

            self.text_and_change(old_v, new_v, draw, text_x, v_y,
                                 text, coin_font, font_small_n)
            v_y += v_delta_y

        # helper:
        def _indicator(_x, _y, name, text_value, old_value, new_value, _margin=72):
            draw.text((_x, _y),
                      name,
                      anchor='lt', fill='#fff',
                      font=font_indicator_name)

            if text_value:
                self.text_and_change(
                    old_value, new_value,
                    draw, _x, _y + _margin,
                    text_value,
                    coin_font, font_small_n
                )

        # ------- total native asset pooled -------

        margin, delta_y = 78, 160
        y = 920

        _indicator(100, y, loc.TEXT_PIC_STATS_NATIVE_ASSET_POOLED,
                   short_dollar(e.pool_usd),
                   e.pool_usd_prev, e.pool_usd)

        # ------- total network security usd -------

        net_sec_y = y + delta_y
        _indicator(100, net_sec_y, loc.TEXT_PIC_STATS_NETWORK_SECURITY,
                   short_dollar(e.bond_usd),
                   e.bond_usd_prev, e.bond_usd)

        # 2. Block
        # -------- protocol revenue -----

        x = x_col_2

        _indicator(x, 442,
                   loc.TEXT_PIC_STATS_PROTOCOL_REVENUE,
                   short_dollar(e.protocol_revenue_usd),
                   e.protocol_revenue_usd_prev, e.protocol_revenue_usd)

        _indicator(x, 623,
                   loc.TEXT_PIC_STATS_AFFILIATE_REVENUE,
                   short_dollar(e.affiliate_revenue_usd),
                   e.protocol_revenue_usd_prev, e.affiliate_revenue_usd)

        # ----- top 3 affiliates table -----

        draw.text((x, 780),
                  loc.TEXT_PIC_STATS_TOP_AFFILIATE,
                  fill='#fff',
                  font=font_indicator_name)

        n_max = 3
        y = 844
        y_margin = 60
        font_aff = r.fonts.get_font_bold(40)
        for i, aff_collector in enumerate(e.affiliates.top_affiliate_collectors_this_week[:n_max], start=1):
            label = aff_collector.code
            fee_usd = aff_collector.current_week_summary.fees_usd
            text = f'{i}. {label}'
            draw.text((x, y),
                      text,
                      font=font_aff,
                      fill='#fff')
            w, _ = font_estimate_size(font_aff, text)

            draw.text((x + w + 20, y + 6),
                      bracketify(short_dollar(fee_usd)),
                      # fill='#afa',
                      fill=COLOR_OF_PROFIT,
                      font=font_small_n)

            y += y_margin

        # ----- organic fees vs block rewards

        # todo: put here maya revenues!

        _indicator(x, net_sec_y, loc.TEXT_PIC_MAYA_HOLDER_DIVIDENDS,
                   short_dollar(e.maya_revenue_usd),
                   e.maya_revenue_usd_prev, e.maya_revenue_usd)

        # draw.text((x, 1050),
        #           loc.TEXT_PIC_STATS_ORGANIC_VS_BLOCK_REWARDS,
        #           fill='#fff',
        #           font=r.fonts.get_font(37))
        #
        # font_fee = r.fonts.get_font_bold(32)
        # x_right = 1283

        # y_p, y_bar = 1142, 1105
        #
        # dual_side_rect(draw, x, y_bar, x_right, y_bar + 14,
        #                liq_fee_usd, block_rewards_usd,
        #                TC_YGGDRASIL_GREEN, TC_LIGHTNING_BLUE)
        #
        # draw.text((x, y_p),
        #           format_percent(organic_ratio, 1, threshold=0.0),
        #           font=font_fee,
        #           anchor='lm',
        #           fill=TC_YGGDRASIL_GREEN)
        #
        # draw.text((x_right, y_p),
        #           format_percent(block_ratio, 1, threshold=0.0),
        #           font=font_fee,
        #           anchor='rm',
        #           fill=TC_LIGHTNING_BLUE)

        # 3. Block

        x, y = x_col_3, 442

        # ---- unique swappers -----

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_UNIQUE_SWAPPERS,
                   pretty_money(e.unique_swapper_count),
                   e.unique_swapper_count_prev, e.unique_swapper_count)

        # ---- count of swaps ----

        y += 159

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_NUMBER_OF_SWAPS,
                   pretty_money(e.number_of_swaps),
                   e.number_of_swaps_prev, e.number_of_swaps)

        # ---- swap volume -----

        y += 159

        _indicator(x, y,
                   loc.TEXT_PIC_STATS_USD_VOLUME,
                   short_dollar(e.swap_volume_usd),
                   e.swap_volume_usd_prev, e.swap_volume_usd)

        # ---- routes ----

        y += 159

        draw.text((x, y),
                  loc.TEXT_PIC_STATS_TOP_SWAP_ROUTES,
                  fill='#fff',
                  font=font_indicator_name)

        y += 60
        y_margin = 60

        font_routes = r.fonts.get_font_bold(40)
        for i, ((label_left, label_right), volume) in zip(range(1, n_max + 1), e.top_swap_routes):
            l_asset, r_asset = Asset(label_left), Asset(label_right)

            text = f'{i}. {l_asset.name} ⇌ {r_asset.name}'

            draw.text((x, y),
                      text,
                      font=font_routes,
                      fill='#fff')

            w, _ = font_estimate_size(font_routes, text)

            draw.text((x + w + 20, y + 6),
                      bracketify(short_dollar(volume)),
                      fill=COLOR_OF_PROFIT,
                      font=font_small_n)

            y += y_margin

        return image
