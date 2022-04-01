import math
from dataclasses import dataclass
from math import floor, log10

EMOJI_SCALE = [
    # negative
    (-50, '💥'), (-35, '👺'), (-25, '🥵'), (-20, '😱'), (-15, '😨'), (-10, '😰'), (-5, '😢'), (-3, '😥'), (-2, '😔'),
    (-1, '😑'), (0, '😕'),
    # positive
    (1, '😏'), (2, '😄'), (3, '😀'), (5, '🤗'), (10, '🍻'), (15, '🎉'), (20, '💸'), (25, '🔥'), (35, '🌙'), (50, '🌗'),
    (65, '🌕'), (80, '⭐'), (100, '✨'), (10000000, '🚀')
]

RAIDO_GLYPH = 'ᚱ'


def emoji_for_percent_change(pc):
    for threshold, emoji in EMOJI_SCALE:
        if pc <= threshold:
            return emoji
    return EMOJI_SCALE[-1]  # last one


def number_commas(x):
    if not isinstance(x, int):
        raise TypeError("Parameter must be an integer.")
    if x < 0:
        return '-' + number_commas(-x)
    result = ''
    while x >= 1000:
        x, r = divmod(x, 1000)
        result = f",{r:03d}{result}"
    return f"{x:d}{result}"


def round_to_dig(x, e=2):
    return round(x, -int(floor(log10(abs(x)))) + e - 1)


def pretty_dollar(x, signed=False, postfix='', short_form=False):
    return pretty_money(x, prefix='$', postfix=postfix, signed=signed, short_form=short_form)


def pretty_rune(x, signed=False, prefix='', short_form=False):
    return pretty_money(x, postfix=RAIDO_GLYPH, signed=signed, prefix=prefix, short_form=short_form)


def _number_short_with_postfix_step(x, up, pf, pf_next, precision):
    prec_const = 10 ** precision
    up_exp = 10 ** up
    y = round(x / up_exp * prec_const) / prec_const
    if y == 1000.0:
        return 1.0, pf_next
    else:
        return y, pf


def number_short_with_postfix(x: float, precision=1):
    x = float(x)
    if x < 0:
        return f'-{number_short_with_postfix(-x)}'

    if x < 1e3:
        return f'{x}'
    elif x < 1e6:
        x, postfix = _number_short_with_postfix_step(x, 3, 'K', 'M', precision)
    elif x < 1e9:
        x, postfix = _number_short_with_postfix_step(x, 6, 'M', 'B', precision)
    elif x < 1e12:
        x, postfix = _number_short_with_postfix_step(x, 9, 'B', 'T', precision)
    elif x < 1e15:
        x, postfix = _number_short_with_postfix_step(x, 12, 'T', 'Q', precision)
    else:
        return f'{x:.2E}'

    return f'{x}{postfix}'


def pretty_money(x, prefix='', signed=False, postfix='', short_form=False):
    if x < 0:
        return f"-{prefix}{pretty_money(-x)}{postfix}"
    elif x == 0:
        r = "0.0"
    else:
        if x < 1e-4:
            r = f'{x:.4f}'
        elif x < 100:
            r = str(round_to_dig(x, 3))
        elif x < 1000:
            r = str(round_to_dig(x, 4))
        else:
            x = int(round(x))
            if short_form:
                r = number_short_with_postfix(x)
            else:
                r = number_commas(x)
    prefix = f'+{prefix}' if signed else prefix
    return f'{prefix}{r}{postfix}'


def too_big(x, limit_abs=1e7):
    return math.isinf(x) or math.isnan(x) or abs(x) > limit_abs


def pretty_percent(x, limit_abs=1e7, limit_text='N/A %', signed=True):
    if too_big(x, limit_abs):
        return limit_text
    return pretty_money(x, postfix=' %', signed=signed)


def round_half_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.floor(n * multiplier + 0.5) / multiplier


