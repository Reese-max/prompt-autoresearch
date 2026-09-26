# -*- coding: utf-8 -*-
"""Bounded local UI trust-boundary tests; no subprocess or provider is run."""

import http.client
import json
import threading
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import run_app


@contextmanager
def running_server():
    with run_app.create_server(0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=3)


def request(port, method, path, payload=None, *, origin=None, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    headers = {}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if origin is not None:
        headers["Origin"] = origin
    if host is not None:
        headers["Host"] = host
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class LocalUiSecurityTests(unittest.TestCase):
    def test_listener_is_loopback_and_read_route_remains_available(self):
        with running_server() as server:
            host, port = server.server_address
            self.assertEqual(host, "127.0.0.1")
            status, headers, body = request(port, "GET", "/api/latest-summary")
            self.assertEqual(status, 200)
            self.assertIn("content", json.loads(body))
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, headers, body = request(port, "GET", "/")
            self.assertEqual(status, 200)
            self.assertIn(
                "text/html", {name.lower(): value for name, value in headers.items()}["content-type"]
            )
            self.assertIn(b"<html", body.lower())

    def test_remote_peer_rebinding_host_and_foreign_origin_are_denied(self):
        port = 8000
        self.assertTrue(run_app.local_request_allowed(
            "127.0.0.1", "127.0.0.1:8000", "http://127.0.0.1:8000", port
        ))
        self.assertTrue(run_app.local_request_allowed(
            "127.0.0.1", "localhost:8000", "http://localhost:8000", port
        ))
        self.assertFalse(run_app.local_request_allowed(
            "192.0.2.10", "127.0.0.1:8000", None, port
        ))
        self.assertFalse(run_app.local_request_allowed(
            "127.0.0.1", "attacker.example:8000", None, port
        ))
        self.assertFalse(run_app.local_request_allowed(
            "127.0.0.1", "127.0.0.1:8000", "https://attacker.example", port
        ))
        self.assertFalse(run_app.local_request_allowed(
            "127.0.0.1", "127.0.0.1:8000", "null", port
        ))
        self.assertFalse(run_app.local_request_allowed(
            "127.0.0.1", "127.0.0.1:8000", "", port
        ))
        with running_server() as server:
            port = server.server_address[1]
            status, headers, _ = request(
                port, "GET", "/api/latest-summary", host=f"attacker.example:{port}"
            )
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, _, _ = request(
                port, "HEAD", "/", origin="https://attacker.example"
            )
            self.assertEqual(status, 403)

    def test_foreign_origin_has_zero_mutation_side_effects(self):
        with running_server() as server, \
             mock.patch.object(run_app.subprocess, "Popen") as popen, \
             mock.patch.object(run_app.urllib.request, "urlopen") as urlopen, \
             mock.patch.object(run_app.os, "makedirs") as makedirs:
            port = server.server_address[1]
            cases = (
                ("/api/run-evolution", {"generations": 1}),
                ("/api/run-final", {"parallel": 1}),
                ("/api/proxy", {
                    "url": "https://api.openai.com/v1/test",
                    "headers": {}, "body": {},
                }),
            )
            for path, payload in cases:
                with self.subTest(path=path):
                    status, headers, _ = request(
                        port, "POST", path, payload,
                        origin="https://attacker.example",
                    )
                    self.assertEqual(status, 403)
                    self.assertNotIn("Access-Control-Allow-Origin", headers)
            status, _, _ = request(
                port, "POST", "/api/run-evolution", {"generations": 1},
                host=f"attacker.example:{port}",
            )
            self.assertEqual(status, 403)
            status, headers, _ = request(
                port, "OPTIONS", "/api/run-evolution",
                origin="https://attacker.example",
            )
            self.assertEqual(status, 403)
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            popen.assert_not_called()
            urlopen.assert_not_called()
            makedirs.assert_not_called()

    def test_local_ui_mutations_work_and_proxy_allowlist_stays_in_force(self):
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        with running_server() as server, \
             mock.patch.object(run_app.subprocess, "Popen", return_value=SimpleNamespace(pid=123)) as popen, \
             mock.patch.object(run_app.urllib.request, "urlopen", return_value=response) as urlopen, \
             mock.patch.object(run_app.os, "makedirs"), \
             mock.patch.object(run_app, "open", mock.mock_open(), create=True):
            port = server.server_address[1]
            origin = f"http://127.0.0.1:{port}"
            status, _, body = request(
                port, "POST", "/api/run-evolution",
                {"generations": 1}, origin=origin,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["status"], "started")
            status, _, body = request(
                port, "POST", "/api/run-final",
                {"parallel": 1}, origin=origin,
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["status"], "started")
            self.assertEqual(popen.call_count, 2)
            status, _, body = request(
                port, "POST", "/api/proxy",
                {"url": "https://api.openai.com/v1/test", "headers": {}, "body": {}},
                origin=origin,
            )
            self.assertEqual(status, 200)
            self.assertEqual(body, b'{"ok":true}')
            urlopen.assert_called_once()
            status, _, _ = request(
                port, "POST", "/api/proxy",
                {"url": "https://attacker.example/v1/test", "headers": {}, "body": {}},
                origin=origin,
            )
            self.assertEqual(status, 403)
            urlopen.assert_called_once()
            status, headers, _ = request(
                port, "OPTIONS", "/api/proxy", origin=origin
            )
            self.assertEqual(status, 204)
            self.assertNotIn("Access-Control-Allow-Origin", headers)


if __name__ == "__main__":
    unittest.main()
