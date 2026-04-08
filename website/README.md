# Website Template - Sales Bot Platform

## 📱 Página Web Copiada

He copiado la página web completa del `iphone-bot 2` al `sales-bot-platform` como base para futuros productos.

---

## 📂 Estructura Copiada

```
website/
├── index.html          # Página principal (catálogo de productos)
├── product.html        # Página de detalle de producto individual
├── checkout.html       # Página de checkout/carrito
├── api/                # Scripts de integración con el bot backend
├── scripts/            # JavaScript para funcionalidad del sitio
├── styles/             # CSS para el diseño
└── images/             # Imágenes de productos
```

---

## 🎨 Características del Template

### Actualmente configurado para Ferreteria Central (Herramientas)

La web actual tiene:

- **Hero Section** con branding de Ferreteria Central
- **Catálogo de Herramientas** con filtros por modelo/color/storage
- **Sistema de checkout** integrado
- **Conexión al bot** para consultas en vivo

### Para Adaptar a Otro Producto

#### 1. **Actualizar Branding** (`index.html`)

Buscar y reemplazar:
```html
<!-- Línea ~10-20 -->
<h1>Ferreteria Central</h1>
<p>Ferreteria especializada</p>
```

Cambiar por:
```html
<h1>{{ store_name }}</h1>
<p>{{ store_description }}</p>
```

#### 2. **Modificar Catálogo de Productos** (`scripts/`)

Los scripts actuales cargan productos desde:
```javascript
// api/products.js o similar
fetch('/api/products')
```

Verificar que el endpoint devuelva productos del catálogo correcto.

#### 3. **Actualizar Imágenes** (`images/`)

Reemplazar las imágenes de Herramientas por imágenes del nuevo producto.

#### 4. **Personalizar Estilos** (`styles/`)

Los colores, fuentes y diseño pueden ajustarse en los archivos CSS para que coincidan con la marca del nuevo producto.

---

## 🚀 Cómo Usar el Template

### Opción 1: Servir directamente

```bash
cd website
python3 -m http.server 8080
```

Luego abrir: `http://localhost:8080`

### Opción 2: Integrar con el bot server

El `iphone-bot 2` incluye un script `start_website.sh` que sirve la web. Podés copiar ese script también si lo necesitás.

---

## 🔗 Integración con el Bot

La web se comunica con el bot backend mediante:

1. **API REST** en `api/` para consultas de stock/precios
2. **WebSocket o Polling** para chat en vivo (si está implementado)
3. **Formularios de checkout** que llaman `crear_reserva()` del backend

Asegurate de que estas rutas estén correctamente configuradas en el servidor del bot.

---

## 📝 Próximos Pasos Recomendados

1. **Revisar `index.html`** para entender la estructura base
2. **Personalizar colores/branding** en `styles/main.css` (o similar)
3. **Actualizar catálogo** para que cargue desde tu database del nuevo producto
4. **Testear localmente** con `python3 -m http.server`
5. **Integrar con el bot** para que las consultas funcionen en tiempo real

---

## ✅ Resultado

Ahora tenés una base sólida de e-commerce que podés adaptar a cualquier producto. La misma estructura premium que usa Ferreteria Central para Herramientas puede venderte herramientas, ropa, o lo que sea.

**Ubicación:** `/Users/julian/Desktop/Dev:ai-labs:/sales-bot-platform/website/`
