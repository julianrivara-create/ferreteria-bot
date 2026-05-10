# Audit V3 — Catálogo y dual-catalog

**HEAD:** `9f7369d` — docs: PENDIENTES actualizado — cierre 2026-05-07 (10 bloques)
**Alcance:** `config/catalog.csv` · `data/tenants/ferreteria/catalog.csv` · referencias en código
**Tipo:** Read-only, sin modificaciones al código.

---

## Resumen

- **Dual catalog resuelto**: `config/catalog.csv` es el catálogo legacy/seed de BlueTools-Bremen-Bulonfer sin precios. El catálogo activo en runtime es `data/tenants/ferreteria/catalog.csv` (63 360 productos, precios reales ARS). No hay ambigüedad en producción, pero `config/catalog.csv` aparece como **fallback en database.py** y como default en `bot_sales/config.py` — riesgo latente.
- **DT-04 es un bug de búsqueda, NO un gap de catálogo**: "mecha 6mm", "mecha 8mm para metal" y "drywall" sí existen en el catálogo activo (10, 23 y 88 matches respectivamente). El problema es que la búsqueda no los encuentra — nomenclatura del catálogo ("Broca Max Mecha 6mm HSS DIN 338 para Metal x 10 unid.") vs. término del usuario ("mecha 6mm") genera mismatch de scoring.
- **"Cinta de carrocero"** es un falso negativo de terminología: el catálogo tiene 115 cintas de enmascarar/pintor bajo "Cinta Enmascarar" — el cliente dice "carrocero", el catálogo dice "Enmascarar". El sinónimo no está cubierto en `language_patterns.yaml`.
- **DT-14**: 4 128 productos tienen keywords de presentación (caja, juego, rollo, bolsa, pack, kit, set) pero ninguno tiene campo de qty-por-unidad. La ausencia de este campo fuerza la pregunta de cantidad en cada transacción.
- **Calidad general**: 752 productos sin precio (1.2%), cero duplicados de SKU, todo en ARS. Categoría "General" concentra el 35.5% del catálogo — señal de falta de taxonomía.
- **2 SKUs falsos** (DISC/Propinas, TIPS/Descuento) usados como recursos de POS — no son inventario real y pueden interferir con búsquedas.

---

## 1. Tamaños y formato

| Atributo | `config/catalog.csv` | `data/tenants/ferreteria/catalog.csv` |
|---|---|---|
| **Líneas** | 8 642 (8 641 datos) | 63 361 (63 360 datos) |
| **MD5** | `f8e9d0daa02ee59d55a33066095e8109` | `d304a07046773a2a374f3ff5f0f4e352` |
| **Son idénticos** | No | — |
| **Columnas** | SKU, Descripcion, Categoria, Proveedor, PriceARS, StockQty | sku, category, name, price, currency, stock |
| **Encoding** | UTF-8 | UTF-8 |
| **Precio real** | Todos 0 | $1 – $141 969 511 ARS |
| **Stock real** | Todos 0 | 999 (fijo) |
| **Proveedores** | BlueTools (5 548), Bremen (2 904), Bulonfer (189) | Inferidos desde sufijo del nombre |
| **Categorías** | 10 categorías (Varios, Bocallaves, etc.) | 13 categorías |

**Overlap de SKUs:**
- SKUs en config: 8 641
- SKUs en tenant: 63 360
- SKUs en ambos: **8 526** (config es ~99% subset del tenant)
- Solo en config (no en tenant): **115 SKUs** (todos BlueTools/Bulonfer)
- Solo en tenant (no en config): **54 834 SKUs**
- Nombres idénticos en SKUs compartidos: **100%** (0 mismatches en muestra de 200)

**Conclusión**: `config/catalog.csv` es una versión antigua y reducida del catálogo activo, congelada sin precios ni stock. Fue el catálogo original antes de que se incorporara el catálogo completo de tenant.

---

## 2. ¿Cuál es el catálogo activo?

### Catálogo activo en runtime: `data/tenants/ferreteria/catalog.csv`

```yaml
# tenants.yaml — línea 57
ferreteria:
  catalog_file: data/tenants/ferreteria/catalog.csv

# data/tenants/ferreteria/profile.yaml — línea 112
paths:
  catalog: data/tenants/ferreteria/catalog.csv
```

