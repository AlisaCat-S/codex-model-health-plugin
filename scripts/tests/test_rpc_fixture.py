import copy
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rpc_fixture import PROTOCOL_VERSION, CallSchedule, decode_frame, encode_frame


class RpcFixtureTests(unittest.TestCase):
    def test_frames_match_sdk_checked_fixture_without_mutating_inputs(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/rpc-v7.json").read_text(encoding="utf-8"))
        self.assertEqual(PROTOCOL_VERSION, 7)
        for fixture in fixtures:
            message = copy.deepcopy(fixture["message"])
            payload = fixture["payload"].encode()
            encoded = encode_frame(message, payload)
            self.assertEqual(message, fixture["message"])
            self.assertEqual(encoded.hex(), fixture["frame_hex"])
            meta, total = struct.unpack(">IQ", encoded[:12])
            self.assertEqual(total, len(encoded) - 12 - meta)
            self.assertEqual(decode_frame(encoded[12:12+meta], encoded[12+meta:]), (message, payload))

    def test_each_epoch_requires_a_resume_and_consumption_releases_resident_result(self):
        call = CallSchedule(1)
        for epoch in (1, 2):
            child = epoch * 2
            call.observe({"type": "callback", "id": child, "parent_id": 1})
            call.observe({"type": "suspend", "id": 1, "epoch": epoch})
            self.assertIn(child, call.resident)
            grant = call.observe({"type": "resume", "id": 1, "epoch": epoch})
            self.assertEqual(grant, {"type": "resumed", "id": 1, "epoch": epoch})
            self.assertIn(child, call.resident)
            call.observe({"type": "callback_consumed", "id": child, "parent_id": 1})
        call.observe({"type": "result", "id": 1})

    def test_invalid_control_or_premature_result_is_rejected(self):
        for message in (
            {"type": "resume", "id": 1, "epoch": 1},
            {"type": "suspend", "id": 1, "epoch": 2},
            {"type": "suspend", "id": 3, "epoch": 1},
        ):
            with self.assertRaises(AssertionError):
                CallSchedule(1).observe(message)
        call = CallSchedule(1)
        call.observe({"type": "callback", "id": 2, "parent_id": 1})
        with self.assertRaises(AssertionError):
            call.observe({"type": "result", "id": 1})
        call.observe({"type": "suspend", "id": 1, "epoch": 1})
        with self.assertRaises(AssertionError):
            call.observe({"type": "callback_consumed", "id": 2, "parent_id": 1})
        with self.assertRaises(AssertionError):
            call.observe({"type": "resume", "id": 1, "epoch": 1}, b"unexpected payload")


if __name__ == "__main__":
    unittest.main()
