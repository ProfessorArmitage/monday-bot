"""
security.py — Capa de seguridad centralizada del Monday Bot.

Módulos incluidos:
  1. Cifrado simétrico (Fernet) para datos sensibles en reposo
  2. Rate limiter por usuario (en memoria, sin dependencias externas)
  3. Validación y sanitización de inputs
  4. Audit logger para acciones admin
  5. OAuth state tokens con TTL

Variables de entorno requeridas:
  ENCRYPTION_KEY  — Fernet key en base64 (generar con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

IMPORTANTE: Si ENCRYPTION_KEY no está configurada al arrancar, el bot
levanta una advertencia pero NO detiene el servicio — los tokens se
guardan sin cifrar como antes (compatibilidad hacia atrás). Configurar
ENCRYPTION_KEY es fuertemente recomendado en producción.

Para rotar la clave (key rotation):
  1. Generar nueva clave
  2. Correr el script de migración: python scripts/rotate_key.py <old_key> <new_key>
  3. Actualizar ENCRYPTION_KEY en Railway
  4. Redeploy
"""

import os
import time
import hmac
import base64
import hashlib
import logging
import secrets
import threading
from collections import defaultdict, deque
from typing import Optional

logger = logging.getLogger(__name__)

# ── 1. CIFRADO SIMÉTRICO (Fernet) ────────────────────────────

_fernet = None
_encryption_available = False

