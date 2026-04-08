
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from dashboard.mock_service import mock_data
    
    print("Testing Mock Service...")
    
    # Test sales list
    sales = mock_data.get_sales_list(limit=5)
    print(f"✅ get_sales_list returned {len(sales)} items")
    if sales:
        print(f"   Sample: {sales[0]['product_sku']} - {sales[0]['status']}")
        
    # Test conversations
    chats = mock_data.get_conversations(limit=5)
    print(f"✅ get_conversations returned {len(chats)} items")
    if chats:
        print(f"   Sample: {chats[0]['session_id']} - {chats[0]['message_count']} msgs")
        
    print("\nSUCCESS: Mock service methods work correctly.")
    
except Exception as e:
    print(f"\n❌ FAIL: {e}")
    sys.exit(1)
