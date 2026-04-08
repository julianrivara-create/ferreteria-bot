#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sales Bot Template Generator v2.0
Clona el bot enterprise y lo configura para cualquier negocio

Incluye TODAS las mejoras del Sprint 1:
- JWT Auth + RBAC
- PII Encryption  
- Redis caching
- Sentry monitoring
- 130+ tests
- CI/CD pipeline
- Docker ready
- Analytics engine
"""

import os
import shutil
import json
import re
from datetime import datetime
import argparse

class BotTemplateGenerator:
    """Generador de bots personalizados v2.0"""
    
    VERSION = "2.0.0"
    
    def __init__(self):
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        
    def run_interactive_setup(self):
        """Wizard interactivo mejorado con nuevas categorías"""
        print("=" * 70)
        print(f"🤖  SALES BOT TEMPLATE GENERATOR v{self.VERSION}")
        print("=" * 70)
        print("✨ Ahora con Security, Monitoring, Caching y 130+ Tests!")
        print()
        
        config = {}
        
        config['business_name'] = input("📝 Nombre del negocio: ").strip()
        
        print("\n📦 Categorías disponibles:")
        categories_list = [
            "1.  Electronics (celulares, computadoras)",
            "2.  Clothing (ropa, accesorios)",
            "3.  Food & Beverages (restaurante, cafetería)",
            "4.  Pharmacy (farmacia, salud)  ✨ NUEVO",
            "5.  Automotive (autos, motos)",
            "6.  Services (servicios profesionales)",
            "7.  Real Estate (inmobiliaria)",
            "8.  Beauty & Wellness (spa, salón)  ✨ NUEVO",
            "9.  Pet Shop (mascotas, veterinaria)  ✨ NUEVO",
            "10. Grocery (supermercado, almacén)  ✨ NUEVO",
            "11. Other (otro - personalizable)"
        ]
        
        for cat in categories_list:
            print(cat)
        
        category_num = input("\nElegí categoría (1-11): ").strip()
        categories = {
            '1': 'electronics', '2': 'clothing', '3': 'food',
            '4': 'pharmacy', '5': 'automotive', '6': 'services',
            '7': 'real_estate', '8': 'beauty_wellness', '9': 'pet_shop',
            '10': 'grocery', '11': 'other'
        }
        config['category'] = categories.get(category_num, 'other')
        
        print("\n💰 Monedas disponibles:")
        print("1. ARS (Peso Argentino)")
        print("2. USD (Dólar)")
        print("3. MXN (Peso Mexicano)")
        print("4. EUR (Euro)")
        print("5. BRL (Real Brasileño)")
        
        currency_num = input("Elegí moneda (1-5): ").strip()
        currencies = {'1': 'ARS', '2': 'USD', '3': 'MXN', '4': 'EUR', '5': 'BRL'}
        config['currency'] = currencies.get(currency_num, 'ARS')
        
        config['language'] = input("\n🌍 Idioma (es/en/pt) [es]: ").strip() or 'es'
        
        print("\n🎨 Tono del bot:")
        print("1. Informal (che, dale, etc.)")
        print("2. Formal (usted, señor/a)")
        print("3. Profesional (neutro)")
        
        tone_num = input("Elegí tono (1-3): ").strip()
        tones = {'1': 'informal', '2': 'formal', '3': 'professional'}
        config['tone'] = tones.get(tone_num, 'informal')
        
        config['use_emojis'] = input("\n😊 ¿Usar emojis? (s/n) [s]: ").strip().lower() != 'n'
        
        # Sprint 1 Features (todas incluidas por default)
        print("\n🔐 SECURITY & PERFORMANCE (Incluidas automáticamente):")
        print("  ✅ JWT Authentication + RBAC")
        print("  ✅ PII Encryption at rest")
        print("  ✅ Input sanitization (XSS, SQL)")
        print("  ✅ Rate limiting")
        print("  ✅ Database optimization (11 indices)")
        print("  ✅ Health checks")
        print("  ✅ Sentry monitoring")
        
        # Optional Features
        print("\n✨ FEATURES OPCIONALES:")
        config['features'] = {
            # Core features (siempre incluidas)
            'authentication': True,
            'encryption': True,
            'sanitization': True,
            'health_checks': True,
            'monitoring': True,
            
            # Optional features
            'redis_cache': self._ask_yes_no("Redis Caching (60% cost reduction)"),
            'shopping_cart': self._ask_yes_no("Shopping Cart (multi-product)"),
            'analytics_dashboard': self._ask_yes_no("Analytics Dashboard (funnel, CLV)"),
            'bundles': self._ask_yes_no("Bundles/Packages"),
            'recommendations': self._ask_yes_no("AI Recommendations"),
            'upselling': self._ask_yes_no("Upselling automático"),
            'email_notifications': self._ask_yes_no("Email notifications"),
            'mercadopago': self._ask_yes_no("MercadoPago payments"),
            'whatsapp_business': self._ask_yes_no("WhatsApp Business API"),
            'webchat': self._ask_yes_no("Web Chat widget"),
            'google_sheets': self._ask_yes_no("Google Sheets sync"),
            'appointment_booking': self._is_service_business(config['category']) and 
                                    self._ask_yes_no("Appointment booking system")
        }
        
        return config
    
    def _is_service_business(self, category):
        """Check if business is service-based"""
        return category in ['services', 'beauty_wellness', 'real_estate']
    
    def _ask_yes_no(self, feature_name):
        """Helper para preguntas sí/no"""
        response = input(f"  • {feature_name}? (s/n) [s]: ").strip().lower()
        return response != 'n'
    
    def generate_bot(self, config):
        """Genera nuevo bot con arquitectura Sprint 1"""
        
        bot_name = config['business_name'].lower().replace(' ', '-')
        dest_dir = os.path.join(os.path.dirname(self.project_root), f"{bot_name}-bot")
        
        print(f"\n📂 Creando bot enterprise en: {dest_dir}")
        
        # Check if exists
        if os.path.exists(dest_dir):
            overwrite = input(f"⚠️  El directorio ya existe. ¿Sobrescribir? (s/n): ").strip().lower()
            if overwrite != 's':
                print("❌ Cancelado")
                return None
            shutil.rmtree(dest_dir)
        
        # Clone project
        print("📋 Clonando proyecto enterprise...")
        shutil.copytree(
            self.project_root,
            dest_dir,
            ignore=shutil.ignore_patterns(
                '*.db', 'backups/', '__pycache__/', '*.pyc', '.git/',
                'template-generator/', '.DS_Store', 'fraud_blacklist.json',
                'experiments_config.json', '.venv/', 'archive/', 
                '*.log', 'htmlcov/'
            )
        )
        
        # Generate business config
        print("⚙️  Generando business_config.json v2.0...")
        business_config = self._generate_config_v2(config)
        
        config_path = os.path.join(dest_dir, 'business_config.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(business_config, f, indent=2, ensure_ascii=False)
        
        # Generate sample catalog
        print("📊 Generando catálogo de ejemplo...")
        self._generate_sample_catalog(dest_dir, config)
        
        # Customize policies
        print("📋 Generando policies.md...")
        self._generate_policies(dest_dir, config)
        
        # Update README
        print("📄 Personalizando README...")
        self._customize_readme_v2(dest_dir, config)
        
        # Create .env files
        print("🔐 Creando archivos .env...")
        self._create_env_files(dest_dir, config)
        
        # Generate DEPLOYMENT guide
        print("🚀 Generando DEPLOYMENT.md...")
        self._generate_deployment_guide(dest_dir, config)
        
        print()
        print("=" * 70)
        print("✅  BOT ENTERPRISE CREADO EXITOSAMENTE!")
        print("=" * 70)
        print(f"\n📂 Ubicación: {dest_dir}")
        print("\n📝 Próximos pasos:")
        print("1. cd " + os.path.basename(dest_dir))
        print("2. cp .env.example .env")
        print("3. Editar .env con tus API keys (OPENAI_API_KEY, SENTRY_DSN, etc.)")
        print("4. Personalizar catalog.csv con tus productos")
        print("5. Ajustar business_config.json si es necesario")
        print("6. Ejecutar: docker-compose up --build")
        print("   O local: python whatsapp_server.py")
        print("\n🧪 Testing:")
        print("   pytest tests/ -v --cov=bot_sales")
        print("\n📚 Ver README.md para documentación completa")
        print()
        
        return dest_dir
    
    def _generate_config_v2(self, config):
        """Generate v2.0 config with Sprint 1 features"""
        return {
            "version": "2.0",
            "template_version": self.VERSION,
            "business": {
                "name": config['business_name'],
                "category": config['category'],
                "currency": config['currency'],
                "country": self._guess_country(config['currency']),
                "language": config['language']
            },
            "bot_personality": {
                "tone": config['tone'],
                "use_emojis": config['use_emojis'],
                "region_slang": "argentina" if config['language'] == 'es' else "none"
            },
            "features": config['features'],
            "product_fields": self._get_category_fields(config['category'], config['currency']),
            "security": {
                "jwt_enabled": True,
                "pii_encryption": True,
                "input_sanitization": True,
                "rate_limiting": True,
                "max_requests_per_minute": 60
            },
            "performance": {
                "redis_enabled": config['features'].get('redis_cache', False),
                "database_indices": True,
                "async_operations": True,
                "cache_ttl_seconds": 300
            },
            "monitoring": {
                "sentry_enabled": True,
                "health_checks": True,
                "metrics_enabled": True,
                "log_level": "INFO"
            },
            "testing": {
                "pytest_configured": True,
                "coverage_target": 75,
                "pre_commit_hooks": True
            },
            "deployment": {
                "docker": True,
                "docker_compose": True,
                "ci_cd": "github_actions",
                "environments": ["development", "staging", "production"]
            },
            "created_at": datetime.now().isoformat(),
            "generator_version": self.VERSION
        }
    
    def _guess_country(self, currency):
        """Guess country from currency"""
        country_map = {
            'ARS': 'AR', 'USD': 'US', 'MXN': 'MX',
            'EUR': 'ES', 'BRL': 'BR'
        }
        return country_map.get(currency, 'UN')
    
    def _get_category_fields(self, category, currency):
        """Get product fields for category"""
        price_field = f"price_{currency.lower()}"
        
        base_fields = {
            "id_field": "sku",
            "name_field": "name",
            "price_field": price_field,
            "category_field": "category",
            "stock_field": "stock"
        }
        
        # Category-specific fields
        category_fields = {
            'pharmacy': ["requires_prescription", "active_ingredient", "dosage"],
            'food': ["preparation_time", "calories", "allergens"],
            'beauty_wellness': ["duration", "therapist", "room_type"],
            'pet_shop': ["species", "breed", "age_range"],
            'grocery': ["brand", "expiration_date", "unit"],
            'services': ["duration", "professional", "location"],
            'real_estate': ["rooms", "m2", "location"],
            'automotive': ["year", "km", "fuel_type"],
            'clothing': ["size", "color", "material"]
        }
        
        base_fields['custom_fields'] = category_fields.get(category, [])
        return base_fields
    
    def _generate_sample_catalog(self, dest_dir, config):
        """Generate sample catalog v2"""
        category = config['category']
        currency = config['currency']
        
        catalogs = {
            'electronics': self._get_electronics_catalog,
            'clothing': self._get_clothing_catalog,
            'food': self._get_food_catalog,
            'pharmacy': self._get_pharmacy_catalog,  # NEW
            'automotive': self._get_automotive_catalog,
            'services': self._get_services_catalog,
            'real_estate': self._get_realestate_catalog,
            'beauty_wellness': self._get_beauty_catalog,  # NEW
            'pet_shop': self._get_petshop_catalog,  # NEW
            'grocery': self._get_grocery_catalog,  # NEW
            'other': self._get_generic_catalog
        }
        
        catalog_func = catalogs.get(category, self._get_generic_catalog)
        catalog_content = catalog_func(currency)
        
        catalog_path = os.path.join(dest_dir, 'data/products.csv')
        os.makedirs(os.path.dirname(catalog_path), exist_ok=True)
        with open(catalog_path, 'w', encoding='utf-8') as f:
            f.write(catalog_content)
    
    def _get_pharmacy_catalog(self, currency):
        """NEW: Pharmacy catalog"""
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,requires_prescription,active_ingredient,dosage,brand
MED-001,Ibuprofeno 400mg,Analgésicos,450,100,No,Ibuprofeno,400mg,GenericoPharma
MED-002,Amoxicilina 500mg,Antibióticos,1200,50,Sí,Amoxicilina,500mg,AntibioMax
VIT-001,Vitamina C 1000mg,Vitaminas,800,150,No,Ácido Ascórbico,1000mg,VitaHealth
MED-003,Omeprazol 20mg,Digestivos,650,80,No,Omeprazol,20mg,DigestPro
COSM-001,Protector Solar FPS 50,Cosméticos,1800,60,No,Óxido de Zinc,N/A,SunCare
BABY-001,Pañales Talla M,Bebé,2500,200,No,N/A,N/A,BabyCare
MED-004,Paracetamol 500mg,Analgésicos,300,200,No,Paracetamol,500mg,ParaMed"""
    
    def _get_beauty_catalog(self, currency):
        """NEW: Beauty & Wellness catalog"""
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,duration,therapist,includes
SPA-001,Masaje Relajante,Masajes,1500,999,60 min,Cualquiera,Aceites aromáticos
SPA-002,Facial Hidratante,Faciales,2000,999,45 min,Especialista,Máscara + serum
HAIR-001,Corte + Peinado,Peluquería,800,999,30 min,Estilista,Lavado incluido
HAIR-002,Coloración Completa,Peluquería,3500,999,120 min,Colorista profesional,Tratamiento post-color
NAILS-001,Manicura Clásica,Uñas,600,999,30 min,Cualquiera,Esmaltado tradicional
NAILS-002,Uñas Gel,Uñas,1200,999,60 min,Especialista,Diseño incluido
SPA-003,Depilación Facial,Depilación,400,999,20 min,Cualquiera,Cera caliente"""
    
    def _get_petshop_catalog(self, currency):
        """NEW: Pet Shop catalog"""
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,species,brand,size
FOOD-001,Alimento Premium Perro,Alimentos,3500,50,Perro,DogChow,15kg
FOOD-002,Alimento Premium Gato,Alimentos,2800,40,Gato,CatFood,10kg
TOY-001,Pelota de Goma,Juguetes,450,100,Perro/Gato,PetToy,Mediana
MED-001,Antiparasitario Pipeta,Medicamentos,1200,80,Perro/Gato,VetCare,3 dosis
ACC-001,Collar Anti-Pulgas,Accesorios,800,60,Perro/Gato,FleaStop,Universal
CAGE-001,Jaula Hamster,Jaulas,2500,15,Roedor,CagePro,40x30cm
GROOM-001,Shampoo Antipulgas,Higiene,350,70,Perro/Gato,CleanPet,500ml"""
    
    def _get_grocery_catalog(self, currency):
        """NEW: Grocery catalog"""
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,brand,unit,expiration_days
DAIRY-001,Leche Entera,Lácteos,450,100,La Serenísima,1L,7
DAIRY-002,Yogur Natural,Lácteos,280,80,Danone,kg,14
BREAD-001,Pan Francés,Panadería,350,50,Panadería Artesanal,unidad,1
FRESH-001,Tomates,Verduras,280,120,Sin marca,kg,5
FRESH-002,Lechuga,Verduras,250,80,Sin marca,unidad,3
MEAT-001,Carne Molida,Carnicería,1200,40,Premium,kg,2
SNACK-001,Galletitas Dulces,Snacks,180,200,Oreo,paquete,180"""
    
    def _get_electronics_catalog(self, currency):
        """Existing - electronics"""
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,brand,warranty,specs
IP15-128-BLK,Herramienta 15 128GB Negro,Smartphones,1200000,5,Apple,12 meses,A16 Bionic
IP15-256-BLU,Herramienta 15 256GB Azul,Smartphones,1400000,3,Apple,12 meses,A16 Bionic
MBA-M2-256,Sierra Circular Air M2 256GB,Laptops,1800000,2,Apple,12 meses,M2 chip
AIRP-PRO2,Destornillador a Bateria Bosch,Audio,450000,10,Apple,12 meses,ANC
IPD-11-128,Lijadora 11 128GB,Tablets,950000,4,Apple,12 meses,M2"""
    
    def _get_clothing_catalog(self, currency):
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,size,color,material
SHIRT-001,Camisa Casual,Camisas,4500,20,M,Azul,Algodón
PANTS-001,Jean Slim Fit,Pantalones,8000,15,32,Negro,Denim
DRESS-001,Vestido Verano,Vestidos,12000,10,S,Rojo,Seda
JACKET-001,Campera Cuero,Camperas,25000,5,L,Negro,Cuero
SHOES-001,Zapatillas Running,Calzado,15000,12,42,Blanco,Mesh"""
    
    def _get_food_catalog(self, currency):
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,preparation_time,calories,allergens
BURGER-001,Hamburguesa Clásica,Burgers,1800,999,15 min,650,Gluten
PIZZA-001,Pizza Margherita,Pizzas,2200,999,20 min,800,Gluten/Lácteos
SALAD-001,Ensalada Caesar,Ensaladas,1500,999,10 min,400,None
PASTA-001,Pasta Carbonara,Pastas,2000,999,18 min,750,Gluten/Huevo
DESSERT-001,Brownie Chocolate,Postres,900,999,5 min,450,Gluten/Lácteos"""
    
    def _get_automotive_catalog(self, currency):
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,year,km,fuel_type
CAR-001,Sedan Compacto,Autos,15000000,3,2020,45000,Nafta
CAR-002,SUV 4x4,Autos,28000000,2,2021,30000,Diesel
MOTO-001,Moto Deportiva 250cc,Motos,5000000,5,2022,5000,Nafta"""
    
    def _get_services_catalog(self, currency):
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,duration,professional,includes
SERV-001,Consultoría Marketing,Consultoría,20000,999,1 hora,Senior,Informe detallado
SERV-002,Diseño Logo,Diseño,15000,999,3 días,Designer,3 revisiones
SERV-003,Desarrollo Web,Desarrollo,150000,999,1 mes,Full Stack,Hosting incluido"""
    
    def _get_realestate_catalog(self, currency):
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,rooms,m2,location
PROP-001,Departamento 2 Ambientes,Venta,150000000,1,2,50,CABA
RENT-001,Monoambiente,Alquiler,600000,1,1,30,Palermo"""
    
    def _get_generic_catalog(self, currency):
        pf = f"price_{currency.lower()}"
        return f"""sku,name,category,{pf},stock,description
