import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from ssl import SSLContext
from types import SimpleNamespace
from typing import Any, Optional, Iterable, Type, Union, List, Dict, Mapping
from urllib.parse import urlparse, urlunparse

import aiohttp
from aiohttp import BaseConnector as BaseConnector, BasicAuth, ClientRequest as ClientRequest, \
    ClientResponse as ClientResponse, ClientWebSocketResponse as ClientWebSocketResponse, HttpVersion, ClientTimeout, \
    TraceConfig, http, Fingerprint as Fingerprint
from aiohttp.abc import AbstractCookieJar
from aiohttp.helpers import sentinel
from aiohttp.typedefs import StrOrURL, LooseCookies, LooseHeaders, JSONEncoder

from services.lib.date_utils import now_ts
from services.lib.lru import LRUCache, WindowAverage
from services.lib.utils import WithLogger

WINDOW_SIZE_TO_AVERAGE = 100
MAX_CACHE_SIZE = 1000


@dataclass
class RequestEntry:
    url: str
    method: str
    total_calls: int = 0
    total_time: float = 0.0
    total_errors: int = 0
    last_timestamp: float = 0.0
    last_timestamp_response: float = 0.0
    response_codes: Dict[int, int] = None
    # none_count: int = 0  # todo
    avg_time: WindowAverage = WindowAverage(WINDOW_SIZE_TO_AVERAGE)
    last_error: Optional[Exception] = None

    def __str__(self):
        return f'{self.method} {self.url}'

    def update_on_start(self, ts_start):
        self.last_timestamp = ts_start
        self.total_calls += 1

    def update_time(self, ts_start):
        time_elapsed = self.last_timestamp_response - ts_start
        self.total_time += time_elapsed
        self.avg_time.append(time_elapsed)

    def update_on_response(self, response: ClientResponse, ts_start):
        if not self.response_codes:
            self.response_codes = defaultdict(int)
        self.response_codes[response.status] += 1
        self.last_timestamp_response = now_ts()

        self.update_time(ts_start)

    def update_on_error(self, e, ts_start):
        self.last_error = e
        self.total_errors += 1
        self.last_timestamp_response = now_ts()

        self.update_time()


