"""离线冒烟宿主的 RPC v7 帧和单次调用调度；帧样本由 Rust SDK 交叉校验。"""

import json
import struct

PROTOCOL_VERSION = 7


def encode_frame(message, payload=b""):
    message = dict(message)
    data = b""
    kind = message["type"]
    if kind == "hello":
        message["handshake"] = dict(message["handshake"])
        value = message["handshake"].pop("configuration")
    elif kind in ("call", "callback"):
        value = message.pop("params")
    elif kind == "result":
        value = message.pop("result")
    else:
        value = None
    if kind in ("hello", "call", "callback", "result"):
        data = json.dumps(value, separators=(",", ":")).encode()
        message["data_bytes"] = len(data)
    meta = json.dumps(message, separators=(",", ":")).encode()
    return struct.pack(">IQ", len(meta), len(data) + len(payload)) + meta + data + payload


def decode_frame(meta, payload):
    message = json.loads(meta)
    assert message.pop("request_context_bytes", 0) == 0, "冒烟宿主不下发入口请求快照"
    length = message.pop("data_bytes", 0)
    assert 0 <= length <= len(payload)
    data, payload = payload[:length], payload[length:]
    if length:
        kind = message["type"]
        value = json.loads(data)
        if kind == "hello":
            message["handshake"]["configuration"] = value
        elif kind in ("call", "callback"):
            message["params"] = value
        else:
            assert kind == "result", message
            message["result"] = value
    return message, payload


class CallSchedule:
    """即使回调已返回，也要等 Resume 后授权；消费通知才释放驻留结果。"""

    def __init__(self, parent_id):
        self.parent_id = parent_id
        self.epoch = 0
        self.suspended = False
        self.resident = set()

    def observe(self, message, payload=b""):
        kind = message["type"]
        if kind == "callback":
            assert not self.suspended and message["parent_id"] == self.parent_id
            assert message["id"] not in self.resident
            self.resident.add(message["id"])
        elif kind == "suspend":
            assert not payload and not self.suspended
            assert message["id"] == self.parent_id and message["epoch"] == self.epoch + 1
            self.epoch = message["epoch"]
            self.suspended = True
        elif kind == "resume":
            assert not payload and self.suspended
            assert (message["id"], message["epoch"]) == (self.parent_id, self.epoch)
            self.suspended = False
            return {"type": "resumed", "id": self.parent_id, "epoch": self.epoch}
        elif kind == "callback_consumed":
            assert not payload and not self.suspended
            assert message["parent_id"] == self.parent_id
            self.resident.remove(message["id"])
        elif kind == "result":
            assert message["id"] == self.parent_id and not self.suspended and not self.resident
        else:
            raise AssertionError(f"unexpected RPC v7 message: {message}")
