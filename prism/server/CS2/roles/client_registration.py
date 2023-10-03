#  Copyright (c) 2019-2023 SRI International.

import trio
from jaeger_client import SpanContext

from prism.client.client import MessageDelegate, PrismClient
from prism.common.cleartext import ClearText
from prism.common.config import configuration
from prism.common.crypto.ibe import BonehFranklin
from prism.common.crypto.server_message import encrypt
from prism.common.crypto.util import make_nonce
from prism.common.message import PrismMessage, TypeEnum, HalfKeyMap, CipherEnum
from prism.server.CS2.roles.abstract_role import AbstractRole


class ClientRegistration(AbstractRole, MessageDelegate, registry_name="CLIENT_REGISTRATION"):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = PrismClient(self._transport, self._state_store, delegate=self)
        self.ibe = BonehFranklin.load_generator(configuration.ibe_param_shard, configuration.ibe_secret)
        self.ibe._system_secret = BonehFranklin.parse_system_secret(configuration.ibe_secret)
        self.distributed_keys = {}

    def message_received(self, cleartext: ClearText):
        if cleartext.message_bytes is None:
            return

        request = PrismMessage.decode(cleartext.message_bytes)

        if request.msg_type != TypeEnum.CLIENT_REGISTRATION_REQUEST:
            self._logger.warning("Received message that wasn't registration request.")
            return

        if not self.authorize(request):
            self._logger.warning("Received unauthorized registration request.")
            return

        with self.trace("client-registration-response", cleartext.context) as scope:
            self.register_client(request, scope.context)

    async def main(self):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)
            nursery.start_soon(self.client.start)

    def authorize(self, request: PrismMessage) -> bool:
        # TODO - preload/persist
        if request.name in self.distributed_keys and request.nonce != self.distributed_keys[request.name]:
            return False
        return True

    def register_client(self, request: PrismMessage, context: SpanContext):
        client_name = request.name
        client_private_key = self.ibe.generate_private_key(client_name)
        client_half_key = request.half_key.to_key()
        private_key = client_half_key.generate_private()
        nonce = make_nonce()

        inner_response = PrismMessage(
            name=self.client.config.name,
            nonce=request.nonce,
            msg_type=TypeEnum.CLIENT_REGISTRATION_RESPONSE,
            messagetext=client_private_key
        )
        encrypted_response = encrypt(inner_response, private_key, peer_key=client_half_key, nonce=nonce)

        response = PrismMessage(
            msg_type=TypeEnum.ENCRYPT_REGISTRATION_MESSAGE,
            cipher=CipherEnum.AES_GCM,
            ciphertext=encrypted_response,
            nonce=nonce,
            half_key=HalfKeyMap.from_key(private_key.public_key())
        )

        clear_response = ClearText(
            sender=self.client.config.name,
            receiver=client_name,
            message_bytes=response.encode(),
            context=context,
            use_ibe=False,
        )

        self.distributed_keys[request.name] = request.nonce
        self.client.process_clear_text(clear_response)
