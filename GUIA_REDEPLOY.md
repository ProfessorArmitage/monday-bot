# Guía de Redeploy — Asistente Personal Monday

## Regla de oro

**Un solo archivo controla todo el comportamiento base del bot: `provisioning.py`.**

Cualquier cambio que quieras propagar a todos los usuarios — nuevas habilidades,
nuevo tono, nuevo prompt, nuevas preguntas de onboarding — se hace en ese archivo.
Los datos personales de cada usuario (memoria, proyectos, metas, etc.) nunca se tocan.

---

## Tipos de cambio y qué hacer en cada caso

### Tipo A — Cambio de comportamiento (prompt, tono, instrucciones)

Ejemplo: quieres que el bot sea más proactivo, o que siempre responda en bullet points.

1. Abre `provisioning.py`
2. Edita el bloque `SYSTEM_PROMPT`
3. Incrementa `MANIFEST_VERSION` en MINOR: `"1.0.0"` → `"1.1.0"`
4. Agrega entrada al `CHANGELOG`:

```python
"1.1.0": {
    "titulo": "Respuestas más proactivas",
    "cambios": [
        "El asistente ahora sugiere acciones antes de que las pidas",
        "Respuestas en formato más visual con emojis y estructura",
    ],
    "accion_requerida": None,
},
```

5. `git add . && git commit -m "v1.1.0 prompt más proactivo" && git push`

**Qué pasa automáticamente:**
- Railway redeploya en ~2 minutos
- Al arrancar, detecta usuarios con versión `< 1.1.0`
- Les envía una notificación con el changelog
- Marca su `bot_version = "1.1.0"` en la DB
- Su memoria personal no se toca

---

### Tipo B — Nueva skill disponible

Ejemplo: agregas una skill de "Análisis de correos" o "Planificación semanal".

1. Abre `provisioning.py`
2. Agrega la skill al array `SKILLS_CATALOG`:

```python
{
    "id": "email_analysis",
    "name": "Análisis de correos",
    "description": "Resumir y priorizar correos importantes",
    "content": (
        "Cuando el usuario pida analizar correos, clasifícalos por urgencia "
        "e identifica los que requieren respuesta hoy."
    ),
    "trigger": "manual",
    "emoji": "🔍",
    "version_added": "1.2.0",
},
```

3. Incrementa `MANIFEST_VERSION`: `"1.1.0"` → `"1.2.0"`
4. Agrega al `CHANGELOG`
5. `git push`

**La skill queda disponible en el catálogo para todos.**
Los usuarios la activan con `/activar_skill análisis de correos`.
Las skills que ya tenían activadas no se tocan.

---

### Tipo C — Corrección menor (typo, ajuste de texto)

Sin impacto en comportamiento, no hay que notificar a usuarios.

1. Haz el cambio donde sea necesario
2. Incrementa solo el PATCH: `"1.2.0"` → `"1.2.1"`
3. En el CHANGELOG, pon cambios mínimos:

```python
"1.2.1": {
    "titulo": "Correcciones menores",
    "cambios": ["Ajustes de texto en mensajes del bot"],
    "accion_requerida": None,
},
```

4. `git push`

Los usuarios reciben la notificación pero es breve y no requiere ninguna acción.

---

### Tipo D — Cambio de base de datos (nueva columna)

Ejemplo: agregas una nueva columna a la tabla `users`.

1. Agrega la columna en el bloque `CREATE TABLE IF NOT EXISTS` de `memory.py`
2. Agrega la migración en el array `migrations` del mismo archivo:

```python
"ALTER TABLE users ADD COLUMN IF NOT EXISTS nueva_columna JSONB DEFAULT '{}'",
```

3. El `ALTER TABLE ... IF NOT EXISTS` se ejecuta al arrancar — nunca falla
   si la columna ya existe, y no toca datos existentes
4. No necesariamente requiere incrementar `MANIFEST_VERSION`
   a menos que el comportamiento cambie para el usuario

---

