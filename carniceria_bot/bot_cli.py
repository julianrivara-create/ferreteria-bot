#!/usr/bin/env python3
"""
Sales Bot CLI - Improved Version
CLI profesional con Rich library para terminal
"""
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track
from rich import print as rprint
from rich.prompt import Prompt, Confirm
import sys
import os

# Agregar al path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot_sales.bot import SalesBot
from bot_sales.core.database import Database
from bot_sales.core.cache import get_cache
from bot_sales.core.logger import setup_logging

console = Console()

@click.group()
def cli():
    """🤖 Sales Bot - CLI de Gestión"""
    pass

# ========== CHAT ==========

@cli.command()
@click.option('--session', '-s', default=None, help='Session ID específico')
def chat(session):
    """💬 Chatear con el bot en terminal"""
    setup_logging(level='WARNING')  # Menos verbose en CLI
    
    console.print(Panel.fit(
        "[bold cyan]Sales Bot - Chat Interactivo[/bold cyan]\n"
        "Escribí [bold]'exit'[/bold] para salir",
        border_style="cyan"
    ))
    
    bot = SalesBot()
    session_id = session or f"cli_{os.getpid()}"
    
    while True:
        try:
            # Input del usuario
            user_input = Prompt.ask("\n[bold green]Vos[/bold green]")
            
            if user_input.lower() in ['exit', 'quit', 'salir']:
                console.print("[yellow]👋 Chau![/yellow]")
                break
            
            # Procesar con bot
            with console.status("[cyan]Pensando...[/cyan]"):
                response = bot.process_message(session_id, user_input)
            
            # Mostrar respuesta del bot
            console.print(f"\n[bold magenta]Bot[/bold magenta]: {response}")
        
        except KeyboardInterrupt:
            console.print("\n[yellow]👋 Chau![/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

# ========== DASHBOARD ==========

@cli.command()
def dashboard():
    """📊 Ver dashboard de métricas"""
    db = Database()
    
    # Stats
    stats = _get_stats(db)
    
    # Panel principal
    console.print("\n")
    console.print(Panel.fit(
        f"[bold cyan]📊 Sales Bot Dashboard[/bold cyan]\n\n"
        f"Ventas Totales: [bold green]{stats['total_sales']}[/bold green]\n"
        f"Ventas Hoy: [bold yellow]{stats['sales_today']}[/bold yellow]\n"
        f"Revenue Total: [bold magenta]${stats['total_revenue']:,}[/bold magenta]\n"
        f"Conversión: [bold blue]{stats['conversion_rate']:.1f}%[/bold blue]",
        border_style="cyan"
    ))
    
    # Tabla de últimas ventas
    table = Table(title="\n💰 Últimas 10 Ventas")
    table.add_column("ID", style="cyan")
    table.add_column("Producto", style="magenta")
    table.add_column("Total", style="green")
    table.add_column("Fecha", style="yellow")
    
    recent = _get_recent_sales(db, limit=10)
    for sale in recent:
        table.add_row(
            f"#{sale['id']}",
            sale['product_sku'],
            f"${sale['total_ars']:,}",
            sale['timestamp'][:10]
        )
    
    console.print(table)

def _get_stats(db):
    """Helper para obtener stats"""
    from datetime import datetime
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Total sales
    cursor.execute("SELECT COUNT(*) as count FROM sales")
    total_sales = cursor.fetchone()['count']
    
    # Sales today
    today = datetime.now().date()
    cursor.execute("SELECT COUNT(*) as count FROM sales WHERE DATE(timestamp) = ?", (today,))
    sales_today = cursor.fetchone()['count']
    
    # Revenue
    cursor.execute("SELECT SUM(total_ars) as revenue FROM sales")
    total_revenue = cursor.fetchone()['revenue'] or 0
    
    # Conversion
    cursor.execute("SELECT COUNT(DISTINCT session_id) as sessions FROM conversation_history")
    sessions = cursor.fetchone()['sessions'] or 1
    conversion_rate = (total_sales / sessions * 100) if sessions > 0 else 0
    
    conn.close()
    
    return {
        'total_sales': total_sales,
        'sales_today': sales_today,
        'total_revenue': total_revenue,
        'conversion_rate': conversion_rate
    }

def _get_recent_sales(db, limit=10):
    """Helper para últimas ventas"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM sales ORDER BY timestamp DESC LIMIT ?", (limit,))
    sales = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return sales

# ========== PRODUCTS ==========

@cli.group()
def products():
    """📦 Gestionar productos"""
    pass

@products.command('list')
@click.option('--search', '-s', default=None, help='Buscar por nombre/SKU')
def list_products(search):
    """Lista productos del catálogo"""
    import csv
    
    table = Table(title="📦 Catálogo de Productos")
    table.add_column("SKU", style="cyan")
    table.add_column("Nombre", style="magenta")
    table.add_column("Precio", style="green")
    table.add_column("Stock", style="yellow")
    
    with open('catalog_extended.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filtrar si hay búsqueda
            if search and search.lower() not in (row.get('sku', '') + row.get('name', '') + row.get('model', '')).lower():
                continue
            
            stock = int(row.get('stock', 0))
            stock_str = f"[green]{stock}[/green]" if stock > 10 else f"[yellow]{stock}[/yellow]" if stock > 0 else "[red]0[/red]"
            
            table.add_row(
                row['sku'],
                row.get('name') or row.get('model', 'N/A'),
                f"${int(row.get('price_ars', 0)):,}",
                stock_str
            )
    
    console.print(table)

@products.command('update-stock')
@click.argument('sku')
@click.argument('stock', type=int)
def update_stock(sku, stock):
    """Actualiza stock de un producto"""
    import csv
    
    # Leer CSV
    rows = []
    found = False
    
    with open('catalog_extended.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row['sku'] == sku:
                row['stock'] = str(stock)
                found = True
                console.print(f"[green]✓[/green] Stock actualizado: {sku} → {stock}")
            rows.append(row)
    
    if not found:
        console.print(f"[red]✗[/red] Producto no encontrado: {sku}")
        return
    
    # Escribir CSV
    with open('catalog_extended.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

# ========== SALES ==========

@cli.command()
@click.option('--limit', '-l', default=20, help='Cantidad de ventas a mostrar')
def sales(limit):
    """💰 Ver ventas recientes"""
    db = Database()
    
    sales_list = _get_recent_sales(db, limit)
    
    table = Table(title=f"💰 Últimas {limit} Ventas")
    table.add_column("ID", style="cyan")
    table.add_column("Producto", style="magenta")
    table.add_column("Cliente", style="blue")
    table.add_column("Total", style="green")
    table.add_column("Método", style="yellow")
    table.add_column("Fecha", style="white")
    
    for sale in sales_list:
        table.add_row(
            f"#{sale['id']}",
            sale['product_sku'],
            sale.get('customer_name', 'N/A')[:20],
            f"${sale['total_ars']:,}",
            sale.get('metodo_pago', 'N/A')[:15],
            sale['timestamp'][:10]
        )
    
    console.print(table)

# ========== CACHE ==========

@cli.group()
def cache():
    """🗄️ Gestionar caché"""
    pass

@cache.command('stats')
def cache_stats():
    """Ver estadísticas del caché"""
    cache_obj = get_cache()
    stats = cache_obj.get_stats()
    
    console.print(Panel.fit(
        f"[bold cyan]🗄️ Cache Stats[/bold cyan]\n\n"
        f"Entradas: [bold green]{stats['total_entries']}[/bold green]\n"
        f"Hits Totales: [bold yellow]{stats['total_hits']}[/bold yellow]\n"
        f"Promedio Hits/Entrada: [bold magenta]{stats['avg_hits_per_entry']:.1f}[/bold magenta]",
        border_style="cyan"
    ))
    
    # Top hits
    if stats['top_hits']:
        table = Table(title="\n🔥 Top 10 Entries")
        table.add_column("Key", style="cyan")
        table.add_column("Hits", style="green")
        table.add_column("Category", style="yellow")
        
        for entry in stats['top_hits']:
            table.add_row(
                entry['key'][:16] + "...",
                str(entry['hit_count']),
                entry['category'] or 'N/A'
            )
        
        console.print(table)

@cache.command('clear')
@click.argument('category', required=False)
def cache_clear(category):
    """Limpiar caché (opcional: por categoría)"""
    if category:
        if Confirm.ask(f"¿Seguro que querés borrar la categoría '{category}'?"):
            cache_obj = get_cache()
            cache_obj.invalidate(category=category)
            console.print(f"[green]✓[/green] Categoría '{category}' borrada")
    else:
        if Confirm.ask("¿Seguro que querés borrar TODO el caché?"):
            cache_obj = get_cache()
            cache_obj.invalidate()
            console.print("[green]✓[/green] Caché completo borrado")

@cache.command('cleanup')
def cache_cleanup():
    """Limpiar entries expirados"""
    cache_obj = get_cache()
    deleted = cache_obj.cleanup_expired()
    console.print(f"[green]✓[/green] {deleted} entries expirados eliminados")

# ========== EXPORT ==========

@cli.command()
@click.option('--format', '-f', type=click.Choice(['csv', 'json']), default='csv')
@click.option('--output', '-o', default='export.csv', help='Archivo de salida')
def export(format, output):
    """📁 Exportar datos"""
    db = Database()
    
    if format == 'csv':
        _export_csv(db, output)
    else:
        _export_json(db, output)
    
    console.print(f"[green]✓[/green] Datos exportados a: {output}")

def _export_csv(db, filename):
    """Export a CSV"""
    import csv
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sales ORDER BY timestamp DESC")
    
    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ID', 'Product', 'Customer', 'Total', 'Method', 'Zone', 'Timestamp'])
        
        for row in cursor.fetchall():
            writer.writerow([
                row['id'],
                row['product_sku'],
                row.get('customer_name', ''),
                row['total_ars'],
                row.get('metodo_pago', ''),
                row.get('zona', ''),
                row['timestamp']
            ])
    
    conn.close()

def _export_json(db, filename):
    """Export a JSON"""
    import json
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sales ORDER BY timestamp DESC")
    
    sales = [dict(row) for row in cursor.fetchall()]
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(sales, f, indent=2, ensure_ascii=False)
    
    conn.close()

# ========== CONFIG ==========

@cli.command()
def config():
    """⚙️ Ver configuración"""
    from bot_sales.config import config as cfg
    
    cfg.print_config()

if __name__ == '__main__':
    cli()
