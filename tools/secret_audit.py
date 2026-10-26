"""Prefix-independent, read-only credential checks. Never returns literal values."""
import ast
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import tokenize

TOKEN_PATTERN = re.compile(
    rb"\b(?:sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    rb"github_pat_[A-Za-z0-9_]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,}|"
    rb"nvapi-[A-Za-z0-9_-]{20,})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
_ALIASES = {
    "seckey", "secretkey", "apikey", "apisecret", "appkey", "appsecret", "clientsecret",
    "accesskeysecret", "secretaccesskey", "accesstoken", "authtoken", "refreshtoken",
    "password", "passwd", "pwd", "signingkey", "privatekey", "authorization", "token",
    "apitoken", "secrettoken", "subscriptionkey", "consumerkey", "consumersecret", "sharedsecret",
}
_SUFFIXES = _ALIASES - {"pwd", "token", "authorization"}
_LITERAL = re.compile(r"""(?i)(?<![\w])["']?([A-Za-z_][A-Za-z0-9_]{0,79})["']?\s*[:=]\s*(["'])([^"'\r\n]*)\2""")
_IP = re.compile(r"(?<![A-Za-z0-9_.])(?:\d{1,3}\.){3}\d{1,3}(?![A-Za-z0-9_.])")

def is_secret_name(name):
    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
    return normalized in _ALIASES or any(normalized.endswith(suffix) for suffix in _SUFFIXES)

def _fixture_file(name):
    p = Path(name)
    return "/tests/" in name or p.name.startswith("test_") or p.name.endswith("_test.py") or p.name == "ci_test_support.py"

def _safe_placeholder(value, filename):
    value = value.strip()
    if not value or value.startswith(("env:", "$" + "{")) or re.fullmatch(r"\$[A-Z_][A-Z0-9_]*", value):
        return True
    if value.lower() in {"[redacted]", "<redacted>", "redacted", "...", "your_api_key", "your-api-key", "your-secret-key"}:
        return True
    return _fixture_file(filename) and bool(re.match(r"(?i)^(unit[-_]|test[-_]|mock[-_]|fake[-_]|dummy[-_]|ci-tests-only-)", value))

def _static_string(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static_string(node.left), _static_string(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr) and all(isinstance(x, ast.Constant) and isinstance(x.value, str) for x in node.values):
        return "".join(x.value for x in node.values)
    return None

def _credential_literals(node):
    value = _static_string(node)
    if value is not None:
        return [(getattr(node, "lineno", None), value)]
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return [item for child in node.values for item in _credential_literals(child)]
    if isinstance(node, ast.IfExp):
        return _credential_literals(node.body) + _credential_literals(node.orelse)
    return []

def _environment_field(node):
    if not isinstance(node, ast.Call) or not node.args:
        return None
    getter = (isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "getenv"}
              or isinstance(node.func, ast.Name) and node.func.id == "getenv")
    return _static_string(node.args[0]) if getter else None

def _deployment_ip(value):
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not addr.is_loopback and not addr.is_unspecified and not any(
        addr in ipaddress.ip_network(net) for net in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))

