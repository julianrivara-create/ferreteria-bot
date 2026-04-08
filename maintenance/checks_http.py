import httpx
import time
from .logging_config import logger

async def check_http(base_url, health_path=None, timeout_ms=5000):
    """Checks HTTP connectivity and optional health endpoint."""
    results = []
    timeout = timeout_ms / 1000.0
    
    # 1. Base URL check
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(base_url)
            duration = int((time.time() - start) * 1000)
            results.append({
                "type": "http_base",
                "url": base_url,
                "status_code": resp.status_code,
                "latency_ms": duration,
                "ok": resp.status_code < 400
            })
    except Exception as e:
        results.append({
            "type": "http_base",
            "url": base_url,
            "error": str(e),
            "ok": False
        })

    # 2. Health Path check
    if health_path:
        full_url = f"{base_url.rstrip('/')}/{health_path.lstrip('/')}"
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(full_url)
                duration = int((time.time() - start) * 1000)
                results.append({
                    "type": "http_health",
                    "url": full_url,
                    "status_code": resp.status_code,
                    "latency_ms": duration,
                    "ok": resp.status_code == 200
                })
        except Exception as e:
            results.append({
                "type": "http_health",
                "url": full_url,
                "error": str(e),
                "ok": False
            })
            
    return results
