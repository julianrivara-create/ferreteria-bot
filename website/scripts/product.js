// Product Detail Page Logic (tenant-aware, multi-industry)

function resolveTenantSlug() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get('tenant') || params.get('t');
    if (fromQuery) return fromQuery;

    const match = window.location.pathname.match(/\/t\/([^/]+)/);
    if (match && match[1]) return match[1];

    return 'default';
}

const TENANT_SLUG = resolveTenantSlug();
const API_URL = `/api/t/${TENANT_SLUG}`;
const PRODUCT_FALLBACK_IMAGE = 'images/product-placeholder.svg';

let productData = null;
let selectedVariant = {
    color: null,
    storage: null,
    condition: null,
};

document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const model = urlParams.get('model');

    if (!model) {
        showError('No se especifico un producto');
        return;
    }

    loadProduct(model);
});

async function loadProduct(model) {
    try {
        const response = await fetch(`${API_URL}/product?model=${encodeURIComponent(model)}`);
        if (!response.ok) {
            showError('Este producto no esta disponible actualmente.');
            return;
        }

        productData = await response.json();
        renderProduct();
    } catch (error) {
        console.error('Error loading product:', error);
        showError('Error de conexion. Intenta nuevamente.');
    }
}

function renderProduct() {
    const container = document.getElementById('product-container');

    container.innerHTML = `
        <div class="product-image-section">
            <img src="${getProductImage(productData)}" alt="${productData.model}" class="product-main-image" onerror="this.onerror=null;this.src='${PRODUCT_FALLBACK_IMAGE}'">
        </div>

        <div class="product-info-section">
            <h1>${productData.model}</h1>
            <div class="product-price" id="dynamic-price">
                $${formatPrice(productData.base_price || productData.price_ars)} ${productData.currency || 'ARS'}
            </div>
            <p class="product-description">Producto disponible con variantes por stock real.</p>

            ${renderStockBadge(productData)}
            ${renderVariantSelectors()}

            <div class="cta-section">
                <button class="btn-buy-now" onclick="handleBuyNow()" id="buy-btn">
                    Comprar Ahora
                </button>
            </div>

            ${renderTechnicalSpecs(productData)}
        </div>
    `;

    autoSelectDefaults();
    updateBreadcrumbs();
    loadRelatedProducts();
}

async function loadRelatedProducts() {
    if (typeof relatedProducts === 'undefined') return;

    try {
        const response = await fetch(`${API_URL}/products`);
        if (!response.ok) return;

        const allProducts = await response.json();
        const related = await relatedProducts.fetchRelated(productData, allProducts);

        const productInfo = document.querySelector('.product-info-section');
        if (productInfo && related.length > 0) {
            productInfo.insertAdjacentHTML('beforeend', relatedProducts.renderSection(related));
        }
    } catch (error) {
        console.error('Error loading related products:', error);
    }
}

function updateBreadcrumbs() {
    const categoryEl = document.getElementById('breadcrumb-category');
    const modelEl = document.getElementById('breadcrumb-model');

    if (categoryEl) categoryEl.textContent = productData.category || 'Producto';
    if (modelEl) modelEl.textContent = productData.model || '';
}

