"""
audio_handler.py — Procesamiento de audio de entrada y salida.

ARQUITECTURA:
  El módulo está diseñado con providers intercambiables.
  Para cambiar de proveedor, solo hay que cambiar STT_PROVIDER o TTS_PROVIDER
  y agregar la implementación correspondiente — el resto del bot no cambia.

STT (Speech-to-Text) — voz → texto:
  Provider actual:  GROQ_WHISPER  (Whisper large-v3 via Groq API)
  Alternativas preparadas: OPENAI_WHISPER, LOCAL_WHISPER

TTS (Text-to-Speech) — texto → voz:
  Provider actual:  GTTS  (Google Text-to-Speech, sin credenciales)
  Alternativas preparadas: OPENAI_TTS, ELEVENLABS, GOOGLE_CLOUD_TTS

FLUJO:
  Audio Telegram (.ogg) → transcribe() → texto → handle_message normal
  Texto respuesta → synthesize() → bytes .ogg → send_voice en Telegram

PREFERENCIA DE RESPUESTA:
  Por default el bot responde en texto.
  El usuario puede cambiar a respuestas en audio con /voz activar.
  Se guarda en preferencias.respuesta_en_voz (bool).
"""

import os
import io
import logging
import asyncio
import tempfile

import httpx

logger = logging.getLogger(__name__)

# ── CONFIGURACIÓN DE PROVIDERS ────────────────────────────────
# Cambiar estas constantes para migrar de proveedor sin tocar
# el resto del código.

STT_PROVIDER = "GROQ_WHISPER"   # opciones: GROQ_WHISPER | OPENAI_WHISPER
TTS_PROVIDER = "GTTS"           # opciones: GTTS | OPENAI_TTS | ELEVENLABS

# Groq Whisper
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
GROQ_AUDIO_URL    = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_WHISPER_MODEL = "whisper-large-v3"
AUDIO_LANGUAGE    = "es"  # idioma base — Whisper auto-detecta pero esto mejora precisión

# OpenAI (alternativa STT y TTS)
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENAI_AUDIO_URL  = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_TTS_URL    = "https://api.openai.com/v1/audio/speech"
OPENAI_TTS_VOICE  = "nova"       # opciones: alloy, echo, fable, onyx, nova, shimmer
OPENAI_TTS_MODEL  = "tts-1"

# ElevenLabs (alternativa TTS premium)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_URL    = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"


# ── STT — TRANSCRIPCIÓN ───────────────────────────────────────

async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """
    Transcribe audio a texto usando el STT_PROVIDER configurado.

    Args:
        audio_bytes: contenido del archivo de audio (ogg, mp3, wav, m4a, webm)
        filename: nombre del archivo con extensión correcta (afecta al MIME type)

    Returns:
        Texto transcrito, o "" si falla.
    """
    if STT_PROVIDER == "GROQ_WHISPER":
        return await _transcribe_groq(audio_bytes, filename)
    elif STT_PROVIDER == "OPENAI_WHISPER":
        return await _transcribe_openai(audio_bytes, filename)
    else:
        logger.error(f"STT_PROVIDER desconocido: {STT_PROVIDER}")
        return ""


async def _transcribe_groq(audio_bytes: bytes, filename: str) -> str:
    """Transcripción via Groq Whisper API."""
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY no configurada para transcripción")
        return ""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                GROQ_AUDIO_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={
                    "file": (filename, audio_bytes, _mime_from_filename(filename)),
                },
                data={
                    "model": GROQ_WHISPER_MODEL,
                    "language": AUDIO_LANGUAGE,
                    "response_format": "json",
                },
            )

        if r.status_code == 200:
            text = r.json().get("text", "").strip()
            logger.info(f"Transcripción Groq exitosa: {len(text)} chars")
            return text
        else:
            logger.error(f"Groq Whisper error {r.status_code}: {r.text[:200]}")
            return ""

    except Exception as e:
        logger.error(f"Error en transcripción Groq: {e}")
        return ""


async def _transcribe_openai(audio_bytes: bytes, filename: str) -> str:
    """Transcripción via OpenAI Whisper API (alternativa)."""
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY no configurada")
        return ""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                OPENAI_AUDIO_URL,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                files={"file": (filename, audio_bytes, _mime_from_filename(filename))},
                data={"model": "whisper-1", "language": AUDIO_LANGUAGE},
            )
        if r.status_code == 200:
            return r.json().get("text", "").strip()
        logger.error(f"OpenAI Whisper error {r.status_code}: {r.text[:200]}")
        return ""
    except Exception as e:
        logger.error(f"Error en transcripción OpenAI: {e}")
        return ""


# ── TTS — SÍNTESIS DE VOZ ─────────────────────────────────────