def _field(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return ""

def scan_file(filename, raw, allowlist=()):
    issues = []
    allowed = {(x["file"], x["field"], x["fingerprint"], x["rule"]) for x in allowlist}
    for match in TOKEN_PATTERN.finditer(raw):
        issues.append({"file": filename, "line": raw.count(b"\n", 0, match.start()) + 1, "rule": "credential-signature"})
    if b"\0" in raw[:8192]:
        return issues
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return issues

    def check(field, value, line, rule):
        if not is_secret_name(field) or value is None or _safe_placeholder(value, filename):
            return
        fingerprint = hashlib.sha256(value.encode()).hexdigest()
        if (filename, field, fingerprint, rule) not in allowed:
            item = {"file": filename, "line": line, "field": field, "rule": rule, "fingerprint": fingerprint}
            if item not in issues:
                issues.append(item)

    comments = []
    if filename.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError as error:
            return issues + [{"file": filename, "line": error.lineno, "rule": "python-syntax"}]
        for node in ast.walk(tree):
            pairs = []
            if isinstance(node, ast.Assign):
                pairs = [(_field(t), node.value) for t in node.targets]
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
                pairs = [(_field(node.target), node.value)]
            elif isinstance(node, ast.keyword):
                pairs = [(node.arg or "", node.value)]
            elif isinstance(node, ast.Dict):
                pairs = [(k.value, v) for k, v in zip(node.keys, node.values)
                         if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            for field, value_node in pairs:
                for line, value in _credential_literals(value_node):
                    check(field, value, line or node.lineno, "credential-literal")
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                field = _environment_field(node.values[0])
                if field:
                    for fallback in node.values[1:]:
                        for line, value in _credential_literals(fallback):
                            check(field, value, line or node.lineno, "credential-default")
            if isinstance(node, ast.Call) and (
                    isinstance(node.func, ast.Name) and node.func.id == "print" or
                    isinstance(node.func, ast.Attribute) and node.func.attr in {"debug", "info", "warning", "error", "critical"}):
                for arg in node.args:
                    emitted = [x.value for x in arg.values if isinstance(x, ast.FormattedValue)] if isinstance(arg, ast.JoinedStr) else [arg]
                    for value in emitted:
                        if is_secret_name(_field(value)):
                            issues.append({"file": filename, "line": node.lineno, "field": _field(value), "rule": "credential-logging"})
            field = _environment_field(node)
            if field:
                defaults = node.args[1:2] + [k.value for k in node.keywords if k.arg == "default"]
                for fallback in defaults:
                    for line, value in _credential_literals(fallback):
                        check(field, value, line or node.lineno, "credential-default")
        try:
            comments = [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(text).readline) if t.type == tokenize.COMMENT]
        except (tokenize.TokenError, IndentationError):
            pass
    elif filename.endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        def visit(value):
            if isinstance(value, dict):
                for field, item in value.items():
                    if isinstance(item, str):
                        match = re.search(re.escape(json.dumps(field)) + r"\s*:", text)
                        line = text.count("\n", 0, match.start()) + 1 if match else None
                        check(field, item, line, "credential-literal")
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(data)
    elif Path(filename).name.startswith(".env"):
        for n, line in enumerate(text.splitlines(), 1):
            if "=" in line and not line.lstrip().startswith("#"):
                field, value = line.split("=", 1)
                check(field.strip(), value.strip().strip("\"'"), n, "credential-literal")
    elif filename.endswith((".js", ".cjs", ".mjs", ".vue", ".ts", ".yaml", ".yml", ".toml", ".ini")) and "public/static/pdf/" not in filename:
        for n, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000:
                continue
            for match in _LITERAL.finditer(line):
                check(match[1], match[3], n, "credential-literal")
            if line.lstrip().startswith(("//", "/*", "*")):
                comments.append((n, line))

    if filename.endswith((".py", ".js", ".vue", ".json")) and "public/static/pdf/" not in filename:
        for n, line in enumerate(text.splitlines(), 1):
            if len(line) > 4000:
                continue
            if any(_deployment_ip(m[1]) for m in re.finditer(r"https?://((?:\d{1,3}\.){3}\d{1,3})(?=[^0-9.]|$)", line)):
                issues.append({"file": filename, "line": n, "rule": "deployment-address-literal"})

    for n, comment in comments:
        for match in _LITERAL.finditer(comment):
            check(match[1], match[3], n, "credential-literal-comment")
        for match in _IP.finditer(comment):
            try:
                addr = ipaddress.ip_address(match[0])
            except ValueError:
                continue
            if not addr.is_loopback and not addr.is_unspecified and not any(
                    addr in ipaddress.ip_network(net) for net in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")):
                issues.append({"file": filename, "line": n, "rule": "deployment-address-in-comment"})
    return issues

def scan_history(repo, refs=("HEAD",), allowlist=()):
    repo = str(repo)
    commits = subprocess.check_output(["git", "-C", repo, "rev-list", *refs]).decode().splitlines()
    blobs = {}
    for commit in commits:
        entries = subprocess.check_output(["git", "-C", repo, "ls-tree", "-r", "-z", commit])
        for entry in entries.split(b"\0"):
            if entry:
                meta, path = entry.split(b"\t", 1)
                mode, kind, oid = meta.decode().split()
                if kind == "blob":
                    blobs.setdefault(oid, []).append((commit, path.decode("utf-8")))
    proc = subprocess.Popen(["git", "-C", repo, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    issues = []
    try:
        for oid, locations in blobs.items():
            proc.stdin.write((oid + "\n").encode()); proc.stdin.flush()
            header = proc.stdout.readline().split()
            raw = proc.stdout.read(int(header[2])); proc.stdout.read(1)
            for commit, filename in locations:
                for item in scan_file(filename, raw, allowlist):
                    issues.append({**item, "commit": commit})
    finally:
        proc.stdin.close()
        proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError('Git history reader failed')
    return {"commits": commits, "blob_versions": len(blobs), "issues": issues}
