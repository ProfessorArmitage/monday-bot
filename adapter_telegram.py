"""
adapter_telegram.py — Adapter de Telegram para Monday Bot.

Responsabilidades:
  - Recibir mensajes de Telegram (texto, voz, comandos)
  - Convertir a InboundMessage normalizado
  - Llamar a channel_router.process_message() con send_fn y typing_fn
  - Enviar la respuesta de vuelta (texto o voz según preferencia)
  - Manejar OAuth callback de Google
  - Registrar todos los handlers en la Application de Telegram

Para agregar un comando nuevo:
  1. Crear async def cmd_nuevo(update, context)
  2. Registrarlo en register_handlers()
"""

import os
import io
import re
import json
import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import memory
import google_auth
import google_services
import workspace_memory
import onboarding
import provisioning
import memory_backup
import audio_handler
import identity as identity_module
import skills as skills_engine
import tz_utils
import domain_seeds
import channel_router
from channel_types import InboundMessage, ChannelType

logger = logging.getLogger(__name__)

RAILWAY_PUBLIC_URL = os.getenv("RAILWAY_PUBLIC_URL", "http://localhost:8080")
PORT               = int(os.getenv("PORT", 8080))
ADMIN_USER_IDS     = set(
    int(x.strip()) for x in os.getenv("ADMIN_USER_IDS", "").split(",")
    if x.strip().isdigit()
)

# Referencia global al bot (para OAuth callback y domain suggestions)
_telegram_app = None

def set_app(app):
    """Registra la referencia global al Application de Telegram."""
    global _telegram_app
    _telegram_app = app


# ── Helpers de envío ──────────────────────────────────────────

def _make_send_fn(update: Update, user_id: int):
    """
    Retorna una función async que envía texto al usuario.
    Si el usuario prefiere voz, envía audio en su lugar.
    Esta función es lo que el channel_router usa para responder — 
    no sabe que está en Telegram.
    """
    async def send_fn(text: str):
        user_data = memory.get_user(user_id)
        if audio_handler.user_wants_voice(user_data):
            await _send_voice_reply(update, user_id, text)
        else:
            await update.message.reply_text(text)
    return send_fn


