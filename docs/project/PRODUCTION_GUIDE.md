# 🚀 Guía de Producción - Sales Bot

## Guía Completa: De Desarrollo a Producción

Esta guía te lleva paso por paso desde la instalación local hasta tener el bot corriendo en producción con todas las integraciones activas.

---

# PARTE 1: SETUP LOCAL (30 minutos)

## Paso 1: Prerequisitos

### A. Instalar Software Base

**Python 3.9+**:
```bash
# Verificar versión
python3 --version
# Debe ser >= 3.9

# Si no tenés, instalar (Mac):
brew install python@3.11

# Linux:
sudo apt update
sudo apt install python3.11 python3-pip
```

**Git** (si querés versionar):
```bash
git --version
# Si no tenés:
brew install git  # Mac
sudo apt install git  # Linux
```

### B. Clonar/Descargar Proyecto

```bash
# Opción 1: Ya lo tenés descargado
cd ~/Desktop/iphone-bot-demo

# Opción 2: Si está en Git
git clone <repo-url>
cd iphone-bot-demo
```

---

## Paso 2: Setup del Entorno Virtual

```bash
# Crear virtualenv
python3 -m venv venv

# Activar
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate  # Windows

# Verificar que está activo (debe aparecer (venv) en el prompt)
which python
# Debe mostrar: /path/to/iphone-bot-demo/venv/bin/python
```

---

## Paso 3: Instalar Dependencias

```bash
# Asegurarse que pip está actualizado
pip install --upgrade pip

# Instalar todas las dependencias
pip install -r requirements.txt

# Verificar instalación
pip list | grep openai
pip list | grep flask
pip list | grep twilio
```

**Si hay errores**:
```bash
# Error común: no se puede instalar google-api-python-client
pip install --upgrade setuptools wheel

# Reintentar
pip install -r requirements.txt
```

---

## Paso 4: Configurar Variables de Entorno

### A. Crear archivo `.env`

```bash
# Copiar template
cp .env.example .env

# Editar con tu editor favorito
nano .env
# O: code .env (VSCode)
# O: vim .env
```

### B. Configurar OpenAI (ESENCIAL)

1. **Ir a**: https://platform.openai.com/api-keys
2. **Crear cuenta** si no tenés
3. **Crear API Key**: 
   - Click en "Create new secret key"
   - Copiar la key (solo se muestra una vez!)
4. **Pegar en .env**:
```bash
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxx
```

**Nota sobre costos**:
- Cuenta nueva tiene $5 de crédito gratis
- GPT-4: ~$0.01 por conversación
- 100 conversaciones = ~$1
- Configurá billing limit en https://platform.openai.com/account/billing

---

## Paso 5: Inicializar Base de Datos

```bash
# El bot crea la DB automáticamente en el primer run
# Pero podés verificar que funcione:

python3 -c "
from bot_sales.core.database import Database
db = Database()
print('✅ Database initialized successfully')
"
```

Deberías ver:
```
✅ Database initialized successfully
```

---

## Paso 6: Cargar Catálogo de Productos

### A. Usar el catálogo de ejemplo

Ya tenés `catalog_extended.csv` con productos de Herramientas.

### B. O crear tu propio catálogo

```bash
# Copiar template
cp catalog_extended.csv mi_catalogo.csv

# Editar con Excel, LibreOffice, o CSV editor
```

**Formato requerido**:
```csv
sku,name,category,price_ars,stock,brand,color,storage_gb
PROD-001,Mi Producto,Categoría,10000,50,Marca,Color,Specs
```

**Campos obligatorios**:
- `sku` - Código único
- `name` o `model` - Nombre del producto
- `price_ars` - Precio en pesos
- `stock` - Cantidad disponible

---

## Paso 7: Personalizar Políticas

```bash
# Editar políticas del negocio
nano policies.md
```

Personalizá:
- Métodos de pago
- Zonas de envío
- Tiempos de entrega
- Garantía
- Devoluciones

---

## Paso 8: Primer Test Local

```bash
# Test rápido del bot
python3 demo_final.py
```

**Qué deberías ver**:
```
============================================================
🤖 IPHONE SALES BOT - DEMO FINAL
============================================================
Features activas:
✅ Analytics & Tracking
✅ FAQ System (Zero-Token)
...

▶️  ESCENARIO: FAQ & Recomendaciones
----------------------------------------

Vos: Hola! Cómo es el tema del envío?
Bot: 📦 opciones de envío:
...
```

