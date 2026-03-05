"""
skills.py — Motor de skills personalizadas y evolutivas.

Cada skill tiene dos capas:
  content_base     → template del catálogo (estático, de provisioning.py)
  content_personal → versión personalizada generada con la memoria real del usuario
                     Se crea al activar y evoluciona cuando el usuario cambia.

Triggers:
  manual     → se inyecta en todo handle_message
  trabajo    → solo cuando ctx == "trabajo"
  calendario → solo cuando ctx == "calendario"
  correo     → solo cuando ctx == "correo"
  metas      → solo cuando ctx == "metas"
  always     → siempre, sin importar el contexto
  morning    → solo en briefing matutino (scheduler)
  heartbeat  → solo en heartbeat (scheduler)
  custom     → skills creadas por el usuario, trigger "manual"
"""

import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cuántos días antes de que una skill se considere "vieja" y sugiera evolución
EVOLUTION_DAYS_THRESHOLD = 30

# Contextos que activan cada tipo de trigger
CONTEXT_TRIGGERS = {
    "trabajo":    ["manual", "trabajo", "always", "custom"],
    "correo":     ["manual", "correo", "always", "custom"],
    "calendario": ["manual", "calendario", "always", "custom"],
    "documentos": ["manual", "documentos", "always", "custom"],
    "metas":      ["manual", "metas", "always", "custom"],
    "personal":   ["always", "custom"],
    "general":    ["manual", "always", "custom"],
}


# ── RENDERIZADO PERSONALIZADO ─────────────────────────────────

def render_skill_content(content_base: str, user_data: dict) -> str:
    """
    Toma el template de una skill y lo enriquece con datos reales del usuario.
    Reemplaza placeholders {{campo}} con datos de memoria si existen.
    Devuelve el template original si no hay datos suficientes para personalizar.
    """
    identidad   = user_data.get("identidad", {})
    trabajo     = user_data.get("trabajo", {})
    metas       = user_data.get("metas", {})
    preferencias = user_data.get("preferencias", {})
    relaciones  = user_data.get("relaciones", [])
    proyectos   = user_data.get("proyectos", [])
    ritmo       = user_data.get("ritmo", {})

    replacements = {
        "{{nombre}}":       identidad.get("nombre", ""),
        "{{empresa}}":      trabajo.get("empresa", ""),
        "{{rol}}":          trabajo.get("rol", ""),
        "{{equipo}}":       trabajo.get("equipo", ""),
        "{{meta_semana}}":  metas.get("semana", ""),
        "{{meta_mes}}":     metas.get("mes", ""),
        "{{tono}}":         preferencias.get("tono", "natural"),
        "{{formato}}":      preferencias.get("formato", "claro y directo"),
        "{{briefing_hora}}": ritmo.get("briefing_hora", "7:00"),
        "{{zona_horaria}}": ritmo.get("zona_horaria", "America/Mexico_City"),
        "{{proyectos_activos}}": ", ".join(
            p.get("nombre", "") for p in proyectos
            if isinstance(p, dict) and p.get("estado") != "completado"
        )[:200],
        "{{contactos_clave}}": ", ".join(
            r.get("nombre", "") for r in relaciones[:5]
            if isinstance(r, dict)
        ),
    }

    result = content_base
    for placeholder, value in replacements.items():
        if value:
            result = result.replace(placeholder, value)

    return result


