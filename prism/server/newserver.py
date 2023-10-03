#  Copyright (c) 2019-2023 SRI International.

from queue import Queue, Empty
from random import seed, random
import structlog
from time import time_ns
import trio
from typing import Optional

from prism.common.config import configuration
from prism.common.state import StateStore
from prism.common.tracing import init_tracer, trace_context
from prism.common.transport.transport import Transport
from prism.server.CS2.roles import ClientRegistration
from prism.server.epoch import Epoch, EpochState
from prism.common.epoch import EpochCommandType, EpochCommand
from prism.server.pki import ServerPKI


class PrismServer:
    def __init__(self, transport: Transport, state_store: StateStore, config=None):
        self.logger = structlog.get_logger("prism.server")
        self.transport = transport
        self.state_store = state_store
        self.configuration = config or configuration

        self.init_logging()
        seed(str(time_ns()) + self.name)

        self.epoch_command_queue: Queue[EpochCommand] = Queue()
        self.epochs = {}
        self.current_epoch: Optional[Epoch] = None

        self.pki = ServerPKI(self.configuration)

    @property
    def name(self):
        if "name" not in self.configuration:
            from socket import getfqdn

            self.configuration["name"] = getfqdn()

        return configuration.get("name")

    def init_logging(self):
        self.logger.bind(server_name=self.name)
        init_tracer(self.logger,
                    configuration=self.configuration,
                    service=self.configuration.get("JAEGER_SERVICE_NAME", self.name))

    def load_epoch(self) -> Epoch:
        # TODO - when implementing state saving, load epoch seed from StateStore
        # TODO - if genesis and transport is PrismTransport,
        #        call transport.configure() or otherwise setup genesis links
        return Epoch.from_seed(self, previous=None, seed=None)

    def epoch_command(self, command: EpochCommand):
        self.epoch_command_queue.put(command)

    def launch_epoch(self, nursery, epoch: Epoch):
        self.current_epoch = epoch
        self.epochs[self.current_epoch.name] = epoch
        self.logger.debug(f"Launching epoch {epoch.name}")
        nursery.start_soon(self.current_epoch.start)

    async def main_loop(self):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.transport.run)
            self.launch_epoch(nursery, self.load_epoch())
            if isinstance(self.current_epoch.role, ClientRegistration):
                self.logger.debug("Role is ClientRegistration, disabling epoch switching")
                while True:
                    await trio.sleep(10.0)

            while True:
                try:
                    epoch_command = self.epoch_command_queue.get_nowait()

                    if epoch_command.target_epoch_name:
                        target_epochs = [self.epochs[epoch_command.target_epoch_name]]
                    else:
                        target_epochs = [epoch for epoch in self.epochs.values() if epoch.state != EpochState.OFF]

                    if epoch_command.command_type == EpochCommandType.NEW:
                        new_epoch = Epoch.from_seed(self, self.current_epoch, epoch_command.epoch_seed)
                        self.launch_epoch(nursery, new_epoch)
                    elif epoch_command.command_type == EpochCommandType.NEXT:
                        for epoch in target_epochs:
                            self.logger.debug(f"Advancing epoch {epoch.name} to next state")
                            await epoch.next_state(nursery)
                    elif epoch_command.command_type == EpochCommandType.OFF:
                        for epoch in target_epochs:
                            self.logger.debug(f"Shutting down epoch {epoch.name}")
                            await epoch.shutdown()
                    elif epoch_command.command_type == EpochCommandType.FLOOD_EPOCH:
                        for epoch in target_epochs:
                            if epoch.state == EpochState.PRE_RUN and epoch.previous:
                                await epoch.previous.flood_ark(epoch.epoch_ark)
                    elif epoch_command.command_type == EpochCommandType.FLOOD_LSP:
                        for epoch in target_epochs:
                            await epoch.flood_lsp()
                    elif epoch_command.command_type == EpochCommandType.CONFIG:
                        epoch_command.update_config(self.logger)
                    else:
                        self.logger.error(f"Unhandled epoch command: {epoch_command}")
                except Empty:
                    pass

                await trio.sleep(0.1)

    async def main(self):
        try:
            with trace_context(self.logger, "initial-sleep", server_id=self.name) as scope:
                offset = self.configuration.delay_fixed + (self.configuration.delay * random())
                scope.info(f"Initial sleep: {offset:.2f}s", seconds=offset)
                await trio.sleep(offset)

            await self.main_loop()
        except Exception as e:
            import traceback
            with trace_context(self.logger, "fatal-error", server_id=self.name) as scope:
                scope.error(f"Server died with exception {traceback.format_exc()}")
            raise e
