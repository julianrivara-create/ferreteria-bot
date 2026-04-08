# Plan de Implementación: Notificaciones por Email

## 🎯 Objetivo
Enviar correos electrónicos automáticos en momentos clave del proceso de venta (confirmación de pedido, alerta de stock, etc.).

## 🏗 Arquitectura

### 1. Nuevo Módulo: `bot_sales/integrations/email_client.py`
Manejará el envío de correos.

```python
class EmailClient:
    def __init__(self, smtp_config=None):
        self.config = smtp_config
    
    def send_order_confirmation(self, to_email: str, order_details: dict):
        """
        Envía confirmación de compra.
        En modo DEMO/MOCK: Imprimir en consola el "email" enviado.
        """
        subject = f"Confirmación de Pedido #{order_details['id']}"
        body = self._render_template("confirmation", order_details)
        
        if not self.config:
            print(f"📧 [MOCK EMAIL] To: {to_email} | Subject: {subject}")
            print("-" * 20)
            print(body)
            print("-" * 20)
            return True
            
        # Implementación SMTP real aquí
        pass

    def _render_template(self, template_name, context):
        # Simple string formatting for now
        pass
```

### 2. Actualización: `business_logic.py`
Incorporar `EmailClient`.
- Al confirmar una venta (`confirmar_venta`), llamar a `send_order_confirmation` si tenemos el email del cliente.
- Necesitamos pedir el email al usuario si no lo tenemos.

### 3. Actualización: `chatgpt.py` (Prompt)
- Entrenar al bot para que pida el **email** además del nombre y teléfono al tomar los datos del cliente.

## 📝 Pasos
1.  Crear `bot_sales/integrations/email_client.py`.
2.  Actualizar `BusinessLogic` para instanciar y usar `EmailClient`.
3.  Modificar el System Prompt en `chatgpt.py` para requerir el email.
4.  Probar con `demo_final.py` (el mock debería imprimir el email en consola).
