#!/usr/bin/env python3
"""
Bot Watchdog - Sistema di monitoraggio esterno per riavviare il bot se si blocca
Mantiene il bot attivo 24/7 su Render
"""

import os
import sys
import time
import requests
import logging
import threading
import subprocess
from datetime import datetime, timezone
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class BotWatchdog:
    """Watchdog per monitorare e riavviare il bot se necessario"""
    
    def __init__(self):
        self.check_interval = 60  # Controllo ogni minuto
        self.max_failures = 3  # Max fallimenti consecutivi prima del restart
        self.consecutive_failures = 0
        self.last_success = None
        self.restart_count = 0
        self.max_restarts = 20  # Limite restart per evitare loop infiniti
        self.running = True
        
        # URL per health check
        self.port = int(os.environ.get('PORT', 10000))
        self.health_url = f'http://localhost:{self.port}/health'
        self.ping_url = f'http://localhost:{self.port}/ping'
        
    def check_bot_health(self) -> bool:
        """Controlla se il bot è attivo e funzionante"""
        try:
            # Prima prova il ping (più leggero)
            response = requests.get(self.ping_url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'pong':
                    return True
            
            # Se ping fallisce, prova health check completo
            response = requests.get(self.health_url, timeout=20)
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'unknown')
                
                # Considera healthy anche se degraded (database issues temporanei)
                if status in ['healthy', 'degraded']:
                    return True
                else:
                    logger.warning(f"⚠️ Bot status not healthy: {status}")
                    return False
            else:
                logger.warning(f"⚠️ Health check HTTP error: {response.status_code}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("⏰ Health check timeout")
            return False
        except requests.exceptions.ConnectionError:
            logger.error("🔌 Cannot connect to bot - may be down")
            return False
        except Exception as e:
            logger.error(f"❌ Health check error: {e}")
            return False
    
    def restart_render_service(self) -> bool:
        """Triggera un restart del servizio Render"""
        try:
            logger.info("🔄 Triggering Render service restart...")
            
            # Su Render, possiamo triggerare un restart forzando un exit
            # Render rileverà che il processo è morto e lo riavvierà automaticamente
            
            # Prima prova a fare un graceful restart tramite API se disponibile
            try:
                # Invia segnale di restart al processo principale
                import signal
                import psutil
                
                # Trova il processo principale del bot
                current_pid = os.getpid()
                parent = psutil.Process(current_pid).parent()
                
                if parent:
                    logger.info(f"📡 Sending restart signal to parent process {parent.pid}")
                    parent.send_signal(signal.SIGUSR1)  # Custom restart signal
                    time.sleep(5)
                    
                    # Verifica se il restart ha funzionato
                    if self.check_bot_health():
                        logger.info("✅ Graceful restart successful")
                        return True
                
            except Exception as graceful_e:
                logger.warning(f"Graceful restart failed: {graceful_e}")
            
            # Se graceful restart fallisce, forza exit per triggere Render restart
            logger.warning("🚨 Forcing process exit to trigger Render restart")
            
            # Crea un file marker per indicare che è un restart intenzionale
            restart_marker = '/tmp/bot_restart_marker'
            with open(restart_marker, 'w') as f:
                f.write(f"Restart triggered by watchdog at {datetime.now(timezone.utc).isoformat()}")
            
            # Forza exit - Render riavvierà automaticamente
            os._exit(1)
            
        except Exception as e:
            logger.error(f"❌ Failed to restart service: {e}")
            return False
    
    def send_alert_to_admins(self, message: str):
        """Invia alert agli admin (se possibile)"""
        try:
            # Prova a inviare notifica tramite il bot stesso se è ancora raggiungibile
            admin_ids = os.getenv('ADMIN_IDS', '').split(',')
            
            for admin_id in admin_ids:
                if admin_id.strip():
                    try:
                        # Usa l'API di Telegram direttamente
                        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
                        if bot_token:
                            telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                            payload = {
                                'chat_id': admin_id.strip(),
                                'text': f"🚨 **Bot Watchdog Alert**\n\n{message}\n\n📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
                            }
                            
                            response = requests.post(telegram_url, json=payload, timeout=10)
                            if response.status_code == 200:
                                logger.info(f"📱 Alert sent to admin {admin_id}")
                            else:
                                logger.warning(f"Failed to send alert to admin {admin_id}: {response.status_code}")
                    except Exception as admin_e:
                        logger.warning(f"Failed to alert admin {admin_id}: {admin_e}")
                        
        except Exception as e:
            logger.error(f"Failed to send admin alerts: {e}")
    
    def run_monitoring(self):
        """Loop principale di monitoraggio"""
        logger.info("🔍 Starting bot monitoring...")
        logger.info(f"📊 Check interval: {self.check_interval}s")
        logger.info(f"🚨 Max failures before restart: {self.max_failures}")
        
        while self.running and self.restart_count < self.max_restarts:
            try:
                # Controlla la salute del bot
                is_healthy = self.check_bot_health()
                
                if is_healthy:
                    # Bot è sano
                    if self.consecutive_failures > 0:
                        logger.info(f"✅ Bot recovered after {self.consecutive_failures} failures")
                    
                    self.consecutive_failures = 0
                    self.last_success = datetime.now(timezone.utc)
                    
                    # Log periodico di stato
                    if self.restart_count > 0:
                        logger.info(f"💓 Bot healthy - Restarts: {self.restart_count}")
                    
                else:
                    # Bot non è sano
                    self.consecutive_failures += 1
                    logger.warning(f"⚠️ Bot health check failed ({self.consecutive_failures}/{self.max_failures})")
                    
                    if self.consecutive_failures >= self.max_failures:
                        # Troppi fallimenti - restart necessario
                        self.restart_count += 1
                        
                        alert_msg = f"Bot non risponde da {self.consecutive_failures} controlli. Restart #{self.restart_count} in corso..."
                        logger.error(f"🚨 {alert_msg}")
                        
                        # Invia alert agli admin
                        self.send_alert_to_admins(alert_msg)
                        
                        # Restart del servizio
                        if self.restart_render_service():
                            logger.info("✅ Restart triggered successfully")
                            # Il processo dovrebbe terminare qui se il restart funziona
                            time.sleep(30)  # Aspetta per vedere se il restart funziona
                        else:
                            logger.error("❌ Failed to trigger restart")
                        
                        # Reset counter dopo restart attempt
                        self.consecutive_failures = 0
                
                # Aspetta prima del prossimo controllo
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Monitoring stopped by user")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Error in monitoring loop: {e}")
                time.sleep(10)  # Aspetta prima di riprovare
        
        if self.restart_count >= self.max_restarts:
            logger.critical(f"💥 Max restarts reached ({self.max_restarts}). Stopping watchdog.")
            self.send_alert_to_admins(f"Watchdog ha raggiunto il limite di restart ({self.max_restarts}). Intervento manuale richiesto.")
        
        logger.info("✅ Bot monitoring completed")
    
    def get_stats(self) -> dict:
        """Restituisce statistiche del watchdog"""
        return {
            'restart_count': self.restart_count,
            'consecutive_failures': self.consecutive_failures,
            'last_success': self.last_success.isoformat() if self.last_success else None,
            'running': self.running,
            'max_restarts': self.max_restarts,
            'check_interval': self.check_interval
        }

def main():
    """Funzione principale del watchdog"""
    logger.info("🐕 ErixCast Bot Watchdog v1.0")
    logger.info("=" * 50)
    
    # Controlla se siamo su Render
    if not os.getenv('RENDER'):
        logger.warning("⚠️ Not running on Render - watchdog may not work as expected")
    
    # Crea e avvia il watchdog
    watchdog = BotWatchdog()
    
    try:
        # Aspetta un po' prima di iniziare per dare tempo al bot di avviarsi
        logger.info("⏳ Waiting 60 seconds for bot to start...")
        time.sleep(60)
        
        # Avvia il monitoraggio
        watchdog.run_monitoring()
        
    except Exception as e:
        logger.critical(f"💥 Watchdog crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()