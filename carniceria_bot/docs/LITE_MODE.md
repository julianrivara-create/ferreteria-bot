# 🤖 Lite Bot (Modo Básico)

El sistema ahora soporta un "Modo Básico" para clientes que buscan una solución más económica.

## ¿Qué hace el Lite Bot?
1.  **Preguntas Frecuentes**: Responde automáticamente todo lo que esté en `faqs.json`.
2.  **Stock Simple**: Si detecta "precio" o "stock", muestra una lista rápida.
3.  **Handoff Inmediato**: Para **CUALQUIER** otra cosa, dice: "Te paso con un humano" y alerta al dueño.
4.  **Cero Costo AI**: No usa OpenAI API (ahorro total de tokens).

## ¿Cómo activarlo?
En el archivo `.env`:

```ini
LITE_MODE=true
```

## Diferencias
| Feature | Full AI Bot (Premium) | Lite Bot (Básico) |
| :--- | :--- | :--- |
| **Inteligencia** | GPT-4 (Entiende todo) | Palabras Clave (Básico) |
| **Venta** | Cierra ventas activamente | Solo informa |
| **Handoff** | Solo si hay problemas | Ante cualquier duda |
| **Costo** | $$ (OpenAI) | Gratis (Solo server) |

Ideal para vender como entrada de gama ("Plan Start") y luego upgradear al "Plan Pro" con IA.
