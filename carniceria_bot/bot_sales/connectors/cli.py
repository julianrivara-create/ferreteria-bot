#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CLI Connector for Sales Bot
Interactive terminal interface for testing
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_sales.bot import SalesBot


# Terminal colors
class C:
    BOT = '\033[92m'      # Green
    USER = '\033[0m'      # White
    GREY = '\033[90m'     # Grey
    ALERT = '\033[93m'    # Yellow
    END = '\033[0m'
    BOLD = '\033[1m'


def main():
    """Run CLI interface"""
    print(f"{C.BOLD}--- 🤖 iPHONE SALES BOT (ChatGPT Edition) ---{C.END}\n")
    
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print(f"{C.ALERT}⚠️  MODO DEMO: No hay OPENAI_API_KEY configurada{C.END}")
        print(f"{C.GREY}El bot funcionará en modo mock (respuestas simuladas){C.END}")
        print(f"{C.GREY}Para usar ChatGPT real: export OPENAI_API_KEY='sk-...'{C.END}\n")
    else:
        print(f"{C.GREY}✅ API Key detectada - Usando ChatGPT real{C.END}\n")
    
    # Initialize bot
    try:
        bot = SalesBot()
    except Exception as e:
        print(f"{C.ALERT}Error inicializando bot: {e}{C.END}")
        return
    
    # Session ID for CLI
    session_id = "cli_user"
    
    # Welcome message
    print(f"{C.GREY}Tip: Escribí 'salir' o 'exit' para terminar, 'reset' para reiniciar{C.END}\n")
    
    # Get initial greeting
    try:
        greeting = bot.process_message(session_id, "hola")
        print(f"{C.BOT}Bot: {greeting}{C.END}\n")
    except Exception as e:
        print(f"{C.ALERT}Error: {e}{C.END}\n")
    
    # Main loop
    while True:
        try:
            # Get user input
            user_input = input(f"{C.USER}Vos: {C.END}").strip()
            
            if not user_input:
                continue
            
            # Handle special commands
            if user_input.lower() in ["exit", "salir", "quit"]:
                print(f"\n{C.GREY}👋 ¡Hasta luego!{C.END}")
                break
            
            if user_input.lower() == "reset":
                bot.reset_session(session_id)
                print(f"{C.GREY}🔄 Conversación reiniciada{C.END}\n")
                continue
            
            # Process message
            response = bot.process_message(session_id, user_input)
            print(f"{C.BOT}Bot: {response}{C.END}\n")
        
        except KeyboardInterrupt:
            print(f"\n\n{C.GREY}👋 Interrupted. Saliendo...{C.END}")
            break
        
        except Exception as e:
            print(f"{C.ALERT}❌ Error: {e}{C.END}\n")
            import traceback
            traceback.print_exc()
    
    # Cleanup
    bot.close()
    print(f"{C.GREY}Bot cerrado correctamente{C.END}")


if __name__ == "__main__":
    main()
