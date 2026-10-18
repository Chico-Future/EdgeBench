from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.merge_transport_retry import is_transient_transport_error


class MergeTransportRetryTests(unittest.TestCase):
    def test_known_transient_transport_errors_are_accepted(self):
        self.assertTrue(
            is_transient_transport_error(
                "RuntimeError: transport_error:[SSL: UNEXPECTED_EOF_WHILE_READING]"
            )
        )
        self.assertTrue(
            is_transient_transport_error(
                "RemoteDisconnected: Remote end closed connection without response"
            )
        )
        self.assertTrue(
            is_transient_transport_error("ConnectionResetError: connection reset")
        )
        self.assertTrue(
            is_transient_transport_error("TimeoutError: The read operation timed out")
        )
        self.assertTrue(
            is_transient_transport_error(
                'RuntimeError: http_error:500:{"code":"InternalError","message":"h2 protocol error"}'
            )
        )

    def test_model_failures_are_not_transport_errors(self):
        self.assertFalse(is_transient_transport_error("max_steps_exceeded"))
        self.assertFalse(is_transient_transport_error("output_protocol_rejected"))
        self.assertFalse(is_transient_transport_error("RuntimeError: http_error:400:bad request"))
        self.assertFalse(is_transient_transport_error(None))


if __name__ == "__main__":
    unittest.main()
