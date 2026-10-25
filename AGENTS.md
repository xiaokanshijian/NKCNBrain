# Public release workspace
- This repository is a sanitized snapshot; no private repository history is included.
- Never add real API keys, database passwords, user uploads, logs, or local caches.
- Keep credentials on the backend. Browser environment variables are public.
- Preserve API paths and response shapes. Backend routes live under /api/.
- Preserve grading curriculum, migrations, and functional data schemas.
- Run backend checks, frontend build, and tools/check_public_release.py before publication.
- Do not run migrations against an existing deployment as part of verification.
