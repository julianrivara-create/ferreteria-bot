// ==========================================
// SEARCH & FILTER - Enhanced UX
// ==========================================

class SearchEngine {
    constructor() {
        this.products = [];
        this.searchInput = null;
        this.resultsContainer = null;
    }

    init(products) {
        this.products = products;
        this.createSearchUI();
        this.attachEventListeners();
    }

    createSearchUI() {
        const heroSection = document.querySelector('.hero-store');
        if (!heroSection) return;

        const searchHTML = `
            <div class="search-container">
                <input 
                    type="text" 
                    class="search-bar" 
                    id="global-search"
                    placeholder="Buscar iPhone, MacBook, AirPods..."
                    autocomplete="off"
                >
                <span class="search-icon">🔍</span>
                <div class="search-results" id="search-results"></div>
            </div>
        `;

        heroSection.insertAdjacentHTML('beforeend', searchHTML);
        this.searchInput = document.getElementById('global-search');
        this.resultsContainer = document.getElementById('search-results');
    }

    attachEventListeners() {
        if (!this.searchInput) return;

        let debounceTimer;
        this.searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.performSearch(e.target.value);
            }, 300);
        });

        // Close results when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-container')) {
                this.resultsContainer.classList.remove('active');
            }
        });
    }

    performSearch(query) {
        if (!query || query.length < 2) {
            this.resultsContainer.classList.remove('active');
            return;
        }

        const results = this.products.filter(product => {
            const searchText = `${product.model} ${product.category} ${product.color} ${product.storage_gb || ''}`.toLowerCase();
            return searchText.includes(query.toLowerCase());
        });

        this.renderResults(results.slice(0, 8)); // Limit to 8 results
    }

    renderResults(results) {
        if (results.length === 0) {
            this.resultsContainer.innerHTML = '<div style="padding:20px;text-align:center;color:rgba(255,255,255,0.5)">No se encontraron productos</div>';
            this.resultsContainer.classList.add('active');
            return;
        }

        this.resultsContainer.innerHTML = results.map(product => {
            const img = this.getProductThumbnail(product);
            return `
                <div class="search-result-item" onclick="navigateToProduct('${product.model}')">
                    <img src="${img}" alt="${product.model}" class="search-result-img" onerror="this.src='images/iphone15pro.png'">
                    <div class="search-result-info">
                        <h4>${product.model}</h4>
                        <p>${product.storage_gb ? product.storage_gb + 'GB' : ''} ${product.color || ''} - $${product.price_ars.toLocaleString('es-AR')}</p>
                    </div>
                </div>
            `;
        }).join('');

        this.resultsContainer.classList.add('active');
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

        if (category === 'iphone') return `images/iphone-${color}.png`;
        if (category === 'macbook') return `images/macbook-${color}.png`;
        if (category === 'ipad') return `images/ipad-${color}.png`;
        if (category === 'airpods') return 'images/airpods-white.png';
        if (category === 'playstation') return 'images/ps5-white.png';

        return 'images/iphone15pro.png';
    }
}

// Initialize search when catalog loads
const searchEngine = new SearchEngine();

// Hook into existing fetchProducts
const originalFetchProducts = window.fetchProducts;
if (typeof originalFetchProducts === 'function') {
    window.fetchProducts = async function () {
        await originalFetchProducts();
        searchEngine.init(catalog);
    };
}
