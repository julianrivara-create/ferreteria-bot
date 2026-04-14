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
        return product.image_url || 'images/product-placeholder.svg';
    }
}

// Global instance
const relatedProducts = new RelatedProducts();
