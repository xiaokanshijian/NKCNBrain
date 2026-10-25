"""Isolated login integration tests: never use the deployment database."""
SECRET_KEY = "unit-session-signing-secret"
DEBUG = False
USE_TZ = True
ALLOWED_HOSTS = ["testserver", "localhost"]
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "corsheaders", "app1.apps.App1Config", "zym.apps.ZymConfig",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
MIGRATION_MODULES = {"app1": None, "zym": None}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "tests.session_test_urls"
CORS_ALLOWED_ORIGINS = ["http://localhost:8080"]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = ["http://localhost:8080"]
SESSION_COOKIE_NAME = "nkcn_public_sessionid"
CSRF_COOKIE_NAME = "nkcn_public_csrftoken"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 43200
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
