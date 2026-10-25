# Public snapshot changes — 2026-10-24

- Copied the main application to backend/ and frontend/; retained the optional reviewer UI.
- Replaced source credentials, fallback credentials and model JSON values with environment references.
- Removed private credential comments and deployment addresses.
- Browser voice clients request authenticated server-generated WebSocket URLs.
- Model configuration saves accept env:VARIABLE references rather than plaintext credentials.
- Omitted private .env, caches, logs, uploaded documents, data backups, internal notes,
  external reference workspace and the separate OCR research project.
- Private experiment fixture entries are empty while their file/schema contracts remain.
- Existing migrations and curriculum/rule data are retained.
- No private or public Git history was imported. No remote is configured.

## 2026-10-25 — login and voice session integration

- Existing NKCN account login creates a server-side session after successful password/allowed checks.
- Login now uses CSRF-protected POST at the same API path, with both trailing-slash forms supported.
- Added CSRF bootstrap, current-session and explicit logout endpoints.
- Automatic login verifies server identity; cached plaintext passwords are removed.
- Voice signing accepts the verified NKCN account session; revoked/expired accounts cannot obtain new signatures.
- Notebook exit remains separate from account logout.
- Added 19 backend HTTP integration tests and 11 frontend authentication checks.
- No model fields or application migrations changed. Integration test databases are memory-only.

## 2026-10-25 — publication

- Publish the reviewed clean snapshot on top of the target repository's existing public main commit.
- Do not import private commits, branches, tags, Git objects, developer .env files or local verification material.
- Replace the current tree with the reviewed manifest; older research projects and internal documents outside this manifest are not included.
- Keep existing public history intact; credential rotation and historical cleanup are separate tasks.
