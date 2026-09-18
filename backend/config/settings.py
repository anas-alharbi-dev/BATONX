"""
Django settings for the VYRA API (Phase 0 — walking skeleton).

Everything environment-specific is read from the environment (optionally via
backend/.env). No secrets are hardcoded. The Anthropic key is read here and used
only by the server-side `ai` app.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")  # no-op if the file is absent

# --- Core ---
SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "corsheaders",
    # local
    "projects",
    "ai",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.ApiJsonErrorMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---
# Defaults to a local PostgreSQL database named "vyra". Override with DATABASE_URL.
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://localhost:5432/vyra"),
}

# Phase P-2: real accounts exist now, so real password strength rules apply.
# Django's own stock validators — no third-party dependency.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ---
# Phase P-2: session-based auth (Django's own session framework + DRF's
# SessionAuthentication) — first-party, zero new dependencies, and already
# fully wired in MIDDLEWARE/INSTALLED_APPS (SessionMiddleware, CSRF
# middleware, AuthenticationMiddleware were present but unused). See the P-2
# report for why this beats introducing JWT/localStorage tokens here.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "common.auth.BatonxSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "common.exception_handler.envelope_exception_handler",
}

# --- CORS / CSRF (cross-port local dev: frontend :3000/:3010, API :8000) ---
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
# Session/CSRF cookies must travel on cross-port fetches for auth to work at
# all — the browser only attaches them when the request opts in
# (credentials: "include") AND the server explicitly allows it.
CORS_ALLOW_CREDENTIALS = True
# Django 4+ checks the request's Origin header against this list for any
# unsafe method even when SESSION/CSRF cookies are same-site (which
# localhost:3010 -> localhost:8000 technically is, by scheme+registrable
# domain) — without it, every authenticated POST/PATCH would 403 on CSRF.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)
# CSRF cookie must stay JS-readable (Django's own default) so the frontend
# can echo it back as X-CSRFToken; the session cookie stays HttpOnly
# (Django's own default) — never read or stored by frontend JS.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True
# "Lax" is correct (not "None") for same-site-by-registrable-domain local
# dev across ports; production deploys behind a real domain should keep
# reviewing this alongside SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

# --- AI service (server-side only) ---
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
VYRA_MODEL = env("VYRA_MODEL", default="claude-sonnet-5")
VYRA_AI_TIMEOUT_SECONDS = env.float("VYRA_AI_TIMEOUT_SECONDS", default=60.0)

# --- Data Projects (Phase I-1) ---
# Raw dataset bytes live behind a FileStore abstraction, never in PostgreSQL.
# LocalFileStore is the MVP backend; a future object-storage backend must not
# require any change to domain code.
DATA_STORAGE_ROOT = env("DATA_STORAGE_ROOT", default=str(BASE_DIR / ".data_store"))
DATA_MAX_UPLOAD_BYTES = env.int("DATA_MAX_UPLOAD_BYTES", default=25 * 1024 * 1024)
DATA_ALLOWED_SOURCE_TYPES = ("csv", "json")
DATA_MAX_ROWS = env.int("DATA_MAX_ROWS", default=1_000_000)
DATA_PROFILE_SAMPLE_ROWS = env.int("DATA_PROFILE_SAMPLE_ROWS", default=200_000)
DATA_PROFILE_TOP_VALUES = env.int("DATA_PROFILE_TOP_VALUES", default=25)
DATA_PROFILE_SAMPLE_VALUES = env.int("DATA_PROFILE_SAMPLE_VALUES", default=5)

# --- Data Projects: DuckDB execution boundary (Phase I-2) ---
# Generated SQL (including BATONX's own) is untrusted; these bound it.
DATA_QUERY_MAX_RESULT_ROWS = env.int("DATA_QUERY_MAX_RESULT_ROWS", default=500)
DATA_QUERY_TIMEOUT_SECONDS = env.float("DATA_QUERY_TIMEOUT_SECONDS", default=15.0)
DATA_QUERY_MAX_FAILURE_SAMPLES = env.int("DATA_QUERY_MAX_FAILURE_SAMPLES", default=10)
DATA_DUCKDB_MEMORY_LIMIT = env("DATA_DUCKDB_MEMORY_LIMIT", default="256MB")
DATA_DUCKDB_THREADS = env.int("DATA_DUCKDB_THREADS", default=2)
DATA_DUCKDB_MAX_TEMP_SIZE = env("DATA_DUCKDB_MAX_TEMP_SIZE", default="512MB")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "vyra": {"handlers": ["console"], "level": "INFO"},
    },
}
