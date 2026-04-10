from __future__ import annotations

from pathlib import Path

from bot_sales.core.database import Database


class _StubVector:
    def __init__(self, hits):
        self._hits = hits

    @property
    def is_ready(self) -> bool:
        return True

    def search(self, query: str, top_k: int = 15):
        return list(self._hits)[:top_k]

    def close(self) -> None:
        return None


def _catalog_file(tmp_path: Path) -> Path:
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "\n".join(
            [
                "sku,category,model,storage_gb,color,proveedor,stock_qty,price_ars,currency",
                "SKU-RED,herramientas,Taladro brushless,128,rojo,Bosch,5,1000,ARS",
                "SKU-BLUE,herramientas,Taladro brushless,256,azul,Bosch,5,1200,ARS",
                "SKU-OTHER,insumos,Silicona acida,0,transparente,Acme,10,900,ARS",
            ]
        ),
        encoding="utf-8",
    )
    return catalog


def test_hybrid_search_preserves_color_and_storage_filters(tmp_path):
    db = Database(
        db_file=str(tmp_path / "hybrid.db"),
        catalog_csv=str(_catalog_file(tmp_path)),
        log_path=str(tmp_path / "hybrid.log"),
    )
    db._vector = _StubVector(
        [
            ("SKU-BLUE", 0.99),
            ("SKU-RED", 0.95),
            ("SKU-OTHER", 0.80),
        ]
    )

    try:
        matches = db.find_matches_hybrid(
            "consulta semantica",
            storage_gb=128,
            color="rojo",
            categoria="herramientas",
            proveedor="Bosch",
        )
    finally:
        db.close()

    assert [product["sku"] for product in matches] == ["SKU-RED"]
