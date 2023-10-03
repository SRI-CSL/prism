#  Copyright (c) 2019-2023 SRI International.

import sys
from cbor2 import loads
from json import dumps
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from bebo.message import CBORFactory, PrismMessage

# Mapping of field names to labels for different message components.
# To add support for a new message component, add a key at the top level
# corresponding to the label that component would be found under (e.g. "Halfkey")
# with a dictionary containing that component's number->label mappings.
LABELS = {
    "PrismMessage": {
        0: "Version",
        1: "Message Type",
        2: "Message",
        3: "Cipher",
        4: "Ciphertext",
        5: "Halfkey",
        6: "Submessage",
        7: "Name",
        8: "Pseudonym",
        9: "Whiteboard Id",
        10: "Opaque Recipient",
        11: "Message Signature",
        12: "Dropbox Index",
        13: "Message Key Encryption Type",
        14: "Encrypted Message Key",
        15: "Hop Count",
        16: "Certificate",
        17: "Nonce",
        18: "CS Output",
        19: "Role",
        20: "Committee",
        21: "Expiration",
        22: "Origination Timestamp",
        23: "Keyshare",
        24: "Debug Info",
        25: "Servers",
        26: "Pad",
        27: "Minimum Transit Time",
        28: "Maximum Transit Time",
        29: "Sequence Number",
        30: "Max Rows",
        31: "Recipients",
        32: "Selected Messages",
        33: "Dropbox Mode",
        5000: "DEBUG: AES Key"
    },
    "Halfkey": {
        0: "Key Type",
        1: "DH_P",
        2: "DH_G",
        3: "DH_Q",
        4: "DH_Y",
        5: "ECDH Public Key"
    },
    "Debug Info": {
        0: "Trace",
        1: "Decryption Key",
        2: "Next Hop Name",
        3: "Tag"
    }
}

# As above, but for decoding enumerated values.
# Outer keys correspond to field labels, inner mappings correspond to enums.
ENUMS = {
    "Message Type": {
        0: "User Message",
        1: "ENC Emix Message",
        2: "Send to Dropbox",
        3: "Read Dropbox",
        4: "ARK",
        5: "ARK Response",
        6: "ENC User Message",
        7: "ENC Dropbox Message",
        8: "Write Dropbox",
        9: "Read Dropbox Recipients",
        10: "Read Dropbox Messages",
        11: "Dropbox Recipients",
        12: "Send to Emix"
    },
    "Key Type": {
        0: "DH",
        1: "ECDH"
    },
    "Cipher": {
        0: "AES-GCM"
    }
}

NONCE_FIELD = 17
DEBUG_INFO_FIELD = 24
DEBUG_KEY_FIELD = 1


def decrypt_submessage(outer_msg, submsg):
    """If the debug information is available, attempt to decrypt
    a sublayer of an outer message."""
    if DEBUG_INFO_FIELD not in outer_msg:
        return "Submessage"

    try:
        debug_info = outer_msg[DEBUG_INFO_FIELD]
        aes = AESGCM(debug_info[DEBUG_KEY_FIELD])
        plaintext = aes.decrypt(outer_msg[NONCE_FIELD], submsg, associated_data=None)
        submsg_dict = loads(plaintext)
        return relabel(submsg_dict)
    except:
        return "Decryption Failed"


def format_value(v, msg, label):
    """Reformat values to be human readable. This includes transforming byte strings
to hex, decoding submessages, and labeling sub-dicts."""
    if label == "Ciphertext":
        return decrypt_submessage(msg, v)

    if label == "Encrypted Message Key":
        return "IBE-Encoded Key"

    if(isinstance(v, bytes) or isinstance(v, bytearray)):
        return v.hex()

    if(isinstance(v, dict)):
        return relabel(v, label)

    if(isinstance(v, int) and label in ENUMS):
        return ENUMS[label][v]

    return v


def relabel(msg, msgtype="PrismMessage"):
    """Given a raw CBOR-decoded dict, and its type, rebuild it with human-readable
labels for fields and values."""
    global LABELS

    if msgtype == "Submessage":
        msgtype = "PrismMessage"

    local_labels = LABELS[msgtype]
    result = {}

    for k, v in msg.items():
        label = local_labels.get(k, k)
        value = format_value(v, msg, label)
        result[label] = value

    return result


def explain(bts):
    """Given a byte sequence, decode it as CBOR, and attempt to label its components."""
    # return relabel(loads(bts))  # TODO: instead of `relabel` call PrismMessage.__str__()?
    msg = PrismMessage.decode(bts)
    # return {"PrismMessage": str(msg)}
    return msg.repr_fields()

def kind(bts):
    m = loads(bts)
    return ENUMS['Message Type'][m[1]]

if __name__ == "__main__":
    import base64
    message = explain(base64.b64decode(sys.argv[1]))
    print(dumps(message, indent=4))

