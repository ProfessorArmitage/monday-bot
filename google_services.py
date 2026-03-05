"""
google_services.py — Llama a las APIs de Google en nombre del usuario.

Servicios disponibles:
  - Google Calendar  → ver agenda, crear eventos
  - Gmail            → leer correos, enviar, responder
  - Google Docs      → crear y leer documentos
  - Google Drive     → buscar y listar archivos
  - Google Sheets    → leer y escribir celdas
"""

import httpx
from datetime import datetime, timezone, timedelta
from google_auth import get_valid_token


# ════════════════════════════════════════════════════════════
# GOOGLE CALENDAR
# ════════════════════════════════════════════════════════════

async def get_upcoming_events(user_id: int, max_results: int = 10, days: int = 7, **kwargs) -> list:
    """Devuelve los próximos eventos del calendario dentro de un rango de días."""
    token = await get_valid_token(user_id)
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days)).isoformat()

    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
        )
        r.raise_for_status()
        return r.json().get("items", [])


async def create_event(user_id: int, title: str = "", start: str = "", end: str = "", description: str = "", **kwargs) -> dict:
    """
    Crea un evento en Google Calendar.
    start y end deben ser strings ISO 8601, ej: "2025-03-15T10:00:00-06:00"
    """
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "summary":     title,
                "description": description,
                "start": {"dateTime": start, "timeZone": "America/Mexico_City"},
                "end":   {"dateTime": end,   "timeZone": "America/Mexico_City"},
            }
        )
        r.raise_for_status()
        return r.json()


# ════════════════════════════════════════════════════════════
# GMAIL
# ════════════════════════════════════════════════════════════

def _build_gmail_query(sender=None, subject=None, extra=None):
    """Construye un query de búsqueda para Gmail."""
    parts = ["in:inbox"]
    if sender:  parts.append(f"from:{sender}")
    if subject: parts.append(f"subject:{subject}")
    if extra:   parts.append(extra)
    return " ".join(parts)


def _extract_body(payload):
    """Extrae el texto plano del cuerpo de un mensaje recursivamente."""
    import base64
    if payload.get("mimeType") == "text/plain":
        data_b64 = payload.get("body", {}).get("data", "")
        if data_b64:
            return base64.urlsafe_b64decode(data_b64 + "==").decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""


async def get_recent_emails(user_id: int, max_results: int = 5, limit: int = None,
                             sender: str = None, subject: str = None, **kwargs) -> list:
    """
    Devuelve correos recientes con SOLO asunto, remitente y fecha.
    Rápido — usa metadatos, no descarga el cuerpo.
    """
    if limit: max_results = limit
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"maxResults": max_results, "q": _build_gmail_query(sender, subject)}
        )
        r.raise_for_status()
        messages = r.json().get("messages", [])

        emails = []
        for msg in messages:
            r2 = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]}
            )
            r2.raise_for_status()
            data = r2.json()
            hdrs = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
            emails.append({
                "id":      msg["id"],
                "Subject": hdrs.get("Subject", "Sin asunto"),
                "From":    hdrs.get("From", "Desconocido"),
                "Date":    hdrs.get("Date", ""),
                "snippet": data.get("snippet", ""),
            })

        return emails


async def get_email_full(user_id: int, max_results: int = 1, limit: int = None,
                          sender: str = None, subject: str = None, **kwargs) -> list:
    """
    Devuelve correos con el cuerpo completo incluido.
    Más lento — descarga el contenido completo de cada mensaje.
    """
    if limit: max_results = limit
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"maxResults": max_results, "q": _build_gmail_query(sender, subject)}
        )
        r.raise_for_status()
        messages = r.json().get("messages", [])

        emails = []
        for msg in messages:
            r2 = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "full"}
            )
            r2.raise_for_status()
            data = r2.json()
            payload = data.get("payload", {})
            hdrs = {h["name"]: h["value"] for h in payload.get("headers", [])}
            emails.append({
                "id":      msg["id"],
                "Subject": hdrs.get("Subject", "Sin asunto"),
                "From":    hdrs.get("From", "Desconocido"),
                "Date":    hdrs.get("Date", ""),
                "Body":    _extract_body(payload)[:3000].strip(),
                "snippet": data.get("snippet", ""),
            })

        return emails


