"""
tz_utils.py — Utilidades centralizadas de timezone.

PRINCIPIO: todo datetime interno se guarda en UTC.
           todo datetime que se muestra al usuario se convierte a su zona.
           todo datetime que se compara con hora local se convierte primero.

Usa zoneinfo (stdlib Python 3.9+) — sin dependencias externas.
Respeta DST (horario de verano) automáticamente.
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging

logger = logging.getLogger(__name__)

# Timezone por defecto si el usuario no tiene una configurada
DEFAULT_TZ = "America/Mexico_City"

# Mapa de ciudades comunes → IANA timezone
# Usado por el onboarding para inferir la zona del usuario
CITY_TO_TZ = {
    # México
    "ciudad de méxico": "America/Mexico_City",
    "cdmx": "America/Mexico_City",
    "mexico city": "America/Mexico_City",
    "guadalajara": "America/Mexico_City",
    "monterrey": "America/Monterrey",
    "tijuana": "America/Tijuana",
    "cancún": "America/Cancun",
    "cancun": "America/Cancun",
    "mérida": "America/Merida",
    "merida": "America/Merida",
    "chihuahua": "America/Chihuahua",
    "hermosillo": "America/Hermosillo",
    "mexicali": "America/Tijuana",
    # Latinoamérica
    "bogotá": "America/Bogota",
    "bogota": "America/Bogota",
    "medellín": "America/Bogota",
    "medellin": "America/Bogota",
    "lima": "America/Lima",
    "santiago": "America/Santiago",
    "buenos aires": "America/Argentina/Buenos_Aires",
    "montevideo": "America/Montevideo",
    "caracas": "America/Caracas",
    "quito": "America/Guayaquil",
    "guayaquil": "America/Guayaquil",
    "la paz": "America/La_Paz",
    "asunción": "America/Asuncion",
    "asuncion": "America/Asuncion",
    "panamá": "America/Panama",
    "panama": "America/Panama",
    "san josé": "America/Costa_Rica",
    "san jose": "America/Costa_Rica",
    "guatemala": "America/Guatemala",
    "tegucigalpa": "America/Tegucigalpa",
    "managua": "America/Managua",
    "san salvador": "America/El_Salvador",
    "santo domingo": "America/Santo_Domingo",
    "havana": "America/Havana",
    "habana": "America/Havana",
    "lima": "America/Lima",
    # EE.UU.
    "nueva york": "America/New_York",
    "new york": "America/New_York",
    "miami": "America/New_York",
    "chicago": "America/Chicago",
    "houston": "America/Chicago",
    "dallas": "America/Chicago",
    "denver": "America/Denver",
    "los angeles": "America/Los_Angeles",
    "los ángeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    # Europa
    "madrid": "Europe/Madrid",
    "barcelona": "Europe/Madrid",
    "london": "Europe/London",
    "londres": "Europe/London",
    "paris": "Europe/Paris",
    "parís": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "berlín": "Europe/Berlin",
    "roma": "Europe/Rome",
    "rome": "Europe/Rome",
    "amsterdam": "Europe/Amsterdam",
    "lisbon": "Europe/Lisbon",
    "lisboa": "Europe/Lisbon",
    # Otros
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "sao paulo": "America/Sao_Paulo",
    "são paulo": "America/Sao_Paulo",
    "rio": "America/Sao_Paulo",
    "brasilia": "America/Sao_Paulo",
}


def get_zoneinfo(tz_name: str) -> ZoneInfo:
    """
    Devuelve ZoneInfo para el nombre dado.
    Si es inválido, devuelve el timezone por defecto.
    """
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        logger.warning(f"Timezone inválido '{tz_name}', usando {DEFAULT_TZ}")
        return ZoneInfo(DEFAULT_TZ)


def get_user_tz_name(user_data: dict) -> str:
    """
    Devuelve el nombre IANA de la timezone del usuario.
    Lee de ritmo.zona_horaria, fallback a DEFAULT_TZ.
    """
    tz_name = user_data.get("ritmo", {}).get("zona_horaria", DEFAULT_TZ)
    if not tz_name:
        return DEFAULT_TZ
    return tz_name


def now_utc() -> datetime:
    """Hora actual en UTC con tzinfo."""
    return datetime.now(tz=timezone.utc)


def now_for_user(user_data: dict) -> datetime:
    """
    Hora actual en la timezone del usuario.
    Siempre tiene tzinfo — seguro para comparaciones.
    """
    tz = get_zoneinfo(get_user_tz_name(user_data))
    return datetime.now(tz=tz)


def to_user_tz(dt: datetime, user_data: dict) -> datetime:
    """
    Convierte cualquier datetime a la timezone del usuario.
    Si dt no tiene tzinfo, se asume UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz = get_zoneinfo(get_user_tz_name(user_data))
    return dt.astimezone(tz)


