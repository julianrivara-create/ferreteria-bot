"""
Response Cache System
Cachea respuestas frecuentes para ahorrar tokens de OpenAI
"""
import sqlite3
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

class ResponseCache:
    """
    Sistema de caché para respuestas del bot
    Usa SQLite para persistencia
    """
    
    def __init__(self, db_path: str = 'cache.db', default_ttl: int = 3600):
        """
        Args:
            db_path: Path a DB de caché
            default_ttl: TTL por defecto en segundos (1 hora)
        """
        self.db_path = db_path
        self.default_ttl = default_ttl
        self.logger = logging.getLogger(__name__)
        
        self._init_db()
        self.logger.info(f"Response cache initialized: {db_path}")
    
    def _init_db(self):
        """Crea tabla de caché si no existe"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS response_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                hit_count INTEGER DEFAULT 0,
                category TEXT
            )
        """)
        
        # Índice para expiración
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at 
            ON response_cache(expires_at)
        """)
        
        conn.commit()
        conn.close()
    
    def _make_key(self, query: str, context: Dict = None) -> str:
        """
        Genera key de caché basada en query + contexto
        
        Args:
            query: Mensaje del usuario
            context: Contexto adicional (opcional)
        
        Returns:
            Hash MD5 del query normalizado
        """
        # Normalizar query
        normalized = query.lower().strip()
        
        # Agregar contexto si hay
        if context:
            normalized += json.dumps(context, sort_keys=True)
        
        # Hash
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def get(self, query: str, context: Dict = None) -> Optional[str]:
        """
        Obtiene respuesta del caché
        
        Args:
            query: Pregunta del usuario
            context: Contexto adicional
        
        Returns:
            Respuesta cacheada o None si no existe/expiró
        """
        key = self._make_key(query, context)
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT value, expires_at, hit_count
            FROM response_cache
            WHERE key = ?
        """, (key,))
        
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        # Verificar expiración
        if row['expires_at']:
            expires = datetime.fromisoformat(row['expires_at'])
            if datetime.now() > expires:
                # Expirado, borrar
                cursor.execute("DELETE FROM response_cache WHERE key = ?", (key,))
                conn.commit()
                conn.close()
                self.logger.debug(f"Cache expired: {key[:12]}...")
                return None
        
        # Incrementar hit count
        cursor.execute("""
            UPDATE response_cache 
            SET hit_count = hit_count + 1
            WHERE key = ?
        """, (key,))
        conn.commit()
        
        value = row['value']
        hit_count = row['hit_count'] + 1
        
        conn.close()
        
        self.logger.info(f"Cache HIT: {key[:12]}... (hits: {hit_count})")
        return value
    
    def set(self, query: str, response: str, ttl: int = None, 
            context: Dict = None, category: str = None):
        """
        Guarda respuesta en caché
        
        Args:
            query: Pregunta del usuario
            response: Respuesta a cachear
            ttl: Time to live en segundos (None = default)
            context: Contexto adicional
            category: Categoría para organizar (faq, product, etc)
        """
        key = self._make_key(query, context)
        ttl = ttl or self.default_ttl
        
        # Calcular expiración
        expires_at = None
        if ttl > 0:
            expires_at = datetime.now() + timedelta(seconds=ttl)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO response_cache 
            (key, value, created_at, expires_at, hit_count, category)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (key, response, datetime.now(), expires_at, category))
        
        conn.commit()
        conn.close()
        
        self.logger.debug(f"Cache SET: {key[:12]}... (ttl: {ttl}s, category: {category})")
    
    def invalidate(self, query: str = None, category: str = None):
        """
        Invalida caché por query o categoría
        
        Args:
            query: Query específico a invalidar
            category: Invalidar toda una categoría
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if query:
            key = self._make_key(query)
            cursor.execute("DELETE FROM response_cache WHERE key = ?", (key,))
            self.logger.info(f"Invalidated cache key: {key[:12]}...")
        
        elif category:
            cursor.execute("DELETE FROM response_cache WHERE category = ?", (category,))
            self.logger.info(f"Invalidated category: {category}")
        
        else:
            # Borrar todo
            cursor.execute("DELETE FROM response_cache")
            self.logger.info("Cleared entire cache")
        
        conn.commit()
        conn.close()
    
    def cleanup_expired(self):
        """Limpia entradas expiradas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM response_cache
            WHERE expires_at IS NOT NULL 
            AND expires_at < ?
        """, (datetime.now(),))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        if deleted > 0:
            self.logger.info(f"Cleaned up {deleted} expired entries")
        
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del caché"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Total entries
        cursor.execute("SELECT COUNT(*) as count FROM response_cache")
        total = cursor.fetchone()['count']
        
        # By category
        cursor.execute("""
            SELECT category, COUNT(*) as count, SUM(hit_count) as total_hits
            FROM response_cache
            GROUP BY category
        """)
        categories = [dict(row) for row in cursor.fetchall()]
        
        # Top hits
        cursor.execute("""
            SELECT key, value, hit_count, category
            FROM response_cache
            ORDER BY hit_count DESC
            LIMIT 10
        """)
        top_hits = [dict(row) for row in cursor.fetchall()]
        
        # Hit rate estimation (total hits / total entries)
        cursor.execute("SELECT SUM(hit_count) as total_hits FROM response_cache")
        total_hits = cursor.fetchone()['total_hits'] or 0
        
        conn.close()
        
        return {
            'total_entries': total,
            'total_hits': total_hits,
            'avg_hits_per_entry': total_hits / total if total > 0 else 0,
            'categories': categories,
            'top_hits': top_hits
        }
    
    def warm_cache(self, entries: Dict[str, str], category: str = 'warm', ttl: int = None):
        """
        Pre-carga el caché con respuestas conocidas (FAQ, etc)
        
        Args:
            entries: {query: response}
            category: Categoría para estas entradas
            ttl: TTL específico (None = infinito)
        """
        count = 0
        for query, response in entries.items():
            self.set(query, response, ttl=ttl or 0, category=category)
            count += 1
        
        self.logger.info(f"Cache warmed with {count} entries (category: {category})")
        return count


def warm_faq_cache(cache: ResponseCache):
    """
    Pre-carga FAQs comunes
    Llamar al inicio de la app
    """
    faqs = {
        "cómo es el envío": "Opciones de envío:\n• CABA: Gratis en moto (24-48hs)\n• AMBA: Consultar costo (48-72hs)\n• Interior: Por Correo/Andreani (3-5 días)\n• Retiro en local: Coordinamos horario",

        "tienen garantía": "Garantía oficial:\n• 1 año de garantía del fabricante\n• Servicio técnico autorizado\n• En caso de falla, coordinamos el service",

        "formas de pago": "Formas de pago:\n• Transferencia bancaria\n• Efectivo (en retiro)\n• MercadoPago (link de pago)\n• Tarjeta: 3/6/12 cuotas con MercadoPago",

        "cuánto tarda el envío": "Tiempos de entrega:\n• CABA: 24-48hs\n• AMBA: 48-72hs\n• Interior: 3-5 días hábiles\n• Retiro inmediato coordinando horario",

        "hacen factura": "Sí, hacemos factura A o B según necesites. Solo avisanos al confirmar el pedido.",

        "stock disponible": "Consultame por el modelo específico que te interesa y te chequeo el stock en tiempo real.",
    }
    
    cache.warm_cache(faqs, category='faq', ttl=0)  # TTL 0 = infinito


# Singleton global
_cache_instance = None

def get_cache(db_path: str = 'cache.db', ttl: int = 3600) -> ResponseCache:
    """Obtiene instancia singleton de caché"""
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = ResponseCache(db_path, ttl)
        # Warm cache con FAQs
        warm_faq_cache(_cache_instance)
    
    return _cache_instance
