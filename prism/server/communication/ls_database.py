#  Copyright (c) 2019-2023 SRI International.
from copy import copy
from dataclasses import dataclass
import heapq
import math
from networkx import shortest_path, Graph
import structlog
import time
import trio
from typing import Dict, List, Optional, Tuple, Set, Callable

from prism.common.message import PrismMessage, TypeEnum
from prism.common.logging import MONITOR_STATUS
from prism.common.config import configuration
from prism.common.tracing import trace_context
from prism.common.util import bytes_hex_abbrv


@dataclass(eq=False, order=False, frozen=True)
class ExpirationElement:
    expiration: float
    originator: bytes

    def __str__(self):
        return f'{bytes_hex_abbrv(self.originator)}: EXP in {self.expiration - time.time():.2f}s'

    def __eq__(self, other):
        # customized equality to use only originator (skip expiration)
        if not isinstance(other, ExpirationElement):
            return False
        return self.originator == other.originator

    def __gt__(self, other):
        # customized comparison to use only expiration (skip originator)
        if not isinstance(other, ExpirationElement):
            raise ValueError(f'Cannot compare {self} to {other}')
        return self.expiration > other.expiration


class LSDatabase:
    def __init__(self, own_lsp: PrismMessage, hops_max: int, epoch: str):
        assert own_lsp
        self.pseudonym = own_lsp.originator
        self.hops_max = hops_max
        self.epoch = epoch

        self._logger = structlog.getLogger(__name__).bind(myself=bytes_hex_abbrv(self.pseudonym), epoch=self.epoch)
        self._monitor_logger = structlog.get_logger(MONITOR_STATUS).bind(
            myself=bytes_hex_abbrv(self.pseudonym),
            epoch=self.epoch,
        )

        # LSP database: { originator -> LSP } where the LSP contains an expiration time
        #  this DB is accessed from different Trio tasks so needs locking
        #  values that expire, need to trigger action(s)
        self.database: Dict[bytes, PrismMessage] = {}
        self.expirations = []  # type: List[ExpirationElement]
        self.timer_scope = None  # type: Optional[trio.CancelScope]
        self.expiration_send_ch, self.expiration_recv_ch = trio.open_memory_channel(0)
        self.routing_table = {}  # type: Dict[str, str]  # pseudonym -> next hop in HEX

        self.previous_nodes = set()
        self.previous_edges = set()
        self.previously_reachable_nodes = set()

        self.main_loop_started = trio.Event()  # to notify when updates can be processed via memory channels
        self.lock = trio.StrictFIFOLock()

        self.trigger_nark: Optional[Callable[[], None]] = None

    def load_state(self, state: dict):
        if "database" not in state:
            return

        self._logger.debug("Loading LSDatabase from saved state")
        database_entries = state["database"]
        self._logger.debug(f"Loading from {len(database_entries)} saved entries")
        for entry in database_entries:
            decoded_entry = PrismMessage.from_b64(entry)
            if not decoded_entry:
                self._logger.warning("Failed to decode saved LSP entry")
                continue

            self.database[decoded_entry.originator] = decoded_entry

        self._logger.debug(f"Loaded {len(self.database)} saved LSP entries")

    async def _timer_task(self, timeout: float, originator: bytes = None, task_status=trio.TASK_STATUS_IGNORED):
        # inspired by: https://stackoverflow.com/a/60675826/3816489
        with trio.CancelScope() as scope:
            task_status.started(scope)
            # self._logger.debug(f'Time for originator={bytes_hex_abbrv(originator)} set to {timeout:.2f}s')
            await trio.sleep(timeout)
            # LSPs which have expired are removed from the LSP database and the removal
            #  triggers the update process.
            #  This should never be our own entry since that gets refreshed every 2/3 * TTL.
            self._logger.warning(f'Timer for originator={bytes_hex_abbrv(originator)} expired - removing!')
            removed = await self.remove_from_db(originator)
            # skip routing update if above removal had already happened
            if removed:
                current_routing_table, has_changed = await self.update_routing_table()
                human_routing_table = {f"{target[:6]} (None)": f"{hop[:6]} (None)"
                                       for target, hop in current_routing_table.items()}
                if has_changed:
                    self._logger.info(f'Current routing table of length={len(current_routing_table)} (_timer_task): ' +
                                      f'{human_routing_table if len(current_routing_table) < 25 else "{...}"}',
                                      size=len(current_routing_table))
                self._monitor_logger.info(f'Current routing table', func_name="_timer_task", table=human_routing_table)

    async def remove_from_db(self, pseudonym: bytes) -> bool:
        async with self.lock:
            removed = self.database.pop(pseudonym, None)
            try:
                self.expirations.remove(ExpirationElement(0, pseudonym))  # equality only cares about originator!
            except ValueError:
                pass  # ignore as the entry is already removed
        if removed and removed.sub_msg and removed.sub_msg.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY:
            # self._logger.info(f"TODO: LS Database to generate NARK for {str(removed.sub_msg)}???")
            pass
        return removed is not None

    async def main_loop(self):
        self._logger.info(f'Link-State Database started')
        async with trio.open_nursery() as nursery:
            # initial timer tasks runs forever until cancelled for the first time that we receive an expiration element:
            timer_scope = await nursery.start(self._timer_task, math.inf)
            self.main_loop_started.set()
            async with self.expiration_recv_ch:
                async for exp_element in self.expiration_recv_ch:
                    timer_scope.cancel()
                    timeout = exp_element.expiration - time.time()
                    # self._logger.debug(f'Re-setting timer for {exp_element}')
                    # if expiration has already happened (timeout < 0) then use 0 to trigger routing table update:
                    timer_scope = await nursery.start(self._timer_task, max(timeout, 0), exp_element.originator)

    async def update_if(self, lsp: PrismMessage, original_digest: str = None) -> Tuple[bool, List[PrismMessage]]:
        """
        Update given originator -> LSP only if:
        1) originator does not yet exist in database, or
        2) originator exists and existing LSP timestamp < lsp.micro_timestamp, or
        3) originator exists and [ existing.micro_timestamp == lsp.micro_timestamp &&
                                   existing.neighbors == lsp.neighbors &&
                                   existing.hop_count == HOPS_MAX &&
                                   lsp.hop_count < HOPS_MAX ]
        Return True if this update was successful, and False otherwise (none of the conditions above hold)
        Also return list with embedded ARK, if this lsp message contained a NEW ARK, otherwise return an empty list
        """
        assert lsp.msg_type == TypeEnum.LSP
        await self.main_loop_started.wait()  # make sure all shared resources are initialized

        originator = lsp.originator
        async with self.lock:
            existing = self.database.get(originator)
            if existing is None or \
                    existing.micro_timestamp < lsp.micro_timestamp or \
                    (existing.micro_timestamp == lsp.micro_timestamp and
                     set([n.pseudonym for n in existing.neighbors]) == set([n.pseudonym for n in lsp.neighbors]) and
                     existing.hop_count == self.hops_max and
                     lsp.hop_count < self.hops_max):
                self.database[originator] = lsp
                # self._logger.debug(f"Updated LS Database for {bytes_hex_abbrv(originator)} -> " +
                #                    f"<sender={bytes_hex_abbrv(lsp.sender)}, neighbors={lsp.neighbors}>",
                #                    prism_disgest_abbrv=original_digest[:8] if original_digest else "None")
                new_arks = []
                if lsp.sub_msg and lsp.sub_msg.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY:
                    new_arks = [lsp.sub_msg]

                new_ee = ExpirationElement(lsp.micro_timestamp/1e6 + lsp.ttl, originator)
                try:
                    if existing:
                        # removes the old expiration (equality is only based on originator)
                        self.expirations.remove(new_ee)
                except ValueError:
                    # This will happen if the existing LSP was preloaded rather than received over the network
                    pass

                self.expirations.append(new_ee)
                heapq.heapify(self.expirations)  # sort by expiration
                await self.expiration_send_ch.send(self.expirations[0])  # sets timer for first expiration
                return True, new_arks
            return False, []

    async def lookup(self, originator: bytes) -> Optional[PrismMessage]:
        assert originator
        async with self.lock:
            return self.database.get(originator, None)

    async def update_routing_table(self) -> Tuple[Dict[str, str], bool]:
        """Return copy of current routing table for display and also whether any strucutural changes in graph."""
        async with self.lock:
            cost_by_directional_edges = {}  # type: Dict[Tuple[str, str], int]
            for source, lsp in self.database.items():
                for neighbor in lsp.neighbors:
                    cost_by_directional_edges[(source.hex(), neighbor.pseudonym.hex())] = neighbor.cost
            graph = Graph()
            bidirectional_edges_processed = set()
            for (src, dst), cost1 in cost_by_directional_edges.items():
                edge = tuple(sorted([src, dst]))
                if edge not in bidirectional_edges_processed:
                    cost2 = cost_by_directional_edges.get((dst, src), None)
                    if cost2 is not None:
                        # both directions exist, so take the larger cost:
                        graph.add_weighted_edges_from([(src, dst, max(cost1, cost2)), (dst, src, max(cost1, cost2))])
                    bidirectional_edges_processed.add(edge)
            # self._logger.debug(f'Running Dijkstra now for {len(graph.nodes)} nodes'),
            #   graph=f'{json.dumps(node_link_data(graph))}')
            # TODO: can we generate a graphviz DOT representation here?

            # compute any differences to previous graph structure (nodes or edges):
            current_nodes = set(graph.nodes())
            new_nodes = current_nodes - self.previous_nodes
            dead_nodes = self.previous_nodes - current_nodes
            if len(new_nodes) or len(dead_nodes):
                with trace_context(self._logger, "updated-LS-nodes",
                                   epoch=self.epoch,
                                   n_current_nodes=len(current_nodes), n_previous_nodes=len(self.previous_nodes)
                                   ) as scope:
                    if len(new_nodes):
                        scope.info(f"New nodes ({len(new_nodes)}) in LS routing graph: " +
                                   f"{sorted([n[:6] for n in new_nodes])}",
                                   n_current_nodes=len(current_nodes), n_previous_nodes=len(self.previous_nodes))
                    if len(dead_nodes):
                        scope.info(f"Dead nodes ({len(dead_nodes)}) in LS routing graph: " +
                                   f"{sorted([n[:6] for n in dead_nodes])}",
                                   n_current_nodes=len(current_nodes), n_previous_nodes=len(self.previous_nodes))
            self.previous_nodes = current_nodes
            current_edges = {tuple(sorted([src, dst])) for src, dst in graph.edges}  # use order to make canonical
            new_edges = current_edges - self.previous_edges
            dead_edges = self.previous_edges - current_edges
            if len(new_edges):
                self._logger.info(f"New edges ({len(new_edges)}) in LS routing graph: " +
                                  f"{sorted([(n1[:6], n2[:6]) for n1, n2 in new_edges])}",
                                  n_current_edges=len(current_edges), n_previous_edges=len(self.previous_edges))
            if len(dead_edges):
                self._logger.info(f"Dead edges ({len(dead_edges)}) in LS routing graph: " +
                                  f"{sorted([(n1[:6], n2[:6]) for n1, n2 in dead_edges])}",
                                  n_current_edges=len(current_edges), n_previous_edges=len(self.previous_edges))
            self.previous_edges = current_edges

            # have we got information about ourselves yet?  if yes, we can proceed with shortest paths calculation
            paths = {}
            if graph.has_node(self.pseudonym.hex()):
                paths = shortest_path(graph, source=self.pseudonym.hex())  # all paths from myself
            else:
                self._logger.warning(f"Haven't added my own LSP to database yet - keeping routing table empty for now!")
            # self._logger.debug(f'Found {len(paths)} paths from myself to others')  #, paths=paths)
            self.routing_table = {target: path[1] for target, path in paths.items()
                                  if len(path) > 1 and target != self.pseudonym.hex()}  # skip myself
            self._monitor_logger.info(f'Updated Link-State Routing table',
                                      ls_db_size=len(self.database), lsp_table_size=len(self.routing_table))

            # compute any difference in reachability
            has_changed = False
            currently_reachable = set(self.routing_table.keys())
            newly_reachable = currently_reachable - self.previously_reachable_nodes
            no_longer_reachable = self.previously_reachable_nodes - currently_reachable
            if len(newly_reachable):
                has_changed = True
                with trace_context(self._logger, "updated-LS-table",
                                   epoch=self.epoch,
                                   ls_db_size=len(self.database), lsp_table_size=len(self.routing_table)) as scope:
                    scope.info(f"Newly reachable nodes ({len(newly_reachable)}) in LS routing graph: " +
                               f"{sorted([n[:6] for n in newly_reachable])}",
                               n_currently_reachable=len(currently_reachable),
                               n_previously_reachable=len(self.previously_reachable_nodes),
                               ls_db_size=len(self.database), lsp_table_size=len(self.routing_table))
            if len(no_longer_reachable):
                has_changed = True
                with trace_context(self._logger, "updated-LS-table",
                                   epoch=self.epoch,
                                   ls_db_size=len(self.database), lsp_table_size=len(self.routing_table)) as scope:
                    scope.info(f"No longer reachable nodes ({len(no_longer_reachable)}) in LS routing graph: " +
                               f"{sorted([n[:6] for n in no_longer_reachable])}",
                               n_currently_reachable=len(currently_reachable),
                               n_previously_reachable=len(self.previously_reachable_nodes),
                               ls_db_size=len(self.database), lsp_table_size=len(self.routing_table))
            self.previously_reachable_nodes = currently_reachable
            if has_changed and configuration.nark_allow_cancel and self.trigger_nark is not None:
                # cancel NARK timers to re-calculate reachability
                self.trigger_nark()

            return copy(self.routing_table), has_changed

    async def reachable_destinations(self) -> Set[str]:
        async with self.lock:
            return set(self.routing_table.keys())

    async def next_hop(self, destination: str) -> Optional[str]:
        assert destination
        async with self.lock:
            return self.routing_table.get(destination)