async def generate_personal_content(
    skill_template: dict,
    user_data: dict,
    motivo: str,
    call_groq_fn,
) -> str:
    """
    Usa Groq para generar una versión personalizada del contenido de la skill.
    Más inteligente que render_skill_content — puede inferir instrucciones
    a partir del contexto del usuario aunque no haya placeholders exactos.
    """
    # Construir resumen de contexto del usuario
    identidad   = user_data.get("identidad", {})
    trabajo     = user_data.get("trabajo", {})
    metas       = user_data.get("metas", {})
    preferencias = user_data.get("preferencias", {})
    proyectos   = user_data.get("proyectos", [])
    relaciones  = user_data.get("relaciones", [])
    ritmo       = user_data.get("ritmo", {})
    hechos      = user_data.get("hechos", [])

    activos = [p.get("nombre", "") for p in proyectos
               if isinstance(p, dict) and p.get("estado") != "completado"]
    contactos = [r.get("nombre", "") for r in relaciones[:5] if isinstance(r, dict)]

    context_summary = f"""
Usuario: {identidad.get('nombre', 'sin nombre')}
Trabajo: {trabajo.get('rol', '')} en {trabajo.get('empresa', '')}
Proyectos activos: {', '.join(activos) or 'ninguno'}
Meta de la semana: {metas.get('semana', 'sin definir')}
Tono preferido: {preferencias.get('tono', 'no especificado')}
Formato preferido: {preferencias.get('formato', 'no especificado')}
Personas clave: {', '.join(contactos) or 'ninguna'}
Briefing: {ritmo.get('briefing_hora', '7:00')}
Hechos recientes: {'; '.join(hechos[-5:]) if hechos else 'ninguno'}
"""

    prompt = f"""Tienes que personalizar una skill de un asistente personal.

SKILL A PERSONALIZAR:
Nombre: {skill_template.get('name', '')}
Descripción: {skill_template.get('description', '')}
Contenido base (instrucciones genéricas):
{skill_template.get('content', '')}

CONTEXTO DEL USUARIO:
{context_summary}

MOTIVO DE ESTA PERSONALIZACIÓN: {motivo}

TAREA:
Reescribe las instrucciones de la skill para que sean específicas a este usuario.
Menciona su empresa, proyectos, contactos y preferencias donde sea relevante.
No pierdas las instrucciones base — enriquécelas con el contexto real del usuario.
Mantén el mismo formato y longitud aproximada que el contenido base.
Responde SOLO con el nuevo contenido de la skill (sin título, sin explicación)."""

    try:
        result = await call_groq_fn(prompt, [], "")
        return result.strip() if result else skill_template.get("content", "")
    except Exception as e:
        logger.warning(f"Error generando content_personal para skill: {e}")
        # Fallback: render con placeholders
        return render_skill_content(skill_template.get("content", ""), user_data)


# ── INYECCIÓN EN SYSTEM PROMPT ────────────────────────────────

def get_active_skills_for_context(active_skills: list, ctx: str) -> list:
    """
    Filtra las skills activas según el contexto de la conversación.
    Solo devuelve las skills cuyo trigger es relevante para el contexto actual.
    """
    valid_triggers = CONTEXT_TRIGGERS.get(ctx, CONTEXT_TRIGGERS["general"])
    return [
        s for s in active_skills
        if s.get("trigger", "manual") in valid_triggers
    ]


def build_skills_prompt_block(active_skills: list, ctx: str) -> str:
    """
    Construye el bloque de skills que se inyecta al final del system prompt.
    Solo incluye skills relevantes para el contexto actual.
    Usa content_personal si existe, si no usa content_base.
    """
    relevant = get_active_skills_for_context(active_skills, ctx)
    if not relevant:
        return ""

    lines = ["\n\n=== SKILLS ACTIVAS PARA ESTA CONVERSACIÓN ==="]
    for skill in relevant:
        content = skill.get("content_personal") or skill.get("content_base") or skill.get("content", "")
        if content:
            emoji = skill.get("emoji", "🛠")
            lines.append(f"\n{emoji} {skill.get('name', skill.get('id', 'Skill'))}:")
            lines.append(content)
    lines.append("\n==============================================")
    return "\n".join(lines)


def check_skills_needing_evolution(active_skills: list) -> list:
    """
    Devuelve las skills que llevan más de EVOLUTION_DAYS_THRESHOLD días
    sin evolucionar. Para sugerir al usuario que las actualice.
    """
    threshold = datetime.now() - timedelta(days=EVOLUTION_DAYS_THRESHOLD)
    stale = []
    for skill in active_skills:
        last = skill.get("last_evolved")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if last_dt < threshold:
                    stale.append(skill)
            except Exception:
                pass
        else:
            # Nunca evolucionó — es candidata
            stale.append(skill)
    return stale