function renderVariantSelectors() {
    let html = '';

    if (productData.colors && productData.colors.length > 0) {
        html += `
            <div class="variant-section">
                <span class="variant-label">Color</span>
                <div class="color-options">
                    ${productData.colors.map(color => `
                        <div class="color-bubble"
                             style="background: ${getColorHex(color)}"
                             data-color="${color}"
                             onclick="selectColor('${color}')">
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    if (productData.storage_options && productData.storage_options.length > 0) {
        html += `
            <div class="variant-section">
                <span class="variant-label">Opciones</span>
                <div class="storage-options">
                    ${productData.storage_options.map(storage => {
            const stockInfo = getStockForVariant({ storage });
            const disabled = stockInfo.stock === 0;
            return `
                            <button class="storage-btn"
                                    data-storage="${storage}"
                                    onclick="selectStorage(${storage})"
                                    ${disabled ? 'disabled' : ''}>
                                ${storage}${Number(storage) > 0 ? 'GB' : ''}
                                ${stockInfo.stock === 0 ? '<span class="stock-indicator">Sin stock</span>' : ''}
                            </button>
                        `;
        }).join('')}
                </div>
            </div>
        `;
    }

    return html;
}

function selectColor(color) {
    selectedVariant.color = color;
    updateUI('color', color);
    updateProductImage(color);
    updatePrice();
}

function selectStorage(storage) {
    selectedVariant.storage = storage;
    updateUI('storage', storage);
    updatePrice();
}

function updateUI(type, value) {
    document.querySelectorAll(`[data-${type}]`).forEach(el => el.classList.remove('selected'));
    const element = document.querySelector(`[data-${type}="${value}"]`);
    if (element) element.classList.add('selected');
}

async function updatePrice() {
    const priceElement = document.getElementById('dynamic-price');
    try {
        const params = new URLSearchParams({
            model: productData.model,
            ...(selectedVariant.color && { color: selectedVariant.color }),
            ...(selectedVariant.storage && { storage: selectedVariant.storage })
        });

        const response = await fetch(`${API_URL}/product/price?${params}`);
        const data = await response.json();

        if (data.price !== undefined) {
            priceElement.textContent = `$${formatPrice(data.price)} ${data.currency || 'ARS'}`;
        }
    } catch (error) {
        console.error('Error updating price:', error);
    }
}

function autoSelectDefaults() {
    if (productData.colors && productData.colors.length > 0) {
        selectColor(productData.colors[0]);
    }
    if (productData.storage_options && productData.storage_options.length > 0) {
        selectStorage(productData.storage_options[0]);
    }
}

async function handleBuyNow() {
    if (!productData || !productData.variants) return;

    const selectedStorageNum = selectedVariant.storage ? parseInt(selectedVariant.storage, 10) : null;

    const matchingVariant = productData.variants.find(v => {
        const colorMatch = !selectedVariant.color || v.color === selectedVariant.color;
        const storageMatch = !selectedStorageNum || Number(v.storage_gb || 0) === selectedStorageNum;
        return colorMatch && storageMatch;
    }) || productData.variants[0];

    const cartItem = {
        sku: matchingVariant.sku,
        name: productData.model,
        price: matchingVariant.price_ars,
        quantity: 1,
        image: getProductImage(productData),
        color: selectedVariant.color || matchingVariant.color || null,
        storage: selectedStorageNum || null
    };

    if (typeof cart !== 'undefined') {
        cart.addItem(cartItem);
        const btn = document.querySelector('.btn-buy-now');
        if (btn) {
            const originalText = btn.textContent;
            btn.textContent = 'Agregado';
            setTimeout(() => {
                btn.textContent = originalText;
            }, 900);
        }
    } else {
        alert('Producto agregado');
    }
}

function getStockForVariant(criteria) {
    if (!productData.variants) return { stock: 0 };

    const matchingVariants = productData.variants.filter(v => {
        let match = true;
        if (criteria.color) match = match && v.color === criteria.color;
        if (criteria.storage) match = match && Number(v.storage_gb || 0) === parseInt(criteria.storage, 10);
        return match;
    });

    const totalStock = matchingVariants.reduce((sum, v) => sum + Number(v.stock_qty || 0), 0);
    return { stock: totalStock, variants: matchingVariants };
}

function updateProductImage(color) {
    const img = document.querySelector('.product-main-image');
    if (!img) return;
    img.src = getProductImage({ ...productData, color });
}

function getProductImage(product) {
    const category = String(product.category || '').toLowerCase();
    const color = String(product.color || '').toLowerCase();

    if (category.includes('smartphone') || category.includes('telefono') || category.includes('celular') || category.includes('mobile')) {
        if (color.includes('blue') || color.includes('azul')) return 'images/iphone-blue.png';
        if (color.includes('pink') || color.includes('rosa')) return 'images/iphone-pink.png';
        if (color.includes('black') || color.includes('negro')) return 'images/iphone-black.png';
        if (color.includes('white') || color.includes('blanco')) return 'images/iphone-white.png';
        return 'images/iphone-black.png';
    }

    if (category.includes('laptop') || category.includes('notebook') || category.includes('macbook')) return 'images/macbook-space-black.png';
    if (category.includes('tablet') || category.includes('ipad')) return 'images/ipad-blue.png';
    if (category.includes('audio') || category.includes('airpod')) return 'images/airpods-white.png';
    if (category.includes('playstation') || category.includes('gaming')) return 'images/ps5-digital-white.png';
    return PRODUCT_FALLBACK_IMAGE;
}

function getProductDescription() {
    return 'Detalle de producto configurable por tenant.';
}

function renderStockBadge(data) {
    const stock = (data.variants || []).reduce((sum, v) => sum + Number(v.stock_qty || 0), 0);
    const className = stock > 10 ? 'in-stock' : stock > 0 ? 'low-stock' : 'out-stock';
    const label = stock > 10 ? 'En stock' : stock > 0 ? `Quedan ${stock}` : 'Sin stock';
    return `<div class="stock-badge ${className}">${label}</div>`;
}

function renderTechnicalSpecs(data) {
    return `
        <div class="tech-specs">
            <h3>Especificaciones</h3>
            <ul>
                <li><strong>Categoria:</strong> ${data.category || 'General'}</li>
                <li><strong>Variantes:</strong> ${(data.variants || []).length}</li>
                <li><strong>SKU base:</strong> ${(data.variants && data.variants[0] && data.variants[0].sku) || '-'}</li>
            </ul>
        </div>`;
}

function formatPrice(price) {
    return Number(price || 0).toLocaleString('es-AR');
}

function getColorHex(color) {
    if (!color) return '#d1d5db';
    const c = color.toLowerCase();
    if (c.includes('black') || c.includes('negro')) return '#111111';
    if (c.includes('white') || c.includes('blanco')) return '#f5f5f5';
    if (c.includes('blue') || c.includes('azul')) return '#3b82f6';
    if (c.includes('red') || c.includes('rojo')) return '#ef4444';
    if (c.includes('green') || c.includes('verde')) return '#22c55e';
    if (c.includes('pink') || c.includes('rosa')) return '#ec4899';
    return '#9ca3af';
}

function showError(message) {
    const container = document.getElementById('product-container');
    if (!container) return;
    container.innerHTML = `
        <div class="error-state">
            <h2>No disponible</h2>
            <p>${message}</p>
            <a href="index.html?tenant=${encodeURIComponent(TENANT_SLUG)}" class="btn-buy-now">Volver al catalogo</a>
        </div>
    `;
}
