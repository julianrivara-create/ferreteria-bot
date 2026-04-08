"""
Performance Optimizations for Sales Bot
Includes async, connection pooling, lazy loading, and profiling tools
"""
import asyncio
import logging
from functools import wraps
from typing import Any, Callable
import time

logger = logging.getLogger(__name__)

# ========== ASYNC HELPERS ==========

def async_timed(func: Callable) -> Callable:
    """
    Decorator para medir tiempo de funciones async
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.debug(f"{func.__name__} took {elapsed:.3f}s")
        return result
    return wrapper


async def run_in_executor(func: Callable, *args, **kwargs) -> Any:
    """
    Ejecuta función bloqueante en thread pool
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# ========== LAZY LOADING ==========

class LazyProperty:
    """
    Property descriptor para lazy loading
    
    Usage:
        class MyClass:
            @LazyProperty
            def expensive_resource(self):
                return ExpensiveObject()
    """
    
    def __init__(self, func):
        self.func = func
        self.name = func.__name__
    
    def __get__(self, obj, owner):
        if obj is None:
            return self
        
        # Calcular y cachear
        value = self.func(obj)
        setattr(obj, self.name, value)
        return value


# ========== CONNECTION POOLING ==========

class ConnectionPool:
    """
    Simple connection pool para SQLite
    """
    
    def __init__(self, db_path: str, pool_size: int = 5):
        import sqlite3
        
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool = []
        self._lock = asyncio.Lock()
        
        # Pre-crear conexiones
        for _ in range(pool_size):
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._pool.append(conn)
        
        logger.info(f"Connection pool created: {pool_size} connections")
    
    async def acquire(self):
        """Adquiere conexión del pool"""
        async with self._lock:
            if not self._pool:
                # Crear nueva si pool vacío
                import sqlite3
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                return conn
            
            return self._pool.pop()
    
    async def release(self, conn):
        """Libera conexión al pool"""
        async with self._lock:
            if len(self._pool) < self.pool_size:
                self._pool.append(conn)
            else:
                conn.close()
    
    def close_all(self):
        """Cierra todas las conexiones"""
        for conn in self._pool:
            conn.close()
        self._pool.clear()


# ========== CACHING DECORATOR ==========

def cached(ttl: int = 300):
    """
    Decorator para cachear resultados de funciones
    
    Args:
        ttl: Time to live en segundos
    """
    cache = {}
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generar key
            key = str((args, tuple(sorted(kwargs.items()))))
            
            # Check cache
            if key in cache:
                result, timestamp = cache[key]
                if time.time() - timestamp < ttl:
                    logger.debug(f"Cache hit: {func.__name__}")
                    return result
            
            # Ejecutar función
            result = func(*args, **kwargs)
            cache[key] = (result, time.time())
            
            return result
        
        return wrapper
    return decorator


# ========== PROFILING ==========

class Profiler:
    """
    Context manager para profiling
    
    Usage:
        with Profiler("My operation"):
            # código a medir
            pass
    """
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        elapsed = time.perf_counter() - self.start_time
        logger.info(f"[PROFILE] {self.name}: {elapsed:.3f}s")


def profile_function(func: Callable) -> Callable:
    """
    Decorator para profile de funciones
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        with Profiler(func.__name__):
            return func(*args, **kwargs)
    return wrapper


# ========== BATCH OPERATIONS ==========

async def batch_process(items: list, func: Callable, batch_size: int = 10) -> list:
    """
    Procesa items en batches async
    
    Args:
        items: Lista de items a procesar
        func: Función async a aplicar
        batch_size: Tamaño de batch
    
    Returns:
        Lista de resultados
    """
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        
        # Procesar batch en paralelo
        batch_results = await asyncio.gather(*[func(item) for item in batch])
        results.extend(batch_results)
    
    return results


# ========== MEMORY OPTIMIZATION ==========

def clear_cache():
    """Limpia cachés de funciones decoradas"""
    # TODO: Implementar registro global de cachés
    logger.info("Cache cleared")


# ========== EXAMPLE USAGE ==========

async def example_async_operations():
    """
    Ejemplo de uso de optimizaciones
    """
    
    # 1. Operaciones en paralelo
    async def fetch_product(sku):
        # await asyncio.sleep(0.1)  # Simular IO
        return f"Product {sku}"
    
    skus = ['IP15-128', 'IP15-256', 'IP16-128']
    products = await asyncio.gather(*[fetch_product(sku) for sku in skus])
    logger.info(f"Fetched: {products}")
    
    # 2. Batch processing
    async def process_sale(sale_id):
        # await asyncio.sleep(0.05)
        return f"Processed {sale_id}"
    
    sales = list(range(50))
    results = await batch_process(sales, process_sale, batch_size=10)
    logger.info(f"Processed {len(results)} sales")
    
    # 3. Con profiling
    with Profiler("Complete operation"):
        pass
        # await asyncio.sleep(0.5)


# ========== RECOMMENDATIONS ==========

PERFORMANCE_TIPS = """
🚀 Performance Optimization Guide:

1. **Async Operations**
   - Use async/await para I/O operations
   - Batch API calls con asyncio.gather()
   
2. **Connection Pooling**
   - Reusa conexiones DB
   - Pool size: 5-10 para bots pequeños
   
3. **Lazy Loading**
   - Cargá módulos solo cuando se usan
   - Use @LazyProperty para resources costosos
   
4. **Caching**
   - Caché responses frecuentes (ver cache.py)
   - Use @cached decorator para funciones puras
   
5. **Profiling**
   - Medí antes de optimizar
   - Use Profiler context manager
   - LOG_LEVEL=DEBUG para ver timings

6. **Memory**
   - Evitá cargar todo el catálogo en memoria
   - Use generators para large datasets
   - Limpiá cachés periódicamente

7. **Database**
   - Indices en campos de búsqueda
   - VACUUM periódico de SQLite
   - Use transactions para bulk inserts

Benchmark targets:
- Response time: < 2s (95th percentile)
- API calls: < 300ms
- DB queries: < 50ms
"""

if __name__ == '__main__':
    print(PERFORMANCE_TIPS)
