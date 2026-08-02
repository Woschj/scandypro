import hashlib
import hmac

import bcrypt

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def generate_csrf_token(csrf_secret: str) -> str:
    """CSRF-Token, deterministisch aus einem stabilen, serverseitig in der
    Session abgelegten Zufallswert abgeleitet (HMAC mit secret_key) - siehe
    app.core.templating.csrf_token, das diesen Zufallswert bei Bedarf erzeugt
    und in `request.session["_csrf_secret"]` ablegt. Bewusst NICHT direkt aus
    dem rohen (httpOnly) Session-Cookie-String abgeleitet: Starlettes
    SessionMiddleware signiert diesen bei jeder Antwort mit einem neuen
    Zeitstempel neu, der rohe Cookie-Wert ist also über zwei Requests hinweg
    nicht stabil - ein daraus abgeleitetes Token wäre schon beim nächsten
    Request wieder ungültig."""
    return hmac.new(settings.secret_key.encode("utf-8"), csrf_secret.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_csrf_token(token: str, csrf_secret: str) -> bool:
    if not token or not csrf_secret:
        return False
    return hmac.compare_digest(token, generate_csrf_token(csrf_secret))
