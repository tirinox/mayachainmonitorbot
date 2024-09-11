import asyncio
import random
from typing import List, NamedTuple

from aionode.types import ThorConstants, ThorMimir, ThorMimirVote
from services.jobs.fetch.base import BaseFetcher
from services.lib.date_utils import parse_timespan_to_seconds
from services.lib.depcont import DepContainer


class MimirTuple(NamedTuple):
    constants: ThorConstants
    mimir: ThorMimir
    node_mimir: dict
    votes: List[ThorMimirVote]


class ConstMimirFetcher(BaseFetcher):
    ATTEMPTS = 5

    def __init__(self, deps: DepContainer):
        sleep_period = parse_timespan_to_seconds(deps.cfg.constants.fetch_period)
        super().__init__(deps, sleep_period)
        self.step_sleep = deps.cfg.sleep_step
        self._dbg_new_votes = []

    async def fetch(self) -> MimirTuple:
        thor = self.deps.thor_connector

        # step by step
        constants = await thor.query_constants()
        await asyncio.sleep(self.step_sleep)

        mimir = await thor.query_mimir()
        await asyncio.sleep(self.step_sleep)

        node_mimir = await thor.query_mimir_node_accepted()
        await asyncio.sleep(self.step_sleep)

        votes = await thor.query_mimir_votes()

        # # fixme ------------------------------------
        # # DEBUG: add some votes
        # self._dbg_new_votes.append(
        #     # ACCEPT_RADIX
        #     ThorMimirVote('ACCEPT_RADIX', random.randint(3, 333), singer=
        #                   random.choice(
        #                       [
        #                           'maya1a9yx064qcjn8en4eal5sqragshtqdq0dj6maya',
        #                           'maya1gsj57czxvxmgkxsd9vc7qe9k9rvupr3sp0rllq',
        #                           'maya1m9l2fuezgfpa6vyt2x62jpuj6y6dyhwqwjlm9l',
        #                           'maya1rw0u9q4p4a9kaellp7m2x2rsu4teqm475cdash',
        #                       ]
        #                   ))
        # )
        # votes += self._dbg_new_votes
        # # fixme ------------------------------------

        await asyncio.sleep(self.step_sleep)

        votes: List[ThorMimirVote]
        node_mimir: dict

        if not constants or not mimir or node_mimir is None or votes is None:
            raise FileNotFoundError('failed to get Mimir data from THORNode')

        self.deps.mimir_const_holder.update(
            constants, mimir, node_mimir, votes,
            self.deps.node_holder.active_nodes
        )

        self.logger.info(f'Got {len(constants.constants)} CONST'
                         f', {len(mimir.constants)} MIMIR'
                         f', {len(votes)} votes'
                         f' and {len(node_mimir)} accepted node mimirs.')
        return MimirTuple(constants, mimir, node_mimir, votes)
