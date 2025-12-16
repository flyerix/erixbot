#!/usr/bin/env python3
"""
Script per pulire gli updates pending del bot
"""

import requests
import os

def clear_pending_updates():
    """Pulisce gli updates pending del bot"""
    
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN not found")
        return False
    
    api_url = f"https://api.telegram.org/bot{bot_token}"
    
    try:
        # Get current updates
        print("🔍 Getting current updates...")
        response = requests.get(f"{api_url}/getUpdates", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                updates = data.get('result', [])
                print(f"📨 Found {len(updates)} pending updates")
                
                if updates:
                    # Get the highest update_id
                    highest_id = max(update.get('update_id', 0) for update in updates)
                    print(f"🔢 Highest update ID: {highest_id}")
                    
                    # Clear all updates by setting offset to highest_id + 1
                    clear_response = requests.get(
                        f"{api_url}/getUpdates?offset={highest_id + 1}&limit=1", 
                        timeout=10
                    )
                    
                    if clear_response.status_code == 200:
                        clear_data = clear_response.json()
                        if clear_data.get('ok'):
                            print("✅ Pending updates cleared successfully")
                            return True
                        else:
                            print(f"❌ Clear failed: {clear_data}")
                            return False
                    else:
                        print(f"❌ Clear HTTP error: {clear_response.status_code}")
                        return False
                else:
                    print("✅ No pending updates to clear")
                    return True
            else:
                print(f"❌ API error: {data}")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Funzione principale"""
    print("🧹 Clear Pending Updates Utility")
    print("=" * 40)
    
    if clear_pending_updates():
        print("\n✅ Updates cleared successfully")
        print("🔄 Bot should now be able to process new commands")
    else:
        print("\n❌ Failed to clear updates")

if __name__ == "__main__":
    main()