def _make_typing_fn(update: Update):
    """Retorna una función async que muestra el indicador de escritura."""
    async def typing_fn():
        await update.message.chat.send_action("typing")
    return typing_fn


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
        if _telegram_app:
            await _telegram_app.bot.send_message(
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
        user_id, skill, memory, channel_router.call_groq
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
                user_id, skill["id"], "evolución manual solicitada por usuario", memory, channel_router.call_groq
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
        user_id, skill["id"], "evolución manual por usuario", memory, channel_router.call_groq
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
    skill = await skills_engine.create_custom_skill(user_id, description, memory, channel_router.call_groq)

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



# ── DOMINIO — helpers ─────────────────────────────────────────

async def _send_domain_suggestion(user_id: int, update):
    """Envía sugerencia de dominio al terminar onboarding."""
    import asyncio
    await asyncio.sleep(1)  # pequeño delay para que llegue después del mensaje de bienvenida
    domain_pending = memory.get_domain_pending(user_id)
    if not domain_pending.get("suggested"):
        # No se detectó dominio — mostrar menú genérico
        msg = (
            "\n🎯 Un último detalle — ¿Cuál describe mejor tu actividad?\n\n"
            + provisioning.get_domains_menu_text()
        )
        try:
            await update.message.reply_text(msg)
        except Exception:
            pass
        return

    suggested_id = domain_pending["suggested"]
    domain = provisioning.get_domain_by_id(suggested_id)
    if not domain:
        return

    skill_names = [s["name"] for s in provisioning.get_domain_skills(suggested_id)]
    skills_text = ", ".join(skill_names)

    msg = (
        f"\n🎯 Detecté que trabajas en {domain['name']} {domain['emoji']}\n\n"
        f"Tengo un paquete de skills especializadas para ti:\n"
        f"{skills_text}\n\n"
        f"¿Activo el paquete {domain['name']}?\n\n"
        f"Responde: si / no / saltar"
    )
    try:
        await update.message.reply_text(msg)
        # Marcar que ya se preguntó
        from datetime import datetime
        memory.set_domain_pending(user_id, {
            **domain_pending,
            "asked_at": datetime.utcnow().isoformat(),
            "state": "awaiting_confirmation",
        })
    except Exception:
        pass




async def cmd_mi_dominio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ver o cambiar el paquete de dominio activo.
    /mi_dominio            → ver dominio actual + opciones
    /mi_dominio legal      → activar paquete legal directamente
    /mi_dominio 3          → activar por número del menú
    """
    user_id = update.effective_user.id
    args = " ".join(context.args).strip().lower() if context.args else ""

    if not args:
        # Mostrar estado actual
        current_domain_id = memory.get_user_domain(user_id)
        current_domain = provisioning.get_domain_by_id(current_domain_id) if current_domain_id else None

        if current_domain:
            skill_names = [s["name"] for s in provisioning.get_domain_skills(current_domain_id)]
            msg = (
                f"🎯 Tu paquete actual: {current_domain['emoji']} {current_domain['name']}\n"
                f"{current_domain['description']}\n\n"
                f"Skills del paquete:\n"
                + "\n".join(f"  • {n}" for n in skill_names)
                + "\n\n¿Quieres cambiarlo?\n\n"
                + provisioning.get_domains_menu_text()
            )
        else:
            msg = (
                "🎯 No tienes un paquete de dominio activo aún.\n\n"
                + provisioning.get_domains_menu_text()
            )

        await update.message.reply_text(msg)

        # Poner en estado de espera de selección
        from datetime import datetime
        memory.set_domain_pending(user_id, {
            "suggested": current_domain_id,
            "asked_at": datetime.utcnow().isoformat(),
            "state": "awaiting_selection",
            "source": "command",
        })
        return

    # Con argumento — activar directamente
    domains = provisioning.DOMAINS_CATALOG
    selected_id = None

    # Por número
    if args.strip() in [str(i) for i in range(1, len(domains)+1)]:
        selected_id = domains[int(args.strip())-1]["id"]
    # Por nombre o id
    else:
        for d in domains:
            if d["id"] in args or d["name"].lower() in args:
                selected_id = d["id"]
                break

    if selected_id:
        await update.message.chat.send_action("typing")
        await _activate_domain_pack(user_id, selected_id, update)
        memory.clear_domain_pending(user_id)
    else:
        await update.message.reply_text(
            f"No reconocí '{args}' como dominio.\n\n"
            + provisioning.get_domains_menu_text()
        )




# ── EXPORT / IMPORT DE MEMORIA ────────────────────────────────



async def cmd_exportar_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Genera un respaldo JSON de toda la memoria del usuario
    y lo guarda en la carpeta Monday de su Google Drive.
    """
    user_id = update.effective_user.id

    if not memory.has_google_connected(user_id):
        await update.message.reply_text(
            "Necesitas conectar tu Google Drive primero.\nUsa /conectar_google para hacerlo."
        )
        return

    await update.message.chat.send_action("typing")
    result = await memory_backup.export_to_drive(user_id)

    if result["ok"]:
        nombre_archivo = result["filename"]
        max_b = memory_backup.MAX_BACKUPS
        await update.message.reply_text(
            f"Respaldo guardado en tu Drive.\n"
            f"Archivo: {nombre_archivo}\n"
            f"Carpeta: Monday — Asistente Personal\n\n"
            f"Se conservan los ultimos {max_b} respaldos automaticamente."
        )
    else:
        error = result.get("error", "desconocido")
        if error == "no_folder":
            await update.message.reply_text(
                "No pude acceder a tu carpeta de Drive. "
                "Intenta reconectar Google con /conectar_google."
            )
        else:
            await update.message.reply_text(
                "Hubo un error al generar el respaldo. Intenta de nuevo en unos minutos."
            )


async def cmd_importar_memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Restaura la memoria desde el respaldo más reciente en Drive.
    Pide confirmación antes de reemplazar la memoria actual.
    """
    user_id = update.effective_user.id

    if not memory.has_google_connected(user_id):
        await update.message.reply_text(
            "Necesitas conectar tu Google Drive primero.\nUsa /conectar_google para hacerlo."
        )
        return

    await update.message.chat.send_action("typing")

    # Listar respaldos disponibles
    backups = await memory_backup.list_backups(user_id)
    if not backups:
        await update.message.reply_text(
            "No encontré respaldos en tu Drive.\n"
            "Genera uno primero con /exportar_memoria."
        )
        return

    # Descargar el más reciente
    snapshot = await memory_backup.get_latest_backup_content(user_id)
    if not snapshot:
        await update.message.reply_text(
            "No pude leer el respaldo más reciente. "
            "Puede estar dañado. Intenta exportar uno nuevo con /exportar_memoria."
        )
        return

    # Mostrar lista y advertencia de confirmación
    backup_list = memory_backup.format_backup_list(backups)
    warning = memory_backup.build_confirmation_warning(user_id, snapshot)

    await update.message.reply_text(backup_list)
    await update.message.reply_text(warning)

    # Guardar snapshot en preferencias temporalmente para el handler de confirmación
    prefs = memory.get_category(user_id, "preferencias") or {}
    prefs["_import_pending"] = True
    prefs["_import_snapshot"] = json.dumps(snapshot, ensure_ascii=False)
    memory.set_category(user_id, "preferencias", prefs)




# ── Handlers de mensajes ──────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal para mensajes de texto."""
    user_id   = update.effective_user.id
    user_name = update.effective_user.first_name or "Usuario"
    user_text = update.message.text

    # Interceptar respuestas de onboarding
    if onboarding.is_in_onboarding(user_id):
        await update.message.chat.send_action("typing")
        next_question = await onboarding.process_answer(
            user_id, user_text, channel_router.call_groq
        )
        if next_question:
            await update.message.reply_text(next_question)
            if not onboarding.is_in_onboarding(user_id):
                if memory.has_google_connected(user_id):
                    asyncio.create_task(workspace_memory.sync_memory_to_doc(user_id))
                asyncio.create_task(_send_domain_suggestion(user_id, update))
        return

    logger.info(f"Mensaje de {user_name} ({user_id}): {user_text}")

    msg = InboundMessage(
        monday_id=user_id,
        channel=ChannelType.TELEGRAM,
        text=user_text,
    )
    await channel_router.process_message(
        msg,
        send_fn=_make_send_fn(update, user_id),
        typing_fn=_make_typing_fn(update),
    )


# ── AUDIO — helpers ──────────────────────────────────────────

async def handle_voice_message(update, context):
    """
    Handler para mensajes de voz.
    Descarga el audio, transcribe con Whisper via Groq,
    y pasa el texto al flujo normal de handle_message.
    """
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Usuario"

    await update.message.chat.send_action("typing")

    # Descargar audio de Telegram
    try:
        voice = update.message.voice
        tg_file = await context.bot.get_file(voice.file_id)
        audio_bytes = await tg_file.download_as_bytearray()
        audio_bytes = bytes(audio_bytes)
    except Exception as e:
        logger.error(f"Error descargando audio de {user_id}: {e}")
        await update.message.reply_text(
            "No pude descargar el audio. Intenta de nuevo o envía tu mensaje en texto."
        )
        return

    # Transcribir
    transcribed = await audio_handler.transcribe(audio_bytes, filename="audio.ogg")

    if not transcribed:
        await update.message.reply_text(
            "No pude entender el audio. "
            "Intenta hablar más claro o envía tu mensaje en texto."
        )
        return

    logger.info(f"Audio transcrito de {user_name} ({user_id}): {transcribed[:80]}")

    msg = InboundMessage(
        monday_id=user_id,
        channel=ChannelType.TELEGRAM,
        text=transcribed,
        is_voice=True,
    )
    await channel_router.process_message(
        msg,
        send_fn=_make_send_fn(update, user_id),
        typing_fn=_make_typing_fn(update),
    )


async def _send_voice_reply(update, user_id: int, text: str):
    """
    Envía la respuesta del bot como mensaje de voz.
    Si la síntesis falla, cae back a texto.
    """
    try:
        audio_bytes = await audio_handler.synthesize(text)
        if audio_bytes:
            await update.message.reply_voice(
                voice=io.BytesIO(audio_bytes),
                caption=None,
            )
            return
    except Exception as e:
        logger.warning(f"TTS falló para usuario {user_id}: {e}")

    # Fallback a texto si TTS falla
    await update.message.reply_text(text)


async def cmd_voz(update, context):
    """
    Configurar el modo de respuesta por voz.

    /voz            → ver estado actual
    /voz activar    → respuestas en audio
    /voz desactivar → respuestas en texto (default)
    """
    user_id = update.effective_user.id
    args = context.args or []
    action = args[0].lower() if args else ""

    user_data = memory.get_user(user_id)
    prefs = memory.get_category(user_id, "preferencias") or {}
    current = prefs.get("respuesta_en_voz", False)

    if not action:
        estado = "activado" if current else "desactivado"
        await update.message.reply_text(
            f"Respuestas por voz: {estado}\n\n"
            f"/voz activar   → respuestas en audio\n"
            f"/voz desactivar → respuestas en texto"
        )
        return

    if action == "activar":
        prefs["respuesta_en_voz"] = True
        memory.set_category(user_id, "preferencias", prefs)
        await update.message.reply_text(
            "Respuestas por voz activadas.\n"
            "A partir de ahora te contestaré con audio.\n"
            "Usa /voz desactivar para volver a texto."
        )
        return

    if action == "desactivar":
        prefs["respuesta_en_voz"] = False
        memory.set_category(user_id, "preferencias", prefs)
        await update.message.reply_text(
            "Respuestas por voz desactivadas. Te contestaré en texto."
        )
        return

    await update.message.reply_text(
        "Opciones:\n"
        "  /voz           → ver estado\n"
        "  /voz activar   → respuestas en audio\n"
        "  /voz desactivar → respuestas en texto"
    )


# ── DO NOT DISTURB ────────────────────────────────────────────

async def cmd_dnd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Configurar el modo silencio (Do Not Disturb).

    /dnd                        → ver estado actual
    /dnd activar 22:00 07:00    → activar con horario nocturno
    /dnd activar 22:00 07:00 sabado domingo  → activar + dias sin notificaciones
    /dnd desactivar             → desactivar DND (sigue el horario pero no silencia)
    /dnd dias sabado domingo    → configurar dias sin notificaciones
    /dnd snooze 1h              → silenciar 1 hora (tambien: 30m, 2h, 3h)
    /dnd snooze off             → cancelar snooze activo
    """
    user_id = update.effective_user.id
    args = context.args or []
    action = args[0].lower() if args else ""

    user_data = memory.get_user(user_id)
    ritmo = memory.get_category(user_id, "ritmo") or {}
    dnd = ritmo.get("dnd", {}) or {}

    # ── Ver estado ──
    if not action:
        await update.message.reply_text(tz_utils.dnd_status_text(user_data))
        return

    # ── Activar con horario ──
    if action == "activar":
        if len(args) < 3:
            await update.message.reply_text(
                "Uso: /dnd activar HH:MM HH:MM\n"
                "Ejemplo: /dnd activar 22:00 07:00\n"
                "Opcional: agrega dias al final — /dnd activar 22:00 07:00 sabado domingo"
            )
            return

        start = args[1]
        end = args[2]

        # Validar formato HH:MM
        import re as _re
        if not _re.match(r'^\d{1,2}:\d{2}$', start) or not _re.match(r'^\d{1,2}:\d{2}$', end):
            await update.message.reply_text(
                "Formato de hora inválido. Usa HH:MM, por ejemplo 22:00 o 07:00."
            )
            return

        # Dias opcionales (resto de args después de las horas)
        dias_map = {
            "lunes": "lunes", "martes": "martes", "miercoles": "miércoles",
            "miércoles": "miércoles", "jueves": "jueves", "viernes": "viernes",
            "sabado": "sábado", "sábado": "sábado", "domingo": "domingo",
        }
        dias = []
        for a in args[3:]:
            d = dias_map.get(a.lower())
            if d:
                dias.append(d)

        dnd["enabled"] = True
        dnd["start"] = start
        dnd["end"] = end
        if dias:
            dnd["dias_libres"] = dias
        elif "dias_libres" not in dnd:
            dnd["dias_libres"] = []

        ritmo["dnd"] = dnd
        memory.set_category(user_id, "ritmo", ritmo)

        dias_txt = f"\nDias sin notificaciones: {', '.join(dias)}" if dias else ""
        await update.message.reply_text(
            f"Modo silencio activado.\n"
            f"Horario: {start} – {end}{dias_txt}\n\n"
            f"No te mandaré notificaciones en ese horario.\n"
            f"Usa /dnd desactivar para quitar el silencio."
        )
        return

    # ── Desactivar ──
    if action == "desactivar":
        dnd["enabled"] = False
        dnd.pop("snooze_until", None)
        ritmo["dnd"] = dnd
        memory.set_category(user_id, "ritmo", ritmo)
        await update.message.reply_text(
            "Modo silencio desactivado. Recibirás notificaciones normalmente."
        )
        return

    # ── Configurar dias ──
    if action == "dias":
        if len(args) < 2:
            await update.message.reply_text(
                "Uso: /dnd dias sabado domingo\n"
                "Dias disponibles: lunes, martes, miercoles, jueves, viernes, sabado, domingo"
            )
            return
        dias_map = {
            "lunes": "lunes", "martes": "martes", "miercoles": "miércoles",
            "miércoles": "miércoles", "jueves": "jueves", "viernes": "viernes",
            "sabado": "sábado", "sábado": "sábado", "domingo": "domingo",
        }
        dias = [dias_map[a.lower()] for a in args[1:] if a.lower() in dias_map]
        if not dias:
            await update.message.reply_text("No reconocí los dias. Usa: sabado, domingo, lunes, etc.")
            return
        dnd["dias_libres"] = dias
        ritmo["dnd"] = dnd
        memory.set_category(user_id, "ritmo", ritmo)
        await update.message.reply_text(
            f"Dias sin notificaciones: {', '.join(dias)}"
        )
        return

    # ── Snooze ──
    if action == "snooze":
        if len(args) < 2:
            await update.message.reply_text(
                "Uso: /dnd snooze 1h\n"
                "Opciones: 30m, 1h, 2h, 3h, 4h\n"
                "/dnd snooze off — cancelar snooze"
            )
            return

        snooze_arg = args[1].lower()

        if snooze_arg == "off":
            dnd.pop("snooze_until", None)
            ritmo["dnd"] = dnd
            memory.set_category(user_id, "ritmo", ritmo)
            await update.message.reply_text("Snooze cancelado. Recibirás notificaciones normalmente.")
            return

        # Parsear duración
        import re as _re
        from datetime import datetime, timezone as _tz, timedelta
        m = _re.match(r'^(\d+)(m|h)$', snooze_arg)
        if not m:
            await update.message.reply_text(
                "Formato no reconocido. Usa: 30m, 1h, 2h, 3h\n"
                "Ejemplo: /dnd snooze 2h"
            )
            return

        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "h":
            delta = timedelta(hours=min(amount, 12))  # máximo 12h
        else:
            delta = timedelta(minutes=min(amount, 120))  # máximo 120m

        until = datetime.now(_tz.utc) + delta
        dnd["snooze_until"] = until.isoformat()
        ritmo["dnd"] = dnd
        memory.set_category(user_id, "ritmo", ritmo)

        duration_txt = f"{amount} {'hora' if unit == 'h' else 'minuto'}{'s' if amount > 1 else ''}"
        until_local = tz_utils.to_user_tz(until, user_data)
        until_txt = until_local.strftime("%H:%M")
        await update.message.reply_text(
            f"Silencio por {duration_txt}.\n"
            f"Notificaciones pausadas hasta las {until_txt}.\n"
            f"Usa /dnd snooze off para cancelar antes."
        )
        return

    # Argumento no reconocido
    await update.message.reply_text(
        "Opciones de /dnd:\n"
        "  /dnd                      → ver estado\n"
        "  /dnd activar 22:00 07:00  → activar horario\n"
        "  /dnd desactivar           → desactivar\n"
        "  /dnd snooze 1h            → silenciar 1 hora\n"
        "  /dnd snooze off           → cancelar snooze\n"
        "  /dnd dias sabado domingo  → dias sin notificaciones"
    )


# ── ADMIN ─────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comandos de administración. Solo para user_ids en ADMIN_USER_IDS.

    /admin seed ver <user_id>
        → Ver el domain_seed actual del usuario

    /admin seed <dominio> <user_id> <campo> <valor>
        → Configurar un campo de domain_extras para un usuario
        Ejemplos:
          /admin seed legal 12345 numero_cedula 1234567
          /admin seed influencer 12345 handle_instagram @miusuario
          /admin seed ventas 12345 crm_usado HubSpot
          /admin seed salud 12345 especialidad cardiologia
          /admin seed educacion 12345 institucion UNAM

    /admin seed reset <user_id>
        → Reinicializar el seed del usuario (conserva domain_extras)

    /admin dominio ver <user_id>
        → Ver el dominio activo del usuario

    /admin dominio set <user_id> <dominio>
        → Cambiar el dominio de un usuario directamente
    """
    user_id = update.effective_user.id

    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("No tienes permisos para usar este comando.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Uso: /admin seed ver <user_id>\n"
            "     /admin seed <dominio> <user_id> <campo> <valor>\n"
            "     /admin seed reset <user_id>\n"
            "     /admin dominio ver <user_id>\n"
            "     /admin dominio set <user_id> <dominio>"
        )
        return

    subcommand = args[0].lower()

    # ── /admin seed ... ──
    if subcommand == "seed":
        action = args[1].lower()

        # /admin seed ver <user_id>
        if action == "ver" and len(args) >= 3:
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            seed = memory.get_domain_seed(target_id)
            domain_id = memory.get_user_domain(target_id)
            if not seed:
                await update.message.reply_text(
                    f"Usuario {target_id} no tiene seed.\n"
                    f"Dominio activo: {domain_id or 'ninguno'}"
                )
                return
            import json as _json
            seed_text = _json.dumps(seed, ensure_ascii=False, indent=2)
            # Telegram tiene límite de 4096 chars
            if len(seed_text) > 3800:
                seed_text = seed_text[:3800] + "\n... (truncado)"
            await update.message.reply_text(
                f"Seed de usuario {target_id} (dominio: {domain_id}):\n\n{seed_text}"
            )
            return

        # /admin seed reset <user_id>
        if action == "reset" and len(args) >= 3:
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            domain_id = memory.get_user_domain(target_id)
            if not domain_id:
                await update.message.reply_text(f"Usuario {target_id} no tiene dominio activo.")
                return
            # Conservar domain_extras del seed anterior
            old_seed = memory.get_domain_seed(target_id)
            old_extras = old_seed.get("domain_extras", {}) if old_seed else {}
            from datetime import datetime as _dt
            new_seed = {
                "domain_id": domain_id,
                "base_memory": domain_seeds.get_base_memory(domain_id),
                "domain_extras": old_extras,
                "created_at": _dt.utcnow().isoformat(),
                "reset_at": _dt.utcnow().isoformat(),
            }
            memory.set_domain_seed(target_id, new_seed)
            await update.message.reply_text(
                f"Seed de usuario {target_id} reinicializado.\n"
                f"domain_extras conservados: {list(old_extras.keys())}"
            )
            return

        # /admin seed <dominio> <user_id> <campo> <valor>
        if len(args) >= 5:
            domain_arg = args[1].lower()
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            field = args[3].lower()
            value = " ".join(args[4:])

            # Validar dominio
            if not provisioning.get_domain_by_id(domain_arg):
                domains_list = [d["id"] for d in provisioning.DOMAINS_CATALOG]
                await update.message.reply_text(
                    f"Dominio '{domain_arg}' no existe.\n"
                    f"Dominios disponibles: {', '.join(domains_list)}"
                )
                return

            # Validar campo
            valid_extras = domain_seeds.get_empty_domain_extras(domain_arg)
            if field not in valid_extras:
                await update.message.reply_text(
                    f"Campo '{field}' no existe en domain_extras de '{domain_arg}'.\n"
                    f"Campos disponibles: {', '.join(valid_extras.keys())}"
                )
                return

            current_seed = memory.get_domain_seed(target_id)
            updated_seed = domain_seeds.apply_admin_override(current_seed, domain_arg, field, value)
            memory.set_domain_seed(target_id, updated_seed)

            await update.message.reply_text(
                f"Actualizado para usuario {target_id}:\n"
                f"  dominio: {domain_arg}\n"
                f"  {field}: {value}"
            )
            return

        await update.message.reply_text("Argumentos insuficientes para /admin seed.")
        return

    # ── /admin dominio ... ──
    if subcommand == "dominio":
        if len(args) < 3:
            await update.message.reply_text("Uso: /admin dominio ver <user_id> | set <user_id> <dominio>")
            return

        action = args[1].lower()

        if action == "ver":
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            domain_id = memory.get_user_domain(target_id)
            user = memory.get_user(target_id)
            nombre = user.get("identidad", {}).get("nombre", "desconocido")
            await update.message.reply_text(
                f"Usuario {target_id} ({nombre}):\n"
                f"Dominio activo: {domain_id or 'ninguno'}"
            )
            return

        if action == "set" and len(args) >= 4:
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            new_domain = args[3].lower()
            if not provisioning.get_domain_by_id(new_domain):
                await update.message.reply_text(f"Dominio '{new_domain}' no existe.")
                return
            memory.set_user_domain(target_id, new_domain)
            await provisioning._inject_domain_seed(target_id, new_domain, memory)
            await update.message.reply_text(
                f"Dominio de usuario {target_id} actualizado a '{new_domain}'.\n"
                f"Seed inyectado correctamente."
            )
            return

    # ── /admin memoria ... ──
    if subcommand == "memoria":
        if len(args) < 3:
            await update.message.reply_text(
                "Uso: /admin memoria exportar <user_id>\n"
                "     /admin memoria ver_backups <user_id>"
            )
            return

        action = args[1].lower()

        if action == "exportar" and len(args) >= 3:
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            await update.message.chat.send_action("typing")
            result = await memory_backup.export_to_drive(target_id)
            if result["ok"]:
                await update.message.reply_text(
                    f"Backup generado para usuario {target_id}:\n"
                    f"Archivo: {result['filename']}"
                )
            else:
                await update.message.reply_text(
                    f"Error al generar backup: {result.get('error')}"
                )
            return

        if action == "ver_backups" and len(args) >= 3:
            try:
                target_id = int(args[2])
            except ValueError:
                await update.message.reply_text("user_id debe ser un número.")
                return
            backups = await memory_backup.list_backups(target_id)
            msg = memory_backup.format_backup_list(backups)
            await update.message.reply_text(f"Backups de usuario {target_id}:\n\n{msg}")
            return

    await update.message.reply_text(f"Subcomando '{subcommand}' no reconocido.")


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

# ── Registro de handlers ──────────────────────────────────────

def register_handlers(app) -> None:
    """Registra todos los handlers de Telegram en la Application."""
    set_app(app)

    app.add_handler(CommandHandler("start",              cmd_start))
    app.add_handler(CommandHandler("conectar_google",    cmd_connect_google))
    app.add_handler(CommandHandler("desconectar_google", cmd_disconnect_google))
    app.add_handler(CommandHandler("estado",             cmd_status))
    app.add_handler(CommandHandler("memoria",            cmd_memory))
    app.add_handler(CommandHandler("olvidar",            cmd_forget))
    app.add_handler(CommandHandler("ayuda",              cmd_help))
    app.add_handler(CommandHandler("skills",             cmd_skills))
    app.add_handler(CommandHandler("activar_skill",      cmd_activate_skill))
    app.add_handler(CommandHandler("desactivar_skill",   cmd_deactivate_skill))
    app.add_handler(CommandHandler("heartbeat",          cmd_heartbeat_test))
    app.add_handler(CommandHandler("mi_doc",             cmd_my_doc))
    app.add_handler(CommandHandler("sincronizar",        cmd_sync_doc))
    app.add_handler(CommandHandler("version",            cmd_version))
    app.add_handler(CommandHandler("mi_dominio",         cmd_mi_dominio))
    app.add_handler(CommandHandler("admin",              cmd_admin))
    app.add_handler(CommandHandler("exportar_memoria",   cmd_exportar_memoria))
    app.add_handler(CommandHandler("importar_memoria",   cmd_importar_memoria))
    app.add_handler(CommandHandler("dnd",                cmd_dnd))
    app.add_handler(CommandHandler("mi_zona",            cmd_mi_zona))
    app.add_handler(CommandHandler("mi_asistente",       cmd_mi_asistente))
    app.add_handler(CommandHandler("evolucion",          cmd_evolucion))
    app.add_handler(CommandHandler("nueva_skill",        cmd_nueva_skill))
    app.add_handler(CommandHandler("mis_skills",         cmd_mis_skills))
    app.add_handler(CommandHandler("voz",                cmd_voz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
