# Railway Deploy Canonico

Servicio de produccion oficial: `ferreteria-bot`.

`ferreteria-bot-clean` no es el runtime canonico. Solo puede vivir como staging o backup si se decide de forma explicita.

## Lo que Railway despliega

- El deploy sale del arbol local actual.
- `.env`, `.env.*`, `.db` y `.sqlite` no se suben. Eso es intencional.
- La paridad con local se resuelve con variables + estrategia de datos, no copiando el entorno de desarrollo.
- Si Railway sigue conectado a GitHub, un auto-deploy desde `main` puede pisar un `railway up` manual. El chequeo de paridad lo marca para que esa deriva no pase desapercibida.

## Dependencias

- `requirements.txt`: runtime HTTP/productivo.
- `requirements-dev.txt`: testing, lint, tooling y multimedia opcional local.

No metas `pytest`, `black`, `flake8`, `bandit`, `openai-whisper`, `torch`, `pydub` ni `soundfile` en la imagen del servicio web canonico.

## Variables minimas de produccion

Estas deben existir de forma explicita en Railway para `ferreteria-bot`:

- `ENVIRONMENT=production`
- `DATABASE_URL`
- `SECRET_KEY`
- `ADMIN_TOKEN`
- `OPENAI_API_KEY`
- `CORS_ORIGINS`

Variables operativas segun integraciones:

- WhatsApp: `WHATSAPP_PROVIDER` mas credenciales Meta o Twilio
- Sheets / stock sync
- MercadoPago
- SendGrid

Notas:

- `DATABASE_URL` debe ser explicita. Produccion no puede depender del fallback SQLite local.
- Si se usa SQLite en Railway, debe apuntar al volumen, por ejemplo `sqlite:////app/data/finalprod.db`.
- Si `WHATSAPP_PROVIDER` queda en `mock`, el servicio sigue arrancando pero la paridad operativa queda en `WARN`.

## Datos

- Catalogos y policies viajan con la imagen (`config/` y `data/tenants/ferreteria/`).
- La base productiva no viaja con la imagen.
- Si se usa SQLite en Railway, la fuente de verdad debe vivir en el volumen montado.
- Si se usa Postgres, la fuente de verdad es `DATABASE_URL`.

## Checklist de release

1. Correr el chequeo local/remoto:

```bash
python3 scripts/check_railway_parity.py --service ferreteria-bot
```

2. Verificar que el resultado final no tenga `FAIL`.

3. Deploy del servicio canonico:

```bash
railway up -s ferreteria-bot -e production -m "Deploy canonical ferreteria bot"
```

## Endpoints de verificacion

- `/health`
- `/api/health`
- `/diag/db` con `X-Admin-Token`
- `/diag/runtime-integrity` con `X-Admin-Token`

`X-Runtime-Stack` debe devolver `final`.
