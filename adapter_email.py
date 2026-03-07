"""
adapter_email.py — Adapter de Email para Monday Bot.

ESTADO: stub — arquitectura lista, pendiente de implementar.

Para activar este canal:
  1. Crear cuenta en SendGrid (sendgrid.com) — tier gratuito: 100 emails/día
  2. Configurar Inbound Parse: Settings > Inbound Parse > Add Host & URL
     - Hostname: un subdominio tuyo (ej. monday.tudominio.com)
     - URL: https://tu-railway-app.railway.app/webhook/email
  3. Apuntar el registro MX del subdominio a mx.sendgrid.net
  4. Obtener la API key de SendGrid (Settings > API Keys)
  5. Agregar las variables de entorno en Railway
  6. Descomentar el registro en bot.py

Variables de entorno requeridas:
  SENDGRID_API_KEY           — API key de SendGrid para envío
  SENDGRID_WEBHOOK_SECRET    — para verificar el webhook (opcional pero recomendado)
  MONDAY_EMAIL               — dirección que recibe correos (ej. monday@tudominio.com)

Flujo de un email entrante:
  Usuario envía correo a monday@tudominio.com
    → SendGrid parsea y hace POST a /webhook/email
    → _parse_inbound()         extrae from, subject, body del multipart
    → memory.resolve_channel() resuelve email → monday_id
    → channel_router.process_message(msg, send_fn)
    → _send_email()            responde al mismo hilo

Diferencias clave vs mensajería:
  - El asunto se pasa como contexto adicional al core engine
  - El hilo se mantiene via In-Reply-To / References headers
  - Las respuestas son más largas (channel_style EMAIL lo maneja)
  - Latencia de entrega: 5-30 segundos, no tiempo real

Referencia: https://docs.sendgrid.com/for-developers/parsing-email/inbound-email
"""

import os
import logging
from aiohttp import web

import memory
import channel_router
from channel_types import InboundMessage, ChannelType

logger = logging.getLogger(__name__)

SENDGRID_API_KEY        = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_WEBHOOK_SECRET = os.getenv("SENDGRID_WEBHOOK_SECRET", "")
MONDAY_EMAIL            = os.getenv("MONDAY_EMAIL", "monday@assistant.example.com")
SENDGRID_SEND_URL       = "https://api.sendgrid.com/v3/mail/send"


# ── Recepción de emails (POST multipart) ─────────────────────

async def webhook_inbound(request: web.Request) -> web.Response:
    """
    Recibe el POST de SendGrid Inbound Parse.
    El payload es multipart/form-data con campos: from, to, subject, text, html, headers.
    Siempre responder 200 — SendGrid reintenta si no recibe 200.
    """
    try:
        data = await request.post()
        await _handle_inbound(data)
    except Exception as e:
        logger.error(f"Error procesando email inbound: {e}")

    return web.Response(text="OK")


async def _handle_inbound(data: dict):
    """
    Procesa un email entrante parseado por SendGrid.

    TODO: implementar completamente.
    """
    sender  = data.get("from", "")
    subject = data.get("subject", "")
    body    = data.get("text", data.get("html", "")).strip()
    headers = data.get("headers", "")

    # Extraer email limpio del sender (puede venir como "Nombre <email@...>")
    import re
    email_match = re.search(r'<([^>]+)>', sender)
    from_email  = email_match.group(1) if email_match else sender.strip()

    if not from_email or not body:
        logger.warning("Email inbound sin from o sin body — ignorado")
        return

    # Extraer In-Reply-To para mantener el hilo
    thread_match = re.search(r'In-Reply-To:\s*(<[^>]+>)', headers, re.IGNORECASE)
    thread_id    = thread_match.group(1) if thread_match else ""

    # Resolver identidad cross-canal
    monday_id = memory.resolve_channel_id(ChannelType.EMAIL, from_email)
    if monday_id is None:
        logger.info(f"Email: dirección nueva {from_email}, pendiente de vincular")
        await _send_email(
            to=from_email,
            subject=f"Re: {subject}",
            body=(
                "Hola, soy Monday — tu asistente personal.\n\n"
                "Para usar el bot por email necesitas vincular tu dirección con tu cuenta de Telegram.\n\n"
                "TODO: incluir instrucciones de vinculación.\n\n"
                "— Monday"
            ),
        )
        return

    # Limpiar el cuerpo: eliminar quoted text de replies anteriores
    body_clean = _strip_quoted_text(body)

    inbound = InboundMessage(
        monday_id=monday_id,
        channel=ChannelType.EMAIL,
        text=body_clean,
        subject=subject,
        thread_id=thread_id,
        raw=dict(data),
    )

    async def send_fn(reply: str):
        await _send_email(
            to=from_email,
            subject=f"Re: {subject}" if not subject.startswith("Re:") else subject,
            body=reply,
            in_reply_to=thread_id,
        )

    await channel_router.process_message(inbound, send_fn=send_fn)


def _strip_quoted_text(body: str) -> str:
    """
    Elimina el texto citado de un email (las líneas con '>' o el bloque
    'On ... wrote:').  Devuelve solo el contenido nuevo.
    TODO: hacer más robusto con varios clientes de correo.
    """
    lines  = body.split("\n")
    clean  = []
    for line in lines:
        stripped = line.strip()
        # Detener en el bloque de quote
        if stripped.startswith(">") or stripped.startswith("On ") and "wrote:" in stripped:
            break
        clean.append(line)
    return "\n".join(clean).strip()


# ── Envío de emails ───────────────────────────────────────────

async def _send_email(to: str, subject: str, body: str, in_reply_to: str = ""):
    """
    Envía un email via SendGrid API.
    TODO: implementar cuando se activen las credenciales.
    """
    import httpx
    headers = {
        "Authorization": f"Bearer {SENDGRID_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload: dict = {
        "personalizations": [{"to": [{"email": to}]}],
        "from":    {"email": MONDAY_EMAIL, "name": "Monday"},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    if in_reply_to:
        payload["headers"] = {"In-Reply-To": in_reply_to, "References": in_reply_to}

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(SENDGRID_SEND_URL, json=payload, headers=headers)
        if r.status_code not in (200, 202):
            logger.error(f"Error enviando email a {to}: {r.status_code} {r.text[:200]}")
        else:
            logger.info(f"Email enviado a {to}: {subject}")


# ── Registro de rutas ─────────────────────────────────────────

def register_routes(app: web.Application) -> None:
    """
    Registra las rutas del adapter en el servidor aiohttp.
    Llamar desde bot.py cuando se active el canal.
    """
    app.router.add_post("/webhook/email", webhook_inbound)
    logger.info("Email adapter: rutas registradas (pendiente de activar)")
