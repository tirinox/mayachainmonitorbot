from contextlib import suppress

from services.lib.constants import thor_to_float
from services.lib.delegates import INotified, WithDelegates
from services.lib.utils import WithLogger
from services.models.tx import ThorTx


class StreamingSwapVsCexProfitCalculator(WithLogger, WithDelegates, INotified):
    def __init__(self, deps):
        super().__init__()
        self.deps = deps

    @staticmethod
    def url_cex(from_asset: str, to_asset: str, amount: float):
        from_asset = from_asset.split('.')[1] if '.' in from_asset else from_asset
        to_asset = to_asset.split('.')[1] if '.' in to_asset else to_asset
        return (
            f"https://api.criptointercambio.com/amount/exchange/full?"
            f"from={from_asset}&"
            f"to={to_asset}&"
            f"amount={amount}"
        )

    async def get_cex_data(self, tx: ThorTx):
        """
        Get CEX output at the moment!
        @param tx:
        @return:
        """
        asset_in = tx.first_input_tx.first_asset
        asset_out = tx.first_output_tx.first_asset
        if not asset_in or not asset_out:
            return

        url = self.url_cex(asset_in, asset_out, thor_to_float(tx.first_input_tx.first_amount))
        async with self.deps.session.get(url) as resp:
            data = await resp.json()
            data = data['fullExchangeAmount']

            tx.meta_swap.cex_out_amount = float(data['result'])
            tx.meta_swap.cex_rate = float(data['rate'])

            tx.meta_swap.streaming.estimated_savings_vs_cex_usd = tx.get_profit_vs_cex_in_usd(self.deps.price_holder)

            # print(f'🎉 {tx.meta_swap.cex_out_amount=}, {tx.meta_swap.cex_rate=}')

    async def on_data(self, sender, data):
        try:
            for tx in data:
                tx: ThorTx
                if tx.is_streaming:
                    await self.get_cex_data(tx)
        except Exception as e:
            self.logger.error(f'{e!r}. Skipping this TX')

            with suppress(Exception):
                self.deps.emergency.report('ProfitVsCEX', txs=', '.join([tx.tx_hash for tx in data]))

        await self.pass_data_to_listeners(data)