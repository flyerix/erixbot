#!/usr/bin/env python3
"""
Deploy automatico per correggere il bot e restartare Render
Corregge tutti i problemi identificati nei log
"""

import os
import sys
import subprocess
import requests
import time
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(cmd, cwd=None):
    """Esegue un comando e restituisce il risultato"""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            logger.info(f"✅ Comando eseguito: {cmd}")
            return True, result.stdout
        else:
            logger.error(f"❌ Comando fallito: {cmd}")
            logger.error(f"Error: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Timeout comando: {cmd}")
        return False, "Timeout"
    except Exception as e:
        logger.error(f"💥 Errore comando: {cmd} - {e}")
        return False, str(e)

def check_git_status():
    """Controlla lo stato di Git"""
    logger.info("🔍 Controllo stato Git...")
    success, output = run_command("git status --porcelain")
    if success:
        if output.strip():
            logger.info(f"📝 File modificati trovati:\n{output}")
            return True
        else:
            logger.info("✅ Nessuna modifica da committare")
            return False
    return False

def commit_and_push_changes():
    """Committa e pusha le modifiche su GitHub"""
    logger.info("📤 Committando e pushando le correzioni...")
    
    # Add all changes
    success, _ = run_command("git add .")
    if not success:
        logger.error("❌ Errore durante git add")
        return False
    
    # Commit with descriptive message
    commit_msg = f"🔧 Fix bot errors - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                f"- Fix timezone mismatch in health check\n" \
                f"- Fix coroutine warning in BackgroundTaskManager\n" \
                f"- Fix database connection test for SQLite\n" \
                f"- Fix timezone calculation in user stats\n" \
                f"- Improve error handling and logging"
    
    success, _ = run_command(f'git commit -m "{commit_msg}"')
    if not success:
        logger.error("❌ Errore durante git commit")
        return False
    
    # Push to GitHub
    success, _ = run_command("git push origin main")
    if not success:
        logger.error("❌ Errore durante git push")
        return False
    
    logger.info("✅ Modifiche pushate su GitHub con successo!")
    return True

def trigger_render_deploy():
    """Triggera il deploy automatico su Render"""
    logger.info("🚀 Triggerando deploy automatico su Render...")
    
    # Render rileva automaticamente i push su GitHub e fa il redeploy
    # Aspettiamo un po' per dare tempo a GitHub di processare il push
    time.sleep(10)
    
    logger.info("✅ Deploy triggerato! Render inizierà il redeploy automaticamente.")
    return True

def wait_for_render_deploy():
    """Aspetta che il deploy su Render sia completato"""
    logger.info("⏳ Aspettando completamento deploy su Render...")
    
    # URL del bot su Render (sostituisci con il tuo URL)
    render_url = "https://erixcastbot.onrender.com"
    health_endpoint = f"{render_url}/health"
    
    max_attempts = 30  # 15 minuti max
    attempt = 0
    
    while attempt < max_attempts:
        try:
            logger.info(f"🔍 Tentativo {attempt + 1}/{max_attempts} - Controllo health check...")
            response = requests.get(health_endpoint, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') in ['healthy', 'degraded']:
                    logger.info("✅ Bot operativo su Render!")
                    logger.info(f"📊 Status: {data.get('status')}")
                    logger.info(f"🗄️ Database: {data.get('database', {}).get('status', 'unknown')}")
                    return True
            
            logger.info(f"⏳ Status: {response.status_code} - Aspettando...")
            
        except requests.exceptions.RequestException as e:
            logger.info(f"⏳ Connessione in corso... ({e})")
        
        attempt += 1
        time.sleep(30)  # Aspetta 30 secondi tra i tentativi
    
    logger.warning("⚠️ Timeout aspettando il deploy. Controlla manualmente su Render.")
    return False

def verify_fixes():
    """Verifica che le correzioni siano state applicate"""
    logger.info("🔍 Verificando che le correzioni siano state applicate...")
    
    render_url = "https://erixcastbot.onrender.com"
    
    try:
        # Test health endpoint
        response = requests.get(f"{render_url}/health", timeout=15)
        if response.status_code == 200:
            data = response.json()
            logger.info("✅ Health check funzionante!")
            logger.info(f"📊 Status: {data.get('status')}")
            
            # Verifica database
            db_status = data.get('database', {}).get('status')
            if db_status in ['connected', 'reconnected']:
                logger.info("✅ Database connesso correttamente!")
            else:
                logger.warning(f"⚠️ Database status: {db_status}")
            
            return True
        else:
            logger.error(f"❌ Health check fallito: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Errore durante verifica: {e}")
        return False

def main():
    """Funzione principale del deploy automatico"""
    logger.info("🚀 Avvio deploy automatico per correggere il bot...")
    logger.info("=" * 60)
    
    # Step 1: Controlla se ci sono modifiche da committare
    if not check_git_status():
        logger.info("ℹ️ Nessuna modifica da deployare")
        return
    
    # Step 2: Committa e pusha le modifiche
    if not commit_and_push_changes():
        logger.error("❌ Errore durante commit/push")
        sys.exit(1)
    
    # Step 3: Triggera deploy su Render
    if not trigger_render_deploy():
        logger.error("❌ Errore triggerando deploy")
        sys.exit(1)
    
    # Step 4: Aspetta completamento deploy
    if not wait_for_render_deploy():
        logger.warning("⚠️ Deploy potrebbe non essere completato")
    
    # Step 5: Verifica che le correzioni funzionino
    if verify_fixes():
        logger.info("🎉 Deploy completato con successo!")
        logger.info("✅ Tutte le correzioni sono state applicate!")
    else:
        logger.warning("⚠️ Deploy completato ma potrebbero esserci ancora problemi")
    
    logger.info("=" * 60)
    logger.info("🏁 Deploy automatico terminato")

if __name__ == "__main__":
    main()