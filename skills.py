"""
skills.py — Sistema de skills personalizadas por usuario.

Una skill es una plantilla de instrucciones guardada con:
  - nombre: identificador amigable
  - descripción: cuándo usarla
  - contenido: el prompt/instrucción
  - trigger: cuándo se activa automáticamente (heartbeat, morning, manual)

El bot detecta cuándo aplicar una skill según el contexto del mensaje.
"""

# Biblioteca de skills predefinidas que el usuario puede activar
DEFAULT_SKILLS = [
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
        "emoji": "📧"
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
        "emoji": "📝"
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
        "emoji": "✅"
    },
    {
        "id": "daily_brief",
        "name": "Briefing matutino",
        "description": "Resumen personalizado cada mañana",
        "content": (
            "Cada mañana incluye en el briefing: una frase motivacional breve, "
            "el clima si está disponible, y un recordatorio del objetivo más "
            "importante del usuario para esta semana."
        ),
        "trigger": "morning",
        "emoji": "🌅"
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
        "emoji": "🚨"
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
        "emoji": "🎯"
    },
]


def get_skills_catalog() -> str:
    """Devuelve el catálogo de skills disponibles como texto formateado."""
    lines = ["🛠 *Skills disponibles:*\n"]
    for i, skill in enumerate(DEFAULT_SKILLS, 1):
        lines.append(
            f"{skill['emoji']} *{i}. {skill['name']}*\n"
            f"   {skill['description']}\n"
            f"   Trigger: `{skill['trigger']}`"
        )
    return "\n\n".join(lines)


def find_skill_by_name(name: str) -> dict | None:
    """Busca una skill por nombre o ID (case insensitive)."""
    name_lower = name.lower()
    for skill in DEFAULT_SKILLS:
        if name_lower in skill["name"].lower() or name_lower == skill["id"]:
            return skill
    return None