### config/catalog.csv — Status: LEGACY con riesgo de fallback activo

```python
# bot_sales/core/database.py:305-311 — _load_catalog_from_csv()
fallback_candidates = [
    Path(...) / "config" / "catalog.csv",          # ← PRIMER FALLBACK
    Path(...) / "data" / "tenants" / "default" / "catalog.csv",
]
```

Si el path del catálogo de tenant no existe (por ejemplo, en un deploy con volumen mal montado), **database.py carga `config/catalog.csv` silenciosamente** — 8 641 productos sin precio. El bot funcionaría pero todas las búsquedas responderían con precio 0.

```python
# bot_sales/config.py:235 — default global
CATALOG_CSV = os.path.join(BASE_DIR, 'config', 'catalog.csv')

# bot_sales/core/tenancy.py:23 — default para tenants no configurados
catalog_file: str = "config/catalog.csv"

# app/services/runtime_integrity.py:17-19 — verifica que AMBOS existan
"config/catalog.csv",
"data/tenants/ferreteria/catalog.csv",
```

### Resumen de rutas activas

| Código | Path usado | Estado |
|---|---|---|
| `tenants.yaml` + `profile.yaml` | `data/tenants/ferreteria/catalog.csv` | ✅ Runtime correcto |
| `database.py` fallback | `config/catalog.csv` | ⚠️ Solo si tenant path no existe |
| `bot_sales/config.py` CATALOG_CSV | `config/catalog.csv` | 🟡 Default global, sobreescrito por tenant |
| `tenancy.py` default | `config/catalog.csv` | 🟡 Para tenants sin catalog_file configurado |
| `app/bot/config.py` | `config/catalog.csv` | 🔴 Rama `app/` no migrada a tenant system |
| Tests ferreteria | `data/tenants/ferreteria/catalog.csv` | ✅ Tests usan catálogo correcto |

---

## 3. Schemas

### Comparación de columnas

| Campo semántico | `config/catalog.csv` | `data/tenants/ferreteria/catalog.csv` |
|---|---|---|
| Identificador | `SKU` | `sku` |
| Nombre/descripción | `Descripcion` | `name` |
| Categoría | `Categoria` | `category` |
| Precio | `PriceARS` (int) | `price` (int) + `currency` |
| Stock | `StockQty` | `stock` |
| Proveedor/marca | `Proveedor` (columna) | **AUSENTE** — inferido del sufijo del nombre |
| Presentación/pack | **AUSENTE** | **AUSENTE** |
| Dimensiones | **AUSENTE** | **AUSENTE** |
| Unidad de venta | **AUSENTE** | **AUSENTE** |

### Columnas faltantes críticas

| Campo faltante | Impacto | Deuda técnica |
|---|---|---|
| **`brand` / `proveedor`** | El código intenta `product.get("brand")` o `product.get("proveedor")` — siempre vacío en catálogo activo. El filtro de marca en `CatalogSearchService._apply_post_filters` nunca puede matchear una marca explícita | DT-04 parcial |
| **`pack_size` / `qty_per_unit`** | Bot pregunta cantidad para todo producto con "caja", "rollo", "bolsa" en el nombre porque no sabe cuántas unidades tiene | DT-14 |
| **`presentation`** | Sin campo formal no hay forma de saber si "tornillos x100" es 1 caja de 100 o 100 tornillos sueltos | DT-14 |

### Database.py: mapeo de columnas al cargar

```python
# database.py — campo model ← columna name del CSV activo
model = normalized.get("model") or normalized.get("name") or normalized.get("descripcion")

# brand/proveedor — puede leerse si existe la columna
"proveedor": (row["proveedor"] if "proveedor" in keys else "") or ""
```

El catálogo activo no tiene columna `proveedor` → todos los productos tienen `proveedor=""` en memoria. Esto rompe el filtro de marca de `CatalogSearchService`.

---

## 4. Calidad de datos

### Stats del catálogo activo (`data/tenants/ferreteria/catalog.csv`)

| Métrica | Valor |
|---|---|
| Total productos | 63 360 |
| Precio = 0 o vacío | **752** (1.19%) |
| Stock = 0 o vacío | 0 (todos tienen stock=999) |
| Sin categoría | 0 |
| Sin nombre | 0 |
| Nombre < 10 chars | **2** (ver §8) |
| SKUs duplicados | 0 |
| Monedas distintas a ARS | 0 |
| Categorías únicas | 13 |

