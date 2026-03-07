"""
bot.py — Punto de entrada de Monday Bot.

Responsabilidades de este archivo:
  - Leer variables de entorno
  - Construir la Application de Telegram
  - Registrar el adapter activo (Telegram)
  - Iniciar el servidor web (OAuth + health + webhooks futuros)
  - Arrancar el scheduler
  - Lanzar la reprovisión al inicio

ARQUITECTURA MULTI-CANAL:
  La lógica de negocio vive en channel_router.py.
  Cada canal tiene su propio adapter:

    adapter_telegram.py  <- ACTIVO
    adapter_whatsapp.py  <- stub (activar cuando se configuren credenciales de Meta)
    adapter_slack.py     <- stub (activar cuando se configure la Slack App)
    adapter_email.py     <- stub (activar cuando se configure SendGrid)

  Para activar un canal nuevo:
    1. Configurar las variables de entorno del canal
    2. Descomentar la sección correspondiente en main()
    3. No tocar channel_router.py ni memory.py

CAPA DE TIPOS:
  channel_types.py  <- InboundMessage, OutboundMessage, ChannelType, CHANNEL_STYLE
"""

import os
import asyncio
import logging

from aiohttp import web
from telegram.ext import ApplicationBuilder

import memory
import provisioning
import adapter_telegram
# Canal future (descomentar cuando esten listos):
# import adapter_whatsapp
# import adapter_slack
# import adapter_email
from scheduler import start_scheduler, init_scheduler
import channel_router

# Configuracion
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
RAILWAY_PUBLIC_URL = os.getenv("RAILWAY_PUBLIC_URL", "http://localhost:8080")
PORT               = int(os.getenv("PORT", 8080))

if not TELEGRAM_TOKEN:
    raise ValueError("Falta TELEGRAM_TOKEN en las variables de entorno")
if not os.getenv("GROQ_API_KEY"):
    raise ValueError("Falta GROQ_API_KEY en las variables de entorno")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _start_web_server(telegram_app) -> None:
    """
    Inicia el servidor aiohttp con todas las rutas activas.

    Rutas permanentes:
      GET  /health           -> health check de Railway
      GET  /oauth/callback   -> callback de Google OAuth2

    Rutas de canales futuros (se agregan al descomentar su adapter):
      POST /webhook/whatsapp -> adapter_whatsapp
      POST /webhook/slack    -> adapter_slack
      POST /webhook/email    -> adapter_email
    """
    web_app = web.Application()

    # Rutas del adapter de Telegram (OAuth vive aqui porque necesita el bot)
    web_app.router.add_get("/oauth/callback", adapter_telegram.oauth_callback)
    web_app.router.add_get("/health",         lambda r: web.Response(text="OK"))

    # Canales futuros — descomentar cuando se activen:
    # adapter_whatsapp.register_routes(web_app)
    # adapter_slack.register_routes(web_app)
    # adapter_email.register_routes(web_app)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Servidor web iniciado en puerto {PORT}")


async def main() -> None:
    # 1. Construir la Application de Telegram
    telegram_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # 2. Registrar todos los handlers de Telegram
    adapter_telegram.register_handlers(telegram_app)

    # 3. Iniciar servidor web (OAuth + health + webhooks futuros)
    await _start_web_server(telegram_app)

    # 4. Arrancar scheduler
    init_scheduler(telegram_app.bot, channel_router.call_groq)
    start_scheduler()

    logger.info("Monday Bot v%s iniciado", provisioning.MANIFEST_VERSION)

    async with telegram_app:
        await telegram_app.start()

        # 5. Reprovisioning al arrancar
        asyncio.create_task(
            provisioning.run_reprovisioning(memory, telegram_app.bot)
        )

        await telegram_app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
