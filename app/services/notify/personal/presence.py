from typing import List

from services.lib.depcont import DepContainer
from services.lib.utils import class_logger
from services.models.node_info import NodeEvent, NodeEventType, NodeSetChanges
from services.notify.personal.helpers import BaseChangeTracker, NodeOpSetting


class PresenceTracker(BaseChangeTracker):
    def __init__(self, deps: DepContainer):
        self.deps = deps
        self.logger = class_logger(self)

    async def get_events(self, node_set_change: NodeSetChanges) -> List[NodeEvent]:
        events = []

        def push_events(node, is_here):
            events.append(NodeEvent(
                node.node_address,
                NodeEventType.PRESENCE,
                data=is_here,
                tracker=self,
                node=node
            ))

        for added_node in node_set_change.nodes_added:
            push_events(added_node, is_here=True)
        for removed_node in node_set_change.nodes_removed:
            push_events(removed_node, is_here=False)

        return events

    async def is_event_ok(self, event: NodeEvent, user_id, settings: dict) -> bool:
        if not bool(settings.get(NodeOpSetting.NODE_PRESENCE, True)):
            return False

        return True