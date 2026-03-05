"""
workspace_memory.py — Google Doc como memoria extendida de largo plazo.

Cada usuario tiene un Google Doc llamado "Memoria — [nombre]" en su Drive.
Este documento actúa como segunda mente: el bot lo lee en cada sesión
y lo actualiza cuando aprende algo importante.

Estructura del documento:
  ## IDENTIDAD
  ## TRABAJO
  ## PROYECTOS ACTIVOS
  ## PERSONAS CLAVE
  ## METAS
  ## RITMO Y PREFERENCIAS
  ## NOTAS Y CONTEXTO
  --- Última sincronización: [fecha] ---

El usuario puede editar cualquier sección directamente en Google Docs
y el bot respetará esos cambios en la siguiente conversación.
"""

import logging
import json
import httpx
from datetime import datetime

import memory
from google_auth import get_valid_token

logger = logging.getLogger(__name__)

DOC_TITLE_PREFIX = "Memoria — "
WORKSPACE_DOC_ID_KEY = "workspace_doc_id"


# ── Obtener o crear el documento de memoria ───────────────────



async def bootstrap_existing_user(user_id: int):
    """
    Para usuarios que ya tienen memoria en PostgreSQL pero aún no tienen
    un Google Doc de memoria. Crea el doc y sube toda la memoria existente.
    Llamar una vez al reconectar Google o al primer mensaje post-deploy.
    """
    if not memory.has_google_connected(user_id):
        return

    prefs = memory.get_category(user_id, "preferencias")
    doc_id = prefs.get(WORKSPACE_DOC_ID_KEY)

    # Si ya tiene doc_id guardado y el doc existe → no hacer nada
    if doc_id and await _doc_exists(user_id, doc_id):
        return

    # Crear o encontrar el doc y volcar toda la memoria de postgres
    logger.info(f"Bootstrapping workspace doc para usuario existente {user_id}")
    await sync_memory_to_doc(user_id)

async def get_or_create_memory_doc(user_id: int) -> str | None:
    """
    Devuelve el doc_id del documento de memoria del usuario.
    Si no existe, lo crea y guarda el ID en preferencias.
    Devuelve None si el usuario no tiene Google conectado.
    """
    if not memory.has_google_connected(user_id):
        return None

    # Verificar si ya tenemos el doc_id guardado
    prefs = memory.get_category(user_id, "preferencias")
    doc_id = prefs.get(WORKSPACE_DOC_ID_KEY)

    if doc_id:
        # Verificar que el doc sigue existiendo
        if await _doc_exists(user_id, doc_id):
            return doc_id

    # Buscar en Drive si ya existe un doc con ese título
    user = memory.get_user(user_id)
    nombre = user.get("identidad", {}).get("nombre", "Usuario")
    title = f"{DOC_TITLE_PREFIX}{nombre}"

    doc_id = await _find_doc_in_drive(user_id, title)

    if not doc_id:
        # Crear el documento desde cero
        doc_id = await _create_memory_doc(user_id, title, nombre)

    if doc_id:
        # Guardar el ID para no buscarlo cada vez
        memory.update_category(user_id, "preferencias", {WORKSPACE_DOC_ID_KEY: doc_id})

    return doc_id


async def _doc_exists(user_id: int, doc_id: str) -> bool:
    """Verifica si un documento existe en Drive."""
    try:
        token = await get_valid_token(user_id)
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{doc_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"fields": "id, trashed"}
            )
            if r.status_code == 200:
                data = r.json()
                return not data.get("trashed", False)
        return False
    except Exception:
        return False


async def _find_doc_in_drive(user_id: int, title: str) -> str | None:
    """Busca un documento por título exacto en Drive."""
    try:
        token = await get_valid_token(user_id)
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q": f"name = '{title}' and mimeType = 'application/vnd.google-apps.document' and trashed = false",
                    "fields": "files(id, name)"
                }
            )
            r.raise_for_status()
            files = r.json().get("files", [])
            return files[0]["id"] if files else None
    except Exception as e:
        logger.error(f"Error buscando doc en Drive: {e}")
        return None


