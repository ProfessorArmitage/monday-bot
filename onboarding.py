"""
onboarding.py — Entrevista inicial para conocer al usuario.

Flujo conversacional en pasos. Cada paso hace una pregunta,
procesa la respuesta con Groq para extraer datos estructurados,
y los guarda en la categoría correcta de memoria vertical.

Pasos:
  1. nombre y ubicación
  2. trabajo / rol
  3. proyectos activos
  4. personas clave
  5. metas actuales
  6. ritmo preferido (horario de briefing, días libres)
  7. preferencias de tono
  8. hooks — qué eventos quiere que el bot monitoree
  (9. conectar Google — opcional, se sugiere al final)
"""

import json
import logging
import memory
import tz_utils

logger = logging.getLogger(__name__)

# ── Definición de pasos ───────────────────────────────────────

STEPS = [
    {
        "id": "nombre",
        "categoria": "identidad",
        "pregunta": (
            "¡Hola! Soy tu asistente personal. Antes de empezar, quiero conocerte un poco "
            "para poder ayudarte mejor.\n\n"
            "¿Cómo te llamas y desde qué ciudad me escribes? 😊"
        ),
        "extractor": """
Extrae del texto: nombre de la persona y ciudad/país.
Responde SOLO con JSON, sin texto extra:
{"nombre": "...", "ubicacion": "...", "idioma": "español"}
Si no menciona ciudad, usa null.
""",
    },
    {
        "id": "trabajo",
        "categoria": "trabajo",
        "pregunta": (
            "¿A qué te dedicas? Cuéntame un poco sobre tu trabajo o proyecto principal — "
            "empresa, rol, en qué estás enfocado ahorita."
        ),
        "extractor": """
Extrae: empresa, rol/cargo, área o equipo, descripción breve del trabajo.
Responde SOLO con JSON:
{"empresa": "...", "rol": "...", "equipo": "...", "descripcion": "..."}
Usa null para lo que no se mencione.
""",
    },
    {
        "id": "proyectos",
        "categoria": "proyectos",
        "pregunta": (
            "¿Cuáles son los 2 o 3 proyectos o prioridades más importantes en los que "
            "estás trabajando ahora mismo?"
        ),
        "extractor": """
Extrae una lista de proyectos o prioridades activas.
Responde SOLO con JSON (array):
[{"nombre": "...", "descripcion": "...", "estado": "activo"}]
""",
    },
    {
        "id": "relaciones",
        "categoria": "relaciones",
        "pregunta": (
            "¿Quiénes son las personas más importantes en tu día a día? "
            "Por ejemplo: tu jefe, clientes clave, equipo, familia — "
            "las personas con quienes más interactúas o que más importan para tu trabajo."
        ),
        "extractor": """
Extrae personas clave mencionadas con su relación o rol.
Responde SOLO con JSON (array):
[{"nombre": "...", "relacion": "jefe|cliente|colega|familia|otro", "notas": "..."}]
""",
    },
    {
        "id": "metas",
        "categoria": "metas",
        "pregunta": (
            "¿Cuál es tu meta más importante esta semana? "
            "Y si tienes claro algo más grande que quieras lograr este mes o este año, "
            "cuéntame también."
        ),
        "extractor": """
Extrae metas por horizonte de tiempo.
Responde SOLO con JSON:
{"semana": "...", "mes": "...", "anio": "..."}
Usa null para lo que no se mencione.
""",
    },
    {
        "id": "ritmo",
        "categoria": "ritmo",
        "pregunta": (
            "Ayúdame a entender tu ritmo. ¿A qué hora sueles empezar tu día de trabajo? "
            "¿Tienes días de descanso fijos? ¿A qué hora prefieres recibir tu resumen diario?"
        ),
        "extractor": """
Extrae información sobre el ritmo y horarios del usuario.
Responde SOLO con JSON:
{
  "inicio_dia": "HH:MM",
  "fin_dia": "HH:MM",
  "briefing_hora": "HH:MM",
  "dias_libres": ["sábado", "domingo"],
  "zona_horaria": "IANA_timezone_string"
}
Para zona_horaria, usa el nombre IANA correcto según la ciudad del usuario:
- México DF / CDMX / Guadalajara → America/Mexico_City
- Monterrey → America/Monterrey
- Tijuana / Mexicali → America/Tijuana
- Bogotá / Medellín → America/Bogota
- Lima → America/Lima
- Santiago → America/Santiago
- Buenos Aires → America/Argentina/Buenos_Aires
- Madrid / Barcelona → Europe/Madrid
- Nueva York / Miami → America/New_York
- Los Ángeles → America/Los_Angeles
Si no mencionó ciudad, usa null (NO uses America/Mexico_City como default).
Usa null para cualquier campo no mencionado.
""",
    },
    {
        "id": "preferencias",
        "categoria": "preferencias",
        "pregunta": (
            "Casi terminamos. ¿Cómo prefieres que me comunique contigo? "
            "¿Respuestas cortas y directas, o más detalladas? "
            "¿Formal o informal? ¿Hay algo más que deba saber sobre cómo ayudarte mejor?"
        ),
        "extractor": """
Extrae preferencias de comunicación.
Responde SOLO con JSON:
{
  "tono": "formal|informal|casual",
  "formato": "conciso|detallado",
  "notas": "..."
}
""",
    },
    {
        "id": "hooks",
        "categoria": "preferencias",
        "pregunta": (
            "¿Qué eventos o situaciones quieres que monitoree para avisarte "
            "automáticamente? Por ejemplo:\n\n"
            "• Correos de personas específicas\n"
            "• Reuniones próximas en tu calendario\n"
            "• Palabras clave en correos (urgente, factura, contrato...)\n\n"
            "Dime qué es importante que no se te escape."
        ),
        "extractor": """
Extrae una lista de hooks/alertas que el usuario quiere monitorear.
Responde SOLO con JSON (array):
[
  {"tipo": "correo_remitente|correo_keyword|evento_proximo|otro",
   "valor": "...",
   "descripcion": "..."}
]
""",
    },
    {
        "id": "identidad_asistente",
        "categoria": "_bot_identity",   # categoría especial — no es memoria del usuario
        "pregunta": (
            "Una última cosa — quiero saber cómo prefieres que sea yo contigo.\n\n"
            "Por defecto me llamo Luma. ¿Quieres cambiar mi nombre? "
            "¿Cómo prefieres que te trate — formal, casual o muy directo?\n\n"
            "Y si quieres, dime en una frase cómo quieres que sea nuestra relación. "
            "Por ejemplo: 'trátame como socio de trabajo' o 'sé mi segundo cerebro'.\n\n"
            "Si te parece bien todo como está, solo di 'así está bien' 😊"
        ),
        "extractor": """
Extrae la personalización del asistente que quiere el usuario.
Responde SOLO con JSON:
{
  "nombre": "nombre que quiere darle al asistente, o null si no quiere cambiarlo",
  "tono": "formal|casual|directo o null si no especificó",
  "frase": "la frase de trato en sus propias palabras, o null si no especificó",
  "activa": true
}
Si el usuario dijo algo como "así está bien" o "no cambies nada", devuelve:
{"nombre": null, "tono": null, "frase": null, "activa": false}
""",
    },
]