def facts_affect_skill(facts: list[str], skill: dict) -> bool:
    """
    Heurística rápida: ¿los nuevos hechos aprendidos son relevantes
    para esta skill? Si sí, triggerear evolución automática.
    """
    skill_keywords = {
        "formal_email":   ["empresa", "trabajo", "cliente", "equipo", "correo", "email"],
        "meeting_notes":  ["reunión", "meeting", "equipo", "proyecto"],
        "task_manager":   ["tarea", "proyecto", "deadline", "entrega", "pendiente"],
        "daily_brief":    ["rutina", "horario", "briefing", "mañana", "día"],
        "urgent_filter":  ["urgente", "importante", "cliente", "jefe", "prioridad"],
        "weekly_goals":   ["meta", "objetivo", "semana", "mes", "goal"],
    }
    skill_id = skill.get("id", "")
    keywords = skill_keywords.get(skill_id, [])
    if not keywords:
        return True  # skills custom siempre se consideran afectadas

    facts_text = " ".join(facts).lower()
    return any(kw in facts_text for kw in keywords)


# ── EVOLUCIÓN ─────────────────────────────────────────────────

async def evolve_skill(
    user_id: int,
    skill_id: str,
    motivo: str,
    memory_module,
    call_groq_fn,
) -> dict | None:
    """
    Regenera el content_personal de una skill con la memoria más actual del usuario.
    Registra el cambio en evolution_log.
    Devuelve la skill actualizada o None si no se encontró.
    """
    import provisioning

    active_skills = memory_module.get_skills(user_id)
    skill = next((s for s in active_skills if s.get("id") == skill_id), None)

    if not skill:
        return None

    user_data = memory_module.get_user(user_id)

    # Buscar template base en provisioning
    template = provisioning.find_skill_by_name(skill_id) or provisioning.find_skill_by_name(skill.get("name", ""))
    if not template:
        template = skill  # usar la skill misma como template si es custom

    new_content = await generate_personal_content(template, user_data, motivo, call_groq_fn)

    # Actualizar la skill en memoria
    now_str = datetime.now().isoformat()
    skill["content_personal"] = new_content
    skill["last_evolved"] = now_str
    skill["evolution_count"] = skill.get("evolution_count", 0) + 1

    log = skill.get("evolution_log", [])
    log.append({"date": now_str, "motivo": motivo})
    skill["evolution_log"] = log[-10:]  # guardar solo los últimos 10

    # Guardar de vuelta
    all_skills = [s if s.get("id") != skill_id else skill for s in active_skills]
    memory_module.save_skills(user_id, all_skills)

    logger.info(f"Skill '{skill_id}' evolucionada para usuario {user_id}: {motivo}")
    return skill


async def auto_evolve_from_facts(
    user_id: int,
    new_facts: list[str],
    memory_module,
    call_groq_fn,
) -> list[str]:
    """
    Evalúa si los nuevos hechos aprendidos [FACT] deben triggerear
    evolución automática en alguna skill activa.
    Devuelve lista de skill IDs que fueron evolucionadas.
    """
    evolved = []
    active_skills = memory_module.get_skills(user_id)

    for skill in active_skills:
        if facts_affect_skill(new_facts, skill):
            result = await evolve_skill(
                user_id,
                skill["id"],
                f"Nuevos datos aprendidos: {'; '.join(new_facts[:3])}",
                memory_module,
                call_groq_fn,
            )
            if result:
                evolved.append(skill["id"])

    return evolved


# ── ACTIVACIÓN CON PERSONALIZACIÓN INMEDIATA ─────────────────

async def activate_skill_personalized(
    user_id: int,
    skill_template: dict,
    memory_module,
    call_groq_fn,
) -> dict:
    """
    Activa una skill y genera inmediatamente su versión personalizada.
    Si el usuario no tiene suficiente memoria, usa el template base.
    """
    user_data = memory_module.get_user(user_id)
    has_memory = bool(
        user_data.get("identidad") or
        user_data.get("trabajo") or
        user_data.get("proyectos")
    )

    now_str = datetime.now().isoformat()
    skill_entry = {
        **skill_template,
        "content_base": skill_template.get("content", ""),
        "content_personal": None,
        "active": True,
        "created_at": now_str,
        "last_evolved": now_str,
        "evolution_count": 0,
        "evolution_log": [],
    }

    if has_memory:
        personal = await generate_personal_content(
            skill_template,
            user_data,
            "activación inicial",
            call_groq_fn,
        )
        skill_entry["content_personal"] = personal

    # Guardar — reemplazar si ya existía, agregar si no
    existing = memory_module.get_skills(user_id)
    existing = [s for s in existing if s.get("id") != skill_template["id"]]
    existing.append(skill_entry)
    memory_module.save_skills(user_id, existing)

    return skill_entry


