import sqlite3
import os
import pathlib
from datetime import datetime, timedelta, timezone

# Configurazione
DB_NAME = "database.db"
DB_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), DB_NAME)

def populate_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("Inserimento liste esistenti nel database\n")
    
    while True:
        print("\n" + "="*50)
        list_name = input("Nome lista (o 'exit' per terminare): ").strip()
        if list_name.lower() == 'exit':
            break
            
        owner_id = input("ID proprietario: ").strip()
        if not owner_id.isdigit():
            print("❌ ID deve essere un numero!")
            continue
            
        mesi = input("Mesi rimanenti: ").strip()
        if not mesi.isdigit():
            print("❌ Mesi deve essere un numero!")
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