**Si funciona**: ¡Excelente! El bot está funcionando localmente.

**Si no funciona**:
1. Verificar que `OPENAI_API_KEY` está configurado
2. Verificar que pip install se completó sin errores
3. Ver logs de error

---

# PARTE 2: CONFIGURAR INTEGRACIONES (2-3 horas)

## Integración 1: Email (Gmail SMTP)

### A. Preparar Gmail

1. **Ir a** tu cuenta Gmail
2. **Habilitar 2FA**:
   - https://myaccount.google.com/security
   - "2-Step Verification" → Activar
3. **Crear App Password**:
   - https://myaccount.google.com/apppasswords
   - Seleccionar "Mail" + "Other"
   - Copiar password de 16 caracteres

### B. Configurar en .env

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # App password de 16 chars
```

### C. Test

```bash
python3 -c "
from bot_sales.integrations.email_client import EmailClient

client = EmailClient()
result = client.send_order_confirmation(
    to_email='tu_email@gmail.com',
    order_details={
        'order_id': 'TEST-001',
        'producto': 'Taladro Percutor 13mm',
        'precio': 1200000,
        'metodo_pago': 'MercadoPago',
        'zona': 'CABA'
    }
)
print('✅ Email sent!' if result['status'] == 'sent' else '❌ Failed')
"
```

Checkeá tu inbox, debería llegar un email profesional HTML.

---

## Integración 2: WhatsApp (Twilio) - RECOMENDADO

### A. Crear Cuenta Twilio

1. **Ir a**: https://www.twilio.com/try-twilio
2. **Sign up** (gratis, incluye $15 de crédito)
3. **Verificar** email y teléfono

### B. Configurar WhatsApp Sandbox

1. **En Twilio Console**: https://console.twilio.com
2. **Ir a**: Messaging → Try it out → Send a WhatsApp message
3. **Seguir instrucciones**:
   - Enviar mensaje desde tu WhatsApp a Twilio
   - Mensaje: `join <palabra-clave>`
   - Ejemplo: `join happy-tiger`

### C. Obtener Credenciales

1. **Account SID**:
   - Dashboard → Account Info → Account SID
   - Ejemplo: `ACxxxxxxxxxxxxxxxxxxxx`

2. **Auth Token**:
   - Dashboard → Account Info → Auth Token
   - Click "Show" para ver

3. **WhatsApp Number**:
   - El número de Twilio (sandbox)
   - Ejemplo: `whatsapp:+14155238886`

### D. Configurar en .env

``bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=tu_auth_token_aquí
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

### E. Test Local

```bash
# Terminal 1: Iniciar servidor WhatsApp
python3 whatsapp_server.py

# Deberías ver:
# 🚀 WhatsApp Server Running (TWILIO)
#    Port: 5001
#    Webhook: http://localhost:5001/webhooks/meta
```

### F. Exponer Webhook con ngrok

**Descargar ngrok**:
```bash
# Mac
brew install ngrok

# Linux
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar -xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/
```

**Autenticar**:
1. Crear cuenta: https://ngrok.com/signup
2. Copiar token
3. `ngrok config add-authtoken <tu-token>`

**Ejecutar**:
```bash
# Terminal 2
ngrok http 5001
```

**Deberías ver**:
```
Forwarding   https://xxxx-xxx-xxx-xxx.ngrok-free.app -> http://localhost:5001
```

**Copiar la URL HTTPS**.

### G. Configurar Webhook en Twilio

1. **Ir a**: Console → Messaging → Settings → WhatsApp sandbox settings
2. **"When a message comes in"**:
   - Pegar: `https://xxxx.ngrok-free.app/webhooks/meta`
   - Method: POST
3. **Save**

### H. Test End-to-End

1. **Desde tu WhatsApp** enviar mensaje al número de Twilio
2. **Escribir**: "Hola"
3. **Deberías recibir** respuesta del bot

**Logs en terminal**:
```
[INFO] WhatsApp message received from +549112...
[INFO] Bot response sent
```

✅ **Si funciona**: WhatsApp está configurado!

---

## Integración 3: Google Sheets (Opcional)

### A. Crear Google Cloud Project

1. **Ir a**: https://console.cloud.google.com
2. **New Project** → Poner nombre → Create
3. **En el proyecto**: APIs & Services → Enable APIs and Services
4. **Buscar**: "Google Sheets API" → Enable

### B. Crear Service Account

