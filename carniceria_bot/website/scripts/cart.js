// ==========================================
// CART.JS - Lógica Centralizada del Carrito
// ==========================================

// Cart Manager
class CartManager {
    constructor() {
        this.storageKey = 'ateliertechnology_cart';
        this.cart = this.loadCart();
    }

    loadCart() {
        try {
            return JSON.parse(localStorage.getItem(this.storageKey) || '[]');
        } catch {
            return [];
        }
    }

    saveCart() {
        localStorage.setItem(this.storageKey, JSON.stringify(this.cart));
        this.updateUI();
    }

    addItem(item) {
        // item: { sku, name, price, quantity, image, color, storage }
        const existingIndex = this.cart.findIndex(i => i.sku === item.sku);

        if (existingIndex >= 0) {
            this.cart[existingIndex].quantity += item.quantity;
        } else {
            this.cart.push(item);
        }

        this.saveCart();
        this.showDrawer();
    }

    removeItem(sku) {
        this.cart = this.cart.filter(i => i.sku !== sku);
        this.saveCart();
    }

    updateQuantity(sku, quantity) {
        const item = this.cart.find(i => i.sku === sku);
        if (item) {
            item.quantity = Math.max(1, quantity);
            this.saveCart();
        }
    }

    getTotal() {
        return this.cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    }

    getItemCount() {
        return this.cart.reduce((sum, item) => sum + item.quantity, 0);
    }

    clear() {
        this.cart = [];
        this.saveCart();
    }

    updateUI() {
        // Update cart count badge
        const countElement = document.getElementById('cart-count');
        if (countElement) {
            const count = this.getItemCount();
            countElement.textContent = count;
            countElement.style.display = count > 0 ? 'flex' : 'none';
        }

        // Update drawer if open
        this.renderDrawer();
    }

    showDrawer() {
        const drawer = document.getElementById('cart-drawer');
        if (drawer) {
            drawer.classList.add('open');
            document.body.style.overflow = 'hidden';
        }
    }

    hideDrawer() {
        const drawer = document.getElementById('cart-drawer');
        if (drawer) {
            drawer.classList.remove('open');
            document.body.style.overflow = '';
        }
    }

    renderDrawer() {
        const container = document.getElementById('cart-items-container');
        if (!container) return;

        if (this.cart.length === 0) {
            container.innerHTML = `
                <div class="empty-cart">
                    <p>🛒 Tu carrito está vacío</p>
                </div>
            `;
            document.getElementById('cart-total').textContent = '$0';
            document.getElementById('checkout-btn').disabled = true;
            return;
        }

        container.innerHTML = this.cart.map(item => `
            <div class="cart-item" data-sku="${item.sku}">
                <img src="${item.image}" alt="${item.name}" class="cart-item-image">
                <div class="cart-item-info">
                    <h4>${item.name}</h4>
                    ${item.color ? `<p class="cart-item-variant">Color: ${item.color}</p>` : ''}
                    ${item.storage ? `<p class="cart-item-variant">${item.storage}GB</p>` : ''}
                    <p class="cart-item-price">$${formatPrice(item.price)}</p>
                </div>
                <div class="cart-item-controls">
                    <div class="quantity-controls">
                        <button onclick="cart.updateQuantity('${item.sku}', ${item.quantity - 1})">−</button>
                        <span>${item.quantity}</span>
                        <button onclick="cart.updateQuantity('${item.sku}', ${item.quantity + 1})">+</button>
                    </div>
                    <button class="remove-btn" onclick="cart.removeItem('${item.sku}')">
                        🗑️
                    </button>
                </div>
            </div>
        `).join('');

        const totalEl = document.getElementById('cart-total');
        if (totalEl) totalEl.textContent = `$${formatPrice(this.getTotal())}`;

        const btn = document.getElementById('checkout-btn');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Iniciar Compra'; // Update text dynamically
        }
    }

    initiateCheckout() {
        if (this.cart.length === 0) return;

        // Redirect to Web Checkout
        window.location.href = 'checkout.html';
    }
}

// Global cart instance
const cart = new CartManager();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    cart.updateUI();
});

// Helper function
function formatPrice(price) {
    return new Intl.NumberFormat('es-AR').format(price);
}

// Toggle cart drawer
function toggleCart() {
    const drawer = document.getElementById('cart-drawer');
    if (drawer && drawer.classList.contains('open')) {
        cart.hideDrawer();
    } else {
        cart.showDrawer();
    }
}
