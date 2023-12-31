import asyncio
import json
import struct
from typing import Optional, List, Iterable, Dict, NamedTuple

from proto.types import ThorName, ThorNameAlias
from services.lib.config import Config
from services.lib.constants import Chains
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.db import DB
from services.lib.midgard.connector import MidgardConnector
from services.lib.utils import WithLogger, keys_to_lower, filter_none_values


class NameMap(NamedTuple):
    by_name: Dict[str, ThorName]
    by_address: Dict[str, ThorName]

    @classmethod
    def empty(cls):
        return cls({}, {})

    def joined_with(self, other: 'NameMap'):
        return NameMap(
            {**self.by_name, **other.by_name},
            {**self.by_address, **other.by_address}
        )


# ThorName: address[owner] -> many of [name] -> many of [address (thor + chains)]
# Here we basically don't care about owners of ThorNames.
# We must have API for Address -> ThorName, and ThorName -> [Address] resolution
class NameService(WithLogger):
    def __init__(self, db: DB, cfg: Config, midgard: MidgardConnector):
        super().__init__()
        self.db = db
        self.cfg = cfg

        self._api = THORNameAPIClient(midgard)
        self._cache = THORNameCache(db, cfg)

        self._thorname_enabled = cfg.as_str('names.thorname.enabled', True)
        self._thorname_expire = int(parse_timespan_to_seconds(cfg.as_str('names.thorname.expire', '24h'))) or None

        if self._thorname_enabled:
            self.logger.info(f'ThorName is enabled with expire time of {self._thorname_expire} sec.')

    def get_affiliate_name(self, affiliate_short):
        return self._cache.get_affiliate_name(affiliate_short)

    async def safely_load_thornames_from_address_set(self, addresses: Iterable) -> NameMap:
        try:
            addresses = list(set(addresses))  # make it unique and strictly ordered

            thorname_by_address = await self.lookup_multiple_names_by_addresses(addresses)
            thorname_by_address = filter_none_values(thorname_by_address)

            thorname_by_name = {}
            for address, thorname in thorname_by_address.items():
                if thorname and thorname != self._cache.NO_VALUE:
                    for alias in thorname.aliases:
                        if alias.address == address:
                            thorname_by_name[thorname.name] = thorname
                            break

            return NameMap(thorname_by_name, thorname_by_address)
        except Exception as e:
            self.logger.exception(f'Something went wrong. That is OK. {e!r}', exc_info=True)
            return NameMap.empty()

    async def lookup_name_by_address(self, address: str) -> Optional[ThorName]:
        if not address:
            return

        local_results = self._cache.lookup_name_by_address_local(address)
        if local_results:
            return local_results

        if not self._thorname_enabled:
            return

        names = await self._cache.load_name_list(address)
        if names is None:
            names = await self._api.thorname_reversed_lookup(address)
            await self._cache.save_name_list(address, names)

        if not names:
            return

        # todo: find a ThorName locally or pick any of this list
        name = names[0]
        if len(names) > 1:
            self.logger.warning(f'Address {address} resolves to more than 1 ThorNames: "{names}". '
                                f'I will take the first one "{name}"')

        return await self.lookup_thorname_by_name(name)

    async def lookup_multiple_names_by_addresses(self, addresses: Iterable) -> Dict[str, ThorName]:
        if not addresses:
            return {}

        thor_names = await asyncio.gather(
            *[self.lookup_name_by_address(address) for address in addresses]
        )
        entries = [(address, thor_name) for address, thor_name in zip(addresses, thor_names)]
        return dict(entries)

    async def lookup_thorname_by_name(self, name: str, forced=False) -> Optional[ThorName]:
        name = name.strip()

        if known_name := self._cache.lookup_name_by_address_local(name):
            return known_name

        if not self._thorname_enabled:
            return

        if forced or not (thorname := await self._cache.load_thor_name(name)):
            thorname = await self._api.thorname_lookup(name)
            await self._cache.save_thor_name(name, thorname)  # save anyway, even if there is not ThorName!

            if forced and thorname:
                await self._cache.save_name_list(self.get_thor_address_of_thorname(thorname), [thorname.name])

        return thorname

    @staticmethod
    def get_thor_address_of_thorname(thor: ThorName) -> Optional[str]:
        if thor:
            try:
                return next(alias.address for alias in thor.aliases if alias.chain == Chains.MAYA)
            except StopIteration:
                pass

    def get_local_service(self, user_id):
        return LocalWalletNameDB(self.db, user_id)