PROD-001,Producto Ejemplo 1,Categoría A,10000,10,Descripción del producto
PROD-002,Producto Ejemplo 2,Categoría A,15000,5,Otro producto de ejemplo"""
    
    def _generate_policies(self, dest_dir, config):
        """Generate basic policies"""
        category = config['category']
        business = config['business_name']
        
        policies = f"""# Políticas de {business}

## Envíos

- CABA: 24-48hs
- GBA: 2-3 días
- Interior: 3-7 días
- Envío gratis en compras mayores a ${10000 if config['currency'] == 'ARS' else 100}

## Devoluciones

- 30 días para devoluciones
- Producto sin usar y en embalaje original
- Reembolso completo

## Garantía

- 12 meses de garantía oficial
- Cubre defectos de fábrica
- No cubre daños por mal uso

## Formas de Pago

- Efectivo
- Transferencia bancaria
- MercadoPago (tarjeta de crédito/débito)
- Cuotas disponibles

## Horarios de Atención

- Lunes a Viernes: 9:00 - 18:00
- Sábados: 9:00 - 13:00
- Domingos y feriados: Cerrado

## Contacto

- WhatsApp: +54 9 11 XXXX-XXXX
- Email: info@{business.lower().replace(' ', '')}.com
- Dirección: [Tu dirección]
"""
        
        policies_path = os.path.join(dest_dir, 'data/policies.md')
        with open(policies_path, 'w', encoding='utf-8') as f:
            f.write(policies)
    
    def _customize_readme_v2(self, dest_dir, config):
        """Generate customized README v2.0"""
        readme = f"""# {config['business_name']} - Enterprise Sales Bot

