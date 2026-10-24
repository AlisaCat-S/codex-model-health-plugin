import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_stream_fixture import encode_model_batch, response_payload


class ModelStreamFixtureTests(unittest.TestCase):
    def test_encoding_matches_sdk_checked_fixture(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/model-events.json").read_text(encoding="utf-8"))
        self.assertEqual(encode_model_batch(fixture["payloads"]).hex(), fixture["batch_hex"])

    def test_all_release_modes_preserve_the_response(self):
        data = {"type": "response.output_text.delta", "delta": "加拿大"}
        for mode in ("json", "raw_sse", "web_socket", "web_socket_text"):
            payload = response_payload(data, mode)
            if mode == "raw_sse":
                self.assertEqual(json.loads(payload["frame"][6:-2]), data)
            elif mode.startswith("web_socket"):
                self.assertEqual(json.loads(payload["message"]), data)
                self.assertEqual(payload["data"], data if mode == "web_socket" else None)
            else:
                self.assertEqual(payload["data"], data)
            self.assertTrue(encode_model_batch([payload]).startswith(b"HME1"))


if __name__ == "__main__":
    unittest.main()
