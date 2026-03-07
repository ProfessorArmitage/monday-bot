"""
channel_types.py — Tipos normalizados para el sistema multi-canal.

Define la interfaz entre los adapters de canal y el core engine.
Cada canal (Telegram, WhatsApp, Slack, Email) convierte sus mensajes
nativos a InboundMessage antes de pasarlos a channel_router.process_message().

PRINCIPIO: el core engine nunca sabe en qué canal está operando.
Solo recibe InboundMessage y llama a send_fn() para responder.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ChannelType(str, Enum):
    TELEGRAM  = "telegram"
    WHATSAPP  = "whatsapp"
    SLACK     = "slack"
    EMAIL     = "email"


@dataclass
class InboundMessage:
    """
    Mensaje normalizado que llega de cualquier canal al core engine.

    Campos:
        monday_id   — ID interno de Monday (users.user_id en PostgreSQL)
                      Resuelto por el adapter antes de llamar al router.
        channel     — canal de origen (ChannelType)
        text        — texto del mensaje (ya transcrito si era audio)
        is_voice    — True si el mensaje original era audio
        subject     — solo email: asunto del correo
        thread_id   — solo email: ID del hilo para responder en el mismo thread
        raw         — payload original del canal (para uso interno del adapter)
    """
    monday_id : int
    channel   : ChannelType
    text      : str
    is_voice  : bool = False
    subject   : str  = ""
    thread_id : str  = ""
    raw       : Any  = field(default=None, repr=False)


@dataclass
class OutboundMessage:
    """
    Respuesta normalizada que el router devuelve al adapter.
    El adapter decide cómo enviarla según el canal.

    Campos:
        text        — texto de la respuesta (siempre presente)
        is_voice    — True si el usuario prefiere respuesta en audio
        monday_id   — ID del destinatario
        channel     — canal de destino
        subject     — solo email: asunto de la respuesta
        thread_id   — solo email: mantener el mismo hilo
    """
    text      : str
    is_voice  : bool = False
    monday_id : int  = 0
    channel   : ChannelType = ChannelType.TELEGRAM
    subject   : str  = ""
    thread_id : str  = ""


# ── Estilo de respuesta por canal ─────────────────────────────
# Se inyecta en el system prompt de Groq según el canal del mensaje.
# Permite que el mismo core genere respuestas adaptadas sin lógica especial.

CHANNEL_STYLE: dict[str, str] = {
    ChannelType.TELEGRAM: (
        "Responde de forma concisa y amigable. Máximo 3-4 oraciones o una lista "
        "corta. Usa emojis con moderación. Evita secciones y headers."
    ),
    ChannelType.WHATSAPP: (
        "Responde de forma muy corta y directa. Máximo 2-3 oraciones. "
        "Sin markdown. Sin asteriscos ni guiones. Solo texto plano."
    ),
    ChannelType.SLACK: (
        "Responde de forma ejecutiva y clara. Puedes usar listas cortas. "
        "Sin emojis. Tono profesional y directo."
    ),
    ChannelType.EMAIL: (
        "Responde de forma detallada y completa. Usa estructura clara con "
        "secciones si el tema lo amerita. Tono profesional. Puedes ser extenso "
        "— el usuario lee correos con más detenimiento que mensajes instantáneos. "
        "Incluye contexto suficiente para que la respuesta sea autónoma."
    ),
}


def get_channel_style(channel: ChannelType) -> str:
    """Devuelve la instrucción de estilo para el canal dado."""
    return CHANNEL_STYLE.get(channel, CHANNEL_STYLE[ChannelType.TELEGRAM])
