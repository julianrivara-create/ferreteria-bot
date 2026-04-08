#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ollama Demo - Demostración interactiva
Muestra cómo funciona el bot con Ollama (GLM-4, Llama, etc.)
"""

import sys
import os
import time

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from bot_sales.core.pretty_cli import (
        console, print_header, print_success, print_error,
        print_info, print_warning, create_table
    )
    PRETTY = True
except ImportError:
    PRETTY = False
    def print_header(msg, sub=""): print(f"\n{'='*60}\n{msg}\n{sub}\n{'='*60}")
    def print_success(msg): print(f"✅ {msg}")
    def print_error(msg): print(f"❌ {msg}")
    def print_info(msg): print(f"ℹ️  {msg}")
    def print_warning(msg): print(f"⚠️  {msg}")


def check_ollama_installed():
    """Verificar si Ollama está instalado"""
    import shutil
    return shutil.which('ollama') is not None


def check_ollama_running():
    """Verificar si Ollama está corriendo"""
    import requests
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        return response.status_code == 200
    except:
        return False


def list_ollama_models():
    """Listar modelos instalados en Ollama"""
    import requests
    try:
        response = requests.get('http://localhost:11434/api/tags')
        if response.status_code == 200:
            models = response.json().get('models', [])
            return [m['name'] for m in models]
    except:
        pass
    return []


def demo_conversation():
    """Demo de conversación con Ollama"""
    print_header("🤖 DEMO: Conversación con Ollama", "Simulando chat de ventas con GLM-4")
    
    # Check prerequisites
    print_info("Verificando requisitos...")
    
    if not check_ollama_installed():
        print_error("Ollama no está instalado")
        print_info("\n📥 Instalación rápida:")
        print_info("  curl -fsSL https://ollama.com/install.sh | sh")
        return False
    
    print_success("Ollama instalado ✓")
    
    if not check_ollama_running():
        print_error("Ollama no está corriendo")
        print_info("\n🚀 Iniciar servidor:")
        print_info("  En otra terminal: ollama serve")
        return False
    
    print_success("Ollama corriendo ✓")
    
    models = list_ollama_models()
    if not models:
        print_warning("No hay modelos instalados")
        print_info("\n📥 Descargar modelo:")
        print_info("  ollama pull glm4:9b")
        return False
    
    print_success(f"Modelos disponibles: {', '.join(models)}")
    
    # Create client
    print_info("\n🔧 Creando cliente LLM...")
    
    try:
        from bot_sales.core.universal_llm import UniversalLLMClient
        
        client = UniversalLLMClient(
            backend='ollama',
            model=models[0],  # Use first available model
            temperature=0.7
        )
        
        print_success(f"Cliente creado con modelo: {models[0]}")
        
    except Exception as e:
        print_error(f"Error creando cliente: {e}")
        return False
    
    # Demo conversation
    print("\n")
    print_header("💬 Simulación de Conversación")
    
    conversations = [
        "Hola, buenos días",
        "Estoy buscando un Herramienta 15",
        "Cuánto cuesta el Herramienta 15 de 128GB?",
        "Lo quiero en color negro",
        "Sí, lo confirmo",
    ]
    
    # IMPORTANTE: Agregar system prompt para que sepa su rol
    messages = [
        {
            "role": "system",
            "content": """Eres un asistente de ventas de Herramientas en Argentina.
Tu trabajo es ayudar a los clientes a encontrar y comprar Herramientas.

IMPORTANTE:
- SIEMPRE responde en ESPAÑOL
- Eres amigable y profesional
- Tienes disponibles Herramienta 15 (128GB, 256GB, 512GB)
- Precios: 128GB=$1.200.000, 256GB=$1.400.000, 512GB=$1.600.000
- Colores: Negro, Azul, Rosa, Blanco
- Todos los modelos están en stock

