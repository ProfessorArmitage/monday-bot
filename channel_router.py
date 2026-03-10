"""
channel_router.py — Core engine 100% agnóstico al canal.

PRINCIPIO: este módulo no sabe nada de Telegram, WhatsApp, Slack ni Email.
Recibe un InboundMessage normalizado y llama a send_fn() para responder.

Contiene:
  - call_groq()           → llamada a Groq LLaMA
  - execute_google_action() → ejecuta acciones de Google Workspace
  - process_message()     → orquesta todo: pending states, prompt, Groq, facts, respuesta
  - activate_domain_pack() → activa paquete de dominio (agnóstico)
  - handle_pending_domain() → intercepta selección de dominio pendiente
  - handle_pending_import() → intercepta confirmación de import de memoria

Para agregar un nuevo canal: crear adapter_<canal>.py que construya InboundMessage
y proporcione send_fn — este módulo no cambia.
"""

import os
import re
import json
import asyncio
import logging
from typing import Callable, Awaitable

import httpx

import memory
import google_services
import workspace_memory
import conversation_context
import provisioning
import domain_seeds
import memory_backup
import skills as skills_engine
from channel_types import InboundMessage, ChannelType, get_channel_style
import security

logger = logging.getLogger(__name__)

# ── Configuración Groq ────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

# System prompt base (versionado en provisioning)
BASE_SYSTEM_PROMPT = provisioning.get_current_system_prompt()

# Tipo para las funciones de envío
SendFn   = Callable[[str], Awaitable[None]]
TypingFn = Callable[[], Awaitable[None]]


# ── Llamada a Groq ────────────────────────────────────────────

async def call_groq(system_prompt: str, history: list, user_text: str) -> str:
    """Llama a Groq LLaMA y retorna el texto de respuesta."""
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
        return data["choices"][0]["message"]["content"]


# ── Acciones de Google ────────────────────────────────────────

async def execute_google_action(user_id: int, action_data: dict) -> str:
    """Ejecuta una acción de Google Workspace y retorna un resumen del resultado."""
    from datetime import datetime, timedelta
    import tz_utils

    service = action_data.get("service")
    action  = action_data.get("action")
    params  = action_data.get("params", {})

    # ── Normalizar params de Calendar ────────────────────────
    if service == "calendar" and action == "create_event":
        for alt in ("summary", "name", "evento", "event_name", "titulo"):
            if alt in params and "title" not in params:
                params["title"] = params.pop(alt)
        for alt in ("start_time", "startTime", "fecha_inicio", "inicio", "fecha_hora_inicio"):
            if alt in params and "start" not in params:
                params["start"] = params.pop(alt)
        for alt in ("end_time", "endTime", "fecha_fin", "fin", "fecha_hora_fin", "duration"):
            if alt in params and "end" not in params:
                if alt == "duration":
                    try:
                        start_str = params.get("start", "")
                        if start_str:
                            start_dt = datetime.fromisoformat(start_str)
                            end_dt = start_dt + timedelta(minutes=int(params.pop(alt)))
                            params["end"] = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
                    except Exception:
                        params.pop(alt, None)
                else:
                    params["end"] = params.pop(alt)
        for unknown in ("location", "recurrence", "reminders", "color", "visibility",
                        "guests", "participants", "conferenceData"):
            if unknown in params and unknown != "attendees":
                params.pop(unknown, None)
        for alt in ("guests", "participants", "invitados"):
            if alt in params and "attendees" not in params:
                params["attendees"] = params.pop(alt)
        logger.info(f"create_event params normalizados: {params}")

    try:
        # ── Calendar ──
        if service == "calendar":
            if action == "list_events":
                period = params.pop("period", None)
                if period == "day":   params["days"] = 1
                elif period == "week": params["days"] = 7
                elif period == "month": params["days"] = 30
                events = await google_services.get_upcoming_events(user_id, **params)
                if not events:
                    return "No tienes eventos en ese período."
                lines = ["📅 Eventos:"]
                for e in events:
                    start_time = e.get("start", {}).get("dateTime",
                                 e.get("start", {}).get("date", ""))[:16].replace("T", " ")
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
                    lines.append(
                        f"• {e.get('Subject','Sin asunto')}\n"
                        f"  De: {e.get('From','?')[:40]}\n"
                        f"  {e.get('snippet','')[:80]}"
                    )
                return "\n\n".join(lines)

            elif action == "send_email":
                await google_services.send_email(user_id, **params)
                return f"✅ Correo enviado a {params.get('to')}."

            elif action == "get_email":
                emails = await google_services.get_email_full(user_id, **params)
                if not emails:
                    return "No hay correos que coincidan."
                email = emails[0]
                body = email.get("Body", email.get("snippet", "Sin contenido"))[:1500]
                return (
                    f"📧 De: {email.get('From','?')}\n"
                    f"Asunto: {email.get('Subject','Sin asunto')}\n"
                    f"Fecha: {email.get('Date','?')}\n\n{body}"
                )

        # ── Docs ──
        elif service == "docs":
            if action == "create":
                result = await google_services.create_doc(user_id, **params)
                return f"✅ Documento creado: {result.get('url', result.get('documentId', ''))}"
            elif action == "get_content":
                content = await google_services.get_doc_content(user_id, **params)
                return f"📄 Contenido del documento:\n{content[:1000]}"
            elif action == "append_text":
                await google_services.create_doc(user_id, **params)
                return "✅ Texto agregado al documento."

        # ── Sheets ──
        elif service == "sheets":
            if action == "create":
                result = await google_services.append_to_sheet(user_id, **params)
                return f"✅ Hoja creada: {result.get('link','')}"
            elif action == "read":
                data = await google_services.read_sheet(user_id, **params)
                if not data:
                    return "La hoja está vacía."
                rows = "\n".join([" | ".join(row) for row in data[:10]])
                return f"📊 Datos:\n{rows}"
            elif action in ("append", "write"):
                result = await google_services.append_to_sheet(user_id, **params)
                return f"✅ {result.get('updated_rows', result.get('updated_cells', '?'))} fila(s)/celda(s) actualizadas."

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


