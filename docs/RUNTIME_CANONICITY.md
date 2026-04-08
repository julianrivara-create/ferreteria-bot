# Runtime canónico del bot

## Resumen

La implementación canónica del bot que atiende el runtime web y los canales activos vive en:

- `app/*`

La carpeta:

- `bot_sales/*`

queda mantenida únicamente como compatibilidad temporal para rutas legacy, scripts viejos y soporte interno mientras termina el retiro progresivo.

## Qué significa en la práctica

- Los cambios críticos de comportamiento deben implementarse primero en `app/*`.
- La cobertura principal del bot real debe vivir en tests del runtime `app/*`.
- Los entrypoints nuevos deben apuntar al stack `app/*`.
- Si un wrapper legacy sigue existiendo, debe anunciarse explícitamente como compatibilidad.

## Entry points canónicos

- Web/API pública: `app/api/*`
- Orquestación del bot: `app/services/bot_core.py`
- Bot principal: `app/bot/bot.py`
- CLI interactiva: `app/bot/connectors/cli.py`
- WhatsApp runtime: `app/bot/connectors/whatsapp.py`
- WSGI productivo: `wsgi.py`

## Regla operativa para fallback legacy

- En desarrollo/local, `wsgi.py` puede caer al legacy para no bloquear debugging.
- En staging/producción, el fallback legacy debe quedar deshabilitado por defecto.
- Si hace falta usarlo como puente de emergencia, se habilita explícitamente con `ALLOW_LEGACY_FALLBACK=true` y se trata como incidente, no como estado normal.

## Estado de `bot_sales/*`

`bot_sales/*` no se elimina de golpe, pero ya no debe presentarse como implementación equivalente del bot real.

Usos aceptables por ahora:

- wrappers de compatibilidad
- tests legacy no críticos
- utilidades que todavía no migraron

Usos no aceptables:

- agregar nueva cobertura crítica ahí en lugar de `app/*`
- introducir fixes principales solo en legacy
- seguir documentándolo como ruta principal del producto
