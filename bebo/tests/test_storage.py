
#  Copyright (c) 2019-2023 SRI International.

import time

from bebo.storage import Storage
from bebo.protocol import RelayMessage as RM

m1 = RM(b'hi1')
m1a = RM(b'hi1')   # m1.message == m1a.message but m1 is not m1a
m2 = RM(b'hi2')
m3 = RM(b'hi3')
m4 = RM(b'hi4')
m5 = RM(b'hi5')

def test_add():
    db = Storage()
    assert db.least_sequence_number == 0
    (m, seqno) = db.add(m1)
    assert m is None
    assert seqno == 1
    assert db.contains(m1)
    assert db.get_by_key(m1.key()) is m1
    assert db.get_by_sequence_number(1) is m1
    assert db.get_message(m1a) is m1
    assert db.least_sequence_number == 1

def test_add_duplicate():
    db = Storage()
    db.add(m1)
    (m, seqno) = db.add(m1a)
    assert m is m1
    assert seqno == 1

def test_contains():
    db = Storage()
    db.add(m1)
    assert db.contains(m1a)    # containment is by ==, not is

def test_count_limit():
    db = Storage(2)
    db.add(m1)
    db.add(m2)
    assert db.contains(m1)
    assert db.contains(m2)
    assert db.least_sequence_number == 1
    db.add(m3)
    assert not db.contains(m1)
    assert db.contains(m2)
    assert db.contains(m3)
    db.add(m4)
    assert not db.contains(m1)
    assert not db.contains(m2)
    assert db.contains(m3)
    assert db.contains(m4)
    assert db.least_sequence_number == 3
    assert db.next_sequence_number == 5

def test_size_limit():
    db = Storage(100, 10)
    db.add(m1)
    db.add(m2)
    db.add(m3)
    assert db.contains(m1)
    assert db.contains(m2)
    assert db.contains(m3)
    assert db.size == 9
    db.add(m4)
    assert not db.contains(m1)
    assert db.contains(m2)
    assert db.contains(m3)
    assert db.contains(m4)
    assert db.size == 9
    assert db.least_sequence_number == 2
    assert db.next_sequence_number == 5

def test_age_limit():
    now = time.time()
    db = Storage(100, 10, 10)
    db.add(m1, 1)
    assert db.contains(m1)
    assert db.state() == {'least': 1, 'greatest': 1, 'uuid': db.uuid}
    db.add(m2, 400)
    assert db.state() == {'least': 2, 'greatest': 2, 'uuid': db.uuid}
    assert not db.contains(m1)
    assert db.contains(m2)
    db.purge(1000)
    assert not db.contains(m1)
    assert not db.contains(m2)
    assert db.state() == {'uuid': db.uuid}
    db.add(m3, 1001)
    assert db.state() == {'least': 3, 'greatest': 3, 'uuid': db.uuid}

def test_messages_for_id():
    db = Storage()
    db.add(m1)
    db.add(m2)
    messages = db.messages_for_id('id1')
    assert messages == [m1, m2]
    messages = db.messages_for_id('id1')
    assert messages == []
    db.add(m3)
    messages = db.messages_for_id('id1')
    assert messages == [m3]
    messages = db.messages_for_id('id2')
    assert messages == [m1, m2, m3]

def test_flush():
    db = Storage()
    uuid1 = db.uuid
    db.add(m1)
    db.add(m2)
    assert db.contains(m1)
    assert db.contains(m2)
    assert db.state() == {'least': 1, 'greatest': 2, 'uuid': uuid1}
    db.flush()
    uuid2 = db.uuid
    assert uuid1 != uuid2
    assert not db.contains(m1)
    assert not db.contains(m2)
    assert db.least_sequence_number == 0
    assert db.next_sequence_number == 1
    assert db.state() == {'uuid': uuid2}
    assert db.size == 0

def test_seen_are_purged():
    db = Storage(2)
    db.add(m1)
    db.add(m2)
    db.messages_for_id('id1')
    assert db.seen_by_id['id1'] == {m1.key(), m2.key()}
    db.add(m3)
    assert db.seen_by_id['id1'] == {m2.key()}

def test_get_range():
    db = Storage(4)
    db.add(m1)
    db.add(m2)
    db.add(m3)
    db.add(m4)
    db.add(m5)
    messages = db.get_range(1, 2)
    assert messages == [(2, m2)]
    messages = db.get_range(2, 3)
    assert messages == [(2, m2), (3, m3), (4, m4)]
    messages = db.get_range(100, 200)
    assert messages == []