### Precios (no-cero, 62 608 productos)

| Stat | Valor ARS |
|---|---|
| Mínimo | $1 |
| Máximo | $141 969 511 |
| Promedio | $205 529 |
| Mediana | $21 947 |

---

## 5. Distribución por categoría / proveedor

### Por categoría (13 categorías totales)

| Categoría | Productos | % |
|---|---|---|
| **General** | 22 493 | 35.5% |
| Electricidad | 9 255 | 14.6% |
| Mechas y Brocas | 6 882 | 10.9% |
| Herramientas Manuales | 6 488 | 10.2% |
| Plomería | 3 327 | 5.2% |
| Puntas y Accesorios | 3 044 | 4.8% |
| Discos y Hojas | 2 689 | 4.2% |
| Tornillería y Fijaciones | 2 524 | 4.0% |
| Pinturas y Acabados | 1 924 | 3.0% |
| Cintas y Adhesivos | 1 736 | 2.7% |
| Herramientas Eléctricas | 1 276 | 2.0% |
| Lijas y Abrasivos | 1 038 | 1.6% |
| Seguridad | 684 | 1.1% |

⚠️ **"General" es el 35.5% del catálogo** — cualquier búsqueda por categoría que caiga en "General" compite contra 22 493 productos. La `CatalogSearchService._search_browse()` para queries genéricos es inefectiva aquí.

### Por proveedor — top 25 (inferidos desde sufijo del nombre)

| Proveedor | Productos |
|---|---|
| Bahco | 4 591 |
| Genrod | 2 639 |
| BREMEN | 2 595 |
| Bosch | 2 269 |
| Irimo | 1 733 |
| General Electric | 1 350 |
| Ezeta | 1 301 |
| Dormer | 1 220 |
| Duroll | 1 179 |
| Zoloda | 1 033 |
| Dogo | 974 |
| Makita | 883 |
| Sica | 873 |
| Stanley | 868 |
| Milwaukee | 863 |
| Schneider | 805 |
| Sinteplast | 792 |
| Kalop | 774 |
| Premier | 706 |
| Norton | 652 |
| Fischer | 616 |
| Tek Bond | 593 |
| Awaduct | 561 |
| Jeluz | 555 |
| Lusqtoff | 467 |

---

## 6. Gaps mencionados en PENDIENTES (DT-04)

> **Hallazgo crítico: DT-04 NO es un gap de catálogo — es un bug de búsqueda.**

| Término buscado | ¿Existe en catálogo? | Matches | Diagnóstico |
|---|---|---|---|
| `mecha 6mm` | ✅ Sí | 10 | Existe como "Broca Max Mecha 6 mm HSS DIN 338 para Metal x 10 unid." — el scoring no rankea bien porque "x 10 unid." añade ruido |
| `mecha 8mm para metal` | ✅ Sí | 23 | Mismo problema. La nomenclatura completa diluciona el overlap |
| `mecha 10mm` | ✅ Sí | 32 | Idem |
| `cinta de carrocero` | ⚠️ Sinónimo | 115 (enmascarar/pintor) | El catálogo dice "Cinta Enmascarar" — el cliente dice "carrocero". Sinónimo NO está en `language_patterns.yaml` |
| `drywall` | ✅ Sí | 88 | Existe. Búsqueda debería funcionar. Si no funciona, es scoring/routing |

### Causa raíz de DT-04

El bot llega a la búsqueda con el término procesado por `_significant_words()` que filtra stop words y palabras < 3 chars. Para "mecha 6mm":
- Query words: `{mecha, 6mm}` (o `{mecha}` si "6mm" no pasa el filtro de len>2)
- Producto: "Broca Max Mecha 6 mm HSS DIN 338 para Metal x 10 unid." → significant words incluyen `{broca, max, mecha, hss, din, 338, metal, unid}`
- Overlap: `{mecha}` → ratio 1/2 = 0.5 → barely above threshold

El problema real es **doble**:
1. La nomenclatura técnica de catálogo ("Broca Max", "HSS DIN 338") genera ruido que baja el overlap ratio
2. No hay sinónimo `mecha → broca` ni `6mm → 6 mm` (espacio) en el path de búsqueda nuevo (`CatalogSearchService`). En `ferreteria_quote.py` el legacy sí tiene `_build_search_terms` con knowledge-based synonyms

