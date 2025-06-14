import sqlite3
import os
import pathlib
import json
from datetime import datetime, timedelta, timezone

# Configurazione
DB_NAME = "database.db"
DB_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), DB_NAME)

def init_db():
    """Crea le tabelle necessarie se non esistono"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Tabella lists
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lists (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        owner_id INTEGER,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expiration TIMESTAMP,
        last_reminder TIMESTAMP
    )
    """)
    
    # Tabella requests
    cur.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY,
        list_name TEXT,
        user_id INTEGER,
        action TEXT,
        months INTEGER,
        total_cost REAL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Tabella reports
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY,
        list_name TEXT,
        user_id INTEGER,
        problem_details TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Tabelle create con successo")

def populate_database():
    # Prima crea le tabelle
    init_db()
    
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
