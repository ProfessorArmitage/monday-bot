"""
memory.py — Maneja la memoria del asistente por usuario.

Guarda hechos sobre cada usuario en un archivo JSON local.
Cada usuario tiene su propio historial de conversación y perfil.
"""

import json
import os
from datetime import datetime

MEMORY_FILE = "memory.json"


def _load() -> dict:
    """Carga toda la memoria desde el archivo JSON."""
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    """Guarda toda la memoria al archivo JSON."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(user_id: int) -> dict:
    """Devuelve el perfil de un usuario. Lo crea si no existe."""
    data = _load()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "facts": [],           # Cosas que el asistente aprendió del usuario
            "history": [],         # Últimos N mensajes (contexto de conversación)
            "created_at": datetime.now().isoformat(),
        }
        _save(data)
    return data[uid]


def add_fact(user_id: int, fact: str):
    """
    Agrega un hecho sobre el usuario.
    Ejemplo: "Le gusta el café", "Trabaja como diseñador"
    """
    data = _load()
    uid = str(user_id)
    user = data.setdefault(uid, {"facts": [], "history": [], "created_at": datetime.now().isoformat()})

    # Evitar duplicados exactos
    if fact not in user["facts"]:
        user["facts"].append(fact)
        # Máximo 50 hechos guardados
        user["facts"] = user["facts"][-50:]
        _save(data)


def add_message(user_id: int, role: str, content: str):
    """
    Agrega un mensaje al historial de conversación.
    role: "user" o "assistant"
    """
    data = _load()
    uid = str(user_id)
    user = data.setdefault(uid, {"facts": [], "history": [], "created_at": datetime.now().isoformat()})

    user["history"].append({"role": role, "content": content})
    # Guardar solo los últimos 20 mensajes para no gastar tokens
    user["history"] = user["history"][-20:]
    _save(data)


def get_history(user_id: int) -> list:
    """Devuelve el historial de mensajes del usuario."""
    return get_user(user_id).get("history", [])


def get_facts(user_id: int) -> list:
    """Devuelve los hechos conocidos sobre el usuario."""
    return get_user(user_id).get("facts", [])


def build_system_prompt(user_id: int, base_prompt: str) -> str:
    """
    Construye el system prompt completo incluyendo
    lo que el asistente sabe del usuario.
    """
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
    """Borra toda la memoria de un usuario (comando /forget)."""
    data = _load()
    uid = str(user_id)
    if uid in data:
        data[uid] = {
            "facts": [],
            "history": [],
            "created_at": datetime.now().isoformat(),
        }
        _save(data)
