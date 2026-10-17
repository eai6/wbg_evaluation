"""Django settings for Scorecard Explorer. Configuration comes from the repository-level .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # q1_prototype/
REPO_DIR = BASE_DIR.parent                                   # repository root
load_dotenv(REPO_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-not-secret-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [h for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "explorer",
    "assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "scorecard_explorer.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request", "explorer.context.assets"]},
}]
WSGI_APPLICATION = "scorecard_explorer.wsgi.application"

# SQLite only stores sessions (conversation state); Scorecard data lives in the read-only DuckDB file.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "app.sqlite3"}}
SESSION_ENGINE = "django.contrib.sessions.backends.db"

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Scorecard Explorer -------------------------------------------------------------------------------------
SCORECARD_DB = Path(os.getenv("SCORECARD_DB_PATH", REPO_DIR / "data" / "scorecard.duckdb"))

LLM = {
    "model": os.getenv("LLM_MODEL", "anthropic/claude-sonnet-5-5"),        # research, writing
    "fast_model": os.getenv("LLM_FAST_MODEL", "") or os.getenv("LLM_MODEL", "anthropic/claude-haiku-5-5"),  # router
    "api_key": os.getenv("LLM_API_KEY", ""),
    "api_base": os.getenv("LLM_API_BASE", "") or None,
    "timeout": int(os.getenv("LLM_TIMEOUT", "60")),
    "effort": os.getenv("LLM_EFFORT", "medium"),               # Claude effort for research / writing
    "router_effort": os.getenv("LLM_ROUTER_EFFORT", "low"),    # Claude effort for routing
}
ASSISTANT = {
    "max_tool_calls": int(os.getenv("ASSISTANT_MAX_TOOL_CALLS", "6")),
    "history_turns": int(os.getenv("ASSISTANT_HISTORY_TURNS", "8")),
    "max_message_chars": 500,
    "rate_limit_per_5min": int(os.getenv("ASSISTANT_RATE_LIMIT", "30")),
}

LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
    "loggers": {"LiteLLM": {"level": "WARNING"}, "httpx": {"level": "WARNING"}},
}
