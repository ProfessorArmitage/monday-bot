"""
memory_backup.py — Export e import de memoria del usuario.

El backup se guarda como JSON en la carpeta Monday del Drive del usuario.
Formato del archivo: Respaldo_YYYY-MM-DD.json

Estructura del JSON exportado:
{
  "version": "1.0",
  "exported_at": "2026-03-06T...",
  "user_id": 12345,
  "nombre": "Juan",
  "memoria": {
    "identidad": {...},
    "trabajo": {...},
    "proyectos": [...],
    "vida_personal": {...},
    "metas": {...},
    "preferencias": {...},
    "relaciones": [...],
    "ritmo": {...},
    "hechos": [...],
  },
  "skills": [...],
  "bot_identity": {...},
  "domain_id": "ventas",
  "domain_seed": {...},
}

POLÍTICA DE RETENCIÓN:
  Se conservan los últimos MAX_BACKUPS respaldos en Drive.
  Al crear uno nuevo, se elimina el más antiguo si se supera el límite.

SEGURIDAD:
  - Los backups NO incluyen google_tokens (credenciales OAuth).
  - Los backups NO incluyen history (historial de conversación).
  - Al importar, se REEMPLAZA toda la memoria — el usuario es advertido antes.
"""

import json
import logging
from datetime import datetime, timezone

import memory
import google_services
import workspace_memory

logger = logging.getLogger(__name__)

BACKUP_FILENAME_PREFIX = "Respaldo"
MAX_BACKUPS = 4  # Retención: últimos 4 respaldos (~1 mes si es semanal)
BACKUP_VERSION = "1.0"


# ── EXPORT ────────────────────────────────────────────────────

def build_memory_snapshot(user_id: int) -> dict:
    """
    Construye el snapshot completo de la memoria del usuario.
    No incluye tokens OAuth ni historial de conversación.
    """
    user = memory.get_user(user_id)

    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "nombre": user.get("identidad", {}).get("nombre", ""),
        "memoria": {
            "identidad":    user.get("identidad", {}),
            "trabajo":      user.get("trabajo", {}),
            "proyectos":    user.get("proyectos", []),
            "vida_personal": user.get("vida_personal", {}),
            "metas":        user.get("metas", {}),
            "preferencias": user.get("preferencias", {}),
            "relaciones":   user.get("relaciones", []),
            "ritmo":        user.get("ritmo", {}),
            "hechos":       user.get("hechos", []),
        },
        "skills":       user.get("skills", []),
        "bot_identity": user.get("bot_identity", {}),
        "domain_id":    memory.get_user_domain(user_id),
        "domain_seed":  memory.get_domain_seed(user_id),
    }


async def export_to_drive(user_id: int) -> dict:
    """
    Exporta la memoria del usuario a un JSON en la carpeta Monday de Drive.
    Aplica política de retención (MAX_BACKUPS).

    Devuelve:
      {"ok": True, "filename": "...", "file_id": "..."}
      {"ok": False, "error": "..."}
    """
    if not memory.has_google_connected(user_id):
        return {"ok": False, "error": "no_google"}

    # Asegurar carpeta Monday
    folder_id = await workspace_memory.get_or_create_monday_folder(user_id)
    if not folder_id:
        return {"ok": False, "error": "no_folder"}

    # Construir snapshot
    snapshot = build_memory_snapshot(user_id)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{BACKUP_FILENAME_PREFIX}_{date_str}.json"
    content_str = json.dumps(snapshot, ensure_ascii=False, indent=2)

    # Subir a Drive
    file_id = await google_services.upload_json_to_drive(
        user_id, filename, content_str, folder_id
    )
    if not file_id:
        return {"ok": False, "error": "upload_failed"}

    # Aplicar retención
    await _apply_retention_policy(user_id, folder_id, exclude_file_id=file_id)

    logger.info(f"Backup exportado para usuario {user_id}: {filename} ({file_id})")
    return {"ok": True, "filename": filename, "file_id": file_id}


async def _apply_retention_policy(user_id: int, folder_id: str, exclude_file_id: str):
    """Elimina backups viejos si se supera MAX_BACKUPS. Conserva el más reciente."""
    files = await google_services.list_folder_files(
        user_id, folder_id, name_contains=BACKUP_FILENAME_PREFIX
    )
    # list_folder_files devuelve ordenado por createdTime desc
    # El archivo recién creado puede no aparecer aún, excluirlo por id
    old_files = [f for f in files if f["id"] != exclude_file_id]

    if len(old_files) >= MAX_BACKUPS:
        # Eliminar los más viejos (están al final de la lista desc)
        to_delete = old_files[MAX_BACKUPS - 1:]
        for f in to_delete:
            deleted = await google_services.delete_drive_file(user_id, f["id"])
            if deleted:
                logger.info(f"Backup antiguo eliminado: {f['name']} ({f['id']})")