**Acción correcta para DT-04**: no ampliar el catálogo — agregar sinónimos `mecha=broca`, `carrocero=enmascarar` en `language_patterns.yaml` y conectarlos al path de `CatalogSearchService`.

---

## 7. DT-14 — productos con presentación

### Distribución por keyword de presentación

| Keyword | Productos |
|---|---|
| `caja` | 1 158 |
| `juego` | 1 166 |
| `kit` | 432 |
| `set` | 525 |
| `rollo` | 357 |
| `bolsa` | 323 |
| `pack` | 238 |
| `lata` | 22 |
| **Total con al menos uno** | **4 128 productos (6.5%)** |

### Ejemplos representativos

```
PPTEZ33015100  | Juego Mechas 1-10 mm x 0.5 mm Acero Rápido DIN 338 x Caja - Ezeta
BLT566805      | Tornillos Madera Autoperforantes Avellanada Caja x100 - ...
IT655463M      | Cinta Enmascarar Masking Scotch 3500 24 mm x 40 mt - 3m  (rollo)
PMLY77         | Acople Cablecanal 18x21mm A Caja Blanco AD - Zoloda
```

### Implicación de DT-14

Sin campo `pack_size`, el bot no puede saber si "Caja x 100 tornillos" implica que el precio es por caja o por unidad, ni cuántas unidades trae. El bot fuerza la pregunta `¿Cuántas unidades necesitás?` para todos estos productos — incluso cuando el cliente pide "una caja" y el catálogo ya dice "x Caja".

**Schema propuesto para resolver DT-14:**
```csv
sku,category,name,price,currency,stock,brand,pack_unit,pack_qty
```
- `brand`: proveedor explícito (hoy inferido del sufijo del nombre)
- `pack_unit`: `unidad` | `caja` | `rollo` | `lata` | `bolsa` | `par` | `metro`
- `pack_qty`: cantidad de unidades por unidad de venta (int, default 1)

---

## 8. Casos especiales

### SKUs falsos de POS

| SKU | Nombre | Categoría |
|---|---|---|
| `DISC` | `Descuento` | General |
| `TIPS` | `Propinas` | General |

Estos SKUs tienen nombres de 8-9 chars (únicos con < 10 chars en el catálogo). Son recursos de un sistema POS para aplicar descuentos o propinas como líneas de venta. **No son inventario real** y pueden aparecer en búsquedas si alguien escribe "descuento" o "propina". El bot debería tenerlos en una blocklist.

### Precios en cero (752 productos)

Distribución por categoría:

| Categoría | Sin precio |
|---|---|
| General | 234 |
| Electricidad | 157 |
| Discos y Hojas | 52 |
| Tornillería y Fijaciones | 48 |
| Herramientas Manuales | 40 |
| Cintas y Adhesivos | 39 |
| Lijas y Abrasivos | 36 |
| Plomería | 34 |
| Seguridad | 26 |
| Mechas y Brocas | 25 |
| Pinturas y Acabados | 23 |
| Puntas y Accesorios | 21 |
| Herramientas Eléctricas | 17 |

Todos son de la marca **DACCORD** (accesorios de baño) y **Karcher** (accesorios industriales). Son productos que no tienen precio de lista porque se cotizan a pedido. El bot los puede encontrar en búsqueda pero no puede armar subtotal — queda en `ambiguous` o `blocked_by_missing_info`.

### Moneda

100% ARS. No hay productos en USD, EUR ni otra moneda. Campo `currency` es constante — no aporta información actualmente pero es correcto tenerlo para escalabilidad.

### Precio máximo inusual

`$141 969 511 ARS` (~$140M) — probablemente un generador industrial, caldera, o compresor de gran porte. Válido para el rubro, no parece error.

### Stock fijo en 999

Todos los productos tienen `stock=999`. Esto indica que el catálogo no tiene integración en tiempo real con el stock real del depósito. La query `H7: always exclude out-of-stock` en `CatalogSearchService._apply_post_filters` nunca filtra nada.

---

## 9. Recomendaciones

