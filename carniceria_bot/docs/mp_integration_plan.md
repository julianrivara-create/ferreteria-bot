# Plan de Integración MercadoPago

## 🎯 Objetivo
Permitir que el bot genere eslabones de pago reales (o simulados en demo) para cerrar las ventas automáticamente.

## 🏗 Arquitectura

### 1. Nuevo Módulo: `bot_sales/integrations/mercadopago_client.py`
Manejará la comunicación con la API de MP.

```python
class MercadoPagoClient:
    def __init__(self, access_token):
        self.sdk = mercadopago.SDK(access_token)
    
    def create_preference(self, item_title, price, quantity, external_reference):
        # Crea la preferencia de pago
        pass
        
    def get_mock_link(self, item_title, price):
        # Genera un link simulado para demos
        return f"https://mpago.la/mock-{item_title.replace(' ', '-')}"
```

### 2. Actualización: `business_logic.py`
Modificar `confirmar_venta` para que, si el método es "MercadoPago", llame al cliente y retorne el link.

### 3. Actualización: `chatgpt.py`
El bot ya tiene la función `confirmar_venta`. Solo necesitamos asegurar que el prompt del sistema sepa que ahora devuelve un Link REAL que debe mostrar al usuario.

## 🧪 Estrategia de Mocking
Como es probable que no tengamos un `MP_ACCESS_TOKEN` real configurado todavía, el sistema debe ser capaz de funcionar en `mock_mode` devolviendo links falsos pero visualmente correctos, para que la demo no se rompa.

## 📝 Pasos de Implementación
1.  Crear `mercadopago_client.py`.
2.  Integrarlo en `BusinessLogic`.
3.  Actualizar `demo_final.py` para probar el flujo de pago.
4.  Agregar manejo de credenciales en `config.py`.
