# 📦 Gestión de Stock Automatizada

Este bot soporta múltiples formas de mantener el stock actualizado. Elegí la que mejor se adapte a tu operación.

## Opción 1: Email (Automático) ✉️

Si tu proveedor te envía un mail diario, el sistema puede leerlo solo.

### Configuración
1. Abrí `.env` y agregá tus credenciales de correo (usar "App Password" si es Gmail):
   ```ini
   EMAIL_IMAP_SERVER=imap.gmail.com
   EMAIL_USER=tu@email.com
   EMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx
   EMAIL_SEARCH_SUBJECT="Lista de Precios"
   ```

2. Probá el script manualmente:
   ```bash
   python scripts/update_stock_from_email.py
   ```

3. Programalo (Cron/Task Scheduler) para correr 2 veces al día.

### Formato esperado del CSV adjunto
El script busca columnas como `sku`, `stock` (o `cantidad`), y `precio`. No importa el orden.

---

## Opción 2: Google Sheets (Nube) ☁️

Ideal si trabajás en equipo. Editás en Drive y el bot se actualiza.

1. Creá un Sheet con las columnas: `sku`, `category`, `model`, `storage_gb`, `color`, `stock_qty`, `price_ars`.
2. Configura `GOOGLE_SHEET_ID` en `.env`.
3. El bot sincronizará automáticamente cada X minutos (o al reiniciar).

---

## Opción 3: Manual (Dashboard) 🖥️

Para ajustes rápidos (ej: vendiste el último en el local).

1. Entrá al Dashboard: `http://localhost:5001/products`
2. Buscá el producto.
3. Editá el stock y guardá.

## ⚠️ Jerarquía de Verdad

1. **Base de Datos (SQLite)**: Es la verdad absoluta del bot en tiempo real.
2. **Inputs**: El mail o Sheet *actualizan* la base de datos.
3. **Reservas**: El bot descuenta stock "lógico" cuando alguien reserva, aunque físicamente siga en el estante por 30 mins.
