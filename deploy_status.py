#!/usr/bin/env python3
"""
🚀 Deploy Status Monitor
Monitora lo stato del deploy automatico su Render
"""

import requests
import time
import sys
from datetime import datetime

def check_service_health(url="https://erixcastbot.onrender.com"):
    """Controlla lo stato del servizio"""
    endpoints = [
        "/health",
        "/ping", 
        "/status"
    ]
    
    results = {}
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{url}{endpoint}", timeout=30)
            results[endpoint] = {
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "response_time": response.elapsed.total_seconds()
            }
        except Exception as e:
            results[endpoint] = {
                "status_code": None,
                "success": False,
                "error": str(e)
            }
    
    return results

def monitor_deploy(max_attempts=15, delay=60):
    """Monitora il deploy fino al completamento"""
    print("🚀 Monitoraggio Deploy Automatico")
    print("=" * 50)
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n🔄 Tentativo {attempt}/{max_attempts} - {datetime.now().strftime('%H:%M:%S')}")
        
        results = check_service_health()
        
        # Controlla se almeno health è OK
        health_ok = results.get("/health", {}).get("success", False)
        
        if health_ok:
            print("✅ DEPLOY COMPLETATO CON SUCCESSO!")
            print("\n📊 Stato Endpoints:")
            for endpoint, result in results.items():
                status = "✅" if result.get("success") else "❌"
                code = result.get("status_code", "N/A")
                time_ms = int(result.get("response_time", 0) * 1000)
                print(f"  {status} {endpoint}: {code} ({time_ms}ms)")
            
            return True
        else:
            print("⏳ Deploy ancora in corso...")
            for endpoint, result in results.items():
                status = "✅" if result.get("success") else "❌"
                error = result.get("error", "")
                print(f"  {status} {endpoint}: {error}")
            
            if attempt < max_attempts:
                print(f"⏱️ Prossimo controllo tra {delay} secondi...")
                time.sleep(delay)
    
    print("\n❌ DEPLOY TIMEOUT - Controllo manuale necessario")
    return False

if __name__ == "__main__":
    success = monitor_deploy()
    sys.exit(0 if success else 1)