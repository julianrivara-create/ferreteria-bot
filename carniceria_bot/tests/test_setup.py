#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quick Setup Test Script
Tests that the bot can be initialized and run basic operations
"""

import sys
import os

# Ensure we're in the right directory
os.chdir('/Users/julian/Desktop/iphone-bot-demo')
sys.path.insert(0, '.')

def test_imports():
    """Test that all modules can be imported"""
    print("1️⃣ Testing imports...")
    try:
        from bot_sales.bot import SalesBot
        from bot_sales.core.database import Database
        from bot_sales.core.chatgpt import ChatGPTClient, get_available_functions
        from bot_sales.core.business_logic import BusinessLogic
        from bot_sales import config
        print("   ✅ All imports successful\n")
        return True
    except Exception as e:
        print(f"   ❌ Import error: {e}\n")
        return False

def test_database():
    """Test database initialization"""
    print("2️⃣ Testing database...")
    try:
        from bot_sales.core.database import Database
        db = Database("test_bot.db", "catalog.csv", "test.log")
        
        # Check catalog loaded
        stock = db.load_stock()
        print(f"   ✅ Database initialized with {len(stock)} products\n")
        
        db.close()
        if os.path.exists("test_bot.db"):
            os.remove("test_bot.db")
        if os.path.exists("test.log"):
            os.remove("test.log")
        return True
    except Exception as e:
        print(f"   ❌ Database error: {e}\n")
        return False

def test_chatgpt_mock():
    """Test ChatGPT in mock mode"""
    print("3️⃣ Testing ChatGPT mock mode...")
    try:
        from bot_sales.core.chatgpt import ChatGPTClient
        
        # No API key = mock mode
        client = ChatGPTClient(api_key="", model="gpt-4")
        
        if not client.mock_mode:
            print("   ❌ Mock mode not activated\n")
            return False
        
        # Test mock response
        response = client.send_message([{"role": "user", "content": "hola"}])
        
        if "content" in response and response["content"]:
            print(f"   ✅ Mock response: {response['content'][:50]}...\n")
            return True
        else:
            print("   ❌ No response from mock\n")
            return False
            
    except Exception as e:
        print(f"   ❌ ChatGPT mock error: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def test_bot_init():
    """Test bot initialization"""
    print("4️⃣ Testing bot initialization...")
    try:
        # Make sure no API key is set
        os.environ.pop('OPENAI_API_KEY', None)
        
        from bot_sales.bot import SalesBot
        bot = SalesBot()
        
        print("   ✅ Bot initialized successfully\n")
        bot.close()
        
        # Clean up test db
        if os.path.exists("iphone_store.db"):
            os.remove("iphone_store.db")
        
        return True
    except Exception as e:
        print(f"   ❌ Bot init error: {e}\n")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("🧪 BOT SETUP VERIFICATION TEST")
    print("=" * 60 + "\n")
    
    tests = [
        test_imports,
        test_database,
        test_chatgpt_mock,
        test_bot_init,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("=" * 60)
    print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("\n🎉 ALL TESTS PASSED! Bot is ready to use.\n")
        print("Next steps:")
        print("1. Test CLI: python bot_sales/connectors/cli.py")
        print("2. Get OpenAI API key from: https://platform.openai.com/api-keys")
        print("3. Set key: export OPENAI_API_KEY='sk-...'")
        print("4. Re-run CLI to use real ChatGPT")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED. Check errors above.\n")
        return 1

if __name__ == "__main__":
    exit(main())
