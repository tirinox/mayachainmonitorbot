from typing import Optional

import aiohttp
from aionode.connector import ThorConnector
from aionode.nodeclient import ThorNodeClient

from services.lib.constants import HTTP_CLIENT_ID
from services.lib.midgard.parser import MidgardParserV2, TxParseResult
from services.lib.midgard.urlgen import free_url_gen
from services.lib.utils import WithLogger
from services.models.earnings_history import EarningHistoryResponse
from services.models.savers import MidgardSaversHistory
from services.models.swap_history import SwapHistoryResponse

DEFAULT_MIDGARD_PORT = 8080


class MidgardConnector(WithLogger):
    ERROR_RESPONSE = 'ERROR_Midgard'
    ERROR_NOT_FOUND = 'NotFound_Midgard'
    ERROR_NO_CLIENT = 'ERROR_NoClient'

    def __init__(self, session: aiohttp.ClientSession, thor: ThorConnector, retry_number=3, public_url='',
                 network_id=None):
        super().__init__()

        self.thor = thor
        self.public_url = public_url.rstrip('/')
        self.session = session
        self.retries = retry_number
        self.session = session or aiohttp.ClientSession()
        self.urlgen = free_url_gen
        self.parser = MidgardParserV2(network_id)

    async def _request_json_from_midgard_by_ip(self, ip_address: str, path: str):
        path = path.lstrip('/')

        if ip_address == self.public_url:
            full_url = f'{self.public_url}/{path}'
        else:
            port = DEFAULT_MIDGARD_PORT
            full_url = f'http://{ip_address}:{port}/{path}'

        self.logger.info(f"Getting Midgard endpoint: {full_url}")
        try:
            headers = {ThorNodeClient.HEADER_CLIENT_ID: HTTP_CLIENT_ID}
            async with self.session.get(full_url, headers=headers) as resp:
                self.logger.debug(f'Midgard "{full_url}"; result code = {resp.status}.')

                if resp.status == 404:
                    return self.ERROR_NOT_FOUND
                elif resp.status != 200:
                    try:
                        answer = resp.content[:200]
                    except TypeError:
                        answer = 'unknown'
                    self.logger.warning(f'Midgard ({full_url}) BAD response {resp.status = }, "{answer}"!')
                    return self.ERROR_RESPONSE
                j = await resp.json()
                return j
        except Exception as e:
            self.logger.error(f'Midgard ({ip_address}/{path}) exception: {e!r}.')
            return self.ERROR_RESPONSE

    async def request(self, path: str):
        result = await self._request_json_from_midgard_by_ip(self.public_url, path)
        if isinstance(result, str) and result != self.ERROR_NOT_FOUND:
            self.logger.error(f'Probably there is an issue. Midgard has returned a plain string: {result!r} '
                              f'for the path {path!r}')
        else:
            return result

    async def query_earnings(self, from_ts=0, to_ts=0, count=0, interval='') -> Optional[EarningHistoryResponse]:
        url = self.urlgen.url_for_earnings_history(from_ts, to_ts, count, interval)
        j = await self.request(url)
        if j:
            return EarningHistoryResponse.from_json(j)

    async def query_swap_stats(self, from_ts=0, to_ts=0, count=10, interval='day') -> Optional[SwapHistoryResponse]:
        url = self.urlgen.url_for_swap_history(from_ts, to_ts, count, interval)
        j = await self.request(url)
        if j:
            return SwapHistoryResponse.from_json(j)

    async def query_transactions(self, url_for_tx) -> TxParseResult:
        j = await self.request(url_for_tx)
        if j:
            return self.parser.parse_tx_response(j)

    async def query_savers_history(self, pool, from_ts=0, to_ts=0, count=10, interval='day') \
            -> Optional[MidgardSaversHistory]:
        url = self.urlgen.url_for_savers_history(pool, from_ts, to_ts, count, interval)
        j = await self.request(url)
        if j:
            return MidgardSaversHistory.from_json(j)