# ── Pending state handlers ────────────────────────────────────

async def handle_pending_domain(user_id: int, text: str, send_fn: SendFn) -> bool:
    """
    Intercepta respuestas a la sugerencia de dominio.
    Retorna True si el mensaje fue consumido.
    """
    domain_pending = memory.get_domain_pending(user_id)
    if not domain_pending.get("asked_at"):
        return False

    text_lower = text.strip().lower()
    state      = domain_pending.get("state", "")
    suggested  = domain_pending.get("suggested")

    if state == "awaiting_confirmation":
        if any(w in text_lower for w in ["sí", "si", "yes", "ok", "dale", "bueno", "claro", "activar", "activa"]):
            await activate_domain_pack(user_id, suggested, send_fn)
            memory.clear_domain_pending(user_id)
            return True

        elif any(w in text_lower for w in ["no", "otro", "otras", "opciones", "cambiar", "diferente"]):
            await send_fn("Claro, ¿cuál prefieres?\n\n" + provisioning.get_domains_menu_text())
            memory.set_domain_pending(user_id, {**domain_pending, "state": "awaiting_selection"})
            return True

        elif any(w in text_lower for w in ["saltar", "skip", "después", "luego", "omitir"]):
            memory.clear_domain_pending(user_id)
            await send_fn("Sin problema, puedes activarlo cuando quieras con /mi_dominio 🙌")
            return True

        return False

    if state == "awaiting_selection":
        domains = provisioning.DOMAINS_CATALOG
        selected_id = None

        if text_lower.strip() in [str(i) for i in range(1, len(domains) + 1)]:
            selected_id = domains[int(text_lower.strip()) - 1]["id"]
        elif text_lower.strip() in ["7", "general", "ninguno", "sin paquete"]:
            memory.clear_domain_pending(user_id)
            await send_fn("Perfecto, sin paquete específico. Puedes activarlo después con /mi_dominio ✌️")
            return True
        else:
            for d in domains:
                if d["id"] in text_lower or d["name"].lower() in text_lower:
                    selected_id = d["id"]
                    break

        if selected_id:
            await activate_domain_pack(user_id, selected_id, send_fn)
            memory.clear_domain_pending(user_id)
            return True

        return False

    return False


