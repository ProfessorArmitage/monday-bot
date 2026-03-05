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
import skills as skills_engine
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

    # ── Normalizar params — Groq a veces usa nombres alternativos ──
    if service == "calendar" and action == "create_event":
        # Normalizar título: summary/name/evento → title
        for alt in ("summary", "name", "evento", "event_name", "titulo"):
            if alt in params and "title" not in params:
                params["title"] = params.pop(alt)
        # Normalizar start: start_time / startTime / fecha_inicio → start
        for alt in ("start_time", "startTime", "fecha_inicio", "inicio", "fecha_hora_inicio"):
            if alt in params and "start" not in params:
                params["start"] = params.pop(alt)
        # Normalizar end: end_time / endTime / fecha_fin → end
        for alt in ("end_time", "endTime", "fecha_fin", "fin", "fecha_hora_fin", "duration"):
            if alt in params and "end" not in params:
                if alt == "duration":
                    # Si Groq manda duración en minutos, calcular end desde start
                    try:
                        from datetime import datetime, timedelta
                        import tz_utils
                        start_str = params.get("start", "")
                        if start_str:
                            start_dt = datetime.fromisoformat(start_str)
                            end_dt = start_dt + timedelta(minutes=int(params.pop(alt)))
                            params["end"] = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
                    except Exception:
                        params.pop(alt, None)
                else:
                    params["end"] = params.pop(alt)
        # Eliminar campos que Google no acepta vía nuestra API
        for unknown in ("location", "recurrence", "reminders", "color", "visibility",
                        "guests", "participants", "conferenceData"):
            if unknown in params and unknown != "attendees":
                params.pop(unknown, None)
        # guests/participants → attendees
        for alt in ("guests", "participants", "invitados"):
            if alt in params and "attendees" not in params:
                params["attendees"] = params.pop(alt)

        logger.info(f"create_event params normalizados: {params}")

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

    # Fecha actual para que Groq pueda calcular fechas correctamente
    from datetime import datetime
    import tz_utils
    _user_data_for_tz = memory.get_user(user_id)
    _user_now = tz_utils.now_for_user(_user_data_for_tz)
    fecha_actual = _user_now.strftime("%Y-%m-%d %H:%M (%A)")

    # Detectar contexto de la conversación
    ctx = conversation_context.detect_context(user_text)

    # Construir prompt con memoria completa + bloque de contexto enfocado
    # Reemplazar {fecha_actual} en el prompt con la fecha real del usuario
    prompt_with_date = BASE_SYSTEM_PROMPT.replace("{fecha_actual}", fecha_actual)
    system_prompt = memory.build_system_prompt(user_id, prompt_with_date)
    system_prompt += f"\n\nEstado Google Workspace del usuario: {google_status}"

    # Agregar bloque de contexto específico de esta conversación
    context_block = conversation_context.build_context_prompt(user_id, ctx, memory)
    if context_block:
        system_prompt += context_block

    # Agregar hint de comportamiento según el contexto
    hint = conversation_context.get_context_hint(ctx)
    if hint:
        system_prompt += f"\n\nINSTRUCCIÓN DE CONTEXTO: {hint}"

    # Inyectar skills activas relevantes para este contexto
    active_skills = memory.get_skills(user_id)
    skills_block = skills_engine.build_skills_prompt_block(active_skills, ctx)
    if skills_block:
        system_prompt += skills_block

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
    # Auto-evolucionar skills cuando se aprenden hechos relevantes
    if facts_found:
        asyncio.create_task(skills_engine.auto_evolve_from_facts(
            user_id, [f.strip() for f in facts_found], memory, call_groq
        ))
    # Sincronizar al Google Doc cuando se aprende algo nuevo
    if facts_found and memory.has_google_connected(user_id):
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
            f"No encontré una skill llamada '{name}'.\n"
            "Usa /skills para ver el catálogo disponible."
        )
        return

    await update.message.chat.send_action("typing")
    skill_entry = await skills_engine.activate_skill_personalized(
        user_id, skill, memory, call_groq
    )
    has_personal = bool(skill_entry.get("content_personal"))
    personal_note = " y la personalicé con tu contexto 🎯" if has_personal else ""
    await update.message.reply_text(
        f"{skill_entry['emoji']} Skill *{skill_entry['name']}* activada ✅{personal_note}\n\n"
        f"{skill_entry['description']}",
        parse_mode="Markdown"
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


async def cmd_evolucion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Regenera la versión personalizada de una skill con la memoria actual.
    Uso: /evolucion [nombre_skill]   → evoluciona una skill específica
         /evolucion todas            → evoluciona todas las activas
    """
    user_id = update.effective_user.id
    args = " ".join(context.args).strip() if context.args else ""

    active_skills = memory.get_skills(user_id)
    if not active_skills:
        await update.message.reply_text("No tienes skills activas. Usa /skills para ver el catálogo.")
        return

    await update.message.chat.send_action("typing")

    if args.lower() == "todas":
        evolved = []
        for skill in active_skills:
            result = await skills_engine.evolve_skill(
                user_id, skill["id"], "evolución manual solicitada por usuario", memory, call_groq
            )
            if result:
                evolved.append(skill.get("emoji","🛠") + " " + skill.get("name",""))
        if evolved:
            await update.message.reply_text(
                "✅ Skills actualizadas con tu memoria actual:\n" + "\n".join(evolved)
            )
        else:
            await update.message.reply_text("No se pudo evolucionar ninguna skill.")
        return

    # Buscar skill por nombre
    if not args:
        names = [f"{s.get('emoji','🛠')} {s.get('name',s.get('id',''))}" for s in active_skills]
        await update.message.reply_text(
            "¿Cuál skill quieres actualizar?\n\n"
            + "\n".join(names)
            + "\n\nUso: /evolucion [nombre] o /evolucion todas"
        )
        return

    skill = next((s for s in active_skills if args.lower() in s.get("name","").lower()
                  or args.lower() == s.get("id","")), None)
    if not skill:
        await update.message.reply_text(f"No encontré una skill activa con ese nombre: '{args}'")
        return

    result = await skills_engine.evolve_skill(
        user_id, skill["id"], "evolución manual por usuario", memory, call_groq
    )
    if result:
        await update.message.reply_text(
            f"✅ {result.get('emoji','🛠')} *{result.get('name','')}* actualizada "
            f"(evolución #{result.get('evolution_count',1)})",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("No pude actualizar esa skill. Intenta de nuevo.")


async def cmd_nueva_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Crea una skill personalizada desde cero basada en la descripción del usuario.
    Uso: /nueva_skill [descripción de lo que quieres que haga]
    """
    user_id = update.effective_user.id
    description = " ".join(context.args).strip() if context.args else ""

    if not description:
        await update.message.reply_text(
            "Describe qué quieres que haga tu nueva skill.\n\n"
            "Ejemplos:\n"
            "/nueva_skill ayúdame a preparar reportes ejecutivos para mi jefe\n"
            "/nueva_skill cuando hable de clientes, recuérdame siempre hacer seguimiento\n"
            "/nueva_skill analiza mis correos y detecta oportunidades de negocio"
        )
        return

    await update.message.chat.send_action("typing")
    skill = await skills_engine.create_custom_skill(user_id, description, memory, call_groq)

    if skill:
        await update.message.reply_text(
            f"{skill['emoji']} Skill *{skill['name']}* creada y activada ✅\n\n"
            f"{skill['description']}\n\n"
            f"Ya está activa en tus conversaciones. Puedes actualizarla con /evolucion {skill['name']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("No pude crear la skill. Intenta con una descripción más específica.")


async def cmd_mis_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las skills activas con su contenido personalizado."""
    user_id = update.effective_user.id
    active = memory.get_skills(user_id)

    if not active:
        await update.message.reply_text(
            "No tienes skills activas.\n"
            "Usa /skills para ver el catálogo y /activar_skill [nombre] para activar una."
        )
        return

    stale = skills_engine.check_skills_needing_evolution(active)
    stale_ids = {s.get("id") for s in stale}

    lines = [f"🛠 Tus skills activas ({len(active)}):"]
    for skill in active:
        emoji = skill.get("emoji", "🛠")
        name = skill.get("name", skill.get("id", ""))
        count = skill.get("evolution_count", 0)
        is_stale = skill.get("id") in stale_ids
        stale_note = " ⚠️ desactualizada" if is_stale else ""
        lines.append(f"\n{emoji} *{name}*{stale_note}")
        lines.append(f"   Evoluciones: {count}")
        content = skill.get("content_personal") or skill.get("content_base", "")
        if content:
            lines.append(f"   {content[:120]}...")

    if stale:
        lines.append(f"\n⚠️ {len(stale)} skill(s) con más de 30 días sin actualizar.")
        lines.append("Usa /evolucion todas para refrescarlas.")

    # Suggest new skills based on user memory
    user_data = memory.get_user(user_id)
    active_ids = [s.get("id") for s in active]
    suggestions = skills_engine.suggest_skills_for_user(user_data, active_ids)
    if suggestions:
        lines.append(f"\n💡 Skills que podrían interesarte: {', '.join(suggestions)}")
        lines.append("Usa /activar_skill [nombre] para activarlas.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
            f'Perfecto — trataré de ser: "{frase}" ✅'
        )

    elif subcmd == "reset":
        memory.set_bot_identity(user_id, {"activa": False})
        await update.message.reply_text(
            "Volví a la identidad global (Luma) ✅"
        )

    else:
        await update.message.reply_text(
            "Uso:\n"
            "/mi_asistente               → ver configuración\n"
            "/mi_asistente nombre Luna   → cambiar nombre\n"
            "/mi_asistente tono casual   → formal | casual | directo\n"
            "/mi_asistente frase [texto] → cómo quieres ser tratado\n"
            "/mi_asistente reset         → volver a identidad global"
        )


async def cmd_mi_zona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ver o cambiar la timezone del usuario.
    Uso:
      /mi_zona                      → ver timezone actual
      /mi_zona America/Los_Angeles  → setear timezone IANA directamente
      /mi_zona Los Angeles          → setear por ciudad (inferencia automática)
    """
    user_id = update.effective_user.id
    args = " ".join(context.args).strip() if context.args else ""

    if not args:
        user = memory.get_user(user_id)
        tz_name = user.get("ritmo", {}).get("zona_horaria") or "No configurada"
        user_now = tz_utils.now_for_user(user)
        offset = tz_utils.get_iso_offset(tz_name) if tz_name != "No configurada" else "?"
        await update.message.reply_text(
            f"🕐 Tu timezone: {tz_name}\n"
            f"   Offset actual: {offset}\n"
            f"   Tu hora local: {user_now.strftime('%H:%M')}\n\n"
            "Para cambiarla:\n"
            "/mi_zona Los Angeles\n"
            "/mi_zona America/Bogota\n"
            "/mi_zona Madrid"
        )
        return

    # Intentar inferir por ciudad primero
    inferred = tz_utils.infer_tz_from_city(args)

    # Si no, intentar como nombre IANA directo
    if not inferred:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(args)
            inferred = args
        except (ZoneInfoNotFoundError, Exception):
            pass

    if not inferred:
        await update.message.reply_text(
            f"No reconocí '{args}' como ciudad o timezone.\n\n"
            "Prueba con el nombre IANA directo, por ejemplo:\n"
            "• America/Los_Angeles\n"
            "• America/New_York\n"
            "• America/Bogota\n"
            "• Europe/Madrid\n\n"
            "O con el nombre de tu ciudad en español o inglés."
        )
        return

    # Guardar
    ritmo = memory.get_category(user_id, "ritmo") or {}
    ritmo["zona_horaria"] = inferred
    memory.set_category(user_id, "ritmo", ritmo)

    offset = tz_utils.get_iso_offset(inferred)
    from datetime import datetime
    local_now = datetime.now(tz_utils.get_zoneinfo(inferred))

    await update.message.reply_text(
        f"✅ Timezone actualizada: *{inferred}*\n"
        f"   Offset: {offset}\n"
        f"   Tu hora ahora: {local_now.strftime('%H:%M')}\n\n"
        "Todos los eventos del calendario se crearán con esta zona horaria.",
        parse_mode="Markdown"
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
    telegram_app.add_handler(CommandHandler("mi_zona", cmd_mi_zona))
    telegram_app.add_handler(CommandHandler("mi_asistente", cmd_mi_asistente))
    telegram_app.add_handler(CommandHandler("evolucion", cmd_evolucion))
    telegram_app.add_handler(CommandHandler("nueva_skill", cmd_nueva_skill))
    telegram_app.add_handler(CommandHandler("mis_skills", cmd_mis_skills))
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
