#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fake Data Generator
Generate realistic test data using Faker
"""

from faker import Faker
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json

fake = Faker('es_AR')  # Argentina locale


class DataGenerator:
    """Generate realistic fake data for testing"""
    
    def __init__(self, seed: int = 42):
        """
        Initialize generator
        
        Args:
            seed: Random seed for reproducibility
        """
        Faker.seed(seed)
        random.seed(seed)
        self.fake = fake
    
    def generate_customer(self) -> Dict[str, Any]:
        """
        Generate realistic customer data
        
        Returns:
            Customer dictionary
        """
        nombre = self.fake.name()
        
        return {
            'nombre': nombre,
            'email': self.fake.email(),
            'contacto': self.fake.phone_number(),
            'dni': str(random.randint(10000000, 45000000)),
            'direccion': self.fake.address(),
            'ciudad': self.fake.city(),
            'provincia': random.choice(['Buenos Aires', 'CABA', 'Córdoba', 'Santa Fe', 'Mendoza']),
            'codigo_postal': self.fake.postcode(),
            'fecha_registro': self.fake.date_time_between(start_date='-2y', end_date='now').isoformat()
        }
    
    def generate_customers(self, count: int = 50) -> List[Dict[str, Any]]:
        """
        Generate multiple customers
        
        Args:
            count: Number of customers to generate
            
        Returns:
            List of customer dicts
        """
        return [self.generate_customer() for _ in range(count)]
    
    def generate_product(self, category: str = 'electronics') -> Dict[str, Any]:
        """
        Generate product based on category
        
        Args:
            category: Product category
            
        Returns:
            Product dictionary
        """
        categories = {
            'electronics': self._generate_electronics_product,
            'clothing': self._generate_clothing_product,
            'food': self._generate_food_product,
            'pharmacy': self._generate_pharmacy_product,
            'beauty': self._generate_beauty_product
        }
        
        generator = categories.get(category, self._generate_generic_product)
        return generator()
    
    def _generate_electronics_product(self) -> Dict[str, Any]:
        """Generate electronics product"""
        brands = ['Apple', 'Samsung', 'Sony', 'LG', 'Xiaomi', 'Motorola']
        models = ['Phone', 'Tablet', 'Laptop', 'Headphones', 'Watch', 'Speaker']
        
        brand = random.choice(brands)
        model = random.choice(models)
        
        return {
            'sku': f"ELEC-{random.randint(1000, 9999)}",
            'name': f"{brand} {model} {random.choice(['Pro', 'Max', 'Plus', 'Ultra', ''])}".strip(),
            'category': 'Electronics',
            'price_ars': random.randint(50000, 2000000),
            'stock_qty': random.randint(0, 50),
            'brand': brand,
            'warranty': random.choice(['6 meses', '12 meses', '24 meses']),
            'condition': random.choice(['Nuevo', 'Reacondicionado'])
        }
    
    def _generate_clothing_product(self) -> Dict[str, Any]:
        """Generate clothing product"""
        items = ['Remera', 'Pantalón', 'Campera', 'Zapatillas', 'Vestido', 'Camisa']
        colors = ['Negro', 'Blanco', 'Azul', 'Rojo', 'Verde', 'Gris']
        sizes = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
        
        return {
            'sku': f"CLOTH-{random.randint(1000, 9999)}",
            'name': f"{random.choice(items)} {random.choice(['Casual', 'Deportivo', 'Formal', ''])}".strip(),
            'category': 'Clothing',
            'price_ars': random.randint(5000, 50000),
            'stock_qty': random.randint(0, 100),
            'size': random.choice(sizes),
            'color': random.choice(colors),
            'material': random.choice(['Algodón', 'Poliéster', 'Lana', 'Seda', 'Denim'])
        }
    
    def _generate_food_product(self) -> Dict[str, Any]:
        """Generate food product"""
        foods = ['Pizza', 'Hamburguesa', 'Ensalada', 'Pasta', 'Sushi', 'Taco']
        
        return {
            'sku': f"FOOD-{random.randint(1000, 9999)}",
            'name': f"{random.choice(foods)} {random.choice(['Especial', 'Clásica', 'Premium', ''])}".strip(),
            'category': 'Food',
            'price_ars': random.randint(1000, 5000),
            'stock_qty': 999,  # Always available
            'preparation_time': f"{random.randint(10, 45)} min",
            'calories': random.randint(300, 1200),
            'allergens': random.choice(['None', 'Gluten', 'Lácteos', 'Nueces', 'Gluten/Lácteos'])
        }
    
    def _generate_pharmacy_product(self) -> Dict[str, Any]:
        """Generate pharmacy product"""
        meds = ['Ibuprofeno', 'Paracetamol', 'Vitamina C', 'Omeprazol', 'Amoxicilina']
        
        name = random.choice(meds)
        dosage = random.choice(['400mg', '500mg', '1000mg', '20mg'])
        
        return {
            'sku': f"MED-{random.randint(1000, 9999)}",
            'name': f"{name} {dosage}",
            'category': 'Pharmacy',
            'price_ars': random.randint(300, 2000),
            'stock_qty': random.randint(20, 200),
            'requires_prescription': random.choice([True, False]),
            'active_ingredient': name,
            'dosage': dosage,
            'brand': random.choice(['GenericoPharma', 'MedPlus', 'HealthCare'])
        }
    
    def _generate_beauty_product(self) -> Dict[str, Any]:
        """Generate beauty/wellness product"""
        services = ['Masaje', 'Facial', 'Manicura', 'Pedicura', 'Depilación', 'Corte de pelo']
        
        return {
            'sku': f"BEAUTY-{random.randint(1000, 9999)}",
            'name': f"{random.choice(services)} {random.choice(['Clásico', 'Premium', 'Express', ''])}".strip(),
            'category': 'Beauty',
            'price_ars': random.randint(1500, 8000),
            'stock_qty': 999,
            'duration': f"{random.choice([30, 45, 60, 90, 120])} min",
            'therapist': random.choice(['Cualquiera', 'Especialista', 'Senior'])
        }
    
    def _generate_generic_product(self) -> Dict[str, Any]:
        """Generate generic product"""
        return {
            'sku': f"PROD-{random.randint(1000, 9999)}",
            'name': self.fake.catch_phrase(),
            'category': random.choice(['General', 'Varios', 'Otros']),
            'price_ars': random.randint(1000, 100000),
            'stock_qty': random.randint(0, 100),
            'description': self.fake.text(max_nb_chars=100)
        }
    
    def generate_products(self, count: int = 100, mix_categories: bool = True) -> List[Dict[str, Any]]:
        """
        Generate multiple products
        
        Args:
            count: Number of products
            mix_categories: Mix different categories
            
        Returns:
            List of products
        """
        if mix_categories:
            categories = ['electronics', 'clothing', 'food', 'pharmacy', 'beauty']
            return [self.generate_product(random.choice(categories)) for _ in range(count)]
        else:
            return [self.generate_product() for _ in range(count)]
    
    def generate_sale(self, product_sku: str, customer_name: str) -> Dict[str, Any]:
        """
        Generate sale record
        
        Args:
            product_sku: Product SKU
            customer_name: Customer name
            
        Returns:
            Sale dictionary
        """
        sale_date = self.fake.date_time_between(start_date='-30d', end_date='now')
        
        return {
            'sale_id': f"SALE-{random.randint(10000, 99999)}",
            'sku': product_sku,
            'name': customer_name,
            'contact': self.fake.phone_number(),
            'zone': random.choice(['CABA', 'GBA Norte', 'GBA Sur', 'Interior']),
            'payment_method': random.choice(['Efectivo', 'Transferencia', 'MercadoPago', 'Tarjeta']),
            'confirmed_at': sale_date.timestamp(),
            'status': random.choice(['confirmed', 'shipped', 'delivered']),
            'total': random.randint(10000, 500000)
        }
    
    def generate_sales(
        self,
        count: int = 200,
        customers: List[Dict] = None,
        products: List[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate sales records
        
        Args:
            count: Number of sales
            customers: List of customers (optional)
            products: List of products (optional)
            
        Returns:
            List of sales
        """
        if not customers:
            customers = self.generate_customers(50)
        if not products:
            products = self.generate_products(100)
        
        sales = []
        for _ in range(count):
            customer = random.choice(customers)
            product = random.choice(products)
            
            sale = self.generate_sale(product['sku'], customer['nombre'])
            sales.append(sale)
        
        return sales
    
    def generate_conversation(self) -> Dict[str, Any]:
        """Generate conversation history"""
        messages = []
        num_messages = random.randint(3, 15)
        
        for i in range(num_messages):
            role = 'user' if i % 2 == 0 else 'assistant'
            
            if role == 'user':
                content = random.choice([
                    "Hola, quiero comprar un Herramienta",
                    "Cuánto cuesta?",
                    "Tienen stock?",
                    "Lo quiero en negro",
                    "Sí, lo confirmo",
                    "Cuándo llega?"
                ])
            else:
                content = random.choice([
                    "Hola! Cómo estás? Te puedo ayudar con algo?",
                    "Tenemos varios modelos disponibles",
                    "El precio es $1.200.000",
                    "Sí, tenemos 5 unidades",
                    "Perfecto! Te lo reservo",
                    "Llega en 24-48hs"
                ])
            
            messages.append({
                'role': role,
                'content': content,
                'timestamp': datetime.now().isoformat()
            })
        
        return {
            'conversation_id': f"CONV-{random.randint(10000, 99999)}",
            'user_id': f"user-{random.randint(100, 999)}",
            'messages': messages,
            'status': random.choice(['active', 'completed', 'abandoned']),
            'created_at': self.fake.date_time_between(start_date='-7d').isoformat()
        }
    
    def save_to_json(self, data: Any, filename: str) -> None:
        """
        Save data to JSON file
        
        Args:
            data: Data to save
            filename: Output filename
        """
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def save_to_csv(self, data: List[Dict], filename: str) -> None:
        """
        Save data to CSV file
        
        Args:
            data: List of dictionaries
            filename: Output filename
        """
        import csv
        
        if not data:
            return
        
        keys = data[0].keys()
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)


def main():
    """Demo data generation"""
    generator = DataGenerator()
    
    print("Generando datos de prueba...")
    
    # Generate customers
    customers = generator.generate_customers(50)
    generator.save_to_json(customers, 'fake_customers.json')
    print(f"✅ {len(customers)} clientes generados")
    
    # Generate products
    products = generator.generate_products(100, mix_categories=True)
    generator.save_to_csv(products, 'fake_products.csv')
    print(f"✅ {len(products)} productos generados")
    
    # Generate sales
    sales = generator.generate_sales(200, customers, products)
    generator.save_to_json(sales, 'fake_sales.json')
    print(f"✅ {len(sales)} ventas generadas")
    
    # Generate conversations
    conversations = [generator.generate_conversation() for _ in range(30)]
    generator.save_to_json(conversations, 'fake_conversations.json')
    print(f"✅ {len(conversations)} conversaciones generadas")
    
    print("\n🎉 Datos generados exitosamente!")


if __name__ == "__main__":
    main()
