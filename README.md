<div align="center">

<br/>

```
███╗   ███╗ ██████╗ ███╗   ██╗██████╗  █████╗ ██╗   ██╗
████╗ ████║██╔═══██╗████╗  ██║██╔══██╗██╔══██╗╚██╗ ██╔╝
██╔████╔██║██║   ██║██╔██╗ ██║██║  ██║███████║ ╚████╔╝ 
██║╚██╔╝██║██║   ██║██║╚██╗██║██║  ██║██╔══██║  ╚██╔╝  
██║ ╚═╝ ██║╚██████╔╝██║ ╚████║██████╔╝██║  ██║   ██║   
╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ╚═╝  ╚═╝   ╚═╝  
```

**Tu asistente personal inteligente en Telegram**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3_70B_+_Whisper-F55036?style=flat-square)](https://groq.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Railway-336791?style=flat-square&logo=postgresql&logoColor=white)](https://railway.app)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://railway.app)
[![Version](https://img.shields.io/badge/Version-1.9.0-27AE60?style=flat-square)](AGENTS.md)
[![Lines](https://img.shields.io/badge/Code-9%2C500%2B_líneas-8E44AD?style=flat-square)](.)
[![Security](https://img.shields.io/badge/Security-Fernet_%2B_Rate_Limiting-E74C3C?style=flat-square)](security.py)

<br/>

*Memoria vertical · Skills evolutivas · Google Workspace · Voz · Multi-canal ready · DST-aware · Seguridad end-to-end*

<br/>

</div>

---

## ¿Qué es Monday?

Monday es un asistente personal que vive en Telegram. No es un chatbot genérico — conoce tu trabajo, tus proyectos, tu equipo y tus metas. Aprende de cada conversación, se integra con tu Google Workspace, entiende mensajes de voz y se adapta a tu ritmo de vida.

Diseñado para ser **multi-usuario desde el inicio**: cada persona tiene su propia memoria, skills y conexión a Google. Un solo despliegue sirve a todos.

```
Usuario: "agenda una cita con mi dentista mañana a las 5:30"
Monday:  ✅ Evento creado: Cita dentista — Viernes 7 Mar, 5:30 PM
         [Agendado en tu Google Calendar]
```

```
Usuario: [mensaje de voz] "¿qué tengo pendiente esta semana?"
Monday:  Tienes 3 cosas prioritarias:
         1. Presentación con el cliente el miércoles
         2. Revisión del sprint (tu meta de la semana)
         3. Llamada con el equipo de marketing el jueves
```

---

## Características

### 🧠 Memoria vertical por categorías

Organiza todo lo que aprende en 9 categorías persistidas en PostgreSQL. Detecta y guarda información nueva automáticamente sin interrumpir la conversación.

| Categoría | Contenido |
|-----------|-----------|
| `identidad` | Nombre, ciudad, idioma, profesión |
| `trabajo` | Empresa, rol, equipo, sector, herramientas |
| `proyectos` | Proyectos activos con estado y deadlines |
| `relaciones` | Personas clave con contexto de la relación |
| `metas` | Objetivos de semana, mes y año |
| `preferencias` | Tono, formato, respuesta en voz |
| `ritmo` | Horarios, timezone, días libres, DND |
| `vida_personal` | Familia, hobbies, contexto personal |
| `hechos` | Datos detectados automáticamente en conversación |

### ⚡ Skills personalizadas y evolutivas

Las skills se personalizan con el contexto real del usuario al activarlas y evolucionan automáticamente cuando aprenden algo nuevo.

**6 skills base** disponibles para todos los usuarios. **24 skills adicionales** en 6 paquetes de dominio profesional:

| Dominio | Skills |
|---------|--------|
| ⚖️ **Legal** | Redacción legal · Análisis de riesgo · Seguimiento de casos · Comunicación con clientes |
| 🎬 **Influencer** | Calendario de contenido · Voz de marca · Propuesta de colaboración · Brief de métricas |
| 🏢 **Corporativo** | Resumen ejecutivo · Comunicación con stakeholders · Revisión estratégica · Preparación de juntas |
| 💼 **Ventas** | Seguimiento de prospectos · Propuesta comercial · Revisión de pipeline · Comunicación con clientes |
| 🩺 **Salud** | Notas de consulta · Seguimiento clínico · Comunicación con pacientes · Brief de agenda |
| 📚 **Educación** | Preparación de clases · Seguimiento de alumnos · Creación de material · Comunicación educativa |

### 🔗 Google Workspace integrado

OAuth2 por usuario — cada quien conecta su propia cuenta:

- **Google Calendar** — leer, crear y eliminar eventos
- **Gmail** — leer correos, ver completos, enviar
- **Google Docs** — crear, leer y buscar documentos
- **Google Drive** — búsqueda de archivos, carpeta Monday, backups de memoria

### 🎙️ Mensajes de voz

- **Entrada**: manda un audio y Monday lo transcribe (Whisper vía Groq)
- **Salida**: activa `/voz activar` para recibir respuestas en audio (gTTS)
- Providers intercambiables en `audio_handler.py`: OpenAI Whisper, ElevenLabs listos para activar

### 💾 Backup automático de memoria

Respaldo JSON semanal en la carpeta **Monday — Asistente Personal** del Drive del usuario. Retención de 4 semanas. Export manual con `/exportar_memoria`, restauración con `/importar_memoria`.

### 🔕 Modo silencio (DND)

Bloquea notificaciones proactivas por horario, por días de la semana, o con snooze temporal (30m–12h). Las respuestas a mensajes directos nunca se bloquean.

### 🔔 Notificaciones programadas

| Job | Frecuencia | Descripción |
|-----|-----------|-------------|
| 💓 Heartbeat | Cada 30 min | Alertas de reuniones próximas |
| 🌅 Briefing matutino | 7–9am hora local | Agenda del día + correos relevantes |
| 📅 Resumen semanal | Lunes 8am | Vista de la semana que comienza |
| 🎉 Cierre semanal | Viernes 5pm | Wrap-up + hechos aprendidos |
| 🌙 Sincronización | Cada noche | Memoria → Google Doc |
| 🔄 Reprovisión | Domingos 3am | Actualiza skills y configuración |
| 💾 Backup | Domingos 4am | Respaldo en Drive (retención 4 semanas) |

---

## Arquitectura multi-canal

A partir de v1.8.0, el bot usa una arquitectura de capas que separa completamente el canal de comunicación de la lógica de negocio.

```
┌─────────────────────────────────────────────────────────────┐
│  ADAPTERS DE CANAL                                          │
│  adapter_telegram.py  ← ACTIVO                              │
│  adapter_whatsapp.py  ← stub listo (Meta Cloud API)         │
│  adapter_slack.py     ← stub listo (Slack Bolt)             │
│  adapter_email.py     ← stub listo (SendGrid Inbound)       │
│                                                             │
│  Cada adapter convierte mensajes nativos → InboundMessage   │
└────────────────────────┬────────────────────────────────────┘
                         │ InboundMessage normalizado
┌────────────────────────▼────────────────────────────────────┐
│  CORE ENGINE  (channel_router.py)                           │
│  100% agnóstico al canal                                    │
│  Memoria · Skills · Groq · Google · Facts · DND             │
│  Recibe InboundMessage, devuelve texto vía send_fn()        │
└────────────────────────┬────────────────────────────────────┘
                         │ respuesta adaptada al canal
┌────────────────────────▼────────────────────────────────────┐
│  ESTILO POR CANAL  (channel_types.py → CHANNEL_STYLE)       │
│  Telegram / WhatsApp  → conciso, emojis, máx 3-4 oraciones  │
│  Slack                → ejecutivo, sin emojis               │
│  Email                → detallado, estructurado, extenso    │
└─────────────────────────────────────────────────────────────┘
```

**Para agregar un canal nuevo:** crear `adapter_<canal>.py`, construir `InboundMessage`, registrar las rutas en `bot.py`. El core engine no se toca.

**Identidad cross-canal:** tabla `channel_identities` en PostgreSQL. Un usuario puede vincular su cuenta de Telegram con WhatsApp, Slack o email — comparten la misma memoria, skills y configuración.

```sql
channel_identities
  monday_id   → FK a users.user_id
  channel     → 'telegram' | 'whatsapp' | 'slack' | 'email'
  channel_id  → ID del usuario en ese canal
  verified_at → timestamp de vinculación
  UNIQUE(channel, channel_id)
```

---


---

## Seguridad

A partir de v1.9.0 todas las capas del bot tienen protección activa. La lógica está centralizada en `security.py`.

### Cifrado en reposo

Los tokens OAuth de Google se cifran con **Fernet** (AES-128-CBC + HMAC-SHA256) antes de persistirse en PostgreSQL. Si alguien accede directamente a la base de datos, los tokens son ilegibles sin la `ENCRYPTION_KEY`.

- Compatibilidad hacia atrás: tokens existentes (sin cifrar) se leen correctamente y se recifran en el siguiente refresh automático.
- Clave generada una sola vez, guardada en Railway Variables. Si se pierde, los usuarios deben reconectar su cuenta de Google.

### SSL en tránsito

La conexión a PostgreSQL fuerza `sslmode=require` — el tráfico entre el bot y la base de datos siempre viaja cifrado, incluso dentro de la infraestructura de Railway.

### Rate limiting por usuario

Ventana deslizante en memoria — sin dependencias externas.

| Parámetro | Default | Variable de entorno |
|-----------|---------|---------------------|
| Mensajes por ventana | 20 | `RATE_LIMIT_MESSAGES` |
| Ventana de tiempo | 60 s | `RATE_LIMIT_WINDOW` |
| Bloqueo tras exceder | 300 s | `RATE_LIMIT_COOLDOWN` |
| Máx. audios por ventana | 10 | `RATE_LIMIT_VOICE_MAX` |
| Longitud máx. de mensaje | 4 000 chars | `MAX_MESSAGE_LENGTH` |
| Tamaño máx. de audio | 10 MB | `MAX_VOICE_SIZE_MB` |

El estado del rate limiter se puede revisar y reiniciar con `/rate_status <user_id>` y `/rate_reset <user_id>` (requiere `ADMIN_USER_IDS`).

### OAuth anti-CSRF

El `state` del flujo OAuth 2.0 ya no expone el `user_id` directamente. Se genera un token aleatorio de 32 bytes con TTL de 10 minutos, de un solo uso. El callback lo valida antes de intercambiar el código con Google.

### Reconexión automática de Google

Cuando el token OAuth expira o es revocado (por ejemplo, tras meses sin uso o al cambiar permisos en la cuenta), el bot detecta el error HTTP 400/401, limpia el token inválido de la base de datos y envía al usuario instrucciones claras paso a paso en lugar de un error técnico.

### Audit log de administración

Todas las acciones del comando `/admin` se registran en Railway con el formato:

```
AUDIT | admin=<id> | action=<acción> | target=<id> | ok=True ✅
```

Filtrable en Railway con: `railway logs | grep AUDIT`

### Validación al arrancar

El bot verifica su configuración de seguridad al iniciar y emite advertencias en los logs si detecta configuración insegura (por ejemplo, `ENCRYPTION_KEY` ausente o `ADMIN_USER_IDS` vacío). No detiene el servicio — permite deploys graduales.

## Comandos disponibles

### Usuario

| Comando | Descripción |
|---------|-------------|
| `/start` | Onboarding de 5 pasos para usuarios nuevos |
| `/estado` | Resumen de memoria, proyectos y skills activas |
| `/memoria` | Ver toda la memoria por categoría |
| `/olvidar` | Borrar toda la memoria (pide confirmación) |
| `/conectar_google` | Conectar cuenta Google via OAuth2 |
| `/desconectar_google` | Desconectar Google y eliminar tokens |
| `/mi_doc` | Enlace al Google Doc de memoria personal |
| `/sincronizar` | Sincronizar memoria con Google Doc |
| `/skills` | Catálogo de skills disponibles |
| `/mis_skills` | Skills activas con contenido personalizado |
| `/activar_skill [nombre]` | Activar una skill del catálogo |
| `/desactivar_skill [nombre]` | Desactivar una skill activa |
| `/nueva_skill [descripción]` | Crear skill personalizada desde cero |
| `/evolucion [nombre]` | Regenerar personalización con memoria actual |
| `/mi_dominio` | Ver o cambiar el paquete de dominio profesional |
| `/mi_zona [tz]` | Ver o cambiar timezone (formato IANA) |
| `/mi_asistente` | Ver o cambiar identidad del asistente |
| `/exportar_memoria` | Respaldo JSON en Google Drive |
| `/importar_memoria` | Restaurar desde el respaldo más reciente |
| `/voz [activar\|desactivar]` | Respuestas en audio (default: texto) |
| `/dnd [config]` | Configurar modo silencio y snooze |
| `/version` | Versión actual y changelog |
| `/ayuda` | Lista de comandos |

### Admin (`ADMIN_USER_IDS`)

| Comando | Descripción |
|---------|-------------|
| `/admin seed ver <id>` | Ver semilla de dominio de un usuario |
| `/admin seed <dominio> <id> <campo> <valor>` | Configurar domain_extras |
| `/admin seed reset <id>` | Reinicializar semilla |
| `/admin dominio ver <id>` | Ver dominio activo de un usuario |
| `/admin dominio set <id> <dominio>` | Cambiar dominio e inyectar semilla |
| `/admin memoria exportar <id>` | Generar backup desde DB |
| `/admin memoria ver_backups <id>` | Listar backups disponibles en Drive |
| `/heartbeat` | Ejecutar heartbeat manual |
| `/rate_status <id>` | Ver estado del rate limiter de un usuario |
| `/rate_reset <id>` | Reiniciar rate limiter de un usuario |

---

## Stack técnico

| Componente | Tecnología |
|-----------|-----------|
| Plataforma | Telegram Bot API |
| Framework | python-telegram-bot 21.5 |
| IA — Chat | Groq API · LLaMA 3.3 70B Versatile |
| IA — STT | Groq Whisper Large v3 |
| IA — TTS | gTTS (Google Text-to-Speech) |
| Audio | ffmpeg · MP3 → OGG/OPUS |
| Base de datos | PostgreSQL (Railway) |
| Scheduler | APScheduler |
| HTTP | httpx async |
| Servidor web | aiohttp (OAuth + webhooks) |
| Deploy | Railway · Docker |
| Google OAuth | OAuth 2.0 con refresh automático |

---

## Estructura del proyecto

```
bot.py                    ← entry point (~120 líneas) · solo ensamblaje
channel_types.py          ← InboundMessage · ChannelType · CHANNEL_STYLE
channel_router.py         ← core engine agnóstico · call_groq · process_message
adapter_telegram.py       ← 31 comandos · handlers · OAuth · voz  [ACTIVO]
adapter_whatsapp.py       ← stub · Meta Graph API                  [pendiente]
adapter_slack.py          ← stub · Slack Bolt                      [pendiente]
adapter_email.py          ← stub · SendGrid Inbound                [pendiente]
memory.py                 ← PostgreSQL · 9 categorías · channel_identities
provisioning.py           ← skills catalog · domains · reprovisión automática
scheduler.py              ← APScheduler · heartbeat · briefing · backup · DND
skills.py                 ← motor de skills personalizadas y evolutivas
domain_seeds.py           ← memoria pre-sembrada por dominio profesional
audio_handler.py          ← STT/TTS con providers intercambiables
google_auth.py            ← OAuth2 + refresh automático de tokens
google_services.py        ← Calendar · Gmail · Docs · Drive
workspace_memory.py       ← Google Doc como memoria extendida
memory_backup.py          ← export/import JSON en Drive
onboarding.py             ← flujo de 5 pasos para usuarios nuevos
conversation_context.py   ← detección de contexto de conversación
tz_utils.py               ← timezone DST-aware · helpers DND
identity.py               ← identidad personalizable del asistente
security.py               ← cifrado Fernet · rate limiting · OAuth CSRF · audit log
```

---

## Variables de entorno

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `TELEGRAM_TOKEN` | ✅ | Token del bot de Telegram |
| `GROQ_API_KEY` | ✅ | Chat (LLaMA) + voz (Whisper) |
| `DATABASE_URL` | ✅ | PostgreSQL — Railway la inyecta automáticamente |
| `RAILWAY_PUBLIC_URL` | ✅ | URL pública para el callback de OAuth |
| `GOOGLE_CLIENT_ID` | ✅ | Client ID de Google Cloud |
| `GOOGLE_CLIENT_SECRET` | ✅ | Client Secret de Google Cloud |
| `ADMIN_USER_IDS` | ✅ | Telegram IDs separados por coma con acceso a `/admin` |
| `WHATSAPP_TOKEN` | ⬜ | Para activar adapter de WhatsApp |
| `WHATSAPP_PHONE_ID` | ⬜ | ID del número de WhatsApp Business |
| `SLACK_BOT_TOKEN` | ⬜ | Para activar adapter de Slack |
| `SENDGRID_API_KEY` | ⬜ | Para activar adapter de Email |
| `OPENAI_API_KEY` | ⬜ | Alternativa a Groq para STT/TTS |
| `ELEVENLABS_API_KEY` | ⬜ | TTS premium (voz de alta calidad) |
| `ENCRYPTION_KEY` | ⚠️ | Clave Fernet para cifrar tokens en DB — generar con `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `RATE_LIMIT_MESSAGES` | ⬜ | Máx. mensajes por ventana (default: 20) |
| `RATE_LIMIT_WINDOW` | ⬜ | Ventana en segundos (default: 60) |
| `RATE_LIMIT_COOLDOWN` | ⬜ | Bloqueo en segundos (default: 300) |
| `MAX_MESSAGE_LENGTH` | ⬜ | Longitud máx. de mensaje en chars (default: 4000) |
| `MAX_VOICE_SIZE_MB` | ⬜ | Tamaño máx. de audio en MB (default: 10) |

---

## Deploy en Railway

```bash
git clone https://github.com/ProfessorArmitage/monday-bot
cd monday-bot
# Configurar variables de entorno en Railway dashboard
railway up
```

El `Dockerfile` incluye `ffmpeg`. La base de datos se inicializa sola al arrancar — incluyendo la nueva tabla `channel_identities` si es un despliegue existente.

---

## Documentación adicional

- **`AGENTS.md`** — arquitectura interna, decisiones de diseño, guías de extensión
- **`Monday_Caracteristicas.docx`** — referencia completa de características y comandos

---

<div align="center">
<sub>Construido con ❤️ · Desplegado en Railway · Impulsado por Groq · v1.9.0</sub>
</div>