Powered by AI Sales Bot Template Generator v{self.VERSION}

## ⚡ Enterprise Features Included

### 🔐 Security
- ✅ JWT Authentication + RBAC
- ✅ PII Encryption (Fernet/AES-256)
- ✅ Input Sanitization (XSS, SQL, Path)
- ✅ Rate Limiting
- ✅ Bcrypt password hashing

### 🚀 Performance
- ✅ Redis Caching ({"enabled" if config['features'].get('redis_cache') else "disabled - enable in business_config.json"})
- ✅ Database 11 Indices
- ✅ Async Operations
- ✅ Background Tasks

###  📊 Monitoring
- ✅ Sentry Error Tracking
- ✅ Health Checks (/health, /health/ready, /metrics)
- ✅ Performance Tracing
- ✅ Structured Logging

### 🧪 Testing
- ✅ 130+ Unit Tests
- ✅ Integration Tests
- ✅ Performance Benchmarks
- ✅ Coverage >75%

### 🐳 DevOps
- ✅ Docker Multi-Stage Build
- ✅ Docker Compose (bot + Redis + dashboard)
- ✅ CI/CD Pipeline (GitHub Actions)
- ✅ Auto-Deployment

## 🎯 Tu Configuración

- **Negocio**: {config['business_name']}
- **Categoría**: {config['category']}
- **Moneda**: {config['currency']}
- **Idioma**: {config['language']}
- **Tono**: {config['tone']}

