#!/usr/bin/env python3
"""
External Pinger Service per ErixCast Bot
Da deployare su un servizio separato (Railway, Heroku, ecc.) per pingare il bot su Render
Garantisce uptime 24/7 completamente gratuito
"""

import time
import requests
import logging
import os
import json
from datetime import datetime, timezone
from flask import Flask, jsonify

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app per health check del pinger stesso
app = Flask(__name__)

class ExternalPinger:
    def __init__(self):
        # URL del bot su Render
        self.target_url = os.getenv('TARGET_URL', 'https://erixcastbot.onrender.com')
        self.ping_interval = int(os.getenv('PING_INTERVAL', '300'))  # 5 minuti default
        self.timeout = 30
        
        # Statistiche
        self.stats = {
            'start_time': datetime.now(timezone.utc).isoformat(),
            'total_pings': 0,
            'successful_pings': 0,
            'failed_pings': 0,
            'last_ping': None,
            'last_success': None,
            'uptime_percentage': 100.0,
            'consecutive_failures': 0
        }
        
        # Endpoints da provare in ordine di priorità
        self.endpoints = ['/health', '/ping', '/', '/status']
        
    def ping_target(self):
        """Ping del target con fallback su endpoint multipli"""
        self.stats['total_pings'] += 1
        self.stats['last_ping'] = datetime.now(timezone.utc).isoformat()
        
        for endpoint in self.endpoints:
            try:
                start_time = time.time()
                url = f"{self.target_url}{endpoint}"
                
                response = requests.get(url, timeout=self.timeout)
                response_time = time.time() - start_time
                
                if response.status_code == 200:
                    self.stats['successful_pings'] += 1
                    self.stats['last_success'] = datetime.now(timezone.utc).isoformat()
                    self.stats['consecutive_failures'] = 0
                    
                    logger.info(f"✅ Ping successful - {endpoint} - {response_time:.2f}s")
                    self._update_uptime()
                    return True
                    
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Timeout on {endpoint}")
                continue
            except requests.exceptions.ConnectionError:
                logger.warning(f"🔌 Connection error on {endpoint}")
                continue
            except Exception as e:
                logger.warning(f"❌ Error on {endpoint}: {e}")
                continue
        
        # Se arriviamo qui, tutti gli endpoint hanno fallito
        self.stats['failed_pings'] += 1
        self.stats['consecutive_failures'] += 1
        
        logger.error(f"💥 All endpoints failed - Consecutive failures: {self.stats['consecutive_failures']}")
        self._update_uptime()
        return False
    
    def _update_uptime(self):
        """Aggiorna la percentuale di uptime"""
        if self.stats['total_pings'] > 0:
            self.stats['uptime_percentage'] = (self.stats['successful_pings'] / self.stats['total_pings']) * 100
    
    def start_pinging(self):
        """Avvia il ping continuo"""
        logger.info(f"🎯 Starting External Pinger for {self.target_url}")
        logger.info(f"⏰ Ping interval: {self.ping_interval} seconds")
        
        while True:
            try:
                self.ping_target()
                
                # Log statistiche ogni 12 ping (1 ora con intervallo 5min)
                if self.stats['total_pings'] % 12 == 0:
                    logger.info(f"📊 Hourly Stats - Uptime: {self.stats['uptime_percentage']:.1f}% | Total: {self.stats['total_pings']} | Failures: {self.stats['consecutive_failures']}")
                
                # Se troppi fallimenti consecutivi, riduci l'intervallo temporaneamente
                if self.stats['consecutive_failures'] >= 3:
                    sleep_time = self.ping_interval // 2  # Dimezza l'intervallo
                    logger.warning(f"🚨 High failure rate - reducing interval to {sleep_time}s")
                else:
                    sleep_time = self.ping_interval
                
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                logger.info("🛑 External Pinger stopped by user")
                break
            except Exception as e:
                logger.error(f"💥 Unexpected error: {e}")
                time.sleep(60)  # Pausa prima di riprovare

# Flask endpoints per monitoraggio del pinger stesso
@app.route('/')
def root():
    return jsonify({
        'service': 'ErixCast Bot External Pinger',
        'status': 'running',
        'target': os.getenv('TARGET_URL', 'https://erixcastbot.onrender.com')
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/stats')
def stats():
    return jsonify(pinger.stats)

# Istanza globale del pinger
pinger = ExternalPinger()

def run_pinger():
    """Esegue il pinger in background"""
    pinger.start_pinging()

if __name__ == '__main__':
    import threading
    
    # Avvia il pinger in un thread separato
    pinger_thread = threading.Thread(target=run_pinger, daemon=True)
    pinger_thread.start()
    
    # Avvia Flask per health check
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)