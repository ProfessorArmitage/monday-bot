"""
memory.py — Memoria vertical estructurada por categorías.

Cada usuario tiene memoria organizada en áreas:
  - identidad:     nombre, edad, ubicación, idioma preferido
  - trabajo:       empresa, rol, equipo, herramientas, responsabilidades
  - proyectos:     proyectos activos, estado, prioridades
  - vida_personal: familia, rutinas, intereses, ciudad
  - metas:         objetivos semanales, mensuales, largo plazo
  - preferencias:  tono, formato de respuesta, horarios de notificación
  - relaciones:    personas clave (jefe, clientes, equipo, familia)
  - ritmo:         horarios de briefing, ventanas de trabajo, días libres
  - hechos:        hechos sueltos detectados en conversación (legacy)
"""

import os
import json
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")

# Categorías válidas de memoria vertical
MEMORY_CATEGORIES = [
    "identidad",
    "trabajo",
    "proyectos",
    "vida_personal",
    "metas",
    "preferencias",
    "relaciones",
    "ritmo",
    "hechos",        # hechos sueltos detectados automáticamente
]


def _connect():
    return psycopg2.connect(DATABASE_URL)


def _init_db():
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id           BIGINT PRIMARY KEY,
                    -- Memoria vertical por categorías
                    identidad         JSONB NOT NULL DEFAULT '{}',
                    trabajo           JSONB NOT NULL DEFAULT '{}',
                    proyectos         JSONB NOT NULL DEFAULT '[]',
                    vida_personal     JSONB NOT NULL DEFAULT '{}',
                    metas             JSONB NOT NULL DEFAULT '{}',
                    preferencias      JSONB NOT NULL DEFAULT '{}',
                    relaciones        JSONB NOT NULL DEFAULT '[]',
                    ritmo             JSONB NOT NULL DEFAULT '{}',
                    hechos            JSONB NOT NULL DEFAULT '[]',
                    -- Onboarding
                    onboarding_done   BOOLEAN NOT NULL DEFAULT FALSE,
                    onboarding_state  JSONB NOT NULL DEFAULT '{}',
                    -- Historial de conversación
                    history           JSONB NOT NULL DEFAULT '[]',
                    -- Google OAuth
                    google_tokens     JSONB DEFAULT NULL,
                    -- Skills activas
                    skills            JSONB NOT NULL DEFAULT '[]',
                    -- Metadata
                    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_seen         TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            # Migraciones para tablas existentes
            migrations = [
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS identidad JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS trabajo JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS proyectos JSONB NOT NULL DEFAULT '[]'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS vida_personal JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS metas JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferencias JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS relaciones JSONB NOT NULL DEFAULT '[]'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS ritmo JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS hechos JSONB NOT NULL DEFAULT '[]'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_done BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_state JSONB NOT NULL DEFAULT '{}'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_tokens JSONB DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS skills JSONB NOT NULL DEFAULT '[]'",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP NOT NULL DEFAULT NOW()",
                # Migrar facts → hechos si existe la columna vieja
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS hechos JSONB NOT NULL DEFAULT '[]'",
            ]
            for sql in migrations:
                try:
                    cur.execute(sql)
                except Exception:
                    pass
        conn.commit()


_init_db()


# ── Operaciones básicas de usuario ───────────────────────────

