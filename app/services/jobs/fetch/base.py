import asyncio
import datetime
import os
import random
from abc import ABC, abstractmethod
from typing import Dict

from services.lib.date_utils import now_ts
from services.lib.delegates import WithDelegates
from services.lib.depcont import DepContainer
from services.lib.utils import WithLogger


class WatchedEntity:
    def __init__(self):
        super().__init__()
        self.name = self.__class__.__qualname__
        self.sleep_period = 1.0
        self.initial_sleep = 1.0
        self.last_timestamp = 0.0
        self.error_counter = 0
        self.total_ticks = 0
        self.creating_date = now_ts()

    @property
    def success_rate(self):
        if not self.total_ticks:
            return 100.0
        return (self.total_ticks - self.error_counter) / self.total_ticks * 100.0


class DataController:
    def __init__(self):
        self._tracker = {}

    def register(self, entity: WatchedEntity):
        if not entity:
            return
        name = entity.name
        self._tracker[name] = entity

    def unregister(self, entity):
        if not entity:
            return
        self._tracker.pop(entity.name)

    @property
    def summary(self) -> Dict[str, WatchedEntity]:
        return self._tracker

    def make_graph(self):
        results = set()

        queue = set(self._tracker.values())
        while queue:
            node = queue.pop()
            emitter_name = node.__class__.__qualname__
            if isinstance(node, WithDelegates):
                for listener in node.delegates:
                    listener_name = listener.__class__.__qualname__
                    results.add((emitter_name, listener_name))
                    queue.add(listener)

        return results

    @staticmethod
    def make_digraph_dot(list_of_connections):
        dot_code = "digraph G {\n"

        for edge in list_of_connections:
            node_from, node_to = edge
            dot_code += f'    "{node_from}" -> "{node_to}";\n'

        dot_code += "}"
        return dot_code

    def save_dot_graph(self, filename):
        with open(filename, 'w') as f:
            connections = self.make_graph()
            dot_code = self.make_digraph_dot(connections)
            f.write(dot_code)

    def display_graph(self):
        filename = '../temp/graph.dot'
        self.save_dot_graph(filename)

        out_filename = filename + '.png'
        os.system(f'dot -Tpng "{filename}" -O "{out_filename}"')
        os.system(f'open "{out_filename}"')


class BaseFetcher(WithDelegates, WatchedEntity, ABC, WithLogger):
    MAX_STARTUP_DELAY = 60

    def __init__(self, deps: DepContainer, sleep_period=60):
        super().__init__()
        self.deps = deps

        self.sleep_period = sleep_period
        self.initial_sleep = random.uniform(0, min(self.MAX_STARTUP_DELAY, sleep_period))
        self.data_controller.register(self)

    @property
    def data_controller(self):
        if not self.deps.data_controller:
            self.deps.data_controller = DataController()
        return self.deps.data_controller

    async def post_action(self, data):
        ...

    @abstractmethod
    async def fetch(self):
        ...

    async def run_once(self):
        try:
            data = await self.fetch()
            await self.pass_data_to_listeners(data)
            await self.post_action(data)
        except Exception as e:
            self.logger.exception(f"task error: {e}")
            self.error_counter += 1
            try:
                await self.handle_error(e)
            except Exception as e:
                self.logger.exception(f"task error while handling on_error: {e}")
        finally:
            self.total_ticks += 1
            self.last_timestamp = datetime.datetime.now().timestamp()

    async def run(self):
        if self.sleep_period < 0:
            self.logger.info('This fetcher is disabled.')
            return

        self.logger.info(f'Waiting {self.initial_sleep:.1f} sec before starting this fetcher...')
        await asyncio.sleep(self.initial_sleep)
        self.logger.info(f'Starting this fetcher with period {self.sleep_period:.1f} sec.')

        while True:
            await self.run_once()
            await asyncio.sleep(self.sleep_period)
