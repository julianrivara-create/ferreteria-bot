# 📊 Dashboard Offline & Mock Data

Como parte del **Sprint 1.5**, hemos implementado un sistema robusto de datos de prueba (`mock data`) para el Dashboard.

Esto permite:
1.  **Desarrollar sin datos reales**: Ver gráficos y tablas llenas desde el día 1.
2.  **Demos efectivas**: Mostrar el potencial del dashboard sin tener que hacer 100 ventas reales.
3.  **Fallback automático**: Si la base de datos está vacía, el dashboard muestra datos simulados automáticamente.

## 📂 Organización del Proyecto

Hemos reorganizado el proyecto para mantener el foco en la versión de producción con ChatGPT, pero guardando los experimentos locales.

```
iphone-bot-demo/
├── .env                  # Configuración activa (ChatGPT por defecto)
├── bot_sales/            # Core del bot
├── dashboard/            # Admin Panel
│   ├── app.py            # Servidor Flask
│   ├── mock_service.py   # ✨ NUEVO: Servicio de datos simulados
│   └── templates/        # HTML
├── scripts/              # Herramientas y utilidades
└── experiments/          # 🧪 Experimentos aislados
    └── ollama/           # Integración local con Ollama (GLM-4, etc.)
```

## 🚀 Cómo probar el Dashboard Offline

1.  Asegurate de estar en el entorno virtual (si usas uno).
2.  Ejecuta el servidor:
    ```bash
    cd dashboard
    python app.py
    ```
3.  Abrí `http://localhost:5000` en tu navegador.
4.  Login: `admin` / `admin123`

**Verás:**
- Gráficos de ventas animados (datos simulados si tu DB está vacía).
- Métricas de revenue y conversión.
- Top productos vendidos.

## 🧹 Limpieza Realizada

- Se movieron todos los scripts y docs de Ollama a `experiments/ollama/`.
- Se restauró `.env` para usar la configuración estable de ChatGPT.
- El root del proyecto está limpio y enfocado.