def parse_google_dt(dt_str: str) -> datetime:
    """
    Parsea un datetime string de Google Calendar (ISO 8601 con o sin offset).
    Siempre devuelve datetime con tzinfo.
    """
    if not dt_str:
        return now_utc()
    dt_str = dt_str.strip()

    # Google a veces manda "Z" en lugar de "+00:00"
    dt_str = dt_str.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning(f"No se pudo parsear datetime: {dt_str}")
        return now_utc()


def minutes_until(event_dt: datetime, user_data: dict) -> float:
    """
    Calcula los minutos hasta un evento en la timezone del usuario.
    Siempre positivo si es futuro, negativo si ya pasó.
    """
    now = now_for_user(user_data)
    # Asegurar que event_dt tiene tzinfo
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)
    event_local = event_dt.astimezone(get_zoneinfo(get_user_tz_name(user_data)))
    return (event_local - now).total_seconds() / 60


def get_iso_offset(tz_name: str) -> str:
    """
    Devuelve el offset ISO actual para una timezone, respetando DST.
    Ejemplo: "America/Mexico_City" → "-06:00" o "-05:00" según la época.
    """
    tz = get_zoneinfo(tz_name)
    now = datetime.now(tz=tz)
    offset = now.utcoffset()
    if offset is None:
        return "-06:00"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def normalize_datetime_for_calendar(dt_str: str, tz_name: str) -> tuple[str, bool]:
    """
    Normaliza un string de fecha/hora para Google Calendar.
    Devuelve (iso_string_con_offset, es_all_day).

    Maneja:
      "2026-03-15"              → all-day
      "2026-03-15T10:00"        → agrega segundos + offset DST-aware
      "2026-03-15T10:00:00"     → agrega offset DST-aware
      "2026-03-15T10:00:00-06:00" → ya está completo, validar y devolver
    """
    import re
    if not dt_str:
        return "", False

    dt_str = dt_str.strip().replace("Z", "+00:00")

    # Solo fecha → all-day
    if re.match(r"^\d{4}-\d{2}-\d{2}$", dt_str):
        return dt_str, True

    # Tiene hora pero sin segundos
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", dt_str):
        dt_str += ":00"

    # Tiene hora y segundos pero sin offset
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", dt_str):
        offset = get_iso_offset(tz_name)
        dt_str += offset

    return dt_str, False


def infer_tz_from_city(city: str) -> str | None:
    """
    Infiere la timezone IANA a partir de una ciudad mencionada.
    Devuelve None si no la reconoce.
    """
    city_lower = city.lower().strip()
    # Búsqueda exacta
    if city_lower in CITY_TO_TZ:
        return CITY_TO_TZ[city_lower]
    # Búsqueda parcial
    for known_city, tz in CITY_TO_TZ.items():
        if known_city in city_lower or city_lower in known_city:
            return tz
    return None


# ── DO NOT DISTURB ────────────────────────────────────────────
# La configuración DND vive en ritmo.dnd del usuario:
# {
#   "enabled": true,
#   "start": "22:00",   -- hora de inicio (hora local del usuario)
#   "end": "07:00",     -- hora de fin
#   "dias_libres": ["sábado", "domingo"],  -- días sin notificaciones
#   "snooze_until": "2026-03-06T15:00:00+00:00"  -- snooze temporal (UTC ISO)
# }

