"""Testes de seguranca do servidor HTTP local (app_server.py)."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import safepckids.app_server as app_server
from safepckids.app_server import (
    API_SESSION_TOKEN,
    MAX_POST_BODY_BYTES,
    SafePCKidsApiHandler,
)
from safepckids.storage import Storage


class TestAppServerSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SafePCKidsApiHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass

    def setUp(self):
        with SafePCKidsApiHandler._pin_rate_lock:
            SafePCKidsApiHandler._pin_failures.clear()
            SafePCKidsApiHandler._pin_lockouts.clear()

    def _request(self, method: str, path: str, body: bytes | None = None,
                 headers: dict[str, str] | None = None) -> tuple[int, dict, bytes]:
        req_headers = dict(headers or {})
        if body is not None and "Content-Type" not in req_headers:
            req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=req_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_non_loopback_client_blocked_from_admin_routes(self):
        handler = SafePCKidsApiHandler.__new__(SafePCKidsApiHandler)
        handler.client_address = ("192.168.1.50", 54321)
        handler.path = "/api/settings/pin"
        handler.headers = {}
        sent = []
        handler.send_json = lambda data, status=200: sent.append((status, data))

        self.assertFalse(handler._check_request_security("/api/settings/pin"))
        self.assertEqual(sent[0][0], 403)
        self.assertFalse(sent[0][1]["ok"])

    def test_non_loopback_client_allowed_on_remote_routes(self):
        handler = SafePCKidsApiHandler.__new__(SafePCKidsApiHandler)
        handler.client_address = ("192.168.1.50", 54321)
        handler.headers = {}
        for route in ("/remote", "/api/remote/status", "/api/remote/pause", "/api/child/1/avatar"):
            handler.path = route
            self.assertTrue(handler._check_request_security(route), f"Rota remota deveria ser permitida: {route}")

    def test_cross_site_origin_and_referer_blocked_on_admin_routes(self):
        status, _, raw = self._request(
            "GET",
            "/api/dashboard",
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertFalse(json.loads(raw)["ok"])

        status_ref, _, _ = self._request(
            "POST",
            "/api/settings/pin",
            body=b'{"pin":"9999"}',
            headers={"Referer": "https://evil.example/attack.html"},
        )
        self.assertEqual(status_ref, 403)

    def test_admin_cors_does_not_return_wildcard(self):
        status, headers, _ = self._request(
            "GET",
            "/api/heartbeat",
            headers={"Origin": f"http://127.0.0.1:{self.port}"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), f"http://127.0.0.1:{self.port}")
        self.assertNotEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_invalid_api_token_rejected_and_required_mode_enforced(self):
        status, _, raw = self._request(
            "GET",
            "/api/dashboard",
            headers={"X-Session-Token": "token-invalido"},
        )
        self.assertEqual(status, 403)
        self.assertFalse(json.loads(raw)["ok"])

        with patch.object(SafePCKidsApiHandler, "require_api_token", True):
            status_missing, _, _ = self._request("GET", "/api/dashboard")
            self.assertEqual(status_missing, 403)

            status_ok, _, _ = self._request(
                "GET",
                "/api/heartbeat",
            )
            self.assertEqual(status_ok, 200)

            with patch.object(app_server, "DEFAULT_DB_FILE", Path(tempfile.gettempdir()) / "nonexistent_sec.sqlite3"):
                status_auth, _, _ = self._request(
                    "GET",
                    "/api/dashboard",
                    headers={"X-Session-Token": SafePCKidsApiHandler.session_token},
                )
                self.assertEqual(status_auth, 200)

    def test_path_traversal_blocked_on_assets_and_ui(self):
        for bad_path in (
            "/assets/../../pyproject.toml",
            "/assets/%2e%2e/%2e%2e/pyproject.toml",
            "/ui/../../pyproject.toml",
            "/ui/%2e%2e/app_server.py",
        ):
            status, _, _ = self._request("GET", bad_path)
            self.assertEqual(status, 403, f"Esperava 403 para {bad_path}, veio {status}")

    def test_app_html_injects_api_token_only_for_loopback(self):
        status, _, raw = self._request("GET", "/")
        self.assertEqual(status, 200)
        html = raw.decode("utf-8", errors="replace")
        self.assertIn("window.__SAFEPCKIDS_TOKEN__", html)
        self.assertIn(SafePCKidsApiHandler.session_token, html)

    def test_post_rejects_invalid_or_oversized_content_length(self):
        tok_headers = {"X-SafePCKids-Token": SafePCKidsApiHandler.session_token}
        status_neg, _, _ = self._request(
            "POST",
            "/api/auth/verify",
            body=b"",
            headers={"Content-Length": "-5", **tok_headers},
        )
        self.assertEqual(status_neg, 400)

        status_big, _, _ = self._request(
            "POST",
            "/api/auth/verify",
            body=b"{}",
            headers={"Content-Length": str(MAX_POST_BODY_BYTES + 1), **tok_headers},
        )
        self.assertEqual(status_big, 413)

        status_bad_json, _, _ = self._request(
            "POST",
            "/api/auth/verify",
            body=b"{not-json",
            headers=tok_headers,
        )
        self.assertEqual(status_bad_json, 400)

    def test_pin_rate_limit_triggers_after_consecutive_failures(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "sec.sqlite3"
            store = Storage(db_path)
            store.set_parent_pin("4321")
            store.close()

            tok_headers = {"X-SafePCKids-Token": SafePCKidsApiHandler.session_token}
            with patch.object(app_server, "DEFAULT_DB_FILE", db_path):
                for _ in range(app_server.PIN_MAX_FAILURES):
                    st, _, raw = self._request(
                        "POST",
                        "/api/auth/verify",
                        body=b'{"pin":"0000"}',
                        headers=tok_headers,
                    )
                    self.assertEqual(st, 200)
                    self.assertFalse(json.loads(raw)["ok"])

                st_locked, _, raw_locked = self._request(
                    "POST",
                    "/api/auth/verify",
                    body=b'{"pin":"4321"}',
                    headers=tok_headers,
                )
                self.assertEqual(st_locked, 429)
                self.assertFalse(json.loads(raw_locked)["ok"])


if __name__ == "__main__":
    unittest.main()
