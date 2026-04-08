import gspread
from google.oauth2.service_account import Credentials
import json
import os
import time
from pathlib import Path
import structlog
import requests
from bs4 import BeautifulSoup
import re
import unicodedata
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is unavailable on Windows.
    fcntl = None

class CatalogService:
    _cache = None
    _cache_time = 0
    _cache_ttl = 600  # 10 minutes TTL for sheet data
    _mep_rate_cache = None
    _mep_rate_time = 0
    _mep_rate_ttl = 3600  # 1 hour in-memory TTL for exchange rate
    _mep_rate_max_age = 60 * 60 * 36  # Use scheduled cache up to 36 hours before bootstrap fetch.
    _mep_rate_cache_file = os.getenv("MEP_RATE_CACHE_FILE", "/tmp/mep_rate_cache.json")
    _mep_rate_lock_file = os.getenv("MEP_RATE_LOCK_FILE", "/tmp/mep_rate_refresh.lock")
    _repo_root = Path(__file__).resolve().parents[2]
    _catalog_image_overrides_by_sku = {}
    _blocked_skus: set = set()  # No product-line-specific blocks
    _color_groups: dict = {}    # Color grouping not used for hardware catalog
    _image_color_hints: dict = {}  # Image-color consistency not used for hardware catalog

    def __init__(self, auth_sheets: bool = True):
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        self.worksheet_name = os.getenv("GOOGLE_SHEETS_WORKSHEET_STOCK", "STOCK")
        self.client = self._auth_gspread() if auth_sheets else None

    @staticmethod
    def _normalize_text(value) -> str:
        text = str(value or "")
        text = unicodedata.normalize("NFD", text)
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return text.lower().strip()

    @classmethod
    def _normalize_color_slug(cls, color_raw) -> str:
        normalized = cls._normalize_text(color_raw)
        if not normalized:
            return ""
        return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

    @classmethod
    def _color_group_from_color(cls, color_raw) -> str:
        color_slug = cls._normalize_color_slug(color_raw)
        for group, values in cls._color_groups.items():
            if color_slug in values:
                return group
        return ""

    @classmethod
    def _infer_color_groups_from_image_url(cls, image_url: str) -> set[str]:
        normalized = cls._normalize_text(image_url).split("?")[0]
        if not normalized:
            return set()

        groups: set[str] = set()
        for group, hints in cls._image_color_hints.items():
            for hint in hints:
                if hint in normalized or hint.replace("-", "") in normalized.replace("-", ""):
                    groups.add(group)
                    break
        return groups

    @classmethod
    def _is_image_color_consistent(cls, color_raw, image_url) -> bool:
        expected_group = cls._color_group_from_color(color_raw)
        if not expected_group:
            return True
        inferred_groups = cls._infer_color_groups_from_image_url(str(image_url or ""))
        if not inferred_groups:
            return True
        return expected_group in inferred_groups

    @classmethod
    def _override_image_for_known_sku(cls, sku: str, current_image_url: str) -> str:
        override = cls._catalog_image_overrides_by_sku.get(str(sku or ""))
        if not override:
            return current_image_url
        candidate = cls._repo_root / "website" / override
        if candidate.exists():
            return override
        return current_image_url

    def _apply_catalog_contract_guards(self, catalog: list[dict]) -> list[dict]:
        sanitized: list[dict] = []
        sku_variants: dict[str, set[tuple[str, str, str]]] = {}

        for item in catalog:
            row = dict(item)
            sku = str(row.get("sku", "")).strip()
            model = str(row.get("name") or row.get("model") or "").strip()
            color = str(row.get("color", "")).strip()
            storage = str(row.get("storage_gb", "")).strip()
            image_url = str(row.get("image_url", "")).strip()

            if sku in self._blocked_skus:
                logger.info(
                    "catalog_variant_blocked",
                    sku=sku,
                    model=model,
                    color=color,
                )
                continue

            image_url = self._override_image_for_known_sku(sku, image_url)
            if image_url and not self._is_image_color_consistent(color, image_url):
                logger.warning(
                    "catalog_image_color_mismatch",
                    sku=sku,
                    model=model,
                    color=color,
                    image_url=image_url,
                )
                # Empty image_url forces frontend resolver to use model/color-safe mapping.
                image_url = ""

            row["image_url"] = image_url
            sanitized.append(row)

            if sku:
                sku_variants.setdefault(sku, set()).add((model, color, storage))

        for sku, variants in sku_variants.items():
            if len(variants) > 1:
                logger.warning(
                    "catalog_duplicate_sku_variants",
                    sku=sku,
                    variant_count=len(variants),
                    variants=sorted(variants),
                )

        return sanitized

    @classmethod
    def _set_mep_rate_cache(cls, rate: float, updated_at: float) -> None:
        cls._mep_rate_cache = rate
        cls._mep_rate_time = updated_at

    @classmethod
    def _read_mep_rate_cache_file(cls):
        path = Path(cls._mep_rate_cache_file)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rate = float(payload["rate"])
            updated_at = float(payload["updated_at"])
            return rate, updated_at
        except Exception as e:
            logger.warning("mep_cache_file_read_failed", path=str(path), error=str(e))
            return None

    @classmethod
    def _write_mep_rate_cache_file(cls, rate: float, updated_at: float) -> None:
        path = Path(cls._mep_rate_cache_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        payload = {"rate": rate, "updated_at": updated_at}
        tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp_path, path)

    @classmethod
    def _try_acquire_mep_rate_lock(cls):
        if fcntl is None:
            return None
        lock_path = Path(cls._mep_rate_lock_file)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fp = lock_path.open("a+")
        try:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_fp
        except BlockingIOError:
            lock_fp.close()
            return None
        except Exception:
            lock_fp.close()
            raise

    @staticmethod
    def _release_mep_rate_lock(lock_fp) -> None:
        if not lock_fp:
            return
        try:
            if fcntl is not None:
                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            lock_fp.close()

    def _fetch_mep_rate_from_api(self):
        url = "https://mercados.ambito.com//dolar/mep/variacion"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
        }
        try:
            logger.info("fetching_mep_rate_from_ambito_api")
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.warning("mep_api_non_200", status=response.status_code)
                return None

            data = response.json()
            mep_value = data.get('venta')
            if not mep_value:
                logger.warning("mep_value_missing_in_response")
                return None

            clean_val = mep_value.replace('.', '').replace(',', '.')
            rate = float(clean_val)
            updated_at = time.time()
            self.__class__._set_mep_rate_cache(rate, updated_at)
            self.__class__._write_mep_rate_cache_file(rate, updated_at)
            logger.info("mep_rate_updated", rate=rate)
            return rate
        except Exception as e:
            logger.error("mep_rate_api_failed", error=str(e))
            return None

    def refresh_mep_rate(self, *, force: bool = False, use_lock: bool = False):
        now = time.time()
        if (
            not force
            and self._mep_rate_cache
            and (now - self._mep_rate_time < self._mep_rate_ttl)
        ):
            return self._mep_rate_cache

        lock_fp = None
        if use_lock:
            lock_fp = self._try_acquire_mep_rate_lock()
            if lock_fp is None:
                shared_cache = self._read_mep_rate_cache_file()
                if shared_cache:
                    rate, updated_at = shared_cache
                    self.__class__._set_mep_rate_cache(rate, updated_at)
                    return rate
                return self._mep_rate_cache or 1400.0

        try:
            refreshed_rate = self._fetch_mep_rate_from_api()
            if refreshed_rate is not None:
                return refreshed_rate
        finally:
            self._release_mep_rate_lock(lock_fp)

        shared_cache = self._read_mep_rate_cache_file()
        if shared_cache:
            rate, updated_at = shared_cache
            self.__class__._set_mep_rate_cache(rate, updated_at)
            return rate
        return self._mep_rate_cache or 1400.0

    def _get_mep_rate(self):
        """Get Dólar MEP from shared cache; bootstrap fetch only when cache is unavailable."""
        now = time.time()
        if self._mep_rate_cache and (now - self._mep_rate_time < self._mep_rate_ttl):
            return self._mep_rate_cache

        shared_cache = self._read_mep_rate_cache_file()
        if shared_cache:
            rate, updated_at = shared_cache
            if now - updated_at <= self._mep_rate_max_age:
                self.__class__._set_mep_rate_cache(rate, updated_at)
                return rate
            logger.warning("mep_rate_cache_stale", age_seconds=round(now - updated_at, 1))

        if self._mep_rate_cache:
            return self._mep_rate_cache

        logger.warning("mep_rate_cache_empty_bootstrap_fetch")
        return self.refresh_mep_rate(force=True, use_lock=True)

    def _auth_gspread(self):
        json_str = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON")
        if not json_str:
            logger.warning("gspread_disabled_missing_credentials")
            return None
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
            clean = json_str.strip()
            if clean.startswith("'") and clean.endswith("'"):
                clean = clean[1:-1]

            try:
                creds_dict = json.loads(clean)
            except json.JSONDecodeError:
                try:
                    clean_fixed = clean.replace('\\n', '\n')
                    creds_dict = json.loads(clean_fixed)
                except json.JSONDecodeError as e:
                    logger.error("json_decode_error_final", error=str(e), partial=clean[:50])
                    raise Exception("Invalid GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON format")

            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            return gspread.authorize(creds)
        except Exception as e:
            logger.error("gspread_auth_failed", error=str(e))
            return None

    def get_catalog(self):
        # Check Cache
        now = time.time()
        if self.__class__._cache and (now - self.__class__._cache_time < self._cache_ttl):
            logger.info("serving_catalog_from_cache", age=now - self.__class__._cache_time)
            return self.__class__._cache

        if not self.client or not self.spreadsheet_id:
            logger.warning("catalog_unavailable_missing_configuration")
            return self.__class__._cache or []

        try:
            sheet = self.client.open_by_key(self.spreadsheet_id)
            
            all_ws = sheet.worksheets()
            
            # 1. Try configured name (relaxed)
            target_name = self.worksheet_name.lower().strip()
            ws = next((w for w in all_ws if w.title.lower().strip() == target_name), None)
            
            # 2. Try 'stock' specifically if not found by name
            if not ws and target_name != 'stock':
                ws = next((w for w in all_ws if w.title.lower().strip() == 'stock'), None)
                
            # 3. Final Fallback: Raise error if no stock sheet
            if not ws:
                logger.error("stock_worksheet_not_found", target=self.worksheet_name, available=[w.title for w in all_ws])
                raise Exception(f"Worksheet '{self.worksheet_name}' not found in spreadsheet.")

            logger.info("using_worksheet", title=ws.title)

            # Get current MEP rate for conversion
            mep_rate = self._get_mep_rate()
            logger.info("applying_conversion", mep_rate=mep_rate)

            rows = ws.get_all_records()
            catalog = []
            
            for i, row in enumerate(rows):
                # Normalize keys to lowercase/stripped
                data = {k.lower().strip(): v for k, v in row.items()}
                
                sku = str(data.get('sku', '')).strip()
                if not sku:
                    continue # Skip empty SKUs

                try:
                    # Strict Parsing
                    price_raw = str(data.get('price_ars', 0)).replace(',', '').replace('.', '').replace('$', '').strip()
                    price = int(float(price_raw)) if price_raw else 0
                    
                    stock_raw = str(data.get('stock', 0)).strip()
                    stock = int(float(stock_raw)) if stock_raw else 0
                    if stock < 0: stock = 0

                    storage_raw = str(data.get('storage_gb', '0')).upper().replace('GB', '').strip()
                    storage = int(float(storage_raw)) if storage_raw and storage_raw.replace('.','',1).isdigit() else 0

                    # Apply MEP conversion: Column D is now treated as USD
                    price_ars = int(round(price * mep_rate))
                    # Round to nearest 100 for cleaner display
                    price_ars = (price_ars // 100) * 100

                    item = {
                        "sku": sku,
                        "name": str(data.get('name', sku)).strip(),
                        "category": str(data.get('category', 'Others')).strip(),
                        "price_ars": price_ars,
                        "price_usd": price, # Keep the original USD value
                        "stock": stock,
                        "available_qty": stock, # Compat
                        "color": str(data.get('color', '')).strip(),
                        "storage_gb": storage,
                        # Optional extras if present, but strictly keeping to contract
                        "image_url": str(data.get('image_url', '')).strip(),
                        "description": str(data.get('description', '')).strip()
                    }
                    catalog.append(item)
                except Exception as e:
                    logger.warning("row_parse_error", row=i, sku=sku, error=str(e))
                    continue
            
            # Update Cache
            catalog = self._apply_catalog_contract_guards(catalog)
            self.__class__._cache = catalog
            self.__class__._cache_time = now
            logger.info("catalog_refreshed_from_sheets", count=len(catalog))
            return catalog

        except Exception as e:
            logger.error("catalog_fetch_failed", error=str(e))
            # Failover: Return stale cache if available, else re-raise
            if self._cache:
                logger.warning("serving_stale_cache_due_to_error")
                return self._cache
            raise e
