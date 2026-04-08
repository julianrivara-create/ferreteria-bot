from __future__ import annotations

import zlib

try:
    import xxhash  # type: ignore
except Exception:  # pragma: no cover
    xxhash = None


def advisory_lock_key(tenant_id: str, process_name: str) -> int:
    material = f"{tenant_id}:{process_name}".encode("utf-8")
    if xxhash is not None:
        value = xxhash.xxh64(material).intdigest()
    else:  # pragma: no cover
        value = zlib.crc32(material)
    if value >= (1 << 63):
        value -= (1 << 64)
    return int(value)


def try_advisory_lock(conn, tenant_id: str, process_name: str) -> bool:
    key = advisory_lock_key(tenant_id, process_name)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        row = cur.fetchone()
    return bool(row and row[0])


def advisory_unlock(conn, tenant_id: str, process_name: str) -> None:
    key = advisory_lock_key(tenant_id, process_name)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (key,))

