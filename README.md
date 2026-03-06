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
[![Version](https://img.shields.io/badge/Version-1.7.0-27AE60?style=flat-square)](AGENTS.md)
[![Lines](https://img.shields.io/badge/Code-~8%2C000_líneas-8E44AD?style=flat-square)](.))

<br/>

*Memoria vertical · Skills evolutivas · Google Workspace · Mensajes de voz · Multi-usuario · Timezone DST-aware*

<br/>

</div>

---

## ¿Qué es Monday?

Monday es un asistente personal que vive en Telegram. No es un chatbot genérico — conoce tu trabajo, tus proyectos, tu equipo y tus metas. Aprende de cada conversación, se integra con tu Google Workspace, responde mensajes de voz y se adapta a tu ritmo de vida.

Está diseñado para ser **multi-usuario desde el inicio**: cada persona tiene su propia memoria, sus propias skills y su propia conexión a Google. Un solo despliegue sirve a todos tus usuarios.

```
Usuario: "agenda una cita con mi dentista mañana a las 5:30"
Monday:  ✅ Evento creado: Cita dentista — Viernes 6 Mar, 5:30 PM
         [Agendado en tu Google Calendar]
```

```
Usuario: [mensaje de voz] "¿qué tengo pendiente esta semana?"
Monday:  Tienes 3 cosas prioritarias esta semana:
         1. Presentación con el cliente el miércoles
         2. Revisión del sprint (tu meta de la semana)
         3. Llamada con el equipo de marketing el jueves
```

---

## Características principales

### 🧠 Memoria vertical por categorías

Monday no olvida. Organiza lo que aprende en 9 categorías estructuradas persistidas en PostgreSQL:

| Categoría | Qué guarda |
|-----------|------------|
| `identidad` | Nombre, ciudad, idioma, profesión |
| `trabajo` | Empresa, rol, equipo, sector |
| `proyectos` | Lista de proyectos activos con estado |
| `relaciones` | Personas clave del día a día |
| `metas` | Objetivos de semana, mes y año |
| `preferencias` | Tono, formato, estilo de comunicación |
| `ritmo` | Horarios, zona horaria, días libres, DND |
| `vida_personal` | Familia, hobbies, contexto personal |
| `hechos` | Datos sueltos detectados en conversación |

Cuando detecta algo nuevo, lo guarda automáticamente sin interrumpir la conversación:
```
[FACT: Juan cambia de empresa en abril] → memoria actualizada silenciosamente
```

### ⚡ Skills personalizadas y evolutivas

Las skills son modos de operación que se activan según el contexto. Lo que las hace únicas: **se personalizan con el contexto real del usuario al activarlas y evolucionan automáticamente cuando aprenden algo nuevo**.

**6 skills base disponibles para todos:**

| Skill | Descripción |
|-------|-------------|
| 📧 Correo formal | Redactar correos profesionales |
| 📝 Acta de reunión | Convertir notas en actas estructuradas |
| ✅ Gestor de tareas | Organizar y priorizar pendientes |
| 🌅 Briefing matutino | Resumen personalizado cada mañana |
| 🚨 Filtro de urgentes | Alertar solo sobre lo realmente urgente |
| 🎯 Metas semanales | Seguimiento de objetivos cada lunes |

### 🏢 Paquetes de dominio profesional

6 paquetes especializados con 4 skills cada uno (24 skills de dominio en total):

| Dominio | Skills incluidas |
|---------|-----------------|
| ⚖️ **Legal** | Redacción legal, Análisis de riesgo, Seguimiento de casos, Comunicación con clientes |
| 🎬 **Influencer** | Calendario de contenido, Voz de marca, Propuesta de colaboración, Brief de métricas |
| 🏢 **Corporativo** | Resumen ejecutivo, Comunicación con stakeholders, Revisión estratégica, Preparación de juntas |
| 💼 **Ventas** | Seguimiento de prospectos, Propuesta comercial, Revisión de pipeline, Comunicación con clientes |
| 🩺 **Salud** | Notas de consulta, Seguimiento clínico, Comunicación con pacientes, Brief de agenda |
| 📚 **Educación** | Preparación de clases, Seguimiento de alumnos, Creación de material, Comunicación educativa |

### 🔗 Google Workspace integrado

Conexión OAuth2 por usuario — cada quien conecta su propia cuenta:

- **Google Calendar** — leer eventos, crear citas, eliminar eventos
- **Gmail** — leer correos recientes, ver correos completos, enviar emails
- **Google Docs** — crear documentos, leer contenido, buscar archivos
- **Google Drive** — búsqueda de archivos, carpeta Monday automática, backups de memoria

### 🎙️ Mensajes de voz

- **Entrada por voz**: manda un audio y Monday lo transcribe con Whisper (via Groq)
- **Respuesta por voz**: activa `/voz activar` para recibir respuestas en audio (gTTS)
- Providers intercambiables: OpenAI Whisper, ElevenLabs, Google Cloud TTS listos para activar

### 💾 Backup automático de memoria

- Respaldo JSON semanal automático en la carpeta Monday de Google Drive
- Retención de últimos 4 respaldos (~1 mes)
- Export manual con `/exportar_memoria`, restauración con `/importar_memoria`

### 🔔 Notificaciones inteligentes

| Job | Frecuencia | Qué hace |
|-----|-----------|----------|
| Heartbeat | Cada 30 min | Alertas de reuniones próximas + hooks personalizados |
| Briefing matutino | 7–9am (hora local) | Resumen del día con calendario y correos |
| Resumen semanal | Lunes 8am | Vista de la semana que comienza |
| Cierre semanal | Viernes 5pm | Wrap-up de la semana |
| Sincronización | Noche | Sincroniza memoria con Google Doc |
| Reprovisión | Domingos 3am | Actualiza skills y configuración |
| Backup | Domingos 4am | Respaldo de memoria en Drive |

### 🌐 Sistema de reprovisión

Sin necesidad de que el usuario haga nada: cada domingo el bot compara la versión instalada del usuario contra la versión actual y aplica cambios automáticamente — nuevas skills, nuevos dominios, actualizaciones de prompts.

---

## Comandos

### Usuario — Conversación y memoria

| Comando | Descripción |
|---------|-------------|
| `/start` | Inicia el bot. Si es nuevo, arranca el onboarding de 5 pasos |
| `/estado` | Resumen de la memoria actual: proyectos, metas, skills activas |
| `/memoria` | Ver toda la memoria guardada por categoría |
| `/olvidar` | Borra toda la memoria (pide confirmación) |

### Usuario — Google Workspace

| Comando | Descripción |
|---------|-------------|
| `/conectar_google` | Conecta la cuenta de Google via OAuth2 |
| `/desconectar_google` | Desconecta Google y elimina los tokens |
| `/mi_doc` | Enlace al Google Doc de memoria personal |
| `/sincronizar` | Sincroniza manualmente la memoria con el Google Doc |

### Usuario — Skills

| Comando | Descripción |
|---------|-------------|
| `/skills` | Catálogo completo de skills disponibles |
| `/mis_skills` | Skills activas con su contenido personalizado |
| `/activar_skill [nombre]` | Activa una skill del catálogo |
| `/desactivar_skill [nombre]` | Desactiva una skill activa |
| `/nueva_skill [descripción]` | Crea una skill personalizada desde cero |
| `/evolucion [nombre]` | Regenera la personalización de una skill con la memoria actual |

### Usuario — Dominio profesional

| Comando | Descripción |
|---------|-------------|
| `/mi_dominio` | Ver dominio activo + skills del paquete |
| `/mi_dominio [nombre]` | Cambiar de dominio (ej. `/mi_dominio ventas`) |

### Usuario — Preferencias y configuración

| Comando | Descripción |
|---------|-------------|
| `/mi_zona` | Ver o cambiar timezone (ej. `/mi_zona America/Monterrey`) |
| `/mi_asistente` | Ver o cambiar nombre e identidad del asistente |
| `/version` | Versión actual del bot y changelog |
| `/ayuda` | Lista de comandos disponibles |

### Usuario — Voz

| Comando | Descripción |
|---------|-------------|
| `/voz` | Ver estado actual de respuestas por voz |
| `/voz activar` | Activar respuestas en audio |
| `/voz desactivar` | Volver a respuestas en texto (default) |

### Usuario — Modo silencio (DND)

| Comando | Descripción |
|---------|-------------|
| `/dnd` | Ver estado actual del modo silencio |
| `/dnd activar HH:MM HH:MM` | Activar horario sin notificaciones (ej. `22:00 07:00`) |
| `/dnd activar HH:MM HH:MM [dias]` | Con días adicionales (ej. `22:00 07:00 sabado domingo`) |
| `/dnd desactivar` | Desactivar modo silencio |
| `/dnd dias [días]` | Configurar días sin notificaciones |
| `/dnd snooze 1h` | Silenciar por tiempo determinado (30m, 1h, 2h, 3h) |
| `/dnd snooze off` | Cancelar snooze activo |

### Usuario — Backup de memoria

| Comando | Descripción |
|---------|-------------|
| `/exportar_memoria` | Genera respaldo JSON en carpeta Monday de Drive |
| `/importar_memoria` | Restaura memoria desde el respaldo más reciente (pide confirmación) |

### Admin — Semilla de dominio

| Comando | Descripción |
|---------|-------------|
| `/admin seed ver <user_id>` | Ver la seed de dominio actual del usuario |
| `/admin seed <dominio> <user_id> <campo> <valor>` | Configurar campo en domain_extras |
| `/admin seed reset <user_id>` | Reinicializar seed conservando domain_extras |

### Admin — Dominio

| Comando | Descripción |
|---------|-------------|
| `/admin dominio ver <user_id>` | Ver el dominio activo del usuario |
| `/admin dominio set <user_id> <dominio>` | Cambiar dominio e inyectar seed |

### Admin — Memoria

| Comando | Descripción |
|---------|-------------|
| `/admin memoria exportar <user_id>` | Genera backup desde DB y lo sube a Drive |
| `/admin memoria ver_backups <user_id>` | Lista los backups disponibles en Drive |

### Admin — Diagnóstico

| Comando | Descripción |
|---------|-------------|
| `/heartbeat` | Ejecuta el heartbeat manualmente para un usuario |

---

## Stack técnico

| Componente | Tecnología |
|-----------|-----------|
| Plataforma | Telegram Bot API |
| Framework | python-telegram-bot 21.5 |
| IA — Chat | Groq API (LLaMA 3.3 70B Versatile) |
| IA — Voz STT | Groq Whisper Large v3 |
| IA — Voz TTS | gTTS (Google Text-to-Speech) |
| Audio | ffmpeg (conversión MP3→OGG) |
| Base de datos | PostgreSQL (Railway) |
| Scheduler | APScheduler |
| HTTP | httpx (async) |
| Deploy | Railway (Docker) |
| Google OAuth | OAuth 2.0 con refresh automático |

---

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `TELEGRAM_TOKEN` | Token del bot de Telegram |
| `GROQ_API_KEY` | API key de Groq (LLaMA + Whisper) |
| `DATABASE_URL` | URL de PostgreSQL (Railway la inyecta automáticamente) |
| `RAILWAY_PUBLIC_URL` | URL pública del servicio (para el callback de OAuth) |
| `GOOGLE_CLIENT_ID` | Client ID de Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Client Secret de Google OAuth |
| `ADMIN_USER_IDS` | IDs de Telegram separados por coma con acceso a `/admin` |

---

## Instalación y deploy

### Requisitos
- Python 3.12+
- PostgreSQL
- Cuenta en Groq (gratuita)
- Proyecto en Google Cloud con OAuth2 configurado

### Variables mínimas para arrancar
```bash
TELEGRAM_TOKEN=...
GROQ_API_KEY=...
DATABASE_URL=postgresql://...
RAILWAY_PUBLIC_URL=https://tu-servicio.railway.app
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ADMIN_USER_IDS=tu_telegram_id
```

### Deploy en Railway
```bash
git clone https://github.com/ProfessorArmitage/monday-bot
cd monday-bot
# Conectar a Railway y configurar variables de entorno
railway up
```

El `Dockerfile` incluido instala ffmpeg automáticamente. La base de datos se inicializa sola al arrancar.

---

## Arquitectura

```
bot.py                  ← núcleo: handlers, Groq, orquestación
├── memory.py           ← PostgreSQL: CRUD de memoria por categorías
├── onboarding.py       ← flujo de 5 pasos para usuarios nuevos
├── provisioning.py     ← skills catalog, domains, reprovisión automática
├── skills.py           ← motor de skills personalizadas y evolutivas
├── domain_seeds.py     ← memoria pre-sembrada por dominio profesional
├── audio_handler.py    ← STT (Whisper/Groq) + TTS (gTTS) con providers
├── scheduler.py        ← APScheduler: heartbeat, briefing, backup, DND
├── google_auth.py      ← OAuth2 con refresh automático de tokens
├── google_services.py  ← Calendar, Gmail, Docs, Drive
├── workspace_memory.py ← Google Doc como memoria extendida
├── memory_backup.py    ← export/import JSON en Drive
└── tz_utils.py         ← timezone DST-aware + helpers DND
```

---

## Documentación

Para especificaciones completas de arquitectura, decisiones de diseño y guías de extensión, ver [`AGENTS.md`](AGENTS.md).

Para referencia completa de características, comandos y opciones de administración, ver el documento de características incluido en el repositorio.

---

<div align="center">
<sub>Construido con ❤️ · Desplegado en Railway · Impulsado por Groq</sub>
</div>
