import sqlite3
import os
import pathlib
from datetime import datetime, timedelta, timezone

# Configurazione
DB_NAME = "database.db"
COSTO_MENSILE = 15

# Percorso assoluto per il database
DB_PATH = os.path.join(pathlib.Path(__file__).parent.resolve(), DB_NAME)

def populate_database():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Esempi di liste da aggiungere (modifica con i tuoi dati)
    liste_esistenti = [
        {
            "name": "ListaPremium",
            "owner_id": 123456789,  # Sostituisci con l'ID reale
            "expiration": datetime.now(timezone.utc) + timedelta(days=90)  # 3 mesi
        },
        {
            "name": "ListaFamiglia",
            "owner_id": 987654321,  # Sostituisci con l'ID reale
            "expiration": datetime.now(timezone.utc) + timedelta(days=30)  # 1 mese
        },
        # Aggiungi altre liste secondo necessità
    ]
    
    for lista in liste_esistenti:
        try:
            cur.execute(
                "INSERT INTO lists (name, owner_id, expiration) "
                "VALUES (?, ?, ?)",
                (lista["name"], lista["owner_id"], lista["expiration"].strftime("%Y-%m-%d %H:%M:%S"))
            )
            print(f"✅ Lista '{lista['name']}' aggiunta al database")
        except sqlite3.IntegrityError:
            print(f"⚠️ Lista '{lista['name']}' già esistente, saltata")
    
    conn.commit()
    conn.close()
    print("\nDatabase popolato con successo!")

if __name__ == "__main__":
    populate_database()
