import logging
import csv
import json
import os
from typing import Dict, List, Any
from datetime import datetime

class SheetsSync:
    """
    Sincronización con Google Sheets
    Versión mejorada con Google Sheets API real
    """
    
    def __init__(self, sheet_id: str = None, credentials_file: str = None):
        self.sheet_id = sheet_id
        self.credentials_file = credentials_file
        self.logger = logging.getLogger(__name__)
        
        # Determinar modo
        self.mock_mode = credentials_file is None or sheet_id is None
        
        if self.mock_mode:
            self.logger.info("Google Sheets Sync in MOCK mode")
        else:
            self._init_google_client()
    
    def _init_google_client(self):
        """Inicializa cliente de Google Sheets API"""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            
            # Cargar credentials
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            
            # Build service
            self.service = build('sheets', 'v4', credentials=creds)
            self.logger.info(f"Google Sheets API initialized. Sheet ID: {self.sheet_id}")
        
        except ImportError:
            self.logger.warning("google-api-python-client not installed. Run: pip install google-api-python-client google-auth")
            self.mock_mode = True
        
        except Exception as e:
            self.logger.error(f"Failed to initialize Google Sheets API: {e}")
            self.mock_mode = True
    
    def sync_inventory(self, local_catalog_file: str = "catalog_extended.csv") -> Dict:
        """
        Sincroniza inventario DESDE Google Sheets hacia archivo local
        
        Returns:
            {
                'status': 'success' | 'error',
                'updated_count': int,
                'last_sync': str
            }
        """
        if self.mock_mode:
            return self._mock_sync(local_catalog_file)
        
        try:
            # Leer datos del Sheet
            sheet = self.service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.sheet_id,
                range='Products!A1:Z1000'  # Ajustar según tu sheet
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return {
                    'status': 'error',
                    'message': 'No data found in sheet'
                }
            
            # Escribir a CSV local
            with open(local_catalog_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(values)
            
            self.logger.info(f"Synced {len(values)} rows from Google Sheets")
            
            return {
                'status': 'success',
                'updated_count': len(values) - 1,  # -1 for header
                'last_sync': datetime.now().isoformat(),
                'source': 'google_sheets'
            }
        
        except Exception as e:
            self.logger.error(f"Sync failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def push_updates(self, updates: List[Dict]) -> Dict:
        """
        Envía actualizaciones HACIA Google Sheets
        
        Args:
            updates: Lista de {row, col, value} o {sku, field, value}
        
        Returns:
            {
                'status': str,
                'updated_count': int
            }
        """
        if self.mock_mode:
            self.logger.info(f"[MOCK] Would push {len(updates)} updates to Sheets")
            return {
                'status': 'mock_success',
                'updated_count': len(updates)
            }
        
        try:
            # Preparar batch update
            data = []
            for update in updates:
                if 'row' in update and 'col' in update:
                    # Actualización por posición
                    range_name = f"Products!{update['col']}{update['row']}"
                    data.append({
                        'range': range_name,
                        'values': [[update['value']]]
                    })
            
            if not data:
                return {'status': 'no_updates', 'updated_count': 0}
            
            # Ejecutar batch update
            body = {'valueInputOption': 'USER_ENTERED', 'data': data}
            result = self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=body
            ).execute()
            
            updated = result.get('totalUpdatedCells', 0)
            self.logger.info(f"Updated {updated} cells in Google Sheets")
            
            return {
                'status': 'success',
                'updated_count': updated
            }
        
        except Exception as e:
            self.logger.error(f"Push failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def update_stock(self, sku: str, new_stock: int) -> Dict:
        """
        Actualiza stock de un producto específico
        
        Args:
            sku: SKU del producto
            new_stock: Nuevo valor de stock
        """
        if self.mock_mode:
            self.logger.info(f"[MOCK] Would update stock for {sku} to {new_stock}")
            return {'status': 'mock_success'}
        
        try:
            # Buscar row del SKU
            sheet = self.service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.sheet_id,
                range='Products!A:A'  # Columna de SKUs
            ).execute()
            
            values = result.get('values', [])
            
            # Encontrar fila
            row_index = None
            for i, row in enumerate(values):
                if row and row[0] == sku:
                    row_index = i + 1  # 1-indexed
                    break
            
            if row_index is None:
                return {
                    'status': 'error',
                    'message': f'SKU {sku} not found'
                }
            
            # Actualizar (asumiendo stock en columna E)
            update_range = f"Products!E{row_index}"
            body = {'values': [[new_stock]]}
            
            sheet.values().update(
                spreadsheetId=self.sheet_id,
                range=update_range,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            self.logger.info(f"Updated stock for {sku} to {new_stock}")
            return {'status': 'success'}
        
        except Exception as e:
            self.logger.error(f"Stock update failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _mock_sync(self, local_file: str) -> Dict:
        """Mock sync - lee archivo local"""
        try:
            with open(local_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                products = list(reader)
            
            self.logger.info(f"[MOCK] Loaded {len(products)} products from {local_file}")
            
            return {
                'status': 'success',
                'mode': 'mock',
                'updated_count': len(products),
                'last_sync': datetime.now().isoformat(),
                'message': f'Mock sync successful ({len(products)} products)'
            }
        
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def setup_sheet_template(self) -> str:
        """
        Retorna URL de template de Google Sheet
        Y estructura recomendada
        """
        return """
📊 SETUP GOOGLE SHEETS:

1. Crear nuevo Google Sheet
2. Renombrar primer tab a "Products"
3. Agregar headers en fila 1:
   A: sku
   B: name
   C: category
   D: price_ars
   E: stock
   F: brand (opcional)
   G: color (opcional)
   H: storage_gb (opcional)

4. Completar con tus productos

5. Google Cloud Console setup:
   a) Ir a console.cloud.google.com
   b) Crear proyecto nuevo
   c) Habilitar "Google Sheets API"
   d) Crear Service Account
   e) Descargar credentials.json
   f) Compartir Sheet con email del service account

6. Configurar en código:
   from bot_sales.integrations.sheets_sync import SheetsSync
   
   sync = SheetsSync(
       sheet_id='YOUR_SHEET_ID',  # De la URL
       credentials_file='credentials.json'
   )
   
   sync.sync_inventory()

Más info: https://developers.google.com/sheets/api/quickstart/python
"""
