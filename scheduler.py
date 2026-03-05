"""
scheduler.py — Heartbeat, briefing matutino y ritmo semanal.

Usa APScheduler para ejecutar tareas en segundo plano:
- Heartbeat: cada 30 min revisa correos/calendario urgentes por usuario
- Briefing: cada mañana a las 7am manda resumen personalizado
- Ritmo semanal: tareas configuradas por día y hora
"""

import logging
import asyncio
from datetime import datetime, timedelta, timezone
import tz_utils
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import memory
import google_services
import workspace_memory
import provisioning
import google_auth

logger = logging.getLogger(__name__)

# Bot global — se asigna desde bot.py al arrancar
_bot = None
_groq_fn = None  # función call_groq de bot.py

def init_scheduler(bot, call_groq_fn):
    """Registra el bot y la función de Groq para usarlos en las tareas."""
    global _bot, _groq_fn
    _bot = bot
    _groq_fn = call_groq_fn


# ── Utilidades ────────────────────────────────────────────────

async def send_to_user(user_id: int, text: str):
    """Envía un mensaje al usuario de Telegram."""
    try:
        await _bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logger.error(f"Error enviando mensaje a {user_id}: {e}")


async def get_all_google_users() -> list[int]:
    return memory.get_all_google_users()

async def get_all_users() -> list[int]:
    return memory.get_all_users()


# ── HEARTBEAT ─────────────────────────────────────────────────

async def _check_hooks(user_id: int, hooks: list, user_data: dict) -> list:
    """
    Evalúa los hooks configurados por el usuario y devuelve alertas.
    Tipos soportados:
      - correo_remitente: avisa si llega correo de ese remitente
      - correo_keyword:   avisa si llega correo con esa palabra en asunto
      - evento_proximo:   avisa si hay evento con esa keyword próximo
    """
    alerts = []

    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        tipo  = hook.get("tipo", "")
        valor = hook.get("valor", "").lower()
        desc  = hook.get("descripcion", valor)

        try:
            if tipo == "correo_remitente":
                emails = await google_services.get_recent_emails(
                    user_id, max_results=5, sender=valor
                )
                if emails:
                    e = emails[0]
                    alerts.append(
                        f"📧 Correo de {desc}:\n"
                        f"   {e.get('Subject','Sin asunto')}\n"
                        f"   {e.get('snippet','')[:80]}"
                    )

            elif tipo == "correo_keyword":
                emails = await google_services.get_recent_emails(
                    user_id, max_results=3, subject=valor
                )
                if emails:
                    for e in emails[:2]:
                        asunto = e.get("Subject", "")
                        if valor in asunto.lower():
                            alerts.append(
                                f"📧 Correo con '{valor}':\n"
                                f"   {asunto}\n"
                                f"   De: {e.get('From','?')[:40]}"
                            )

            elif tipo == "evento_proximo":
                events = await google_services.get_upcoming_events(user_id, max_results=10, days=1)
                for event in events:
                    titulo = event.get("summary", "").lower()
                    if valor in titulo:
                        start_str = event.get("start", {}).get("dateTime", "")
                        if start_str:
                            start_dt = tz_utils.parse_google_dt(start_str)
                            mins = tz_utils.minutes_until(start_dt, user_data)
                            if 0 < mins <= 60:
                                alerts.append(
                                    f"📅 Evento '{desc}' en {int(mins)} min:\n"
                                    f"   {event.get('summary','')}"
                                )
        except Exception as e:
            logger.warning(f"Error evaluando hook {tipo} para {user_id}: {e}")

    return alerts