async def handle_pending_import(user_id: int, text: str, send_fn: SendFn) -> bool:
    """
    Intercepta confirmación de importación de memoria.
    Retorna True si el mensaje fue consumido.
    """
    prefs = memory.get_category(user_id, "preferencias") or {}
    if not prefs.get("_import_pending"):
        return False

    text_lower = text.strip().lower()

    if text_lower in ["si", "sí", "yes", "confirmar", "ok"]:
        snapshot_json = prefs.get("_import_snapshot")
        if not snapshot_json:
            await send_fn("No encontré el respaldo. Intenta /importar_memoria de nuevo.")
            _clear_import_pending(user_id)
            return True

        snapshot = json.loads(snapshot_json)
        ok = memory_backup.restore_from_snapshot(user_id, snapshot)
        _clear_import_pending(user_id)

        if ok:
            exported_at = snapshot.get("exported_at", "")[:10]
            await send_fn(
                f"Memoria restaurada desde el respaldo del {exported_at}.\n"
                f"Tu contexto, skills y configuración han sido recuperados."
            )
        else:
            await send_fn(
                "Hubo un error al restaurar la memoria. "
                "Tu memoria actual no fue modificada. Intenta de nuevo."
            )
        return True

    elif text_lower in ["no", "cancelar", "cancel"]:
        _clear_import_pending(user_id)
        await send_fn("Importación cancelada. Tu memoria actual no fue modificada.")
        return True

    return False


def _clear_import_pending(user_id: int):
    prefs = memory.get_category(user_id, "preferencias") or {}
    prefs.pop("_import_pending", None)
    prefs.pop("_import_snapshot", None)
    memory.set_category(user_id, "preferencias", prefs)


async def activate_domain_pack(user_id: int, domain_id: str, send_fn: SendFn):
    """
    Activa todas las skills de un paquete de dominio.
    Agnóstico al canal — usa send_fn para notificar al usuario.
    """
    domain = provisioning.get_domain_by_id(domain_id)
    if not domain:
        return

    domain_skills = provisioning.get_domain_skills(domain_id)
    memory.set_user_domain(user_id, domain_id)
    await provisioning._inject_domain_seed(user_id, domain_id, memory)

    activated = []
    for skill_data in domain_skills:
        activated_skill = await skills_engine.activate_skill_personalized(
            user_id, skill_data, memory, call_groq
        )
        if activated_skill:
            activated.append(f"{skill_data['emoji']} {skill_data['name']}")

    skills_text = "\n".join(f"  {s}" for s in activated)
    await send_fn(
        f"✅ Paquete {domain['emoji']} {domain['name']} activado\n\n"
        f"Skills listas:\n{skills_text}\n\n"
        f"Están personalizadas con tu contexto. "
        f"Usa /mis_skills para verlas o /mi_dominio para cambiar el paquete."
    )


# ── Core engine — process_message ────────────────────────────

