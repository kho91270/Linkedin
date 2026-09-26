"""
CONFIG.PY - Centralized configuration and secrets management
Validates environment variables at startup to fail fast
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---- API KEYS & CREDENTIALS ----
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
LEONARDO_API_KEY = os.environ.get("LEONARDO_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_PERSON_ID = os.environ.get("LINKEDIN_PERSON_ID")

# X (Twitter) API v2
X_API_KEY = os.environ.get("X_API_KEY")
X_API_KEY_SECRET = os.environ.get("X_API_KEY_SECRET")
X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET")

# ---- MODEL & DIRECTORY CONFIGURATION ----
GROQ_MODEL = "llama-3.3-70b-versatile"
QUEUE_FILE = "content_queue.json"
TRACKER_FILE = "tracker.json"
PUBLISHED_DIR = "published_posts"
BRIEF_DIR = "veille_briefs"
PENDING_DIR = "pending_approval"
APPROVED_DIR = "approved_posts"
LOG_FILE = "bot.log"

# ---- LOGGING ----
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ---- BUSINESS CONSTANTS ----
TARGET_POSTS_PER_WEEK = 3
MAX_HISTORY_RECORDS = 100
TWITTER_CHAR_LIMIT = 280
TWITTER_SAFETY_MARGIN = 20  # Reserve for ellipsis

# ---- PILLAR SCHEDULE ----
PILLAR_SCHEDULE = {
    "even": {"Tuesday": "terrain", "Thursday": "analyste", "Saturday": "conversation"},
    "odd": {"Tuesday": "analyste", "Thursday": "terrain", "Saturday": "insight"},
}

PILLAR_INSTRUCTIONS = {
    "terrain": "Experience personnelle de Category Manager. Evaluation fournisseur, negociation, scorecard, RFI/RFP, erreurs, lecons. 100% vecu avec details concrets.",
    "analyste": "Analyse une startup procuretech, un outil, une tendance. Utilise le brief. Donne ton AVIS de praticien. Compare avec ton experience. Sois critique.",
    "conversation": "Question ouverte qui genere du debat. Polarisante. Mini-contexte personnel en intro.",
    "insight": "Lecon courte et percutante. 1 contexte + 1 insight + 1 question. 200-400 chars.",
}

FORMAT_MAP = {
    "terrain": "texte",
    "analyste": "texte",
    "conversation": "question",
    "insight": "insight",
}

# ---- VALIDATION & STARTUP CHECKS ----


def validate_google_credentials() -> Optional[dict]:
    """Validate and parse Google credentials JSON."""
    if not GOOGLE_CREDENTIALS_JSON:
        logger.warning("GOOGLE_CREDENTIALS not set; Gmail API will be skipped.")
        return None
    try:
        creds_data = json.loads(GOOGLE_CREDENTIALS_JSON)
        logger.debug("Google credentials parsed successfully")
        return creds_data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid GOOGLE_CREDENTIALS JSON: {e}")
        return None


def check_required_secrets_for_service(service: str) -> bool:
    """
    Check if required secrets are available for a service.
    Returns True if secrets are present, False otherwise.
    """
    required_secrets = {
        "groq": [GROQ_API_KEY],
        "linkedin": [LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_ID],
        "x": [X_API_KEY, X_API_KEY_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET],
        "email": [SMTP_EMAIL, SMTP_PASSWORD, NOTIFY_EMAIL],
        "gmail": [GOOGLE_CREDENTIALS_JSON],
    }

    secrets = required_secrets.get(service, [])
    is_available = all(secrets)

    if is_available:
        logger.info(f"✓ Secrets for '{service}' are available")
    else:
        logger.warning(f"⚠ Secrets for '{service}' are incomplete or missing")

    return is_available


def check_all_services() -> dict:
    """Check availability of all external services. Returns status dict."""
    services = {
        "groq": check_required_secrets_for_service("groq"),
        "linkedin": check_required_secrets_for_service("linkedin"),
        "x": check_required_secrets_for_service("x"),
        "email": check_required_secrets_for_service("email"),
        "gmail": check_required_secrets_for_service("gmail"),
    }

    if services["groq"]:
        logger.info("✓ Ready to generate content (Groq)")
    else:
        logger.error("✗ Cannot generate content without Groq API key")

    return services


def setup_logging():
    """Configure logging for the application."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=log_format,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
