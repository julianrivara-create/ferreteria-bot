# 🚀 Guía de Deploy en Railway

Esta guía te permite subir tu bot a **Railway** para que funcione 24/7 sin depender de tu computadora ni de Ngrok.

## 1. Preparación (Ya realizada) ✅

He preparado el código para que sea "Cloud Ready":
-   `wsgi.py`: Punto de entrada para servidor de producción.
-   `requirements.txt`: Agregado `gunicorn`.
-   `Dockerfile`: Configurado para escuchar en el puerto que asigne Railway.

## 2. Crear Proyecto en Railway

1.  Entrá a [railway.app](https://railway.app/) y logueate (GitHub recomendado).
2.  Click en **+ New Project** → **Github Repo**.
3.  Seleccioná el repositorio donde subiste este código.
    - *Si no lo subiste a GitHub, hacelo primero.*

## 3. Configuración de Variables

Una vez creado, andá a la pestaña **Variables** y agregá estas (son las mismas de tu `.env`):

| Variable | Valor (Ejemplo) |
|----------|-----------------|
| `LLM_CLIENT` | `chatgpt` (o `auto`) |
| `OPENAI_API_KEY` | `sk-...` |
| `WHATSAPP_PROVIDER` | `mock`, `twilio` o `meta` |
| `PORT` | (No agregar, Railway la pone sola) |

*Opcionales (según provider):*
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, etc.

## 4. Deploy del Dashboard (Opcional)

Si querés el Dashboard también online:
1.  En el mismo proyecto, click **+ New Service**.
2.  Seleccioná el mismo repo.
3.  En **Settings** de este nuevo servicio:
    - **Build Command**: `pip install -r requirements.txt` (o dejar auto)
    - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT dashboard.app:app`
    - **Root Directory**: `/dashboard` (IMPORTANTE)

## 5. Obtener tu URL Pública

1.  En la pestaña **Settings** → **Domains**.
2.  Click **Generate Domain**.
3.  Te dará un link tipo: `iphone-bot-production.up.railway.app`.

¡Ese es tu Webhook! 🎉

## 6. Conectar con WhatsApp

-   **Twilio/Meta**: Andá a la configuración de tu proveedor y pegá el link de Railway + `/webhooks/whatsapp`.
    -   Ej: `https://iphone-bot-production.up.railway.app/webhooks/whatsapp`

---

### Fallback sin GitHub (Railway CLI)

Si no querés usar GitHub, instalá la CLI de Railway en tu Mac:

```bash
# 1. Instalar
brew install railway

# 2. Login
railway login

# 3. Subir desde tu carpeta
railway up
```

¡Listo! Tu bot vive en la nube. ☁️