Responde de forma breve y clara."""
        }
    ]
    
    for i, user_msg in enumerate(conversations, 1):
        print(f"\n[bold cyan]Usuario:[/bold cyan] {user_msg}" if PRETTY else f"\nUsuario: {user_msg}")
        
        # Add to conversation
        messages.append({
            "role": "user",
            "content": user_msg
        })
        
        # Show typing indicator
        if PRETTY:
            from rich.progress import Progress, SpinnerColumn, TextColumn
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Bot pensando...", total=None)
                
                # Send to LLM
                start = time.time()
                try:
                    response = client.send_message(messages)
                    elapsed = time.time() - start
                except Exception as e:
                    print_error(f"Error: {e}")
                    continue
        else:
            print("⏳ Bot pensando...")
            start = time.time()
            try:
                response = client.send_message(messages)
                elapsed = time.time() - start
            except Exception as e:
                print_error(f"Error: {e}")
                continue
        
        # Show response
        bot_msg = response.get('content', '')
        messages.append({
            "role": "assistant",
            "content": bot_msg
        })
        
        if PRETTY:
            console.print(f"[bold green]Bot:[/bold green] {bot_msg}")
            console.print(f"[dim]⚡ Respondió en {elapsed:.2f}s[/dim]")
        else:
            print(f"\nBot: {bot_msg}")
            print(f"⚡ Respondió en {elapsed:.2f}s")
        
        # Small delay for realism
        time.sleep(0.5)
    
    print("\n")
    print_success("✅ Demo completado!")
    
    # Show stats
    if PRETTY:
        console.print("\n[bold]📊 Estadísticas:[/bold]")
        console.print(f"  • Mensajes: {len(conversations)}")
        console.print(f"  • Modelo: {models[0]}")
        console.print(f"  • Backend: Ollama (local, gratis)")
        console.print(f"  • Costo: $0 💸")
    
    return True


def demo_backend_comparison():
    """Demo comparando backends disponibles"""
    print_header("🔍 Demo: Backends Disponibles")
    
    from bot_sales.core.llm_backend import LLMFactory
    
    backends = LLMFactory.list_available_backends()
    
    if PRETTY:
        table = create_table(
            "LLM Backends",
            ["Backend", "Estado", "Notas"],
            []
        )
        
        for name, available in backends:
            status = "✅ Disponible" if available else "❌ No disponible"
            
            if name == 'openai':
                notes = "Requiere API key" if not available else "GPT-4"
            elif name == 'ollama':
                notes = "Gratis, local" if available else "Run: ollama serve"
            else:
                notes = "LM Studio app"
            
            table.add_row(name.upper(), status, notes)
        
        console.print(table)
    else:
        print("\nBackends Disponibles:")
        for name, available in backends:
            status = "✅" if available else "❌"
            print(f"  {status} {name.upper()}")
    
    # Recommend
    available_backends = [name for name, avail in backends if avail]
    if available_backends:
        print_success(f"\n✨ Puedes usar: {', '.join(available_backends)}")
    else:
        print_warning("\n⚠️  No hay backends disponibles")
        print_info("Instalar Ollama: curl -fsSL https://ollama.com/install.sh | sh")


def demo_model_info():
    """Mostrar info de modelos disponibles"""
    print_header("📚 Modelos Recomendados para Ollama")
    
    models_info = [
        ("glm4:9b", "4.7GB", "8GB RAM", "Multilingüe, general"),
        ("llama3.1:8b", "4.7GB", "8GB RAM", "Rápido, inglés"),
        ("mistral:7b", "4.1GB", "6GB RAM", "Ultra rápido"),
        ("qwen2.5:14b", "9GB", "16GB RAM", "Mejor español"),
        ("llama3.3:70b", "40GB", "GPU 24GB", "Production-grade"),
    ]
    
    if PRETTY:
        table = create_table(
            "Modelos Ollama",
            ["Modelo", "Tamaño", "Requisitos", "Best For"],
            models_info
        )
        console.print(table)
    else:
        print("\nModelos Recomendados:")
        for model, size, req, desc in models_info:
            print(f"  • {model} - {size} - Req: {req} - {desc}")
    
    print_info("\n💡 Para empezar: ollama pull glm4:9b")


def main():
    """Main demo"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ollama Demo')
    parser.add_argument('--conversation', action='store_true', help='Demo conversación')
    parser.add_argument('--backends', action='store_true', help='Ver backends')
    parser.add_argument('--models', action='store_true', help='Ver modelos')
    parser.add_argument('--all', action='store_true', help='Todas las demos')
    
    args = parser.parse_args()
    
    if not any([args.conversation, args.backends, args.models, args.all]):
        # Interactive menu
        print_header("🤖 OLLAMA DEMO", "Demostración de LLMs Open Source")
        
        print("\n¿Qué demo querés ver?\n")
        print("1. 💬 Conversación con Ollama (principal)")
        print("2. 🔍 Backends disponibles")
        print("3. 📚 Info de modelos")
        print("4. 🎯 Todas las demos")
        print("0. Salir")
        
        choice = input("\nElegí (1-4): ").strip()
        
        if choice == '1':
            args.conversation = True
        elif choice == '2':
            args.backends = True
        elif choice == '3':
            args.models = True
        elif choice == '4':
            args.all = True
        else:
            print_info("Saliendo...")
            return
    
    # Run demos
    if args.all or args.backends:
        demo_backend_comparison()
        print()
    
    if args.all or args.models:
        demo_model_info()
        print()
    
    if args.all or args.conversation:
        success = demo_conversation()
        
        if not success:
            print("\n")
            print_warning("Demo de conversación no pudo ejecutarse")
            print_info("Asegurate de:")
            print_info("  1. Instalar Ollama: curl -fsSL https://ollama.com/install.sh | sh")
            print_info("  2. Descargar modelo: ollama pull glm4:9b")
            print_info("  3. Correr servidor: ollama serve")


if __name__ == "__main__":
    main()
