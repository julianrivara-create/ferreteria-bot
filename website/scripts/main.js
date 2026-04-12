// Tenant-aware storefront renderer

let catalog = [];
let storefront = {};

function resolveTenantSlug() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get('tenant') || params.get('t');
    if (fromQuery) return fromQuery;

    const match = window.location.pathname.match(/\/t\/([^/]+)/);
    if (match && match[1]) return match[1];

    return 'default';
}

const TENANT_SLUG = resolveTenantSlug();
const API_URL = `/api`;
window.__TENANT_SLUG = TENANT_SLUG;
const PRODUCT_FALLBACK_IMAGE = 'images/product-placeholder.svg';

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Fetch storefront first so categories are available for per-category product loading.
    await fetchStorefront();
    renderStorefront();   // renders nav + category links immediately

    // Render category shells with loading placeholders, then fill each lazily.
    renderProductShells();
    await loadAllCategoryProducts();
});

async function fetchStorefront() {
    try {
        const response = await fetch(`${API_URL}/storefront?tenant=${TENANT_SLUG}`);
        if (!response.ok) throw new Error('storefront request failed');
        storefront = await response.json();
    } catch (error) {
        console.error('Error fetching storefront:', error);
        storefront = {
            store_name: 'Salesbot Store',
            store_description: 'Catalogo',
            categories: [],
            branding: {}
        };
    }
}

async function fetchProductsByCategory(category, limit = 200) {
    const params = new URLSearchParams({ limit, tenant: TENANT_SLUG });
    if (category) params.set('category', category);
    const response = await fetch(`${API_URL}/catalog/grouped?${params}`);
    if (!response.ok) throw new Error(`products request failed for category: ${category}`);
    const data = await response.json();
    return Array.isArray(data) ? data : (data.products || []);
}

async function loadAllCategoryProducts() {
    const categories = storefront.categories && storefront.categories.length
        ? storefront.categories
        : [];
    if (!categories.length) return;

    // Load categories in parallel batches of 4 to avoid overwhelming the server.
    for (let i = 0; i < categories.length; i += 4) {
        await Promise.allSettled(
            categories.slice(i, i + 4).map(cat => loadOneCategoryProducts(cat))
        );
    }
}

async function loadOneCategoryProducts(category) {
    const anchor = categoryAnchor(category);
    const grid = document.getElementById(`grid-${anchor}`);
    if (!grid) return;

    try {
        const items = await fetchProductsByCategory(category);
        // Merge into global catalog (replace any existing items for this category).
        catalog = catalog.filter(p => p.category !== category).concat(items);
        grid.innerHTML = renderCategoryGridContent(category);
    } catch (e) {
        console.error('Error loading category:', category, e);
        grid.innerHTML = '<p class="specs">Error cargando productos.</p>';
    }
}

function renderStorefront() {
    const branding = storefront.branding || {};
    const storeName = storefront.store_name || 'Salesbot Store';
    const storeDesc = storefront.store_description || 'Catalogo';

    document.title = `${storeName} | Store`;

    const storeNameEls = document.querySelectorAll('[data-store-name]');
    storeNameEls.forEach(el => {
        el.textContent = storeName;
    });

    const taglineEl = document.getElementById('store-tagline');
    if (taglineEl) taglineEl.textContent = branding.tagline || storeDesc;

    const heroTitle = document.getElementById('hero-title');
    if (heroTitle) heroTitle.textContent = branding.hero_title || storeName;

    const heroSubtitle = document.getElementById('hero-subtitle');
    if (heroSubtitle) heroSubtitle.textContent = branding.hero_subtitle || storeDesc;

    if (branding.accent_color) {
        document.documentElement.style.setProperty('--accent-color', branding.accent_color);
        document.documentElement.style.setProperty('--primary-color', branding.accent_color);
    }
    if (branding.secondary_color) {
        document.documentElement.style.setProperty('--secondary-color', branding.secondary_color);
    }

    renderCategoryNav();
}

function renderCategoryNav() {
    const nav = document.getElementById('categories-nav');
    if (!nav) return;

    const categories = storefront.categories && storefront.categories.length
        ? storefront.categories
        : [...new Set(catalog.map(item => item.category).filter(Boolean))];

    const links = categories.map(cat => {
        const anchor = categoryAnchor(cat);
        return `<a href="#${anchor}" onclick="smoothScrollTo('${anchor}')">${cat}</a>`;
    });

    nav.innerHTML = links.join('');

    const footer = document.getElementById('footer-categories');
    if (footer) {
        footer.innerHTML = categories
            .map(cat => {
                const anchor = categoryAnchor(cat);
                return `<p><a href=\"#${anchor}\" onclick=\"smoothScrollTo('${anchor}')\">${cat}</a></p>`;
            })
            .join('');
    }
}

function renderProductShells() {
    const sectionsRoot = document.getElementById('dynamic-sections');
    if (!sectionsRoot) return;

    const categories = storefront.categories && storefront.categories.length
        ? storefront.categories
        : [];

    if (!categories.length) {
        sectionsRoot.innerHTML = '<section class="products"><div class="container"><p>Sin productos disponibles.</p></div></section>';
        return;
    }

    // Render section shells with loading placeholders immediately so the page
    // feels responsive. Product grids are filled by loadOneCategoryProducts().
    sectionsRoot.innerHTML = categories
        .map((cat, idx) => renderCategoryShell(cat, idx % 2 === 1))
        .join('');
}

