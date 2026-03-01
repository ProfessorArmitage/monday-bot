"""
bot.py — Asistente personal en Telegram con memoria.

Stack:
  - python-telegram-bot  →  conexión con Telegram
  - Gemini REST API      →  IA gratis, sin SDK (compatible con Python 3.14+)
  - httpx                →  cliente HTTP async para llamar a Gemini
  - memory.py            →  memoria persistente por usuario

Flujo:
  Usuario escribe → bot recibe → agrega contexto/memoria
  → llama a Gemini REST → extrae nuevos hechos → responde al usuario
"""

import os
import re
import logging
import httpx
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import memory

# ── Configuración ────────────────────────────────────────────
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise ValueError("Falta TELEGRAM_TOKEN o GROQ_API_KEY en el archivo .env")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Prompt base del asistente ────────────────────────────────
BASE_SYSTEM_PROMPT = """Eres un asistente personal amigable, empático e inteligente.

Tu objetivo principal es conocer bien al usuario y personalizar cada respuesta según lo que sabes de él.

Reglas importantes:
1. Responde siempre en el idioma que use el usuario.
2. Si el usuario menciona algo personal (nombre, trabajo, gustos, horarios, objetivos, etc.),
   recuérdalo y úsalo naturalmente en futuras respuestas.
3. Haz preguntas cortas y naturales para conocer mejor al usuario, pero sin ser invasivo.
4. Sé conciso: respuestas cortas y útiles, no párrafos interminables.
5. Tienes memoria de las conversaciones anteriores, así que nunca preguntes algo que ya te dijeron.

Al final de tu respuesta, si detectaste un nuevo hecho sobre el usuario,
agrégalo en una línea especial con el formato:
[FACT: descripción breve del hecho]

Ejemplos de [FACT]:
[FACT: Se llama Carlos]
[FACT: Trabaja como desarrollador web]
[FACT: Prefiere respuestas cortas]
[FACT: Tiene un perro llamado Max]

Solo agrega [FACT] si aprendiste algo nuevo y concreto.
El usuario NO verá estas líneas [FACT], son solo para tu memoria interna.
"""


# ── Llamada a la API REST de Groq ───────────────────────────
async def call_gemini(system_prompt: str, history: list, user_text: str) -> str:
    """Llama a Groq via REST con httpx. Gratis, sin cuotas raras, compatible con Python 3.14+."""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 512,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GROQ_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"].strip()


# ── Función principal: procesar un mensaje ───────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id   = update.effective_user.id
    user_name = update.effective_user.first_name or "Usuario"
    user_text = update.message.text

    logger.info(f"Mensaje de {user_name} ({user_id}): {user_text}")

    # 1. Construir system prompt con memoria del usuario
    system_prompt = memory.build_system_prompt(user_id, BASE_SYSTEM_PROMPT)

    # 2. Obtener historial de conversación
    hist = memory.get_history(user_id)

    # 3. Mostrar "escribiendo..." mientras se procesa
    await update.message.chat.send_action("typing")

    # 4. Llamar a Gemini via REST
    try:
        full_reply = await call_gemini(system_prompt, hist, user_text)
    except httpx.HTTPStatusError as e:
        logger.error(f"Error HTTP de Groq: {e.response.status_code} — {e.response.text}")
        await update.message.reply_text(
            "Ups, Groq devolvió un error. Verifica que tu GROQ_API_KEY sea correcta. 🙏"
        )
        return
    except Exception as e:
        logger.error(f"Error llamando a Groq: {e}")
        await update.message.reply_text(
            "Ups, hubo un problema conectándome. Intenta en un momento 🙏"
        )
        return

    # 5. Extraer [FACT]s antes de enviar la respuesta al usuario
    facts_found = re.findall(r'\[FACT:\s*(.+?)\]', full_reply)
    for fact in facts_found:
        memory.add_fact(user_id, fact.strip())
        logger.info(f"Nuevo hecho guardado para {user_id}: {fact.strip()}")

    # 6. Limpiar la respuesta (quitar líneas [FACT] internas)
    clean_reply = re.sub(r'\[FACT:.*?\]\n?', '', full_reply).strip()

    # 7. Guardar el intercambio en el historial
    memory.add_message(user_id, "user", user_text)
    memory.add_message(user_id, "assistant", clean_reply)

    # 8. Responder al usuario
    await update.message.reply_text(clean_reply)


# ── Comandos ─────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "!"
    await update.message.reply_text(
        f"¡Hola {name}! 👋 Soy tu asistente personal.\n\n"
        "Cuéntame sobre ti — ¿en qué puedo ayudarte hoy?\n\n"
        "Comandos útiles:\n"
        "  /memoria — ver lo que sé de ti\n"
        "  /olvidar — borrar toda mi memoria de ti\n"
        "  /ayuda   — ver todos los comandos"
    )


async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    facts   = memory.get_facts(user_id)

    if not facts:
        await update.message.reply_text(
            "Todavía no sé mucho sobre ti. ¡Cuéntame más! 😊"
        )
    else:
        facts_list = "\n".join(f"• {f}" for f in facts)
        await update.message.reply_text(
            f"Esto es lo que sé sobre ti:\n\n{facts_list}"
        )


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    memory.clear_memory(user_id)
    await update.message.reply_text(
        "Listo, borré toda mi memoria sobre ti. ¡Empezamos de cero! 🧹"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Comandos disponibles:\n\n"
        "/start    — iniciar el asistente\n"
        "/memoria  — ver lo que sé de ti\n"
        "/olvidar  — borrar mi memoria\n"
        "/ayuda    — este mensaje\n\n"
        "Simplemente escríbeme cualquier cosa para conversar 💬"
    )


# ── Arrancar el bot ───────────────────────────────────────────
# Python 3.14 es más estricto con asyncio: hay que crear el event loop
# explícitamente en lugar de depender de get_event_loop().
import asyncio

async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("memoria", cmd_memory))
    app.add_handler(CommandHandler("olvidar", cmd_forget))
    app.add_handler(CommandHandler("ayuda",   cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("✅ Bot iniciado. Esperando mensajes...")

    async with app:
        await app.start()
        await app.updater.start_polling()
        # Mantener el bot corriendo hasta Ctrl+C
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
