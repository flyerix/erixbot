#!/usr/bin/env python3
"""
Enhanced Uptime Keeper per ErixCast Bot
Sistema di ping multiplo per garantire uptime 24/7 su Render (piano gratuito)
"""

import time
import requests
import logging
import os
import threading
from datetime import datetime, timezone
import json

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UptimeKeeper:
    def __init__(self):
        self.render_url = os.getenv('RENDER_URL', 'https://erixcastbot.onrender.com')
        self.ping_intervals = [4, 6, 8]  # minuti - intervalli diversi per ridondanza
        self.timeout = 30
        self.max_failures = 3
        self.threads = []
        self.stats = {
            'total_pings': 0,
            'successful_pings': 0,
            'failed_pings': 0,
            'last_success': None,
            'uptime_percentage': 100.0
        }
        
    def ping_service(self, endpoint='/health'):
        """Ping del servizio con gestione errori avanzata"""
        try:
            start_time = time.time()
            response = requests.get(f"{self.render_url}{endpoint}", timeout=self.timeout)
            response_time = time.time() - start_time
            
            self.stats['total_pings'] += 1
            
            if response.status_code == 200:
                self.stats['successful_pings'] += 1
                self.stats['last_success'] = datetime.now(timezone.utc).isoformat()
                logger.info(f"✅ Ping successful - {response_time:.2f}s - Status: {response.status_code}")
                return True
            else:
                self.stats['failed_pings'] += 1
                logger.warning(f"⚠️ Ping failed - Status: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            self.stats['failed_pings'] += 1
            logger.error("⏰ Ping timeout")
            return False
        except requests.exceptions.ConnectionError:
            self.stats['failed_pings'] += 1
            logger.error("🔌 Connection error - service might be sleeping")
            return False
        except Exception as e:
            self.stats['failed_pings'] += 1
            logger.error(f"💥 Ping error: {e}")
            return False
    
    def create_ping_worker(self, interval_minutes, worker_id):
        """Crea un worker di ping con intervallo specifico"""
        def worker():
            logger.info(f"🚀 Starting ping worker {worker_id} (interval: {interval_minutes}min)")
            consecutive_failures = 0
            
            while True:
                success = self.ping_service()
                
                if success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    
                    # Se troppi fallimenti consecutivi, prova endpoint alternativi
                    if consecutive_failures >= self.max_failures:
                        logger.warning(f"🔄 Worker {worker_id}: {consecutive_failures} failures, trying alternative endpoints")
                        
                        # Prova endpoint alternativi
                        for alt_endpoint in ['/ping', '/', '/status']:
                            if self.ping_service(alt_endpoint):
                                consecutive_failures = 0
                                break
                            time.sleep(10)  # Pausa tra tentativi
                
                # Calcola uptime percentage
                if self.stats['total_pings'] > 0:
                    self.stats['uptime_percentage'] = (self.stats['successful_pings'] / self.stats['total_pings']) * 100
                
                # Log statistiche ogni 10 ping
                if self.stats['total_pings'] % 10 == 0:
                    logger.info(f"📊 Stats - Total: {self.stats['total_pings']}, Success: {self.stats['successful_pings']}, Uptime: {self.stats['uptime_percentage']:.1f}%")
                
                # Attendi prossimo ping
                time.sleep(interval_minutes * 60)
        
        return threading.Thread(target=worker, daemon=True, name=f"PingWorker-{worker_id}")
    
    def start_monitoring(self):
        """Avvia il monitoraggio con thread multipli"""
        logger.info(f"🎯 Starting Enhanced Uptime Keeper for {self.render_url}")
        
        # Crea e avvia thread multipli con intervalli diversi
        for i, interval in enumerate(self.ping_intervals):
            worker = self.create_ping_worker(interval, i+1)
            self.threads.append(worker)
            worker.start()
            time.sleep(30)  # Sfasa l'avvio dei thread
        
        logger.info(f"✅ Started {len(self.threads)} ping workers for 24/7 uptime")
        
        # Thread principale per statistiche
        self.stats_thread()
    
    def stats_thread(self):
        """Thread per logging statistiche periodiche"""
        while True:
            time.sleep(3600)  # Ogni ora
            logger.info(f"📈 Hourly Stats - Uptime: {self.stats['uptime_percentage']:.2f}% | Total Pings: {self.stats['total_pings']} | Last Success: {self.stats['last_success']}")
    
    def get_stats(self):
        """Restituisce statistiche correnti"""
        return self.stats.copy()

def main():
    """Funzione principale"""
    keeper = UptimeKeeper()
    
    try:
        keeper.start_monitoring()
        
        # Mantieni il processo attivo
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("🛑 Uptime Keeper stopped by user")
    except Exception as e:
        logger.error(f"💥 Uptime Keeper crashed: {e}")
        raise

if __name__ == '__main__':
    main()