import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from ..config import config as bot_config

class EmailClient:
    """
    Cliente de email con soporte SMTP real
    """
    
    def __init__(
        self,
        smtp_host: str = None,
        smtp_port: int = None,
        smtp_user: str = None,
        smtp_password: str = None,
        mock_mode: Optional[bool] = None,
    ):
        """
        Args:
            smtp_host: SMTP server (e.g., smtp.gmail.com)
            smtp_port: Port (587 for TLS, 465 for SSL)
            smtp_user: Email address
            smtp_password: App password (not regular password!)
            mock_mode: If True, only prints to console. If None, auto-detect from SMTP config.
        """
        self.smtp_host = smtp_host or bot_config.SMTP_HOST
        self.smtp_port = smtp_port or bot_config.SMTP_PORT or 587
        self.smtp_user = smtp_user or bot_config.SMTP_USER
        self.smtp_password = smtp_password or bot_config.SMTP_PASSWORD
        if mock_mode is None:
            self.mock_mode = not all([self.smtp_host, self.smtp_user, self.smtp_password])
        else:
            self.mock_mode = bool(mock_mode)

        self.logger = logging.getLogger(__name__)
        
        if self.mock_mode:
            self.logger.info("Email client in MOCK mode")
        else:
            self.logger.info(f"Email client configured: {self.smtp_host}:{self.smtp_port}")

    @staticmethod
    def _pick(order_details: Dict[str, Any], *keys: str, default: Any = "N/A") -> Any:
        for key in keys:
            value = order_details.get(key)
            if value not in (None, ""):
                return value
        return default

    @staticmethod
    def _format_price(value: Any) -> str:
        if isinstance(value, (int, float)):
            return "$" + f"{int(value):,}".replace(",", ".")
        if value in (None, ""):
            return "$0"
        return str(value)
    
    def send_order_confirmation(self, to_email: str, order_details: Dict[str, Any]):
        """
        Envía email de confirmación de pedido
        
        Args:
            to_email: Email del cliente
            order_details: {
                'order_id': str,
                'producto': str,
                'precio': float,
                'metodo_pago': str,
                'zona': str,
                'payment_link': str (opcional)
            }
        """
        order_id = self._pick(order_details, "order_id", "sale_id")
        subject = f"🎉 Pedido Confirmado #{order_id}"
        
        # Generar HTML del email
        html_body = self._generate_order_html(order_details)
        
        # Fallback texto plano
        text_body = self._generate_order_text(order_details)
        
        return self._send_email(to_email, subject, text_body, html_body)
    
    def send_payment_link(self, to_email: str, payment_link: str, order_id: str):
        """Envía link de pago"""
        subject = f"💳 Link de Pago - Pedido #{order_id}"
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #667eea;">Link de Pago Listo! 💳</h2>
                <p>Tu pedido <strong>#{order_id}</strong> está reservado.</p>
                <p>Hacé click en el siguiente link para completar el pago:</p>
                <a href="{payment_link}" 
                   style="display: inline-block; background: #667eea; color: white; 
                          padding: 15px 30px; text-decoration: none; border-radius: 5px;
                          margin: 20px 0;">
                    Pagar Ahora
                </a>
                <p style="color: #666; font-size: 12px;">
                    Si el botón no funciona, copiá este link: {payment_link}
                </p>
            </body>
        </html>
        """
        
        text_body = f"Link de pago para pedido #{order_id}: {payment_link}"
        
        return self._send_email(to_email, subject, text_body, html_body)
    
    def _generate_order_html(self, order_details: Dict) -> str:
        """Genera HTML profesional para confirmación"""
        order_id = self._pick(order_details, "order_id", "sale_id")
        product_name = self._pick(order_details, "producto", "product_model")
        payment_method = self._pick(order_details, "metodo_pago", "payment_method")
        zone = self._pick(order_details, "zona", "entrega")
        price_raw = self._pick(order_details, "precio", "total_amount", "total_formatted", default=0)
        formatted_price = self._format_price(price_raw)

        payment_link_html = ""
        if order_details.get('payment_link'):
            payment_link_html = f"""
            <div style="margin: 20px 0; padding: 15px; background: #f0f0f0; border-radius: 5px;">
                <strong>Link de Pago:</strong><br>
                <a href="{order_details['payment_link']}" style="color: #667eea;">
                    {order_details['payment_link']}
                </a>
            </div>
            """

        transfer_instructions_html = ""
        if order_details.get("transfer_instructions_html"):
            transfer_instructions_html = f"""
            <div style="margin: 20px 0; padding: 15px; background: #eef7ff; border: 1px solid #cfe8ff; border-radius: 8px;">
                <strong>Datos para transferencia</strong>
                <div style="margin-top: 10px; color: #2f3a4a; line-height: 1.6;">
                    {order_details.get("transfer_instructions_html")}
                </div>
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background: white;">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                            padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0;">🎉 Pedido Confirmado!</h1>
                </div>
                
                <!-- Body -->
                <div style="padding: 30px;">
                    <h2 style="color: #333;">Gracias por tu compra!</h2>
                    <p style="color: #666; line-height: 1.6;">
                        Tu pedido ha sido confirmado exitosamente. 
                        Acá están los detalles:
                    </p>
                    
                    <!-- Order Details -->
                    <div style="background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Pedido #:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {order_id}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Producto:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {product_name}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Precio:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right; 
                                           color: #667eea; font-size: 18px;">
                                    {formatted_price}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Método de Pago:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {payment_method}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Zona:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {zone}
                                </td>
                            </tr>
                        </table>
                    </div>

                    {payment_link_html}
                    {transfer_instructions_html}
                    
                    <p style="color: #666; margin-top: 30px;">
                        Te contactaremos pronto para coordinar la entrega.
                    </p>
                    
                    <p style="color: #666;">
                        ¿Dudas? Respondé este email o escribinos por WhatsApp.
                    </p>
                </div>
                
                <!-- Footer -->
                <div style="background: #f0f0f0; padding: 20px; text-align: center; 
                            color: #999; font-size: 12px;">
                    <p>Sales Bot - Tu tienda de confianza 🛍️</p>
                    <p>Este es un email automático, por favor no responder.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _generate_order_text(self, order_details: Dict) -> str:
        """Genera versión texto plano"""
        order_id = self._pick(order_details, "order_id", "sale_id")
        product_name = self._pick(order_details, "producto", "product_model")
        payment_method = self._pick(order_details, "metodo_pago", "payment_method")
        zone = self._pick(order_details, "zona", "entrega")
        price_raw = self._pick(order_details, "precio", "total_amount", "total_formatted", default=0)
        formatted_price = self._format_price(price_raw)

        text = f"""
🎉 PEDIDO CONFIRMADO

Gracias por tu compra!

DETALLES DEL PEDIDO:
-------------------
Pedido #: {order_id}
Producto: {product_name}
Precio: {formatted_price}
Método de Pago: {payment_method}
Zona: {zone}
"""

        if order_details.get('payment_link'):
            text += f"\nLink de Pago:\n{order_details['payment_link']}\n"

        if order_details.get("transfer_instructions_text"):
            text += (
                "\nDatos para transferencia:\n"
                f"{order_details['transfer_instructions_text']}\n"
            )

        text += "\nTe contactaremos pronto para coordinar la entrega.\n\n"
        text += "Sales Bot - Tu tienda de confianza 🛍️"
        
        return text
    
    def _send_email(self, to_email: str, subject: str, text_body: str, html_body: str = None):
        """Envía el email"""
        
        if self.mock_mode:
            self.logger.info("=" * 60)
            self.logger.info("[MOCK EMAIL]")
            self.logger.info(f"To: {to_email}")
            self.logger.info(f"Subject: {subject}")
            self.logger.info("=" * 60)
            self.logger.info(text_body)
            self.logger.info("=" * 60)
            return {'status': 'mock_sent', 'to': to_email}
        
        try:
            # Crear mensaje
            msg = MIMEMultipart('alternative')
            msg['From'] = self.smtp_user
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Attach parts
            part1 = MIMEText(text_body, 'plain', 'utf-8')
            msg.attach(part1)
            
            if html_body:
                part2 = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(part2)

            # Conectar y enviar
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)

            with server:
                if self.smtp_port != 465:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            self.logger.info(f"Email sent successfully to {to_email}")
            return {'status': 'sent', 'to': to_email}
        
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            return {'status': 'error', 'message': str(e)}
