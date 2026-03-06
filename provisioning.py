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
MANIFEST_VERSION = "1.3.0"

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
    "1.1.0": {
        "titulo": "Identidad propia — conoce a Luma",
        "cambios": [
            "Tu asistente ahora tiene nombre y personalidad propia: Luma",
            "Nuevo comando /mi_asistente para personalizar nombre, tono y trato",
            "Los saludos son variados y personalizados — ya no son genéricos",
            "El onboarding ahora incluye un paso para personalizar al asistente",
        ],
        "accion_requerida": "Prueba /mi_asistente para personalizar cómo me llamo y cómo te trato",
    },
    "1.2.0": {
        "titulo": "Skills personalizadas y evolutivas",
        "cambios": [
            "Las skills ahora se personalizan con tu contexto real al activarlas",
            "Las skills evolucionan automáticamente cuando aprendes algo nuevo",
            "Nuevo comando /evolucion para actualizar skills manualmente",
            "Nuevo comando /nueva_skill para crear skills desde cero",
            "Nuevo comando /mis_skills para ver tus skills activas y su estado",
        ],
        "accion_requerida": "Prueba /mis_skills para ver tus skills actuales y /nueva_skill para crear una propia",
    },
    "1.2.1": {
        "titulo": "Timezone por usuario — corrección de horarios",
        "cambios": [
            "Los eventos del calendario ahora se crean en tu timezone real",
            "Nuevo comando /mi_zona para ver y corregir tu zona horaria",
            "Auto-detección de timezone desde tu Google Calendar si no está configurada",
        ],
        "accion_requerida": "Si tus eventos aparecen con hora incorrecta, usa /mi_zona para corregirla",
    },
    "1.3.0": {
        "titulo": "Skills de dominio — paquetes especializados por industria",
        "cambios": [
            "6 paquetes de skills: Legal, Influencer, Corporativo, Ventas, Salud, Educación",
            "Detección automática de dominio durante el onboarding",
            "Nuevo comando /mi_dominio para ver y cambiar tu paquete activo",
            "Los usuarios existentes reciben sugerencia personalizada basada en su perfil",
        ],
        "accion_requerida": "domain_suggestion",  # activa flujo de sugerencia
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
SYSTEM_PROMPT = """Tienes acceso a Google Workspace y puedes operar en nombre del usuario.

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

Parámetros exactos por acción (úsalos siempre con estos nombres):
- calendar.create_event: title (str), start (ISO8601 ej: "2026-03-15T10:00:00"), end (ISO8601, opcional), description (str, opcional)
- calendar.list_events: days (int, default 7)
- calendar.delete_event: event_id (str)
- gmail.send_email: to (str), subject (str), body (str)
- gmail.list_emails: max_results (int, default 5)
- gmail.get_email: email_id (str)
- docs.create: title (str), content (str)
- docs.get_content: doc_id (str)
- docs.append_text: doc_id (str), text (str)
- sheets.create: title (str)
- sheets.read: sheet_id (str)
- sheets.append: sheet_id (str), values (list)
- drive.list_files: max_results (int)
- drive.search: query (str)

Ejemplos de [ACTION]:
[ACTION: {"service": "calendar", "action": "list_events", "params": {"days": 7}}]
[ACTION: {"service": "calendar", "action": "create_event", "params": {"title": "Reunión con equipo", "start": "2026-03-15T10:00:00", "end": "2026-03-15T11:00:00"}}]
[ACTION: {"service": "gmail", "action": "send_email", "params": {"to": "juan@gmail.com", "subject": "Hola", "body": "¿Cómo estás?"}}]
[ACTION: {"service": "docs", "action": "create", "params": {"title": "Mi documento", "content": "Contenido inicial"}}]

IMPORTANTE para fechas: usa siempre formato "YYYY-MM-DDTHH:MM:SS" para start y end.
Si el usuario dice "mañana a las 3pm", calcula la fecha ISO completa.
Hoy es {fecha_actual}. Si no conoces la fecha exacta, usa el formato correcto de todos modos.

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
            "Cuando redactes un correo para {{nombre}}, usa un tono profesional y formal. "
            "Si escribe a alguien de {{empresa}} o a {{contactos_clave}}, adapta el saludo "
            "al nivel de confianza. Incluye saludo apropiado, desarrollo claro y despedida "
            "cordial. Revisa gramática y ortografía antes de enviar. "
            "Tono base del usuario: {{tono}}."
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
            "Ayuda a {{nombre}} a organizar sus tareas. Considera siempre "
            "sus proyectos activos: {{proyectos_activos}}. "
            "Clasifica los pendientes por urgencia (Alta/Media/Baja) "
            "y relaciónalos con su meta de la semana: {{meta_semana}}. "
            "Sugiere el orden de atención y ofrece dividir tareas grandes."
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
            "En el briefing de {{nombre}} a las {{briefing_hora}}, "
            "incluye siempre: una frase motivacional breve, "
            "un recordatorio de su meta de la semana ({{meta_semana}}) "
            "y una revisión rápida de sus proyectos activos: {{proyectos_activos}}."
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

    # ── DOMINIO: LEGAL ────────────────────────────────────────
    {
        "id": "legal_drafting",
        "name": "Redacción legal",
        "description": "Redactar contratos, cláusulas y documentos legales con lenguaje preciso",
        "content": (
            "Cuando {{nombre}} necesite redactar documentos legales, usa lenguaje jurídico preciso "
            "y formal. Incluye siempre: partes involucradas, objeto, obligaciones, plazos y firma. "
            "Adapta el nivel técnico al destinatario. Empresa: {{empresa}}. Rol: {{rol}}."
        ),
        "trigger": "manual",
        "emoji": "⚖️",
        "dominio": "legal",
        "version_added": "1.3.0",
    },
    {
        "id": "legal_risk",
        "name": "Análisis de riesgo legal",
        "description": "Identificar riesgos legales en situaciones, contratos o decisiones",
        "content": (
            "Cuando {{nombre}} presente una situación o documento para análisis, "
            "identifica: riesgos legales potenciales, cláusulas problemáticas, "
            "vacíos jurídicos y recomendaciones de mitigación. "
            "Sé específico y práctico. Contexto: {{descripcion_trabajo}}."
        ),
        "trigger": "trabajo",
        "emoji": "🔍",
        "dominio": "legal",
        "version_added": "1.3.0",
    },
    {
        "id": "legal_case_tracker",
        "name": "Seguimiento de casos",
        "description": "Organizar y dar seguimiento a casos, expedientes y deadlines legales",
        "content": (
            "Ayuda a {{nombre}} a mantener orden en sus casos activos: {{proyectos_activos}}. "
            "Para cada caso, rastrea: estatus actual, próxima acción, deadline y partes involucradas. "
            "Prioriza según urgencia legal y fechas de vencimiento."
        ),
        "trigger": "trabajo",
        "emoji": "📂",
        "dominio": "legal",
        "version_added": "1.3.0",
    },
    {
        "id": "legal_client_comm",
        "name": "Comunicación con clientes legales",
        "description": "Redactar comunicados profesionales a clientes sobre temas legales",
        "content": (
            "Al redactar comunicaciones de {{nombre}} a clientes legales, "
            "usa tono profesional pero accesible — evita jerga técnica innecesaria. "
            "Explica implicaciones prácticas, no solo legales. "
            "Incluye próximos pasos claros. Contactos clave: {{contactos_clave}}."
        ),
        "trigger": "correo",
        "emoji": "📬",
        "dominio": "legal",
        "version_added": "1.3.0",
    },

    # ── DOMINIO: INFLUENCER ───────────────────────────────────
    {
        "id": "influencer_content_calendar",
        "name": "Calendario de contenido",
        "description": "Planificar y organizar contenido para redes sociales",
        "content": (
            "Ayuda a {{nombre}} a planificar su contenido. "
            "Considera su meta de la semana ({{meta_semana}}) y proyectos activos ({{proyectos_activos}}). "
            "Para cada pieza de contenido sugiere: plataforma, formato, hook de apertura, "
            "mensaje central y call to action. Adapta al tono de su marca: {{tono}}."
        ),
        "trigger": "trabajo",
        "emoji": "📅",
        "dominio": "influencer",
        "version_added": "1.3.0",
    },
    {
        "id": "influencer_brand_voice",
        "name": "Voz de marca",
        "description": "Mantener consistencia en el tono y mensaje de marca personal",
        "content": (
            "Cuando {{nombre}} cree contenido o comunicaciones, mantén siempre "
            "su voz de marca: {{tono}}. Revisa que el mensaje sea auténtico, "
            "consistente con su narrativa y alineado a su propuesta de valor. "
            "Sugiere ajustes si el tono se desvía de su identidad de marca."
        ),
        "trigger": "manual",
        "emoji": "✨",
        "dominio": "influencer",
        "version_added": "1.3.0",
    },
    {
        "id": "influencer_collab_pitch",
        "name": "Propuesta de colaboración",
        "description": "Redactar pitches y propuestas de colaboración con marcas",
        "content": (
            "Al redactar propuestas de colaboración para {{nombre}}, incluye: "
            "presentación personal breve, audiencia y alcance, propuesta de valor para la marca, "
            "formatos de colaboración sugeridos, entregables y condiciones básicas. "
            "Tono: profesional pero con personalidad. Empresa/marca: {{empresa}}."
        ),
        "trigger": "correo",
        "emoji": "🤝",
        "dominio": "influencer",
        "version_added": "1.3.0",
    },
    {
        "id": "influencer_analytics_brief",
        "name": "Brief de métricas",
        "description": "Resumen de métricas y rendimiento de contenido en el briefing",
        "content": (
            "En el briefing de {{nombre}}, incluye una sección de rendimiento: "
            "qué contenido funcionó mejor esta semana, tendencias de engagement, "
            "y una recomendación de qué tipo de contenido priorizar hoy "
            "basándote en sus metas activas: {{meta_semana}}."
        ),
        "trigger": "morning",
        "emoji": "📊",
        "dominio": "influencer",
        "version_added": "1.3.0",
    },

    # ── DOMINIO: CORPORATIVO ──────────────────────────────────
    {
        "id": "corp_exec_summary",
        "name": "Resumen ejecutivo",
        "description": "Estructurar información compleja en resúmenes ejecutivos claros",
        "content": (
            "Cuando {{nombre}} necesite un resumen ejecutivo, usa estructura: "
            "Situación actual, Problema u oportunidad, Análisis clave, "
            "Opciones evaluadas, Recomendación y Próximos pasos. "
            "Máximo 1 página. Lenguaje directo, orientado a decisión. "
            "Rol: {{rol}} en {{empresa}}."
        ),
        "trigger": "manual",
        "emoji": "📋",
        "dominio": "corporativo",
        "version_added": "1.3.0",
    },
    {
        "id": "corp_stakeholder_comm",
        "name": "Comunicación con stakeholders",
        "description": "Redactar comunicaciones estratégicas para directivos y stakeholders",
        "content": (
            "Al redactar comunicaciones de {{nombre}} para stakeholders o directivos, "
            "prioriza: claridad sobre detalle, impacto sobre proceso, "
            "y siempre incluye qué se necesita de ellos (decisión, aprobación, información). "
            "Adapta al nivel del destinatario. Contactos clave: {{contactos_clave}}."
        ),
        "trigger": "correo",
        "emoji": "🏢",
        "dominio": "corporativo",
        "version_added": "1.3.0",
    },
    {
        "id": "corp_strategic_review",
        "name": "Revisión estratégica",
        "description": "Analizar situaciones con enfoque estratégico y de negocio",
        "content": (
            "Cuando {{nombre}} presente una situación de negocio, analiza con marco estratégico: "
            "contexto y datos relevantes, factores internos y externos, "
            "opciones con pros/contras, riesgo de cada opción y recomendación. "
            "Conecta siempre con sus metas: {{meta_semana}}. Empresa: {{empresa}}."
        ),
        "trigger": "trabajo",
        "emoji": "🎯",
        "dominio": "corporativo",
        "version_added": "1.3.0",
    },
    {
        "id": "corp_board_prep",
        "name": "Preparación de juntas",
        "description": "Preparar agenda, materiales y puntos clave para juntas directivas",
        "content": (
            "Ayuda a {{nombre}} a preparar juntas efectivas. Para cada junta: "
            "define objetivo claro, agenda con tiempos, materiales necesarios, "
            "puntos de decisión requeridos y pre-work para participantes. "
            "Proyectos activos relevantes: {{proyectos_activos}}."
        ),
        "trigger": "manual",
        "emoji": "🗓️",
        "dominio": "corporativo",
        "version_added": "1.3.0",
    },

    # ── DOMINIO: VENTAS ───────────────────────────────────────
    {
        "id": "sales_prospect_follow",
        "name": "Seguimiento de prospectos",
        "description": "Mantener seguimiento efectivo del pipeline de ventas",
        "content": (
            "Ayuda a {{nombre}} a mantener su pipeline activo. "
            "Para cada prospecto, rastrea: etapa actual, último contacto, "
            "próxima acción y fecha de seguimiento. "
            "Prioriza según probabilidad de cierre y valor. "
            "Proyectos/cuentas activas: {{proyectos_activos}}."
        ),
        "trigger": "trabajo",
        "emoji": "🔭",
        "dominio": "ventas",
        "version_added": "1.3.0",
    },
    {
        "id": "sales_proposal",
        "name": "Propuesta comercial",
        "description": "Redactar propuestas comerciales persuasivas y estructuradas",
        "content": (
            "Al redactar propuestas comerciales para {{nombre}}, estructura: "
            "entendimiento del problema del cliente, solución propuesta, "
            "beneficios concretos (no características), inversión y ROI esperado, "
            "casos de éxito relevantes y llamada a la acción clara. "
            "Empresa: {{empresa}}. Tono: {{tono}}."
        ),
        "trigger": "manual",
        "emoji": "💼",
        "dominio": "ventas",
        "version_added": "1.3.0",
    },
    {
        "id": "sales_pipeline_brief",
        "name": "Revisión de pipeline",
        "description": "Resumen diario del estado del pipeline en el briefing",
        "content": (
            "En el briefing de {{nombre}}, incluye revisión de pipeline: "
            "prospectos que requieren acción hoy, deals en riesgo de enfriarse, "
            "y meta de cierre de la semana: {{meta_semana}}. "
            "Sugiere la acción de mayor impacto para el día."
        ),
        "trigger": "morning",
        "emoji": "📈",
        "dominio": "ventas",
        "version_added": "1.3.0",
    },
    {
        "id": "sales_client_comm",
        "name": "Comunicación con clientes",
        "description": "Redactar seguimientos, check-ins y comunicaciones de ventas",
        "content": (
            "Al redactar comunicaciones de ventas para {{nombre}}, "
            "usa tono consultivo — ayuda primero, vende después. "
            "Cada mensaje debe tener un objetivo claro y un siguiente paso específico. "
            "Personaliza según el historial del cliente. Contactos: {{contactos_clave}}."
        ),
        "trigger": "correo",
        "emoji": "💬",
        "dominio": "ventas",
        "version_added": "1.3.0",
    },

    # ── DOMINIO: SALUD ────────────────────────────────────────
    {
        "id": "health_patient_notes",
        "name": "Notas de consulta",
        "description": "Estructurar notas clínicas y de consulta de forma clara",
        "content": (
            "Cuando {{nombre}} registre notas de consulta, estructura: "
            "motivo de consulta, antecedentes relevantes, evaluación/hallazgos, "
            "diagnóstico o impresión, plan de tratamiento y próxima cita. "
            "Usa lenguaje clínico apropiado. Rol: {{rol}} en {{empresa}}."
        ),
        "trigger": "manual",
        "emoji": "🩺",
        "dominio": "salud",
        "version_added": "1.3.0",
    },
    {
        "id": "health_clinical_follow",
        "name": "Seguimiento clínico",
        "description": "Dar seguimiento a pacientes y tratamientos activos",
        "content": (
            "Ayuda a {{nombre}} a mantener seguimiento de sus pacientes/casos activos: "
            "{{proyectos_activos}}. Para cada caso: estatus del tratamiento, "
            "adherencia observada, alertas o cambios relevantes y próxima revisión. "
            "Prioriza casos de mayor riesgo o urgencia clínica."
        ),
        "trigger": "trabajo",
        "emoji": "📋",
        "dominio": "salud",
        "version_added": "1.3.0",
    },
    {
        "id": "health_patient_comm",
        "name": "Comunicación con pacientes",
        "description": "Redactar comunicaciones claras y empáticas para pacientes",
        "content": (
            "Al redactar comunicaciones de {{nombre}} para pacientes, "
            "usa lenguaje claro, empático y accesible — sin tecnicismos innecesarios. "
            "Explica el qué y el por qué de indicaciones. "
            "Incluye siempre: qué hacer, cuándo y a quién contactar ante dudas."
        ),
        "trigger": "correo",
        "emoji": "💙",
        "dominio": "salud",
        "version_added": "1.3.0",
    },
    {
        "id": "health_agenda_brief",
        "name": "Brief de agenda clínica",
        "description": "Resumen de la agenda del día con preparación por paciente",
        "content": (
            "En el briefing de {{nombre}}, incluye revisión de agenda clínica: "
            "citas del día con notas de preparación relevantes, "
            "seguimientos pendientes de ayer y alertas de pacientes prioritarios. "
            "Meta de la semana: {{meta_semana}}."
        ),
        "trigger": "morning",
        "emoji": "🏥",
        "dominio": "salud",
        "version_added": "1.3.0",
    },

    # ── DOMINIO: EDUCACIÓN ────────────────────────────────────
    {
        "id": "edu_lesson_prep",
        "name": "Preparación de clases",
        "description": "Planificar y estructurar clases, sesiones o talleres",
        "content": (
            "Ayuda a {{nombre}} a preparar sus clases o sesiones. "
            "Para cada sesión estructura: objetivo de aprendizaje, "
            "contenido principal, actividades o dinámicas, materiales necesarios "
            "y cómo medir que el objetivo se cumplió. "
            "Adapta al nivel de los estudiantes/coachees. Rol: {{rol}}."
        ),
        "trigger": "trabajo",
        "emoji": "📚",
        "dominio": "educacion",
        "version_added": "1.3.0",
    },
    {
        "id": "edu_student_follow",
        "name": "Seguimiento de alumnos",
        "description": "Dar seguimiento al progreso de alumnos o coachees",
        "content": (
            "Ayuda a {{nombre}} a mantener seguimiento de sus alumnos/coachees: "
            "{{proyectos_activos}}. Para cada persona: progreso observado, "
            "áreas de mejora, logros recientes y próxima intervención necesaria. "
            "Celebra avances y detecta quién necesita más atención."
        ),
        "trigger": "manual",
        "emoji": "👥",
        "dominio": "educacion",
        "version_added": "1.3.0",
    },
    {
        "id": "edu_content_creation",
        "name": "Creación de material",
        "description": "Crear material educativo, guías y recursos de aprendizaje",
        "content": (
            "Cuando {{nombre}} cree material educativo, asegura: "
            "objetivo claro de aprendizaje, estructura lógica y progresiva, "
            "ejemplos concretos y aplicables, y actividades de práctica. "
            "Adapta complejidad al nivel de la audiencia. Tono: {{tono}}."
        ),
        "trigger": "manual",
        "emoji": "✏️",
        "dominio": "educacion",
        "version_added": "1.3.0",
    },
    {
        "id": "edu_comm",
        "name": "Comunicación educativa",
        "description": "Redactar comunicaciones con alumnos, padres o instituciones",
        "content": (
            "Al redactar comunicaciones de {{nombre}} en contexto educativo, "
            "usa tono profesional y empático. Para alumnos: motivador y claro. "
            "Para padres: transparente y colaborativo. Para instituciones: formal. "
            "Incluye siempre próximos pasos concretos. Contactos: {{contactos_clave}}."
        ),
        "trigger": "correo",
        "emoji": "📩",
        "dominio": "educacion",
        "version_added": "1.3.0",
    },
]

# ── CATÁLOGO DE DOMINIOS ──────────────────────────────────────
# Cada dominio agrupa un paquete de skills relacionadas.
# Para agregar un dominio nuevo:
#   1. Agregar entrada aquí con su id, nombre, descripción y skill_ids
#   2. Agregar las skills correspondientes en SKILLS_CATALOG (con "dominio": "id")
#   3. Bump MANIFEST_VERSION MINOR + CHANGELOG + deploy
DOMAINS_CATALOG = [
    {
        "id": "legal",
        "name": "Legal",
        "emoji": "⚖️",
        "description": "Abogados, notarios, consultores legales",
        "keywords": ["abogado", "legal", "derecho", "jurídico", "notario", "litigios",
                     "contratos", "bufete", "firma legal", "compliance"],
        "skill_ids": ["legal_drafting", "legal_risk", "legal_case_tracker", "legal_client_comm"],
    },
    {
        "id": "influencer",
        "name": "Influencer / Creador",
        "emoji": "🎬",
        "description": "Creadores de contenido, influencers, personal brand",
        "keywords": ["influencer", "creador", "contenido", "redes sociales", "youtube",
                     "instagram", "tiktok", "marca personal", "community", "streaming"],
        "skill_ids": ["influencer_content_calendar", "influencer_brand_voice",
                      "influencer_collab_pitch", "influencer_analytics_brief"],
    },
    {
        "id": "corporativo",
        "name": "Corporativo",
        "emoji": "🏢",
        "description": "Ejecutivos, gerentes, líderes de área en empresas",
        "keywords": ["director", "gerente", "ejecutivo", "corporativo", "empresa",
                     "junta", "board", "estrategia", "operaciones", "c-suite", "vp"],
        "skill_ids": ["corp_exec_summary", "corp_stakeholder_comm",
                      "corp_strategic_review", "corp_board_prep"],
    },
    {
        "id": "ventas",
        "name": "Ventas",
        "emoji": "💼",
        "description": "Vendedores, account managers, equipos comerciales",
        "keywords": ["ventas", "comercial", "prospecto", "cliente", "pipeline",
                     "cierre", "cuenta", "revenue", "cuota", "deal", "crm"],
        "skill_ids": ["sales_prospect_follow", "sales_proposal",
                      "sales_pipeline_brief", "sales_client_comm"],
    },
    {
        "id": "salud",
        "name": "Salud / Wellness",
        "emoji": "🩺",
        "description": "Médicos, nutriólogos, psicólogos, entrenadores, terapeutas",
        "keywords": ["médico", "doctor", "salud", "paciente", "clínica", "nutriólogo",
                     "psicólogo", "terapeuta", "wellness", "entrenador", "consultorio"],
        "skill_ids": ["health_patient_notes", "health_clinical_follow",
                      "health_patient_comm", "health_agenda_brief"],
    },
    {
        "id": "educacion",
        "name": "Educación / Coaching",
        "emoji": "📚",
        "description": "Profesores, coaches, consultores, formadores",
        "keywords": ["profesor", "maestro", "coach", "educación", "enseñanza",
                     "alumno", "estudiante", "capacitación", "formación", "taller", "curso"],
        "skill_ids": ["edu_lesson_prep", "edu_student_follow",
                      "edu_content_creation", "edu_comm"],
    },
]

# ── HELPERS DE DOMINIO ────────────────────────────────────────

def get_domain_by_id(domain_id: str) -> dict | None:
    """Devuelve el dominio del catálogo por su id."""
    return next((d for d in DOMAINS_CATALOG if d["id"] == domain_id), None)

def get_domain_skills(domain_id: str) -> list[dict]:
    """Devuelve las skills del catálogo que pertenecen a un dominio."""
    domain = get_domain_by_id(domain_id)
    if not domain:
        return []
    ids = set(domain["skill_ids"])
    return [s for s in SKILLS_CATALOG if s.get("id") in ids]

def get_domains_menu_text() -> str:
    """Genera el texto del menú de selección de dominio para enviar al usuario."""
    lines = ["*Elige el paquete que mejor describe tu actividad:*\n"]
    for i, d in enumerate(DOMAINS_CATALOG, 1):
        lines.append(f"{i}\u20e3 {d['emoji']} *{d['name']}*")
        lines.append(f"   _{d['description']}_")
    lines.append("\n7\u20e3 \U0001f513 *General* _(sin paquete específico)_")
    lines.append("\nResponde con el número o usa /mi_dominio más adelante.")
    return "\n".join(lines)

async def infer_domain_from_memory(user_data: dict, call_groq_fn) -> str | None:
    """
    Usa Groq para inferir el dominio del usuario a partir de su memoria.
    Devuelve el id del dominio o None si no puede inferirlo con confianza.
    """
    trabajo = user_data.get("trabajo", {})
    identidad = user_data.get("identidad", {})
    proyectos = user_data.get("proyectos", [])

    context = (
        f"Rol: {trabajo.get('rol', '')}\n"
        f"Empresa: {trabajo.get('empresa', '')}\n"
        f"Descripción: {trabajo.get('descripcion', '')}\n"
        f"Proyectos: {', '.join(p.get('nombre', '') if isinstance(p, dict) else str(p) for p in proyectos[:3])}\n"
        f"Profesión: {identidad.get('profesion', '')}"
    )

    domain_ids = [d["id"] for d in DOMAINS_CATALOG]
    keywords_map = {d["id"]: d["keywords"] for d in DOMAINS_CATALOG}

    prompt = f"""Analiza este perfil profesional y determina a qué dominio pertenece.

PERFIL:
{context}

DOMINIOS DISPONIBLES: {", ".join(domain_ids)}
PALABRAS CLAVE POR DOMINIO: {keywords_map}

Responde SOLO con el id del dominio más probable, o "general" si no hay suficiente información.
No expliques nada. Solo el id. Ejemplo: legal"""

    try:
        result = await call_groq_fn(
            "Eres un clasificador de perfiles profesionales. Responde solo con el id del dominio.",
            [],
            prompt
        )
        result = result.strip().lower().strip('"').strip("'")
        if result in domain_ids:
            return result
        return None
    except Exception:
        return None


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



async def _suggest_domain_to_existing_user(user_id: int, user_data: dict, memory_module, bot):
    """
    Para usuarios existentes en reprovisión: Groq infiere dominio,
    pero también se hace matching por keywords como fallback.
    Envía mensaje con sugerencia personalizada o menú genérico.
    """
    from datetime import datetime

    trabajo = user_data.get("trabajo", {})
    text = " ".join([
        str(trabajo.get("rol", "")),
        str(trabajo.get("empresa", "")),
        str(trabajo.get("descripcion", "")),
    ]).lower()

    # Match por keywords
    best_domain = None
    best_score = 0
    for domain in DOMAINS_CATALOG:
        score = sum(1 for kw in domain["keywords"] if kw in text)
        if score > best_score:
            best_score = score
            best_domain = domain["id"]

    from datetime import datetime
    pending_state = {
        "asked_at": datetime.utcnow().isoformat(),
        "source": "reprovisioning",
    }

    if best_domain and best_score > 0:
        domain = get_domain_by_id(best_domain)
        skill_names = [s["name"] for s in get_domain_skills(best_domain)]
        msg = (
            f"\n🎯 *Novedad — Paquetes de skills por dominio*\n\n"
            f"Basándome en tu perfil, creo que el paquete "
            f"*{domain['emoji']} {domain['name']}* es para ti:\n"
            f"_{', '.join(skill_names)}_\n\n"
            f"¿Lo activo? Responde *sí*, *no* para ver otras opciones, "
            f"o *saltar* para después con /mi_dominio"
        )
        pending_state["suggested"] = best_domain
        pending_state["state"] = "awaiting_confirmation"
    else:
        msg = (
            f"\n🎯 *Novedad — Paquetes de skills por dominio*\n\n"
            f"Ahora tengo skills especializadas según tu área de trabajo.\n\n"
            + get_domains_menu_text()
        )
        pending_state["suggested"] = None
        pending_state["state"] = "awaiting_selection"

    try:
        await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
        memory_module.set_domain_pending(user_id, pending_state)
    except Exception as e:
        logger.warning(f"No se pudo enviar sugerencia de dominio a {user_id}: {e}")

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

            # Si el cambio incluye domain_suggestion y el usuario no tiene dominio
            needs_domain = any(
                CHANGELOG.get(v, {}).get("accion_requerida") == "domain_suggestion"
                for v in CHANGELOG
                if _version_lt(current_version, v)
            )
            if needs_domain and memory_module.get_user_domain(user_id) is None:
                await _suggest_domain_to_existing_user(user_id, user, memory_module, bot)

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