async def _create_memory_doc(user_id: int, title: str, nombre: str) -> str | None:
    """Crea el documento de memoria con estructura inicial."""
    try:
        token = await get_valid_token(user_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        initial_content = (
            f"MEMORIA DE {nombre.upper()}\n"
            f"Documento de memoria del asistente personal.\n"
            f"Puedes editar este documento directamente — el asistente lo leerá en cada conversación.\n\n"
            f"--- IDENTIDAD ---\n\n"
            f"--- TRABAJO ---\n\n"
            f"--- PROYECTOS ACTIVOS ---\n\n"
            f"--- PERSONAS CLAVE ---\n\n"
            f"--- METAS ---\n\n"
            f"--- RITMO Y PREFERENCIAS ---\n\n"
            f"--- NOTAS Y CONTEXTO ---\n\n"
            f"=== Creado: {now} ==="
        )

        async with httpx.AsyncClient() as client:
            # Crear el doc
            r = await client.post(
                "https://docs.googleapis.com/v1/documents",
                headers={"Authorization": f"Bearer {token}"},
                json={"title": title}
            )
            r.raise_for_status()
            doc_id = r.json()["documentId"]

            # Insertar contenido inicial
            await client.post(
                f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
                headers={"Authorization": f"Bearer {token}"},
                json={"requests": [{"insertText": {"location": {"index": 1}, "text": initial_content}}]}
            )

        logger.info(f"Documento de memoria creado para usuario {user_id}: {doc_id}")
        return doc_id

    except Exception as e:
        logger.error(f"Error creando doc de memoria: {e}")
        return None


# ── Leer memoria del Doc ──────────────────────────────────────

async def read_memory_doc(user_id: int) -> str | None:
    """
    Lee el contenido del documento de memoria.
    Devuelve el texto plano o None si no hay doc o hay error.
    """
    doc_id = await get_or_create_memory_doc(user_id)
    if not doc_id:
        return None

    try:
        token = await get_valid_token(user_id)
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"https://docs.googleapis.com/v1/documents/{doc_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            body = r.json().get("body", {}).get("content", [])

            text = ""
            for element in body:
                for para in element.get("paragraph", {}).get("elements", []):
                    text += para.get("textRun", {}).get("content", "")

            return text.strip()

    except Exception as e:
        logger.error(f"Error leyendo doc de memoria: {e}")
        return None


# ── Escribir/sincronizar memoria en el Doc ────────────────────

async def sync_memory_to_doc(user_id: int):
    """
    Sincroniza toda la memoria vertical del usuario al Google Doc.
    Reemplaza el contenido del documento con la memoria actual.
    Llamar después de cambios importantes en la memoria.
    """
    doc_id = await get_or_create_memory_doc(user_id)
    if not doc_id:
        return

    try:
        user = memory.get_user(user_id)
        nombre = user.get("identidad", {}).get("nombre", "Usuario")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Construir contenido del documento
        lines = [
            f"MEMORIA DE {nombre.upper()}",
            f"Última sincronización: {now}",
            "Puedes editar este documento — el asistente lo leerá en cada conversación.",
            "",
        ]

        # IDENTIDAD
        identidad = user.get("identidad", {})
        lines.append("--- IDENTIDAD ---")
        if identidad:
            for k, v in identidad.items():
                if v and k != "idioma":
                    lines.append(f"{k}: {v}")
        lines.append("")

        # TRABAJO
        trabajo = user.get("trabajo", {})
        lines.append("--- TRABAJO ---")
        if trabajo:
            for k, v in trabajo.items():
                if v:
                    lines.append(f"{k}: {v}")
        lines.append("")

        # PROYECTOS
        proyectos = user.get("proyectos", [])
        lines.append("--- PROYECTOS ACTIVOS ---")
        for p in proyectos:
            if isinstance(p, dict):
                estado = p.get("estado", "activo")
                nombre_p = p.get("nombre", "?")
                desc = p.get("descripcion", "")
                lines.append(f"• {nombre_p} [{estado}]: {desc}")
            else:
                lines.append(f"• {p}")
        lines.append("")

        # PERSONAS CLAVE
        relaciones = user.get("relaciones", [])
        lines.append("--- PERSONAS CLAVE ---")
        for r in relaciones:
            if isinstance(r, dict):
                lines.append(f"• {r.get('nombre','?')} ({r.get('relacion','?')}): {r.get('notas','')}")
            else:
                lines.append(f"• {r}")
        lines.append("")

        # METAS
        metas = user.get("metas", {})
        lines.append("--- METAS ---")
        for horizonte, meta in metas.items():
            if meta:
                lines.append(f"{horizonte}: {meta}")
        lines.append("")

        # RITMO Y PREFERENCIAS
        ritmo = user.get("ritmo", {})
        prefs = user.get("preferencias", {})
        lines.append("--- RITMO Y PREFERENCIAS ---")
        for k, v in ritmo.items():
            if v:
                lines.append(f"{k}: {v}")
        for k, v in prefs.items():
            if v and k != WORKSPACE_DOC_ID_KEY:
                lines.append(f"{k}: {v}")
        lines.append("")

        # HOOKS
        hooks = prefs.get("hooks", [])
        if hooks:
            lines.append("--- ALERTAS CONFIGURADAS ---")
            for h in hooks:
                if isinstance(h, dict):
                    lines.append(f"• {h.get('tipo','?')}: {h.get('valor','?')} — {h.get('descripcion','')}")
            lines.append("")

        # NOTAS SUELTAS
        hechos = user.get("hechos", [])
        if hechos:
            lines.append("--- NOTAS Y CONTEXTO ---")
            for h in hechos[-20:]:
                lines.append(f"• {h}")
            lines.append("")

        new_content = "\n".join(lines)

        token = await get_valid_token(user_id)
        async with httpx.AsyncClient() as client:
            # Obtener longitud actual del doc para reemplazar todo
            r = await client.get(
                f"https://docs.googleapis.com/v1/documents/{doc_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            doc_data = r.json()
            body = doc_data.get("body", {})
            end_index = body.get("content", [{}])[-1].get("endIndex", 1)

            # Reemplazar contenido completo
            requests = []
            if end_index > 2:
                requests.append({
                    "deleteContentRange": {
                        "range": {"startIndex": 1, "endIndex": end_index - 1}
                    }
                })
            requests.append({
                "insertText": {"location": {"index": 1}, "text": new_content}
            })

            await client.post(
                f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
                headers={"Authorization": f"Bearer {token}"},
                json={"requests": requests}
            )

        logger.info(f"Memoria sincronizada al Doc para usuario {user_id}")

    except Exception as e:
        logger.error(f"Error sincronizando memoria al Doc: {e}")


# ── Parsear cambios del Doc de vuelta a memoria ───────────────

async def sync_doc_to_memory(user_id: int):
    """
    Lee el Google Doc y actualiza la memoria vertical con cualquier
    cambio que el usuario haya hecho directamente en el documento.
    """
    doc_content = await read_memory_doc(user_id)
    if not doc_content:
        return

    current_section = None
    updates = {
        "identidad": {}, "trabajo": {}, "proyectos": [],
        "relaciones": [], "metas": {}, "ritmo": {}
    }

    for line in doc_content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Detectar secciones
        if "--- IDENTIDAD ---" in line:
            current_section = "identidad"
        elif "--- TRABAJO ---" in line:
            current_section = "trabajo"
        elif "--- PROYECTOS" in line:
            current_section = "proyectos"
        elif "--- PERSONAS CLAVE ---" in line:
            current_section = "relaciones"
        elif "--- METAS ---" in line:
            current_section = "metas"
        elif "--- RITMO" in line:
            current_section = "ritmo"
        elif line.startswith("---"):
            current_section = None
        elif current_section and ":" in line and not line.startswith("•"):
            # key: value
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if value and current_section in ("identidad", "trabajo", "metas", "ritmo"):
                updates[current_section][key] = value

    # Aplicar actualizaciones: reemplazar categorías que tengan contenido en el doc
    # Si el doc tiene una sección con datos → esos datos son la fuente de verdad
    # Si el doc tiene una sección vacía → no tocar PostgreSQL (el usuario no la borró)
    for category, data in updates.items():
        if not data:
            continue
        try:
            if isinstance(data, list):
                if data:  # solo reemplazar si hay elementos
                    memory.set_category(user_id, category, data)
            else:
                # Para dicts: merge respetando el doc como fuente de verdad
                # pero solo para campos que están presentes en el doc
                current = memory.get_category(user_id, category)
                if isinstance(current, dict):
                    current.update(data)
                    memory.set_category(user_id, category, current)
        except Exception as e:
            logger.warning(f"Error aplicando sync doc→memory en {category}: {e}")

    logger.info(f"Memoria sincronizada desde Doc para usuario {user_id}")
