"""
adapter_whatsapp.py — Adapter de WhatsApp para Monday Bot.

ESTADO: stub — arquitectura lista, pendiente de implementar.

Para activar este canal:
  1. Crear una aplicación en Meta for Developers (developers.facebook.com)
  2. Agregar el producto "WhatsApp" y configurar un número de teléfono
  3. Obtener WHATSAPP_TOKEN y WHATSAPP_PHONE_ID del panel de Meta
  4. Configurar el webhook en Meta apuntando a /webhook/whatsapp en Railway
  5. Agregar las variables de entorno en Railway
  6. Descomentar el registro en bot.py

Variables de entorno requeridas:
  WHATSAPP_TOKEN       — Bearer token de la Graph API
  WHATSAPP_PHONE_ID    — ID del número de teléfono de WhatsApp Business
  WHATSAPP_VERIFY_TOKEN — Token de verificación del webhook (inventado por ti)

Flujo de un mensaje entrante:
  Meta POST /webhook/whatsapp
    → _parse_inbound()         convierte payload de Meta a InboundMessage
    → memory.resolve_channel() resuelve channel_id → monday_id
    → channel_router.process_message(msg, send_fn)
    → _send_text() / _send_audio()

Limitación de WhatsApp:
  Los mensajes proactivos (briefing, heartbeat) solo se pueden enviar usando
  Message Templates aprobados por Meta. Para notificaciones del scheduler,
  crear templates en el panel de Meta y registrarlos en scheduler.py.

Referencia: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import os
import logging
from aiohttp import web

import memory
import channel_router
import audio_handler
from channel_types import InboundMessage, ChannelType

logger = logging.getLogger(__name__)

WHATSAPP_TOKEN        = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID     = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
GRAPH_API_URL         = "https://graph.facebook.com/v19.0"


# ── Verificación del webhook (GET) ───────────────────────────

async def webhook_verify(request: web.Request) -> web.Response:
    """
    Meta verifica el webhook enviando un GET con hub.challenge.
    Hay que responder con el challenge si el verify_token coincide.
    """
    mode      = request.rel_url.query.get("hub.mode")
    token     = request.rel_url.query.get("hub.verify_token")
    challenge = request.rel_url.query.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verificado")
        return web.Response(text=challenge)

    return web.Response(status=403, text="Forbidden")


# ── Recepción de mensajes (POST) ─────────────────────────────

async def webhook_receive(request: web.Request) -> web.Response:
    """
    Recibe eventos de Meta (mensajes, estado de entrega, etc).
    Solo procesa mensajes de texto y audio entrantes.

    TODO: implementar cuando se activen las credenciales de Meta.
    """
    # Siempre responder 200 rápido para que Meta no reintente
    payload = await request.json()
    logger.debug(f"WhatsApp payload: {payload}")

    try:
        entry    = payload.get("entry", [{}])[0]
        changes  = entry.get("changes", [{}])[0]
        value    = changes.get("value", {})
        messages = value.get("messages", [])

        for raw_msg in messages:
            await _handle_incoming(raw_msg)

    except Exception as e:
        logger.error(f"Error procesando webhook de WhatsApp: {e}")

    return web.Response(text="OK")


async def _handle_incoming(raw_msg: dict):
    """
    Convierte un mensaje de Meta a InboundMessage y lo enruta al core.

    TODO: implementar completamente.
    """
    msg_type = raw_msg.get("type")
    phone    = raw_msg.get("from")  # número de teléfono del remitente

    # Resolver identidad cross-canal
    monday_id = memory.resolve_channel_id(ChannelType.WHATSAPP, phone)
    if monday_id is None:
        # Usuario nuevo en WhatsApp — TODO: iniciar onboarding o vincular a cuenta existente
        logger.info(f"WhatsApp: nuevo número {phone}, pendiente de vincular")
        await _send_text(phone, "Hola, soy Monday. Para usar el bot en WhatsApp necesitas vincularlo con tu cuenta. TODO: flujo de vinculación.")
        return

    text = ""
    is_voice = False

    if msg_type == "text":
        text = raw_msg.get("text", {}).get("body", "")

    elif msg_type == "audio":
        # TODO: descargar audio con Graph API y transcribir con audio_handler.transcribe()
        media_id = raw_msg.get("audio", {}).get("id")
        logger.info(f"Audio recibido de {phone}, media_id={media_id} — pendiente STT")
        await _send_text(phone, "Recibí tu audio. La transcripción estará disponible pronto.")
        return

    else:
        logger.info(f"Tipo de mensaje no soportado: {msg_type}")
        return

    if not text:
        return

    inbound = InboundMessage(
        monday_id=monday_id,
        channel=ChannelType.WHATSAPP,
        text=text,
        is_voice=is_voice,
        raw=raw_msg,
    )

    async def send_fn(reply: str):
        await _send_text(phone, reply)

    await channel_router.process_message(inbound, send_fn=send_fn)


# ── Envío de mensajes ─────────────────────────────────────────

async def _send_text(to: str, text: str):
    """
    Envía un mensaje de texto via Graph API.
    TODO: implementar cuando se activen las credenciales.
    """
    import httpx
    url     = f"{GRAPH_API_URL}/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":                to,
        "type":              "text",
        "text":              {"body": text[:4096]},  # límite de WhatsApp
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code != 200:
            logger.error(f"Error enviando WhatsApp a {to}: {r.text}")


# ── Registro de rutas ─────────────────────────────────────────

def register_routes(app: web.Application) -> None:
    """
    Registra las rutas del adapter en el servidor aiohttp.
    Llamar desde bot.py cuando se active el canal.
    """
    app.router.add_get("/webhook/whatsapp",  webhook_verify)
    app.router.add_post("/webhook/whatsapp", webhook_receive)
    logger.info("WhatsApp adapter: rutas registradas (pendiente de activar)")
