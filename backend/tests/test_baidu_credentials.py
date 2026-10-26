import base64
import contextlib
import hashlib
import hmac
import importlib
import io
import json
import os
import sys
import types
import unittest
from unittest.mock import patch
from nkcn_public_config import redact, validate_public_config

class BaiduCredentialTests(unittest.TestCase):
    def setUp(self):
        ocr = types.ModuleType("llm_langchain.pdf_ocr_utils")
        ocr.extract_and_save_images_from_ocr = lambda *args, **kwargs: None
        self.modules = patch.dict(sys.modules, {"llm_langchain.pdf_ocr_utils": ocr})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        with contextlib.redirect_stdout(io.StringIO()):
            self.module = importlib.import_module("app_chat.baidu_trans_doc")

    def test_import_and_construction_do_not_require_optional_credentials(self):
        with contextlib.redirect_stdout(io.StringIO()):
            module = importlib.reload(self.module)
        self.assertEqual(module.trans_obj.appid, "")
        self.assertEqual(module.trans_obj.seckey, "")

    def test_reads_environment_without_hardcoded_fallback(self):
        with patch.dict(os.environ, {
                "BAIDU_TRANS_APPID": "unit-baidu-app",
                "BAIDU_TRANS_SECKEY": "unit-baidu-signing-secret"}):
            client = self.module.Translate()
        self.assertEqual(client.appid, "unit-baidu-app")
        self.assertEqual(client.seckey, "unit-baidu-signing-secret")

    def test_missing_either_value_fails_before_files_or_network(self):
        calls = [
            ("create_quote_job", ("en", "zh", "pdf", "unit.pdf", "unused.pdf")),
            ("query_quote", ("unit-file",)),
            ("create_trans_job", ("en", "zh", "pdf", "unit.pdf", "unused.pdf")),
            ("query_trans", ("unit-job",)),
            ("create_sign", (123, {})),
        ]
        for provided in [{"BAIDU_TRANS_APPID": "unit-baidu-app"},
                         {"BAIDU_TRANS_SECKEY": "unit-baidu-signing-secret"}]:
            with self.subTest(provided=list(provided)), patch.dict(os.environ, provided, clear=True):
                client = self.module.Translate()
                with patch.object(self.module.requests, "post") as post, patch("builtins.open") as opened:
                    for method, args in calls:
                        with self.assertRaisesRegex(ValueError, "BAIDU_TRANS_APPID") as caught:
                            getattr(client, method)(*args)
                        self.assertNotIn("unit-baidu-signing-secret", str(caught.exception))
                    post.assert_not_called()
                    opened.assert_not_called()

    def test_signature_and_headers_keep_provider_protocol(self):
        with patch.dict(os.environ, {
                "BAIDU_TRANS_APPID": "unit-baidu-app",
                "BAIDU_TRANS_SECKEY": "unit-baidu-signing-secret"}):
            client = self.module.Translate()
        payload = {"from": "en", "to": "zh", "input": {"filename": "unit.pdf"}}
        timestamp = 123456
        canonical = "unit-baidu-app" + str(timestamp) + json.dumps(payload)
        expected = base64.b64encode(hmac.new(b"unit-baidu-signing-secret",
                                             canonical.encode(), hashlib.sha256).digest())
        signature = client.create_sign(timestamp, payload)
        self.assertEqual(signature, expected)
        headers = client.create_headers(timestamp, signature)
        self.assertEqual(headers["X-Appid"], "unit-baidu-app")
        self.assertEqual(headers["X-Sign"], expected)
        self.assertEqual(headers["X-Timestamp"], str(timestamp))
        self.assertNotIn("unit-baidu-signing-secret", str(headers))

    def test_query_preserves_response_contract_without_network(self):
        with patch.dict(os.environ, {
                "BAIDU_TRANS_APPID": "unit-baidu-app",
                "BAIDU_TRANS_SECKEY": "unit-baidu-signing-secret"}):
            client = self.module.Translate()
        response = types.SimpleNamespace(text='{"status":"unit-ready"}')
        with patch.object(self.module.requests, "post", return_value=response) as post:
            self.assertEqual(client.query_quote("unit-file"), response.text)
            self.assertEqual(post.call_args.kwargs["json"], {"fileId": "unit-file"})
            self.assertNotIn("unit-baidu-signing-secret", str(post.call_args))

    def test_seckey_is_redacted_and_cannot_be_persisted_as_plaintext(self):
        data = {"nested": [{"seckey": "unit-baidu-signing-secret"}]}
        self.assertEqual(redact(data)["nested"][0]["seckey"], "[redacted]")
        with self.assertRaises(ValueError):
            validate_public_config(data)
        validate_public_config({"seckey": "env:BAIDU_TRANS_SECKEY"})

if __name__ == "__main__":
    unittest.main()
