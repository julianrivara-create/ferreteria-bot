"""
Robust Google Sheets Stock Sync Module
Reads stock data from Google Sheets and updates Product.on_hand_qty in database
"""
import gspread
from google.oauth2.service_account import Credentials
import structlog
import json
import os
import time
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

logger = structlog.get_logger()

class SheetsSyncError(Exception):
    """Custom exception for sheets sync errors"""
    pass

class StockSheetSync:
    """Production-grade Google Sheets → DB stock sync"""
    
    def __init__(
        self,
        spreadsheet_id: str,
        worksheet_name: str = "STOCK",
        service_account_json: Optional[str] = None,
        service_account_path: Optional[str] = None
    ):
        """
        Initialize sync client
        
        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            worksheet_name: Name of worksheet to read (default: STOCK)
            service_account_json: JSON string of service account credentials
            service_account_path: Path to service account JSON file
        """
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        
        # Validate credentials
        if not service_account_json and not service_account_path:
            raise SheetsSyncError("No credentials provided (need JSON or path)")
        
        # Initialize gspread client
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
            
            if service_account_json:
                # Parse JSON from env var (Robust handling for Railway/dotenv escaping)
                clean_json = service_account_json.strip()
                
                # Remove outer quotes if present (e.g. '"{"type":...}"')
                if clean_json.startswith('"') and clean_json.endswith('"'):
                    clean_json = clean_json[1:-1]
                elif clean_json.startswith("'") and clean_json.endswith("'"):
                    clean_json = clean_json[1:-1]
                
                # Fix escaped newlines (e.g. literal "\n" -> actual newline)
                clean_json = clean_json.replace('\\n', '\n')
                
                # Fix escaped quotes (e.g. \" -> ")
                clean_json = clean_json.replace('\\"', '"')
                
                try:
                    creds_dict = json.loads(clean_json)
                except json.JSONDecodeError:
                    # Fallback: try loading original just in case
                    creds_dict = json.loads(service_account_json)
                    
                creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            else:
                # Load from file path
                if not os.path.exists(service_account_path):
                    raise SheetsSyncError(f"Credentials file not found: {service_account_path}")
                creds = Credentials.from_service_account_file(service_account_path, scopes=scopes)
            
            self.client = gspread.authorize(creds)
            logger.info("gspread_client_initialized", spreadsheet_id=spreadsheet_id)
            
        except json.JSONDecodeError as e:
            raise SheetsSyncError(f"Invalid service account JSON: {e}")
        except Exception as e:
            raise SheetsSyncError(f"Failed to initialize gspread: {e}")
    
    def _normalize_header(self, header: str) -> str:
        """Normalize header name (case-insensitive, strip spaces)"""
        return header.lower().strip().replace('_', '').replace(' ', '')
    
    def read_stock_data(self) -> List[Dict[str, any]]:
        """
        Read stock data from Google Sheet
        
        Returns:
            List of dicts: [{"sku": "ABC", "qty": 10}, ...]
            
        Raises:
            SheetsSyncError: If sheet/worksheet doesn't exist or can't be read
        """
        try:
            start_time = time.time()
            
            # Open spreadsheet
            # Open spreadsheet
            try:
                spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            except gspread.SpreadsheetNotFound:
                raise SheetsSyncError(
                    f"Spreadsheet not found: {self.spreadsheet_id}. "
                    "Make sure you shared the sheet with: "
                    f"{self.client.auth.service_account_email} (Viewer access)"
                )
            except Exception as e:
                # Capture full details for debugging
                import traceback
                logger.error("spreadsheet_open_failed", error=str(e), error_type=type(e).__name__, traceback=traceback.format_exc())
                raise SheetsSyncError(f"Failed to open spreadsheet: {type(e).__name__} - {str(e) or repr(e)}")
            
            # Get worksheet (Case-insensitive fallback)
            try:
                worksheet = spreadsheet.worksheet(self.worksheet_name)
            except gspread.WorksheetNotFound:
                # Try finding case-insensitive match
                all_worksheets = spreadsheet.worksheets()
                matched_ws = next(
                    (ws for ws in all_worksheets if ws.title.lower() == self.worksheet_name.lower()),
                    None
                )
                
                if matched_ws:
                    logger.info("worksheet_found_case_insensitive", original=self.worksheet_name, found=matched_ws.title)
                    worksheet = matched_ws
                else:
                    available = [ws.title for ws in all_worksheets]
                    raise SheetsSyncError(
                        f"Worksheet '{self.worksheet_name}' not found (tried case-insensitive too). "
                        f"Available: {available}"
                    )
            
            # Get all values
            all_values = worksheet.get_all_values()
            
            if not all_values:
                raise SheetsSyncError("Worksheet is empty")
            
            # Parse headers (case-insensitive mapping)
            raw_headers = all_values[0]
            header_map = {}
            
            for idx, h in enumerate(raw_headers):
                norm = self._normalize_header(h)
                if norm in ['sku']:
                    header_map['sku'] = idx
                elif norm in ['onhandqty', 'stock', 'qty', 'quantity']:
                    header_map['qty'] = idx
            
            # Validate required columns
            if 'sku' not in header_map:
                raise SheetsSyncError(
                    f"Missing 'SKU' column. Found headers: {raw_headers}"
                )
            if 'qty' not in header_map:
                raise SheetsSyncError(
                    f"Missing stock quantity column. "
                    f"Expected: OnHandQty/stock/qty. Found: {raw_headers}"
                )
            
            # Parse data rows
            stock_data = []
            skipped_rows = 0
            
            for row_idx, row in enumerate(all_values[1:], start=2):
                # Skip empty rows
                if not row or len(row) == 0:
                    skipped_rows += 1
                    continue
                
                sku_val = row[header_map['sku']].strip() if len(row) > header_map['sku'] else ""
                qty_val = row[header_map['qty']].strip() if len(row) > header_map['qty'] else "0"
                
                # Skip rows with empty SKU
                if not sku_val:
                    skipped_rows += 1
                    continue
                
                # Parse quantity (handle "5.0", " 5 ", etc.)
                try:
                    qty = int(float(qty_val))
                except (ValueError, TypeError):
                    logger.warning(
                        "invalid_qty_value",
                        row=row_idx,
                        sku=sku_val,
                        qty_value=qty_val
                    )
                    qty = 0
                
                stock_data.append({"sku": sku_val, "qty": qty})
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                "sheet_data_read",
                spreadsheet_id=self.spreadsheet_id,
                worksheet=self.worksheet_name,
                rows_read=len(stock_data),
                skipped_rows=skipped_rows,
                duration_ms=duration_ms
            )
            
            return stock_data
            
        except SheetsSyncError:
            raise
        except Exception as e:
            raise SheetsSyncError(f"Unexpected error reading sheet: {e}")
    
    def sync_to_database(
        self,
        session: Session,
        product_model,
        dry_run: bool = False
    ) -> Dict:
        """
        Sync stock data to database
        
        Args:
            session: SQLAlchemy session
            product_model: Product model class
            dry_run: If True, don't commit changes
            
        Returns:
            Dict with metrics: {
                "updated_count": int,
                "missing_sku_count": int,
                "skipped_rows": int,
                "errors": List[str],
                "duration_ms": int
            }
        """
        start_time = time.time()
        
        try:
            # Read sheet data
            stock_data = self.read_stock_data()
            
            updated_count = 0
            missing_skus = []
            
            # Update each SKU
            for item in stock_data:
                sku = item["sku"]
                qty = item["qty"]
                
                product = session.query(product_model).filter(
                    product_model.sku == sku
                ).first()
                
                if product:
                    if not dry_run:
                        product.on_hand_qty = qty
                    updated_count += 1
                    
                    logger.debug(
                        "product_updated" if not dry_run else "product_would_update",
                        sku=sku,
                        new_qty=qty
                    )
                else:
                    missing_skus.append(sku)
                    logger.debug("product_not_found", sku=sku)
            
            # Commit if not dry run
            if not dry_run:
                session.commit()
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            result = {
                "status": "ok",
                "dry_run": dry_run,
                "updated_count": updated_count,
                "missing_sku_count": len(missing_skus),
                "missing_skus": missing_skus[:10],  # First 10 only
                "total_rows": len(stock_data),
                "duration_ms": duration_ms,
                "errors": []
            }
            
            logger.info(
                "stock_sync_complete",
                spreadsheet_id=self.spreadsheet_id,
                worksheet=self.worksheet_name,
                **{k: v for k, v in result.items() if k not in ['errors', 'missing_skus']}
            )
            
            return result
            
        except SheetsSyncError as e:
            return {
                "status": "error",
                "errors": [str(e)],
                "updated_count": 0,
                "missing_sku_count": 0,
                "total_rows": 0,
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        except Exception as e:
            logger.error("sync_unexpected_error", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "errors": [f"Unexpected error: {e}"],
                "updated_count": 0,
                "missing_sku_count": 0,
                "total_rows": 0,
                "duration_ms": int((time.time() - start_time) * 1000)
            }
