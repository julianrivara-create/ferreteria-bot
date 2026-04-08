# 🚀 Dashboard Quick Start Guide

## 1. Start the Dashboard (Backend)

Ejecuta este comando siempre desde la carpeta `dashboard`:

ir a la carpeta
cd /Users/julian/Desktop/Dev:ai-labs:/iphone-bot-demo/dashboard

Despues 
cd dashboard
../.venv/bin/python app.py

*   **URL Local:** [http://localhost:5001](http://localhost:5001)
*   **User:** `admin`
*   **Pass:** `[ADMIN_PASSWORD]`

---

## 2. Expose via Ngrok

En una **nueva terminal**, ejecuta:

```bash
ngrok http 5001
```

Copia la URL que termina en `.ngrok-free.app` (ej. `https://a1b2-c3d4.ngrok-free.app`) y úsala para acceder desde fuera.

---

## 🛠 Troubleshooting

Si `app.py` falla por falta de módulos (`ModuleNotFoundError`), usa el comando "mágico" para reparar las dependencias en el entorno correcto:

```bash
cd dashboard
../.venv/bin/python -m pip install flask flask-cors
```