function renderCategoryShell(category, dark) {
    const anchor = categoryAnchor(category);
    return `
    <section class="products" id="${anchor}" ${dark ? 'style="background: #111;"' : ''}>
        <div class="container">
            <div class="section-header-left">
                <h2>${category}</h2>
                <p>Productos disponibles en esta categoria.</p>
            </div>
            <div class="grid product-grid" id="grid-${anchor}">
                <p class="specs" style="opacity:0.5">Cargando productos…</p>
            </div>
        </div>
    </section>`;
}

function renderCategoryGridContent(category) {
    const categoryItems = catalog.filter(item => item.category === category);

    const byModel = new Map();
    categoryItems.forEach(item => {
        const key = item.model || item.name || item.sku;
        if (!byModel.has(key)) byModel.set(key, []);
        byModel.get(key).push(item);
    });

    const cards = [...byModel.values()].map(variants => {
        const first = variants[0];
        const minPrice = Math.min(...variants.map(v => Number(v.price_ars || 0)));
        const viewModel = first.model || first.name || first.sku;

        return createProductCard({
            ...first,
            model: viewModel,
            price_ars: minPrice,
            variant_count: variants.length
        });
    });

    return cards.length ? cards.join('') : '<p class="specs">Sin stock disponible.</p>';
}

function createProductCard(item) {
    const imgSrc = getProductImage(item);
    const priceValue = Number(item.price_ars || item.price || 0);

    return `
    <div class="product-card" onclick="navigateToProduct('${escapeForAttr(item.model)}')" style="cursor: pointer;">
        <div class="product-image">
            <img src="${imgSrc}"
                 alt="${item.model}"
                 class="product-img"
                 loading="lazy"
                 onload="this.style.opacity=1"
                 onerror="this.onerror=null; this.src='${PRODUCT_FALLBACK_IMAGE}'">
        </div>
        <div class="product-info">
            <h3>${item.model}</h3>
            <p class="specs">${item.color ? item.color : ''}${item.storage_gb ? ` • ${item.storage_gb}GB` : ''}</p>
            <div class="price-row">
                <span class="price">$${priceValue.toLocaleString('es-AR')} ${storefront.currency || 'ARS'}</span>
            </div>
            <button class="btn-buy" onclick="event.stopPropagation(); quickAddToCart('${escapeForAttr(item.model)}')">Ver Detalles</button>
        </div>
    </div>
    `;
}

function categoryAnchor(category) {
    return String(category)
        .toLowerCase()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'categoria';
}

function escapeForAttr(value) {
    return String(value).replace(/'/g, "\\'");
}

function getProductImage(item) {
    const category = String(item.category || '').toLowerCase();
    const name = String(item.name || item.model || '').toLowerCase();

    // Ferretería categories
    if (category.includes('herramientas el') || category.includes('electrica')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('herramientas manuales')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('mechas') || category.includes('brocas')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('discos') || category.includes('hojas')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('pinturas') || category.includes('acabados') || category.includes('pintur')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('plomer') || category.includes('plomeria')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('torniller') || category.includes('fijacion')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('electricidad')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('seguridad')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('lijas') || category.includes('abrasivos')) {
        return PRODUCT_FALLBACK_IMAGE;
    }
    if (category.includes('cintas') || category.includes('adhesivos')) {
        return PRODUCT_FALLBACK_IMAGE;
    }

    // Use item image_url if provided by the API
    if (item.image_url) return item.image_url;

    // Legacy electronics (kept for multi-tenant compatibility)
    const color = String(item.color || '').toLowerCase();
    if (category.includes('smartphone') || category.includes('telefono') || category.includes('celular')) {
        if (color.includes('blue') || color.includes('azul')) return 'images/iphone-blue.png';
        if (color.includes('pink') || color.includes('rosa')) return 'images/iphone-pink.png';
        if (color.includes('black') || color.includes('negro')) return 'images/iphone-black.png';
        if (color.includes('white') || color.includes('blanco')) return 'images/iphone-white.png';
        return 'images/iphone-black.png';
    }
    if (category.includes('laptop')) return 'images/macbook-space-black.png';
    if (category.includes('tablet')) return 'images/ipad-blue.png';
    if (category.includes('audio')) return 'images/airpods-white.png';
    if (category.includes('gaming')) return 'images/ps5-digital-white.png';

    return PRODUCT_FALLBACK_IMAGE;
}

function navigateToProduct(model) {
    window.location.href = `product.html?tenant=${encodeURIComponent(TENANT_SLUG)}&model=${encodeURIComponent(model)}`;
}

function quickAddToCart(model) {
    navigateToProduct(model);
}

function scrollToProducts() {
    const firstSection = document.querySelector('#dynamic-sections section.products');
    if (firstSection) firstSection.scrollIntoView({ behavior: 'smooth' });
}

function smoothScrollTo(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
}

function toggleCart() {
    if (typeof cart !== 'undefined') {
        cart.showDrawer();
    } else {
        alert('Carrito aun no disponible');
    }
}
