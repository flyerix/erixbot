#!/usr/bin/env python3
"""
Sistema di stabilità avanzato per mantenere il bot attivo 24/7
Implementa auto-restart, monitoraggio e recovery automatico
"""

import os
import sys
import asyncio
import logging
import time
import threading
import signal
from datetime import datetime, timezone
from typing import Optional
import subprocess

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class BotStabilityManager:
    """Gestore di stabilità per mantenere il bot attivo 24/7"""
    
    def __init__(self):
        self.bot_process = None
        self.restart_count = 0
        self.max_restarts = 50  # Limite restart per evitare loop infiniti
        self.restart_delay = 30  # Secondi tra restart
        self.last_restart = None
        self.running = True
        self.health_check_interval = 60  # Controllo ogni minuto
        self.last_health_check = None
        
    def is_bot_healthy(self) -> bool:
        """Controlla se il bot è sano tramite health check"""
        try:
            import requests
            port = int(os.environ.get('PORT', 10000))
            health_url = f'http://localhost:{port}/health'
            
            response = requests.get(health_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', 'unknown')
                
                if status in ['healthy', 'degraded']:
                    logger.info(f"✅ Bot health check OK - Status: {status}")
                    return True
                else:
                    logger.warning(f"⚠️ Bot health check failed - Status: {status}")
                    return False
            else:
                logger.warning(f"⚠️ Health check HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return False
    
    def start_bot_process(self):
        """Avvia il processo del bot"""
        try:
            logger.info("🚀 Starting bot process...")
            
            # Comando per avviare il bot
            cmd = [sys.executable, "-m", "bot"]
            
            # Avvia il processo
            self.bot_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            logger.info(f"✅ Bot process started with PID: {self.bot_process.pid}")
            
            # Thread per leggere output del bot
            def read_bot_output():
                try:
                    for line in iter(self.bot_process.stdout.readline, ''):
                        if line:
                            logger.info(f"BOT: {line.strip()}")
                except Exception as e:
                    logger.error(f"Error reading bot output: {e}")
            
            output_thread = threading.Thread(target=read_bot_output, daemon=True)
            output_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start bot process: {e}")
            return False
    
    def stop_bot_process(self):
        """Ferma il processo del bot"""
        if self.bot_process:
            try:
                logger.info("🛑 Stopping bot process...")
                self.bot_process.terminate()
                
                # Aspetta che il processo si chiuda
                try:
                    self.bot_process.wait(timeout=30)
                    logger.info("✅ Bot process stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("⚠️ Bot process didn't stop gracefully, forcing kill")
                    self.bot_process.kill()
                    self.bot_process.wait()
                    
            except Exception as e:
                logger.error(f"❌ Error stopping bot process: {e}")
            finally:
                self.bot_process = None
    
    def restart_bot(self, reason: str = "Manual restart"):
        """Riavvia il bot"""
        if self.restart_count >= self.max_restarts:
            logger.critical(f"💥 Max restarts reached ({self.max_restarts}). Stopping stability manager.")
            self.running = False
            return False
        
        self.restart_count += 1
        self.last_restart = datetime.now(timezone.utc)
        
        logger.warning(f"🔄 Restarting bot (#{self.restart_count}) - Reason: {reason}")
        
        # Ferma il processo corrente
        self.stop_bot_process()
        
        # Aspetta prima di riavviare
        logger.info(f"⏳ Waiting {self.restart_delay}s before restart...")
        time.sleep(self.restart_delay)
        
        # Avvia nuovo processo
        if self.start_bot_process():
            logger.info(f"✅ Bot restarted successfully (#{self.restart_count})")
            return True
        else:
            logger.error(f"❌ Failed to restart bot (#{self.restart_count})")
            return False
    
    def monitor_bot_health(self):
        """Monitora la salute del bot e riavvia se necessario"""
        logger.info("🔍 Starting bot health monitoring...")
        
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        while self.running:
            try:
                # Controlla se il processo è ancora vivo
                if self.bot_process and self.bot_process.poll() is not None:
                    logger.error(f"💥 Bot process died with exit code: {self.bot_process.returncode}")
                    if self.restart_bot("Process died"):
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                
                # Controlla health check
                elif not self.is_bot_healthy():
                    consecutive_failures += 1
                    logger.warning(f"⚠️ Bot health check failed ({consecutive_failures}/{max_consecutive_failures})")
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error("💥 Multiple consecutive health check failures")
                        if self.restart_bot("Health check failures"):
                            consecutive_failures = 0
                        else:
                            logger.critical("❌ Failed to restart after health check failures")
                            break
                else:
                    # Bot è sano
                    consecutive_failures = 0
                
                self.last_health_check = datetime.now(timezone.utc)
                
                # Aspetta prima del prossimo controllo
                time.sleep(self.health_check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Health monitoring stopped by user")
                self.running = False
                break
            except Exception as e:
                logger.error(f"❌ Error in health monitoring: {e}")
                time.sleep(10)  # Aspetta prima di riprovare
    
    def get_stats(self) -> dict:
        """Restituisce statistiche del stability manager"""
        return {
            'restart_count': self.restart_count,
            'last_restart': self.last_restart.isoformat() if self.last_restart else None,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'bot_process_alive': self.bot_process is not None and self.bot_process.poll() is None,
            'bot_process_pid': self.bot_process.pid if self.bot_process else None,
            'running': self.running
        }
    
    def run(self):
        """Avvia il sistema di stabilità"""
        logger.info("🚀 Starting Bot Stability Manager...")
        
        # Gestione segnali per shutdown graceful
        def signal_handler(signum, frame):
            logger.info(f"📡 Received signal {signum}, shutting down...")
            self.running = False
            self.stop_bot_process()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        try:
            # Avvia il bot inizialmente
            if not self.start_bot_process():
                logger.critical("❌ Failed to start initial bot process")
                return False
            
            # Avvia il monitoraggio in un thread separato
            monitor_thread = threading.Thread(target=self.monitor_bot_health, daemon=True)
            monitor_thread.start()
            
            # Loop principale - mantiene il processo vivo
            logger.info("🔄 Entering main stability loop...")
            while self.running:
                try:
                    time.sleep(10)  # Check ogni 10 secondi
                    
                    # Log periodico delle statistiche
                    if self.restart_count > 0 and self.restart_count % 5 == 0:
                        stats = self.get_stats()
                        logger.info(f"📊 Stability stats: {stats}")
                        
                except KeyboardInterrupt:
                    logger.info("🛑 Stability manager stopped by user")
                    break
                except Exception as e:
                    logger.error(f"❌ Error in main stability loop: {e}")
                    time.sleep(5)
            
            logger.info("✅ Stability manager shutdown complete")
            return True
            
        except Exception as e:
            logger.critical(f"💥 Critical error in stability manager: {e}")
            return False
        finally:
            self.stop_bot_process()

def main():
    """Funzione principale"""
    logger.info("🚀 ErixCast Bot Stability Manager v2.0")
    logger.info("=" * 60)
    
    # Crea e avvia il stability manager
    stability_manager = BotStabilityManager()
    
    try:
        success = stability_manager.run()
        if success:
            logger.info("✅ Stability manager completed successfully")
        else:
            logger.error("❌ Stability manager failed")
            sys.exit(1)
    except Exception as e:
        logger.critical(f"💥 Stability manager crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()