import asyncio

from services.dialog.telegram.telegram import TG_TEST_USER
from tools.lib.lp_common import LpAppFramework


async def main():
    app = LpAppFramework()
    async with app(brief=True):
        stickers = app.deps.cfg.price.ath.stickers.contents
        print(stickers)

        n = len(stickers)
        n_unique = len(set(stickers))
        print(f'Unique: {n_unique}/{n}')

        for sticker in stickers:
            await app.deps.telegram_bot.bot.send_message(
                TG_TEST_USER,
                f"--------------------------\n"
                f"Sticker:\n"
                f"<code>{sticker}</code>"
                f"👇"
            )
            await app.deps.telegram_bot.bot.send_sticker(
                TG_TEST_USER, sticker
            )
            await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())