class THORNameCache:
    def __init__(self, db: DB, cfg: Config):
        self.db = db
        self.cfg = cfg

        self._known_address = {}
        self._known_names = {}
        self._affiliates = {}

        self.thorname_expire = int(parse_timespan_to_seconds(cfg.as_str('names.thorname.expire', '24h'))) or None

        self._load_preconfigured_names()

    def lookup_name_by_address_local(self, address: str) -> Optional[ThorName]:
        return self._known_address.get(address)

    def _load_preconfigured_names(self):
        name_dic: dict = self.cfg.get_pure('names.preconfig', {})
        for address, label in name_dic.items():
            if address and label:
                self._known_address[address] = ThorName(
                    label, 0, address.encode(),
                    aliases=[
                        ThorNameAlias(Chains.detect_chain(address), address)
                    ]
                )
                self._known_names[label] = address

        self.affiliates = keys_to_lower(self.cfg.get_pure('names.affiliates'))

    def get_affiliate_name(self, affiliate_short: str):
        return self.affiliates.get(affiliate_short.lower())

    @staticmethod
    def _key_thorname_to_addresses(name: str):
        return f'THORName:Entries:{name}'

    @staticmethod
    def _key_address_to_names(address: str):
        return f'THORName:Address-to-Names:{address}'

    async def save_name_list(self, address: str, names: List[str]):
        await self.db.redis.set(self._key_address_to_names(address),
                                value=json.dumps(names),
                                ex=self.thorname_expire)

    async def load_name_list(self, address: str) -> List[str]:
        data = await self.db.redis.get(self._key_address_to_names(address))
        return json.loads(data) if data else None

    NO_VALUE = 'no_value'

    async def save_thor_name(self, name, thorname: ThorName):
        if not name:
            return

        value = thorname.to_json() if thorname else self.NO_VALUE
        await self.db.redis.set(
            self._key_thorname_to_addresses(name),
            value=value,
            ex=self.thorname_expire
        )

    async def load_thor_name(self, name: str) -> Optional[ThorName]:
        if not name:
            return

        data = await self.db.redis.get(self._key_thorname_to_addresses(name))
        if not data:
            return

        try:
            if data == self.NO_VALUE:
                return data
            else:
                return ThorName().from_json(data)
        except (TypeError, struct.error):
            return

    async def clear_cache_for_name(self, name: str):
        await self.db.redis.delete(self._key_thorname_to_addresses(name))

    async def clear_cache_for_address(self, address: str):
        await self.db.redis.delete(self._key_address_to_names(address))


class THORNameAPIClient:
    def __init__(self, midgard: MidgardConnector):
        self.midgard = midgard

    def _empty_if_error_or_not_found(self, results):
        if results is None or results == self.midgard.ERROR_RESPONSE or results == self.midgard.ERROR_NOT_FOUND:
            return None
        else:
            return results

    async def thorname_lookup(self, name: str) -> Optional[ThorName]:
        """
        Returns an array of chains and their addresses associated with the given ThorName
        """
        results = await self.midgard.request(f'/v2/thorname/lookup/{name}')
        results = self._empty_if_error_or_not_found(results)
        if results:
            return ThorName(
                name=name,
                expire_block_height=int(results['expire']),
                owner=results['owner'].encode(),
                aliases=[
                    ThorNameAlias(alias['chain'], alias['address']) for alias in results['entries']
                ]
            )

    async def thorname_reversed_lookup(self, address: str) -> List[str]:
        """
        Returns an array of ThorNames associated with the given address
        """
        results = await self.midgard.request(f'/v2/thorname/rlookup/{address}')
        results = self._empty_if_error_or_not_found(results)
        return results or []

    async def get_thornames_owned_by_address(self, thor_address: str):
        """
        Returns an array of ThorNames owned by the address.
        The address is not necessarily an associated address for those thornames.
        """
        results = await self.midgard.request(f'/v2/thorname/owner/{thor_address}')
        results = self._empty_if_error_or_not_found(results)
        return results or []


class LocalWalletNameDB:
    def __init__(self, db: DB, user_id):
        self.db = db
        self.user_id = user_id

    @property
    def db_key(self):
        return f'THORName:Local:{self.user_id}'

    async def get_wallet_local_name(self, address: str) -> Optional[str]:
        if not address or not self.user_id:
            return
        return await self.db.redis.hget(self.db_key, address)

    async def delete_wallet_local_name(self, address: str):
        if not address or not self.user_id:
            return
        await self.db.redis.hdel(self.db_key, address)

    async def set_wallet_local_name(self, address: str, wallet_name: str):
        if not address or not self.user_id:
            return
        return await self.db.redis.hset(self.db_key, address, wallet_name)

    async def get_all_for_user(self):
        return await self.db.redis.hgetall(self.db_key)

    async def get_name_map(self) -> Optional[NameMap]:
        all_names = await self.get_all_for_user()
        if not all_names:
            return NameMap.empty()

        by_name, by_address = {}, {}
        for address, name in all_names.items():
            thor_name = ThorName(
                name=name,
                expire_block_height=0,
                owner=address,
                aliases=[
                    # chain is unknown here
                    ThorNameAlias(Chains.MAYA, address)
                ]
            )
            by_name[name] = thor_name
            by_address[address] = thor_name

        return NameMap(by_name, by_address)


def add_thor_suffix(thor_name: ThorName):
    if thor_name.expire_block_height:
        # Registered
        return f'{thor_name.name}.thor'
    else:
        # Configured
        return thor_name.name
