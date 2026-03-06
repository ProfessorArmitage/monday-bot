"""
domain_seeds.py — Memoria pre-sembrada por dominio

Cada dominio tiene un SEED con tres capas:
  1. base_memory   → contexto general que se fusiona con la memoria vertical del usuario
  2. domain_extras → campos específicos del dominio que el admin puede configurar por usuario
  3. fact_keywords → palabras que, al aparecer en un [FACT], actualizan el seed automáticamente

CÓMO AGREGAR UN DOMINIO NUEVO (para humanos o agentes):
  1. Agregar una entrada en DOMAIN_SEEDS con su id, base_memory, domain_extras y fact_keywords
  2. Agregar el dominio en DOMAINS_CATALOG en provisioning.py con sus skill_ids
  3. Bump MANIFEST_VERSION MINOR en provisioning.py + entrada en CHANGELOG
  4. git push — la reprovisión inyecta el seed a usuarios existentes con ese dominio

CÓMO EDITAR EL SEED DE UN USUARIO (admin override):
  Desde Telegram como admin:
    /admin seed <dominio> <user_id> <campo> <valor>
    /admin seed legal 12345 numero_cedula 1234567
    /admin seed influencer 12345 handle_instagram @miusuario
    /admin seed ver 12345   → ver seed actual del usuario

NOTA DE SEGURIDAD:
  domain_extras nunca se sobreescribe con la reproducción automática de hechos.
  Solo el admin puede modificar domain_extras. Los [FACT] solo enriquecen base_memory.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── SEEDS POR DOMINIO ─────────────────────────────────────────────────────────
# base_memory: se fusiona (merge) con la memoria vertical del usuario al activar dominio
# domain_extras: campos configurables por admin, nunca tocados por auto-aprendizaje
# fact_keywords: si alguna aparece en un [FACT] nuevo, se actualiza base_memory del seed

DOMAIN_SEEDS = {
    "legal": {
        "base_memory": {
            "trabajo": {
                "sector": "legal",
                "vocabulario_clave": [
                    "expediente", "contraparte", "diligencia", "cláusula",
                    "notificación", "amparo", "apelación", "demanda",
                    "sentencia", "jurisprudencia", "poder notarial"
                ],
                "flujos_tipicos": [
                    "redacción y revisión de contratos",
                    "seguimiento de expedientes y casos",
                    "comunicación con clientes legales",
                    "preparación de audiencias",
                    "investigación jurídica"
                ],
                "herramientas_comunes": ["Word/Google Docs", "expediente digital"],
            },
            "preferencias": {
                "formato_documentos": "formal jurídico con encabezado, cuerpo y firma",
                "incluir_fundamento_legal": True,
                "estructura_contratos": ["partes", "antecedentes", "objeto",
                                          "obligaciones", "vigencia", "firma"],
            },
        },
        "domain_extras": {
            "logo_url": None,             # URL del logo del despacho/firma
            "firma_texto": None,          # Texto de firma profesional
            "numero_cedula": None,        # Cédula profesional
            "nombre_despacho": None,      # Nombre del despacho o firma
            "especialidades": [],         # ej. ["derecho corporativo", "litigios"]
            "jurisdiccion": None,         # País o estado de práctica
        },
        "fact_keywords": [
            "caso", "cliente", "expediente", "juicio", "contrato",
            "demanda", "audiencia", "cedula", "especialidad", "jurisdiccion"
        ],
    },

    "influencer": {
        "base_memory": {
            "trabajo": {
                "sector": "creación de contenido digital",
                "tipos_contenido": ["reels", "stories", "posts", "lives", "videos"],
                "metricas_clave": [
                    "engagement rate", "alcance orgánico",
                    "impresiones", "seguidores", "conversiones"
                ],
                "flujos_tipicos": [
                    "planificación de contenido semanal",
                    "negociación con marcas",
                    "análisis de métricas",
                    "respuesta a comunidad",
                    "producción de contenido"
                ],
            },
            "preferencias": {
                "tono_contenido": "auténtico, cercano y conversacional",
                "formato_publicaciones": "gancho + desarrollo + CTA",
                "incluir_hashtags": True,
            },
        },
        "domain_extras": {
            "handle_instagram": None,
            "handle_tiktok": None,
            "handle_youtube": None,
            "handle_twitter": None,
            "handle_linkedin": None,
            "nicho": None,                # ej. "fitness", "viajes", "finanzas personales"
            "publico_objetivo": None,     # descripción de la audiencia
            "media_kit_url": None,        # URL del media kit
            "agencia": None,              # Agencia o manager si aplica
            "tarifas_referencia": None,   # Nota interna sobre tarifas
        },
        "fact_keywords": [
            "seguidores", "plataforma", "nicho", "marca", "colaboración",
            "engagement", "contenido", "publicación", "audiencia", "handle"
        ],
    },

    "corporativo": {
        "base_memory": {
            "trabajo": {
                "sector": "corporativo / empresarial",
                "flujos_tipicos": [
                    "preparación de reportes ejecutivos",
                    "comunicación con directivos y stakeholders",
                    "revisión estratégica de proyectos",
                    "preparación y seguimiento de juntas",
                    "gestión de equipos"
                ],
                "herramientas_comunes": [
                    "PowerPoint/Google Slides", "Excel/Google Sheets",
                    "correo corporativo", "CRM"
                ],
            },
            "preferencias": {
                "formato_reportes": "resumen ejecutivo + análisis + recomendación",
                "longitud_comunicados": "conciso — máximo 1 página",
                "estructura_juntas": ["objetivo", "agenda", "decisiones", "siguientes pasos"],
            },
        },
        "domain_extras": {
            "logo_empresa": None,          # URL del logo corporativo
            "nombre_empresa_completo": None,
            "industria": None,             # ej. "tecnología", "manufactura", "retail"
            "numero_empleados": None,      # referencia de tamaño
            "reporta_a": None,             # título del superior directo
            "kpis_clave": [],              # métricas del rol
            "plantillas_url": None,        # URL de plantillas corporativas
        },
        "fact_keywords": [
            "empresa", "directivo", "proyecto", "presupuesto", "kpi",
            "equipo", "junta", "estrategia", "trimestre", "reporte"
        ],
    },

    "ventas": {
        "base_memory": {
            "trabajo": {
                "sector": "ventas / comercial",
                "flujos_tipicos": [
                    "prospección y calificación de leads",
                    "seguimiento de pipeline",
                    "redacción de propuestas comerciales",
                    "negociación y cierre",
                    "reporte de resultados"
                ],
                "etapas_pipeline": [
                    "prospecto identificado", "primer contacto",
                    "propuesta enviada", "negociación", "cerrado ganado", "cerrado perdido"
                ],
                "herramientas_comunes": ["CRM", "correo", "LinkedIn"],
            },
            "preferencias": {
                "tono_ventas": "consultivo — primero entender, luego proponer",
                "formato_propuesta": ["problema del cliente", "solución", "beneficios", "inversión", "CTA"],
                "seguimiento_frecuencia": "máximo 3 intentos antes de pausar",
            },
        },
        "domain_extras": {
            "nombre_empresa_vendedora": None,
            "producto_servicio_principal": None,  # qué vende
            "ticket_promedio": None,               # referencia de valor
            "ciclo_venta_dias": None,              # duración típica del ciclo
            "crm_usado": None,                     # ej. "Salesforce", "HubSpot", "Pipedrive"
            "territorio": None,                    # región o segmento asignado
            "cuota_mensual": None,                 # referencia de meta
        },
        "fact_keywords": [
            "prospecto", "cliente", "propuesta", "cierre", "pipeline",
            "deal", "cuota", "crm", "negociación", "seguimiento"
        ],
    },

    "salud": {
        "base_memory": {
            "trabajo": {
                "sector": "salud / wellness",
                "flujos_tipicos": [
                    "consultas y notas clínicas",
                    "seguimiento de pacientes",
                    "comunicación con pacientes y familias",
                    "revisión de tratamientos",
                    "coordinación con otros profesionales"
                ],
                "estructura_nota_clinica": [
                    "motivo de consulta", "antecedentes",
                    "evaluación / hallazgos", "diagnóstico",
                    "plan de tratamiento", "próxima cita"
                ],
            },
            "preferencias": {
                "tono_pacientes": "empático, claro y sin tecnicismos innecesarios",
                "incluir_proximos_pasos": True,
                "formato_notas": "SOAP (Subjetivo, Objetivo, Evaluación, Plan)",
            },
        },
        "domain_extras": {
            "nombre_consultorio": None,
            "especialidad": None,          # ej. "medicina general", "nutrición", "psicología"
            "cedula_profesional": None,
            "logo_consultorio": None,
            "sistema_expedientes": None,   # ej. "expediente propio", "nombre del software"
            "poblacion_pacientes": None,   # descripción de pacientes típicos
            "horario_consultas": None,     # referencia de horario
        },
        "fact_keywords": [
            "paciente", "diagnóstico", "tratamiento", "consulta", "especialidad",
            "cita", "expediente", "medicamento", "síntoma", "seguimiento"
        ],
    },

    "educacion": {
        "base_memory": {
            "trabajo": {
                "sector": "educación / coaching",
                "flujos_tipicos": [
                    "preparación y planeación de clases o sesiones",
                    "seguimiento de alumnos o coachees",
                    "creación de material educativo",
                    "evaluación de progreso",
                    "comunicación con alumnos, padres o instituciones"
                ],
                "estructura_clase": [
                    "objetivo de aprendizaje", "contenido principal",
                    "actividad / dinámica", "cierre y evaluación"
                ],
            },
            "preferencias": {
                "tono_alumnos": "motivador, claro y adaptado al nivel",
                "incluir_objetivo_aprendizaje": True,
                "formato_material": "objetivo + contenido + actividad + evaluación",
            },
        },
        "domain_extras": {
            "institucion": None,           # escuela, universidad, empresa donde da clases
            "nivel_educativo": None,       # ej. "universidad", "preparatoria", "adultos"
            "materia_principal": None,     # o área de coaching
            "plataforma_clases": None,     # ej. "Zoom", "Google Meet", "presencial"
            "numero_alumnos": None,        # referencia de grupo
            "lms_usado": None,             # ej. "Moodle", "Canvas", "Google Classroom"
        },
        "fact_keywords": [
            "alumno", "clase", "sesión", "materia", "programa", "módulo",
            "evaluación", "tarea", "coachee", "institución", "nivel"
        ],
    },
}


# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_seed(domain_id: str) -> dict:
    """Devuelve el seed completo de un dominio o {} si no existe."""
    return DOMAIN_SEEDS.get(domain_id, {})


def get_base_memory(domain_id: str) -> dict:
    """Devuelve solo la parte base_memory del seed."""
    return DOMAIN_SEEDS.get(domain_id, {}).get("base_memory", {})


def get_empty_domain_extras(domain_id: str) -> dict:
    """Devuelve domain_extras vacío (todos los campos en None) para un dominio."""
    extras = DOMAIN_SEEDS.get(domain_id, {}).get("domain_extras", {})
    return {k: ([] if isinstance(v, list) else None) for k, v in extras.items()}


def get_fact_keywords(domain_id: str) -> list[str]:
    """Devuelve las keywords que triggean actualización del seed."""
    return DOMAIN_SEEDS.get(domain_id, {}).get("fact_keywords", [])


def fact_affects_seed(fact: str, domain_id: str) -> bool:
    """Devuelve True si un [FACT] es relevante para el seed del dominio."""
    if not domain_id:
        return False
    keywords = get_fact_keywords(domain_id)
    fact_lower = fact.lower()
    return any(kw in fact_lower for kw in keywords)


def merge_seed_into_memory(user_data: dict, domain_id: str) -> dict:
    """
    Fusiona el base_memory del seed en la memoria vertical del usuario.
    NO sobreescribe valores existentes — solo llena los vacíos.
    Devuelve dict con las categorías que fueron modificadas.
    """
    base = get_base_memory(domain_id)
    changes = {}

    for category, seed_values in base.items():
        current = user_data.get(category, {}) or {}
        if isinstance(seed_values, dict) and isinstance(current, dict):
            merged = {**seed_values, **current}  # current tiene prioridad
            if merged != current:
                changes[category] = merged

    return changes


def build_seed_summary(domain_seed: dict) -> str:
    """
    Construye un texto legible del seed actual del usuario
    para inyectar en el system prompt como contexto de dominio.
    """
    if not domain_seed:
        return ""

    lines = ["[CONTEXTO DE DOMINIO]"]
    domain_id = domain_seed.get("domain_id")
    if domain_id:
        lines.append(f"Dominio: {domain_id}")

    base = domain_seed.get("base_memory", {})
    for category, values in base.items():
        if values:
            lines.append(f"{category.capitalize()}: {values}")

    extras = domain_seed.get("domain_extras", {})
    filled_extras = {k: v for k, v in extras.items() if v}
    if filled_extras:
        lines.append("Configuración específica:")
        for k, v in filled_extras.items():
            lines.append(f"  {k}: {v}")

    return "\n".join(lines)


def apply_admin_override(domain_seed: dict, domain_id: str, field: str, value: str) -> dict:
    """
    Aplica un override de admin a domain_extras.
    Convierte listas separadas por comas automáticamente.
    Devuelve el domain_seed actualizado.
    """
    if not domain_seed:
        domain_seed = {
            "domain_id": domain_id,
            "base_memory": get_base_memory(domain_id),
            "domain_extras": get_empty_domain_extras(domain_id),
            "created_at": datetime.utcnow().isoformat(),
        }

    extras = domain_seed.get("domain_extras", {})

    # Detectar si el campo original es una lista
    original = DOMAIN_SEEDS.get(domain_id, {}).get("domain_extras", {}).get(field)
    if isinstance(original, list):
        # Convertir "valor1, valor2" a lista
        extras[field] = [v.strip() for v in value.split(",") if v.strip()]
    else:
        extras[field] = value

    domain_seed["domain_extras"] = extras
    domain_seed["updated_at"] = datetime.utcnow().isoformat()
    return domain_seed


async def auto_enrich_seed_from_fact(
    user_id: int,
    new_facts: list[str],
    memory_module,
) -> bool:
    """
    Cuando se aprenden hechos nuevos relevantes al dominio,
    los incorpora al base_memory del seed del usuario.
    Solo toca base_memory — nunca domain_extras (esos son solo para admin).
    Devuelve True si hubo cambios.
    """
    domain_id = memory_module.get_user_domain(user_id)
    if not domain_id:
        return False

    relevant_facts = [f for f in new_facts if fact_affects_seed(f, domain_id)]
    if not relevant_facts:
        return False

    domain_seed = memory_module.get_domain_seed(user_id)
    if not domain_seed:
        domain_seed = {
            "domain_id": domain_id,
            "base_memory": get_base_memory(domain_id),
            "domain_extras": get_empty_domain_extras(domain_id),
            "created_at": datetime.utcnow().isoformat(),
        }

    # Agregar hechos relevantes como contexto adicional en base_memory
    hechos_actuales = domain_seed.get("base_memory", {}).get("hechos_relevantes", [])
    nuevos = [f for f in relevant_facts if f not in hechos_actuales]
    if not nuevos:
        return False

    if "base_memory" not in domain_seed:
        domain_seed["base_memory"] = {}
    domain_seed["base_memory"]["hechos_relevantes"] = (hechos_actuales + nuevos)[-20:]
    domain_seed["updated_at"] = datetime.utcnow().isoformat()

    memory_module.set_domain_seed(user_id, domain_seed)
    logger.info(f"Seed de dominio enriquecido para usuario {user_id}: {len(nuevos)} hechos nuevos")
    return True
