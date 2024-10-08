from typing import List, NamedTuple


class PoolEarnings(NamedTuple):
    asset_liquidity_fees: float
    earnings: float
    pool: str
    rewards: float
    rune_liquidity_fees: float
    saver_earning: float
    total_liquidity_fees_rune: float

    @classmethod
    def from_json(cls, pool_dict):
        return cls(
            asset_liquidity_fees=float(pool_dict['assetLiquidityFees']),
            earnings=float(pool_dict['earnings']),
            pool=pool_dict['pool'],
            rewards=float(pool_dict['rewards']),
            rune_liquidity_fees=float(pool_dict['runeLiquidityFees']),
            saver_earning=float(pool_dict['saverEarning']),
            total_liquidity_fees_rune=float(pool_dict['totalLiquidityFeesRune'])
        )


class IntervalMeta(NamedTuple):
    avg_node_count: float
    block_rewards: float
    bonding_earnings: float
    cacao_price_usd: float
    earnings: float
    end_time: int
    liquidity_earnings: float
    liquidity_fees: float
    pools: List[PoolEarnings]
    rune_price_usd: float
    start_time: int

    @classmethod
    def from_json(cls, interval_meta_dict):
        pools = [PoolEarnings.from_json(pool) for pool in interval_meta_dict['pools']]
        return cls(
            avg_node_count=float(interval_meta_dict['avgNodeCount']),
            block_rewards=float(interval_meta_dict['blockRewards']),
            bonding_earnings=float(interval_meta_dict['bondingEarnings']),
            cacao_price_usd=float(interval_meta_dict['cacaoPriceUSD']),
            earnings=float(interval_meta_dict['earnings']),
            end_time=int(interval_meta_dict['endTime']),
            liquidity_earnings=float(interval_meta_dict['liquidityEarnings']),
            liquidity_fees=float(interval_meta_dict['liquidityFees']),
            pools=pools,
            rune_price_usd=float(interval_meta_dict['runePriceUSD']),
            start_time=int(interval_meta_dict['startTime'])
        )


class EarningsData(NamedTuple):
    intervals: List[IntervalMeta]
    meta: IntervalMeta

    @classmethod
    def from_json(cls, json_data):
        intervals = [IntervalMeta.from_json(interval) for interval in json_data['intervals']]
        intervals.sort(key=lambda x: x.start_time, reverse=True)
        meta = IntervalMeta.from_json(json_data['meta'])
        return cls(intervals=intervals, meta=meta)

    @property
    def current_week(self):
        return self.intervals[0]

    @property
    def previous_week(self):
        return self.intervals[1]


class EarningsInterval(NamedTuple):
    avg_node_count: float
    block_rewards: int
    bonding_earnings: int
    earnings: int
    end_time: int
    liquidity_earnings: int
    liquidity_fees: int
    pools: List[PoolEarnings]
    rune_price_usd: float
    start_time: int

    @staticmethod
    def from_dict(data: dict) -> 'EarningsInterval':
        return EarningsInterval(
            avg_node_count=float(data['avgNodeCount']),
            block_rewards=int(data['blockRewards']),
            bonding_earnings=int(data['bondingEarnings']),
            earnings=int(data['earnings']),
            end_time=int(data['endTime']),
            liquidity_earnings=int(data['liquidityEarnings']),
            liquidity_fees=int(data['liquidityFees']),
            pools=[PoolEarnings.from_json(pool) for pool in data['pools']],
            rune_price_usd=float(data['runePriceUSD']),
            start_time=int(data['startTime'])
        )


class EarningHistoryResponse(NamedTuple):
    intervals: List[EarningsInterval]
    meta: EarningsInterval

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            intervals=[EarningsInterval.from_dict(interval) for interval in data['intervals']],
            meta=EarningsInterval.from_dict(data['meta'])
        )
