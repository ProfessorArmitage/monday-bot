"""
memory.py — Maneja la memoria del asistente por usuario.

Usa PostgreSQL como almacenamiento persistente.
La variable DATABASE_URL la provee Railway automáticamente
al agregar un plugin de Postgres al proyecto.
"""

import os
import json
import psycopg2
import psycopg2.extras
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


def _connect():
    """Abre una conexión a PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)


def _init_db():
    """
    Crea la tabla de usuarios si no existe.
    Se llama automáticamente la primera vez.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     BIGINT PRIMARY KEY,
                    facts       JSONB  NOT NULL DEFAULT '[]',
                    history     JSONB  NOT NULL DEFAULT '[]',
                    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()


# Inicializar la tabla al importar el módulo
_init_db()


def get_user(user_id: int) -> dict:
    """Devuelve el perfil de un usuario. Lo crea si no existe."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row:
                return dict(row)

            # Crear usuario nuevo
            cur.execute("""
                INSERT INTO users (user_id, facts, history, created_at)
                VALUES (%s, '[]', '[]', %s)
                RETURNING *
            """, (user_id, datetime.now()))
            conn.commit()
            return dict(cur.fetchone())


def add_fact(user_id: int, fact: str):
    """Agrega un hecho sobre el usuario, evitando duplicados."""
    with _connect() as conn:
        with conn.cursor() as cur:
            # Obtener facts actuales
            cur.execute("SELECT facts FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            facts = row[0] if row else []

            if fact not in facts:
                facts.append(fact)
                facts = facts[-50:]  # máximo 50 hechos

                cur.execute(
                    "UPDATE users SET facts = %s WHERE user_id = %s",
                    (json.dumps(facts), user_id)
                )
                conn.commit()


def add_message(user_id: int, role: str, content: str):
    """Agrega un mensaje al historial de conversación."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT history FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            history = row[0] if row else []

            history.append({"role": role, "content": content})
            history = history[-20:]  # últimos 20 mensajes

            cur.execute(
                "UPDATE users SET history = %s WHERE user_id = %s",
                (json.dumps(history), user_id)
            )
            conn.commit()


def get_history(user_id: int) -> list:
    """Devuelve el historial de mensajes del usuario."""
    return get_user(user_id).get("history", [])


def get_facts(user_id: int) -> list:
    """Devuelve los hechos conocidos sobre el usuario."""
    return get_user(user_id).get("facts", [])


def build_system_prompt(user_id: int, base_prompt: str) -> str:
    """Construye el system prompt incluyendo lo que se sabe del usuario."""
    facts = get_facts(user_id)

    if facts:
        facts_text = "\n".join(f"- {f}" for f in facts)
        memory_section = f"""

Lo que sabes sobre este usuario (úsalo para personalizar tus respuestas):
{facts_text}
"""
    else:
        memory_section = "\nAún no sabes nada específico sobre este usuario. Haz preguntas naturales para conocerlo mejor."

    return base_prompt + memory_section


def clear_memory(user_id: int):
    """Borra toda la memoria de un usuario (comando /olvidar)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET facts = '[]', history = '[]' WHERE user_id = %s",
                (user_id,)
            )
            conn.commit()
