#!/usr/bin/env python3
"""
Script per riavviare il bot su Render
Triggera un restart automatico del servizio
"""

import os
import sys
import requests
import time
import logging
import subprocess
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def trigger_render_restart():
    """Triggera un restart del bot su Render"""
    logger.info("🔄 Triggering bot restart on Render...")
    
    try:
        # Metodo 1: Commit vuoto per triggerare redeploy
        logger.info("📤 Creating empty commit to trigger redeploy...")
        
        # Crea un commit vuoto
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        commit_msg = f"🔄 Restart bot - {timestamp}"
        
        # Esegui git commit vuoto
        result = subprocess.run([
            'git', 'commit', '--allow-empty', '-m', commit_msg
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Empty commit created successfully")
            
            # Push per triggerare deploy
            result = subprocess.run([
                'git', 'push', 'origin', 'main'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("✅ Push successful - Render will restart automatically")
                return True
            else:
                logger.error(f"❌ Push failed: {result.stderr}")
                return False
        else:
            logger.error(f"❌ Commit failed: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to trigger restart: {e}")
        return False

def wait_for_restart():
    """Aspetta che il restart sia completato"""
    logger.info("⏳ Waiting for bot restart to complete...")
    
    render_url = "https://erixcastbot.onrender.com"
    health_endpoint = f"{render_url}/health"
    
    # Aspetta un po' per dare tempo al deploy di iniziare
    logger.info("⏳ Waiting 30 seconds for deploy to start...")
    time.sleep(30)
    
    max_attempts = 20  # 10 minuti max
    attempt = 0
    
    while attempt < max_attempts:
        try:
            logger.info(f"🔍 Checking bot status (attempt {attempt + 1}/{max_attempts})...")
            
            response = requests.get(health_endpoint, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'unknown')
                
                if status == 'healthy':
                    logger.info("✅ Bot restarted successfully!")
                    logger.info(f"📊 Status: {status}")
                    logger.info(f"🗄️ Database: {data.get('database', {}).get('status', 'unknown')}")
                    return True
                else:
                    logger.info(f"⏳ Bot status: {status} - waiting...")
            else:
                logger.info(f"⏳ HTTP {response.status_code} - bot still restarting...")
                
        except requests.exceptions.RequestException as e:
            logger.info(f"⏳ Connection error (expected during restart): {e}")
        
        attempt += 1
        time.sleep(30)  # Aspetta 30 secondi tra i tentativi
    
    logger.warning("⚠️ Timeout waiting for restart - check manually")
    return False

def verify_bot_functionality():
    """Verifica che il bot funzioni correttamente dopo il restart"""
    logger.info("🔍 Verifying bot functionality...")
    
    try:
        render_url = "https://erixcastbot.onrender.com"
        
        # Test ping endpoint
        ping_response = requests.get(f"{render_url}/ping", timeout=10)
        if ping_response.status_code == 200:
            logger.info("✅ Ping endpoint working")
        else:
            logger.warning(f"⚠️ Ping endpoint issue: {ping_response.status_code}")
        
        # Test health endpoint
        health_response = requests.get(f"{render_url}/health", timeout=15)
        if health_response.status_code == 200:
            data = health_response.json()
            logger.info("✅ Health endpoint working")
            logger.info(f"📊 Bot Status: {data.get('status')}")
            logger.info(f"🗄️ Database: {data.get('database', {}).get('status')}")
            logger.info(f"💾 Memory: {data.get('resources', {}).get('memory_mb', 'N/A')}MB")
            return True
        else:
            logger.error(f"❌ Health endpoint failed: {health_response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

def main():
    """Funzione principale per il restart del bot"""
    logger.info("🔄 ErixCast Bot Restart Utility")
    logger.info("=" * 50)
    
    # Step 1: Triggera il restart
    if not trigger_render_restart():
        logger.error("❌ Failed to trigger restart")
        sys.exit(1)
    
    # Step 2: Aspetta il completamento
    if not wait_for_restart():
        logger.warning("⚠️ Restart may not have completed successfully")
    
    # Step 3: Verifica funzionalità
    if verify_bot_functionality():
        logger.info("🎉 Bot restart completed successfully!")
        logger.info("✅ All systems operational")
    else:
        logger.warning("⚠️ Bot restarted but some issues detected")
    
    logger.info("=" * 50)
    logger.info("🏁 Restart process completed")

if __name__ == "__main__":
    main()