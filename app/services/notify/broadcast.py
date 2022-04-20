import asyncio
import logging
import random
import time
import typing
from io import BytesIO
from typing import List

from aiogram.utils import exceptions

from localization import LocalizationManager
from services.dialog.discord.discord_bot import DiscordBot
from services.dialog.slack.slack_bot import SlackBot
from services.lib.constants import Messengers
from services.lib.depcont import DepContainer
from services.lib.telegram import TelegramStickerDownloader, TELEGRAM_MAX_MESSAGE_LENGTH, TELEGRAM_MAX_CAPTION_LENGTH
from services.lib.texts import MessageType, BoardMessage, CHANNEL_INACTIVE


def copy_photo(p: BytesIO):
    p.seek(0)
    new = BytesIO(p.read())
    new.name = p.name
    return new


class ChannelDescriptor(typing.NamedTuple):
    type: str
    name: str
    id: int = 0
    lang: str = 'eng'

    @classmethod
    def from_json(cls, j):
        return cls(
            str(j.get('type')).strip().lower(),
            j.get('name', ''),
            int(j.get('id', 0)),
            j.get('lang', 'eng'),
        )

    @property
    def channel_id(self):
        return self.id or self.name


class Broadcaster:
    KEY_USERS = 'thbot_users'

    EXTRA_RETRY_DELAY = 0.1

    def __init__(self, d: DepContainer):
        self.deps = d

        self._sticker_download = TelegramStickerDownloader(d.bot)
        self._broadcast_lock = asyncio.Lock()
        self._rng = random.Random(time.time())
        self.logger = logging.getLogger('broadcast')
        self.channels = list(ChannelDescriptor.from_json(j) for j in self.deps.cfg.get_pure('channels'))
        self.channels_inactive = set()

    def clear_channels_inactive(self):
        self.channels_inactive.clear()

    def remove_me_from_inactive_channels(self, ch):
        if ch:
            self.channels_inactive.remove(ch)

    def get_channels(self, chan_type):
        return [c for c in self.channels if c.type == chan_type]

    async def notify_preconfigured_channels(self, f, *args, **kwargs):
        loc_man: LocalizationManager = self.deps.loc_man
        user_lang_map = {
            chan.channel_id: loc_man.get_from_lang(chan.lang)
            for chan in self.channels
        }

        if not callable(f):  # if constant
            await self.broadcast(self.channels, f, *args, **kwargs)
            return

        async def message_gen(chat_id):
            locale = user_lang_map[chat_id]
            if hasattr(locale, f.__name__):
                loc_f = getattr(locale, f.__name__)
                call_args = args
            else:
                loc_f = f
                call_args = [locale, *args]

            if asyncio.iscoroutinefunction(loc_f):
                return await loc_f(*call_args, **kwargs)
            else:
                return loc_f(*call_args, **kwargs)

        await self.broadcast(self.channels, message_gen)

    @staticmethod
    def remove_bad_args(kwargs, dis_web_preview=False, dis_notification=False):
        if dis_web_preview:
            if 'disable_web_page_preview' in kwargs:
                del kwargs['disable_web_page_preview']
        if dis_notification:
            if 'disable_notification' in kwargs:
                del kwargs['disable_notification']
        return kwargs

    async def safe_send_message_tg(self, chat_id, text, message_type=MessageType.TEXT, *args, **kwargs) -> bool:
        try:
            bot = self.deps.bot
            if message_type == MessageType.TEXT:
                trunc_text = text[:TELEGRAM_MAX_MESSAGE_LENGTH]
                if trunc_text != text:
                    self.logger.error(f'Message is too long:\n{text[:10000]}\n... Sending is cancelled.')
                await bot.send_message(chat_id, trunc_text, *args, **kwargs)
            elif message_type == MessageType.STICKER:
                kwargs = self.remove_bad_args(kwargs, dis_web_preview=True)
                await bot.send_sticker(chat_id, sticker=text, *args, **kwargs)
            elif message_type == MessageType.PHOTO:
                kwargs = self.remove_bad_args(kwargs, dis_web_preview=True)
                trunc_text = text[:TELEGRAM_MAX_CAPTION_LENGTH]
                if trunc_text != text:
                    self.logger.error(f'Caption is too long:\n{text[:10000]}\n... Sending is cancelled.')
                await bot.send_photo(chat_id, caption=trunc_text, *args, **kwargs)
        except exceptions.ChatNotFound:
            self.logger.error(f"Target [ID:{chat_id}]: invalid user ID")
        except exceptions.RetryAfter as e:
            self.logger.error(f"Target [ID:{chat_id}]: Flood limit is exceeded. Sleep {e.timeout} seconds.")
            await asyncio.sleep(e.timeout + self.EXTRA_RETRY_DELAY)
            return await self.safe_send_message_tg(chat_id, text, message_type=message_type, *args,
                                                   **kwargs)  # Recursive call
        except exceptions.Unauthorized as e:
            self.logger.error(f"Target [ID:{chat_id}]: user is deactivated: {e!r}")
            return CHANNEL_INACTIVE
        except exceptions.TelegramAPIError:
            self.logger.exception(f"Target [ID:{chat_id}]: failed")
            return True  # tg error is not the reason to exclude the user
        except exceptions.MessageIsTooLong:
            self.logger.error(f'Message is too long:\n{text[:10000]}\n...')
            return False
        else:
            self.logger.info(f"Target [ID:{chat_id}]: success")
            return True
        return False

    def sort_and_shuffle_chats(self, chat_ids):
        numeric_ids = [i for i in chat_ids if isinstance(i, int)]
        non_numeric_ids = [i for i in chat_ids if not isinstance(i, int)]

        user_dialogs = [i for i in numeric_ids if i > 0]
        multi_chats = [i for i in numeric_ids if i < 0]
        self._rng.shuffle(user_dialogs)
        self._rng.shuffle(multi_chats)

        return non_numeric_ids + multi_chats + user_dialogs

    async def safe_send_message_discord(self, chat_id, text, message_type=MessageType.TEXT, *args, **kwargs) -> bool:
        discord: DiscordBot = self.deps.discord_bot
        if not discord:
            self.logger.error('Discord bot is disabled!')
            return False
        try:
            if message_type == MessageType.TEXT:
                await discord.send_message_to_channel(chat_id, text, need_convert=True)
            elif message_type == MessageType.STICKER:
                sticker = await self._sticker_download.get_sticker_image(text)
                await discord.send_message_to_channel(chat_id, ' ', picture=sticker)
            elif message_type == MessageType.PHOTO:
                photo = kwargs['photo']
                await discord.send_message_to_channel(chat_id, text, picture=photo, need_convert=True)
            return True
        except Exception as e:
            self.logger.exception(f'discord exception {e}, {message_type = }, text = "{text}"!')
            return False

    async def safe_send_message_slack(self, chat_id, text, message_type=MessageType.TEXT, *args,
                                      **kwargs) -> bool:
        slack: SlackBot = self.deps.slack_bot
        if not slack:
            self.logger.error('Slack bot is disabled!')
            return False

        try:
            result = ''
            if message_type == MessageType.TEXT:
                result = await slack.send_message_to_channel(chat_id, text, need_convert=True)
            elif message_type == MessageType.STICKER:
                self.logger.warning('stickers not supported yet sorry')
                sticker = await self._sticker_download.get_sticker_image(text)
                result = await slack.send_message_to_channel(chat_id, ' ', picture=sticker)
            elif message_type == MessageType.PHOTO:
                photo = kwargs['photo']
                result = await slack.send_message_to_channel(chat_id, text, picture=photo, need_convert=True)

            if result:
                self.logger.debug(f'Slack result: {result}')
            return result
        except Exception as e:
            self.logger.exception(f'Slack exception {e}, {message_type = }, text = "{text}"!')
            return False

    async def safe_send_message(self, channel_info: ChannelDescriptor,
                                text, message_type=MessageType.TEXT, *args, **kwargs) -> bool:
        chan_id = channel_info.channel_id
        if channel_info.type == Messengers.TELEGRAM:
            result = await self.safe_send_message_tg(chan_id, text, message_type, *args, **kwargs)
        elif channel_info.type == Messengers.DISCORD:
            result = await self.safe_send_message_discord(chan_id, text, message_type, *args, **kwargs)
        elif channel_info.type == Messengers.SLACK:
            result = await self.safe_send_message_slack(chan_id, text, message_type, *args, **kwargs)
        else:
            self.logger.error(f'unsupported channel type: {channel_info.type}!')
            return False

        if result == CHANNEL_INACTIVE:
            self.logger.info(f'{channel_info} became inactive!')
            self.channels_inactive.add(channel_info.channel_id)

        return result

    async def broadcast(self, channels: List[ChannelDescriptor], message, delay=0.075,
                        message_type=MessageType.TEXT, remove_bad_users=False,
                        *args, **kwargs) -> int:
        async with self._broadcast_lock:
            count = 0
            bad_ones = []

            try:
                # chat_ids = self.sort_and_shuffle_chats(chat_ids)

                for channel_info in channels:
                    extra = {}
                    if isinstance(message, str):
                        text = message
                    elif callable(message):
                        message_result = await message(channel_info.channel_id, *args, **kwargs)
                        if isinstance(message_result, BoardMessage):
                            message_type = message_result.message_type
                            if message_result.message_type is MessageType.PHOTO:
                                # noinspection PyTypeChecker
                                extra['photo'] = copy_photo(message_result.photo)
                            text = message_result.text
                        else:
                            text = message_result
                    else:
                        text = str(message)

                    if text or 'photo' in extra:
                        send_results = await self.safe_send_message(
                            channel_info, text, message_type=message_type,
                            disable_web_page_preview=True,
                            disable_notification=False, **extra)

                        if send_results == CHANNEL_INACTIVE:
                            bad_ones.append(channel_info.channel_id)
                        elif send_results is True:
                            count += 1

                        await asyncio.sleep(delay)  # 10 messages per second (Limit: 30 messages per second)

                if remove_bad_users:
                    await self.remove_users(bad_ones)
            finally:
                self.logger.info(f"{count} messages successful sent (of {len(channels)})")

            return count

    async def register_user(self, chat_id):
        chat_id = str(int(chat_id))
        r = await self.deps.db.get_redis()
        await r.sadd(self.KEY_USERS, chat_id)

    async def remove_users(self, idents):
        idents = [str(int(i)) for i in idents]
        if idents:
            r = await self.deps.db.get_redis()
            await r.srem(self.KEY_USERS, *idents)

    async def all_users(self):
        r = await self.deps.db.get_redis()
        items = await r.smembers(self.KEY_USERS)
        return [int(it) for it in items]
