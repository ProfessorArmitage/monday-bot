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
import onboarding
import workspace_memory
import conversation_context
import provisioning
import identity as identity_module
from scheduler import start_scheduler, init_scheduler

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
# System prompt cargado desde provisioning.py (versionado)
BASE_SYSTEM_PROMPT = provisioning.get_current_system_prompt()


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
                # Mapear period → days
                period = params.pop("period", None)
                if period == "day":   params["days"] = 1
                elif period == "week": params["days"] = 7
                elif period == "month": params["days"] = 30
                events = await google_services.get_upcoming_events(user_id, **params)
                if not events:
                    return "No tienes eventos en ese período."
                lines = ["📅 Eventos:"]
                for e in events:
                    start_time = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))[:16].replace("T", " ")
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
                lines = ["📧 Correos recientes:"]
                for e in emails:
                    lines.append(f"• {e.get('Subject','Sin asunto')}\n  De: {e.get('From','?')[:40]}\n  {e.get('snippet','')[:80]}")
                return "\n\n".join(lines)

            elif action == "send_email":
                await google_services.send_email(user_id, **params)
                return f"✅ Correo enviado a {params.get('to')}."

            elif action == "get_email":
                # Descarga el cuerpo completo del correo
                emails = await google_services.get_email_full(user_id, **params)
                if not emails:
                    return "No hay correos que coincidan."
                email = emails[0]
                body = email.get("Body", email.get("snippet", "Sin contenido"))[:1500]
                return (f"📧 De: {email.get('From','?')}\n"
                        f"Asunto: {email.get('Subject','Sin asunto')}\n"
                        f"Fecha: {email.get('Date','?')}\n\n"
                        f"{body}")

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
            if action == "list_files":
                files = await google_services.list_recent_files(user_id, **params)
                if not files:
                    return "No se encontraron archivos."
                lines = ["📁 Archivos recientes:"]
                for f in files:
                    lines.append(f"• {f.get('name','?')} — {f.get('webViewLink','')}")
                return "\n".join(lines)
            elif action == "search":
                files = await google_services.search_files(user_id, **params)
                if not files:
                    return "No se encontraron archivos con ese nombre."
                lines = ["🔍 Resultados:"]
                for f in files:
                    lines.append(f"• {f.get('name','?')} — {f.get('webViewLink','')}")
                return "\n".join(lines)

        return "⚠️ Acción no reconocida."

    except PermissionError:
        return "⚠️ No has conectado tu cuenta de Google. Usa /conectar_google."
    except Exception as e:
        logger.error(f"Error ejecutando acción Google: {e}")
        return f"⚠️ Error al ejecutar la acción: {str(e)[:100]}"


