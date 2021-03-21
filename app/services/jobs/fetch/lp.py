import asyncio
import datetime
import logging

from services.jobs.midgard import get_midgard_url
from services.jobs.fetch.pool_price import PoolPriceFetcher
from services.lib.depcont import DepContainer
from services.models.stake_info import CurrentLiquidity, StakePoolReport, StakeDayGraphPoint


# https://mctn.vercel.app/dashboard?thor=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e  multi-chain
# FEES:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/fee?address=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e|tb1qsasla0n6rjgwr6s4pa8jrqmvzzr0vfugulyyf0&pool=BTC.BTC
# thor address vs on-chain address:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/pooladdress?address=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e
# POOL list of address:
# https://multichain-asgard-consumer-api.vercel.app/api/v2/member/poollist?address=tthor1zzwlsaq84sxuyn8zt3fz5vredaycvgm7n8gs6e&isDev
# Midgard pool info https://testnet.midgard.thorchain.info/v2/pool/BTC.BTC


class LiqPoolFetcher:
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = logging.getLogger('LiqPoolFetcher')

    def url_midgard_my_pools(self, address):
        return get_midgard_url(self.deps.cfg, f"/stakers/{address}")

    # fixme: Multi-chain
    @staticmethod
    def url_asgard_consumer_weekly_history(address, pool):
        return f'https://asgard-consumer.vercel.app/api/weekly?address={address}&pool={pool}'

    # fixme: Multi-chain
    @staticmethod
    def url_asgard_consumer_liquidity(address, pool):
        return f'https://asgard-consumer.vercel.app/api/v2/history/liquidity?address={address}&pools={pool}'

    async def get_my_pools(self, address):
        url = self.url_midgard_my_pools(address)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                my_pools = j['poolsArray']
                return my_pools
            except KeyError:
                return None

    async def fetch_one_pool_liquidity_info(self, address, pool):
        url = self.url_asgard_consumer_liquidity(address, pool)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            return CurrentLiquidity.from_asgard(j)

    async def fetch_one_pool_weekly_chart(self, address, pool):
        url = self.url_asgard_consumer_weekly_history(address, pool)
        self.logger.info(f'get {url}')
        async with self.deps.session.get(url) as resp:
            j = await resp.json()
            try:
                return pool, [StakeDayGraphPoint.from_asgard(point) for point in j['data']]
            except TypeError:
                self.logger.warning(f'no weekly chart for {pool} @ {address}')
                return pool, None

    async def fetch_all_pools_weekly_charts(self, address, pools):
        weekly_charts = await asyncio.gather(*[self.fetch_one_pool_weekly_chart(address, pool) for pool in pools])
        return dict(weekly_charts)

    async def fetch_all_pool_liquidity_info(self, address, my_pools=None) -> dict:
        my_pools = (await self.get_my_pools(address)) if my_pools is None else my_pools
        cur_liquidity = await asyncio.gather(*(self.fetch_one_pool_liquidity_info(address, pool) for pool in my_pools))
        return {c.pool: c for c in cur_liquidity}

    async def fetch_stake_report_for_pool(self, liq: CurrentLiquidity, ppf: PoolPriceFetcher) -> StakePoolReport:
        try:
            first_stake_dt = datetime.datetime.utcfromtimestamp(liq.first_stake_ts)
            # get prices at the moment of first stake
            usd_per_rune_start, usd_per_asset_start = await ppf.get_usd_price_of_rune_and_asset_by_day(
                liq.pool,
                first_stake_dt.date())
        except Exception as e:
            self.logger.exception(e, exc_info=True)
            usd_per_rune_start, usd_per_asset_start = None, None

        d = self.deps
        stake_report = StakePoolReport(d.price_holder.usd_per_asset(liq.pool),
                                       d.price_holder.usd_per_rune,
                                       usd_per_asset_start, usd_per_rune_start,
                                       liq,
                                       d.price_holder.pool_info_map.get(liq.pool))
        return stake_report