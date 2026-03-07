"""
adapter_slack.py — Adapter de Slack para Monday Bot.

ESTADO: stub — arquitectura lista, pendiente de implementar.

Para activar este canal:
  1. Crear una Slack App en https://api.slack.com/apps
  2. Activar "Event Subscriptions" y suscribirse a message.im (DMs)
  3. Activar "Socket Mode" (recomendado — no requiere URL pública)
  4. Instalar la app en el workspace y obtener los tokens
  5. Agregar las variables de entorno en Railway
  6. Descomentar el registro en bot.py

Variables de entorno requeridas:
  SLACK_BOT_TOKEN     — xoxb-... token del bot
  SLACK_APP_TOKEN     — xapp-... token para Socket Mode
  SLACK_SIGNING_SECRET — para verificar requests si no usas Socket Mode

Flujo de un DM entrante:
  Slack evento message.im
    → _handle_dm()             convierte evento Slack a InboundMessage
    → memory.resolve_channel() resuelve slack_user_id → monday_id
    → channel_router.process_message(msg, send_fn)
    → _send_text()

Ventaja de Slack: Block Kit permite UI rica (botones, menús, etc.) para
comandos como /mi_dominio o confirmaciones. Ver _send_blocks() para el futuro.

Sin soporte de voz: Slack no ofrece API de audio en DMs.

Referencia: https://api.slack.com/apis/events-api
            https://slack.dev/bolt-python/
"""

import os
import logging
from aiohttp import web

import memory
import channel_router
from channel_types import InboundMessage, ChannelType

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN      = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN      = os.getenv("SLACK_APP_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_API_URL        = "https://slack.com/api"


# ── Verificación de firma (seguridad) ────────────────────────

def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verifica que el request viene de Slack usando HMAC SHA-256.
    Obligatorio en producción si no se usa Socket Mode.
    TODO: implementar.
    """
    import hmac
    import hashlib
    base_string  = f"v0:{timestamp}:{request_body.decode()}".encode()
    expected_sig = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), base_string, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, signature)


# ── Recepción de eventos (POST) ──────────────────────────────

async def webhook_events(request: web.Request) -> web.Response:
    """
    Recibe eventos de Slack via Events API (modo webhook).
    Alternativa: usar Slack Bolt con Socket Mode (sin esta ruta).

    TODO: implementar completamente.
    """
    payload = await request.json()

    # Verificación de URL (Slack envía un challenge al configurar)
    if payload.get("type") == "url_verification":
        return web.json_response({"challenge": payload["challenge"]})

    # Procesar evento
    event = payload.get("event", {})
    if event.get("type") == "message" and not event.get("bot_id"):
        # Es un DM de un usuario real (no del propio bot)
        await _handle_dm(event)

    return web.Response(text="OK")


async def _handle_dm(event: dict):
    """
    Convierte un evento de DM de Slack a InboundMessage y lo enruta.

    TODO: implementar completamente.
    """
    slack_user_id = event.get("user")
    text          = event.get("text", "").strip()
    channel_id    = event.get("channel")  # canal del DM (para responder)

    if not slack_user_id or not text:
        return

    # Resolver identidad cross-canal
    monday_id = memory.resolve_channel_id(ChannelType.SLACK, slack_user_id)
    if monday_id is None:
        logger.info(f"Slack: usuario nuevo {slack_user_id}, pendiente de vincular")
        await _send_text(channel_id, "Hola, soy Monday. Para usar el bot en Slack necesitas vincularlo con tu cuenta. TODO: flujo de vinculación.")
        return

    inbound = InboundMessage(
        monday_id=monday_id,
        channel=ChannelType.SLACK,
        text=text,
        raw=event,
    )

    async def send_fn(reply: str):
        await _send_text(channel_id, reply)

    await channel_router.process_message(inbound, send_fn=send_fn)


# ── Envío de mensajes ─────────────────────────────────────────

async def _send_text(channel: str, text: str):
    """
    Envía un mensaje de texto a un canal/DM de Slack.
    TODO: implementar cuando se activen las credenciales.
    """
    import httpx
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "channel": channel,
        "text":    text[:4000],  # límite de Slack
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{SLACK_API_URL}/chat.postMessage",
                              json=payload, headers=headers)
        data = r.json()
        if not data.get("ok"):
            logger.error(f"Error enviando Slack a {channel}: {data.get('error')}")


async def _send_blocks(channel: str, blocks: list, fallback_text: str = ""):
    """
    Envía un mensaje con Block Kit (UI rica).
    Usar para confirmaciones, menús de dominio, etc.
    TODO: implementar y usar en flows interactivos.
    """
    import httpx
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "channel": channel,
        "text":    fallback_text,
        "blocks":  blocks,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{SLACK_API_URL}/chat.postMessage",
                          json=payload, headers=headers)


# ── Registro de rutas ─────────────────────────────────────────

def register_routes(app: web.Application) -> None:
    """
    Registra las rutas del adapter en el servidor aiohttp.
    Llamar desde bot.py cuando se active el canal.
    """
    app.router.add_post("/webhook/slack", webhook_events)
    logger.info("Slack adapter: rutas registradas (pendiente de activar)")
