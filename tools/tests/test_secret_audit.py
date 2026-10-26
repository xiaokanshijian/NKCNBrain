import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secret_audit import scan_file, scan_history

class SecretAuditTests(unittest.TestCase):
    def synthetic(self):
        return secrets.token_hex(12)

    def synthetic_endpoint(self):
        return 'http://' + '.'.join(str(x) for x in (10, 23, 45, 67)) + ':8000'

    def test_attribute_aliases_without_vendor_prefix(self):
        for field in ["seckey", "apiSecret", "client_secret", "secret_access_key"]:
            value = self.synthetic()
            issues = scan_file("service.py", ("self." + field + " = " + repr(value)).encode())
            self.assertTrue(any(x.get("field") == field for x in issues), field)
            self.assertNotIn(value, json.dumps(issues))

    def test_annotations_and_concatenated_literals(self):
        value = self.synthetic()
        source = "self.seckey: str = " + repr(value[:12]) + " + " + repr(value[12:])
        self.assertTrue(scan_file("service.py", source.encode()))

    def test_environment_defaults_are_checked_even_with_innocent_target(self):
        value = self.synthetic()
        source = "value = os.getenv('BAIDU_TRANS_SECKEY', " + repr(value) + ")"
        self.assertTrue(any(x["rule"] == "credential-default" for x in scan_file("service.py", source.encode())))

    def test_boolean_environment_fallback_is_checked(self):
        value = self.synthetic()
        for source in [
            "self.seckey = os.getenv('BAIDU_TRANS_SECKEY') or " + repr(value),
            "value = os.getenv('BAIDU_TRANS_SECKEY') or " + repr(value),
            "value = getenv('BAIDU_TRANS_SECKEY', default=" + repr(value) + ")",
        ]:
            self.assertTrue(scan_file("service.py", source.encode()))

    def test_conditional_secret_literal_is_checked(self):
        value = self.synthetic()
        source = "self.seckey = configured if configured else " + repr(value)
        self.assertTrue(scan_file("service.py", source.encode()))

    def test_deployment_address_in_live_endpoint_is_checked(self):
        self.assertTrue(scan_file("service.py", ("url = " + repr(self.synthetic_endpoint() + "/api")).encode()))
        self.assertEqual(scan_file("service.py", b"url = 'http://localhost:8000/api'"), [])

    def test_deployment_address_adjacent_to_chinese_comment(self):
        address = '.'.join(str(x) for x in (10, 23, 45, 67))
        for comment in ['# 地址' + address + '端口', '# OCR默认使用' + address + '服务']:
            findings = scan_file('service.py', comment.encode())
            self.assertTrue(any(x['rule'] == 'deployment-address-in-comment' for x in findings))

    def test_json_environment_and_javascript_fields(self):
        value = self.synthetic()
        for path, text in [
            ("model.json", json.dumps({"config": {"seckey": value}})),
            (".env.example", "BAIDU_TRANS_SECKEY=" + value),
            ("client.js", "const secKey = " + json.dumps(value)),
        ]:
            self.assertTrue(scan_file(path, text.encode()), path)

    def test_commented_out_credentials_are_not_ignored(self):
        value = self.synthetic()
        issues = scan_file("service.py", ("# self.seckey = " + repr(value)).encode())
        self.assertTrue(any(x["rule"] == "credential-literal-comment" for x in issues))

    def test_runtime_attribute_logging_is_flagged(self):
        issues = scan_file("service.py", b"print(self.seckey)")
        self.assertTrue(any(x["rule"] == "credential-logging" for x in issues))

    def test_dynamic_configuration_and_metadata_keys_are_not_literals(self):
        source = "self.seckey = secret('BAIDU_TRANS_SECKEY')\nSCENE_SLOT_KEY='scene_meta'\n"
        self.assertEqual(scan_file("service.py", source.encode()), [])

    def test_actual_values_in_test_files_are_still_detected(self):
        value = self.synthetic()
        issues = scan_file("backend/tests/test_example.py", ("seckey = " + repr(value)).encode())
        self.assertTrue(issues)

    def test_known_prefix_rules_cannot_be_hidden_by_fixture_label(self):
        value = "unit-" + "sk-" + self.synthetic()
        issues = scan_file("backend/tests/test_example.py", ("api_key = " + repr(value)).encode())
        self.assertTrue(any(x["rule"] == "credential-signature" for x in issues))

    def test_allowlist_is_bound_to_exact_value_and_field(self):
        value = self.synthetic()
        source = ("self.seckey = " + repr(value)).encode()
        exception = {"file": "service.py", "field": "seckey", "rule": "credential-literal",
                     "fingerprint": hashlib.sha256(value.encode()).hexdigest()}
        self.assertEqual(scan_file("service.py", source, [exception]), [])
        self.assertTrue(scan_file("service.py", ("self.seckey = " + repr(self.synthetic())).encode(), [exception]))
        self.assertTrue(scan_file("other.py", source, [exception]))

    def test_deployment_addresses_in_comments_are_not_ignored(self):
        self.assertTrue(scan_file("service.py", ("# OCR endpoint: " + self.synthetic_endpoint()).encode()))
        self.assertEqual(scan_file("service.py", b"# Example: http://192.0.2.10:8000"), [])

    def test_history_detects_removed_prefixless_secret(self):
        value = self.synthetic()
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", temp, "-c", "user.name=unit-test",
                     "-c", "user.email=unit@example.invalid", "-c", "commit.gpgsign=false", *args],
                    stderr=subprocess.DEVNULL)
            git("init", "-q", "--initial-branch=main")
            (repo / "service.py").write_text("self.seckey = " + repr(value), encoding="utf-8")
            git("add", "service.py"); git("commit", "-qm", "unit fixture")
            old = git("rev-parse", "HEAD").decode().strip()
            (repo / "service.py").write_text("self.seckey = ''", encoding="utf-8")
            git("add", "service.py"); git("commit", "-qm", "unit cleanup")
            report = scan_history(repo)
            self.assertEqual(len(report["commits"]), 2)
            self.assertTrue(any(x.get("field") == "seckey" and x["commit"] == old for x in report["issues"]))
            self.assertNotIn(value, json.dumps(report))

if __name__ == "__main__":
    unittest.main()