1. **IAM & Admin** → Service Accounts
2. **Create Service Account**:
   - Name: "sales-bot"
   - Role: Editor
   - Create
3. **Actions** → Manage Keys → Add Key → JSON
4. **Descargar** `credentials.json`
5. **Mover** a directorio del proyecto:
```bash
mv ~/Downloads/credentials-xxx.json ./credentials.json
```

### C. Crear Google Sheet

1. **Crear nuevo Sheet**: https://sheets.google.com
2. **Renombrar** pestaña a "Products"
3. **Headers en fila 1**:
   ```
   A: sku | B: name | C: category | D: price_ars | E: stock
   ```
4. **Agregar algunos productos** de prueba
5. **Compartir Sheet**:
   - Click "Share"
   - Agregar email del service account (está en credentials.json)
   - Rol: Editor
6. **Copiar Sheet ID** de la URL:
   ```
   https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit
   ```

### D. Configurar en .env

```bash
GOOGLE_SHEETS_CREDENTIALS=credentials.json
GOOGLE_SHEET_ID=tu_sheet_id_aquí
```

### E. Test

```bash
python3 -c "
from bot_sales.integrations.sheets_sync import SheetsSync

sync = SheetsSync(
    sheet_id='TU_SHEET_ID',
    credentials_file='credentials.json'
)

result = sync.sync_inventory('catalog_extended.csv')
print(f'✅ Synced {result[\"updated_count\"]} products')
"
```

---

## Integración 4: MercadoPago (Opcional)

### A. Crear Cuenta

1. **Ir a**: https://www.mercadopago.com.ar/developers
2. **Crear aplicación**
3. **Obtener credenciales**:
   - Access Token (producción)
   - Public Key

### B. Configurar en .env

```bash
MERCADOPAGO_ACCESS_TOKEN=APP_USR-xxxxxxxxx
MERCADOPAGO_PUBLIC_KEY=APP_USR-xxxxxxxxx
```

### C. Test

```bash
python3 -c "
from bot_sales.integrations.mp_client import MercadoPagoClient

mp = MercadoPagoClient()
link = mp.create_payment_link(
    title='Test Product',
    price=10000
)
print(f'✅ Payment link: {link}')
"
```

---

# PARTE 3: TESTING LOCAL COMPLETO (1 hora)

## Test 1: Bot en Terminal

```bash
# CLI chat
python3 bot_cli.py chat

# Probar:
> Hola
> Qué Herramientas tenés?
> Cuánto sale el 15?
> Lo quiero
> exit
```

## Test 2: Admin Dashboard

```bash
# Terminal separada
cd dashboard
python app.py

# Abrir navegador:
# http://localhost:5000

# Login:
# User: admin
# Pass: [ADMIN_PASSWORD]

# Verificar:
# - Stats carguen
# - Ventas se listen
# - Productos se listen
```

## Test 3: Web Widget

```bash
# Abrir en navegador:
open static/widget_v2.html

# Testear conversación completa
```

## Test 4: WhatsApp (si configuraste)

```bash
# Asegurar que server está corriendo
python3 whatsapp_server.py

# En otra terminal
ngrok http 5001

# Enviar mensajes desde WhatsApp
```

---

# PARTE 4: DEPLOYMENT A PRODUCCIÓN CON RAILWAY (1-2 horas)

## Por qué Railway

**Railway es perfecto para este bot porque**:
- ✅ Deploy en 5 minutos
- ✅ Auto-deploy con Git push
- ✅ SSL/HTTPS automático
- ✅ $5/mes (súper económico)
- ✅ No necesitás manejar servidores
- ✅ Logs en vivo integrados
- ✅ Soporta múltiples servicios (Dashboard + WhatsApp)

**Puede manejar tranquilamente**:
- 100-200 conversaciones/día
- 50 usuarios simultáneos
- Todas las integraciones (OpenAI, Twilio, Sheets, MP)
- SQLite persistente (o Postgres si escalás)

---

## Paso 1: Preparar Proyecto para Railway

### A. Crear archivos de configuración

```bash
cd ~/Desktop/iphone-bot-demo

# 1. Crear Procfile (define qué correr)
cat > Procfile << 'EOF'
web: python dashboard/app.py
EOF

# 2. Crear railway.json (configuración Railway)
cat > railway.json << 'EOF'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
EOF

# 3. Crear runtime.txt (versión Python)
echo "python-3.11.0" > runtime.txt

# 4. Actualizar .gitignore
cat >> .gitignore << 'EOF'
.env
*.db
__pycache__/
*.pyc
logs/
backups/
cache.db
.DS_Store
EOF
```