async def send_email(user_id: int, to: str = "", subject: str = "", body: str = "", message: str = None, **kwargs) -> dict:
    if message: body = message
    """Envía un correo desde la cuenta del usuario."""
    import base64
    from email.mime.text import MIMEText

    token = await get_valid_token(user_id)

    msg = MIMEText(body)
    msg["to"]      = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"raw": raw}
        )
        r.raise_for_status()
        return r.json()


# ════════════════════════════════════════════════════════════
# GOOGLE DOCS
# ════════════════════════════════════════════════════════════

async def create_doc(user_id: int, title: str = "Nuevo documento", content: str = "", text: str = None, **kwargs) -> dict:
    if text: content = text
    """Crea un Google Doc con título y contenido opcional."""
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        # Crear el documento
        r = await client.post(
            "https://docs.googleapis.com/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": title}
        )
        r.raise_for_status()
        doc_id = r.json()["documentId"]

        # Insertar contenido si se proporcionó
        if content:
            await client.post(
                f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
                headers={"Authorization": f"Bearer {token}"},
                json={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]}
            )

        return {"documentId": doc_id, "url": f"https://docs.google.com/document/d/{doc_id}"}


async def get_doc_content(user_id: int, doc_id: str) -> str:
    """Lee el contenido de texto de un Google Doc."""
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


# ════════════════════════════════════════════════════════════
# GOOGLE DRIVE
# ════════════════════════════════════════════════════════════

async def search_files(user_id: int, query: str = "", keyword: str = None,
                        name: str = None, max_results: int = 5, **kwargs) -> list:
    """Busca archivos en Google Drive por nombre o keyword."""
    if keyword: query = keyword
    if name:    query = name
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "q":        f"name contains '{query}' and trashed = false",
                "pageSize": max_results,
                "fields":   "files(id, name, mimeType, webViewLink, modifiedTime)"
            }
        )
        r.raise_for_status()
        return r.json().get("files", [])


async def list_recent_files(user_id: int, max_results: int = 5, limit: int = None, **kwargs) -> list:
    if limit: max_results = limit
    """Lista los archivos más recientes de Drive."""
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "pageSize": max_results,
                "orderBy":  "modifiedTime desc",
                "fields":   "files(id, name, mimeType, webViewLink, modifiedTime)"
            }
        )
        r.raise_for_status()
        return r.json().get("files", [])


# ════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ════════════════════════════════════════════════════════════

async def read_sheet(user_id: int, spreadsheet_id: str = "", range_: str = "Sheet1!A1:Z100", **kwargs) -> list:
    """Lee un rango de celdas de Google Sheets."""
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_}",
            headers={"Authorization": f"Bearer {token}"}
        )
        r.raise_for_status()
        return r.json().get("values", [])


async def append_to_sheet(user_id: int, spreadsheet_id: str = "", values: list = None, range_: str = "Sheet1!A1", **kwargs) -> dict:
    if values is None: values = []
    """Agrega filas al final de una hoja de Sheets."""
    token = await get_valid_token(user_id)

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_}:append",
            headers={"Authorization": f"Bearer {token}"},
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": values}
        )
        r.raise_for_status()
        return r.json()


async def delete_event(user_id: int, event_id: str = "", **kwargs) -> dict:
    """Elimina un evento del calendario."""
    token = await get_valid_token(user_id)
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        r.raise_for_status()
        return {"deleted": True, "event_id": event_id}

async def get_doc_content(user_id: int, doc_id: str = "", **kwargs) -> str:
    """Lee el contenido de un Google Doc."""
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