class ObservableSession(aiohttp.ClientSession, WithLogger):
    """
    This class is a wrapper around aiohttp.ClientSession that records all requests and responses
    """

    @property
    def debug_cache(self):
        return self._debug_cache

    def debug_top_calls(self, n=10):
        return sorted(self._debug_cache.values(), key=lambda r: r.total_calls, reverse=True)[:n]

    @staticmethod
    def _key_from_url(url: str, method):
        return method + ' ' + urlunparse(urlparse(url)._replace(query=''))

    def _register_start(self, url, method, ts_start):
        try:
            clean_url = self._key_from_url(url, method)

            record = self._debug_cache.get(clean_url)
            if record is None:
                record = RequestEntry(clean_url, method, last_timestamp=ts_start, total_calls=1)
                self._debug_cache[clean_url] = record
            else:
                record: RequestEntry
                record.update_on_start(ts_start)

        except Exception as e:
            self.logger.error(f'Error registering {url}: {e}')

    def _register_end(self, url, method, ts_start, response: ClientResponse):
        try:
            clean_url = self._key_from_url(url, method)

            record = self._debug_cache.get(clean_url)
            if not record:
                self.logger.warning(f'No record for {url} {method}')
                return

            record: RequestEntry
            record.update_on_response(response, ts_start)

        except Exception as e:
            self.logger.error(f'Error registering {url}: {e}')

    def _register_error(self, url, method, ts_start, e):
        try:
            clean_url = self._key_from_url(url, method)

            record = self._debug_cache.get(clean_url)
            if not record:
                self.logger.warning(f'No record for {url} {method}')
                return

            record: RequestEntry
            record.update_on_error(e, ts_start)

        except Exception as e:
            self.logger.error(f'Error registering error in {url}: {e}')

    async def _request(self, method: str, str_or_url: StrOrURL, *, params: Optional[Mapping[str, str]] = None,
                       data: Any = None, json: Any = None, cookies: Optional[LooseCookies] = None,
                       headers: Optional[LooseHeaders] = None, skip_auto_headers: Optional[Iterable[str]] = None,
                       auth: Optional[BasicAuth] = None, allow_redirects: bool = True, max_redirects: int = 10,
                       compress: Optional[str] = None, chunked: Optional[bool] = None, expect100: bool = False,
                       raise_for_status: Optional[bool] = None, read_until_eof: bool = True,
                       proxy: Optional[StrOrURL] = None, proxy_auth: Optional[BasicAuth] = None,
                       timeout: Union[ClientTimeout, object] = sentinel, verify_ssl: Optional[bool] = None,
                       fingerprint: Optional[bytes] = None, ssl_context: Optional[SSLContext] = None,
                       ssl: Optional[Union[SSLContext, bool, Fingerprint]] = None,
                       proxy_headers: Optional[LooseHeaders] = None,
                       trace_request_ctx: Optional[SimpleNamespace] = None,
                       read_bufsize: Optional[int] = None) -> ClientResponse:
        ts_start = now_ts()
        self._register_start(str_or_url, method, ts_start)

        try:
            result = await super()._request(method, str_or_url, params=params, data=data, json=json, cookies=cookies,
                                            headers=headers, skip_auto_headers=skip_auto_headers, auth=auth,
                                            allow_redirects=allow_redirects, max_redirects=max_redirects,
                                            compress=compress,
                                            chunked=chunked, expect100=expect100, raise_for_status=raise_for_status,
                                            read_until_eof=read_until_eof, proxy=proxy, proxy_auth=proxy_auth,
                                            timeout=timeout, verify_ssl=verify_ssl, fingerprint=fingerprint,
                                            ssl_context=ssl_context, ssl=ssl, proxy_headers=proxy_headers,
                                            trace_request_ctx=trace_request_ctx, read_bufsize=read_bufsize)
            self._register_end(str_or_url, method, ts_start, result)
        except Exception as e:
            self._register_error(str_or_url, method, ts_start, e)
            raise e
        return result

    def __init__(self, *, connector: Optional[BaseConnector] = None, loop: Optional[asyncio.AbstractEventLoop] = None,
                 cookies: Optional[LooseCookies] = None, headers: Optional[LooseHeaders] = None,
                 skip_auto_headers: Optional[Iterable[str]] = None, auth: Optional[BasicAuth] = None,
                 json_serialize: JSONEncoder = json.dumps, request_class: Type[ClientRequest] = ClientRequest,
                 response_class: Type[ClientResponse] = ClientResponse,
                 ws_response_class: Type[ClientWebSocketResponse] = ClientWebSocketResponse,
                 version: HttpVersion = http.HttpVersion11, cookie_jar: Optional[AbstractCookieJar] = None,
                 connector_owner: bool = True, raise_for_status: bool = False,
                 read_timeout: Union[float, object] = sentinel, conn_timeout: Optional[float] = None,
                 timeout: Union[object, ClientTimeout] = sentinel, auto_decompress: bool = True,
                 trust_env: bool = False, requote_redirect_url: bool = True,
                 trace_configs: Optional[List[TraceConfig]] = None, read_bufsize: int = 2 ** 16,
                 debug_deque_size=MAX_CACHE_SIZE) -> None:
        super().__init__(connector=connector, loop=loop, cookies=cookies, headers=headers,
                         skip_auto_headers=skip_auto_headers, auth=auth, json_serialize=json_serialize,
                         request_class=request_class, response_class=response_class,
                         ws_response_class=ws_response_class, version=version, cookie_jar=cookie_jar,
                         connector_owner=connector_owner, raise_for_status=raise_for_status, read_timeout=read_timeout,
                         conn_timeout=conn_timeout, timeout=timeout, auto_decompress=auto_decompress,
                         trust_env=trust_env, requote_redirect_url=requote_redirect_url, trace_configs=trace_configs,
                         read_bufsize=read_bufsize)

        self._debug_cache = LRUCache(debug_deque_size)