### B. Inicializar Git (si no está)

```bash
# Verificar si ya está
git status

# Si dice "not a git repository", inicializar:
git init
git add .
git commit -m "Initial commit - Sales Bot ready for Railway"
```

### C. Crear repo en GitHub (opcional pero recomendado)

**Opción 1: Desde la terminal** (requiere GitHub CLI):
```bash
# Instalar gh CLI
brew install gh  # Mac
# O descargar de: https://cli.github.com/

# Login
gh auth login

# Crear repo
gh repo create iphone-bot-demo --private --source=. --push
```

**Opción 2: Manual**:
1. Ir a https://github.com/new
2. Nombre: `iphone-bot-demo`
3. Private
4. Create repository
5. Seguir instrucciones para push

```bash
git remote add origin https://github.com/tu-usuario/iphone-bot-demo.git
git branch -M main
git push -u origin main
```

---

## Paso 2: Deploy en Railway

### A. Crear cuenta

1. **Ir a**: https://railway.app
2. **Sign up** → Elegir "Login with GitHub"
3. **Autorizar** Railway a acceder a tus repos

### B. Crear proyecto

1. **Dashboard** → Click "New Project"
2. **Deploy from GitHub repo**
3. **Seleccionar** `iphone-bot-demo`
4. Railway detecta automáticamente que es Python

**Lo que Railway hace automáticamente**:
- ✅ Lee `requirements.txt`
- ✅ Instala todas las dependencias
- ✅ Lee `Procfile`
- ✅ Inicia el servicio web
- ✅ Genera una URL pública

### C. Configurar Variables de Entorno

1. **En Railway Dashboard** → Tu proyecto → **Variables**
2. **Click** "Raw Editor"
3. **Copiar y pegar** esto (reemplazando con tus valores reales):

```bash
# OpenAI (ESENCIAL)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx

# Email (opcional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_email@gmail.com
SMTP_PASSWORD=tu_app_password_16_chars

# WhatsApp Twilio (opcional)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=tu_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Google Sheets (opcional)
GOOGLE_SHEET_ID=tu_sheet_id
GOOGLE_SHEETS_CREDENTIALS=credentials.json

# MercadoPago (opcional)
MERCADOPAGO_ACCESS_TOKEN=APP_USR-xxxx
MERCADOPAGO_PUBLIC_KEY=APP_USR-xxxx

# Config
LOG_LEVEL=INFO
```

4. **Click** "Update Variables"

### D. Obtener URL pública

1. **Settings** → **Domains**
2. **Generate Domain**
3. Copiar la URL (ejemplo: `sales-bot-production.up.railway.app`)

**¡Tu bot ya está online!** 🎉

---

## Paso 3: Configurar Servicio WhatsApp (Opcional)

Si querés WhatsApp funcionando, necesitás un segundo servicio:

### A. Agregar servicio WhatsApp

1. **En tu proyecto Railway** → Click "New"
2. **Empty Service**
3. **Settings** → Nombre: "whatsapp-bot"
4. **Variables** → Copiar las mismas de arriba
5. **Settings** → Start Command: `python whatsapp_server.py`

### B. Generar dominio para webhook

1. **whatsapp-bot service** → Settings → Domains
2. **Generate Domain**
3. Copiar URL del webhook:
```
https://tu-whatsapp-service.up.railway.app/webhooks/meta
```

### C. Configurar en Twilio

1. **Twilio Console** → Messaging → WhatsApp Sandbox
2. **When a message comes in**:
   - Pegar: `https://tu-whatsapp-service.up.railway.app/webhooks/meta`
   - Method: POST
3. **Save**

### D. Test

Enviar mensaje de WhatsApp al número de Twilio.
Deberías recibir respuesta del bot!

---

## Paso 4: Verificar Deployment

### A. Ver logs en vivo

```
Railway Dashboard → Tu servicio → Logs
```

Deberías ver:
```
🖥️  ADMIN DASHBOARD
URL: http://0.0.0.0:5000
```

### B. Abrir Dashboard

```
https://tu-app.up.railway.app/login
```

Login:
- User: `admin`
- Pass: `[ADMIN_PASSWORD]`

### C. Test rápido

```bash
# Desde tu terminal local
curl https://tu-app.up.railway.app/api/stats
```

Debería devolver JSON con stats.

