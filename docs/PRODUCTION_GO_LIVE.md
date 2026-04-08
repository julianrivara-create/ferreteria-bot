# Go-Live Checklist del bot real

Esta guía deja el deploy alineado con el runtime canónico `app/*` servido por `wsgi.py`.

## 1. Entry point oficial

- Producción debe arrancar con:

```bash
gunicorn --bind 0.0.0.0:$PORT wsgi:app
```

- `wsgi.py` intenta primero `app.main`.
- `wsgi_legacy.py` queda solo como compatibilidad de emergencia si el stack final no inicializa.
- En `staging` y `production`, el fallback legacy ya no debe activarse en silencio. Si se necesita usarlo como emergencia, hay que habilitarlo explícitamente con:

```bash
ALLOW_LEGACY_FALLBACK=true
```

## 2. Variables obligatorias antes de promover

### Requeridas

- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_TOKEN`

### Recomendadas

- `REDIS_URL`
- `OPENAI_API_KEY`

### Según canal activo

- Meta:
  - `META_VERIFY_TOKEN`
  - `META_ACCESS_TOKEN`
  - `WHATSAPP_PHONE_NUMBER_ID`
  - `META_APP_SECRET` recomendado para firma del webhook
- Twilio:
  - `TWILIO_ACCOUNT_SID`
  - `TWILIO_AUTH_TOKEN`
  - `TWILIO_WHATSAPP_NUMBER`

## 3. Preflight local / de entorno

### Staging

```bash
python3 scripts/preflight_production.py --mode staging --channel-provider auto
```

### Producción

```bash
python3 scripts/preflight_production.py --mode production --channel-provider auto
```

Bloquear la promoción si:

- falta `DATABASE_URL`
- falta `SECRET_KEY`
- falta `ADMIN_TOKEN`
- en producción falta `OPENAI_API_KEY`

## 4. Suite obligatoria antes de staging

```bash
pytest -q tests app/bot/tests
```

Esperado: verde completo.

## 5. Deploy a staging

Usar el mismo artefacto/config base que va a ir a producción.

Si se usa Railway:

- Start command: `gunicorn --bind 0.0.0.0:$PORT wsgi:app`
- No usar entrypoints legacy como start command principal.

## 6. Smoke de staging

```bash
python3 scripts/staging_smoke.py \
  --base-url https://TU-STAGING \
  --admin-token TU_ADMIN_TOKEN \
  --tenant-slug farmacia \
  --channel-provider meta \
  --meta-verify-token TU_META_VERIFY_TOKEN \
  --meta-app-secret TU_META_APP_SECRET
```

El smoke valida:

- `/health`
- `/api/health`
- header `X-Runtime-Stack=final`
- `/diag/db`
- redacción segura de `/diag/db`
- `/api/catalog`
- `/api/catalog/grouped`
- `/api/t/<tenant>/products`
- `/api/t/<tenant>/chat`
- `/api/chat`
- rate limit de `/api/chat`
- `GET /webhooks/whatsapp`
- `POST /webhooks/whatsapp`

## 7. Go / No-Go para producción

Promover solo si staging cumple todo:

- stack final `app.main` levanta correctamente
- `/api/health` devuelve `X-Runtime-Stack=final`
- `/api/chat` responde con shape estable
- `429` aparece al exceder el límite
- webhook de WhatsApp verifica y procesa
- catálogo y tenant routes responden
- no aparecen errores crudos del proveedor hacia el usuario

## 8. Smoke inmediato post-deploy

- `GET /health`
- `GET /api/health`
- confirmar header `X-Runtime-Stack=final`
- `POST /api/chat`
- verificación del webhook del proveedor

## 9. Observación 30-60 minutos

Mirar especialmente:

- errores `final_stack_init_failed_using_legacy_fallback`
- errores de DB
- errores de Redis
- uso inesperado del fallback
- volumen inesperado de `429`
- errores de canal WhatsApp

## 10. Qué queda fuera de esta salida

- retiro total de `bot_sales/*`
- migración grande de scripts/docs históricos
- cambios de infraestructura o auth nueva sobre `/api/chat`