## 📦 Features Activas

{self._format_features_v2(config['features'])}

## 🚀 Quick Start

### Option A: Docker (Recommended)

```bash
# 1. Configure
cp .env.example .env
nano .env  # Add OPENAI_API_KEY, SENTRY_DSN, etc.

# 2. Start full stack
docker-compose up --build

# 3. Access
# Bot: http://localhost:5000
# Dashboard: http://localhost:5001
# Redis: localhost:6379
```

### Option B: Local Development

```bash
# 1. Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
nano .env

# 3. Run migrations
python3 migrations/001_add_indices_and_constraints.py

# 4. Start bot
python whatsapp_server.py
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=bot_sales --cov-report=html

# Performance benchmarks
pytest tests/test_performance.py --benchmark-only
```

## 📝 Customization

1. **Products**: Edit `data/products.csv`
2. **Policies**: Edit `data/policies.md`
3. **Config**: Adjust `business_config.json`
4. **System Prompt**: Modify `bot_sales/intelligence/system_prompts.py`

## 📊 Health Checks

```bash
curl http://localhost:5000/health
curl http://localhost:5000/health/ready
curl http://localhost:5000/metrics
```

## 📚 Documentation

- `QUICKSTART.md` - 5-minute setup
- `docs/project/PRODUCTION_GUIDE.md` - Production deployment
- `SECURITY_AUDIT.md` - Security checklist
- `CONTRIBUTING.md` - Development guidelines