async def process_message(
    msg: InboundMessage,
    send_fn: SendFn,
    typing_fn: TypingFn = None,
) -> None:
    """
    Procesa un mensaje normalizado de cualquier canal.

    Args:
        msg:       mensaje normalizado (InboundMessage)
        send_fn:   función async que envía una respuesta al usuario
        typing_fn: función async opcional que muestra indicador de escritura
    """
    import tz_utils
    from datetime import datetime

    user_id = msg.monday_id

    # ── Rate limiting ─────────────────────────────────────────
    allowed, reason = security.check_rate_limit(user_id, is_voice=msg.is_voice)
    if not allowed:
        await send_fn(reason)
        return

    # ── Sanitizar y limitar longitud ──────────────────────────
    clean_text, was_truncated = security.sanitize_text(msg.text)
    if not clean_text:
        return
    if was_truncated:
        await send_fn(
            f"ℹ️ Tu mensaje era muy largo y fue recortado a {security.MAX_MESSAGE_LENGTH} caracteres."
        )
    msg = InboundMessage(
        monday_id=msg.monday_id,
        channel=msg.channel,
        text=clean_text,
        is_voice=msg.is_voice,
        subject=msg.subject,
        thread_id=msg.thread_id,
        raw=msg.raw,
    )

    # ── Pending states (interceptan antes de ir a Groq) ──────
    if await handle_pending_domain(user_id, msg.text, send_fn):
        return
    if await handle_pending_import(user_id, msg.text, send_fn):
        return

    # ── Indicador de escritura ────────────────────────────────
    if typing_fn:
        try:
            await typing_fn()
        except Exception:
            pass

    # ── Construir system prompt ───────────────────────────────
    google_status = (
        "✅ Conectado" if memory.has_google_connected(user_id)
        else "❌ No conectado (usa /conectar_google)"
    )

    user_data = memory.get_user(user_id)
    user_now  = tz_utils.now_for_user(user_data)
    fecha_actual = user_now.strftime("%Y-%m-%d %H:%M (%A)")

    ctx = conversation_context.detect_context(msg.text)

    prompt_with_date = BASE_SYSTEM_PROMPT.replace("{fecha_actual}", fecha_actual)
    system_prompt    = memory.build_system_prompt(user_id, prompt_with_date)

    # Seed de dominio
    seed_context = domain_seeds.build_seed_summary(memory.get_domain_seed(user_id))
    if seed_context:
        system_prompt += "\n\n" + seed_context

    system_prompt += f"\n\nEstado Google Workspace del usuario: {google_status}"

    # Estilo de respuesta según canal
    channel_style = get_channel_style(msg.channel)
    system_prompt += f"\n\nESTILO DE RESPUESTA PARA ESTE CANAL: {channel_style}"

    # Contexto de conversación
    context_block = conversation_context.build_context_prompt(user_id, ctx, memory)
    if context_block:
        system_prompt += context_block

    hint = conversation_context.get_context_hint(ctx)
    if hint:
        system_prompt += f"\n\nINSTRUCCIÓN DE CONTEXTO: {hint}"

    # Skills activas
    active_skills = memory.get_skills(user_id)
    skills_block  = skills_engine.build_skills_prompt_block(active_skills, ctx)
    if skills_block:
        system_prompt += skills_block

    # Bootstrap workspace doc en background
    if memory.has_google_connected(user_id):
        asyncio.create_task(workspace_memory.bootstrap_existing_user(user_id))

    # Memoria extendida del Google Doc
    if memory.has_google_connected(user_id):
        try:
            doc_content = await workspace_memory.read_memory_doc(user_id)
            if doc_content:
                system_prompt += (
                    "\n\n=== MEMORIA EXTENDIDA (Google Doc) ===\n"
                    + doc_content[:3000]
                    + "\n======================================"
                )
        except Exception as e:
            logger.warning(f"No se pudo leer workspace doc: {e}")

    # ── Llamar a Groq ─────────────────────────────────────────
    hist = memory.get_history(user_id)
    try:
        full_reply = await call_groq(system_prompt, hist, msg.text)
    except Exception as e:
        logger.error(f"Error llamando a Groq: {e}")
        await send_fn("Ups, hubo un problema. Intenta en un momento 🙏")
        return

    # ── Ejecutar acciones de Google ───────────────────────────
    action_result = ""
    action_match  = re.search(r'\[ACTION:\s*({.+?})\]', full_reply, re.DOTALL)
    if action_match:
        try:
            action_data   = json.loads(action_match.group(1))
            action_result = await execute_google_action(user_id, action_data)
        except json.JSONDecodeError:
            logger.error("No se pudo parsear el ACTION JSON")

    # ── Extraer FACTs ─────────────────────────────────────────
    facts_found = re.findall(r'\[FACT:\s*(.+?)\]', full_reply)
    for fact in facts_found:
        memory.add_fact(user_id, fact.strip())

    if facts_found:
        asyncio.create_task(skills_engine.auto_evolve_from_facts(
            user_id, [f.strip() for f in facts_found], memory, call_groq
        ))
        asyncio.create_task(domain_seeds.auto_enrich_seed_from_fact(
            user_id, [f.strip() for f in facts_found], memory
        ))
    if facts_found and memory.has_google_connected(user_id):
        asyncio.create_task(workspace_memory.sync_memory_to_doc(user_id))

    # ── Limpiar respuesta ─────────────────────────────────────
    clean_reply = re.sub(r'\[ACTION:.*?\]', '', full_reply, flags=re.DOTALL)
    clean_reply = re.sub(r'\[FACT:.*?\]',  '', clean_reply)
    clean_reply = clean_reply.strip()

    # ── Guardar en historial ──────────────────────────────────
    memory.add_message(user_id, "user",      msg.text)
    memory.add_message(user_id, "assistant", clean_reply)

    # ── Enviar respuesta ──────────────────────────────────────
    if clean_reply:
        await send_fn(clean_reply)

    if action_result:
        await send_fn(action_result)