# ── Procesar mensaje principal ────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ── Interceptar respuestas de onboarding ──────────────────
    user_id = update.effective_user.id
    if onboarding.is_in_onboarding(user_id):
        await update.message.chat.send_action("typing")
        next_question = await onboarding.process_answer(
            user_id,
            update.message.text,
            call_groq
        )
        if next_question:
            await update.message.reply_text(next_question)
            # Si onboarding terminó y tiene Google, sincronizar al doc
            if not onboarding.is_in_onboarding(user_id) and memory.has_google_connected(user_id):
                import asyncio
                asyncio.create_task(workspace_memory.sync_memory_to_doc(user_id))
        return
    # ─────────────────────────────────────────────────────────
    user_id   = update.effective_user.id
    user_name = update.effective_user.first_name or "Usuario"
    user_text = update.message.text

    logger.info(f"Mensaje de {user_name} ({user_id}): {user_text}")


    # Agregar estado de conexión Google al contexto
    google_status = "✅ Conectado" if memory.has_google_connected(user_id) else "❌ No conectado (usa /conectar_google)"

    # Detectar contexto de la conversación
    ctx = conversation_context.detect_context(user_text)

    # Construir prompt con memoria completa + bloque de contexto enfocado
    system_prompt = memory.build_system_prompt(user_id, BASE_SYSTEM_PROMPT)
    system_prompt += f"\n\nEstado Google Workspace del usuario: {google_status}"

    # Agregar bloque de contexto específico de esta conversación
    context_block = conversation_context.build_context_prompt(user_id, ctx, memory)
    if context_block:
        system_prompt += context_block

    # Agregar hint de comportamiento según el contexto
    hint = conversation_context.get_context_hint(ctx)
    if hint:
        system_prompt += f"\n\nINSTRUCCIÓN DE CONTEXTO: {hint}"

    # Bootstrap: si el usuario ya tiene Google y no tiene doc todavía, crearlo
    if memory.has_google_connected(user_id):
        import asyncio
        asyncio.create_task(workspace_memory.bootstrap_existing_user(user_id))

    # Leer memoria extendida del Google Doc (en background, sin bloquear)
    if memory.has_google_connected(user_id):
        try:
            doc_content = await workspace_memory.read_memory_doc(user_id)
            if doc_content:
                system_prompt += (
                    "\n\n=== MEMORIA EXTENDIDA (Google Doc) ===\n"
                    + doc_content[:3000]
                    + "\n======================================"
                )
        except Exception as _e:
            logger.warning(f"No se pudo leer workspace doc: {_e}")

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
    # Sincronizar al Google Doc cuando se aprende algo nuevo
    if facts_found and memory.has_google_connected(user_id):
        import asyncio
        asyncio.create_task(workspace_memory.sync_memory_to_doc(user_id))

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
    user_id = update.effective_user.id
    tg_name = update.effective_user.first_name or ""

    if memory.is_new_user(user_id):
        # Usuario nuevo — saludo con identidad global + arrancar onboarding
        greeting = identity_module.get_new_user_greeting()
        await update.message.reply_text(greeting)
        first_question = onboarding.get_first_question(user_id)
        await update.message.reply_text(first_question)
    else:
        # Usuario conocido — saludo personalizado con su identidad
        user = memory.get_user(user_id)
        nombre = user.get("identidad", {}).get("nombre", tg_name)
        bot_identity = memory.get_bot_identity(user_id)
        greeting = identity_module.get_greeting(bot_identity, nombre)
        await update.message.reply_text(greeting)


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
    user = memory.get_user(user_id)

    sections = []

    identidad = user.get("identidad", {})
    if identidad:
        parts = [f"{k}: {v}" for k, v in identidad.items() if v]
        if parts: sections.append("👤 Identidad\n" + "\n".join(f"  • {p}" for p in parts))

    trabajo = user.get("trabajo", {})
    if trabajo:
        parts = [f"{k}: {v}" for k, v in trabajo.items() if v]
        if parts: sections.append("💼 Trabajo\n" + "\n".join(f"  • {p}" for p in parts))

    proyectos = user.get("proyectos", [])
    if proyectos:
        names = [p.get("nombre", str(p)) if isinstance(p, dict) else str(p) for p in proyectos]
        sections.append("🚀 Proyectos\n" + "\n".join(f"  • {n}" for n in names))

    metas = user.get("metas", {})
    if metas:
        parts = [f"{k}: {v}" for k, v in metas.items() if v]
        if parts: sections.append("🎯 Metas\n" + "\n".join(f"  • {p}" for p in parts))

    relaciones = user.get("relaciones", [])
    if relaciones:
        names = [f"{r.get('nombre','?')} ({r.get('relacion','?')})" if isinstance(r, dict) else str(r) for r in relaciones]
        sections.append("👥 Personas clave\n" + "\n".join(f"  • {n}" for n in names))

    ritmo = user.get("ritmo", {})
    if ritmo:
        parts = [f"{k}: {v}" for k, v in ritmo.items() if v]
        if parts: sections.append("⏰ Ritmo\n" + "\n".join(f"  • {p}" for p in parts))

    hechos = user.get("hechos", [])
    if hechos:
        sections.append("📝 Notas sueltas\n" + "\n".join(f"  • {h}" for h in hechos[-5:]))

    if sections:
        msg = "🧠 Lo que sé de ti:\n\n" + "\n\n".join(sections)
    else:
        msg = "Aún no sé mucho de ti. Usa /start para hacer la entrevista inicial."

    await update.message.reply_text(msg)


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

        # Crear documento de memoria en Google Drive
        import asyncio
        asyncio.create_task(workspace_memory.get_or_create_memory_doc(user_id))
        asyncio.create_task(workspace_memory.sync_memory_to_doc(user_id))

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



