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
[![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3_70B-F55036?style=flat-square)](https://groq.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Railway-336791?style=flat-square&logo=postgresql&logoColor=white)](https://railway.app)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://railway.app)
[![Version](https://img.shields.io/badge/Version-1.2.1-27AE60?style=flat-square)](AGENTS.md)
[![Lines](https://img.shields.io/badge/Code-4%2C760_líneas-8E44AD?style=flat-square)](.)

<br/>

*Memoria vertical · Skills evolutivas · Google Workspace · Multi-usuario · Timezone DST-aware*

<br/>

</div>

---

## ¿Qué es Monday?

Monday es un asistente personal que vive en Telegram. No es un chatbot genérico — conoce tu trabajo, tus proyectos, tu equipo y tus metas. Aprende de cada conversación, se integra con tu Google Workspace y se adapta a tu ritmo de vida.

Está diseñado para ser **multi-usuario desde el inicio**: cada persona tiene su propia memoria, sus propias skills y su propia conexión a Google. Un solo despliegue sirve a todos tus usuarios.

```
Usuario: "agenda una cita con mi dentista mañana a las 5:30"
Monday:  ✅ Evento creado: Cita dentista — Viernes 6 Mar, 5:30 PM PST
         [Agendado en tu Google Calendar]
```

```
Usuario: "¿qué tengo pendiente esta semana?"
Monday:  Tienes 3 cosas prioritarias esta semana:
         1. Presentación con el cliente el miércoles → ¿la preparamos juntos?
         2. Revisión del sprint (tu meta de la semana)
         3. Llamada con el equipo de marketing el jueves
```

---

## Características

### 🧠 Memoria vertical por categorías

Monday no olvida. Organiza lo que sabes en 9 categorías estructuradas:

| Categoría | Qué guarda |
|-----------|-----------|
| `identidad` | Nombre, ciudad, idioma, profesión |
| `trabajo` | Empresa, rol, equipo, sector |
| `proyectos` | Lista de proyectos activos con estado |
| `relaciones` | Personas clave de tu día a día |
| `metas` | Objetivos de semana, mes y año |
| `preferencias` | Tono, formato, estilo de comunicación |
| `ritmo` | Horarios, zona horaria, días libres |
| `vida_personal` | Familia, hobbies, contexto personal |
| `hechos` | Datos sueltos aprendidos en conversación |

Cuando detecta algo nuevo en la conversación, lo guarda automáticamente:
```
Monday aprende → [FACT: Juan cambia de empresa en abril] → memoria actualizada
```

### ⚡ Skills personalizadas y evolutivas

Las skills son modos de operación que el asistente activa según el contexto. Lo que las hace únicas: **se personalizan con tu contexto real al activarlas y evolucionan automáticamente cuando aprendes algo nuevo**.

**Skills incluidas:**

| Skill | Trigger | Qué hace |
|-------|---------|---------|
| 📧 Correo formal | Contexto correo | Redacta correos con tu tono, empresa y contactos reales |
| 📝 Acta de reunión | Manual | Estructura notas de reunión con tus proyectos como contexto |
| ✅ Gestor de tareas | Contexto trabajo | Clasifica tareas por urgencia considerando tus metas activas |
| 🌅 Briefing matutino | Mañana | Resumen diario personalizado a tu hora y zona horaria |
| 🚨 Filtro de urgentes | Heartbeat | Detecta reuniones próximas y correos críticos |
| 🎯 Metas semanales | Mañana lunes | Seguimiento de objetivos conectado a tu ritmo |

**También puedes crear las tuyas:**
```
/nueva_skill ayúdame a preparar reportes ejecutivos para mi jefe
```

### 🔗 Google Workspace integrado

Conecta tu cuenta de Google una vez y Monday opera directamente sobre ella:

- **📅 Calendar** — leer, crear y eliminar eventos. Respeta tu timezone y DST.
- **📧 Gmail** — leer, filtrar y enviar correos
- **📄 Docs** — crear documentos, leer contenido, agregar texto
- **📊 Sheets** — crear hojas, leer rangos, agregar filas
- **💾 Drive** — listar y buscar archivos

Cada usuario conecta **su propia cuenta** — Monday nunca mezcla credenciales.

### 🌍 Timezone DST-aware por usuario

Cada usuario tiene su timezone guardada. Monday la auto-detecta desde tu Google Calendar si no la configuras. Respeta el horario de verano (DST) automáticamente.

```
/mi_zona Los Angeles      → America/Los_Angeles (-08:00 / -07:00 DST)
/mi_zona Europe/Madrid    → Europe/Madrid (+01:00 / +02:00 DST)
```

### 💾 Memoria extendida en Google Doc

Además de la base de datos, Monday mantiene un Google Doc de memoria personal que puedes leer y editar directamente. Sincronización bidireccional:

```
DB ←→ Google Doc "Memoria — {tu nombre}"
```

### 🔄 Reprovisión automática versionada

Cuando el sistema se actualiza, Monday notifica a cada usuario con el changelog exacto de qué cambió. **Sin perder ningún dato personal.**

```
🔄 Actualicé mis capacidades:
v1.2.0 — Skills personalizadas y evolutivas
  • Las skills ahora se personalizan con tu contexto al activarlas
  • Evolución automática cuando aprendes algo nuevo
  • /nueva_skill para crear skills propias
Tu memoria personal está intacta ✅
```

### ⏰ Ritmo automático

Jobs automáticos sin configuración extra:

| Momento | Qué hace |
|---------|---------|
| Cada 30 min | Heartbeat — revisa reuniones próximas y alerts |
| Lun-Vie mañana | Briefing personalizado a tu hora local |
| Lunes | Resumen semanal + metas de la semana |
| Viernes | Cierre de semana |
| 2am | Sync silencioso de memoria al Google Doc |
| Domingo | Reprovisión de backup |

---

## Comandos

### Esenciales
| Comando | Descripción |
|---------|-------------|
| `/start` | Inicia el onboarding o saluda si ya te conoce |
| `/ayuda` | Lista todos los comandos |
| `/estado` | Resumen de tu configuración actual |
| `/memoria` | Ver tu memoria guardada por categorías |
| `/olvidar` | Borrar una categoría o toda la memoria |

### Google Workspace
| Comando | Descripción |
|---------|-------------|
| `/conectar_google` | Conecta tu cuenta de Google (OAuth) |
| `/desconectar_google` | Revoca el acceso a tu cuenta |
| `/mi_doc` | Ver tu Google Doc de memoria |
| `/sincronizar` | Sync manual Doc → DB |

### Skills
| Comando | Descripción |
|---------|-------------|
| `/skills` | Ver catálogo de skills disponibles |
| `/mis_skills` | Ver tus skills activas y su estado |
| `/activar_skill [nombre]` | Activar una skill (se personaliza al instante) |
| `/desactivar_skill [nombre]` | Desactivar una skill |
| `/nueva_skill [descripción]` | Crear una skill personalizada |
| `/evolucion [skill]` | Actualizar una skill con tu memoria actual |

### Personalización
| Comando | Descripción |
|---------|-------------|
| `/mi_asistente` | Ver/cambiar nombre, tono y trato del asistente |
| `/mi_zona` | Ver/cambiar tu timezone |

### Sistema
| Comando | Descripción |
|---------|-------------|
| `/version` | Ver versión actual del bot |
| `/heartbeat` | Forzar heartbeat manual |

---

## Onboarding

El primer arranque guía al usuario en 9 preguntas. Groq extrae los datos automáticamente — el usuario puede responder en lenguaje natural.

```
1. 👤 Nombre y ubicación
2. 💼 Trabajo y empresa
3. 🚀 Proyectos activos
4. 👥 Personas clave
5. 🎯 Metas de la semana
6. ⏰ Ritmo y horarios
7. 💬 Preferencias de comunicación
8. 🔔 Qué eventos monitorear
9. 🤖 Cómo quieres que sea tu asistente
```

---

## Arquitectura

```
monday-bot/
├── bot.py                  # Entrada. Telegram + Groq + acciones Google
├── memory.py               # Única interfaz con PostgreSQL
├── provisioning.py         # Versioning, system prompt, catálogo de skills
├── identity.py             # Identidad Luma + personalización por usuario
├── skills.py               # Motor de skills: render, evolución, custom
├── onboarding.py           # 9 pasos con extracción inteligente
├── scheduler.py            # Heartbeat, briefing, ritmo semanal
├── conversation_context.py # Detección de contexto + memoria enfocada
├── tz_utils.py             # Timezones DST-aware por usuario
├── google_auth.py          # OAuth 2.0 por usuario
├── oauth_server.py         # Callback server aiohttp
├── google_services.py      # APIs Google: Calendar, Gmail, Docs, Sheets, Drive
├── workspace_memory.py     # Sync bidireccional con Google Doc
├── AGENTS.md               # Instrucciones completas para agentes autónomos
└── GUIA_REDEPLOY.md        # Guía de deploys seguros
```

### Flujo de un mensaje

```
Mensaje del usuario
      ↓
detect_context()          ← ¿es sobre trabajo, correo, calendario...?
      ↓
build_system_prompt()     ← identidad + memoria vertical + skills activas
      ↓
call_groq()               ← LLaMA 3.3 70B
      ↓
parse [ACTION] / [FACT]   ← ejecutar Google API / guardar en memoria
      ↓
Respuesta al usuario
```

---

## Deploy

### Requisitos

- Cuenta en [Railway](https://railway.app)
- Bot de Telegram ([@BotFather](https://t.me/BotFather))
- API Key de [Groq](https://console.groq.com)
- Google Cloud Project con OAuth 2.0 configurado

### Variables de entorno

```env
TELEGRAM_TOKEN=
GROQ_API_KEY=
DATABASE_URL=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
RAILWAY_PUBLIC_URL=https://tu-proyecto.up.railway.app
CALLBACK_URL=https://tu-proyecto.up.railway.app/oauth/callback
PORT=8080
```

### Pasos

```bash
# 1. Clonar el repo
git clone https://github.com/tu-usuario/monday-bot
cd monday-bot

# 2. Crear proyecto en Railway y agregar PostgreSQL
# (desde railway.app o Railway CLI)

# 3. Configurar variables de entorno en Railway

# 4. Deploy
git push origin main
# Railway detecta el push y despliega automáticamente

# 5. La DB se inicializa sola al primer arranque
```

### Google OAuth — configuración

1. Crear proyecto en [Google Cloud Console](https://console.cloud.google.com)
2. Habilitar APIs: Calendar, Gmail, Drive, Docs, Sheets
3. Crear credenciales OAuth 2.0 (tipo: Web application)
4. Agregar URI de redirección: `https://tu-proyecto.up.railway.app/oauth/callback`
5. Agregar tu email como usuario de prueba (mientras la app no esté verificada)

---

## Para agentes autónomos

Este proyecto incluye [`AGENTS.md`](AGENTS.md) — 854 líneas de instrucciones estructuradas para que cualquier LLM pueda operar el proyecto de forma autónoma y segura.

Cubre: arquitectura completa, schema de DB, flujo de mensajes, sistema de skills, reprovisión, timezones, cómo hacer cada tipo de cambio, y zonas protegidas que ningún agente debe tocar sin autorización explícita.

```
Para cambiar el comportamiento del asistente:
  → provisioning.py (SYSTEM_PROMPT) + bump MINOR + CHANGELOG + deploy

Para agregar una skill:
  → provisioning.py (SKILLS_CATALOG) + bump MINOR + deploy

Para agregar un comando:
  → bot.py (función cmd_*) + registrar en main() + deploy
```

---

## Stack

| Componente | Tecnología |
|-----------|-----------|
| Lenguaje | Python 3.12 |
| IA | Groq — LLaMA 3.3 70B |
| Telegram | python-telegram-bot 21.5 |
| Base de datos | PostgreSQL (Railway) |
| HTTP | httpx 0.27.2 |
| Scheduler | APScheduler 3.10.4 |
| OAuth server | aiohttp 3.9.5 |
| Timezones | zoneinfo (stdlib) |
| Deploy | Railway PaaS |

---

## Seguridad

- Los tokens de Google se guardan cifrados por usuario en PostgreSQL — nunca se comparten entre usuarios
- Cada llamada a Groq usa el contexto exclusivo del usuario — sin filtraciones entre sesiones
- OAuth 2.0 estándar con refresh automático de tokens
- Las credenciales nunca se escriben en código — siempre via variables de entorno
- Las zonas protegidas del sistema están documentadas explícitamente en `AGENTS.md`

---

<div align="center">

**Monday v1.2.1** · Python 3.12 · Groq LLaMA 3.3 70B · Railway

*Construido con ♥ para ser el asistente que realmente conoce a su usuario*

</div>