## 🆘 Support

- **Logs**: `tail -f data/sales_bot.log`
- **Sentry**: Check your Sentry dashboard
- **Tests**: `pytest tests/ -v`

---

Generated with ❤️ by Sales Bot Template Generator v{self.VERSION}
"""
        
        readme_path = os.path.join(dest_dir, 'README.md')
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme)
    
    def _format_features_v2(self, features):
        """Format features list v2"""
        core = []
        optional = []
        
        for k, v in features.items():
            label = k.replace('_', ' ').title()
            marker = "✅" if v else "⚪"
            line = f"- {marker} {label}"
            
            if k in ['authentication', 'encryption', 'sanitization', 'health_checks', 'monitoring']:
                core.append(line)
            else:
                optional.append(line)
        
        result = "### Core (Always Included)\n" + '\n'.join(core)
        result += "\n\n### Optional\n" + '\n'.join(optional)
        return result
    
    def _create_env_files(self, dest_dir, config):
        """Create .env files"""
        env_content = f"""# OpenAI API Key (REQUIRED)
OPENAI_API_KEY=your_openai_api_key_here

# Sentry Monitoring (RECOMMENDED)
SENTRY_DSN=your_sentry_dsn_here
ENVIRONMENT=development
RELEASE_VERSION=1.0.0