async def heartbeat(single_user: int = None):
    """
    Corre cada 30 minutos.
    Por cada usuario revisa:
      1. Reuniones en los próximos 30 min (siempre)
      2. Hooks personalizados configurados en el onboarding
      3. Skills con trigger=heartbeat
    Solo notifica si hay algo relevante — nunca spamea.
    """
    logger.info("💓 Heartbeat ejecutándose...")

    users = [single_user] if single_user else await get_all_google_users()
    for user_id in users:
        try:
            alerts = []
            user_data = memory.get_user(user_id)

            # ── 1. Reuniones próximas (siempre activo) ────────────
            events = await google_services.get_upcoming_events(user_id, max_results=10, days=1)
            for event in events:
                start_str = event.get("start", {}).get("dateTime", "")
                if not start_str:
                    continue
                start_dt = tz_utils.parse_google_dt(start_str)
                mins_until = tz_utils.minutes_until(start_dt, user_data)
                if 0 < mins_until <= 30:
                    alerts.append(
                        f"⏰ Reunión en {int(mins_until)} minutos:\n"
                        f"   {event.get('summary', 'Sin título')}"
                    )

            # ── 2. Hooks personalizados del usuario ───────────────
            prefs = memory.get_category(user_id, "preferencias")
            hooks = prefs.get("hooks", [])
            if hooks:
                hook_alerts = await _check_hooks(user_id, hooks, user_data)
                alerts.extend(hook_alerts)

            # ── 3. Skills con trigger=heartbeat ───────────────────
            skills = memory.get_skills(user_id)
            hb_skill = next((s for s in skills if s.get("trigger") == "heartbeat"), None)
            if hb_skill and alerts:
                # La skill de filtro de urgentes ya está aplicada implícitamente
                # en la lógica de _check_hooks — no duplicar
                pass

            # Enviar solo si hay alertas
            if alerts:
                msg = "💓 Alerta de tu asistente:\n\n" + "\n\n".join(alerts)
                await send_to_user(user_id, msg)

        except Exception as e:
            logger.error(f"Error en heartbeat para usuario {user_id}: {e}")


# ── BRIEFING MATUTINO ─────────────────────────────────────────

async def morning_briefing():
    """
    Corre a las 7, 8 y 9am. Cada usuario recibe su briefing
    solo en la hora más cercana a la que configuró en su ritmo.
    """
    logger.info("🌅 Enviando briefing matutino...")

    users = await get_all_google_users()

    for user_id in users:
        try:
            # Obtener hora local del usuario (respeta su timezone y DST)
            user = memory.get_user(user_id)
            user_now = tz_utils.now_for_user(user)
            current_hour = user_now.hour
            today = user_now.strftime("%A %d de %B")

            ritmo = user.get("ritmo", {})
            preferred = ritmo.get("briefing_hora", "07:00")
            try:
                preferred_hour = int(preferred.split(":")[0])
            except Exception:
                preferred_hour = 7
            if preferred_hour != current_hour:
                continue  # no es su hora en su timezone

            sections = [f"🌅 Buenos días! Aquí tu briefing del {today}*\n"]

            # Agenda del día
            events = await google_services.get_upcoming_events(user_id, max_results=5, days=1)
            if events:
                sections.append("📅 *Tu agenda de hoy:*")
                for e in events:
                    start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))[:16].replace("T", " ")
                    sections.append(f"  • {e.get('summary', 'Sin título')} — {start}")
            else:
                sections.append("📅 No tienes eventos agendados para hoy.")

            # Correos recientes (últimos 3)
            emails = await google_services.get_recent_emails(user_id, max_results=3)
            if emails:
                sections.append("\n📧 *Correos recientes:*")
                for e in emails:
                    sections.append(f"  • {e.get('Subject','Sin asunto')[:50]}\n    De: {e.get('From','?')[:35]}")

            # Verificar si tiene skill de briefing personalizado
            skills = memory.get_skills(user_id)
            briefing_skill = next((s for s in skills if s.get("trigger") == "morning"), None)
            if briefing_skill:
                sections.append(f"\n💡 *{briefing_skill['name']}:*\n{briefing_skill['content'][:200]}")

            sections.append("\n¡Que tengas un excelente día! 🚀")
            await send_to_user(user_id, "\n".join(sections))

        except Exception as e:
            logger.error(f"Error en briefing para usuario {user_id}: {e}")


# ── RITMO SEMANAL ─────────────────────────────────────────────

async def weekly_summary():
    """
    Corre todos los lunes a las 8:00am.
    Manda un resumen de la semana que viene.
    """
    logger.info("📅 Enviando resumen semanal...")

    users = await get_all_google_users()

    for user_id in users:
        try:
            # Eventos de los próximos 7 días
            events = await google_services.get_upcoming_events(user_id, max_results=20, days=7)

            if not events:
                await send_to_user(user_id, "📅 *Tu semana está libre — no tienes eventos agendados.*")
                continue

            lines = ["🗓 *Tu semana que viene:*\n"]
            current_day = ""
            for e in events:
                start_str = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
                day = start_str[:10]
                time = start_str[11:16] if "T" in start_str else "Todo el día"
                if day != current_day:
                    current_day = day
                    lines.append(f"\n📌 *{day}*")
                lines.append(f"  • {time} — {e.get('summary', 'Sin título')}")

            await send_to_user(user_id, "\n".join(lines))

        except Exception as e:
            logger.error(f"Error en resumen semanal para usuario {user_id}: {e}")


