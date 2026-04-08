// ==========================================
// RELATED PRODUCTS - Cross-selling
// ==========================================

class RelatedProducts {
    constructor() {
        this.rules = {};
    }

    async fetchRelated(currentProduct, allProducts) {
        const category = currentProduct.category;
        const sameCategory = allProducts.filter(p => p.category === category && p.model !== currentProduct.model);
        const otherCategories = allProducts.filter(p => p.category !== category);

        const fromRules = this.rules[category] || [];
        const preferred = allProducts.filter(p => fromRules.includes(p.model) && p.model !== currentProduct.model);

        const merged = [...preferred, ...sameCategory, ...otherCategories];
        return merged
            .reduce((acc, p) => {
                if (!acc.find(item => item.model === p.model)) acc.push(p);
                return acc;
            }, [])
            .slice(0, 3);
    }

    renderSection(products) {
        if (!products || products.length === 0) return '';

        return `
            <div class="related-products-section">
                <h3>También te puede interesar</h3>
                <div class="related-products-grid">
                    ${products.map(p => this.renderCard(p)).join('')}
                </div>
            </div>
        `;
    }

    renderCard(product) {
        const img = this.getProductThumbnail(product);
        return `
            <div class="related-product-card" onclick="navigateToProduct('${product.model}')">
                <img src="${img}" alt="${product.model}" onerror="this.onerror=null;this.src='images/product-placeholder.svg'">
                <h4>${product.model}</h4>
                <p class="related-price">Desde $${product.price_ars?.toLocaleString('es-AR') || '0'}</p>
            </div>
        `;
    }

    getProductThumbnail(product) {
        const category = (product.category || '').toLowerCase();
        const color = (product.color || 'white')
            .toLowerCase()
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .replace(/titanio\s*/gi, '')
            .replace(/negro\s*espacial/gi, 'black')
            .replace(/plata/gi, 'silver')
            .replace(/\s+/g, '-')
            .trim();

        if (category.includes('iphone') || category.includes('smartphone') || category.includes('telefono') || category.includes('celular')) return `images/iphone-${color || 'black'}.png`;
        if (category.includes('macbook') || category.includes('laptop') || category.includes('notebook')) return `images/macbook-${color || 'space-black'}.png`;
        if (category.includes('ipad') || category.includes('tablet')) return `images/ipad-${color}.png`;
        if (category.includes('airpod') || category.includes('audio')) return 'images/airpods-white.png';
        if (category.includes('playstation') || category.includes('gaming')) return 'images/ps5-white.png';

        return 'images/product-placeholder.svg';
    }
}

// Global instance
const relatedProducts = new RelatedProducts();
