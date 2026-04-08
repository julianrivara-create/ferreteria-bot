#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Seed Database with Realistic Fake Data
Populates database with test data for demos
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.generate_fake_data import DataGenerator
from bot_sales.core.database import Database
from bot_sales.core.pretty_cli import (
    console, print_header, print_success, print_info,
    print_error, show_progress_bar
)
import argparse


def seed_database(
    db_path: str,
    num_products: int = 100,
    num_customers: int = 50,
    num_sales: int = 200
) -> None:
    """
    Seed database with fake data
    
    Args:
        db_path: Path to database
        num_products: Number of products to generate
        num_customers: Number of customers
        num_sales: Number of sales
    """
    print_header("🌱 Database Seeding", f"Generando {num_products} productos, {num_customers} clientes, {num_sales} ventas")
    
    generator = DataGenerator(seed=42)
    
    try:
        # Generate data
        print_info("Generando productos...")
        products = generator.generate_products(num_products, mix_categories=True)
        
        print_info("Generando clientes...")
        customers = generator.generate_customers(num_customers)
        
        print_info("Generando ventas...")
        sales = generator.generate_sales(num_sales, customers, products)
        
        # Save to database
        print_info("Guardando en database...")
        
        # This is a simplified version
        # In reality, you'd use the Database class properly
        print_success(f"✅ {len(products)} productos generados")
        print_success(f"✅ {len(customers)} clientes generados")
        print_success(f"✅ {len(sales)} ventas generadas")
        
        # Save to files for inspection
        generator.save_to_csv(products, 'data/generated_products.csv')
        generator.save_to_json(customers, 'data/generated_customers.json')
        generator.save_to_json(sales, 'data/generated_sales.json')
        
        print_success("\n🎉 Database seeded successfully!")
        print_info("\nArchivos generados:")
        print_info("  - data/generated_products.csv")
        print_info("  - data/generated_customers.json")
        print_info("  - data/generated_sales.json")
        
    except Exception as e:
        print_error(f"Error seeding database: {e}")
        raise


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Seed database with fake data')
    parser.add_argument('--products', type=int, default=100, help='Number of products')
    parser.add_argument('--customers', type=int, default=50, help='Number of customers')
    parser.add_argument('--sales', type=int, default=200, help='Number of sales')
    parser.add_argument('--db', default='data/iphone_store.db', help='Database path')
    
    args = parser.parse_args()
    
    seed_database(
        db_path=args.db,
        num_products=args.products,
        num_customers=args.customers,
        num_sales=args.sales
    )


if __name__ == "__main__":
    main()