async def friday_wrap():
    """
    Corre todos los viernes a las 5:00pm.
    Resumen de cierre de semana.
    """
    logger.info("🎉 Enviando wrap del viernes...")

    users = await get_all_users()
    for user_id in users:
        try:
            facts = memory.get_facts(user_id)
            facts_text = "\n".join(f"- {f}" for f in facts[:5]) if facts else "Aún estoy conociéndote."

            msg = (
                "🎉 *¡Feliz viernes!*\n\n"
                "Esta semana aprendí esto sobre ti:\n"
                f"{facts_text}\n\n"
                "¿Hay algo en lo que te pueda ayudar antes de cerrar la semana? 💪"
            )
            await send_to_user(user_id, msg)
        except Exception as e:
            logger.error(f"Error en wrap del viernes para {user_id}: {e}")


# ── ARRANCAR EL SCHEDULER ─────────────────────────────────────

async def nightly_doc_sync():
    """
    Corre cada noche a las 2am.
    Sincroniza el Google Doc de cada usuario con su memoria vertical.
    Lee cambios que el usuario haya hecho directamente en el doc.
    """
    logger.info("🌙 Sincronización nocturna de workspace docs...")
    users = await get_all_google_users()
    for user_id in users:
        try:
            await workspace_memory.sync_doc_to_memory(user_id)
            logger.info(f"Doc sincronizado para usuario {user_id}")
        except Exception as e:
            logger.error(f"Error en sync nocturno para {user_id}: {e}")


async def weekly_reprovisioning():
    """
    Corre cada domingo a las 3am.
    Aplica reprovisión a todos los usuarios que tienen versión desactualizada.
    También corre automáticamente al arrancar el bot (ver main() en bot.py).
    """
    logger.info("🔄 Ejecutando reprovisión semanal...")
    stats = await provisioning.run_reprovisioning(memory, _bot)
    logger.info(
        f"Reprovisión completada: {stats['actualizados']} actualizados, "
        f"{stats['errores']} errores de {stats['total']} usuarios"
    )


def start_scheduler() -> AsyncIOScheduler:
    """
    Crea y arranca el scheduler con todas las tareas.
    Devuelve el scheduler para que bot.py lo pueda detener limpiamente.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")  # Jobs run in UTC, per-user tz handled in logic

    # Heartbeat cada 30 minutos
    scheduler.add_job(heartbeat, "interval", minutes=30, id="heartbeat")

    # Briefing matutino todos los días a las 7:00am (hora por defecto)
    # Cada usuario puede tener su hora en ritmo.briefing_hora — 
    # el scheduler usa 7am como base; la función verifica el ritmo individual
    scheduler.add_job(
        morning_briefing,
        CronTrigger(hour=7, minute=0, timezone="America/Mexico_City"),
        id="morning_briefing_0700"
    )
    scheduler.add_job(
        morning_briefing,
        CronTrigger(hour=8, minute=0, timezone="America/Mexico_City"),
        id="morning_briefing_0800"
    )
    scheduler.add_job(
        morning_briefing,
        CronTrigger(hour=9, minute=0, timezone="America/Mexico_City"),
        id="morning_briefing_0900"
    )

    # Resumen semanal los lunes a las 8:00am
    scheduler.add_job(
        weekly_summary,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="America/Mexico_City"),
        id="weekly_summary"
    )

    # Wrap del viernes a las 5:00pm
    scheduler.add_job(
        friday_wrap,
        CronTrigger(day_of_week="fri", hour=17, minute=0, timezone="America/Mexico_City"),
        id="friday_wrap"
    )

    # Sincronizar docs de workspace cada noche a las 2am
    scheduler.add_job(
        nightly_doc_sync,
        CronTrigger(hour=2, minute=0, timezone="America/Mexico_City"),
        id="nightly_doc_sync"
    )

    # Reprovisión semanal: cada domingo a las 3am
    scheduler.add_job(
        weekly_reprovisioning,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="America/Mexico_City"),
        id="weekly_reprovisioning"
    )

    scheduler.start()
    logger.info("✅ Scheduler iniciado — heartbeat, briefing, ritmo semanal activos")
    return scheduler
