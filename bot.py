"""
bot.py — Asistente personal en Telegram con memoria y Google Workspace.

Stack:
  - python-telegram-bot  →  Telegram
  - Groq REST API        →  IA (LLaMA 3.3)
  - httpx                →  HTTP async
  - memory.py            →  Memoria persistente en PostgreSQL
  - google_auth.py       →  OAuth 2.0 con Google
  - google_services.py   →  Calendar, Gmail, Docs, Sheets, Drive
  - aiohttp              →  Servidor web para el callback de OAuth
"""

import os
import re
import json
import logging
import asyncio
import httpx
from aiohttp import web
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import memory
import google_auth
import google_services
import google_services

# ── Configuración ────────────────────────────────────────────
load_dotenv()

TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
RAILWAY_PUBLIC_URL = os.getenv("RAILWAY_PUBLIC_URL", "http://localhost:8080")
PORT               = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Falta TELEGRAM_TOKEN o GROQ_API_KEY en el archivo .env")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Referencia global al bot para usarla en el callback de OAuth
telegram_app = None

# ── Prompt base ───────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """Eres un asistente personal inteligente con acceso a Google Workspace.

Puedes ayudar con:
- 📅 Google Calendar: agendar, consultar y eliminar eventos
- 📧 Gmail: leer, buscar y enviar correos
- 📄 Google Docs: crear y consultar documentos
- 📊 Google Sheets: crear hojas y registrar datos
- 💾 Google Drive: buscar y listar archivos

Reglas:
1. Responde siempre en el idioma del usuario.
2. Cuando el usuario quiera realizar una acción de Google Workspace, responde con un bloque
   JSON especial al FINAL de tu mensaje con este formato exacto:
   [ACTION: {"service": "calendar|gmail|docs|sheets|drive", "action": "nombre_accion", "params": {...}}]
3. Si el usuario no ha conectado Google, dile que use /conectar_google.
4. Recuerda siempre lo que sabes del usuario y personaliza tus respuestas.
5. Sé conciso y útil.

Acciones disponibles por servicio:
- calendar: list_events, create_event, delete_event
- gmail: list_emails, send_email, get_email
- docs: create, get_content, append_text
- sheets: create, read, append, write
- drive: list_files, search

Ejemplos de [ACTION]:
[ACTION: {"service": "calendar", "action": "list_events", "params": {"days": 7}}]
[ACTION: {"service": "gmail", "action": "send_email", "params": {"to": "juan@gmail.com", "subject": "Hola", "body": "¿Cómo estás?"}}]
[ACTION: {"service": "docs", "action": "create", "params": {"title": "Mi documento", "content": "Contenido inicial"}}]

