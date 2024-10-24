import asyncio
import logging
import pickle

from localization.languages import Language
from services.dialog.picture.key_stats_picture import KeyStatsPictureGenerator
from services.jobs.fetch.key_stats import KeyStatsFetcher
from services.lib.delegates import INotified
from services.lib.texts import sep
from services.notify.types.key_metrics_notify import KeyMetricsNotifier
from tools.lib.lp_common import LpAppFramework, save_and_show_pic


async def demo_load(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    r = await f._load_dividends()
    # r = await f._load_earnings_history()
    # r = await f._load_lock_stats()
    # r = await f.fetch()
    print(r)
    print(f'{r.current_week_cacao_sum = }')
    print(f'{r.previous_week_cacao_sum = }')


class FlipSideSaver(INotified):
    DEFAULT_FILENAME = '../temp/key_metrics_v5.pickle'

    def __init__(self, filename=DEFAULT_FILENAME) -> None:
        super().__init__()
        self.filename = filename

    def clear_data(self):
        try:
            import os
            os.remove(self.filename)
        except Exception:
            print(f'Failed to remove {self.filename}')

    async def on_data(self, sender, data):
        # result, fresh_pools, old_pools = data
        with open(self.filename, 'wb') as f:
            pickle.dump(data, f)
            print(f'DATA SAVED to {self.filename}')

    def load_data(self):
        try:
            with open(self.filename, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass


async def demo_analyse(app: LpAppFramework):
    f = KeyStatsFetcher(app.deps)
    noter = KeyMetricsNotifier(app.deps)
    f.add_subscriber(noter)
    noter.add_subscriber(app.deps.alert_presenter)

    saver = FlipSideSaver()
    f.add_subscriber(saver)

    await f.run_once()


async def demo_picture(app: LpAppFramework, cached=True):
    sep()
    print('Start')

    loader = FlipSideSaver()

    if not cached:
        loader.clear_data()

    data = loader.load_data()
    if not data:
        await demo_analyse(app)
        data = loader.load_data()

    sep()
    print('Data loaded')

    # loc = app.deps.loc_man.default
    loc = app.deps.loc_man[Language.ENGLISH]

    sep('DATA')
    print(data)
    sep()

    pic_gen = KeyStatsPictureGenerator(loc, data)
    pic, name = await pic_gen.get_picture()
    save_and_show_pic(pic, name=name)


async def main():
    lp_app = LpAppFramework(log_level=logging.INFO)
    async with lp_app(brief=True):
        # await lp_app.prepare(brief=True)
        await lp_app.deps.last_block_fetcher.run_once()

        # await demo_analyse(lp_app)
        await demo_picture(lp_app, cached=False)
        # await demo_load(lp_app)


if __name__ == '__main__':
    asyncio.run(main())
