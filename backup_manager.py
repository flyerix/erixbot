import os
import json
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import asyncio

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, database_url):
        self.database_url = database_url
        self.backup_dir = "backups"
        
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def get_db_connection(self):
        try:
            conn = psycopg2.connect(self.database_url)
            return conn
        except Exception as e:
            logger.error(f"Errore connessione database per backup: {e}")
            raise

    async def create_backup(self):
        try:
            conn = self.get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            backup_data = {
                'metadata': {
                    'timestamp': datetime.now().isoformat(),
                    'version': '2.0',
                    'tables': ['users', 'lists', 'tickets', 'ticket_messages'],
                    'features': ['cache', 'rate_limiting', 'smart_notifications', 'templates']
                },
                'data': {}
            }
            
            # Backup tabella users
            cur.execute("SELECT * FROM users")
            backup_data['data']['users'] = [dict(row) for row in cur.fetchall()]
            
            # Backup tabella lists
            cur.execute("SELECT * FROM lists")
            backup_data['data']['lists'] = [dict(row) for row in cur.fetchall()]
            
            # Backup tabella tickets
            cur.execute("SELECT * FROM tickets")
            backup_data['data']['tickets'] = [dict(row) for row in cur.fetchall()]
            
            # Backup tabella ticket_messages
            cur.execute("SELECT * FROM ticket_messages")
            backup_data['data']['ticket_messages'] = [dict(row) for row in cur.fetchall()]
            
            cur.close()
            conn.close()
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"backup_{timestamp}.json"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Backup creato con successo: {backup_path}")
            
            self._cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Errore nella creazione del backup: {e}")
            return None

    def _cleanup_old_backups(self):
        try:
            backup_files = []
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('backup_') and filename.endswith('.json'):
                    file_path = os.path.join(self.backup_dir, filename)
                    if os.path.exists(file_path):
                        backup_files.append((file_path, os.path.getctime(file_path)))
            
            backup_files.sort(key=lambda x: x[1], reverse=True)
            
            for file_path, _ in backup_files[7:]:
                try:
                    os.remove(file_path)
                    logger.info(f"Backup vecchio eliminato: {file_path}")
                except Exception as e:
                    logger.error(f"Errore nell'eliminazione backup {file_path}: {e}")
                    
        except Exception as e:
            logger.error(f"Errore nella pulizia backup vecchi: {e}")

    async def restore_backup(self, backup_file_path):
        try:
            if not os.path.exists(backup_file_path):
                logger.error(f"File backup non trovato: {backup_file_path}")
                return False
                
            with open(backup_file_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            conn = self.get_db_connection()
            cur = conn.cursor()
            
            cur.execute("SET session_replication_role = 'replica';")
            
            tables = ['ticket_messages', 'tickets', 'lists', 'users']
            for table in tables:
                cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
            
            for user in backup_data['data']['users']:
                cur.execute("""
                    INSERT INTO users (id, telegram_id, username, full_name, is_admin, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    user['id'], user['telegram_id'], user['username'], 
                    user['full_name'], user['is_admin'], user['created_at']
                ))
            
            for list_item in backup_data['data']['lists']:
                cur.execute("""
                    INSERT INTO lists (id, name, cost, expiration_date, notes, created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    list_item['id'], list_item['name'], list_item['cost'],
                    list_item['expiration_date'], list_item['notes'],
                    list_item['created_by'], list_item['created_at']
                ))
            
            for ticket in backup_data['data']['tickets']:
                cur.execute("""
                    INSERT INTO tickets (id, user_id, subject, status, is_ai_responded, created_at, closed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    ticket['id'], ticket['user_id'], ticket['subject'],
                    ticket['status'], ticket['is_ai_responded'],
                    ticket['created_at'], ticket.get('closed_at')
                ))
            
            for message in backup_data['data']['ticket_messages']:
                cur.execute("""
                    INSERT INTO ticket_messages (id, ticket_id, user_id, message, is_from_admin, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    message['id'], message['ticket_id'], message['user_id'],
                    message['message'], message['is_from_admin'], message['created_at']
                ))
            
            cur.execute("SET session_replication_role = 'origin';")
            
            conn.commit()
            cur.close()
            conn.close()
            
            logger.info(f"Backup ripristinato con successo da: {backup_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Errore nel ripristino del backup: {e}")
            return False

    async def get_backup_info(self):
        try:
            backup_files = []
            if not os.path.exists(self.backup_dir):
                return []
                
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('backup_') and filename.endswith('.json'):
                    file_path = os.path.join(self.backup_dir, filename)
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path) / 1024
                        created_time = datetime.fromtimestamp(os.path.getctime(file_path))
                        
                        backup_files.append({
                            'filename': filename,
                            'path': file_path,
                            'size_kb': round(file_size, 2),
                            'created': created_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'age_days': (datetime.now() - created_time).days
                        })
            
            return sorted(backup_files, key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            logger.error(f"Errore nel recupero info backup: {e}")
            return []

# Istanza globale del backup manager
backup_manager = BackupManager(os.getenv('DATABASE_URL'))

# Funzioni di utilità
async def create_backup():
    return await backup_manager.create_backup()

async def restore_backup(backup_file_path):
    return await backup_manager.restore_backup(backup_file_path)

async def get_backup_info():
    return await backup_manager.get_backup_info()

# Job per backup automatico
async def backup_job(context):
    try:
        logger.info("Esecuzione backup automatico...")
        backup_file = await backup_manager.create_backup()
        
        if backup_file:
            from bot import ADMIN_IDS
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_document(
                        chat_id=admin_id,
                        document=open(backup_file, 'rb'),
                        filename=f"auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        caption="🤖 Backup automatico completato"
                    )
                except Exception as e:
                    logger.error(f"Errore nell'invio backup all'admin {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Errore in backup_job: {e}")