# ── CREACIÓN DE SKILLS CUSTOM ─────────────────────────────────

async def create_custom_skill(
    user_id: int,
    description: str,
    memory_module,
    call_groq_fn,
) -> dict | None:
    """
    El usuario describe en lenguaje natural qué quiere que haga la skill.
    Groq genera el contenido personalizado de la skill.
    """
    user_data = memory_module.get_user(user_id)
    identidad = user_data.get("identidad", {})
    nombre = identidad.get("nombre", "el usuario")

    prompt = f"""Crea una skill personalizada para un asistente personal.

El usuario ({nombre}) quiere que su asistente tenga esta capacidad:
"{description}"

Contexto del usuario:
- Trabajo: {user_data.get('trabajo', {}).get('rol', '')} en {user_data.get('trabajo', {}).get('empresa', '')}
- Tono preferido: {user_data.get('preferencias', {}).get('tono', 'natural')}
- Proyectos: {', '.join(p.get('nombre','') for p in user_data.get('proyectos',[])[:3] if isinstance(p,dict))}

Genera la skill en formato JSON:
{{
  "name": "nombre corto de la skill (máx 4 palabras)",
  "description": "qué hace esta skill (1 oración)",
  "content": "instrucciones detalladas para el asistente sobre cómo comportarse con esta skill activa (2-4 oraciones específicas)",
  "emoji": "un emoji representativo",
  "trigger": "manual"
}}

Responde SOLO con el JSON, sin backticks."""

    try:
        result = await call_groq_fn(prompt, [], "")
        clean = result.strip().replace("```json", "").replace("```", "").strip()
        skill_data = json.loads(clean)

        import hashlib
        skill_id = "custom_" + hashlib.md5(description.encode()).hexdigest()[:8]

        now_str = datetime.now().isoformat()
        skill_entry = {
            "id": skill_id,
            "name": skill_data.get("name", "Skill personalizada"),
            "description": skill_data.get("description", description),
            "content_base": skill_data.get("content", ""),
            "content_personal": skill_data.get("content", ""),
            "emoji": skill_data.get("emoji", "⚡"),
            "trigger": "custom",
            "active": True,
            "created_at": now_str,
            "last_evolved": now_str,
            "evolution_count": 0,
            "evolution_log": [{"date": now_str, "motivo": "creación por usuario"}],
            "version_added": "custom",
        }

        existing = memory_module.get_skills(user_id)
        existing.append(skill_entry)
        memory_module.save_skills(user_id, existing)
        return skill_entry

    except Exception as e:
        logger.error(f"Error creando skill custom: {e}")
        return None


# ── SUGERENCIA DE NUEVAS SKILLS ───────────────────────────────

def suggest_skills_for_user(user_data: dict, active_skill_ids: list) -> list[str]:
    """
    Analiza la memoria del usuario y sugiere skills que podrían serle útiles
    pero que aún no tiene activas.
    Devuelve lista de IDs de skills sugeridas.
    """
    suggestions = []
    trabajo = user_data.get("trabajo", {})
    proyectos = user_data.get("proyectos", [])
    relaciones = user_data.get("relaciones", [])
    metas = user_data.get("metas", {})

    # Si tiene equipo o empresa → correo formal útil
    if (trabajo.get("empresa") or trabajo.get("equipo")) and "formal_email" not in active_skill_ids:
        suggestions.append("formal_email")

    # Si tiene proyectos activos → gestor de tareas útil
    if proyectos and "task_manager" not in active_skill_ids:
        suggestions.append("task_manager")

    # Si tiene relaciones → notas de reunión útiles
    if relaciones and "meeting_notes" not in active_skill_ids:
        suggestions.append("meeting_notes")

    # Si tiene metas definidas → seguimiento semanal útil
    if metas.get("semana") and "weekly_goals" not in active_skill_ids:
        suggestions.append("weekly_goals")

    return suggestions[:3]  # máximo 3 sugerencias a la vez
