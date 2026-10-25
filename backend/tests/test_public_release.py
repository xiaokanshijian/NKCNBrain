import base64
import contextlib
import hashlib
import hmac
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.conf import settings
if not settings.configured:
    settings.configure(DEFAULT_CHARSET="utf-8")
from django.test import RequestFactory
from app_chat.voice_session import voice_session
from nkcn_public_config import secret, required, redact, validate_public_config

class VoiceSessionTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def request(self, service="iat", authenticated=True, method="get"):
        req = getattr(self.factory, method)("/api/voice/session", {"service": service})
        req.user = SimpleNamespace(is_authenticated=authenticated)
        return voice_session(req)

    def test_anonymous_cannot_obtain_signed_url(self):
        self.assertEqual(self.request(authenticated=False).status_code, 401)

    def test_unconfigured_service_fails_without_secret_details(self):
        response = self.request()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"api_secret", response.content)

    def test_arbitrary_service_and_host_are_rejected(self):
        self.assertEqual(self.request("https://attacker.example").status_code, 400)

    def test_post_is_not_supported(self):
        self.assertEqual(self.request(method="post").status_code, 405)

    def test_signature_is_vendor_specific_and_secret_is_not_returned(self):
        for service, host, path in [("iat", "iat-api.xfyun.cn", "/v2/iat"),
                                    ("tts", "tts-api.xfyun.cn", "/v2/tts")]:
            with self.subTest(service=service), patch.dict(os.environ, {
                    "XFYUN_APP_ID": "unit-app", "XFYUN_API_KEY": "unit-key",
                    "XFYUN_API_SECRET": "unit-secret"}):
                response = self.request(service)
                self.assertEqual(response.status_code, 200)
                data = json.loads(response.content)
                parsed = urlsplit(data["url"])
                self.assertEqual((parsed.scheme, parsed.hostname, parsed.path), ("wss", host, path))
                query = parse_qs(parsed.query)
                auth = base64.b64decode(query["authorization"][0]).decode()
                canonical = f"host: {host}\ndate: {query['date'][0]}\nGET {path} HTTP/1.1"
                expected = base64.b64encode(hmac.new(b"unit-secret", canonical.encode(), hashlib.sha256).digest()).decode()
                self.assertIn(f'signature="{expected}"', auth)
                self.assertNotIn("unit-secret", auth)
                self.assertNotIn("unit-secret", response.content.decode())
                self.assertIn("no-store", response["Cache-Control"])

class ConfigurationTests(unittest.TestCase):
    def test_missing_credential_has_no_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(secret("UNCONFIGURED_TEST_CREDENTIAL"), "")
            with self.assertRaisesRegex(ValueError, "UNCONFIGURED_TEST_CREDENTIAL"):
                required("UNCONFIGURED_TEST_CREDENTIAL")

    def test_recursive_log_redaction_does_not_mutate_original(self):
        payload = {"models": [{"api_key": "unit-secret", "name": "demo"}]}
        clean = redact(payload)
        self.assertEqual(clean["models"][0]["api_key"], "[redacted]")
        self.assertEqual(payload["models"][0]["api_key"], "unit-secret")
        self.assertEqual(clean["models"][0]["name"], "demo")

    def test_persisted_configs_accept_refs_and_reject_plaintext(self):
        validate_public_config({"config": {"openai_api_key": "env:UNIT_PROVIDER_KEY"}})
        with self.assertRaises(ValueError):
            validate_public_config({"config": {"openai_api_key": "unit-secret"}})
        with self.assertRaises(ValueError):
            validate_public_config({"config": {"openai_api_key": "env:bad-name"}})

    def test_config_save_uses_reference_and_runtime_uses_resolved_value(self):
        with contextlib.redirect_stdout(io.StringIO()):
            module = importlib.import_module("app_chat.config.config_manager")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"UNIT_PROVIDER_KEY": "unit-secret"}):
            manager = module.ConfigManager(temp)
            payload = {"abbr_name": "unit-model", "config": {"openai_api_key": "env:UNIT_PROVIDER_KEY"}}
            with patch.object(module, "ModelConfig", side_effect=lambda x: x), contextlib.redirect_stdout(io.StringIO()) as output:
                manager.add_new_model_config(payload)
            saved = (Path(temp) / "unit-model.json").read_text(encoding="utf-8")
            self.assertIn("env:UNIT_PROVIDER_KEY", saved)
            self.assertNotIn("unit-secret", saved)
            self.assertNotIn("unit-secret", output.getvalue())
            self.assertEqual(manager.configs["unit-model"]["config"]["openai_api_key"], "unit-secret")
            self.assertEqual(payload["config"]["openai_api_key"], "env:UNIT_PROVIDER_KEY")

    def test_rejected_plaintext_does_not_create_a_config_file(self):
        with contextlib.redirect_stdout(io.StringIO()):
            module = importlib.import_module("app_chat.config.config_manager")
        with tempfile.TemporaryDirectory() as temp:
            manager = module.ConfigManager(temp)
            with self.assertRaises(ValueError):
                manager.add_new_model_config({"abbr_name": "blocked", "config": {"api_key": "unit-secret"}})
            self.assertEqual(list(Path(temp).iterdir()), [])

if __name__ == "__main__":
    unittest.main()
