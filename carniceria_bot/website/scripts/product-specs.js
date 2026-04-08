// Technical Specifications Data
const TECHNICAL_SPECS = {
    'iPhone 17 Pro': {
        'Pantalla': '6.3" Super Retina XDR OLED',
        'Chip': 'A19 Pro (3nm)',
        'Cámara': 'Triple 48MP + Teleobjetivo',
        'Batería': 'Hasta 28 horas de video',
        'Peso': '206 gramos'
    },
    'iPhone 17': {
        'Pantalla': '6.1" Super Retina XDR',
        'Chip': 'A18',
        'Cámara': 'Dual 48MP',
        'Batería': 'Hasta 20 horas',
        'Peso': '174 gramos'
    },
    'iPhone 17 Pro Max': {
        'Pantalla': '6.7" Super Retina XDR OLED',
        'Chip': 'A19 Pro (3nm)',
        'Cámara': 'Triple 48MP + Periscopio',
        'Batería': 'Hasta 29 horas',
        'Peso': '221 gramos'
    },
    'iPhone 15': {
        'Pantalla': '6.1" Super Retina XDR',
        'Chip': 'A16 Bionic',
        'Cámara': 'Dual 48MP + 12MP',
        'Batería': 'Hasta 20 horas',
        'Peso': '171 gramos'
    },
    'MacBook Air M2': {
        'Pantalla': '13.6" Liquid Retina',
        'Chip': 'Apple M2 (8 núcleos)',
        'RAM': 'Hasta 24GB unificada',
        'Almacenamiento': 'Hasta 2TB SSD',
        'Peso': '1.24 kg'
    },
    'MacBook Pro 14': {
        'Pantalla': '14.2" Liquid Retina XDR',
        'Chip': 'M2 Pro / M2 Max',
        'RAM': 'Hasta 96GB',
        'Batería': 'Hasta 18 horas',
        'Peso': '1.6 kg'
    },
    'MacBook Pro 16': {
        'Pantalla': '16.2" Liquid Retina XDR',
        'Chip': 'M2 Pro / M2 Max',
        'RAM': 'Hasta 96GB unificada',
        'Batería': 'Hasta 22 horas',
        'Peso': '2.15 kg'
    },
    'iPad Pro 11': {
        'Pantalla': '11" Liquid Retina',
        'Chip': 'Apple M2',
        'Cámara': '12MP gran angular',
        'Batería': 'Hasta 10 horas',
        'Peso': '466 gramos'
    },
    'iPad Pro 12.9': {
        'Pantalla': '12.9" Liquid Retina XDR',
        'Chip': 'Apple M2',
        'Cámara': '12MP ultra gran angular',
        'Batería': 'Hasta 10 horas',
        'Peso': '682 gramos'
    },
    'iPad Air 5': {
        'Pantalla': '10.9" Liquid Retina',
        'Chip': 'Apple M1',
        'Cámara': '12MP gran angular',
        'Batería': 'Hasta 10 horas',
        'Peso': '461 gramos'
    },
    'AirPods Pro 2nd Gen': {
        'Chip': 'H2 de Apple',
        'Cancelación': 'Activa de ruido 2x',
        'Batería': 'Hasta 6h (30h con estuche)',
        'Resistencia': 'IPX4 (agua y sudor)',
        'Conectividad': 'Bluetooth 5.3'
    },
    'AirPods 3rd Gen': {
        'Chip': 'H1 de Apple',
        'Audio': 'Espacial con seguimiento',
        'Batería': '6h (30h con estuche)',
        'Resistencia': 'IPX4',
        'Conectividad': 'Bluetooth 5.0'
    },
    'AirPods Max': {
        'Chip': 'H1 (dos unidades)',
        'Controladores': '40mm dinámicos',
        'Cancelación': 'Activa de ruido',
        'Batería': 'Hasta 20 horas',
        'Peso': '384.8 gramos'
    },
    'PlayStation 5': {
        'CPU': 'AMD Zen 2 (8 núcleos)',
        'GPU': 'AMD RDNA 2 (10.28 TFLOPS)',
        'RAM': '16GB GDDR6',
        'Almacenamiento': '825GB SSD NVMe',
        'Resolución': 'Hasta 8K'
    },
    'PlayStation 5 Digital': {
        'CPU': 'AMD Zen 2 (8 núcleos)',
        'GPU': 'AMD RDNA 2',
        'RAM': '16GB GDDR6',
        'Almacenamiento': '825GB SSD',
        'Edición': 'Solo Digital'
    }
};

// Render stock badge
function renderStockBadge(productData) {
    const totalStock = productData.variants ?
        productData.variants.reduce((sum, v) => sum + (v.stock_qty || 0), 0) : 0;

    if (totalStock === 0) {
        return `<div class="stock-badge out-of-stock">Sin Stock</div>`;
    } else if (totalStock <= 5) {
        return `<div class="stock-badge low-stock">⚠️ Últimas ${totalStock} unidades</div>`;
    } else {
        return `<div class="stock-badge in-stock">✓ En Stock (${totalStock} disponibles)</div>`;
    }
}

// Render technical specifications
function renderTechnicalSpecs(productData) {
    const specs = TECHNICAL_SPECS[productData.model];
    if (!specs) return '';

    const rows = Object.entries(specs).map(([key, value]) => `
        <tr>
            <td class="spec-label">${key}</td>
            <td class="spec-value">${value}</td>
        </tr>
    `).join('');

    return `
        <div class="tech-specs-section">
            <h3>Especificaciones Técnicas</h3>
            <table class="specs-table">
                ${rows}
            </table>
            <p class="shipping-info">🚚 <strong>Envío Gratis</strong> a todo el país</p>
        </div>
    `;
}