# Redis (Optional but recommended)
REDIS_URL=redis://localhost:6379/0

# JWT Authentication
JWT_SECRET=change-me-in-production-use-strong-secret
SESSION_SECRET=another-strong-secret

# PII Encryption
ENCRYPTION_PASSWORD=your-encryption-password-here
ENCRYPTION_SALT=your-salt-here

# Database
DATABASE_PATH=data/ferreteria.db
CATALOG_CSV=data/products.csv
LOG_FILE=data/sales_bot.log

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# Optional Integrations
{"# WhatsApp Business API" if config['features'].get('whatsapp_business') else ""}
{"TWILIO_ACCOUNT_SID=" if config['features'].get('whatsapp_business') else ""}
{"TWILIO_AUTH_TOKEN=" if config['features'].get('whatsapp_business') else ""}

{"# MercadoPago" if config['features'].get('mercadopago') else ""}
{"MP_ACCESS_TOKEN=" if config['features'].get('mercadopago') else ""}

{"# Google Sheets" if config['features'].get('google_sheets') else ""}
{"GOOGLE_SHEETS_CREDENTIALS_JSON=credentials/google-sheets.json" if config['features'].get('google_sheets') else ""}
{"GOOGLE_SHEET_ID=" if config['features'].get('google_sheets') else ""}