def short_money(x, prefix='', postfix='', localization=None, signed=False):
    if x == 0:
        return f'{prefix}0.0{postfix}'

    if hasattr(localization, 'SHORT_MONEY_LOC'):
        localization = localization.SHORT_MONEY_LOC
    localization = localization or {}

    if x < 0:
        sign = '-'
        x = -x
    else:
        sign = '+' if signed and x >= 0 else ''
    orig_x = x

    if x < 1_000:
        key = ''
    elif x < 1_000_000:
        x /= 1_000
        key = 'K'
    elif x < 1_000_000_000:
        x /= 1_000_000
        key = 'M'
    elif x < 1_000_000_000_000:
        x /= 1_000_000_000
        key = 'B'
    else:
        x /= 1_000_000_000_000
        key = 'T'

    letter = localization.get(key, key) if localization else key

    dec = 1
    if orig_x < 10:
        for dec in range(8, 0, -1):
            if orig_x < 10 ** (-dec):
                dec = dec + 1
                break
        dec = max(dec, 1)

    result = f'{round_half_up(x, dec)}{letter}'
    return f'{sign}{prefix}{result}{postfix}'


def short_dollar(x, localization=None):
    return short_money(x, prefix='$', localization=localization)


def short_address(address, begin=5, end=4, filler='...'):
    address = str(address)
    if len(address) > begin + end:
        return address[:begin] + filler + (address[-end:] if end else '')
    else:
        return address


def format_percent(x, total=1.0, signed=False):
    if total <= 0:
        s = 0
    else:
        s = x / total * 100.0

    return pretty_money(s, signed=signed) + " %"


def adaptive_round_to_str(x, force_sign=False, prefix=''):
    ax = abs(x)
    sign = ('+' if force_sign else '') if x > 0 else '-'
    sign = prefix + sign
    if ax < 1.0:
        return f"{sign}{ax:.2f}"
    elif ax < 10.0:
        return f"{sign}{ax:.1f}"
    else:
        return f"{sign}{pretty_money(ax)}"


def calc_percent_change(old_value, new_value):
    return 100.0 * (new_value - old_value) / old_value if old_value and new_value else 0.0


@dataclass
class Asset:
    chain: str = ''
    name: str = ''
    tag: str = ''
    is_synth: bool = False

    @property
    def valid(self):
        return bool(self.chain) and bool(self.name)

    def __post_init__(self):
        if self.chain and not self.name:
            source = self.chain
            a = self.from_string(source)
            self.chain = a.chain
            self.name = a.name
            self.tag = a.tag
            self.is_synth = a.is_synth

    @staticmethod
    def get_name_tag(name_and_tag_str):
        components = name_and_tag_str.split('-', maxsplit=2)
        if len(components) == 2:
            return components
        else:
            return name_and_tag_str, ''

    @classmethod
    def from_string(cls, asset: str):
        try:
            if asset == 'rune':
                return cls('THOR', 'RUNE')
            is_synth = '/' in asset
            chain, name_and_tag = asset.split('/' if is_synth else '.', maxsplit=2)
            name, tag = cls.get_name_tag(name_and_tag)
            return cls(str(chain).upper(), str(name).upper(), str(tag).upper(), is_synth)
        except (IndexError, TypeError, ValueError):
            return cls(name=asset)

    @property
    def short_str(self):
        s = 'Synth:' if self.is_synth else ''
        if self.tag:
            short_tag = self.tag[:6]
            return f'{s}{self.chain}.{self.name}-{short_tag}'
        else:
            return f'{s}{self.chain}.{self.name}'

    @property
    def full_name(self):
        if self.valid:
            return f'{self.name}-{self.tag}' if self.tag else self.name
        else:
            return self.name

    @property
    def first_filled_component(self):
        return self.chain or self.name or self.tag

    @property
    def native_pool_name(self):
        return f'{self.chain}.{self.full_name}' if self.valid else self.name

    def __str__(self):
        return self.native_pool_name

    @classmethod
    def convert_synth_to_pool_name(cls, asset: str):
        return cls.from_string(asset).native_pool_name


def weighted_mean(values, weights):
    return sum(values[g] * weights[g] for g in range(len(values))) / sum(weights)
