#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Slack File Upload Handler
Process uploaded files (catalogs, images, documents)
"""

import logging
import requests
import csv
import io
from typing import Dict, Any, List, Optional
from PIL import Image

logger = logging.getLogger(__name__)

class SlackFileHandler:
    """Handle file uploads from Slack"""
    
    def __init__(self, slack_connector, db, config):
        """
        Initialize file handler
        
        Args:
            slack_connector: SlackConnector instance
            db: Database instance
            config: Config instance
        """
        self.slack = slack_connector
        self.db = db
        self.config = config
    
    def handle_file_upload(self, file_data: Dict, user_id: str, channel_id: str) -> Dict:
        """
        Handle file upload event
        
        Args:
            file_data: File data from Slack
            user_id: Uploader user ID
            channel_id: Channel ID
            
        Returns:
            Processing result
        """
        file_type = file_data.get('mimetype', '')
        file_name = file_data.get('name', 'unknown')
        file_url = file_data.get('url_private', '')
        
        logger.info(f"Processing file upload: {file_name} ({file_type})")
        
        try:
            # Download file
            file_content = self._download_file(file_url)
            
            # Process based on type
            if file_type == 'text/csv' or file_name.endswith('.csv'):
                result = self._process_catalog_csv(file_content, user_id, channel_id)
            elif file_type.startswith('image/'):
                result = self._process_product_image(file_content, file_data, user_id, channel_id)
            elif file_type == 'application/pdf':
                result = self._process_pdf(file_content, file_name, user_id, channel_id)
            elif file_type in ['application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                result = self._process_excel(file_content, user_id, channel_id)
            else:
                result = {
                    'success': False,
                    'message': f"❌ Tipo de archivo no soportado: {file_type}"
                }
            
            # Send result to channel
            self.slack.send_message(channel_id, result['message'])
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            error_msg = f"❌ Error procesando archivo: {str(e)}"
            self.slack.send_message(channel_id, error_msg)
            return {'success': False, 'message': error_msg}
    
    def _download_file(self, url: str) -> bytes:
        """Download file from Slack"""
        headers = {
            'Authorization': f'Bearer {self.slack.bot_token}'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        return response.content
    
    def _process_catalog_csv(self, content: bytes, user_id: str, channel_id: str) -> Dict:
        """
        Process product catalog CSV
        
        Expected columns: sku, modelo, categoria, almacenamiento, precio, stock
        """
        try:
            # Parse CSV
            csv_text = content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_text))
            
            products_added = 0
            products_updated = 0
            errors = []
            
            for row in csv_reader:
                try:
                    # Validate required fields
                    required_fields = ['sku', 'modelo', 'precio']
                    if not all(field in row for field in required_fields):
                        errors.append(f"Fila sin campos requeridos: {row}")
                        continue
                    
                    # Prepare product data
                    product_data = {
                        'sku': row['sku'].strip(),
                        'modelo': row['modelo'].strip(),
                        'categoria': row.get('categoria', '').strip(),
                        'almacenamiento': row.get('almacenamiento', '').strip(),
                        'price_ars': float(row['precio']),
                        'stock': int(row.get('stock', 0)),
                        'condicion': row.get('condicion', 'Nuevo').strip()
                    }
                    
                    # Check if product exists
                    existing = self.db.get_product_by_sku(product_data['sku'])
                    
                    if existing:
                        # Update
                        self.db.update_product(product_data['sku'], product_data)
                        products_updated += 1
                    else:
                        # Insert
                        self.db.insert_product(product_data)
                        products_added += 1
                        
                except Exception as e:
                    errors.append(f"Error en fila {row.get('sku', 'unknown')}: {str(e)}")
            
            # Build result message
            message = f"✅ *Catálogo procesado*\n\n"
            message += f"• Productos agregados: {products_added}\n"
            message += f"• Productos actualizados: {products_updated}\n"
            
            if errors:
                message += f"\n⚠️ Errores ({len(errors)}):\n"
                for error in errors[:5]:  # Show first 5
                    message += f"• {error}\n"
                if len(errors) > 5:
                    message += f"• ... y {len(errors) - 5} más\n"
            
            return {'success': True, 'message': message}
            
        except Exception as e:
            return {'success': False, 'message': f"❌ Error procesando CSV: {str(e)}"}
    
    def _process_product_image(self, content: bytes, file_data: Dict, user_id: str, channel_id: str) -> Dict:
        """Process product image upload"""
        try:
            # Open image
            image = Image.open(io.BytesIO(content))
            
            # Get image info
            width, height = image.size
            format_type = image.format
            
            # TODO: Save image to storage (S3, local, etc.)
            # For now, just acknowledge
            
            file_name = file_data.get('name', 'image')
            
            message = f"✅ *Imagen procesada*\n\n"
            message += f"• Archivo: {file_name}\n"
            message += f"• Dimensiones: {width}x{height}\n"
            message += f"• Formato: {format_type}\n\n"
            message += f"_Para asociar a un producto, usa: `/product_image {file_name} SKU`_"
            
            return {'success': True, 'message': message}
            
        except Exception as e:
            return {'success': False, 'message': f"❌ Error procesando imagen: {str(e)}"}
    
    def _process_pdf(self, content: bytes, file_name: str, user_id: str, channel_id: str) -> Dict:
        """Process PDF document"""
        try:
            # TODO: Extract text from PDF using PyPDF2 or similar
            # For now, just acknowledge
            
            size_kb = len(content) / 1024
            
            message = f"✅ *PDF recibido*\n\n"
            message += f"• Archivo: {file_name}\n"
            message += f"• Tamaño: {size_kb:.1f} KB\n\n"
            message += f"_Procesamiento de PDFs en desarrollo_"
            
            return {'success': True, 'message': message}
            
        except Exception as e:
            return {'success': False, 'message': f"❌ Error procesando PDF: {str(e)}"}
    
    def _process_excel(self, content: bytes, user_id: str, channel_id: str) -> Dict:
        """Process Excel file"""
        try:
            # TODO: Process Excel using pandas or openpyxl
            # For now, suggest CSV
            
            message = f"⚠️ *Archivo Excel detectado*\n\n"
            message += f"Por favor, exporta el archivo como CSV para procesarlo.\n"
            message += f"_Soporte para Excel próximamente_"
            
            return {'success': False, 'message': message}
            
        except Exception as e:
            return {'success': False, 'message': f"❌ Error procesando Excel: {str(e)}"}
    
    def associate_image_to_product(self, image_url: str, sku: str) -> bool:
        """
        Associate uploaded image to product
        
        Args:
            image_url: URL of uploaded image
            sku: Product SKU
            
        Returns:
            Success boolean
        """
        try:
            self.db.update_product(sku, {'image_url': image_url})
            logger.info(f"Associated image to product {sku}")
            return True
        except Exception as e:
            logger.error(f"Error associating image: {e}")
            return False