def _init_encryption():
    """Inicializa Fernet con ENCRYPTION_KEY del entorno."""
    global _fernet, _encryption_available
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        logger.warning(
            "⚠️  ENCRYPTION_KEY no configurada. "
            "Los tokens de Google se guardarán SIN cifrar. "
            "Genera una clave con: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        return
    try:
        from cryptography.fernet import Fernet, InvalidToken
        _fernet = Fernet(key.encode())
        _encryption_available = True
        logger.info("✅ Cifrado simétrico (Fernet) inicializado correctamente")
    except Exception as e:
        logger.error(f"❌ Error inicializando cifrado: {e}. Los datos se guardarán sin cifrar.")

_init_encryption()


def encrypt(plaintext: str) -> str:
    """
    Cifra un string con Fernet y retorna el token cifrado en base64.
    Si el cifrado no está disponible, retorna el texto original
    (compatibilidad hacia atrás — siempre logea una advertencia).
    """
    if not _encryption_available or not plaintext:
        return plaintext
    from cryptography.fernet import Fernet
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Descifra un token Fernet. Retorna el texto original.
    Si el texto no es un token válido (datos legacy sin cifrar),
    lo retorna tal cual para compatibilidad.
    """
    if not _encryption_available or not ciphertext:
        return ciphertext
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        # Datos legacy sin cifrar — retornar tal cual
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Heurística: los tokens Fernet empiezan con 'gAAAAA'."""
    return isinstance(value, str) and value.startswith("gAAAAA")


# ── 2. RATE LIMITER POR USUARIO ───────────────────────────────

# Configuración — ajustar según necesidades
RATE_LIMIT_MESSAGES  = int(os.getenv("RATE_LIMIT_MESSAGES", "20"))  # max msgs
RATE_LIMIT_WINDOW    = int(os.getenv("RATE_LIMIT_WINDOW", "60"))    # por N segundos
RATE_LIMIT_VOICE_MAX = int(os.getenv("RATE_LIMIT_VOICE_MAX", "10")) # audios por ventana
RATE_LIMIT_COOLDOWN  = int(os.getenv("RATE_LIMIT_COOLDOWN", "300")) # 5 min de bloqueo

_rate_lock = threading.Lock()
_user_timestamps: dict[int, deque] = defaultdict(deque)  # user_id → timestamps
_user_blocked_until: dict[int, float] = {}                # user_id → unblock_time


def check_rate_limit(user_id: int, is_voice: bool = False) -> tuple[bool, str]:
    """
    Verifica si el usuario puede enviar otro mensaje.

    Retorna:
        (allowed: bool, reason: str)
        allowed=True → mensaje permitido
        allowed=False → mensaje rechazado, reason explica por qué

    Algoritmo: ventana deslizante de RATE_LIMIT_WINDOW segundos.
    Si supera RATE_LIMIT_MESSAGES en la ventana → bloqueo de RATE_LIMIT_COOLDOWN.
    """
    now = time.monotonic()
    limit = RATE_LIMIT_VOICE_MAX if is_voice else RATE_LIMIT_MESSAGES

    with _rate_lock:
        # ── Chequeo de bloqueo activo ─────────────────────────
        if user_id in _user_blocked_until:
            unblock = _user_blocked_until[user_id]
            if now < unblock:
                remaining = int(unblock - now)
                return False, (
                    f"⏸ Demasiados mensajes. Puedes continuar en {remaining} segundos."
                )
            else:
                del _user_blocked_until[user_id]
                _user_timestamps[user_id].clear()

        # ── Limpiar timestamps fuera de la ventana ────────────
        window_start = now - RATE_LIMIT_WINDOW
        q = _user_timestamps[user_id]
        while q and q[0] < window_start:
            q.popleft()

        # ── Verificar límite ──────────────────────────────────
        if len(q) >= limit:
            _user_blocked_until[user_id] = now + RATE_LIMIT_COOLDOWN
            logger.warning(
                f"Rate limit aplicado a user_id={user_id}: "
                f"{len(q)} msgs en {RATE_LIMIT_WINDOW}s"
            )
            return False, (
                f"⏸ Enviaste demasiados mensajes muy rápido. "
                f"Por favor espera {RATE_LIMIT_COOLDOWN // 60} minutos."
            )

        # ── Registrar este mensaje ────────────────────────────
        q.append(now)
        return True, ""


def get_rate_status(user_id: int) -> dict:
    """Retorna el estado actual del rate limit para un usuario (uso admin)."""
    now = time.monotonic()
    with _rate_lock:
        blocked_until = _user_blocked_until.get(user_id)
        window_start  = now - RATE_LIMIT_WINDOW
        q = _user_timestamps.get(user_id, deque())
        recent = sum(1 for t in q if t > window_start)
        return {
            "user_id":       user_id,
            "msgs_in_window": recent,
            "limit":         RATE_LIMIT_MESSAGES,
            "window_seconds": RATE_LIMIT_WINDOW,
            "blocked":       blocked_until is not None and now < (blocked_until or 0),
            "unblocks_in":   max(0, int((blocked_until or 0) - now)),
        }


def reset_rate_limit(user_id: int) -> None:
    """Reinicia el rate limit de un usuario (uso admin)."""
    with _rate_lock:
        _user_timestamps.pop(user_id, None)
        _user_blocked_until.pop(user_id, None)
    logger.info(f"Rate limit reiniciado para user_id={user_id}")


# ── 3. VALIDACIÓN Y SANITIZACIÓN DE INPUTS ───────────────────

MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", "4000"))
MAX_VOICE_SIZE_MB  = int(os.getenv("MAX_VOICE_SIZE_MB", "10"))
MAX_VOICE_BYTES    = MAX_VOICE_SIZE_MB * 1024 * 1024


def sanitize_text(text: str) -> tuple[str, bool]:
    """
    Sanitiza un mensaje de texto entrante.

    Retorna:
        (texto_limpio: str, fue_truncado: bool)

    Operaciones:
        - Limpia caracteres de control peligrosos (null bytes, etc.)
        - Trunca a MAX_MESSAGE_LENGTH caracteres
        - Preserva emojis y caracteres Unicode válidos
    """
    if not text:
        return "", False

    # Eliminar null bytes y otros caracteres de control problemáticos
    # Preservar saltos de línea (\n) y tabs (\t) que son válidos en mensajes
    cleaned = "".join(
        ch for ch in text
        if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) != 127)
    )

    truncated = len(cleaned) > MAX_MESSAGE_LENGTH
    if truncated:
        cleaned = cleaned[:MAX_MESSAGE_LENGTH]
        logger.info(f"Mensaje truncado de {len(text)} a {MAX_MESSAGE_LENGTH} chars")

    return cleaned, truncated


def validate_voice_size(size_bytes: int) -> tuple[bool, str]:
    """
    Valida que un archivo de audio no exceda el límite configurado.
    Retorna (válido: bool, mensaje_error: str).
    """
    if size_bytes > MAX_VOICE_BYTES:
        return False, (
            f"El audio es demasiado largo ({size_bytes // (1024*1024):.1f} MB). "
            f"Máximo: {MAX_VOICE_SIZE_MB} MB. Divide el mensaje en partes más cortas."
        )
    return True, ""


def validate_category(category: str) -> bool:
    """
    Valida que un nombre de categoría de memoria sea válido.
    Previene SQL injection via nombre de columna.
    """
    VALID_CATEGORIES = {
        "identidad", "trabajo", "proyectos", "vida_personal",
        "metas", "preferencias", "relaciones", "ritmo", "hechos"
    }
    return category in VALID_CATEGORIES


