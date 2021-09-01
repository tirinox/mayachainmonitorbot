import asyncio

import pytest

from services.lib.cooldown import CooldownBiTrigger
from services.lib.db import DB


@pytest.fixture(scope="function")
def db():
    loop = asyncio.get_event_loop()
    return DB(loop)


@pytest.mark.asyncio
async def test_cd_trigger(db):
    trigger = CooldownBiTrigger(db, 'test_evt', 1.0)
    assert await trigger.turn_on()
    assert not await trigger.turn_on()
    assert await trigger.turn_off()
    assert not await trigger.turn_off()
    print('Wait a sec!')
    await asyncio.sleep(1.1)
    assert await trigger.turn_off()
    print('Wait a sec!')
    await asyncio.sleep(1.1)
    assert await trigger.turn_on()
    print('OK')
