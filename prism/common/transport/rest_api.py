#  Copyright (c) 2019-2023 SRI International.
from abc import ABCMeta
from base64 import b64decode
import httpx
import structlog
from time import time
import trio
from typing import Tuple, Optional, AsyncIterable

from prism.common.message import MSG_MIME_TYPE


class RestAPI(metaclass=ABCMeta):
    def __init__(self, configuration):
        super().__init__()
        self.configuration = configuration
        self._logger = structlog.get_logger(__name__)

    async def post_data(self, address: str, proxy, data: bytes,
                        posting_timeout: int = 0, destination: str = None) -> bool:
        headers = {'Content-Type': MSG_MIME_TYPE}
        entrypoint = f'{address}/message{"" if destination is None else f"?dest={destination}"}'

        try:
            async with httpx.AsyncClient(proxies=proxy) as client:
                response = await client.post(entrypoint,
                                             headers=headers,
                                             content=data,
                                             timeout=posting_timeout if posting_timeout > 0 else None)
                if response.status_code == httpx.codes.CREATED:
                    # response_json = response.json()
                    # message_text = f'message id={response_json["id"]}' if "id" in response_json else "<no message id>"
                    # digest = hash_data(data)
                    # self._logger.debug(f'POST success [{digest[:8]}]: {message_text} to {address}',
                    #                    digest=digest, amount=len(data),
                    #                    least=response_json.get("least", "<None>"),
                    #                    greatest=response_json.get("greatest", "<None>"))
                    return True
        except httpx.RequestError as exc:
            self._logger.warning(f"Request Error with POST {exc.request.url!r} - giving up")

        return False

    async def get_data(self, address: str, proxy, polling_interval_setting: str, polling_timeout: int = 10,
                       batch_size: int = 1) -> AsyncIterable[Tuple[bytes, Optional[str]]]:

        # obtain current UUID:
        last_seen_uuid_id = None
        while last_seen_uuid_id is None:
            try:
                async with httpx.AsyncClient(proxies=proxy) as client:
                    response = await client.get(f'{address}/message?count=0',
                                                timeout=(polling_timeout + 1) if polling_timeout > 0 else None)
                    if response.status_code == httpx.codes.OK:
                        uuid = response.json()["uuid"]
                        last_seen_uuid_id = [uuid, 0]
                        self._logger.info(f"Obtained UUID={uuid} from {address} to start polling")
            except httpx.RequestError as exc:
                self._logger.warning(f"Request Error with GET {exc.request.url!r} - trying again later")
            if last_seen_uuid_id is None:
                await trio.sleep(max(1, self.configuration.get(polling_interval_setting)*60))

        self._logger.info(f'Start from least={last_seen_uuid_id[1]} for UUID={last_seen_uuid_id[0]}')
        while True:
            greatest = last_seen_uuid_id[1] + 1  # trigger one polling of whiteboard (at start of polling interval)
            # start = time()

            try:
                async with httpx.AsyncClient(proxies=proxy) as client:
                    # get all unseen messages in this round = polling interval
                    while last_seen_uuid_id[1] < greatest:
                        entrypoint = f'{address}/message?first={last_seen_uuid_id[1] + 1}' + \
                                     f'{"" if batch_size == 1 else f"&count={batch_size}"}'
                        response = await client.get(entrypoint,
                                                    timeout=(polling_timeout + 1) if polling_timeout > 0 else None)
                        if response.status_code == httpx.codes.OK:
                            response_json = response.json()
                            if response_json["uuid"] != last_seen_uuid_id[0]:
                                # reset counters for new UUID and poll immediately again (with new 'first' setting)
                                last_seen_uuid_id[0] = response_json["uuid"]
                                last_seen_uuid_id[1] = max(response_json.get("least", 0) - 1, 0)
                                self._logger.info(f'Restart from least={last_seen_uuid_id[1]} ' +
                                                  f'for (new) UUID={last_seen_uuid_id[0]}')
                            else:
                                # self._logger.debug(f'OK - response JSON={response_json}')
                                if len(response_json["messages"]):
                                    for message_dict in response_json["messages"]:
                                        last_seen_uuid_id[1] = message_dict["id"]
                                        destination = None  # for anonymous broadcast
                                        if "host" in message_dict:
                                            # dest_type: unicast
                                            destination = message_dict["host"]
                                        elif "group" in message_dict:
                                            # dest_type: multicast
                                            destination = message_dict["group"]
                                            self._logger.error(f'Cannot handle multicast (group) messages yet!')
                                        data = b64decode(message_dict["message"].encode())
                                        # digest = hash_data(data)
                                        # self._logger.debug(f'GET success [{digest[:8]}]: message from {address}',
                                        #                    digest=digest, amount=len(data), msg_id=message_dict["id"])
                                        yield data, destination
                                else:
                                    # potentially update last seen ID to what may be available when trying again, but never
                                    # below any processed message above (i.e., when last_seen_id > 0)
                                    # if protocol falsely returns "least":0 instead of omitting it on empty database,
                                    # we need to set our internal counter `last_seen_id` to 0 instead of -1
                                    last_seen_uuid_id[1] = max(response_json.get("least", 0) - 1, last_seen_uuid_id[1])
                            # if field "greatest" omitted, then database is empty, and we wait for new messages:
                            greatest = response_json.get("greatest", last_seen_uuid_id[1])
                        else:
                            self._logger.warning(f'Could not poll {entrypoint}; response code={response.status_code}')
                            greatest = last_seen_uuid_id[1]  # trigger wait time before trying again
            except httpx.RequestError as exc:
                self._logger.warning(f"Request Error with GET {exc.request.url!r} - trying again later")
                # TODO: fail if we cannot make connection for a certain time span (say 5 or 10 minutes)
                #  and then let PRISM Transport select new Bebo address (if no other links are working)

            await trio.sleep(max(1, self.configuration.get(polling_interval_setting)*60))
            # # reduce sleep time by elapsed seconds since started poll interval:
            # await trio.sleep(max(0, self.configuration.get(polling_interval_setting)*60 - (time() - start)))