def get_user(user_id: int) -> dict:
    """Devuelve el perfil completo del usuario. Lo crea si no existe."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row:
                # Actualizar last_seen
                cur.execute(
                    "UPDATE users SET last_seen = NOW() WHERE user_id = %s",
                    (user_id,)
                )
                conn.commit()
                return dict(row)

            cur.execute("""
                INSERT INTO users (user_id, created_at, last_seen)
                VALUES (%s, NOW(), NOW())
                RETURNING *
            """, (user_id,))
            conn.commit()
            return dict(cur.fetchone())


def is_new_user(user_id: int) -> bool:
    """True si el usuario nunca ha completado el onboarding."""
    user = get_user(user_id)
    return not user.get("onboarding_done", False)


# ── Memoria vertical ──────────────────────────────────────────

def get_category(user_id: int, category: str) -> dict | list:
    """Devuelve el contenido de una categoría de memoria."""
    if category not in MEMORY_CATEGORIES:
        raise ValueError(f"Categoría inválida: {category}")
    user = get_user(user_id)
    return user.get(category, {} if category not in ("proyectos", "relaciones", "hechos") else [])


def set_category(user_id: int, category: str, data: dict | list):
    """Reemplaza completamente el contenido de una categoría."""
    if category not in MEMORY_CATEGORIES:
        raise ValueError(f"Categoría inválida: {category}")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE users SET {category} = %s WHERE user_id = %s",
                (json.dumps(data), user_id)
            )
            conn.commit()


def update_category(user_id: int, category: str, updates: dict):
    """
    Actualiza campos específicos dentro de una categoría dict.
    Hace merge — no reemplaza campos existentes que no estén en updates.
    """
    current = get_category(user_id, category)
    if isinstance(current, list):
        raise ValueError(f"Categoría '{category}' es lista — usa set_category o add_to_category")
    current.update(updates)
    set_category(user_id, category, current)


def add_to_category(user_id: int, category: str, item: dict | str):
    """Agrega un elemento a una categoría que es lista (proyectos, relaciones, hechos)."""
    current = get_category(user_id, category)
    if not isinstance(current, list):
        raise ValueError(f"Categoría '{category}' no es lista")
    # Evitar duplicados en hechos
    if category == "hechos" and item in current:
        return
    current.append(item)
    # Límite de hechos
    if category == "hechos":
        current = current[-100:]
    set_category(user_id, category, current)


# ── Compatibilidad con código anterior ───────────────────────

def add_fact(user_id: int, fact: str):
    """Agrega un hecho suelto (compatibilidad con código anterior)."""
    add_to_category(user_id, "hechos", fact)


def get_facts(user_id: int) -> list:
    """Devuelve hechos sueltos."""
    return get_category(user_id, "hechos")


# ── Historial de conversación ─────────────────────────────────

def add_message(user_id: int, role: str, content: str):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT history FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            history = row[0] if row else []
            history.append({"role": role, "content": content})
            history = history[-30:]  # últimos 30 mensajes
            cur.execute(
                "UPDATE users SET history = %s WHERE user_id = %s",
                (json.dumps(history), user_id)
            )
            conn.commit()


def get_history(user_id: int) -> list:
    return get_user(user_id).get("history", [])


def clear_history(user_id: int):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET history = '[]' WHERE user_id = %s", (user_id,))
            conn.commit()


# ── Onboarding ────────────────────────────────────────────────

def get_onboarding_state(user_id: int) -> dict:
    return get_user(user_id).get("onboarding_state", {})


def set_onboarding_state(user_id: int, state: dict):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET onboarding_state = %s WHERE user_id = %s",
                (json.dumps(state), user_id)
            )
            conn.commit()


def complete_onboarding(user_id: int):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET onboarding_done = TRUE, onboarding_state = '{}' WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()


# ── System prompt con memoria vertical ───────────────────────

def build_system_prompt(user_id: int, base_prompt: str) -> str:
    """
    Construye el system prompt completo incluyendo toda la memoria vertical.
    El contexto se organiza por categorías para máxima relevancia.
    """
    user = get_user(user_id)

    sections = []

    # Identidad
    identidad = user.get("identidad", {})
    if identidad:
        parts = []
        if identidad.get("nombre"):   parts.append(f"nombre: {identidad['nombre']}")
        if identidad.get("ubicacion"): parts.append(f"ubicación: {identidad['ubicacion']}")
        if identidad.get("idioma"):    parts.append(f"idioma preferido: {identidad['idioma']}")
        if parts:
            sections.append("IDENTIDAD: " + ", ".join(parts))

    # Trabajo
    trabajo = user.get("trabajo", {})
    if trabajo:
        parts = []
        if trabajo.get("empresa"):  parts.append(f"empresa: {trabajo['empresa']}")
        if trabajo.get("rol"):      parts.append(f"rol: {trabajo['rol']}")
        if trabajo.get("equipo"):   parts.append(f"equipo: {trabajo['equipo']}")
        if parts:
            sections.append("TRABAJO: " + ", ".join(parts))

    # Proyectos activos
    proyectos = user.get("proyectos", [])
    activos = [p for p in proyectos if isinstance(p, dict) and p.get("estado") != "completado"]
    if activos:
        names = [p.get("nombre", str(p)) for p in activos[:5]]
        sections.append(f"PROYECTOS ACTIVOS: {', '.join(names)}")

    # Metas
    metas = user.get("metas", {})
    if metas.get("semana"):  sections.append(f"META DE LA SEMANA: {metas['semana']}")
    if metas.get("mes"):     sections.append(f"META DEL MES: {metas['mes']}")

    # Preferencias
    prefs = user.get("preferencias", {})
    if prefs:
        parts = []
        if prefs.get("tono"):    parts.append(f"tono: {prefs['tono']}")
        if prefs.get("formato"): parts.append(f"formato: {prefs['formato']}")
        if parts:
            sections.append("PREFERENCIAS: " + ", ".join(parts))

    # Ritmo
    ritmo = user.get("ritmo", {})
    if ritmo.get("briefing_hora"):
        sections.append(f"RITMO: briefing a las {ritmo['briefing_hora']}")

    # Relaciones clave
    relaciones = user.get("relaciones", [])
    if relaciones:
        names = [r.get("nombre", str(r)) for r in relaciones[:5] if isinstance(r, dict)]
        if names:
            sections.append(f"PERSONAS CLAVE: {', '.join(names)}")

    # Hechos sueltos
    hechos = user.get("hechos", [])
    if hechos:
        recent = hechos[-15:]
        sections.append("CONTEXTO ADICIONAL:\n" + "\n".join(f"- {h}" for h in recent))

    if sections:
        memory_block = "\n\n=== LO QUE SABES DE ESTE USUARIO ===\n" + "\n".join(sections) + "\n==================================="
    else:
        memory_block = "\n\nAún no sabes nada de este usuario — es su primera conversación."

    return base_prompt + memory_block


# ── Google OAuth ──────────────────────────────────────────────

def save_google_tokens(user_id: int, tokens):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET google_tokens = %s WHERE user_id = %s",
                (json.dumps(tokens) if tokens else None, user_id)
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO users (user_id, google_tokens) VALUES (%s, %s)",
                    (user_id, json.dumps(tokens) if tokens else None)
                )
            conn.commit()


def get_google_tokens(user_id: int) -> dict | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT google_tokens FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] else None


def has_google_connected(user_id: int) -> bool:
    return get_google_tokens(user_id) is not None


# ── Skills ────────────────────────────────────────────────────

def get_skills(user_id: int) -> list:
    return get_user(user_id).get("skills", [])


def save_skill(user_id: int, skill: dict):
    skills = get_skills(user_id)
    skills = [s for s in skills if s.get("id") != skill.get("id")]
    skills.append(skill)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET skills = %s WHERE user_id = %s",
                (json.dumps(skills), user_id)
            )
            conn.commit()


def remove_skill(user_id: int, skill_id: str):
    skills = [s for s in get_skills(user_id) if s.get("id") != skill_id]
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET skills = %s WHERE user_id = %s",
                (json.dumps(skills), user_id)
            )
            conn.commit()


# ── Borrar toda la memoria ────────────────────────────────────

def clear_memory(user_id: int):
    """Borra toda la memoria del usuario excepto tokens de Google."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET
                    identidad = '{}', trabajo = '{}', proyectos = '[]',
                    vida_personal = '{}', metas = '{}', preferencias = '{}',
                    relaciones = '[]', ritmo = '{}', hechos = '[]',
                    history = '[]', onboarding_done = FALSE, onboarding_state = '{}'
                WHERE user_id = %s
            """, (user_id,))
            conn.commit()


# ── Todos los usuarios (para scheduler) ──────────────────────

def get_all_users() -> list[int]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            return [r[0] for r in cur.fetchall()]


def get_all_google_users() -> list[int]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE google_tokens IS NOT NULL")
            return [r[0] for r in cur.fetchall()]
