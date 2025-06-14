import sqlite3
import os
import pathlib
from datetime import datetime, timedelta, timezone
import json

# Configurazione
DB_NAME = "database.db"
DB_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), DB_NAME)

def populate_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("Inserimento liste esistenti nel database\n")
    
    # Leggi le liste dalla variabile d'ambiente
    lists_json = os.getenv("EXISTING_LISTS")
    if not lists_json:
        print("❌ Variabile d'ambiente EXISTING_LISTS non trovata")
        return
    
    try:
        lists = json.loads(lists_json)
    except json.JSONDecodeError as e:
        print(f"❌ Errore nel parsing di EXISTING_LISTS: {e}")
        return
    
    print(f"Trovate {len(lists)} liste da inserire")
    
    for lista in lists:
        list_name = lista.get("name")
        owner_id = lista.get("owner_id")
        mesi = lista.get("mesi")
        
        if not list_name or not owner_id or not mesi:
            print(f"❌ Dati mancanti per una lista: {lista}")
            continue
            
        # Calcola scadenza
        exp_date = datetime.now(timezone.utc) + timedelta(days=int(mesi)*30)
        exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            cur.execute(
                "INSERT INTO lists (name, owner_id, expiration) "
                "VALUES (?, ?, ?)",
                (list_name, int(owner_id), exp_str)
            )
            print(f"✅ Lista '{list_name}' aggiunta - Scadenza: {exp_date.strftime('%d/%m/%Y')}")
        except sqlite3.IntegrityError:
            print(f"❌ Lista '{list_name}' già esistente!")
    
    conn.commit()
    conn.close()
    print("\nDatabase popolato con successo!")

if __name__ == "__main__":
    populate_database()
