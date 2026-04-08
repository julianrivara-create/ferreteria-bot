import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any

class EmailClient:
    """
    Cliente de email con soporte SMTP real
    """
    
    def __init__(self, smtp_host: str = None, smtp_port: int = None,
                 smtp_user: str = None, smtp_password: str = None,
                 mock_mode: bool = True):
        """
        Args:
            smtp_host: SMTP server (e.g., smtp.gmail.com)
            smtp_port: Port (587 for TLS, 465 for SSL)
            smtp_user: Email address
            smtp_password: App password (not regular password!)
            mock_mode: If True, only prints to console
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port or 587
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.mock_mode = mock_mode or not smtp_host
        
        self.logger = logging.getLogger(__name__)
        
        if self.mock_mode:
            self.logger.info("Email client in MOCK mode")
        else:
            self.logger.info(f"Email client configured: {smtp_host}:{smtp_port}")
    
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
        subject = f"🎉 Pedido Confirmado #{order_details.get('order_id', 'N/A')}"
        
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
                                    {order_details.get('order_id', 'N/A')}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Producto:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {order_details.get('producto', 'N/A')}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Precio:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right; 
                                           color: #667eea; font-size: 18px;">
                                    ${order_details.get('precio', 0):,}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Método de Pago:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {order_details.get('metodo_pago', 'N/A')}
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; color: #666;">Zona:</td>
                                <td style="padding: 10px 0; font-weight: bold; text-align: right;">
                                    {order_details.get('zona', 'N/A')}
                                </td>
                            </tr>
                        </table>
                    </div>
                    
                    {payment_link_html}
                    
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
        text = f"""
🎉 PEDIDO CONFIRMADO

Gracias por tu compra!

DETALLES DEL PEDIDO:
-------------------
Pedido #: {order_details.get('order_id', 'N/A')}
Producto: {order_details.get('producto', 'N/A')}
Precio: ${order_details.get('precio', 0):,}
Método de Pago: {order_details.get('metodo_pago', 'N/A')}
Zona: {order_details.get('zona', 'N/A')}
"""
        
        if order_details.get('payment_link'):
            text += f"\nLink de Pago:\n{order_details['payment_link']}\n"
        
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
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            self.logger.info(f"Email sent successfully to {to_email}")
            return {'status': 'sent', 'to': to_email}
        
        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            return {'status': 'error', 'message': str(e)}