# Mapeo explícito columna→nombre SQL validado (previene f-string injection)
CATEGORY_COLUMN_MAP = {
    "identidad":     "identidad",
    "trabajo":       "trabajo",
    "proyectos":     "proyectos",
    "vida_personal": "vida_personal",
    "metas":         "metas",
    "preferencias":  "preferencias",
    "relaciones":    "relaciones",
    "ritmo":         "ritmo",
    "hechos":        "hechos",
}


def safe_column_name(category: str) -> Optional[str]:
    """
    Retorna el nombre de columna SQL seguro para una categoría.
    Retorna None si la categoría no es válida.
    Usar en lugar de f-strings con nombres de columna.
    """
    return CATEGORY_COLUMN_MAP.get(category)


# ── 4. OAUTH STATE TOKENS (anti-CSRF) ────────────────────────

_oauth_states: dict[str, tuple[int, float]] = {}  # token → (user_id, expires_at)
_oauth_lock = threading.Lock()
OAUTH_STATE_TTL = 600  # 10 minutos


def generate_oauth_state(user_id: int) -> str:
    """
    Genera un token de estado OAuth para un user_id.
    El token expira en OAUTH_STATE_TTL segundos.
    Usar en cmd_connect_google() en lugar de pasar user_id directamente.
    """
    token = secrets.token_urlsafe(32)
    expires = time.monotonic() + OAUTH_STATE_TTL
    with _oauth_lock:
        # Limpiar tokens expirados del mismo usuario
        _oauth_states[token] = (user_id, expires)
        _cleanup_oauth_states()
    logger.debug(f"OAuth state generado para user_id={user_id}")
    return token


def validate_oauth_state(token: str) -> Optional[int]:
    """
    Valida un token de estado OAuth y retorna el user_id asociado.
    Retorna None si el token es inválido o expiró.
    El token se consume (one-time use).
    """
    with _oauth_lock:
        entry = _oauth_states.pop(token, None)
        if entry is None:
            logger.warning(f"OAuth state inválido o ya usado: {token[:8]}...")
            return None
        user_id, expires = entry
        if time.monotonic() > expires:
            logger.warning(f"OAuth state expirado para user_id={user_id}")
            return None
        return user_id


def _cleanup_oauth_states():
    """Elimina tokens expirados (llamar con _oauth_lock adquirido)."""
    now = time.monotonic()
    expired = [t for t, (_, exp) in _oauth_states.items() if now > exp]
    for t in expired:
        del _oauth_states[t]


# ── 5. AUDIT LOGGER ──────────────────────────────────────────

_audit_logger = logging.getLogger("monday.audit")


def audit_log(
    admin_id: int,
    action: str,
    target_user_id: Optional[int] = None,
    details: str = "",
    success: bool = True,
) -> None:
    """
    Registra una acción administrativa en el audit log.

    Formato del log:
        AUDIT | admin=<id> | action=<action> | target=<id> | ok=<bool> | <details>

    Estas líneas van al mismo stream de logs de Railway y pueden ser
    filtradas con: railway logs | grep AUDIT
    """
    target_str = f"target={target_user_id}" if target_user_id else "target=N/A"
    status     = "✅" if success else "❌"
    _audit_logger.info(
        f"AUDIT | admin={admin_id} | action={action} | "
        f"{target_str} | ok={success} {status}"
        + (f" | {details}" if details else "")
    )


# ── 6. VALIDACIÓN DE ARRANQUE ────────────────────────────────

def validate_startup_config() -> list[str]:
    """
    Valida la configuración de seguridad al arrancar.
    Retorna lista de advertencias (vacía = todo ok).
    Llamar desde bot.py antes de iniciar la Application.
    """
    warnings = []

    # ENCRYPTION_KEY
    if not os.getenv("ENCRYPTION_KEY"):
        warnings.append(
            "ENCRYPTION_KEY no configurada — los tokens de Google se guardan sin cifrar. "
            "Genera una con: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # ADMIN_USER_IDS
    admin_ids_raw = os.getenv("ADMIN_USER_IDS", "")
    valid_ids = [x.strip() for x in admin_ids_raw.split(",") if x.strip().isdigit()]
    if not valid_ids:
        warnings.append(
            "ADMIN_USER_IDS no configurado o inválido. "
            "Los comandos /admin no tendrán acceso. "
            "Configura tu Telegram user_id numérico."
        )

    # RAILWAY_PUBLIC_URL — debe ser HTTPS en producción
    pub_url = os.getenv("RAILWAY_PUBLIC_URL", "")
    if pub_url and not pub_url.startswith("https://"):
        warnings.append(
            f"RAILWAY_PUBLIC_URL no usa HTTPS: {pub_url}. "
            "El callback de OAuth debe ser HTTPS en producción."
        )

    return warnings