def get_current_step(user_id: int) -> dict | None:
    """Devuelve el paso actual del onboarding, o None si terminó."""
    state = memory.get_onboarding_state(user_id)
    step_index = state.get("step", 0)
    if step_index >= len(STEPS):
        return None
    return {**STEPS[step_index], "index": step_index, "total": len(STEPS)}


def get_first_question(user_id: int) -> str:
    """Devuelve la primera pregunta del onboarding."""
    memory.set_onboarding_state(user_id, {"step": 0})
    return STEPS[0]["pregunta"]


async def process_answer(user_id: int, answer: str, call_groq_fn) -> str:
    """
    Procesa la respuesta del usuario al paso actual:
    1. Extrae datos estructurados con Groq
    2. Los guarda en la categoría de memoria correcta
    3. Avanza al siguiente paso o termina el onboarding

    Devuelve la siguiente pregunta o el mensaje de bienvenida final.
    """
    state = memory.get_onboarding_state(user_id)
    step_index = state.get("step", 0)

    if step_index >= len(STEPS):
        return None  # ya terminó

    step = STEPS[step_index]

    # Extraer datos estructurados con Groq
    try:
        extraction_prompt = (
            f"El usuario respondió lo siguiente a la pregunta '{step['pregunta']}':\n\n"
            f"\"{answer}\"\n\n"
            f"{step['extractor']}\n"
            "Responde SOLO con el JSON, sin texto adicional, sin backticks."
        )
        raw = await call_groq_fn(
            system_prompt="Eres un extractor de información. Responde SOLO con JSON válido.",
            history=[],
            user_text=extraction_prompt
        )
        # Limpiar y parsear JSON
        raw = raw.strip().strip("```json").strip("```").strip()
        extracted = json.loads(raw)

        # Guardar en la categoría correcta
        categoria = step["categoria"]
        if step["id"] == "identidad_asistente":
            # Personalización del asistente — va a bot_identity, no a memoria personal
            clean = {k: v for k, v in extracted.items() if v is not None}
            if clean.get("activa", True):
                memory.update_bot_identity(user_id, **{k: v for k, v in clean.items() if k != "activa"})
        elif step["id"] in ("proyectos", "relaciones"):
            # Son listas — agregar cada elemento
            if isinstance(extracted, list):
                for item in extracted:
                    memory.add_to_category(user_id, categoria, item)
            else:
                memory.add_to_category(user_id, categoria, extracted)
        elif step["id"] == "hooks":
            # Guardar hooks en preferencias
            current = memory.get_category(user_id, "preferencias")
            current["hooks"] = extracted
            memory.set_category(user_id, "preferencias", current)
        else:
            # Son dicts — merge con lo existente
            clean = {k: v for k, v in extracted.items() if v is not None}
            # Si es ritmo y no tiene zona_horaria, inferir de la ubicación
            if step["id"] == "ritmo" and "zona_horaria" not in clean:
                ubicacion = memory.get_category(user_id, "identidad").get("ubicacion", "")
                inferred = tz_utils.infer_tz_from_city(ubicacion) if ubicacion else None
                if inferred:
                    clean["zona_horaria"] = inferred
            memory.update_category(user_id, categoria, clean)

    except Exception as e:
        logger.warning(f"Error extrayendo datos del paso {step['id']}: {e}")
        # Guardar respuesta raw como hecho si falla el parsing
        memory.add_fact(user_id, f"{step['id']}: {answer[:200]}")

    # Avanzar al siguiente paso
    next_index = step_index + 1
    memory.set_onboarding_state(user_id, {"step": next_index})

    if next_index >= len(STEPS):
        # Onboarding completo
        memory.complete_onboarding(user_id)
        return _build_completion_message(user_id)

    # Devolver siguiente pregunta con progreso
    next_step = STEPS[next_index]
    progress = f"({next_index + 1}/{len(STEPS)})"
    return f"{progress} {next_step['pregunta']}"


