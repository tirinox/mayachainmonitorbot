from abc import ABC, abstractmethod
from math import log10, floor

from aiogram.types import *

from services.models.cap_info import ThorInfo
from services.models.tx import StakeTx


class BaseLocalization(ABC):
    # ----- WELCOME ------

    @abstractmethod
    def welcome_message(self, info: ThorInfo): ...

    BUTTON_RUS = 'Русский'
    BUTTON_ENG = 'English'

    def lang_help(self):
        return (f'Пожалуйста, выберите язык / Please select a language',
                ReplyKeyboardMarkup(keyboard=[[
                    KeyboardButton(self.BUTTON_RUS),
                    KeyboardButton(self.BUTTON_ENG)
                ]], resize_keyboard=True, one_time_keyboard=True))

    # ------- CAP -------

    @abstractmethod
    def notification_cap_change_text(self, old: ThorInfo, new: ThorInfo): ...

    @abstractmethod
    def price_message(self, info: ThorInfo): ...

    # ------- STAKES -------

    @abstractmethod
    def tx_text(self, tx: StakeTx, rune_per_dollar): ...


def number_commas(x):
    if not isinstance(x, int):
        raise TypeError("Parameter must be an integer.")
    if x < 0:
        return '-' + number_commas(-x)
    result = ''
    while x >= 1000:
        x, r = divmod(x, 1000)
        result = f",{r:03d}{result}"
    return f"{x:d}{result}.0"


def round_to_dig(x, e=2):
    return round(x, -int(floor(log10(abs(x)))) + e - 1)


def pretty_money(x):
    if x < 0:
        return "-" + pretty_money(-x)
    else:
        if x < 100:
            return str(round_to_dig(x, 2))
        else:
            return number_commas(int(round(x)))