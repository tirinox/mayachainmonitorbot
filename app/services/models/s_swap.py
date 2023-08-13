from typing import NamedTuple, List

from services.lib.constants import THOR_BLOCK_TIME


class StreamingSwap(NamedTuple):
    # the hash of a transaction
    tx_id: str

    # how often each swap is made, in blocks
    interval: int

    # the total number of swaps in a streaming swaps
    quantity: int

    # the amount of swap attempts so far
    count: int

    # the block height of the latest swap
    last_height: int

    # the total number of tokens the swapper wants to receive of the output asset
    trade_target: int

    # the number of input tokens the swapper has deposited
    deposit: int

    # the amount of input tokens that have been swapped so far
    in_amt: int

    # the amount of output tokens that have been swapped so far
    out_amt: int

    # the list of swap indexes that failed
    failed_swaps: List[int]

    # the list of reasons that sub-swaps have failed
    failed_swap_reasons: List[str]

    @property
    def progress_on_amount(self):
        """
        Swap progress on input amount in %
        @return: float 0.0...100.0
        """
        return 100.0 * self.in_amt / self.deposit if self.deposit else 0.0

    @property
    def progress_on_swap_count(self):
        """
        Swap progress on swap count in % (count/quantity)
        @return: float 0.0...100.0

        @return:
        """
        return 100.0 * self.count / self.quantity if self.quantity else 0.0

    @classmethod
    def from_json(cls, j):
        return cls(
            j.get('tx_id', ''),
            j.get('interval', 0),
            j.get('quantity', 0),
            j.get('count', 1),
            j.get('last_height', 0),
            j.get('trade_target', 0),
            int(j.get('deposit', 0)),
            int(j.get('in', 0)),
            int(j.get('out', 0)),
            j.get('failed_swaps', []),
            j.get('failed_swap_reasons', []),
        )

    @property
    def blocks_to_wait(self):
        return (self.quantity - self.count) * self.interval

    @property
    def second_to_wait(self):
        return self.blocks_to_wait * THOR_BLOCK_TIME

    @property
    def total_duration(self):
        return self.quantity * self.interval * THOR_BLOCK_TIME


class EventStreamingSwapStart(NamedTuple):
    ss: StreamingSwap
    from_address: str
    in_amount: float
    in_asset: str
    out_asset: str
    expected_rate: float
    volume_usd: float