def _build_completion_message(user_id: int) -> str:
    """Mensaje final de bienvenida tras completar el onboarding."""
    import identity as identity_module
    user = memory.get_user(user_id)
    nombre_usuario = user.get("identidad", {}).get("nombre", "")
    nombre_str = f", {nombre_usuario}" if nombre_usuario else ""
    ritmo = user.get("ritmo", {})
    briefing = ritmo.get("briefing_hora", "7:00")

    # Usar el nombre del asistente personalizado
    bot_identity = memory.get_bot_identity(user_id)
    bot_nombre = identity_module.get_identity_for_user(bot_identity)["nombre"]

    return (
        f"¡Listo{nombre_str}! Ya te conozco mucho mejor 🎉\n\n"
        f"Soy {bot_nombre} y a partir de ahora seré tu asistente personal.\n\n"
        f"Configuré:\n"
        f"📋 Tu memoria organizada en categorías\n"
        f"⏰ Briefing diario a las {briefing}\n"
        f"🔔 Monitoreo de tus alertas\n\n"
        f"El siguiente paso es conectar tu Google:\n"
        f"👉 /conectar_google\n\n"
        f"O simplemente escríbeme lo que necesitas. ¡Arrancamos! 💪"
    )



def is_in_onboarding(user_id: int) -> bool:
    """True si el usuario está actualmente en proceso de onboarding."""
    if not memory.is_new_user(user_id):
        return False
    state = memory.get_onboarding_state(user_id)
    return "step" in state
