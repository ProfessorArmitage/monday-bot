# AGENTS.md — Monday Personal Assistant Bot

> **Para agentes autónomos (Claude, GPT, Gemini, Rovo Dev, etc.)**
> Este archivo es tu fuente primaria de verdad sobre este proyecto.
> Léelo completo antes de modificar cualquier cosa.
> Cuando termines una tarea, actualiza la sección correspondiente si el cambio lo requiere.

---

## Índice

1. [Qué es este proyecto](#1-qué-es-este-proyecto)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Variables de entorno](#3-variables-de-entorno)
4. [Arquitectura de archivos](#4-arquitectura-de-archivos)
5. [Base de datos — schema completo](#5-base-de-datos--schema-completo)
6. [Flujo principal de un mensaje](#6-flujo-principal-de-un-mensaje)
7. [Sistema de memoria vertical](#7-sistema-de-memoria-vertical)
8. [Sistema de skills](#8-sistema-de-skills)
9. [Sistema de identidad](#9-sistema-de-identidad)
10. [Sistema de reprovisión y versioning](#10-sistema-de-reprovisión-y-versioning)
11. [Google Workspace — integración](#11-google-workspace--integración)
12. [Scheduler — jobs automáticos](#12-scheduler--jobs-automáticos)
13. [Comandos Telegram registrados](#13-comandos-telegram-registrados)
14. [Onboarding — 9 pasos](#14-onboarding--9-pasos)
15. [Timezones](#15-timezones)
16. [Cómo hacer cambios seguros](#16-cómo-hacer-cambios-seguros)
17. [⛔ Zonas protegidas — NO tocar sin autorización explícita](#17--zonas-protegidas--no-tocar-sin-autorización-explícita)
18. [Recetas de tareas frecuentes](#18-recetas-de-tareas-frecuentes)
19. [Cómo actualizar este archivo](#19-cómo-actualizar-este-archivo)

---

## 1. Qué es este proyecto

Monday es un asistente personal en Telegram, multi-usuario, desplegado en Railway.
Cada usuario tiene su propia memoria vertical, identidad del asistente, skills personalizadas
y conexión a Google Workspace (Calendar, Gmail, Docs, Sheets, Drive).

**Características únicas frente a otros proyectos similares:**
- Multi-usuario real (N usuarios, OAuth independiente por usuario)
- Skills evolutivas: se personalizan con Groq al activarse y se auto-actualizan cuando el bot aprende hechos nuevos
- Detección de contexto por conversación (6 contextos: trabajo, correo, calendario, documentos, metas, personal)
- Timezone DST-aware con auto-detección desde Google Calendar
- Sistema de reprovisión semántico versionado (los usuarios reciben actualizaciones automáticas sin perder memoria)

**Modelo de IA:** Groq API — LLaMA 3.3 70B (groq-llamá-3.3-70b-versatile)
**Canal:** Telegram únicamente
**Deploy:** Railway PaaS — git push → auto-deploy

---

## 2. Stack tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Lenguaje | Python | 3.12 |
| Telegram | python-telegram-bot | 21.5 |
| HTTP client | httpx | 0.27.2 |
| DB driver | psycopg2-binary | 2.9.9 |
| OAuth server | aiohttp | 3.9.5 |
| Scheduler | apscheduler | 3.10.4 |
| Versioning | packaging | 24.1 |
| Timezones | zoneinfo | stdlib (Python 3.9+) |
| Base de datos | PostgreSQL | Railway managed |
| Deploy | Railway PaaS | — |

**Instalar dependencias:**
```bash
pip install -r requirements.txt
```

**Correr en local:**
```bash
export TELEGRAM_TOKEN=...
export GROQ_API_KEY=...
export DATABASE_URL=...
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export RAILWAY_PUBLIC_URL=https://tu-dominio.up.railway.app
export CALLBACK_URL=https://tu-dominio.up.railway.app/oauth/callback
python bot.py
```

---

## 3. Variables de entorno

Todas requeridas. Sin ninguna de estas el bot no arranca.

| Variable | Dónde se usa | Descripción |
|----------|-------------|-------------|
| `TELEGRAM_TOKEN` | bot.py | Token del bot de Telegram |
| `GROQ_API_KEY` | bot.py | Clave de la API de Groq |
| `DATABASE_URL` | memory.py | Connection string PostgreSQL |
| `GOOGLE_CLIENT_ID` | google_auth.py | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | google_auth.py | OAuth 2.0 client secret |
| `RAILWAY_PUBLIC_URL` | bot.py | URL pública del servidor Railway |
| `CALLBACK_URL` | google_auth.py | URL del callback OAuth (usualmente `RAILWAY_PUBLIC_URL/oauth/callback`) |
| `PORT` | bot.py | Puerto HTTP (default: 8080) |

**⚠️ Regla de seguridad:** Nunca escribir valores de estas variables en código fuente.
Siempre usar `os.getenv("NOMBRE")`. Si un agente detecta una credencial hardcodeada,
debe reemplazarla por `os.getenv()` inmediatamente.

---

## 4. Arquitectura de archivos

```
monday-bot/
├── bot.py                  # Punto de entrada. Telegram handlers + Groq + Google actions
├── memory.py               # Única interfaz con PostgreSQL. Toda la memoria pasa por aquí
├── provisioning.py         # MANIFEST_VERSION, CHANGELOG, system prompt, skills catalog
├── identity.py             # Identidad global Luma + personalización por usuario
├── skills.py               # Motor de skills: render, evolución, creación custom
├── onboarding.py           # 9 pasos de onboarding con extracción Groq
├── scheduler.py            # Jobs automáticos: heartbeat, briefing, ritmo semanal
├── conversation_context.py # Detección de contexto y memoria enfocada
├── tz_utils.py             # Timezones DST-aware, 60+ ciudades, por usuario
├── google_auth.py          # OAuth 2.0 flow para Google Workspace
├── oauth_server.py         # Servidor aiohttp para callback OAuth
├── google_services.py      # APIs de Google: Calendar, Gmail, Docs, Sheets, Drive
├── workspace_memory.py     # Sync bidireccional con Google Doc de memoria
├── requirements.txt        # Dependencias pip
├── AGENTS.md               # ← este archivo
└── GUIA_REDEPLOY.md        # Guía para hacer deploys seguros
```

### Regla de responsabilidad única

Cada módulo tiene un único dueño de responsabilidad:

- **¿Quieres cambiar qué dice el asistente?** → `provisioning.py` (SYSTEM_PROMPT)
- **¿Quieres cambiar cómo se almacena algo?** → `memory.py`
- **¿Quieres agregar una skill al catálogo?** → `provisioning.py` (SKILLS_CATALOG)
- **¿Quieres cambiar la personalidad base?** → `identity.py` (GLOBAL_IDENTITY)
- **¿Quieres cambiar el horario de algo?** → `scheduler.py`
- **¿Quieres agregar un comando Telegram?** → `bot.py` + registrar en `main()`
- **¿Quieres cambiar cómo se detecta el contexto?** → `conversation_context.py`
- **¿Quieres agregar una ciudad al mapa de timezones?** → `tz_utils.py` (CITY_TO_TZ)

---

## 5. Base de datos — schema completo

Una sola tabla `users`. Toda la memoria vive en columnas JSONB.

```sql
CREATE TABLE users (
    user_id           BIGINT PRIMARY KEY,          -- Telegram user ID

    -- Memoria vertical (9 categorías)
    identidad         JSONB NOT NULL DEFAULT '{}', -- nombre, edad, ubicación, etc.
    trabajo           JSONB NOT NULL DEFAULT '{}', -- empresa, rol, equipo, etc.
    proyectos         JSONB NOT NULL DEFAULT '[]', -- lista de proyectos activos
    vida_personal     JSONB NOT NULL DEFAULT '{}', -- familia, hobbies, etc.
    metas             JSONB NOT NULL DEFAULT '{}', -- semana, mes, año
    preferencias      JSONB NOT NULL DEFAULT '{}', -- tono, formato, idioma
    relaciones        JSONB NOT NULL DEFAULT '[]', -- personas clave
    ritmo             JSONB NOT NULL DEFAULT '{}', -- horarios, timezone, briefing_hora
    hechos            JSONB NOT NULL DEFAULT '[]', -- hechos sueltos detectados [FACT]

    -- Onboarding
    onboarding_done   BOOLEAN NOT NULL DEFAULT FALSE,
    onboarding_state  JSONB NOT NULL DEFAULT '{}',

    -- Historial de conversación (últimos N mensajes)
    history           JSONB NOT NULL DEFAULT '[]',

    -- Google OAuth (tokens por usuario)
    google_tokens     JSONB DEFAULT NULL,

    -- Skills activas del usuario
    skills            JSONB NOT NULL DEFAULT '[]',

    -- Versioning y reprovisión
    bot_version       TEXT NOT NULL DEFAULT '0.0.0',
    last_reprovisioned TIMESTAMP DEFAULT NULL,
    system_overrides  JSONB NOT NULL DEFAULT '{}',

    -- Identidad del asistente personalizada
    bot_identity      JSONB NOT NULL DEFAULT '{}',

    -- Metadata
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen         TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Cómo agregar una columna nueva

1. Agregar la columna con `DEFAULT` en `_init_db()` en `memory.py` — PostgreSQL aplica el default a filas existentes.
2. Agregar getter/setter en `memory.py` si la columna necesita acceso frecuente.
3. **Nunca** usar `ALTER TABLE` manual en producción — `_init_db()` se ejecuta en cada arranque y maneja migraciones aditivas (`ADD COLUMN IF NOT EXISTS`).
4. Hacer un deploy normal. La columna se crea automáticamente.

---

## 6. Flujo principal de un mensaje

```
Usuario envía mensaje
        ↓
handle_message() — bot.py
        ↓
¿Está en onboarding? → process_answer() — onboarding.py
        ↓ (no)
detect_context(message) — conversation_context.py
        ↓
build_system_prompt(user_id, BASE_SYSTEM_PROMPT) — memory.py
  → identity_block (identity.py)
  → base_prompt con {fecha_actual} inyectada
  → memoria vertical del usuario (9 categorías)
        ↓
get skills activas → build_skills_prompt_block(active_skills, ctx) — skills.py
  (solo inyecta skills cuyo trigger coincide con el contexto)
        ↓
read_memory_doc() si tiene Google conectado — workspace_memory.py
        ↓
call_groq(system_prompt, history, user_text) — bot.py
        ↓
Parsear respuesta:
  [ACTION: {...}]  → execute_google_action()
  [FACT: ...]      → memory.add_fact() + auto_evolve_from_facts()
        ↓
add_message(history) → enviar respuesta al usuario
```

### El contrato del [ACTION]

Cuando Groq quiere ejecutar algo en Google Workspace, incluye al final de su respuesta:

```
[ACTION: {"service": "calendar", "action": "create_event", "params": {"title": "...", "start": "YYYY-MM-DDTHH:MM:SS"}}]
```

**Servicios disponibles:**

| service | actions disponibles |
|---------|-------------------|
| `calendar` | `list_events`, `create_event`, `delete_event` |
| `gmail` | `list_emails`, `send_email`, `get_email` |
| `docs` | `create`, `get_content`, `append_text` |
| `sheets` | `create`, `read`, `append`, `write` |
| `drive` | `list_files`, `search` |

**Parámetros exactos por acción** (estos nombres son los únicos válidos):

```
calendar.create_event: title (str), start (YYYY-MM-DDTHH:MM:SS), end (opcional), description (opcional)
calendar.list_events:  days (int)
calendar.delete_event: event_id (str)
gmail.send_email:      to (str), subject (str), body (str)
gmail.list_emails:     max_results (int)
gmail.get_email:       email_id (str)
docs.create:           title (str), content (str)
docs.get_content:      doc_id (str)
docs.append_text:      doc_id (str), text (str)
sheets.create:         title (str)
sheets.read:           sheet_id (str)
sheets.append:         sheet_id (str), values (list)
drive.list_files:      max_results (int)
drive.search:          query (str)
```

Si Groq manda un parámetro con nombre alternativo (ej. `summary` en lugar de `title`),
`execute_google_action()` lo normaliza automáticamente antes de llamar a la API.

---

## 7. Sistema de memoria vertical

La memoria se divide en 9 categorías. Cada categoría es una columna JSONB en la DB.

| Categoría | Tipo | Contenido típico |
|-----------|------|-----------------|
| `identidad` | dict | nombre, edad, ciudad, profesión, idioma |
| `trabajo` | dict | empresa, rol, equipo, sector |
| `proyectos` | list | [{nombre, estado, deadline, descripción}] |
| `vida_personal` | dict | familia, hobbies, mascotas |
| `metas` | dict | semana, mes, año |
| `preferencias` | dict | tono, formato, idioma, notificaciones |
| `relaciones` | list | [{nombre, relación, notas}] |
| `ritmo` | dict | briefing_hora, inicio_dia, fin_dia, zona_horaria, dias_libres |
| `hechos` | list | strings sueltos detectados vía [FACT] |

**Funciones de acceso en memory.py:**

```python
get_category(user_id, "trabajo")              # → dict o list
set_category(user_id, "trabajo", {...})        # reemplaza todo
update_category(user_id, "trabajo", {"rol": "CTO"})  # merge parcial
add_to_category(user_id, "proyectos", {...})   # append a lista
add_fact(user_id, "texto del hecho")           # append a hechos[]
```

**Regla de escritura:** Siempre usar las funciones de `memory.py`. Nunca escribir
SQL directo para modificar memoria de usuario — `memory.py` es la única interfaz.

### Cómo se construye el system prompt

`build_system_prompt(user_id, base_prompt)` en `memory.py`:

1. Lee `bot_identity` → `identity.build_identity_block()` → bloque de personalidad
2. Inyecta el bloque de identidad AL INICIO del prompt
3. Añade el `base_prompt` (viene de `provisioning.SYSTEM_PROMPT` con `{fecha_actual}` ya reemplazada)
4. Añade un bloque con todas las categorías de memoria del usuario que no estén vacías

---

## 8. Sistema de skills

### Estructura de una skill en DB (columna `skills`)

```json
{
  "id": "formal_email",
  "name": "Correo formal",
  "emoji": "📧",
  "trigger": "manual",
  "description": "Qué hace la skill",
  "content_base": "Instrucciones genéricas del catálogo",
  "content_personal": "Versión personalizada con datos del usuario (generada por Groq)",
  "active": true,
  "created_at": "2026-01-01T10:00:00",
  "last_evolved": "2026-01-15T10:00:00",
  "evolution_count": 3,
  "evolution_log": [{"date": "...", "motivo": "..."}]
}
```

### Triggers disponibles

| Trigger | Cuándo se inyecta |
|---------|------------------|
| `manual` | Siempre en handle_message (todos los contextos) |
| `trabajo` | Solo cuando ctx == "trabajo" |
| `correo` | Solo cuando ctx == "correo" |
| `calendario` | Solo cuando ctx == "calendario" |
| `documentos` | Solo cuando ctx == "documentos" |
| `metas` | Solo cuando ctx == "metas" |
| `always` | Siempre, sin importar contexto |
| `morning` | Solo en briefing matutino (scheduler) |
| `heartbeat` | Solo en heartbeat (scheduler) |
| `custom` | Skills creadas por usuario — tratadas como `manual` |

### Cómo agregar una skill al catálogo

1. Ir a `provisioning.py` → `SKILLS_CATALOG`
2. Agregar el dict con los campos: `id`, `name`, `description`, `content`, `emoji`, `trigger`, `version_added`
3. Usar placeholders `{{campo}}` para que se personalicen: `{{nombre}}`, `{{empresa}}`, `{{rol}}`, `{{meta_semana}}`, `{{proyectos_activos}}`, `{{contactos_clave}}`, `{{briefing_hora}}`, `{{zona_horaria}}`, `{{tono}}`, `{{formato}}`
4. Bump `MANIFEST_VERSION` MINOR (ej. 1.2.1 → 1.3.0)
5. Agregar entrada al `CHANGELOG`
6. Hacer deploy

### Evolución automática

Cuando `handle_message` detecta un `[FACT]` nuevo en la respuesta de Groq:
1. `memory.add_fact(user_id, fact)` guarda el hecho
2. `skills.auto_evolve_from_facts(user_id, new_facts, memory, call_groq)` corre en background
3. Para cada skill activa cuyo `id` esté en `skills.facts_affect_skill()`, Groq regenera `content_personal`
4. Se actualiza `last_evolved` y `evolution_count` en DB

---

## 9. Sistema de identidad

### Identidad global (Luma)

Definida en `identity.py` → `GLOBAL_IDENTITY`. Tres características centrales:

- **CALIDEZ:** cercana, conversacional, recuerda detalles personales
- **PROACTIVIDAD:** orientada a resultados, menciona cosas antes de que pregunten
- **CURIOSIDAD ESTRATÉGICA:** conecta el día a día con objetivos de largo plazo

### Personalización por usuario

Guardada en columna `bot_identity` (JSONB):

```json
{
  "nombre": "Luna",
  "tono": "casual",
  "frase": "trátame como tu socio de trabajo",
  "activa": true
}
```

**Tonos disponibles:** `formal` | `casual` | `directo`

Cuando `bot_identity` está vacío o `activa == false`, se usa la identidad global Luma.

### Cómo modifica el system prompt

`identity.build_identity_block(bot_identity, user_nombre)` genera un bloque que se inyecta
**antes** del system prompt base. Tiene prioridad sobre cualquier instrucción de tono posterior.

---

## 10. Sistema de reprovisión y versioning

### MANIFEST_VERSION

Definido en `provisioning.py`. Sigue semver: `MAJOR.MINOR.PATCH`

| Tipo de cambio | Qué bump hacer |
|---------------|---------------|
| Cambio de comportamiento radical, nuevo onboarding | MAJOR (1.x.x → 2.x.x) |
| Nueva skill en catálogo, nueva funcionalidad, prompt mejorado | MINOR (x.1.x → x.2.x) |
| Corrección de texto, ajuste menor | PATCH (x.x.1 → x.x.2) |

### Qué toca y qué NO toca la reprovisión

| | Qué le pasa |
|--|------------|
| ✅ TOCA | `bot_version` del usuario (se actualiza) |
| ✅ TOCA | Notificación al usuario con el CHANGELOG |
| ✅ TOCA | `last_reprovisioned` timestamp |
| ❌ NO TOCA | Toda la memoria vertical (identidad, trabajo, proyectos, metas, etc.) |
| ❌ NO TOCA | `history` (historial de conversación) |
| ❌ NO TOCA | `google_tokens` (credenciales OAuth) |
| ❌ NO TOCA | `skills` activas del usuario |
| ❌ NO TOCA | `onboarding_done` (un usuario que lo completó no lo rehace) |
| ❌ NO TOCA | `bot_identity` (personalización del asistente) |

### Cuándo se ejecuta la reprovisión

- Al arrancar el bot: `run_reprovisioning()` compara `user.bot_version` vs `MANIFEST_VERSION`
- Cada domingo 3am: `weekly_reprovisioning()` en scheduler como backup

### Flujo completo de un deploy

```
1. Editar MANIFEST_VERSION en provisioning.py
2. Agregar entrada al CHANGELOG en provisioning.py
3. Hacer el cambio en el código correspondiente
4. git add . && git commit -m "descripción" && git push
5. Railway redeploy automático (~2 min)
6. Al arrancar: run_reprovisioning() notifica a todos los usuarios con versión vieja
```

---

## 11. Google Workspace — integración

### OAuth 2.0 por usuario

Cada usuario conecta su propia cuenta de Google. Los tokens se guardan en `google_tokens` (JSONB).
Railway expone el servidor aiohttp en `RAILWAY_PUBLIC_URL/oauth/callback`.

**Scopes autorizados:**
```
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/gmail.modify
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/spreadsheets
```

**Refresh automático:** `get_valid_token(user_id)` en `google_auth.py` refresca el token
si está expirado antes de cada llamada a la API.

### Workspace Memory (Google Doc)

Cada usuario con Google conectado tiene un Google Doc de memoria:
- Título: `"Memoria — {nombre_del_usuario}"`
- Se sincroniza DB → Doc en background cuando se aprende algo nuevo (`[FACT]`)
- Se lee al inicio de cada `handle_message` y se inyecta como "MEMORIA EXTENDIDA"
- El usuario puede editar el Doc directamente y esos cambios se reflejan en la DB vía `/sincronizar`

---

## 12. Scheduler — jobs automáticos

El scheduler usa APScheduler con timezone UTC. La lógica por usuario convierte a timezone local.

| Job | Función | Schedule | Descripción |
|-----|---------|----------|-------------|
| heartbeat | `heartbeat()` | Cada 30 min | Revisa reuniones próximas, hooks, skills heartbeat |
| morning_briefing_7 | `morning_briefing()` | Lun-Vie 7am UTC | Briefing — solo para usuarios con briefing_hora=7 en su tz |
| morning_briefing_8 | `morning_briefing()` | Lun-Vie 8am UTC | Briefing — solo para usuarios con briefing_hora=8 en su tz |
| morning_briefing_9 | `morning_briefing()` | Lun-Vie 9am UTC | Briefing — solo para usuarios con briefing_hora=9 en su tz |
| weekly_summary | `weekly_summary()` | Lunes 8am UTC | Resumen semanal del lunes |
| friday_wrap | `friday_wrap()` | Viernes 5pm UTC | Cierre de semana |
| nightly_doc_sync | `nightly_doc_sync()` | 2am UTC | Sync DB → Google Doc para todos los usuarios |
| weekly_reprovisioning | `weekly_reprovisioning()` | Domingo 3am UTC | Reprovisión de backup |

**Cómo agregar un job nuevo:**

```python
# En scheduler.py, dentro de start_scheduler():
scheduler.add_job(
    nombre_de_la_funcion,
    CronTrigger(day_of_week="wed", hour=10, minute=0, timezone="UTC"),
    id="id_unico_del_job"
)
```

**Importante:** Los jobs iteran sobre usuarios con Google conectado (`get_all_google_users()`).
Para jobs que no requieren Google, usar `get_all_users()`.

---

## 13. Comandos Telegram registrados

| Comando | Función | Descripción |
|---------|---------|-------------|
| `/start` | `cmd_start` | Inicia sesión o muestra saludo si ya existe |
| `/ayuda` | `cmd_help` | Lista todos los comandos disponibles |
| `/estado` | `cmd_status` | Resumen del estado del usuario (memoria, skills, Google) |
| `/memoria` | `cmd_memory` | Muestra el contenido de la memoria vertical |
| `/olvidar` | `cmd_forget` | Borra una categoría o toda la memoria |
| `/conectar_google` | `cmd_connect_google` | Inicia el flujo OAuth con Google |
| `/desconectar_google` | `cmd_disconnect_google` | Revoca y elimina tokens de Google |
| `/skills` | `cmd_skills` | Muestra el catálogo de skills disponibles |
| `/activar_skill` | `cmd_activate_skill` | Activa una skill + genera versión personalizada |
| `/desactivar_skill` | `cmd_deactivate_skill` | Desactiva una skill activa |
| `/mis_skills` | `cmd_mis_skills` | Ver skills activas con su contenido y estado |
| `/nueva_skill` | `cmd_nueva_skill` | Crear skill custom desde descripción libre |
| `/evolucion` | `cmd_evolucion` | Regenerar content_personal de una skill |
| `/mi_asistente` | `cmd_mi_asistente` | Ver/cambiar nombre, tono y frase del asistente |
| `/mi_zona` | `cmd_mi_zona` | Ver/cambiar timezone del usuario |
| `/version` | `cmd_version` | Ver versión actual del bot |
| `/mi_doc` | `cmd_my_doc` | Ver o crear el Google Doc de memoria |
| `/sincronizar` | `cmd_sync_doc` | Sincronizar Doc → DB manualmente |
| `/heartbeat` | `cmd_heartbeat_test` | Forzar un heartbeat manual (debug) |

**Cómo agregar un comando nuevo:**

```python
# 1. Definir la función en bot.py
async def cmd_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # ... lógica
    await update.message.reply_text("respuesta")

# 2. Registrar en main() — dentro del bloque de add_handler
telegram_app.add_handler(CommandHandler("nuevo", cmd_nuevo))
```

Después del deploy, avisar a BotFather con `/setcommands` si se quiere que aparezca en el menú.

---

## 14. Onboarding — 9 pasos

El onboarding corre una vez por usuario (cuando `onboarding_done == false`).
Cada respuesta es procesada por Groq con un extractor JSON específico al paso.

| # | ID del paso | Categoría que llena | Pregunta resumida |
|---|------------|---------------------|------------------|
| 1 | `nombre` | `identidad` | Nombre, ciudad, idioma |
| 2 | `trabajo` | `trabajo` | Empresa, rol, equipo |
| 3 | `proyectos` | `proyectos` | 2-3 proyectos principales |
| 4 | `relaciones` | `relaciones` | Personas clave del día a día |
| 5 | `metas` | `metas` | Meta más importante de la semana |
| 6 | `ritmo` | `ritmo` | Horario, briefing_hora, **zona_horaria** |
| 7 | `preferencias` | `preferencias` | Tono, formato de respuestas |
| 8 | `hooks` | `preferencias.hooks` | Qué eventos monitorear |
| 9 | `identidad_asistente` | `bot_identity` | Nombre, tono y frase para el asistente |

**Regla crítica:** El paso 6 (`ritmo`) es el único que llena `zona_horaria`.
Si el usuario no menciona su ciudad explícitamente, el sistema:
1. Intenta inferirla del texto de la respuesta con `tz_utils.infer_tz_from_city()`
2. Si falla, deja `zona_horaria = null` (no usa un default incorrecto)
3. Al primer `create_event`, auto-detecta desde `GET /calendars/primary` de Google

---

## 15. Timezones

**Principio central:** Todo datetime interno se maneja en UTC. Solo se convierte a local
para mostrar al usuario o para operaciones de calendario.

**Módulo:** `tz_utils.py` — toda la lógica de timezone pasa por aquí.

```python
tz_utils.now_for_user(user_data)          # → datetime en hora local del usuario
tz_utils.parse_google_dt(dt_str)          # → datetime con tzinfo desde string de Google
tz_utils.minutes_until(event_dt, user)    # → minutos hasta un evento (tz-aware)
tz_utils.get_iso_offset("America/Los_Angeles")  # → "-08:00" o "-07:00" según DST
tz_utils.normalize_datetime_for_calendar(dt_str, tz_name)  # → (iso_string, is_allday)
tz_utils.infer_tz_from_city("Madrid")     # → "Europe/Madrid"
```

**Mapa de ciudades:** `CITY_TO_TZ` en `tz_utils.py` — ~60 ciudades latinoamericanas y europeas.
Para agregar una ciudad:

```python
# En tz_utils.py → CITY_TO_TZ
"monterrey":    "America/Monterrey",
"guadalajara":  "America/Mexico_City",
```

**DST awareness:** `get_iso_offset()` calcula el offset en el momento de la llamada,
no usa offsets hardcodeados. Respeta automáticamente el cambio de horario de verano.

---

## 16. Cómo hacer cambios seguros

### Árbol de decisión para cualquier cambio

```
¿El cambio afecta el comportamiento del asistente con usuarios existentes?
├── SÍ → Bump MANIFEST_VERSION + CHANGELOG + deploy normal
└── NO → Deploy normal sin bump de versión

¿El cambio agrega o modifica una columna en DB?
├── SÍ → Usar ADD COLUMN IF NOT EXISTS en _init_db() en memory.py
└── NO → No tocar memory.py/_init_db()

¿El cambio toca google_tokens, oauth flow, o scopes?
├── SÍ → Ver sección 17 (ZONA PROTEGIDA — requiere revisión humana)
└── NO → Continuar

¿El cambio modifica la lógica de execute_google_action o call_groq?
├── SÍ → Ver sección 17 (ZONA PROTEGIDA)
└── NO → Continuar
```

### Tipos de cambio y sus recetas

**Tipo A — Cambiar el tono o comportamiento del asistente:**
```
1. Editar SYSTEM_PROMPT en provisioning.py
2. Bump MINOR en MANIFEST_VERSION
3. Agregar entrada al CHANGELOG
4. git push
```
> ⚠️ **Regla explícita:** Cualquier cambio en `SYSTEM_PROMPT` —
> por pequeño que sea— requiere bump MINOR + entrada en CHANGELOG.
> Sin esto, los usuarios existentes no son notificados y su `bot_version`
> queda desincronizada con el comportamiento real del asistente.

**Tipo B — Agregar skill al catálogo:**
```
1. Agregar dict en SKILLS_CATALOG en provisioning.py
2. Bump MINOR en MANIFEST_VERSION
3. Agregar entrada al CHANGELOG
4. git push
```

**Tipo C — Corrección de texto/bug menor:**
```
1. Hacer el fix
2. Bump PATCH en MANIFEST_VERSION si afecta al usuario, si no ningún bump
3. git push
```

**Tipo D — Nueva columna en DB:**
```
1. Agregar en _init_db() con ADD COLUMN IF NOT EXISTS y DEFAULT
2. Agregar getter/setter en memory.py
3. git push (la migración es automática al arrancar)
```

**Tipo E — Nuevo comando Telegram:**
```
1. Definir función cmd_* en bot.py
2. Registrar con telegram_app.add_handler(CommandHandler(...)) en main()
3. Actualizar tabla de comandos en AGENTS.md (sección 13)
4. git push
```

**Tipo F — Nuevo job de scheduler:**
```
1. Definir función async en scheduler.py
2. Agregar add_job() en start_scheduler()
3. Actualizar tabla de jobs en AGENTS.md (sección 12)
4. git push (no requiere bump de versión)
```

---

## 17. ⛔ Zonas protegidas — NO tocar sin autorización explícita

Estas secciones afectan directamente la seguridad de los usuarios o la integridad de su memoria.
**Un agente autónomo NO debe modificar estas zonas sin una instrucción explícita y específica del dueño del proyecto.**

### 🔴 CRÍTICO — Nunca tocar bajo ninguna circunstancia

```
google_auth.py → SCOPES
```
Los scopes de OAuth definen exactamente a qué datos de Google tiene acceso el bot.
Ampliar scopes sin consentimiento del usuario es una violación de privacidad.
Si hay que agregar un scope nuevo: el usuario debe re-autorizar manualmente.

```
memory.py → _connect(), _init_db()
```
Cualquier error aquí afecta a TODOS los usuarios simultáneamente.
No modificar sin probar localmente con una DB de prueba.

```
bot.py → call_groq() — el system prompt nunca debe filtrar datos de un usuario a otro
```
Cada llamada a Groq usa el prompt del usuario específico. No compartir contexto entre usuarios.

### 🟠 ALTO RIESGO — Solo tocar con instrucción explícita

```
google_auth.py → get_valid_token(), exchange_code_for_tokens(), refresh_access_token()
```
Son el corazón del OAuth flow. Un bug aquí desconecta a todos los usuarios de Google.

```
oauth_server.py → oauth_callback()
```
Maneja el callback de Google. Cualquier cambio puede romper el flujo de autorización.

```
memory.py → save_google_tokens(), get_google_tokens()
```
Los tokens de Google son credenciales de usuario. No loguear su contenido. No exponer en respuestas.

```
provisioning.py → run_reprovisioning(), reprovision_user()
```
Corre sobre todos los usuarios. Un bug puede enviar mensajes masivos no deseados o corromper versiones.

```
onboarding.py → complete_onboarding()
```
Una vez que `onboarding_done = True`, no vuelve a `False` automáticamente.
Re-activar el onboarding de un usuario existente borra su progreso.

### 🟡 PRECAUCIÓN — Verificar impacto antes de cambiar

```
identity.py → GLOBAL_IDENTITY
```
Cambia la personalidad base de Luma para TODOS los usuarios que no tienen personalización propia.
Hacer bump de versión y notificar en changelog.

```
conversation_context.py → CONTEXT_KEYWORDS
```
Afecta qué memoria se inyecta en qué contexto. Un keyword mal puesto puede inyectar memoria incorrecta.

```
scheduler.py → horarios de CronTrigger
```
Cambiar el horario de morning_briefing sin considerar timezones de usuarios puede
mandar el briefing a las 3am de alguien.

```
skills.py → auto_evolve_from_facts()
```
Corre en background para todos los usuarios que aprenden hechos. 
Errores aquí son silenciosos pero acumulativos.

---

## 18. Recetas de tareas frecuentes

### Agregar una ciudad al mapa de timezones

```python
# tz_utils.py → CITY_TO_TZ dict
"hermosillo":   "America/Hermosillo",
"la habana":    "America/Havana",
```
No requiere bump de versión. Solo un deploy.

### Agregar un placeholder a una skill

```python
# provisioning.py → skill content
"Ayuda a {{nombre}} con sus tareas en {{empresa}}."
# Los placeholders disponibles son:
# {{nombre}}, {{empresa}}, {{rol}}, {{equipo}}, {{meta_semana}}, {{meta_mes}},
# {{tono}}, {{formato}}, {{briefing_hora}}, {{zona_horaria}},
# {{proyectos_activos}}, {{contactos_clave}}
```

### Ver logs de Railway en tiempo real

```bash
railway logs --tail
```

### Forzar reprovisión manual de un usuario específico

```python
# Desde Python REPL con el bot corriendo
import provisioning, memory
import asyncio
asyncio.run(provisioning.reprovision_user(USER_ID, memory))
```

### Revisar el estado completo de un usuario en DB

```sql
SELECT user_id, 
       identidad->>'nombre' as nombre,
       bot_version,
       onboarding_done,
       last_seen,
       google_tokens IS NOT NULL as tiene_google,
       jsonb_array_length(skills) as num_skills
FROM users
ORDER BY last_seen DESC;
```

### Agregar un nuevo contexto de conversación

```python
# conversation_context.py → CONTEXT_KEYWORDS
"finanzas": ["presupuesto", "gasto", "factura", "pago", "dinero", "inversión"],

# conversation_context.py → CONTEXT_MEMORY_FOCUS
"finanzas": ["metas", "hechos"],

# skills.py → CONTEXT_TRIGGERS
"finanzas": ["manual", "finanzas", "always", "custom"],
```

Bump MINOR de versión porque cambia el comportamiento del asistente.

---

## 19. Cómo actualizar este archivo

AGENTS.md debe mantenerse sincronizado con el código. Cuando hagas un cambio que afecte
alguna de las secciones documentadas aquí, actualiza la sección correspondiente en el mismo
commit o PR.

### Qué actualizar con cada tipo de cambio

| Si cambias... | Actualiza en AGENTS.md |
|--------------|----------------------|
| Nuevo comando Telegram | Sección 13 — tabla de comandos |
| Nueva skill en catálogo | Sección 8 — mencionar el nuevo id y trigger |
| Nuevo job de scheduler | Sección 12 — tabla de jobs |
| Nueva columna en DB | Sección 5 — schema SQL |
| Nueva variable de entorno | Sección 3 — tabla de variables |
| Nuevo contexto de conversación | Sección 7 y sección 18 |
| Nuevo módulo Python | Sección 4 — árbol de archivos |
| Cambio en OAuth scopes | Sección 11 — tabla de scopes |
| Cambio en flujo de onboarding | Sección 14 — tabla de pasos |
| Nueva ciudad en tz_utils | No requiere actualización (lista muy larga) |

### Formato de este archivo

- Los títulos de sección usan `##` con número y nombre
- Las tablas tienen siempre una fila de encabezado
- Los bloques de código usan triple backtick con lenguaje
- Los niveles de riesgo usan los emojis 🔴 🟠 🟡 para consistencia visual
- Los nombres de archivos y funciones van en `backticks`
- Cuando algo está prohibido va en sección 17 (nunca disperso en el texto)

---

*Última actualización: Marzo 2026 — v1.2.1*
*Maintainer: revisar con el dueño del proyecto antes de modificar zonas protegidas*