# ── Comandos de Skills y Heartbeat ───────────────────────────
async def cmd_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el catálogo de skills disponibles."""
    user_id = update.effective_user.id
    catalog = provisioning.get_skills_catalog_text()
    active = memory.get_skills(user_id)
    active_names = [s["name"] for s in active]

    msg = catalog
    if active_names:
        msg += f"\n\nTus skills activas: {', '.join(active_names)}"
    else:
        msg += "\n\nNo tienes skills activas. Usa /activar_skill [nombre] para activar una."

    await update.message.reply_text(msg)


async def cmd_activate_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activa una skill. Uso: /activar_skill correo formal"""
    user_id = update.effective_user.id
    name = " ".join(context.args) if context.args else ""

    if not name:
        await update.message.reply_text(
            "Uso: /activar_skill [nombre]\n"
            "Ejemplo: /activar_skill correo formal\n\n"
            "Mira el catalogo con /skills"
        )
        return

    skill = provisioning.find_skill_by_name(name)
    if not skill:
        await update.message.reply_text(
            f"No encontre una skill llamada '{name}'.\n"
            "Usa /skills para ver las disponibles."
        )
        return

    memory.save_skill(user_id, skill)
    await update.message.reply_text(
        f"{skill['emoji']} Skill {skill['name']} activada.\n{skill['description']}"
    )


async def cmd_deactivate_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desactiva una skill. Uso: /desactivar_skill correo formal"""
    user_id = update.effective_user.id
    name = " ".join(context.args) if context.args else ""

    skill = provisioning.find_skill_by_name(name)
    if not skill:
        await update.message.reply_text("No encontre esa skill. Usa /skills para ver las activas.")
        return

    memory.remove_skill(user_id, skill["id"])
    await update.message.reply_text(f"Skill {skill['name']} desactivada.")


async def cmd_heartbeat_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prueba manual del heartbeat."""
    from scheduler import heartbeat
    user_id = update.effective_user.id
    await update.message.reply_text("Ejecutando heartbeat manual, espera un momento...")
    await heartbeat(single_user=user_id)
    await update.message.reply_text("Heartbeat completado. Si no hubo alertas, todo esta en orden.")


async def cmd_my_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía al usuario el enlace a su Google Doc de memoria."""
    user_id = update.effective_user.id
    if not memory.has_google_connected(user_id):
        await update.message.reply_text("Primero conecta tu Google con /conectar_google")
        return
    await update.message.chat.send_action("typing")
    doc_id = await workspace_memory.get_or_create_memory_doc(user_id)
    if doc_id:
        url = f"https://docs.google.com/document/d/{doc_id}"
        await update.message.reply_text(
            f"Tu documento de memoria esta aqui:\n{url}\n\n"
            "Puedes editarlo directamente y tu asistente lo leera en cada conversacion."
        )
    else:
        await update.message.reply_text("No se pudo acceder al documento. Intenta de nuevo.")


async def cmd_sync_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sincroniza manualmente la memoria al Google Doc y viceversa."""
    user_id = update.effective_user.id
    if not memory.has_google_connected(user_id):
        await update.message.reply_text("Primero conecta tu Google con /conectar_google")
        return
    await update.message.chat.send_action("typing")
    # Primero leer cambios del doc
    await workspace_memory.sync_doc_to_memory(user_id)
    # Luego escribir memoria actualizada
    await workspace_memory.sync_memory_to_doc(user_id)
    doc_id = await workspace_memory.get_or_create_memory_doc(user_id)
    url = f"https://docs.google.com/document/d/{doc_id}" if doc_id else ""
    await update.message.reply_text(
        f"Sincronizacion completada.\n{url}"
    )


