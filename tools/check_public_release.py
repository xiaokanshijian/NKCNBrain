"""Read-only publication checks. Reports locations, never credential values."""
import ast
import argparse
from secret_audit import scan_file, scan_history, is_secret_name
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
def publication_files():
    result = subprocess.check_output(["git", "-C", str(ROOT), "ls-files",
                                      "--cached", "--others", "--exclude-standard", "-z"])
    return sorted(set(p.decode("utf-8") for p in result.split(b"\0") if p))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also scan all versions reachable from HEAD")
    args = parser.parse_args()
    allowlist_path = ROOT / "tools/secret_scan_allowlist.json"
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8")) if allowlist_path.exists() else []
    issues = []
    paths = publication_files()
    token_pattern = re.compile(rb"\b(?:sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,}|nvapi-[A-Za-z0-9_-]{20,})\b")
    model_count = 0
    python_count = 0
    for name in paths:
        p = ROOT / name
        if not p.is_file():
            issues.append({"file": name, "rule": "missing-file"})
            continue
        if (p.name.startswith(".env") and p.name != ".env.example") or p.suffix.lower() in {".log", ".pkl", ".pickle", ".xlsx", ".csv", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}:
            issues.append({"file": name, "rule": "private-file"})
        if any(part in p.relative_to(ROOT).parts for part in (".git", "node_modules", "__pycache__", ".idea", ".vscode", "received_dir", "document_split_cache", "backData", "yq")):
            issues.append({"file": name, "rule": "private-directory"})
        raw = p.read_bytes()
        issues.extend(scan_file(name, raw, allowlist))
        for match in token_pattern.finditer(raw):
            issues.append({"file": name, "line": raw.count(b"\n", 0, match.start()) + 1, "rule": "credential-signature"})
        if b"\0" in raw[:8192]:
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            continue
        if p.suffix == ".py":
            try:
                tree = ast.parse(text)
                python_count += 1
            except SyntaxError as error:
                issues.append({"file": name, "line": error.lineno, "rule": "python-syntax"})
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                    for arg in node.args:
                        values = [arg]
                        if isinstance(arg, ast.JoinedStr):
                            values = [v.value for v in arg.values if isinstance(v, ast.FormattedValue)]
                        for value in values:
                            if isinstance(value, ast.Name) and re.search(r"(?i)(api.?key|api.?secret|password)$", value.id):
                                issues.append({"file": name, "line": node.lineno, "rule": "credential-logging"})
        if name.startswith("backend/app_chat/config/model_config/") and p.suffix == ".json":
            data = json.loads(text)
            model_count += 1
            for key, value in data.get("config", {}).items():
                if is_secret_name(key) and isinstance(value, str) and value:
                    if not re.fullmatch(r"env:[A-Z_][A-Z0-9_]*", value):
                        issues.append({"file": name, "rule": "model-credential-must-be-env-reference", "field": key})
        if p.suffix in {".py", ".js", ".vue", ".json"} and "public/static/" not in name and not name.startswith("tools/"):
            for n, line in enumerate(text.splitlines(), 1):
                if re.search(r"[A-Za-z]:[\\/](?:Users|postgraduate)|/(?:home|root)/[A-Za-z0-9_-]+", line):
                    issues.append({"file": name, "line": n, "rule": "private-machine-path"})
    manifest_path = ROOT / "PUBLIC_RELEASE_MANIFEST.json"
    manifest_ok = False
    if manifest_path.exists():
        try:
            recorded = json.loads(manifest_path.read_text(encoding="utf-8-sig"))["files"]
            actual = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                      for p in paths if p != "PUBLIC_RELEASE_MANIFEST.json" and (ROOT / p).is_file()}
            manifest_ok = actual == recorded
        except (KeyError, ValueError):
            pass
    if not manifest_ok:
        issues.append({"file": "PUBLIC_RELEASE_MANIFEST.json", "rule": "manifest-out-of-date"})
    result = {"files": len(paths), "python_files": python_count, "model_configs": model_count,
              "issues": [{k: v for k, v in item.items() if k != "fingerprint"} for item in issues]}
    history = scan_history(ROOT, allowlist=allowlist) if args.history else None
    if history is not None:
        result["history"] = {**history, "issues": [
            {k: v for k, v in item.items() if k != "fingerprint"} for item in history["issues"]]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if issues or (history and history["issues"]) else 0

if __name__ == "__main__":
    sys.exit(main())
