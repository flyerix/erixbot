#!/usr/bin/env python3
"""
Test per verificare se il bot riceve i comandi
"""

import requests
import json
import os
from datetime import datetime

def test_bot_commands():
    """Testa se il bot riceve i comandi"""
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not found")
        return False
    
    # URL API Telegram
    api_url = f"https://api.telegram.org/bot{bot_token}"
    
    try:
        # Test 1: Verifica che il bot sia online
        print("🔍 Testing bot status...")
        response = requests.get(f"{api_url}/getMe", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                print(f"✅ Bot online: @{bot_info.get('username', 'unknown')}")
            else:
                print(f"❌ Bot API error: {data}")
                return False
        else:
            print(f"❌ Bot API HTTP error: {response.status_code}")
            return False
        
        # Test 2: Verifica gli updates recenti
        print("🔍 Checking recent updates...")
        response = requests.get(f"{api_url}/getUpdates?limit=5", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                updates = data.get('result', [])
                print(f"📨 Recent updates: {len(updates)}")
                
                for update in updates[-3:]:  # Ultimi 3 updates
                    update_id = update.get('update_id')
                    message = update.get('message', {})
                    text = message.get('text', 'N/A')
                    date = message.get('date', 0)
                    
                    if date:
                        dt = datetime.fromtimestamp(date)
                        print(f"  📝 Update {update_id}: '{text}' at {dt}")
                    
            else:
                print(f"❌ Updates API error: {data}")
                return False
        else:
            print(f"❌ Updates API HTTP error: {response.status_code}")
            return False
        
        # Test 3: Verifica webhook status
        print("🔍 Checking webhook status...")
        response = requests.get(f"{api_url}/getWebhookInfo", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                webhook_info = data.get('result', {})
                webhook_url = webhook_info.get('url', '')
                pending_updates = webhook_info.get('pending_update_count', 0)
                last_error = webhook_info.get('last_error_message', '')
                
                print(f"🌐 Webhook URL: {webhook_url or 'Not set (polling mode)'}")
                print(f"📊 Pending updates: {pending_updates}")
                if last_error:
                    print(f"❌ Last webhook error: {last_error}")
                else:
                    print("✅ No webhook errors")
                    
            else:
                print(f"❌ Webhook API error: {data}")
                return False
        else:
            print(f"❌ Webhook API HTTP error: {response.status_code}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def main():
    """Funzione principale"""
    print("🧪 ErixCast Bot Command Test")
    print("=" * 40)
    
    if test_bot_commands():
        print("\n✅ Bot tests completed")
        print("\n💡 If bot is not responding to commands:")
        print("   1. Check if bot is stuck in initialization")
        print("   2. Verify command handlers are registered")
        print("   3. Check for event loop issues")
        print("   4. Restart the bot service")
    else:
        print("\n❌ Bot tests failed")
        print("   Bot may be offline or misconfigured")

if __name__ == "__main__":
    main()