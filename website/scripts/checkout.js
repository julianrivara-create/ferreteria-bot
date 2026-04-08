// Checkout Logic

let selectedPayment = 'credit';
const CHECKOUT_TENANT = (() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('tenant') || window.__TENANT_SLUG || 'default';
})();

document.addEventListener('DOMContentLoaded', () => {
    renderOrderSummary();
});

function renderOrderSummary() {
    // Re-use cart data from global cart instance (loaded via cart.js)
    const items = cart.cart;
    const container = document.getElementById('summary-items-container');
    const subtotalEl = document.getElementById('summary-subtotal');
    const totalEl = document.getElementById('summary-total');

    if (items.length === 0) {
        window.location.href = `index.html?tenant=${encodeURIComponent(CHECKOUT_TENANT)}`; // Redirect if empty
        return;
    }

    container.innerHTML = items.map(item => `
        <div class="summary-item">
            <img src="${item.image}" alt="${item.name}">
            <div class="summary-details">
                <h4>${item.name}</h4>
                <p>${item.color || ''} ${item.storage ? `• ${item.storage}GB` : ''}</p>
                <p>Cant: ${item.quantity}</p>
                <p><strong>$${formatPrice(item.price * item.quantity)}</strong></p>
            </div>
        </div>
    `).join('');

    const total = cart.getTotal();
    subtotalEl.textContent = `$${formatPrice(total)}`;
    totalEl.textContent = `$${formatPrice(total)} ARS`;
}

function selectPayment(method) {
    selectedPayment = method;
    document.querySelectorAll('.payment-option').forEach(opt => opt.classList.remove('selected'));

    if (method === 'credit') {
        document.querySelectorAll('.payment-option')[0].classList.add('selected');
    } else if (method === 'mercadopago') {
        document.querySelectorAll('.payment-option')[1].classList.add('selected');
    } else if (method === 'transfer') {
        document.querySelectorAll('.payment-option')[2].classList.add('selected');
    }
}

async function handlePlaceOrder() {
    // Validate fields
    const requiredIds = ['email', 'firstName', 'lastName', 'address', 'city', 'zip', 'phone'];
    let isValid = true;

    requiredIds.forEach(id => {
        const el = document.getElementById(id);
        if (!el.value.trim()) {
            el.style.borderColor = 'red';
            isValid = false;
        } else {
            el.style.borderColor = '#d2d2d7';
        }
    });

    if (!isValid) {
        alert('Por favor completa todos los campos requeridos.');
        return;
    }

    // Simulate Processing
    const btn = document.querySelector('.place-order-btn');
    const originalText = btn.textContent;

    btn.textContent = 'Procesando...';
    btn.disabled = true;
    btn.style.opacity = '0.7';

    // Fake API delay
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Success State
    showSuccessModal();

    // Clear Cart
    cart.clear();
}

function showSuccessModal() {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
        backdrop-filter: blur(5px);
    `;

    const content = document.createElement('div');
    content.style.cssText = `
        background: white;
        padding: 40px;
        border-radius: 20px;
        text-align: center;
        max-width: 400px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        animation: scaleIn 0.3s ease;
    `;

    // Order ID Generator
    const orderId = 'ORD-' + Math.random().toString(36).substr(2, 9).toUpperCase();

    content.innerHTML = `
        <div style="font-size: 60px; margin-bottom: 20px;">🎉</div>
        <h2 style="margin-bottom: 10px; color: #1d1d1f;">¡Pago Exitoso!</h2>
        <p style="color: #666; line-height: 1.5; margin-bottom: 20px;">
            Tu orden <strong>${orderId}</strong> ha sido confirmada.
            <br>Te enviamos el recibo a tu email.
        </p>
        <button style="
            background: #0071e3;
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 20px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
        ">Volver a la Tienda</button>
    `;

    const returnBtn = content.querySelector('button');
    if (returnBtn) {
        returnBtn.addEventListener('click', () => {
            window.location.href = `index.html?tenant=${encodeURIComponent(CHECKOUT_TENANT)}`;
        });
    }

    // Add animation style
    const style = document.createElement('style');
    style.textContent = `
        @keyframes scaleIn {
            from { transform: scale(0.9); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
        }
    `;
    document.head.appendChild(style);

    modal.appendChild(content);
    document.body.appendChild(modal);
}