{"# Email SMTP" if config['features'].get('email_notifications') else ""}
{"SMTP_SERVER=smtp.gmail.com" if config['features'].get('email_notifications') else ""}
{"SMTP_PORT=587" if config['features'].get('email_notifications') else ""}
{"SMTP_USERNAME=" if config['features'].get('email_notifications') else ""}
{"SMTP_PASSWORD=" if config['features'].get('email_notifications') else ""}

# Admin Dashboard
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me_in_production
"""
        
        env_path = os.path.join(dest_dir, '.env.example')
        with open(env_path, 'w') as f:
            f.write(env_content)
    
    def _generate_deployment_guide(self, dest_dir, config):
        """Generate deployment guide"""
        guide = f"""# Deployment Guide - {config['business_name']}

## Pre-Production Checklist

### 1. Security ✅
- [ ] Change JWT_SECRET in .env
- [ ] Change ENCRYPTION_PASSWORD
- [ ] Change ADMIN_PASSWORD
- [ ] Review SECURITY_AUDIT.md
- [ ] Configure Sentry DSN
- [ ] Set strong passwords

### 2. Configuration ✅
- [ ] Update business_config.json
- [ ] Load real products in data/products.csv
- [ ] Customize data/policies.md
- [ ] Set correct DATABASE_PATH for production
- [ ] Configure integrations (MP, WhatsApp, etc.)