---

## Paso 5: Configuración Post-Deploy

### A. Cambiar password del admin

Railway → Variables → Agregar:
```
ADMIN_USERNAME=tu_usuario
ADMIN_PASSWORD=tu_password_seguro
```

**O** editar `dashboard/app.py` y hacer commit.

### B. Subir credentials.json (Google Sheets)

Si usás Google Sheets:

1. **Railway Dashboard** → Variables
2. **Agregar variable** `GOOGLE_SHEETS_CREDENTIALS_JSON`
3. **Copiar todo el contenido** de `credentials.json` como string
4. **Actualizar código** para leer de variable en vez de archivo

O más fácil: **Subir archivo**
```bash
# Railway CLI
npm i -g @railway/cli
railway login
railway link
railway volumes create
# Subir archivo al volume
```

### C. Activar persistencia (SQLite)

1. **Railway** → Settings → **Volumes**
2. **Add Volume**:
   - Mount path: `/app/data`
   - Nombre: `salesbot-db`

3. **Actualizar código** para usar `/app/data/`:
```python
# En database.py
DB_PATH = os.getenv('DB_PATH', '/app/data/ferreteria.db')
```

Hacer commit y push → Auto-redeploy.

---

## Paso 6: Auto-Deploy Configurado

Desde ahora, **cada vez que hagas**:

```bash
git add .
git commit -m "Mejora X"
git push
```

**Railway automáticamente**:
1. Detecta el push
2. Rebuild
3. Redeploy
4. Sin downtime

**Ver progreso**: Railway Dashboard → Deployments

---

# PARTE 5: CONFIGURACIÓN DE DOMINIO

## Paso 1: Comprar Dominio

- **Namecheap**: https://www.namecheap.com
- **GoDaddy**: https://www.godaddy.com
- Ejemplo: `salesbot-{tu-negocio}.com` (~$10/año)

## Paso 2: Configurar DNS

**Si usás Railway/Heroku**:
1. Panel del dominio → DNS Settings
2. Agregar CNAME:
   ```
   Type: CNAME
   Host: @
   Value: tu-app.up.railway.app
   ```

**Si usás VPS**:
1. DNS Settings
2. Agregar A Record:
   ```
   Type: A
   Host: @
   Value: IP_de_tu_servidor
   ```

**Esperar** 1-48hs para propagación DNS.

---

# PARTE 6: MONITOREO Y MANTENIMIENTO

## Monitoreo con Railway

### Logs en Vivo

**Railway tiene logs integrados**:
1. Dashboard → Tu servicio → **Logs**
2. Ver en tiempo real
3. Buscar/filtrar por keyword

**Desde CLI**:
```bash
railway logs
```

### Métricas

**Railway Dashboard** muestra:
- CPU usage
- Memory usage
- Network traffic
- Response times
- Error rate

### Alertas

1. **Settings** → **Webhooks**
2. Configurar notificación a Discord/Slack cuando:
   - Deploy falla
   - Service crashea
   - Alta CPU/memoria

### Setup Sentry (Opcional - Error Tracking Avanzado)

```bash
# Instalar
pip install sentry-sdk

# Agregar a requirements.txt
echo "sentry-sdk>=1.40.0" >> requirements.txt
```

**Configurar** en `bot_sales/__init__.py`:
```python
import sentry_sdk
import os

if os.getenv('SENTRY_DSN'):
    sentry_sdk.init(
        dsn=os.getenv('SENTRY_DSN'),
        traces_sample_rate=1.0,
        environment="production"
    )
```

**Railway Variables**:
```
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
```

---

## Backups con Railway

### Opción 1: Railway Volumes (Automático)

Railway hace snapshots automáticos de los volumes.

### Opción 2: Backup manual programado

**Crear script** `backup_to_s3.py`:
```python
from bot_sales.maintenance.backup import BackupSystem
import boto3
from datetime import datetime

# Crear backup
backup = BackupSystem()
backup_file = backup.create_backup()

# Upload a S3 (opcional)
s3 = boto3.client('s3')
s3.upload_file(
    backup_file,
    'my-bot-backups',
    f'backup-{datetime.now().isoformat()}.db'
)
```

**Railway Cron** (beta):
```bash
railway cron add "0 3 * * *" "python backup_to_s3.py"
```

---

## Updates y CI/CD

**Railway auto-deploys** cuando hacés push:

