"""
google_auth.py — Maneja el flujo OAuth 2.0 de Google por usuario.

Flujo:
  1. Usuario ejecuta /conectar en Telegram
  2. Bot genera un URL de autorización y se lo envía
  3. Usuario abre el URL, autoriza en Google
  4. Google redirige a nuestro callback con un código
  5. Bot intercambia el código por tokens (access + refresh)
  6. Tokens se guardan en PostgreSQL por usuario
  7. Bot usa los tokens para llamar a las APIs de Google
"""

import os
import json
import httpx
from datetime import datetime, timedelta

# ── Credenciales de Google (desde .env / Railway Variables) ──
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
CALLBACK_URL         = os.getenv("CALLBACK_URL")  # ej: https://tu-app.railway.app/oauth/callback

# Scopes — permisos que pedimos al usuario
SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
])


def get_auth_url(telegram_user_id: int) -> str:
    """
    Genera el URL de autorización de Google.
    Incluye el telegram_user_id en el 'state' para saber
    a qué usuario pertenece el callback.
    """
    from urllib.parse import urlencode

    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  CALLBACK_URL,
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         str(telegram_user_id),
    }
    # urlencode escapa correctamente todos los caracteres especiales
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Intercambia el código de autorización por tokens de acceso.
    Devuelve dict con access_token, refresh_token, expires_in.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  CALLBACK_URL,
                "grant_type":    "authorization_code",
            }
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Renueva el access_token usando el refresh_token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_token,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "grant_type":    "refresh_token",
            }
        )
        response.raise_for_status()
        return response.json()


async def get_valid_token(user_id: int) -> str | None:
    """
    Devuelve un access_token válido para el usuario.
    Si expiró, lo renueva automáticamente con el refresh_token.
    Devuelve None si el usuario no ha conectado su cuenta.
    """
    import memory  # importar aquí para evitar circular imports

    tokens = memory.get_google_tokens(user_id)
    if not tokens:
        return None

    # Verificar si el token expiró (con 5 min de margen)
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if datetime.now() >= expires_at - timedelta(minutes=5):
        # Renovar el token
        new_tokens = await refresh_access_token(tokens["refresh_token"])
        tokens["access_token"] = new_tokens["access_token"]
        tokens["expires_at"] = (
            datetime.now() + timedelta(seconds=new_tokens["expires_in"])
        ).isoformat()
        memory.save_google_tokens(user_id, tokens)

    return tokens["access_token"]
