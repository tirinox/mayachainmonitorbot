import asyncio
import logging
import random
from copy import copy

from semver import VersionInfo

from localization import LocalizationManager
from services.jobs.fetch.node_info import NodeInfoFetcher
from services.lib.utils import setup_logs, sep
from services.models.node_info import NodeSetChanges, NodeVersionConsensus
from tools.lib.lp_common import LpAppFramework


def localizations(lpgen: LpAppFramework):
    loc_man: LocalizationManager = lpgen.deps.loc_man

    locs = (
        loc_man.get_from_lang('eng'),
        loc_man.get_from_lang('rus'),
    )
    return locs

async def node_version_notification_check_progress(lpgen: LpAppFramework, data: NodeSetChanges):
    locs = localizations(lpgen)

    await lpgen.send_test_tg_message('------------------------------------')

    new_ver = '0.60.1'
    n_new = 0
    progress = 0.1  # 0..1
    for n in data.nodes_all:
        if random.uniform(0, 1) <= progress:
            n.version = new_ver
            n_new += 1

    ver_con = NodeVersionConsensus(
        n_new / len(data.active_only_nodes),
        VersionInfo.parse(new_ver),
        n_new,
        len(data.active_only_nodes)
    )

    for loc in locs:
        sep()
        msg = loc.notification_text_version_upgrade_progress(data, ver_con)
        print(msg)
        await lpgen.send_test_tg_message(msg)


async def node_version_notification_check_1(lpgen: LpAppFramework, data):
    locs = localizations(lpgen)

    await lpgen.send_test_tg_message('------------------------------------')

    for loc in locs:
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[
                VersionInfo.parse('0.59.1'),
                VersionInfo.parse('0.60.0'),
            ],
            old_active_ver=None,
            new_active_ver=None
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)

    await lpgen.send_test_tg_message('------------------------------------')

    for loc in locs:
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[],
            old_active_ver=VersionInfo.parse('0.59.0'),
            new_active_ver=VersionInfo.parse('0.59.1')
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)

    await lpgen.send_test_tg_message('------------------------------------')

    data: NodeSetChanges = copy(data)
    for n in data.nodes_all:
        if random.uniform(0, 1) > 0.35:
            n.version = '0.59.2'
        if random.uniform(0, 1) > 0.25:
            n.version = '0.60.0'
        if random.uniform(0, 1) > 0.20:
            n.version = '0.60.1'
        if random.uniform(0, 1) > 0.15:
            n.version = '0.60.3'

    for loc in locs:
        sep()
        msg = loc.notification_text_version_upgrade(
            data,
            new_versions=[],
            old_active_ver=VersionInfo.parse('0.59.1'),
            new_active_ver=VersionInfo.parse('0.59.0')
        )
        print(msg)
        await lpgen.send_test_tg_message(msg)


async def main():
    lpgen = LpAppFramework()
    async with lpgen:
        node_info_fetcher = NodeInfoFetcher(lpgen.deps)

        data = await node_info_fetcher.fetch()

        await node_version_notification_check_1(lpgen, data)
        # await node_version_notification_check_progress(lpgen, data)


if __name__ == "__main__":
    setup_logs(logging.INFO)
    asyncio.run(main())
