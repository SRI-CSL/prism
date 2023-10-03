#  Copyright (c) 2019-2023 SRI International.
from __future__ import annotations
import math
from abc import ABCMeta
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, Callable, Awaitable, Optional, Union

import structlog
import trio
from jaeger_client import SpanContext

from prism.common.config import configuration
from prism.common.crypto.halfkey import PrivateKey
from prism.common.crypto.halfkey.rsa import RSAPrivateKey
from prism.common.crypto.server_message import decrypt
from prism.common.logging import MONITOR_STATUS
from prism.common.message import PrismMessage
from prism.common.state import StateStore
from prism.common.tracing import trace_context
from prism.common.transport.hooks import MessageTypeHook
from prism.common.transport.transport import Transport
from prism.common.util import bytes_hex_abbrv
from prism.server.communication.ls_routing import LSRouting
from ...communication.flooding import Flooding
from prism.server.server_data import ServerData
from ...pki import RoleKeyMaterial

# see: https://blog.yuo.be/2018/08/16/__init_subclass__-a-simpler-way-to-implement-class-registries-in-python/
# for role registry implementation; note that registered (= non-abstract) subclasses in other modules need to be
# imported in __init__.py for this to work

_role_registry: Dict[str, type] = {}


class AbstractRole(metaclass=ABCMeta):
    _role: str

    def __init__(
            self,
            transport: Transport,
            state_store: StateStore,
            sd: ServerData,
            role_keys: RoleKeyMaterial,
            previous_role: Optional[AbstractRole] = None,
            **kwargs
    ):
        self._transport = transport
        self._state_store = state_store
        assert sd
        self._server_data = sd
        self._key_material = role_keys
        self.previous_role = previous_role

        # messages should not be routed through dropbox or client_reg servers
        if self.server_data.role_name.startswith("DROPBOX") or self.server_data.role_name.startswith("CLIENT"):
            lsp_cost = 100
        else:
            lsp_cost = 1

        # only AnnouncingRoles that actually start the ARK update loop participate in Link-State Routing Protocol,
        # but we also use this to maintain pseudonym -> address translation so elevating it here.
        self.ls_routing = LSRouting(self.server_data,
                                    own_cost=lsp_cost,
                                    transport=self._transport,
                                    state_store=self._state_store)
        self.flooding = Flooding(self.pseudonym, transport=self._transport, epoch=self.epoch)

        short_pseudonym = bytes_hex_abbrv(sd.pseudonym, 6)
        self._logger = structlog.get_logger(__name__ + ' > ' + self.__class__.__name__)\
            .bind(role=self.role, server_name=sd.id, pseudonym=short_pseudonym, epoch=sd.epoch)
        # init special file logger for any monitor:
        self._monitor_logger = structlog.get_logger(MONITOR_STATUS)\
            .bind(role=self.role, server_id=sd.id, epoch=sd.epoch, pseudonym=short_pseudonym)

    @classmethod
    def __init_subclass__(cls, registry_name: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if registry_name is not None:
            _role_registry[registry_name.upper()] = cls
            cls._role = registry_name

    @property
    def role(self):
        return self.__class__._role

    @property
    def pseudonym(self) -> bytes:
        return self.server_data.pseudonym

    @property
    def epoch(self) -> str:
        return self.server_data.epoch

    @staticmethod
    def create(registry_name: str, **kwargs):
        """
        create the appropriate (subclass) role object from given string
        """
        role_class = _role_registry.get(registry_name.upper())
        if role_class:
            structlog.getLogger(__name__).debug(f'Creating role {registry_name.upper()}')
            return role_class(**kwargs)
        raise ValueError(f'Cannot find class for {registry_name.upper()}')

    @property
    def server_data(self) -> ServerData:
        return self._server_data

    @property
    def private_key(self) -> PrivateKey:
        return self._key_material.private_key

    @property
    def root_certificate(self):
        return self._key_material.root_cert

    @property
    def server_key(self) -> Optional[RSAPrivateKey]:
        return self._key_material.server_key

    def __repr__(self):
        return self.role

    async def emit(
            self,
            message: PrismMessage,
            address: str = None,  # if not specified, will try to resolve the destination address from msg.pseudonym
            context: SpanContext = None,
            timeout_ms: int = math.inf
    ):
        assert message

        with self.trace("emit-message", context or message, address=address) as scope:
            for n_try in range(0, max(configuration.emit_retries, 1)):
                if address is None:
                    # resolve address from message.pseudonym:
                    address, message = await self.ls_routing.resolve_address(message, scope.context)

                    if address == "*" and configuration.ls_routing:
                        address = None
                        scope.warning(f"Failed to resolve address for message. "
                                             f"Sleeping for {configuration.sleep_try_emitting}")
                        await trio.sleep(configuration.sleep_try_emitting)
                        continue

                if await self._transport.emit_on_links(address, message, scope.context, timeout_ms):
                    if n_try:
                        scope.debug(f"Emit to {address} worked for {n_try+1}. try")
                    return True

                scope.debug(f"Emit to {address} didn't work at the {n_try+1}. try - " +
                            f"sleeping for {configuration.sleep_try_emitting}s")
                await trio.sleep(configuration.sleep_try_emitting)

            scope.warning(f"Could not emit {message.msg_type} to {address}")
            return False

    @contextmanager
    def trace(
            self,
            operation: str,
            parent: Optional[Union[PrismMessage, SpanContext]] = None,
            *joining: Union[PrismMessage, SpanContext],
            **kwargs
    ):
        tags = {"role": self.role, "epoch": self.epoch, **kwargs}

        with trace_context(self._logger, operation, parent, *joining, **tags) as scope:
            yield scope

    def monitor_data(self) -> dict:
        return {
            "flood_db_size": len(self.flooding),
            "dropbox_index": self.server_data.dropbox_index,
            "lsp_table_size": len(self.ls_routing.LSP_DB.routing_table),
            "monitor_ts": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "monitor_interval": configuration.log_monitor_interval
        }

    async def alive_loop(self):
        if not configuration.get('log_dir'):
            self._logger.debug(f'done with alive-loop as no log directory specified')
            return  # we are done!

        self._monitor_logger.info(f'Initialized monitor logging')
        while True:
            next_sleep = configuration.get('log_monitor_interval', 60)
            self._monitor_logger.info(f'still alive - sleeping for {next_sleep}s', sleep=next_sleep,
                                      **self.monitor_data())
            with self.trace("alive-loop", sleep=next_sleep, **self.monitor_data()):
                pass
            await trio.sleep(next_sleep)

    async def handler_loop(
            self,
            nursery: trio.Nursery,
            handler: Callable[[trio.Nursery, PrismMessage, SpanContext], Awaitable[None]],
            require_pseudonym: bool,
            *types
    ):
        if require_pseudonym:
            hook = MessageTypeHook(self.pseudonym, *types)
        else:
            hook = MessageTypeHook(None, *types)
        await self._transport.register_hook(hook)

        while True:
            package = await hook.receive_pkg()
            message = package.message
            context = package.context

            if message.ciphertext and message.half_key and message.nonce:
                with self.trace("handling-decrypted", context) as scope:
                    decrypted = decrypt(message, self.private_key)
                    if not isinstance(decrypted, PrismMessage):
                        scope.warning(f"Decrypted message is not a valid Prism Message: {decrypted} as {self}")
                        continue

                    scope.debug(f'{self} handling decrypted {decrypted.msg_type}')
                    context = scope.context
                    message = decrypted

            await handler(nursery, message, context)

    async def main(self):
        """
        Main entry point to run this role.
        """
        # self._logger.debug(f'starting main() in {__class__}')

        with self.trace("role-choice", pseudonym=bytes_hex_abbrv(self.pseudonym), **self.monitor_data()) as role_scope:
            role_scope.info(f'Chosen role: {self.role}' +
                            (f' ({self.server_data.dropbox_index})'
                             if self.server_data.dropbox_index is not None and self.server_data.dropbox_index >= 0
                             else ''),
                            role=self.role, proof=self.server_data.proof, pseudonym=bytes_hex_abbrv(self.pseudonym),
                            key_material=self._key_material)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.alive_loop)  # output alive messages to any monitor
            nursery.start_soon(self.flooding.flood_listen_loop)

    def cleanup(self) -> None:
        self._logger.info(f'Goodbye from role {self}')
        # subclasses can do clean up here but should call super().cleanup()