async def cmd_mi_asistente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ver y cambiar la identidad personalizada del asistente.

    Uso:
      /mi_asistente              → ver configuración actual
      /mi_asistente nombre Luna  → cambiar nombre
      /mi_asistente tono casual  → cambiar tono (formal|casual|directo)
      /mi_asistente frase [texto] → cambiar frase de trato
      /mi_asistente reset        → volver a identidad global
    """
    user_id = update.effective_user.id
    args = context.args or []

    if not args:
        # Mostrar configuración actual
        bot_identity = memory.get_bot_identity(user_id)
        msg = identity_module.describe_identity(bot_identity)
        await update.message.reply_text(msg)
        return

    subcmd = args[0].lower()

    if subcmd == "nombre" and len(args) > 1:
        nuevo_nombre = " ".join(args[1:])
        memory.update_bot_identity(user_id, nombre=nuevo_nombre)
        await update.message.reply_text(
            f"Listo — a partir de ahora me llamo *{nuevo_nombre}* para ti 😊",
            parse_mode="Markdown"
        )

    elif subcmd == "tono" and len(args) > 1:
        tono = args[1].lower()
        tonos_validos = ["formal", "casual", "directo"]
        if tono not in tonos_validos:
            await update.message.reply_text(
                f"Tono no reconocido. Opciones: {', '.join(tonos_validos)}"
            )
            return
        memory.update_bot_identity(user_id, tono=tono)
        await update.message.reply_text(f"Tono actualizado a: *{tono}* ✅", parse_mode="Markdown")

    elif subcmd == "frase" and len(args) > 1:
        frase = " ".join(args[1:])
        memory.update_bot_identity(user_id, frase=frase)
        await update.message.reply_text(
            f"Perfecto — trataré de ser: "{frase}" ✅"
        )

    elif subcmd == "reset":
        memory.set_bot_identity(user_id, {"activa": False})
        await update.message.reply_text(
            "Volví a la identidad global (Luma) ✅"
        )

    else:
        await update.message.reply_text(
            "Uso:
"
            "/mi_asistente               → ver configuración
"
            "/mi_asistente nombre Luna   → cambiar nombre
"
            "/mi_asistente tono casual   → formal | casual | directo
"
            "/mi_asistente frase [texto] → cómo quieres ser tratado
"
            "/mi_asistente reset         → volver a identidad global"
        )


async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la versión actual del bot y cuándo se actualizó."""
    user_id = update.effective_user.id
    user_version = memory.get_bot_version(user_id)
    user = memory.get_user(user_id)
    last_reprov = user.get("last_reprovisioned")
    last_str = str(last_reprov)[:16] if last_reprov else "nunca"

    msg = (
        f"Bot v{provisioning.MANIFEST_VERSION} (sistema)\n"
        f"Tu versión: v{user_version}\n"
        f"Última actualización: {last_str}\n\n"
    )
    if user_version != provisioning.MANIFEST_VERSION:
        msg += "Hay una actualización pendiente — se aplicará automáticamente."
    else:
        msg += "Estás en la versión más reciente."

    await update.message.reply_text(msg)


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
    telegram_app.add_handler(CommandHandler("skills",           cmd_skills))
    telegram_app.add_handler(CommandHandler("activar_skill",    cmd_activate_skill))
    telegram_app.add_handler(CommandHandler("desactivar_skill", cmd_deactivate_skill))
    telegram_app.add_handler(CommandHandler("heartbeat",        cmd_heartbeat_test))
    telegram_app.add_handler(CommandHandler("mi_doc",    cmd_my_doc))
    telegram_app.add_handler(CommandHandler("sincronizar", cmd_sync_doc))
    telegram_app.add_handler(CommandHandler("version", cmd_version))
    telegram_app.add_handler(CommandHandler("mi_asistente", cmd_mi_asistente))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Iniciar servidor web y bot en paralelo
    await start_web_server()

    # Arrancar scheduler (heartbeat, briefing, ritmo semanal, reprovisión)
    init_scheduler(telegram_app.bot, call_groq)
    start_scheduler()

    logger.info("✅ Bot iniciado. Esperando mensajes...")

    async with telegram_app:
        await telegram_app.start()

        # Reprovisión al arrancar: actualizar usuarios con versión vieja
        asyncio.create_task(provisioning.run_reprovisioning(memory, telegram_app.bot))

        await telegram_app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
