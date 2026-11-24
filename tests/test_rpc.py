"""JSON-RPC framing: fragmented, combined, and malformed protocol output."""
import json
import unittest

from tests import helpers  # noqa: F401  (adds the project root to sys.path)
from agent_hq.codex.rpc import LineFramer, classify


class FramingTests(unittest.TestCase):
    def test_single_message(self):
        f = LineFramer()
        self.assertEqual(f.feed(b'{"id":1,"result":{}}\n'), [{"id": 1, "result": {}}])

    def test_fragmented_message(self):
        f = LineFramer()
        raw = json.dumps({"method": "item/agentMessage/delta", "params": {"delta": "héllo wörld"}}).encode("utf-8") + b"\n"
        out = []
        for i in range(len(raw)):  # one byte at a time, including inside multi-byte UTF-8 sequences
            out += f.feed(raw[i:i + 1])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["params"]["delta"], "héllo wörld")
        self.assertEqual(f.malformed, 0)

    def test_combined_messages_in_one_chunk(self):
        f = LineFramer()
        chunk = b'{"method":"a"}\n{"method":"b"}\r\n\n{"id":7,"result":1}\n{"method":"c"'
        out = f.feed(chunk)
        self.assertEqual([m.get("method") or m.get("id") for m in out], ["a", "b", 7])
        self.assertEqual(f.feed(b"}\n"), [{"method": "c"}])

    def test_malformed_lines_are_skipped_not_raised(self):
        f = LineFramer()
        out = f.feed(b'not json\n{"broken": \n[1,2,3]\n"text"\n{"method":"ok"}\n')
        self.assertEqual(out, [{"method": "ok"}])
        self.assertEqual(f.malformed, 4)

    def test_classification(self):
        self.assertEqual(classify({"id": 1, "result": {}}), "response")
        self.assertEqual(classify({"id": 1, "error": {"code": -1, "message": "x"}}), "response")
        self.assertEqual(classify({"id": "srv-1", "method": "item/fileChange/requestApproval", "params": {}}), "request")
        self.assertEqual(classify({"method": "turn/completed", "params": {}}), "notification")
        self.assertEqual(classify({"foo": 1}), "invalid")


if __name__ == "__main__":
    unittest.main()
