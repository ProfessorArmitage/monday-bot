"""
conversation_context.py — Detección automática del contexto de conversación.

El bot detecta de qué área está hablando el usuario y carga
solo la memoria relevante para ese contexto, haciendo las
respuestas más precisas y el prompt más eficiente.

Contextos disponibles:
  - trabajo:       proyectos, equipo, responsabilidades
  - calendario:    eventos, agenda, reuniones
  - correo:        gmail, mensajes, comunicación
  - documentos:    docs, sheets, drive, archivos
  - metas:         objetivos, prioridades, progreso
  - personal:      vida personal, familia, rutinas
  - general:       conversación sin contexto específico
"""

import re

# Keywords por contexto — se evalúan contra el mensaje del usuario
CONTEXT_KEYWORDS = {
    "calendario": [
        "reunión", "reunion", "evento", "agenda", "calendario", "cita",
        "meeting", "schedule", "mañana", "semana", "mes", "hoy",
        "agendar", "recordar", "reminder", "disponibilidad"
    ],
    "correo": [
        "correo", "email", "mail", "gmail", "mensaje", "inbox",
        "enviar", "responder", "leer", "recibí", "mándame", "escríbele",
        "asunto", "remitente", "bandeja"
    ],
    "documentos": [
        "documento", "doc", "sheet", "hoja", "archivo", "drive",
        "excel", "word", "crear", "abrir", "compartir", "editar",
        "reporte", "informe", "presentación"
    ],
    "trabajo": [
        "proyecto", "tarea", "cliente", "equipo", "trabajo", "oficina",
        "sprint", "entrega", "deadline", "presentar", "jefe", "empresa",
        "reunión de trabajo", "propuesta", "contrato", "factura"
    ],
    "metas": [
        "meta", "objetivo", "goal", "prioridad", "enfoque", "lograr",
        "avance", "progreso", "plan", "estrategia", "resultado",
        "esta semana", "este mes", "este año"
    ],
    "personal": [
        "familia", "casa", "fin de semana", "vacaciones", "salud",
        "ejercicio", "amigos", "personal", "hobby", "descanso"
    ],
}

# Cuánta memoria cargar por contexto
CONTEXT_MEMORY_FOCUS = {
    "calendario":  ["identidad", "ritmo", "relaciones"],
    "correo":      ["identidad", "relaciones", "trabajo"],
    "documentos":  ["identidad", "trabajo", "proyectos"],
    "trabajo":     ["trabajo", "proyectos", "relaciones", "metas"],
    "metas":       ["metas", "proyectos", "ritmo"],
    "personal":    ["identidad", "vida_personal", "preferencias"],
    "general":     None,  # None = cargar todo
}


def detect_context(message: str) -> str:
    """
    Detecta el contexto de la conversación basado en el mensaje.
    Devuelve el nombre del contexto más probable.
    """
    message_lower = message.lower()
    scores = {ctx: 0 for ctx in CONTEXT_KEYWORDS}

    for ctx, keywords in CONTEXT_KEYWORDS.items():
        for kw in keywords:
            if kw in message_lower:
                scores[ctx] += 1

    # Si hay empate o no hay matches claros → general
    max_score = max(scores.values())
    if max_score == 0:
        return "general"

    # Devolver el contexto con mayor score
    return max(scores, key=lambda k: scores[k])


def get_context_memory(user_id: int, context: str, memory_module) -> dict:
    """
    Devuelve solo las categorías de memoria relevantes para el contexto.
    """
    import memory as mem
    focus = CONTEXT_MEMORY_FOCUS.get(context)

    if focus is None:
        # Contexto general — cargar todo
        return memory_module.get_user(user_id)

    user = memory_module.get_user(user_id)
    # Devolver solo las categorías relevantes
    return {cat: user.get(cat, {} if cat not in ("proyectos", "relaciones", "hechos") else [])
            for cat in focus}


def build_context_prompt(user_id: int, context: str, memory_module) -> str:
    """
    Construye un bloque de contexto enfocado en el área de la conversación.
    Más eficiente que cargar toda la memoria siempre.
    """
    ctx_data = get_context_memory(user_id, context, memory_module)

    if not ctx_data:
        return ""

    context_labels = {
        "calendario":  "📅 Contexto: AGENDA Y CALENDARIO",
        "correo":      "📧 Contexto: CORREO Y COMUNICACIÓN",
        "documentos":  "📁 Contexto: DOCUMENTOS Y ARCHIVOS",
        "trabajo":     "💼 Contexto: TRABAJO Y PROYECTOS",
        "metas":       "🎯 Contexto: METAS Y PRIORIDADES",
        "personal":    "👤 Contexto: PERSONAL",
        "general":     "🧠 Contexto: GENERAL",
    }

    label = context_labels.get(context, "Contexto detectado")
    lines = [f"\n\n{label}"]

    for category, data in ctx_data.items():
        if not data:
            continue
        if isinstance(data, dict):
            items = [f"{k}: {v}" for k, v in data.items() if v and k != "workspace_doc_id"]
            if items:
                lines.append(f"[{category}] " + " | ".join(items))
        elif isinstance(data, list):
            for item in data[:5]:
                if isinstance(item, dict):
                    name = item.get("nombre", item.get("name", str(item)))
                    lines.append(f"[{category}] {name}")
                elif isinstance(item, str):
                    lines.append(f"[{category}] {item}")

    return "\n".join(lines)


def get_context_hint(context: str) -> str:
    """
    Devuelve una instrucción adicional al sistema según el contexto.
    Orienta al modelo sobre qué tipo de respuesta dar.
    """
    hints = {
        "calendario": (
            "El usuario está hablando de su agenda. "
            "Sé proactivo: si menciona una fecha, ofrece crear el evento. "
            "Usa las relaciones clave para sugerir a quién invitar."
        ),
        "correo": (
            "El usuario está hablando de correos. "
            "Si menciona a alguien de sus relaciones, ya sabes quiénes son. "
            "Para correos urgentes o de clientes importantes, prioriza."
        ),
        "documentos": (
            "El usuario quiere trabajar con documentos. "
            "Relaciona con sus proyectos activos cuando sea relevante."
        ),
        "trabajo": (
            "El usuario está en modo trabajo. "
            "Ten en mente sus proyectos activos y la meta de la semana. "
            "Respuestas enfocadas, sin rodeos."
        ),
        "metas": (
            "El usuario está hablando de sus objetivos. "
            "Conecta la conversación con sus metas actuales. "
            "Sé un aliado estratégico, no solo un ejecutor."
        ),
        "personal": (
            "El usuario está en modo personal. "
            "Adapta el tono según sus preferencias. "
            "No mezcles con trabajo a menos que el usuario lo haga."
        ),
        "general": "",
    }
    return hints.get(context, "")
