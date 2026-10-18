from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloud.backend import OpenAICompatibleBackend


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        self.__class__.requests.append(payload)
        body = json.dumps(
            {
                "id": "local-test",
                "model": payload["model"],
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"mode":"execution","actions":[]}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return None


class CloudBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def backend(
        self, schema=None, request_extra=None, temperature=0.0, schema_transport=None
    ):
        return OpenAICompatibleBackend(
            base_url=f"http://127.0.0.1:{self.server.server_port}/v1",
            model="offline-test-model",
            api_key_env="",
            system_prompt="system",
            max_new_tokens=64,
            temperature=temperature,
            timeout=5,
            schema=schema,
            schema_transport=schema_transport,
            request_extra=request_extra,
        )

    def test_prompt_only_request_has_no_response_format(self):
        backend = self.backend()
        raw, telemetry = backend.start_case("user", "r1")
        self.assertIn("actions", raw)
        self.assertNotIn("response_format", Handler.requests[-1])
        self.assertEqual(15, telemetry["usage"]["total_tokens"])
        self.assertEqual(3, len(backend.messages))

    def test_optional_temperature_is_omitted(self):
        backend = self.backend(temperature=None)
        backend.start_case("user", "no-temperature")
        self.assertNotIn("temperature", Handler.requests[-1])

    def test_schema_defaults_to_prompt_transport(self):
        schema = {"type": "object", "properties": {}, "additionalProperties": False}
        backend = self.backend(schema)
        backend.start_case("user", "r2")
        request = Handler.requests[-1]
        self.assertNotIn("response_format", request)
        self.assertIn("JSON_SCHEMA=", request["messages"][-1]["content"])

    def test_prompt_schema_is_appended_without_response_format(self):
        schema = {
            "type": "object",
            "properties": {"mode": {"const": "answer"}},
            "required": ["mode"],
            "additionalProperties": False,
        }
        backend = self.backend(schema, schema_transport="prompt")
        backend.start_case("user payload", "prompt-schema")
        request = Handler.requests[-1]
        self.assertNotIn("response_format", request)
        self.assertIn("JSON_SCHEMA=", request["messages"][-1]["content"])
        self.assertIn('"additionalProperties":false', request["messages"][-1]["content"])
        self.assertEqual("user payload", backend.messages[1]["content"])

    def test_bailian_request_extra_is_sent_at_top_level(self):
        backend = self.backend(request_extra={"enable_thinking": False})
        backend.start_case("user", "r3")
        self.assertIs(False, Handler.requests[-1]["enable_thinking"])

    def test_request_extra_cannot_override_protocol_fields(self):
        with self.assertRaisesRegex(ValueError, "request_extra_reserved_keys"):
            self.backend(request_extra={"model": "wrong-model"})


if __name__ == "__main__":
    unittest.main()
