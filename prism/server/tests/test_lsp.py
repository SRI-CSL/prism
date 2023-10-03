#  Copyright (c) 2019-2023 SRI International.
import heapq
import time

from prism.server.communication.ls_database import ExpirationElement
from prism.server.communication.ls_queue import QItem, PrioritizedQItem


# async def test_non_priority():
#     async with trio.open_nursery() as nursery:
#         send_ch, recv_ch = trio.open_memory_channel(math.inf)
#         with send_ch, recv_ch:
#             q = LSQueue(QType.SEND, send_ch)
#             await q.insert_item(QItem(b'n1', b'o1'))
#             await q.insert_item(QItem(b'n2', b'o2'))
#             await q.insert_item(QItem(b'n3', b'o3'))
#             await q.remove_item(QItem(b'n2', b'o2'))
#             nursery.start_soon(q.rate_limited_processing)
#             async for _, neighbor, originator in recv_ch:
#                 print(f'{neighbor}, {originator}')


def test_items():
    qi = QItem(b'n2', b'o2')
    pi1 = PrioritizedQItem(b'n1', b'o1', 1.3)
    pi2 = PrioritizedQItem(b'n2', b'o2', 0.3)
    assert pi2 < pi1
    h = [pi1, pi2]
    index = h.index(PrioritizedQItem(b'n1', b'o1', 1.3))
    assert index == 0
    # test customized equality:
    assert pi2 == PrioritizedQItem(b'n2', b'o2', 0)
    index = h.index(qi)
    assert index == 1


def test_expirations():
    now = time.time()
    ei1 = ExpirationElement(now + 5, b'one')
    ei2 = ExpirationElement(now + 2, b'two')
    ei3 = ExpirationElement(now + 10, b'three')
    my_expirations = [ei1, ei2, ei3]
    assert my_expirations[0] == ei1
    heapq.heapify(my_expirations)
    assert my_expirations[0] == ei2
    my_expirations.remove(ExpirationElement(0, b'one'))
    assert len(my_expirations) == 2
    assert my_expirations[1] == ei3

    # pm = PrismMessage(msg_type=TypeEnum.LSP, originator=b'me')
    # lsp_db = LSDatabase()
    # existing = await lsp_db.update(ei1)
    # assert not existing


