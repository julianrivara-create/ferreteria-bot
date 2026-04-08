#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pretty CLI with Rich Library
Beautiful command-line interface with colors, tables, and progress bars
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.tree import Tree
from rich import box
from typing import List, Dict, Any, Optional
import time

console = Console()


def print_header(title: str, subtitle: str = "") -> None:
    """
    Print a beautiful header
    
    Args:
        title: Main title
        subtitle: Optional subtitle
    """
    panel_content = f"[bold cyan]{title}[/bold cyan]"
    if subtitle:
        panel_content += f"\n[dim]{subtitle}[/dim]"
    
    console.print(Panel(panel_content, box=box.DOUBLE, style="bold green"))


def print_success(message: str) -> None:
    """Print success message"""
    console.print(f"[bold green]✅ {message}[/bold green]")


def print_error(message: str) -> None:
    """Print error message"""
    console.print(f"[bold red]❌ {message}[/bold red]")


def print_warning(message: str) -> None:
    """Print warning message"""
    console.print(f"[bold yellow]⚠️  {message}[/bold yellow]")


def print_info(message: str) -> None:
    """Print info message"""
    console.print(f"[bold blue]ℹ️  {message}[/bold blue]")


def create_table(
    title: str,
    columns: List[str],
    rows: List[List[Any]],
    show_header: bool = True,
    show_lines: bool = False
) -> Table:
    """
    Create a beautiful table
    
    Args:
        title: Table title
        columns: Column names
        rows: List of row data
        show_header: Show header row
        show_lines: Show row lines
        
    Returns:
        Rich Table object
    """
    table = Table(
        title=title,
        show_header=show_header,
        header_style="bold magenta",
        show_lines=show_lines,
        box=box.ROUNDED
    )
    
    # Add columns
    for col in columns:
        table.add_column(col, style="cyan", no_wrap=False)
    
    # Add rows
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    
    return table


def print_products_table(products: List[Dict[str, Any]]) -> None:
    """
    Print products in a beautiful table
    
    Args:
        products: List of product dicts
    """
    if not products:
        print_warning("No hay productos para mostrar")
        return
    
    table = Table(
        title="📦 Productos Disponibles",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
        box=box.ROUNDED
    )
    
    table.add_column("SKU", style="cyan", width=15)
    table.add_column("Producto", style="green", width=30)
    table.add_column("Precio", style="yellow", justify="right")
    table.add_column("Stock", style="blue", justify="center")
    table.add_column("Categoría", style="magenta")
    
    for product in products[:10]:  # Limit to 10 for display
        sku = product.get('sku', 'N/A')
        name = product.get('model', product.get('name', 'N/A'))
        price = f"${product.get('price_ars', product.get('price', 0)):,}"
        stock = str(product.get('stock_qty', product.get('stock', 0)))
        category = product.get('category', 'N/A')
        
        # Color stock based on quantity
        if int(stock) == 0:
            stock = f"[red]{stock}[/red]"
        elif int(stock) < 5:
            stock = f"[yellow]{stock}[/yellow]"
        else:
            stock = f"[green]{stock}[/green]"
        
        table.add_row(sku, name, price, stock, category)
    
    console.print(table)
    
    if len(products) > 10:
        print_info(f"Mostrando 10 de {len(products)} productos")


def print_sales_table(sales: List[Dict[str, Any]]) -> None:
    """Print sales in a beautiful table"""
    if not sales:
        print_warning("No hay ventas para mostrar")
        return
    
    table = Table(
        title="💰 Ventas Recientes",
        show_header=True,
        header_style="bold green",
        box=box.ROUNDED
    )
    
    table.add_column("ID", style="cyan")
    table.add_column("Cliente", style="green")
    table.add_column("Producto", style="yellow")
    table.add_column("Total", style="magenta", justify="right")
    table.add_column("Fecha", style="blue")
    
    for sale in sales[:10]:
        table.add_row(
            sale.get('sale_id', 'N/A'),
            sale.get('name', 'N/A'),
            sale.get('sku', 'N/A'),
            f"${sale.get('total', 0):,}",
            sale.get('date', 'N/A')
        )
    
    console.print(table)


