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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import memory
import google_services
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

async def heartbeat(single_user: int = None):
    """
    Corre cada 30 minutos.
    Por cada usuario con Google conectado:
    - Revisa si hay correos urgentes (sin leer, de contactos importantes)
    - Revisa si hay reuniones en los próximos 30 minutos
    - Solo notifica si hay algo relevante — nunca spamea
    """
    logger.info("💓 Heartbeat ejecutándose...")

    users = [single_user] if single_user else await get_all_google_users()
    now = datetime.now()

    for user_id in users:
        try:
            alerts = []

            # Revisar eventos próximos (en los siguientes 30 min)
            events = await google_services.get_upcoming_events(user_id, max_results=5, days=1)
            for event in events:
                start_str = event.get("start", {}).get("dateTime", "")
                if not start_str:
                    continue
                # Parsear hora del evento
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                start_local = start_dt.replace(tzinfo=None)
                mins_until = (start_local - now).total_seconds() / 60
                if 0 < mins_until <= 30:
                    alerts.append(
                        f"⏰ Tienes una reunión en {int(mins_until)} minutos:\n"
                        f"   *{event.get('summary', 'Sin título')}*"
                    )

            # Revisar si hay skills de heartbeat configuradas para este usuario
            skills = memory.get_skills(user_id)
            heartbeat_skill = next((s for s in skills if s.get("trigger") == "heartbeat"), None)

            if alerts:
                msg = "💓 *Alerta de tu asistente:*\n\n" + "\n\n".join(alerts)
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

    current_hour = datetime.now().hour
    users = await get_all_google_users()
    today = datetime.now().strftime("%A %d de %B")

    for user_id in users:
        try:
            # Verificar si este usuario quiere el briefing en esta hora
            user = memory.get_user(user_id)
            ritmo = user.get("ritmo", {})
            preferred = ritmo.get("briefing_hora", "07:00")
            try:
                preferred_hour = int(preferred.split(":")[0])
            except Exception:
                preferred_hour = 7
            if preferred_hour != current_hour:
                continue  # no es su hora

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

def start_scheduler() -> AsyncIOScheduler:
    """
    Crea y arranca el scheduler con todas las tareas.
    Devuelve el scheduler para que bot.py lo pueda detener limpiamente.
    """
    scheduler = AsyncIOScheduler(timezone="America/Mexico_City")

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

    scheduler.start()
    logger.info("✅ Scheduler iniciado — heartbeat, briefing, ritmo semanal activos")
    return scheduler