async def synthesize(text: str) -> bytes | None:
    """
    Convierte texto a audio usando el TTS_PROVIDER configurado.

    Args:
        text: texto a convertir (se limpian marcadores internos del bot)

    Returns:
        Bytes del archivo .ogg, o None si falla.
    """
    clean_text = _clean_text_for_tts(text)
    if not clean_text:
        return None

    if TTS_PROVIDER == "GTTS":
        return await _synthesize_gtts(clean_text)
    elif TTS_PROVIDER == "OPENAI_TTS":
        return await _synthesize_openai(clean_text)
    elif TTS_PROVIDER == "ELEVENLABS":
        return await _synthesize_elevenlabs(clean_text)
    else:
        logger.error(f"TTS_PROVIDER desconocido: {TTS_PROVIDER}")
        return None


async def _synthesize_gtts(text: str) -> bytes | None:
    """
    TTS via gTTS (Google Text-to-Speech público, sin credenciales).
    Genera MP3 y lo devuelve como bytes OGG via ffmpeg si está disponible,
    o MP3 directo si no (Telegram acepta ambos).
    """
    try:
        from gtts import gTTS

        # gTTS es síncrono — correrlo en executor para no bloquear el event loop
        loop = asyncio.get_event_loop()

        def _generate():
            tts = gTTS(text=text, lang="es", slow=False)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()

        audio_bytes = await loop.run_in_executor(None, _generate)

        # Intentar convertir a OGG/OPUS via ffmpeg (mejor calidad en Telegram)
        ogg_bytes = await _mp3_to_ogg(audio_bytes)
        return ogg_bytes if ogg_bytes else audio_bytes

    except ImportError:
        logger.error("gTTS no instalado — agrega 'gtts' a requirements.txt")
        return None
    except Exception as e:
        logger.error(f"Error en síntesis gTTS: {e}")
        return None


async def _synthesize_openai(text: str) -> bytes | None:
    """TTS via OpenAI API (alternativa de alta calidad)."""
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY no configurada para TTS")
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                OPENAI_TTS_URL,
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_TTS_MODEL,
                    "input": text,
                    "voice": OPENAI_TTS_VOICE,
                    "response_format": "opus",
                },
            )
        if r.status_code == 200:
            return r.content
        logger.error(f"OpenAI TTS error {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Error en síntesis OpenAI TTS: {e}")
        return None


async def _synthesize_elevenlabs(text: str) -> bytes | None:
    """TTS via ElevenLabs (alternativa premium con voz personalizable)."""
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        logger.error("ELEVENLABS_API_KEY o ELEVENLABS_VOICE_ID no configurados")
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                ELEVENLABS_URL,
                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
                params={"output_format": "ogg_48000_128"},
            )
        if r.status_code == 200:
            return r.content
        logger.error(f"ElevenLabs error {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Error en síntesis ElevenLabs: {e}")
        return None


# ── HELPERS ───────────────────────────────────────────────────

async def _mp3_to_ogg(mp3_bytes: bytes) -> bytes | None:
    """
    Convierte MP3 a OGG/OPUS usando ffmpeg si está disponible.
    Telegram prefiere OGG para mensajes de voz (send_voice).
    Si ffmpeg no está disponible, devuelve None y se usa el MP3 original.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", "pipe:0",          # input desde stdin
            "-c:a", "libopus",        # codec OPUS
            "-b:a", "64k",            # bitrate
            "-f", "ogg",              # formato output
            "pipe:1",                 # output a stdout
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        ogg_bytes, _ = await asyncio.wait_for(
            proc.communicate(input=mp3_bytes),
            timeout=15,
        )
        return ogg_bytes if ogg_bytes else None
    except (FileNotFoundError, asyncio.TimeoutError):
        return None  # ffmpeg no disponible — usar MP3 directamente
    except Exception as e:
        logger.debug(f"ffmpeg conversion failed: {e}")
        return None


def _mime_from_filename(filename: str) -> str:
    """Devuelve el MIME type correcto según la extensión del archivo."""
    ext = filename.rsplit(".", 1)[-1].lower()
    return {
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "mp4": "audio/mp4",
        "m4a": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "flac": "audio/flac",
    }.get(ext, "audio/ogg")


def _clean_text_for_tts(text: str) -> str:
    """
    Limpia el texto antes de enviarlo al TTS.
    - Elimina marcadores internos del bot ([FACT:...], [ACTION:...])
    - Elimina Markdown
    - Trunca si es muy largo (TTS tiene límites y respuestas muy largas suenan mal)
    """
    import re
    # Eliminar marcadores internos
    text = re.sub(r'\[FACT:[^\]]*\]', '', text)
    text = re.sub(r'\[ACTION:[^\]]*\]', '', text)
    # Eliminar Markdown básico
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'#{1,6}\s', '', text)
    # Limpiar espacios extra
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    # Truncar a 1000 chars para TTS (respuestas muy largas son poco útiles en audio)
    if len(text) > 1000:
        text = text[:950] + "... (respuesta completa disponible en texto)"
    return text


def user_wants_voice(user_data: dict) -> bool:
    """Devuelve True si el usuario prefiere respuestas en audio."""
    return bool(
        user_data.get("preferencias", {}).get("respuesta_en_voz", False)
    )