async def list_backups(user_id: int) -> list:
    """
    Lista los backups disponibles en Drive del usuario.
    Devuelve lista de dicts con id, name, createdTime.
    """
    if not memory.has_google_connected(user_id):
        return []

    folder_id = memory.get_monday_folder_id(user_id)
    if not folder_id:
        return []

    files = await google_services.list_folder_files(
        user_id, folder_id, name_contains=BACKUP_FILENAME_PREFIX
    )
    return files


# ── IMPORT ────────────────────────────────────────────────────

async def get_latest_backup_content(user_id: int) -> dict | None:
    """
    Descarga el backup más reciente del Drive del usuario.
    Devuelve el dict del snapshot o None si no hay backups.
    """
    backups = await list_backups(user_id)
    if not backups:
        return None

    # El primero es el más reciente (ordenado desc)
    latest = backups[0]
    content_str = await google_services.download_drive_file(user_id, latest["id"])
    if not content_str:
        return None

    try:
        return json.loads(content_str)
    except json.JSONDecodeError:
        logger.error(f"Backup corrupto para usuario {user_id}: {latest['name']}")
        return None


def restore_from_snapshot(user_id: int, snapshot: dict) -> bool:
    """
    Restaura la memoria del usuario desde un snapshot.
    REEMPLAZA toda la memoria existente.
    No toca: google_tokens, history, onboarding_done, bot_version.

    Devuelve True si tuvo éxito.
    """
    try:
        mem = snapshot.get("memoria", {})

        # Restaurar categorías de memoria vertical
        for category in ["identidad", "trabajo", "proyectos", "vida_personal",
                          "metas", "preferencias", "relaciones", "ritmo", "hechos"]:
            if category in mem:
                memory.set_category(user_id, category, mem[category])

        # Restaurar skills
        if "skills" in snapshot:
            memory.save_skills(user_id, snapshot["skills"])

        # Restaurar identidad del asistente
        if "bot_identity" in snapshot and snapshot["bot_identity"]:
            memory.set_bot_identity(user_id, snapshot["bot_identity"])

        # Restaurar dominio y seed
        if snapshot.get("domain_id"):
            memory.set_user_domain(user_id, snapshot["domain_id"])
        if snapshot.get("domain_seed"):
            memory.set_domain_seed(user_id, snapshot["domain_seed"])

        logger.info(f"Memoria restaurada para usuario {user_id} "
                    f"desde backup del {snapshot.get('exported_at', '?')}")
        return True

    except Exception as e:
        logger.error(f"Error restaurando memoria para usuario {user_id}: {e}")
        return False


def format_backup_list(backups: list) -> str:
    """Formatea la lista de backups para mostrar al usuario."""
    if not backups:
        return "No tienes respaldos guardados aún."

    lines = ["Tus respaldos disponibles:\n"]
    for i, b in enumerate(backups, 1):
        name = b.get("name", "Respaldo")
        created = b.get("createdTime", "")[:10]  # YYYY-MM-DD
        lines.append(f"  {i}. {name} ({created})")
    lines.append("\nEl respaldo más reciente es el 1.")
    return "\n".join(lines)


def build_confirmation_warning(user_id: int, snapshot: dict) -> str:
    """
    Construye el mensaje de advertencia antes de importar.
    Claro, conciso y honesto sobre lo que se perderá.
    """
    exported_at = snapshot.get("exported_at", "")[:10]
    nombre_backup = snapshot.get("nombre", "")
    mem = snapshot.get("memoria", {})

    # Contar qué tiene el backup
    proyectos = len(mem.get("proyectos", []))
    hechos = len(mem.get("hechos", []))
    skills = len(snapshot.get("skills", []))

    # Contar qué tiene la memoria actual
    user = memory.get_user(user_id)
    proyectos_actual = len(user.get("proyectos", []))
    hechos_actual = len(user.get("hechos", []))
    skills_actual = len(user.get("skills", []))

    msg = (
        f"⚠️ Estás a punto de REEMPLAZAR tu memoria actual.\n\n"
        f"Respaldo seleccionado: {exported_at}\n"
        f"  • {proyectos} proyectos  •  {hechos} hechos  •  {skills} skills\n\n"
        f"Memoria actual (se perderá):\n"
        f"  • {proyectos_actual} proyectos  •  {hechos_actual} hechos  •  {skills_actual} skills\n\n"
        f"Todo lo que aprendí después del {exported_at} se perderá.\n"
        f"Tu conexión con Google no se verá afectada.\n\n"
        f"¿Confirmas? Responde si para continuar o no para cancelar."
    )
    return msg
