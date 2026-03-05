"""
provisioning.py — Motor de reprovisión del asistente.

CÓMO USAR CUANDO HACES UN CAMBIO:
  1. Incrementa MANIFEST_VERSION (ej: "1.0.0" → "1.1.0")
  2. Agrega una entrada a CHANGELOG describiendo qué cambió
  3. Modifica lo que necesites en SYSTEM_PROMPT, SKILLS_CATALOG, etc.
  4. Haz git push → Railway redeploy
  5. Al arrancar, el scheduler detecta usuarios con versión vieja y los actualiza

REGLAS DE VERSIONING:
  MAJOR (1.x.x → 2.x.x): cambio de comportamiento radical, nuevo onboarding
  MINOR (x.1.x → x.2.x): nuevas skills, nuevo contexto, mejoras de prompt
  PATCH (x.x.1 → x.x.2): correcciones de texto, ajustes menores

QUÉ TOCA Y QUÉ NO TOCA LA REPROVISIÓN:
  ✅ TOCA:   system_prompt_version, skills disponibles en catálogo
  ✅ TOCA:   notificación al usuario sobre qué cambió
  ❌ NO TOCA: identidad, trabajo, proyectos, metas, relaciones, ritmo
  ❌ NO TOCA: history, google_tokens, skills activas del usuario
  ❌ NO TOCA: onboarding_done (un usuario que ya lo hizo no lo rehace)
"""

import logging
from packaging.version import Version  # pip install packaging

logger = logging.getLogger(__name__)

# ── VERSIÓN ACTUAL DEL SISTEMA ────────────────────────────────
# Incrementa esto con cada cambio que quieras propagar a usuarios existentes
MANIFEST_VERSION = "1.0.0"

# ── CHANGELOG ─────────────────────────────────────────────────
# Describe qué cambió en cada versión. Se envía al usuario al reprovisionarse.
CHANGELOG = {
    "1.0.0": {
        "titulo": "Lanzamiento inicial del asistente",
        "cambios": [
            "Memoria vertical por categorías (identidad, trabajo, proyectos, metas, relaciones, ritmo)",
            "Integración completa con Google Workspace (Calendar, Gmail, Docs, Sheets, Drive)",
            "Onboarding de 8 pasos con extracción inteligente",
            "Heartbeat con hooks personalizados cada 30 minutos",
            "Briefing matutino personalizado según tu horario",
            "Workspace como memoria extendida (Google Doc bidireccional)",
            "Detección automática de contexto por conversación",
            "6 skills activables por el usuario",
        ],
        "accion_requerida": None,  # None = no se pide nada al usuario
    },
    # Ejemplo de cómo agregar la próxima versión:
    # "1.1.0": {
    #     "titulo": "Identidad del asistente + nuevas skills",
    #     "cambios": [
    #         "El asistente ahora tiene nombre y personalidad configurable",
    #         "3 nuevas skills: resumen ejecutivo, análisis de correos, planificación semanal",
    #     ],
    #     "accion_requerida": "Usa /nombre_asistente para personalizar cómo me llamo",
    # },
}

