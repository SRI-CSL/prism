#  Copyright (c) 2019-2023 SRI International.

from __future__ import annotations

from dataclasses import dataclass
from jaeger_client import SpanContext
import random
import trio
from typing import List, Dict, Set, Optional, Tuple

from prism.common.transport.maintenance import outgoing_links_task
from prism.server.CS2.roles.lockfree.fragment import Fragment
from prism.server.CS2.roles.lockfree.mpc import MPCRole, mpc_op
from prism.server.CS2.roles.lockfree.peer import DropboxPeer
from prism.server.CS2.roles.lockfree.poll import Poll
from prism.common.transport.transport import Link
from prism.common.message import PrismMessage, Share, TypeEnum, ActionEnum, HalfKeyMap
from prism.common.config import configuration
from prism.common.crypto.server_message import decrypt, encrypt_data
from prism.common.crypto.util import make_nonce
from prism.common.tracing import inject_span_context, extract_span_context, PrismScope


class LockFreeDropbox(MPCRole, registry_name="DROPBOX_LF"):
    """
    Lock-free implementation of our MPC dropbox.

    When sending messages, clients construct secret shares of both the message and the receiver's pseudonym and encrypt
    them using the keys of different peers in the dropbox.

    Storing messages is simple: The peer handling the store request generates a unique fragment ID and distributes the
    encrypted submessages to different peers to store under the fragment ID.

    When polling, clients construct shares of their own pseudonym and likewise encrypt them for different peers.
    The peer that receives the poll request requests a series of operations in which different fragment IDs that are
    known to still be stored are checked against the pseudonym fragments via an algorithm described in
    LockFreeDropbox.retrieve_task().
    """

    peers: List[DropboxPeer]
    stored_fragments: Dict[bytes, Fragment]
    retrieved_fragments: Set[bytes]
    outgoing_link: Optional[Link]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.stored_fragments = {}
        self.retrieved_fragments = set()
        self.store_limiter = trio.CapacityLimiter(configuration.mpc_lf_concurrent_store_limit)
        self.find_limiter = trio.CapacityLimiter(configuration.mpc_lf_concurrent_find_limit)
        self.active_polls = 0

    def ark_data(self) -> Optional[dict]:
        d = super().ark_data()

        d["dropbox_index"] = self.server_data.dropbox_index
        # TODO - Remove and have clients use system modulus?
        d["secret_sharing"] = self.sharing.parameters
        d["worker_keys"] = [peer.ark_key for peer in self.peers]

        # FIXME - Find a more permanent solution to premature MPC ARKing
        if len(list(filter(None, d["worker_keys"]))) < len(self.peers):
            return None

        return d

    @property
    def ark_ready(self) -> bool:
        return self.is_leader and self.preproducts.total_remaining([]) > 0

    def monitor_data(self) -> dict:
        if not self.is_active_member:
            return super().monitor_data()

        return {
            **super().monitor_data(),
            "dropbox_stored_count": len(self.stored_fragments),
            "active_polls": self.active_polls,
        }

    async def dropbox_task(self, nursery: trio.Nursery, decrypted: PrismMessage, context: SpanContext):
        """Handles incoming ENCRYPTED_DROPBOX_MESSAGE messages, starting a new task to process each request."""
        if decrypted.msg_type == TypeEnum.READ_OBLIVIOUS_DROPBOX:
            nursery.start_soon(self.poll_task, context, decrypted)
        elif decrypted.msg_type == TypeEnum.WRITE_OBLIVIOUS_DROPBOX:
            nursery.start_soon(self.store_task, context, decrypted)

    async def store_task(self, context: SpanContext, message: PrismMessage):
        """Handles a request to store a message. Will retry until success."""
        # noinspection PyTypeChecker
        submessages: List[PrismMessage] = message.submessages
        fragment_id = self.random_id()
        with self.trace("store-message", context) as scope:
            scope.debug(f"STO: Storing fragment {fragment_id.hex()[:6]}")
        while True:
            self.store_limiter.total_tokens = configuration.mpc_lf_concurrent_store_limit
            async with self.store_limiter:
                if await self.attempt_store_task(fragment_id, scope, submessages):
                    break
                else:
                    await trio.sleep(10)
            self._monitor_logger.debug("STO: Stored fragment", dropbox_stored_count=len(self.stored_fragments))

    async def attempt_store_task(self, fragment_id: bytes, scope: PrismScope, submessages: List[PrismMessage]) -> bool:
        peers = []
        requests = []

        for m in submessages:
            if self.online(m.party_id) and fragment_id not in self.peers[m.party_id].stored_fragments:
                peers.append(self.peers[m.party_id])
                requests.append(
                    self.request(self.handle_store_op, fragment_id, sub_msg=inject_span_context(m, scope.context))
                )

        for response in await self.send_and_gather(peers, requests, timeout_sec=configuration.mpc_lf_store_timeout):
            self.peers[response.party_id].stored_fragments.add(fragment_id)

        stored_peers = [peer for peer in self.online_peers if fragment_id in peer.stored_fragments and peer.ready]

        if len(stored_peers) >= self.sharing.threshold:
            scope.debug(f"STO: Stored {len(stored_peers)} fragments of {fragment_id.hex()[:6]}")
            return True
        else:
            scope.debug(f"STO: Failed to store fragments {fragment_id.hex()[:6]}... retrying")
            return False

    # noinspection PyTypeChecker
    @mpc_op(ActionEnum.ACTION_STORE_FRAGMENT)
    async def handle_store_op(self, message: PrismMessage):
        fragment_id = message.mpc_map.request_id
        encrypted = message.sub_msg
        context = extract_span_context(encrypted)
        decrypted = decrypt(encrypted, self.private_key)

        if not decrypted:
            self._logger.debug("STO: Error decrypting message fragment.")
            return

        share = Share(decrypted.pseudonym_share, self.party_id)
        fragment = Fragment(fragment_id, share, decrypted.ciphertext, context)
        self.stored_fragments[fragment_id] = fragment

        with self.trace("store-fragment", context) as scope:
            scope.debug(f"STO: Stored fragment {fragment}")
            if configuration.debug_extra:
                scope.debug(f"STO: trace {scope.trace_id}, share: {decrypted.pseudonym_share}, "
                            f"party_id {self.party_id}")

        self.peers[self.party_id].stored_fragments.add(fragment_id)

        await self.respond_to(message, op_success=True)

    async def poll_task(self, context: SpanContext, message: PrismMessage):
        """
        Handles a poll request for messages matching a secret-shared pseudonym.

        In a single iteration, check fragments that the poll request has not already checked until we run out of
        un-checked fragments. If the poll request has an expiration date attached, continue checking until it expires.
        """

        with self.trace("poll", context, request_id=message.nonce.hex()[:6]) as scope:
            poll = Poll.from_message(message, scope)

            async with trio.open_nursery() as nursery:
                scope.debug(f"POLL: Poll request {poll.nonce.hex()[:6]} started with {len(poll.peer_fragments)} shares."
                            f" Polling until {poll.expiration}")

                self.active_polls += 1
                while poll.live:
                    threshold = self.sharing.threshold
                    limit = configuration.mpc_lf_find_limit
                    fragments_to_check = poll.fragments_to_check(self.online_peers, threshold, limit)

                    while fragments_to_check and (not poll.expiration or poll.live):
                        self.find_limiter.total_tokens = configuration.mpc_lf_concurrent_find_limit
                        async with self.find_limiter:
                            await self.attempt_poll_task(nursery, poll, fragments_to_check)
                        fragments_to_check = poll.fragments_to_check(self.online_peers, threshold, limit)

                    # If the poll has no expiration date, then finish after checking once
                    if not poll.expiration:
                        break

                    await trio.sleep(0.1)

                scope.debug(f"POLL: Poll request {poll.nonce.hex()[:6]} ended.")
                self.active_polls -= 1

            # TODO - more vigorous cleanup to prevent memory leak
            for link in poll.links:
                scope.debug(f"Closing link {link}")
                await link.close()
                scope.debug("Link closed")

    def peers_for_fragments(self, poll: Poll, fragments: Set[bytes]) -> List[DropboxPeer]:
        """Picks some peers to use for a check task. Tries to pick a set of peers of size threshold+1 if available,
        but will settle for threshold peers."""
        buddies = [
            peer
            for peer in self.online_peers
            if not peer.local and fragments.issubset(peer.stored_fragments) and peer.party_id in poll.peer_fragments
        ]
        buddy_count = min(len(buddies), self.sharing.threshold)
        return [self.local_peer, *random.sample(buddies, k=buddy_count)]

    async def attempt_poll_task(self, nursery: trio.Nursery, poll: Poll, fragments: Set[bytes]):
        fragments_to_retrieve = await self.check_task(poll, fragments)

        if fragments_to_retrieve:
            poll.scope.debug(
                f"POLL: Poll {poll.nonce.hex()[:6]} found fragments "
                f"{[frag.hex()[:6] for frag in fragments_to_retrieve]}"
            )
            if poll.link_addresses and not poll.links:
                for address in poll.link_addresses:
                    poll.scope.debug(f"Loading poll return address: {address}")
                    link = await self._transport.load_address(address, [poll.nonce.hex()], self.epoch)
                    if not link:
                        poll.scope.error(f"POLL: Failed to load link address {address}")
                        continue
                    poll.scope.debug(f"POLL: Loaded link {link}")
                    poll.links.append(link)

                if not poll.links:
                    poll.scope.error("Could not load any links for poll request.")
                    # TODO - configurable sleep
                    await trio.sleep(5.0)
                    return

            nursery.start_soon(self.retrieve_and_delete_task, nursery, poll, fragments_to_retrieve)

    async def check_task(self, poll: Poll, fragments: Set[bytes]) -> Set[bytes]:
        op_id = self.random_id()
        op_peers = self.peers_for_fragments(poll, fragments)
        if len(op_peers) < self.sharing.threshold:
            poll.scope.error("POLL: Not enough peers to retrieve.")
            return set()

        poll.scope.debug(f"POLL: Running retrieve with {len(op_peers)} peers")

        preproduct_info = await self.preproducts.claim_chunk(len(fragments), op_peers)
        targets = list(fragments)[: preproduct_info.size]

        poll.scope.debug(
            f"POLL: Poll {poll.nonce.hex()[:6]} checking fragments " f"{[fragment.hex()[:6] for fragment in targets]}"
        )

        requests = [
            self.request(
                self.handle_find_op,
                op_id,
                sub_msg=poll.peer_fragments[peer.party_id],
                participants=[peer.party_id for peer in op_peers],
                target_fragments=targets,
                preproduct_info=preproduct_info,
                origin=poll.trace,
            )
            for peer in op_peers
        ]

        timeout = configuration.mpc_lf_check_timeout + self.timeout_padding(4, 1000 * len(targets), len(op_peers))
        responses = await self.send_and_gather(op_peers, requests, timeout_sec=timeout)
        successes = [response for response in responses if response.mpc_map.op_success]
        poll.scope.debug(f"POLL: Got {len(successes)} responses")

        if len(successes) < self.sharing.threshold:
            poll.scope.error("POLL: Not enough successful results to finish retrieve.")
            return set()

        shares = list(zip(*(m.mpc_map.shares for m in successes)))
        results = [self.sharing.open(share_set) for share_set in shares]
        poll.scope.debug(f"Results: {results}")
        checked_fragment_ids = [frag_id for frag_id, result in zip(list(fragments), results) if result is not None]
        poll.checked_fragments.update(checked_fragment_ids)

        return set(fragment_id for fragment_id, result in zip(targets, results) if result == 0)

    @mpc_op(ActionEnum.ACTION_FIND_HANDLER)
    async def handle_find_op(self, message: PrismMessage):
        trace = message.mpc_map.origin
        targets = message.mpc_map.target_fragments
        self._logger.debug(f"FIND {trace}: Handling find op with {message.mpc_map.participants}")
        op_peers = [peer for peer in self.online_peers if peer.party_id in sorted(message.mpc_map.participants)]
        preproducts = self.preproducts.get_chunk(message.mpc_map.preproduct_info)

        if not preproducts:
            self._logger.debug("FIND: Failed to acquire preproducts.")
            return

        # noinspection PyTypeChecker
        read_peer = decrypt(message.sub_msg, self.private_key)
        if not read_peer:
            self._logger.debug("FIND: Failed to decrypt peer message.")
            return

        pseudo_share = Share(read_peer.pseudonym_share, self.party_id)
        frags = [self.stored_fragments.get(fragment_id, Fragment.dummy()) for fragment_id in targets]
        diffs = [self.sharing.sub(frag.pseudonym_share, pseudo_share) for frag in frags]

        rand_diffs = await self.mulm(
            diffs,
            preproducts.random_numbers,
            preproducts.triples,
            op_peers,
            message.mpc_map.request_id,
        )

        if configuration.debug_extra:
            self._mpc_logger.debug(
                f"FIND",
                poll_trace=trace,
                preproducts=preproducts.json(),
                pseudo_share=pseudo_share.json(),
                fragments=[frag.json() for frag in frags],
                diffs=[diff.json() for diff in diffs],
                rand_diffs=[rdiff.json() for rdiff in rand_diffs]
            )

        if not rand_diffs:
            return

        await self.respond_to(message, op_success=True, shares=rand_diffs)

    @dataclass
    class RetrievedMessage:
        fragment_id: bytes
        submessages: List[PrismMessage]

        def __repr__(self) -> str:
            return f"Retrieved({self.fragment_id.hex()[:6]})"

    async def retrieve_and_delete_task(self, nursery: trio.Nursery, poll: Poll, fragments: Set[bytes]):
        for result in await self.retrieve_task(poll, fragments):
            nursery.start_soon(self.reply_and_delete_task, poll, result)

    async def retrieve_task(self, poll: Poll, fragments: Set[bytes]) -> List[LockFreeDropbox.RetrievedMessage]:
        poll.scope.debug(f"RAD {poll.trace}: Requesting fragments of {len(fragments)} messages")
        op_id = self.random_id()
        peers = [
            peer
            for peer in self.online_peers
            if peer.stored_fragments.intersection(fragments) and peer.party_id in poll.peer_fragments
        ]
        requests = [
            self.request(
                self.handle_retrieve_op,
                op_id,
                target_fragments=list(fragments),
                sub_msg=poll.peer_fragments[peer.party_id],
            )
            for peer in peers
        ]
        # TODO - shortcut retrieve when possible
        responses = await self.send_and_gather(peers, requests, timeout_sec=configuration.mpc_lf_retrieve_timeout)
        poll.scope.debug(f"RAD {poll.trace}: Got {len(responses)} responses")

        fragment_responses = {fragment_id: [] for fragment_id in fragments}
        for response in responses:
            for fragment_id, submessage in zip(response.mpc_map.target_fragments, response.submessages):
                fragment_responses[fragment_id].append(submessage)

        results = []
        for fragment_id, submessages in fragment_responses.items():
            if len(submessages) < self.sharing.threshold:
                continue

            if configuration.mpc_lf_minimal_replies:
                submessages = submessages[: self.sharing.threshold]
            results.append(LockFreeDropbox.RetrievedMessage(fragment_id, submessages))

        return results

    async def reply_and_delete_task(self, poll: Poll, message: RetrievedMessage):
        reply = poll.reply(message.submessages)
        while not await self.reply_to_client(poll, reply):
            retry_timer = configuration.mpc_lf_reply_retry_seconds
            poll.scope.debug(f"Reply attempt failed. Retrying in {retry_timer}s")
            await trio.sleep(retry_timer)
            # TODO - eventually give up
        poll.scope.debug(f"RAD {poll.trace}: Sent {message} to client")
        await self.delete_task(message)

    async def delete_task(self, message: RetrievedMessage):
        op_id = self.random_id()
        request = self.request(self.handle_delete_op, op_id, target_fragments=[message.fragment_id])
        peers = [peer for peer in self.online_peers if message.fragment_id in peer.stored_fragments]
        for peer in peers:
            peer.stored_fragments.remove(message.fragment_id)
        # Don't await a response, because we don't actually care
        await self.send_to_peers(peers, request)

    async def reply_on_link(self, link: Link, event: trio.Event, message: PrismMessage, context: SpanContext):
        if await link.send(message, context):
            event.set()

    async def reply_to_client(self, poll: Poll, reply: PrismMessage) -> bool:
        sender_context = extract_span_context(reply)
        with self.trace("fwd-message", sender_context, poll.context) as scope:
            scope.debug(f"Forwarding message to poller via {f'{poll.links}' if poll.links else '*client'}")
            sender_context = scope.context
        if poll.links:
            # Attempt to send on each of the links provided by the client.
            # Return True immediately if one succeeds.
            success = trio.Event()
            with trio.move_on_after(configuration.db_reply_timeout) as cancel_scope:
                async with trio.open_nursery() as nursery:
                    for link in poll.links:
                        nursery.start_soon(self.reply_on_link, link, success, reply, sender_context)

                    await success.wait()
                    cancel_scope.cancel()
            return success.is_set()
        else:
            if self.outgoing_links:
                self._logger.debug(f"Sending reply on broadcast link(s)")
                # TODO - better tracking of send success, should probably want a success on all channels
                success = False
                for link in self.outgoing_links:
                    if await link.send(reply, sender_context):
                        success = True
                return success
            else:
                return await self._transport.emit_on_links(
                    "*client",
                    reply,
                    sender_context,
                    timeout_ms=int(1000 * configuration.db_reply_timeout),
                )

    @mpc_op(ActionEnum.ACTION_RETRIEVE)
    async def handle_retrieve_op(self, message: PrismMessage):
        # noinspection PyTypeChecker
        req_info = decrypt(message.sub_msg, self.private_key)
        targets = message.mpc_map.target_fragments
        client_key = req_info.half_key.to_key()

        self._logger.debug(f"RETR: Requested to retrieve {len(targets)} fragments")

        response_fragments = []
        response_messages = []
        for target in targets:
            fragment = self.stored_fragments.get(target)

            if not fragment:
                continue
            response_fragments.append(target)
            nonce = make_nonce()
            key = client_key.generate_private()

            response_messages.append(
                inject_span_context(
                    PrismMessage(
                        msg_type=TypeEnum.ENCRYPTED_MESSAGE_FRAGMENT,
                        party_id=self.party_id,
                        nonce=nonce,
                        half_key=HalfKeyMap.from_key(key.public_key()),
                        ciphertext=encrypt_data(fragment.ciphertext, key, client_key, nonce),
                    ),
                    fragment.store_context,
                )
            )

        await self.respond_to(
            message, submessages=response_messages, target_fragments=response_fragments, op_success=True
        )

    @mpc_op(ActionEnum.ACTION_DELETE)
    async def handle_delete_op(self, message: PrismMessage):
        fragments = message.mpc_map.target_fragments
        for fragment_id in fragments:
            frag_to_delete = self.stored_fragments.pop(fragment_id, None)
            if frag_to_delete:
                self._logger.debug(f"DEL: Deleted {frag_to_delete}")
                self.retrieved_fragments.add(fragment_id)

    @property
    def ready(self) -> bool:
        """If True, this node has enough information to participate in MPC."""
        if not self.sharing:
            return False

        threshold = self.preprocessing_threshold
        peer_key_count = len(list(filter(lambda p: p.half_key, self.peers)))

        if peer_key_count < threshold:
            return False

        return True

    # Overridden for type checking
    @property
    def online_peers(self) -> List[DropboxPeer]:
        return [peer for peer in self.peers if self.online(peer)]

    @property
    def local_peer(self) -> DropboxPeer:
        return self.peers[self.party_id]

    def form_committee(self):
        if self.epoch == "genesis":
            self.form_genesis_committee()
        else:
            self.form_epoch_committee()

        if not self.is_active_member:
            return

        self.local_peer.local = True
        self.local_peer.pseudonym = self.pseudonym
        self.local_peer.half_key = self.server_data.half_key_map()

    def form_genesis_committee(self):
        committee_members = [member.strip() for member in configuration.get("committee_members", "").split(",")]
        self.party_id = int(configuration.get("party_id", -1))
        self.peers = [DropboxPeer(i, name) for i, name in enumerate(committee_members)]

    def form_epoch_committee(self):
        nparties = configuration.get("mpc_nparties")
        minimum_parties = configuration.get("threshold") + 1

        committee_name = self.server_data.committee
        committee_members = [eark for eark in self.previous_role.flooding.payloads
                             if eark.committee == committee_name]

        def committee_ordering_key(eark: PrismMessage):
            return eark.pseudonym.hex()

        committee_members = sorted(committee_members, key=committee_ordering_key)
        active_members = committee_members[:nparties]
        if len(active_members) < minimum_parties:
            self._logger.error(f"Not enough known members sorted into committee {committee_name}. "
                               f"Sleeping until next epoch.")
            return False

        self._logger.debug(f"Committee formed with members {[member.name for member in active_members]}")

        self.peers = [DropboxPeer(i, eark.name) for i, eark in enumerate(active_members)]
        for i in range(len(self.peers)):
            if self.peers[i].name == self.server_data.id:
                self.party_id = i
                break

        return True

    def link_targets(self, seed: int) -> List[Tuple[PrismMessage, str]]:
        if not self.is_active_member:
            return super().link_targets(seed)

        targets = []
        pool = self.previous_role.flooding.payloads
        peer_names = [peer.name for peer in self.peers if not peer.local]
        targets.extend((eark, "mpc") for eark in pool if eark.name in peer_names)

        if self.is_leader:
            targets.extend(super().link_targets(seed))

        return targets

    async def main(self):
        self.form_committee()

        if not self.is_active_member:
            return await super(MPCRole, self).main()

        async with trio.open_nursery() as nursery:
            nursery.start_soon(super().main)

            if self.is_leader:
                nursery.start_soon(
                    outgoing_links_task,
                    self._logger,
                    self._transport,
                    self.outgoing_links,
                    {"downlink"},
                    self.epoch
                )

            nursery.start_soon(self.handler_loop, nursery, self.dropbox_task, True, TypeEnum.ENCRYPT_DROPBOX_MESSAGE)
