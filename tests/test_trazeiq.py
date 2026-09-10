"""Stdlib-only tests for the trazeiq Python SDK (run: python -m unittest)."""

import functools
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import trazeiq
from trazeiq import _reset_for_tests


class _Handler(BaseHTTPRequestHandler):
    requests = []
    status = 201

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        type(self).requests.append(
            {
                "path": self.path,
                "api_key": self.headers.get("X-API-Key"),
                "body": body,
            }
        )
        payload = json.dumps({"success": True}).encode()
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # silence test output
        pass


def _serve():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class SdkTests(unittest.TestCase):
    def setUp(self):
        _reset_for_tests()
        _Handler.requests = []
        _Handler.status = 201
        self.server = _serve()
        self.base = (
            f"http://127.0.0.1:{self.server.server_address[1]}"
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        _reset_for_tests()

    def test_init_requires_api_key(self):
        with self.assertRaises(ValueError):
            trazeiq.init(api_key="")

    def test_capture_message_posts_api_key_and_shape(self):
        trazeiq.init(
            api_key="test-key",
            endpoint=self.base,
            environment="production",
            service="payment-api",
        )
        trazeiq.capture_message("boom", level="fatal", metadata={"a": 1})
        self.assertEqual(len(_Handler.requests), 1)
        req = _Handler.requests[0]
        self.assertEqual(req["path"], "/api/v1/events/")
        self.assertEqual(req["api_key"], "test-key")
        payload = json.loads(req["body"])
        self.assertEqual(payload["message"], "boom")
        self.assertEqual(payload["level"], "fatal")
        self.assertEqual(payload["environment"], "production")
        self.assertEqual(payload["service"], "payment-api")
        self.assertEqual(payload["metadata"], {"a": 1})

    def test_capture_exception_uses_active_exception(self):
        trazeiq.init(api_key="k", endpoint=self.base)
        try:
            raise RuntimeError("kaput")
        except RuntimeError:
            trazeiq.capture_exception(service="svc")
        payload = json.loads(_Handler.requests[0]["body"])
        self.assertEqual(payload["message"], "kaput")
        self.assertIn("kaput", payload["stacktrace"])
        self.assertIn("RuntimeError", payload["stacktrace"])
        self.assertEqual(payload["level"], "error")
        self.assertEqual(payload["service"], "svc")

    def test_user_and_breadcrumbs_stamped(self):
        trazeiq.init(api_key="k", endpoint=self.base)
        trazeiq.set_user("user-1")
        trazeiq.add_breadcrumb({"message": "clicked checkout"})
        trazeiq.capture_message("hi")
        payload = json.loads(_Handler.requests[0]["body"])
        self.assertEqual(payload["user_id"], "user-1")
        self.assertEqual(len(payload["breadcrumbs"]), 1)
        trazeiq.clear_breadcrumbs()
        trazeiq.capture_message("hi2")
        self.assertEqual(
            len(json.loads(_Handler.requests[1]["body"])["breadcrumbs"]), 0
        )

    def test_transport_failures_never_raise(self):
        trazeiq.init(
            api_key="k", endpoint="http://127.0.0.1:1", timeout_seconds=0.5
        )
        trazeiq.capture_message("unreachable")  # must not raise
        try:
            raise ValueError("unreachable")
        except ValueError as exc:
            trazeiq.capture_exception(exc)  # must not raise
        trazeiq.flush()

    def test_close_disables_and_wrap_reraises(self):
        trazeiq.init(api_key="k", endpoint=self.base)
        trazeiq.close()
        trazeiq.capture_message("silent")
        self.assertEqual(len(_Handler.requests), 0)

        _reset_for_tests()
        trazeiq.init(api_key="k", endpoint=self.base)

        @trazeiq.wrap(service="svc")
        def failing():
            raise RuntimeError("wrapped")

        with self.assertRaises(RuntimeError):
            failing()
        self.assertEqual(len(_Handler.requests), 1)


if __name__ == "__main__":
    unittest.main()