### 3. Testing ✅
- [ ] Run all tests: `pytest tests/ -v`
- [ ] Check coverage: >75%
- [ ] Manual testing in staging
- [ ] Load testing if high traffic expected

### 4. Performance ✅
- [ ] Enable Redis in production
- [ ] Configure Redis URL
- [ ] Run database migration
- [ ] Verify indices created

### 5. Monitoring ✅
- [ ] Sentry configured and tested
- [ ] Health checks responding
- [ ] Metrics endpoint working
- [ ] Log rotation configured

## Deployment Options

### Option 1: Railway

```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize
railway init

# 4. Add services
railway add redis

# 5. Set environment variables
railway variables set OPENAI_API_KEY=xxx
railway variables set SENTRY_DSN=xxx
# ... etc

# 6. Deploy
railway up
```

### Option 2: Render

1. Connect GitHub repo
2. Create Web Service
3. Add Redis instance
4. Set environment variables
5. Deploy

### Option 3: Digital Ocean

1. Create Droplet
2. Install Docker & Docker Compose
3. Clone repo
4. Configure .env
5. Run: `docker-compose up -d`

### Option 4: Heroku

```bash
# Similar to Railway
heroku create {config['business_name'].lower().replace(' ', '-')}
heroku addons:create heroku-redis
heroku config:set OPENAI_API_KEY=xxx
git push heroku main
```

## Post-Deployment

1. **Verify Health**: `curl https://your-domain.com/health/ready`
2. **Check Sentry**: Trigger a test error
3. **Monitor Logs**: Check for issues
4. **Test Bot**: Send test messages
5. **Load Test**: If high traffic expected

## Monitoring

- **Health**: https://your-domain.com/health
- **Metrics**: https://your-domain.com/metrics
- **Sentry**: Check dashboard
- **Logs**: `docker-compose logs -f bot`

---

See PRODUCTION_GUIDE.md for more details.
"""
        
        guide_path = os.path.join(dest_dir, 'DEPLOYMENT.md')
        with open(guide_path, 'w', encoding='utf-8') as f:
            f.write(guide)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Sales Bot Template Generator v2.0')
    parser.add_argument('--business', help='Business name')
    parser.add_argument('--category', help='Business category')
    parser.add_argument('--currency', help='Currency (ARS, USD, etc.)')
    parser.add_argument('--non-interactive', action='store_true', help='Skip interactive wizard')
    
    args = parser.parse_args()
    
    generator = BotTemplateGenerator()
    
    try:
        if args.non_interactive and args.business and args.category:
            # Non-interactive mode
            config = {
                'business_name': args.business,
                'category': args.category,
                'currency': args.currency or 'ARS',
                'language': 'es',
                'tone': 'informal',
                'use_emojis': True,
                'features': {
                    'authentication': True,
                    'encryption': True,
                    'sanitization': True,
                    'health_checks': True,
                    'monitoring': True,
                    'redis_cache': True,
                    'shopping_cart': True,
                    'analytics_dashboard': True,
                    'bundles': True,
                    'recommendations': True,
                    'upselling': True,
                    'email_notifications': True,
                    'mercadopago': False,
                    'whatsapp_business': False,
                    'webchat': False,
                    'google_sheets': False,
                    'appointment_booking': False
                }
            }
        else:
            # Interactive mode
            config = generator.run_interactive_setup()
        
        generator.generate_bot(config)
        
    except KeyboardInterrupt:
        print("\n\n❌ Cancelado por el usuario")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
