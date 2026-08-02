import hashlib
import hmac

import bcrypt

from app.core.config import settings

SESSION_COOKIE_NAME = "session"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def generate_csrf_token(session_value: str) -> str:
    """Stateless CSRF-Token, deterministisch aus dem Wert des (httpOnly)
    Session-Cookies abgeleitet (HMAC mit secret_key) - kein zusätzlicher
    Server-State nötig. Ein Angreifer kann den Wert nicht fälschen, ohne
    secret_key zu kennen, und kann den httpOnly-Cookie nicht per JS
    auslesen, um ihn selbst abzuleiten (Analogie: Schwestermodul
    Scandy-Lite, app/core/security.py dort)."""
    return hmac.new(settings.secret_key.encode("utf-8"), session_value.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_csrf_token(token: str, session_value: str) -> bool:
    if not token or not session_value:
        return False
    return hmac.compare_digest(token, generate_csrf_token(session_value))