Al final de tu respuesta, si aprendiste algo nuevo del usuario:
[FACT: descripción breve]
"""


# ── Llamada a Groq ────────────────────────────────────────────
async def call_groq(system_prompt: str, history: list, user_text: str) -> str:
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"].strip()


# ── Ejecutar acción de Google ────────────────────────────────
async def execute_google_action(user_id: int, action_data: dict) -> str:
    """Ejecuta la acción de Google Workspace y retorna un resumen del resultado."""
    service = action_data.get("service")
    action  = action_data.get("action")
    params  = action_data.get("params", {})

    try:
        # ── Calendar ──
        if service == "calendar":
            if action == "list_events":
                events = await google_services.get_upcoming_events(user_id, **params)
                if not events:
                    return "No tienes eventos próximos."
                lines = [f"📅 *Próximos eventos:*"]
                for e in events:
                    start_time = e.get('start', {}).get('dateTime', e.get('start', {}).get('date', ''))[:16].replace('T', ' ')
                    lines.append(f"• {e.get('summary', 'Sin título')} — {start_time}")
                return "\n".join(lines)

            elif action == "create_event":
                result = await google_services.create_event(user_id, **params)
                return f"✅ Evento creado: {result.get('summary', 'Evento')} — {result.get('htmlLink', '')}"

            elif action == "delete_event":
                await google_services.delete_event(user_id, **params)
                return "✅ Evento eliminado."

        # ── Gmail ──
        elif service == "gmail":
            if action == "list_emails":
                emails = await google_services.get_recent_emails(user_id, **params)
                if not emails:
                    return "No hay correos nuevos."
                lines = ["📧 *Correos recientes:*"]
                for e in emails:
                    lines.append(f"• {e.get('Subject', e.get('subject', 'Sin asunto'))} — {e.get('From', e.get('from', '?'))[:40]}")
                return "\n".join(lines)

            elif action == "send_email":
                await google_services.send_email(user_id, **params)
                return f"✅ Correo enviado a {params.get('to')}."

            elif action == "get_email":
                email = await google_services.get_recent_emails(user_id, **params)
                return f"📧 De: {email.get('From', '?')}\nAsunto: {email.get('Subject', '?')}"

        # ── Docs ──
        elif service == "docs":
            if action == "create":
                result = await google_services.create_doc(user_id, **params)
                return f"✅ Documento creado: {result.get('url', result.get('documentId', ''))}"

            elif action == "get_content":
                content = await google_services.get_doc_content(user_id, **params)
                return f"📄 *Contenido del documento:*\n{content[:1000]}"

            elif action == "append_text":
                await google_services.create_doc(user_id, **params)
                return "✅ Texto agregado al documento."

        # ── Sheets ──
        elif service == "sheets":
            if action == "create":
                result = await google_services.append_to_sheet(user_id, **params)
                return f"✅ Hoja creada: [abrir]({result['link']})"

            elif action == "read":
                data = await google_services.read_sheet(user_id, **params)
                if not data:
                    return "La hoja está vacía."
                rows = "\n".join([" | ".join(row) for row in data[:10]])
                return f"📊 *Datos:*\n```\n{rows}\n```"

            elif action == "append":
                result = await google_services.append_to_sheet(user_id, **params)
                return f"✅ {result['updated_rows']} fila(s) agregada(s)."

            elif action == "write":
                result = await google_services.append_to_sheet(user_id, **params)
                return f"✅ {result['updated_cells']} celda(s) actualizadas."

        # ── Drive ──
        elif service == "drive":
            if action in ("list_files", "search"):
                files = await google_services.list_recent_files(user_id, **params)
                if not files:
                    return "No se encontraron archivos."
                lines = ["💾 *Archivos encontrados:*"]
                for f in files:
                    lines.append(f"• [{f['name']}]({f['link']})")
                return "\n".join(lines)

        return "⚠️ Acción no reconocida."

    except PermissionError:
        return "⚠️ No has conectado tu cuenta de Google. Usa /conectar_google."
    except Exception as e:
        logger.error(f"Error ejecutando acción Google: {e}")
        return f"⚠️ Error al ejecutar la acción: {str(e)[:100]}"


# ── Procesar mensaje principal ────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id   = update.effective_user.id
    user_name = update.effective_user.first_name or "Usuario"
    user_text = update.message.text

    logger.info(f"Mensaje de {user_name} ({user_id}): {user_text}")

    # Agregar estado de conexión Google al contexto
    google_status = "✅ Conectado" if memory.has_google_connected(user_id) else "❌ No conectado (usa /conectar_google)"
    system_prompt = memory.build_system_prompt(user_id, BASE_SYSTEM_PROMPT)
    system_prompt += f"\n\nEstado Google Workspace del usuario: {google_status}"

    hist = memory.get_history(user_id)
    await update.message.chat.send_action("typing")

    try:
        full_reply = await call_groq(system_prompt, hist, user_text)
    except Exception as e:
        logger.error(f"Error llamando a Groq: {e}")
        await update.message.reply_text("Ups, hubo un problema. Intenta en un momento 🙏")
        return

    # Extraer y ejecutar acciones de Google
    action_match = re.search(r'\[ACTION:\s*({.+?})\]', full_reply, re.DOTALL)
    action_result = ""
    if action_match:
        try:
            action_data = json.loads(action_match.group(1))
            action_result = await execute_google_action(user_id, action_data)
        except json.JSONDecodeError:
            logger.error("No se pudo parsear el ACTION JSON")

    # Extraer FACTs
    facts_found = re.findall(r'\[FACT:\s*(.+?)\]', full_reply)
    for fact in facts_found:
        memory.add_fact(user_id, fact.strip())

    # Limpiar la respuesta
    clean_reply = re.sub(r'\[ACTION:.*?\]', '', full_reply, flags=re.DOTALL)
    clean_reply = re.sub(r'\[FACT:.*?\]', '', clean_reply)
    clean_reply = clean_reply.strip()

    # Guardar en historial
    memory.add_message(user_id, "user", user_text)
    memory.add_message(user_id, "assistant", clean_reply)

    # Enviar respuesta
    if clean_reply:
        await update.message.reply_text(clean_reply)

    # Enviar resultado de la acción Google si hay
    if action_result:
        await update.message.reply_text(action_result)


# ── Comandos ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "!"
    await update.message.reply_text(
        f"¡Hola {name}! 👋 Soy tu asistente personal con acceso a Google Workspace.\n\n"
        "Puedo ayudarte con tu calendario, correos, documentos y más.\n\n"
        "Para conectar tu cuenta de Google usa:\n"
        "  /conectar_google\n\n"
        "Otros comandos:\n"
        "  /memoria  — ver lo que sé de ti\n"
        "  /olvidar  — borrar mi memoria\n"
        "  /estado   — ver estado de conexiones\n"
        "  /ayuda    — ver todos los comandos"
    )


async def cmd_connect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if memory.has_google_connected(user_id):
        await update.message.reply_text(
            "✅ Ya tienes tu cuenta de Google conectada.\n"
            "Si quieres reconectar usa /desconectar_google primero."
        )
        return

    auth_url = google_auth.get_auth_url(user_id)
    await update.message.reply_text(
        "Para conectar tu cuenta de Google, abre este link y autoriza el acceso:\n\n"
        f"{auth_url}\n\n"
        "Después de autorizar, regresa aquí y el bot confirmará la conexión automáticamente."
    )


async def cmd_disconnect_google(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    memory.save_google_tokens(user_id, None)
    await update.message.reply_text("✅ Cuenta de Google desconectada.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    google_ok = "✅ Conectado" if memory.has_google_connected(user_id) else "❌ No conectado"
    facts_count = len(memory.get_facts(user_id))
    await update.message.reply_text(
        f"📊 *Estado de tu asistente:*\n\n"
        f"Google Workspace: {google_ok}\n"
        f"Hechos en memoria: {facts_count}\n\n"
        f"Usa /conectar_google para vincular tu cuenta de Google.",
        parse_mode="Markdown"
    )


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    facts   = memory.get_facts(user_id)
    if not facts:
        await update.message.reply_text("Todavía no sé mucho sobre ti. ¡Cuéntame más! 😊")
    else:
        facts_list = "\n".join(f"• {f}" for f in facts)
        await update.message.reply_text(f"Esto es lo que sé sobre ti:\n\n{facts_list}")


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    memory.clear_memory(update.effective_user.id)
    await update.message.reply_text("Listo, borré toda mi memoria sobre ti. 🧹")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos disponibles:\n\n"
        "/start              — iniciar el asistente\n"
        "/conectar_google    — vincular cuenta de Google\n"
        "/desconectar_google — desvincular cuenta de Google\n"
        "/estado             — ver estado de conexiones\n"
        "/memoria            — ver lo que sé de ti\n"
        "/olvidar            — borrar mi memoria\n"
        "/ayuda              — este mensaje\n\n"
        "Ejemplos de lo que puedes pedirme:\n"
        "• ¿Qué tengo en el calendario esta semana?\n"
        "• Agéndame una reunión mañana a las 3pm\n"
        "• ¿Tengo correos sin leer?\n"
        "• Envíale un correo a juan@gmail.com\n"
        "• Crea un documento con mis notas de hoy\n"
        "• Busca el archivo de presupuesto en Drive"
    )


# ── Servidor OAuth callback ───────────────────────────────────
async def oauth_callback(request: web.Request) -> web.Response:
    """Recibe el callback de Google OAuth y guarda el token."""
    code     = request.rel_url.query.get("code")
    state    = request.rel_url.query.get("state")   # user_id
    error    = request.rel_url.query.get("error")

    if error or not code or not state:
        return web.Response(text="Error en la autorización. Cierra esta ventana y vuelve a intentarlo.", content_type="text/html")

    try:
        user_id = int(state)

        # Intercambiar código por tokens usando httpx (sin SDK)
        tokens = await google_auth.exchange_code_for_tokens(code)
        from datetime import datetime, timedelta
        tokens["expires_at"] = (
            datetime.now() + timedelta(seconds=tokens.get("expires_in", 3600))
        ).isoformat()
        memory.save_google_tokens(user_id, tokens)

        # Notificar al usuario en Telegram
        if telegram_app:
            await telegram_app.bot.send_message(
                chat_id=user_id,
                text="✅ ¡Google conectado exitosamente!\n\n"
                     "Ya puedo acceder a tu Calendar, Gmail, Docs, Sheets y Drive.\n"
                     "¿En qué te puedo ayudar?"
            )

        return web.Response(
            text="<h2>✅ ¡Conexión exitosa!</h2><p>Puedes cerrar esta ventana y volver a Telegram.</p>",
            content_type="text/html"
        )

    except Exception as e:
        logger.error(f"Error en OAuth callback: {e}")
        return web.Response(text=f"Error: {e}", content_type="text/html")


async def start_web_server():
    """Inicia el servidor web para el callback de OAuth."""
    app = web.Application()
    app.router.add_get("/oauth/callback", oauth_callback)
    app.router.add_get("/health", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"✅ Servidor OAuth iniciado en puerto {PORT}")


# ── Arrancar todo ─────────────────────────────────────────────
async def main():
    global telegram_app

    telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start",              cmd_start))
    telegram_app.add_handler(CommandHandler("conectar_google",    cmd_connect_google))
    telegram_app.add_handler(CommandHandler("desconectar_google", cmd_disconnect_google))
    telegram_app.add_handler(CommandHandler("estado",             cmd_status))
    telegram_app.add_handler(CommandHandler("memoria",            cmd_memory))
    telegram_app.add_handler(CommandHandler("olvidar",            cmd_forget))
    telegram_app.add_handler(CommandHandler("ayuda",              cmd_help))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Iniciar servidor web y bot en paralelo
    await start_web_server()

    logger.info("✅ Bot iniciado. Esperando mensajes...")

    async with telegram_app:
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