# ── SYSTEM PROMPT VERSIONADO ──────────────────────────────────
# Esta es la fuente de verdad del comportamiento base del bot.
# Al cambiar esto e incrementar MANIFEST_VERSION, todos los usuarios
# recibirán el nuevo prompt en su próxima sesión.
SYSTEM_PROMPT = """Eres un asistente personal inteligente con acceso a Google Workspace.

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
5. Sé conciso y útil. Responde según las preferencias de tono del usuario.
6. Cuando el contexto detectado sea trabajo, enfócate en proyectos y metas activas.
7. Nunca inventes información sobre el usuario — solo usa lo que está en su memoria.

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

# ── CATÁLOGO DE SKILLS VERSIONADO ────────────────────────────
# Al agregar nuevas skills aquí e incrementar MANIFEST_VERSION,
# quedarán disponibles para todos los usuarios sin activarse automáticamente.
SKILLS_CATALOG = [
    {
        "id": "formal_email",
        "name": "Correo formal",
        "description": "Redactar correos profesionales y formales",
        "content": (
            "Cuando redactes un correo, usa un tono profesional y formal. "
            "Incluye saludo apropiado, desarrollo claro y despedida cordial. "
            "Revisa gramática y ortografía antes de enviar."
        ),
        "trigger": "manual",
        "emoji": "📧",
        "version_added": "1.0.0",
    },
    {
        "id": "meeting_notes",
        "name": "Acta de reunión",
        "description": "Convertir notas en actas estructuradas",
        "content": (
            "Cuando el usuario comparta notas de una reunión, "
            "estructura la información en: Fecha, Asistentes, Puntos tratados, "
            "Acuerdos y Próximos pasos. Usa formato limpio y profesional."
        ),
        "trigger": "manual",
        "emoji": "📝",
        "version_added": "1.0.0",
    },
    {
        "id": "task_manager",
        "name": "Gestor de tareas",
        "description": "Organizar y priorizar tareas pendientes",
        "content": (
            "Ayuda al usuario a organizar sus tareas. Cuando mencione pendientes, "
            "clasifícalos por urgencia (Alta/Media/Baja) e impacto. "
            "Sugiere en qué orden abordarlos y ofrece dividir tareas grandes."
        ),
        "trigger": "manual",
        "emoji": "✅",
        "version_added": "1.0.0",
    },
    {
        "id": "daily_brief",
        "name": "Briefing matutino",
        "description": "Resumen personalizado cada mañana",
        "content": (
            "Cada mañana incluye en el briefing: una frase motivacional breve, "
            "y un recordatorio del objetivo más importante del usuario para esta semana."
        ),
        "trigger": "morning",
        "emoji": "🌅",
        "version_added": "1.0.0",
    },
    {
        "id": "urgent_filter",
        "name": "Filtro de urgentes",
        "description": "Alertar solo sobre correos y eventos realmente urgentes",
        "content": (
            "En el heartbeat, considera urgente solo: correos de jefes/clientes "
            "directos, palabras clave como 'urgente', 'ASAP', 'importante', "
            "reuniones en menos de 15 minutos. Ignora newsletters y promociones."
        ),
        "trigger": "heartbeat",
        "emoji": "🚨",
        "version_added": "1.0.0",
    },
    {
        "id": "weekly_goals",
        "name": "Metas semanales",
        "description": "Seguimiento de metas cada lunes",
        "content": (
            "Los lunes, además del resumen de agenda, pregunta al usuario cuál es "
            "su meta más importante de la semana y guárdala en memoria. "
            "Los viernes, recuérdale esa meta y pregunta cómo le fue."
        ),
        "trigger": "morning",
        "emoji": "🎯",
        "version_added": "1.0.0",
    },
]

# ── PASOS DE ONBOARDING VERSIONADOS ──────────────────────────
# Si agregas pasos nuevos en una versión MAJOR, los usuarios existentes
# con onboarding_done=True NO los ven (ya pasaron). Solo afecta a nuevos usuarios
# o a usuarios que reinicien con /olvidar.
ONBOARDING_VERSION = "1.0.0"

# ── MOTOR DE REPROVISIÓN ──────────────────────────────────────

def _version_lt(v1: str, v2: str) -> bool:
    """True si v1 es menor que v2."""
    try:
        return Version(v1) < Version(v2)
    except Exception:
        return v1 != v2


def get_pending_changelog(from_version: str) -> list[str]:
    """
    Devuelve la lista de cambios entre from_version y MANIFEST_VERSION.
    Se usa para notificar al usuario qué cambió.
    """
    changes = []
    for version, entry in sorted(CHANGELOG.items(), key=lambda x: Version(x[0])):
        if _version_lt(from_version, version):
            changes.append(f"v{version} — {entry['titulo']}:")
            for c in entry["cambios"]:
                changes.append(f"  • {c}")
            if entry.get("accion_requerida"):
                changes.append(f"  👉 {entry['accion_requerida']}")
    return changes


async def reprovision_user(user_id: int, memory_module, bot=None) -> bool:
    """
    Aplica reprovisión a un usuario específico.
    
    - Actualiza bot_version en la DB
    - Actualiza catálogo de skills disponibles (sin tocar las activas)
    - Notifica al usuario si tiene Telegram activo
    - NUNCA toca memoria personal del usuario
    
    Devuelve True si se reprovisionó, False si ya estaba actualizado.
    """
    user = memory_module.get_user(user_id)
    current_version = user.get("bot_version", "0.0.0")

    if not _version_lt(current_version, MANIFEST_VERSION):
        return False  # ya está actualizado

    logger.info(f"Reprovisionando usuario {user_id}: {current_version} → {MANIFEST_VERSION}")

    # 1. Obtener changelog para notificar
    changes = get_pending_changelog(current_version)

    # 2. Actualizar bot_version en la DB
    memory_module.set_bot_version(user_id, MANIFEST_VERSION)

    # 3. Notificar al usuario si el bot está disponible
    if bot and changes:
        try:
            msg = (
                "🔄 Actualicé mis capacidades. Aquí los cambios:\n\n"
                + "\n".join(changes)
                + "\n\nTu memoria personal está intacta — no perdiste nada."
            )
            await bot.send_message(chat_id=user_id, text=msg)
        except Exception as e:
            logger.warning(f"No se pudo notificar al usuario {user_id}: {e}")

    return True


async def run_reprovisioning(memory_module, bot=None) -> dict:
    """
    Corre la reprovisión para todos los usuarios que tienen una versión vieja.
    Llamar al arrancar el bot y semanalmente desde el scheduler.
    
    Devuelve estadísticas: {total, actualizados, errores}
    """
    stats = {"total": 0, "actualizados": 0, "errores": 0}

    users = memory_module.get_all_users()
    stats["total"] = len(users)

    for user_id in users:
        try:
            updated = await reprovision_user(user_id, memory_module, bot)
            if updated:
                stats["actualizados"] += 1
        except Exception as e:
            logger.error(f"Error reprovisionando usuario {user_id}: {e}")
            stats["errores"] += 1

    logger.info(
        f"Reprovisión completa: {stats['actualizados']}/{stats['total']} actualizados, "
        f"{stats['errores']} errores"
    )
    return stats


def get_current_system_prompt() -> str:
    """Devuelve el system prompt de la versión actual del manifiesto."""
    return SYSTEM_PROMPT


def get_skills_catalog() -> list:
    """Devuelve el catálogo completo de skills de la versión actual."""
    return SKILLS_CATALOG


def get_skills_catalog_text() -> str:
    """Devuelve el catálogo de skills formateado como texto para Telegram."""
    lines = [f"🛠 Skills disponibles (v{MANIFEST_VERSION}):\n"]
    for i, skill in enumerate(SKILLS_CATALOG, 1):
        lines.append(
            f"{skill['emoji']} {i}. {skill['name']}\n"
            f"   {skill['description']}\n"
            f"   Trigger: {skill['trigger']}"
        )
    return "\n\n".join(lines)


def find_skill_by_name(name: str) -> dict | None:
    """Busca una skill en el catálogo por nombre o ID."""
    name_lower = name.lower()
    for skill in SKILLS_CATALOG:
        if name_lower in skill["name"].lower() or name_lower == skill["id"]:
            return skill
    return None
