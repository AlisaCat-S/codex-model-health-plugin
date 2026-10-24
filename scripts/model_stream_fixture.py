"""发布冒烟使用的 HME1/GPE2 编码；由锁定 SDK 的解码测试校验。"""

import json
import struct


def encode_model_batch(payloads):
    events = []
    for original in payloads:
        payload = dict(original)
        field = {
            "json": "raw_sse", "web_socket": "message", "raw_sse": "frame",
            "raw_json": "body", "raw_body": "body",
        }[payload["kind"]]
        raw = b""
        if payload.get(field) is not None:
            # SDK decode 的 attach 要求元数据字节数组为空，原字节只能放在 wire 段。
            raw = bytes(payload[field])
            payload[field] = []
        metadata = json.dumps(
            {"wire": {"protocol": "openai", "payload": payload}},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        events.append(b"GPE2" + struct.pack(">III", len(metadata), len(raw), 0) + metadata + raw)
    return (b"HME1" + struct.pack(">I", len(events))
            + b"".join(struct.pack(">I", len(event)) for event in events)
            + b"".join(events))


def response_payload(data, mode):
    """同一 Responses 事件覆盖解析视图、原生 SSE 和两种 WS 形态。"""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if mode == "json":
        return {"kind": "json", "event": None, "data": data}
    if mode == "raw_sse":
        return {"kind": "raw_sse", "frame": b"data: " + raw + b"\n\n"}
    if mode in ("web_socket", "web_socket_text"):
        return {"kind": "web_socket", "event": None,
                "data": data if mode == "web_socket" else None, "message": raw}
    raise ValueError(f"unknown fixture mode: {mode}")
