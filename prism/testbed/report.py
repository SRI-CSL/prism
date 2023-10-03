#  Copyright (c) 2019-2023 SRI International.

from datetime import timedelta, datetime, date
from typing import List

import trio

from prism.testbed.client import TestMessage


def serialize_test_object(obj):
    """JSON serializer for datetime objects."""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()

    try:
        return obj.to_json()
    except Exception:
        raise TypeError(f"Type {type(obj)} is not JSON serializable")


def drain_queue(results: dict, q: trio.MemoryReceiveChannel):
    try:
        while True:
            evt = q.receive_nowait()
            results[evt['event']].append(evt)

            if not results['by_message'].get(evt['message']):
                results['by_message'][evt['message']] = []

            results['by_message'][evt['message']].append(evt)
    except trio.WouldBlock:
        return


def generate_report(results):
    test_messages: List[TestMessage] = results['test_messages']
    anomalies = []
    latencies = []
    average_latency = None
    drops = 0

    for test_message in test_messages:
        message = test_message.message
        if message.message not in results['by_message']:
            anomalies.append({
                'message': message,
                'anomaly': 'NOT_SENT_OR_RECEIVED'
            })
            continue

        history = results['by_message'][message.message]

        sends = [evt for evt in history if evt['event'] == 'send']
        receives = [evt for evt in history if evt['event'] == 'receive']

        if len(sends) == 0:
            anomalies.append({
                'message': message,
                'anomaly': 'RECEIVED_BUT_NOT_SENT'
            })
            continue
        if len(sends) > 1:
            anomalies.append({
                'message': message,
                'anomaly': 'MULTIPLE_SENDS',
                'count': len(sends)
            })

        if len(receives) == 0:
            anomalies.append({
                'message': message,
                'anomaly': 'DROPPED'
            })
            drops += 1
            continue
        elif len(receives) > 1:
            anomalies.append({
                'message': message,
                'anomaly': 'DUPLICATED'
            })

        delay = receives[0]['time'] - sends[0]['time']

        latencies.append({
            'sender': message.sender,
            'receiver': message.receiver,
            'delay': delay
        })

    if len(latencies) > 0:
        average_latency = sum([transit['delay'] for transit in latencies], timedelta()) / len(latencies)
        average_latency = average_latency.total_seconds()

    return {
        'anomalies': anomalies,
        'average_latency': average_latency,
        'received': len(results['receive']),
        'sent': len(results['send']),
        'dropped': drops,
        'errors': len(results['error'])
    }


def present(report):
    print(report)