| Prioridad | Acción | Impacto |
|---|---|---|
| 🔴 **Alta** | **Documentar el fallback de database.py**: cuando el path tenant no existe, carga `config/catalog.csv` sin precio. Agregar un log de ERROR (no WARNING) y una variable de entorno `CATALOG_PATH_FALLBACK_ENABLED=false` para bloquear el silencio | Previene deploy silencioso con catálogo vacío |
| 🔴 **Alta** | **DT-04 fix**: agregar sinónimos `carrocero=enmascarar`, `mecha=broca` en `language_patterns.yaml`. Conectar al path de `CatalogSearchService` (hoy solo lo usa `ferreteria_quote.py` legacy) | Resuelve falsos negativos de búsqueda |
| 🔴 **Alta** | **Bloquear DISC y TIPS** de búsquedas de catálogo: agregarlos a una blocklist de SKUs o filtrarlos en `_apply_post_filters` (e.g., `stock_qty == 0 and price == 0 and len(name) < 10`) | Evita que aparezcan en respuestas |
| 🟡 **Media** | **Agregar columna `brand`** en `catalog.csv` con el proveedor extraído del sufijo del nombre. Sin esta columna, el filtro de marca de `CatalogSearchService` siempre devuelve vacío | Habilita filtros de marca del usuario |
| 🟡 **Media** | **DT-14: schema de presentación**: agregar `pack_unit` y `pack_qty` al CSV. Auditar con Nacho los ~4 128 productos afectados para poblar los campos | Elimina pregunta redundante de cantidad |
| 🟡 **Media** | **Revisar y subdividir "General"** (22 493 productos = 35.5%): categorías candidatas — Accesorios Baño, Neumáticos y Presión, Herrajes, Fijaciones Especiales | Mejora ranking de búsqueda browse |
| 🟢 **Baja** | **Archivar `config/catalog.csv`**: moverlo a `archive/` o documentarlo explícitamente como "seed legacy sin precios — NO usar en runtime". Los 115 SKUs exclusivos de BlueTools/Bulonfer deberían evaluarse para migrar al catálogo activo o descartar | Elimina confusión del dual-catalog |
| 🟢 **Baja** | **Auditar 752 productos sin precio** con Nacho: los de DACCORD y Karcher que son cotización a pedido deberían tener una flag `requires_quote=true` o directamente excluirse del catálogo online | Evita falsos positivos en búsqueda |
| 🟢 **Baja** | **Agregar dimension parsing al catálogo**: muchos nombres tienen medidas embebidas ("6 mm", "1/2 pulgada", "24 mm x 50 mt"). Parsear esto como campo estructurado mejoraría drásticamente el filtrado de specs | Mejora filtrado dimensional |

---

## 10. Dudas para Julian

1. **¿Los 115 SKUs solo en `config/catalog.csv`** (todos BlueTools/Bulonfer, sin precio) son productos que ya no vendés, o son productos que faltaron migrar al catálogo activo?

2. **DISC y TIPS**: ¿son recursos de algún sistema POS integrado, o son artifacts de un sistema anterior? ¿Los clientes pueden solicitarlos vía WhatsApp?

3. **Los 752 productos sin precio** (principalmente DACCORD y Karcher): ¿son productos que siempre se cotizan manualmente? Si sí, ¿deberían estar en el catálogo del bot o en una lista separada de "consultar precio"?

4. **Stock = 999 para todos**: ¿es un placeholder porque no tienen sistema de stock digital, o el depósito siempre tiene todo disponible? Si hay productos que pueden agotarse, ¿de dónde viene la actualización de stock?

5. **`scripts/update_stock_from_email.py`** abre `config/catalog.csv` directamente (línea 125). ¿Este script corre en producción? Si sí, está usando el catálogo legacy sin precios.

6. **Sinónimo `carrocero → enmascarar`**: ¿Nacho confirma que cuando el cliente dice "cinta de carrocero" siempre se refiere a cinta de enmascarar? ¿O hay una "cinta de carrocero" específica que no tienen en stock?

7. **`language_patterns.yaml`** ya tiene el sinónimo `drywall → durlock` (DT-12). ¿El path de búsqueda nuevo (`CatalogSearchService`) consume ese archivo, o solo lo usa el código legacy en `ferreteria_quote.py`? (Parecería que no lo consume — sería importante verificarlo).