### Tipo E — Cambio de onboarding (nuevas preguntas)

> ⚠️ Afecta solo a usuarios nuevos. Los que ya completaron el onboarding no lo ven.

1. Edita `ONBOARDING_STEPS` en `onboarding.py`
2. Incrementa `ONBOARDING_VERSION` en `provisioning.py`
3. Si es un cambio MAJOR que quieres aplicar a todos:
   - Incrementa la versión MAJOR: `"1.x.x"` → `"2.0.0"`
   - En `run_reprovisioning()`, agrega lógica para marcar `onboarding_done = False`
     solo si el cambio lo justifica (raro — solo en rediseños totales)

---

## Flujo completo de un redeploy normal

```
1. Edita provisioning.py
   ├── MANIFEST_VERSION = "X.Y.Z"  ← incrementar
   ├── CHANGELOG["X.Y.Z"] = {...}  ← describir cambio
   └── SYSTEM_PROMPT o SKILLS_CATALOG ← el cambio real

2. git add provisioning.py
   git commit -m "vX.Y.Z descripción del cambio"
   git push

3. Railway detecta el push → redeploya automáticamente (~2 min)

4. Al arrancar bot.py → llama provisioning.run_reprovisioning()
   ├── Lee todos los user_ids de PostgreSQL
   ├── Por cada usuario con bot_version < "X.Y.Z":
   │   ├── Envía notificación en Telegram con el changelog
   │   ├── Actualiza bot_version en DB
   │   └── NO toca ningún dato personal
   └── Log: "X actualizados, Y errores de Z usuarios"

5. Cada domingo 3am → weekly_reprovisioning() corre como respaldo
   (por si alguien no estaba activo cuando se desplegó)
```

---

## Qué NUNCA hace la reprovisión

| Dato del usuario | ¿Lo toca? |
|-----------------|-----------|
| identidad (nombre, ubicación) | ❌ Nunca |
| trabajo, proyectos, metas | ❌ Nunca |
| relaciones, ritmo, preferencias | ❌ Nunca |
| hechos aprendidos en conversación | ❌ Nunca |
| historial de conversación | ❌ Nunca |
| tokens de Google (OAuth) | ❌ Nunca |
| skills que el usuario activó | ❌ Nunca |
| onboarding_done (si ya lo hizo) | ❌ Nunca* |
| Google Doc de memoria | ❌ Nunca |

*Solo en versiones MAJOR con cambio explícito de `onboarding_done`

---

## Comandos útiles post-deploy

Desde Telegram, como usuario:
```
/version    → ver qué versión tienes vs. la del sistema
/skills     → ver catálogo actualizado de skills
/memoria    → confirmar que tu memoria está intacta
```

En Railway logs, buscar:
```
Reprovisión completa: X/Y actualizados
```

---

## Referencia rápida de versioning

```
MAJOR.MINOR.PATCH

MAJOR → cambio radical de comportamiento, nuevo onboarding para todos
        ejemplo: 1.0.0 → 2.0.0

MINOR → nueva funcionalidad, nuevas skills, cambio de prompt
        ejemplo: 1.0.0 → 1.1.0

PATCH → corrección de texto, ajuste sin impacto en comportamiento
        ejemplo: 1.0.0 → 1.0.1
```

---

## Estructura de archivos del sistema

```
provisioning.py    ← ÚNICA fuente de verdad del comportamiento base
memory.py          ← Schema DB + funciones de versión
bot.py             ← Carga prompt desde provisioning, dispara reprovisión al arrancar
scheduler.py       ← Reprovisión semanal como respaldo (domingos 3am)
onboarding.py      ← Pasos de entrevista (versionados por ONBOARDING_VERSION)
skills.py          ← YA NO SE USA DIRECTAMENTE — todo va por provisioning.py
```

> **Nota:** `skills.py` quedó obsoleto. El catálogo de skills ahora vive
> en `provisioning.SKILLS_CATALOG`. Puedes eliminarlo o mantenerlo como referencia.