def is_dnd_active(user_data: dict) -> tuple[bool, str]:
    """
    Devuelve (True, razón) si el usuario tiene DND activo ahora mismo.
    Devuelve (False, "") si puede recibir notificaciones.

    Considera en orden:
      1. Snooze temporal (tiene prioridad sobre todo)
      2. DND desactivado → siempre False
      3. Día libre
      4. Ventana horaria (soporta rangos que cruzan medianoche)
    """
    from datetime import datetime, timezone as _tz
    import re as _re

    ritmo = user_data.get("ritmo", {}) or {}
    dnd = ritmo.get("dnd", {}) or {}

    # 1. Snooze activo
    snooze_until = dnd.get("snooze_until")
    if snooze_until:
        try:
            until_dt = datetime.fromisoformat(snooze_until)
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=_tz.utc)
            now_utc = datetime.now(_tz.utc)
            if now_utc < until_dt:
                remaining = int((until_dt - now_utc).total_seconds() / 60)
                return True, f"snooze activo ({remaining} min restantes)"
            # Snooze expiró — limpiar en memoria no es responsabilidad de tz_utils
        except Exception:
            pass

    # 2. DND desactivado
    if not dnd.get("enabled"):
        return False, ""

    # 3. Hora local del usuario
    user_now = now_for_user(user_data)
    day_name = user_now.strftime("%A").lower()  # monday, tuesday...

    # Mapa español de días
    day_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes",
        "saturday": "sábado", "sunday": "domingo",
    }.get(day_name, day_name)

    dias_libres = [d.lower() for d in dnd.get("dias_libres", [])]
    if day_es in dias_libres:
        return True, f"día libre ({day_es})"

    # 4. Ventana horaria
    start_str = dnd.get("start", "")
    end_str = dnd.get("end", "")
    if not start_str or not end_str:
        return False, ""

    try:
        sh, sm = [int(x) for x in start_str.split(":")]
        eh, em = [int(x) for x in end_str.split(":")]
        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        now_mins = user_now.hour * 60 + user_now.minute

        # Rango normal (ej. 09:00 – 18:00)
        if start_mins <= end_mins:
            in_window = start_mins <= now_mins < end_mins
        else:
            # Rango que cruza medianoche (ej. 22:00 – 07:00)
            in_window = now_mins >= start_mins or now_mins < end_mins

        if in_window:
            return True, f"horario DND ({start_str} – {end_str})"
    except Exception:
        pass

    return False, ""


def dnd_status_text(user_data: dict) -> str:
    """Devuelve un texto legible del estado DND actual del usuario."""
    ritmo = user_data.get("ritmo", {}) or {}
    dnd = ritmo.get("dnd", {}) or {}

    if not dnd:
        return "No tienes horario de silencio configurado."

    active, reason = is_dnd_active(user_data)
    status = "ACTIVO ahora" if active else "inactivo ahora"

    lines = [f"Modo silencio: {status}"]
    if dnd.get("enabled"):
        lines.append(f"Horario: {dnd.get('start', '?')} – {dnd.get('end', '?')}")
    else:
        lines.append("Notificaciones: activadas")

    dias = dnd.get("dias_libres", [])
    if dias:
        lines.append(f"Dias sin notificaciones: {', '.join(dias)}")

    snooze = dnd.get("snooze_until")
    if snooze:
        from datetime import datetime, timezone as _tz
        try:
            until_dt = datetime.fromisoformat(snooze)
            if until_dt.tzinfo is None:
                until_dt = until_dt.replace(tzinfo=_tz.utc)
            now_utc = datetime.now(_tz.utc)
            if now_utc < until_dt:
                mins = int((until_dt - now_utc).total_seconds() / 60)
                lines.append(f"Snooze activo: {mins} minutos restantes")
        except Exception:
            pass

    return "\n".join(lines)