def show_progress_bar(items: List[Any], description: str = "Procesando...") -> List:
    """
    Show progress bar while processing items
    
    Args:
        items: List of items to process
        description: Progress description
        
    Returns:
        Processed items
    """
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        
        task = progress.add_task(description, total=len(items))
        
        for item in items:
            # Simulate processing
            time.sleep(0.05)  # Remove in production
            results.append(item)
            progress.update(task, advance=1)
    
    return results


def print_menu(options: List[str], title: str = "Menú") -> int:
    """
    Print interactive menu and get selection
    
    Args:
        options: List of menu options
        title: Menu title
        
    Returns:
        Selected option index (0-based)
    """
    console.print(f"\n[bold cyan]{title}[/bold cyan]\n")
    
    for i, option in enumerate(options, 1):
        console.print(f"  [yellow]{i}.[/yellow] {option}")
    
    console.print()
    
    choice = Prompt.ask(
        "Elegí una opción",
        choices=[str(i) for i in range(1, len(options) + 1)],
        default="1"
    )
    
    return int(choice) - 1


def confirm_action(message: str, default: bool = False) -> bool:
    """
    Ask for confirmation
    
    Args:
        message: Confirmation message
        default: Default answer
        
    Returns:
        User's confirmation
    """
    return Confirm.ask(f"[yellow]{message}[/yellow]", default=default)


def print_code(code: str, language: str = "python") -> None:
    """
    Print syntax-highlighted code
    
    Args:
        code: Code to print
        language: Programming language
    """
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def print_tree_structure(data: Dict, title: str = "Estructura") -> None:
    """
    Print tree structure
    
    Args:
        data: Nested dictionary
        title: Tree title
    """
    tree = Tree(f"[bold cyan]{title}[/bold cyan]")
    
    def add_branches(parent, data_dict):
        for key, value in data_dict.items():
            if isinstance(value, dict):
                branch = parent.add(f"[yellow]{key}[/yellow]")
                add_branches(branch, value)
            elif isinstance(value, list):
                branch = parent.add(f"[yellow]{key}[/yellow] ({len(value)} items)")
            else:
                parent.add(f"[green]{key}:[/green] {value}")
    
    add_branches(tree, data)
    console.print(tree)


def print_stats_panel(stats: Dict[str, Any]) -> None:
    """
    Print statistics in a panel
    
    Args:
        stats: Statistics dictionary
    """
    content = ""
    for key, value in stats.items():
        label = key.replace('_', ' ').title()
        content += f"[cyan]{label}:[/cyan] [bold yellow]{value}[/bold yellow]\n"
    
    console.print(Panel(content, title="📊 Estadísticas", border_style="green"))


# Example usage functions
def demo_pretty_cli():
    """Demo of all pretty CLI features"""
    print_header("Bot Sales - Demo CLI", "Beautiful command-line interface")
    
    print_success("Conexión exitosa a la base de datos")
    print_info("Cargando productos...")
    print_warning("Algunos productos tienen stock bajo")
    print_error("No se pudo conectar a la API externa")
    
    # Demo table
    products = [
        {'sku': 'IP15-128-BLK', 'model': 'iPhone 15 128GB', 'price_ars': 1200000, 'stock_qty': 5, 'category': 'Smartphones'},
        {'sku': 'IP15-256-BLU', 'model': 'iPhone 15 256GB', 'price_ars': 1400000, 'stock_qty': 2, 'category': 'Smartphones'},
        {'sku': 'MBA-M2-256', 'model': 'MacBook Air M2', 'price_ars': 1800000, 'stock_qty': 0, 'category': 'Laptops'},
    ]
    
    console.print()
    print_products_table(products)
    
    # Demo progress
    console.print()
    items = list(range(20))
    show_progress_bar(items, "Sincronizando inventario...")
    
    # Demo stats
    console.print()
    stats = {
        'total_productos': 62,
        'ventas_hoy': 15,
        'revenue_hoy': '$3,450,000',
        'usuarios_activos': 23
    }
    print_stats_panel(stats)
    
    print_success("Demo completado!")


if __name__ == "__main__":
    demo_pretty_cli()