```bash
# Hacer cambios
nano bot_sales/bot.py

# Commit
git add .
git commit -m "Mejora en el bot"

# Push
git push

# Railway auto-detecta y redeploy
# Ver progreso en Dashboard
```

**Rollback** si algo falla:
```
Railway Dashboard → Deployments → Click en deploy anterior → Redeploy
```

---

# PARTE 7: CHECKLIST FINAL DE PRODUCCIÓN

## Pre-Launch Checklist

- [ ] OpenAI API key configurado
- [ ] Email SMTP funcionando
- [ ] WhatsApp Twilio/Meta configurado
- [ ] Base de datos inicializada
- [ ] Catálogo cargado
- [ ] Políticas personalizadas
- [ ] .env configurado (NO commitear!)
- [ ] Tests locales pasando
- [ ] Dashboard funciona
- [ ] Widget funciona
- [ ] Logs configurados
- [ ] Backups configurados
- [ ] SSL/HTTPS activo
- [ ] Dominio apuntando
- [ ] Monitoreo (Sentry) activo

## Post-Launch Checklist

- [ ] Enviar mensaje de prueba por WhatsApp
- [ ] Verificar email de confirmación
- [ ] Verificar admin dashboard
- [ ] Monitorear logs primeras 24hs
- [ ] Verificar backup se creó
- [ ] Documentar credenciales en lugar seguro
- [ ] Configurar alertas de uptime
- [ ] Testear flujo completo de venta

---

# PARTE 8: TROUBLESHOOTING

## Problema: Bot no responde

**Verificar**:
```bash
# OpenAI key
echo $OPENAI_API_KEY

# Logs
tail -f logs/sales_bot.log

# Test manual
python3 -c "from bot_sales.bot import SalesBot; bot = SalesBot(); print(bot.process_message('test', 'hola'))"
```

## Problema: WhatsApp no recibe mensajes

**Verificar**:
1. Twilio webhook está configurado
2. ngrok/servidor está corriendo
3. Webhook HTTPS (no HTTP)
4. Logs del servidor

## Problema: Dashboard no carga

**Verificar**:
```bash
# Puerto ocupado
lsof -i :5000

# Permisos
ls -la dashboard/

# Logs Flask
cd dashboard && python app.py
```

## Problema: Emails no llegan

**Verificar**:
1. Gmail app password correcto
2. 2FA habilitado
3. SMTP puerto 587
4. Test directo

---

# PARTE 9: PRÓXIMOS PASOS

## Semana 1
- [ ] Monitorear métricas diarias
- [ ] Ajustar respuestas según feedback
- [ ] Optimizar FAQs

## Semana 2-4
- [ ] Analizar conversiones
- [ ] A/B test de mejoras
- [ ] Agregar más productos

## Mes 2+
- [ ] Fine-tuning con datos reales
- [ ] Expansión a nuevos canales
- [ ] Automatizaciones adicionales

---

# 📞 SOPORTE

**Logs para debug**:
- `logs/sales_bot.log` - Log principal
- `logs/sales_bot.error.log` - Solo errores

**Comandos útiles**:
```bash
# Ver stats
python3 bot_cli.py dashboard

# Ver feedback
python3 bot_cli.py cache stats

# Export datos
python3 bot_cli.py export
```

---

# ✅ RESUMEN EJECUTIVO

**Tiempo total estimado**: 3-4 horas (con Railway)

**Pasos críticos**:
1. Setup local (30min)
2. OpenAI API key (5min) ← ESENCIAL
3. Testing local (1h)
4. Deploy a Railway (15min) ← MUY RÁPIDO
5. Configurar WhatsApp (30min)
6. Variables de entorno (15min)

**Costos mensuales (Railway)**:
- Railway: $5/mes (incluye hosting + SSL + auto-deploy)
- OpenAI API: $20-50/mes (depende del uso)
- Twilio WhatsApp: $5-20/mes (depende de mensajes)
- Dominio (opcional): $10/año = $1/mes
- **Total**: ~$30-75/mes

**Comparación con otras opciones**:
- Heroku: $7-13/mes (más caro)
- VPS (DigitalOcean): $6/mes (más complejo, más trabajo)
- Railway: $5/mes ⭐ **MEJOR RELACIÓN PRECIO/SIMPLICIDAD**

**ROI esperado**: 
- Bot automatiza 70-80% de consultas
- Ahorro de 2-4 horas/día de atención manual
- Disponibilidad 24/7
- Primera venta paga el servicio del mes

---

¡Éxito! 🚀
