#!/usr/bin/env python3
"""
Uptime Monitor per ErixCast Bot
Questo script può essere eseguito su un servizio esterno (come Railway, Heroku, o un VPS)
per mantenere attivo il bot su Render pingando periodicamente l'endpoint.
"""

import time
import requests
import logging
import os
from datetime import datetime

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configurazione
RENDER_URL = os.getenv('RENDER_URL', 'https://erixcastbot.onrender.com')
PING_INTERVAL = int(os.getenv('PING_INTERVAL', '300'))  # 5 minuti default
TIMEOUT = 30  # secondi

def ping_service():
    """Ping the Render service to keep it alive"""
    try:
        start_time = time.time()

        # Ping health check endpoint
        response = requests.get(f"{RENDER_URL}/", timeout=TIMEOUT)
        response_time = time.time() - start_time

        if response.status_code == 200:
            logger.info(f"✅ Health check successful - Response time: {response_time:.2f}s")
        else:
            logger.warning(f"Health check failed with status {response.status_code}")

        # Also ping the ping endpoint
        ping_response = requests.get(f"{RENDER_URL}/ping", timeout=TIMEOUT)
        if ping_response.status_code == 200:
            logger.info("✅ Ping endpoint responded successfully")
        else:
            logger.warning(f"Ping endpoint failed with status {ping_response.status_code}")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Ping failed: {e}")
    except Exception as e:
        logger.error(f"💥 Unexpected error during ping: {e}")

def main():
    """Main monitoring loop"""
    logger.info("🚀 Starting Uptime Monitor for ErixCast Bot")
    logger.info(f"📡 Monitoring URL: {RENDER_URL}")
    logger.info(f"⏰ Ping interval: {PING_INTERVAL} seconds")

    while True:
        ping_service()
        time.sleep(PING_INTERVAL)

if __name__ == '__main__':
    main()