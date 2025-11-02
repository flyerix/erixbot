# ErixCast Bot 🤖

> Un bot Telegram avanzato per la gestione di liste IPTV/Streaming con assistenza AI integrata, sistema ticket e notifiche automatiche.

[![Deploy on Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat&logo=render)](https://render.com)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat&logo=python)](https://python.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot_API-0088CC?style=flat&logo=telegram)](https://core.telegram.org/bots/api)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--3.5-412991?style=flat&logo=openai)](https://openai.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13+-336791?style=flat&logo=postgresql)](https://postgresql.org)

## 📋 Descrizione del Progetto

ErixCast Bot è una soluzione completa per la gestione di liste di contenuti streaming (IPTV, VOD, ecc.) attraverso Telegram. Il bot offre un'interfaccia intuitiva per utenti e amministratori, con funzionalità avanzate come assistenza AI automatica, sistema di ticket, notifiche di scadenza e backup automatico.

### 🎯 Funzionalità Principali

#### 👤 Per gli Utenti
- **🔍 Ricerca Liste**: Cerca e visualizza dettagli completi delle liste disponibili
- **🎫 Sistema Ticket**: Apri ticket di assistenza con risposte AI automatiche
- **🔔 Notifiche Scadenza**: Imposta promemoria personalizzati per le scadenze
- **📊 Dashboard Personale**: Visualizza statistiche e stato delle tue liste
- **🔄 Rinnovi**: Richiedi rinnovi direttamente tramite bot

#### 👑 Per gli Amministratori
- **⚙️ Pannello Admin**: Gestione completa di liste, ticket e utenti
- **📋 CRUD Liste**: Crea, modifica, elimina e monitora tutte le liste
- **🎫 Gestione Ticket**: Monitora e rispondi ai ticket degli utenti
- **📊 Statistiche**: Dashboard con metriche dettagliate
- **🔄 Gestione Rinnovi**: Approva/rifiuta richieste di rinnovo
- **💾 Backup Automatico**: Backup giornaliero del database

#### 🤖 Intelligenza Artificiale
- **AI Assistant**: Risposte automatiche ai problemi comuni
- **Escalation Smart**: Passaggio automatico ad admin per problemi complessi
- **Supporto Multilingua**: Risposte sempre in italiano


###  Deploy su Render

1. **Connetti Repository**: Collega il tuo repo GitHub a Render
2. **Configura Servizio**:
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app/main.py`
3. **Aggiungi Secrets**: Configura tutte le variabili d'ambiente
4. **Deploy**: Render gestirà automaticamente il deploy

## 📖 Utilizzo

### Comandi Principali

| Comando | Descrizione |
|---------|-------------|
| `/start` | Avvia il bot e mostra il menu principale |
| `/help` | Guida completa e comandi disponibili |
| `/status` | Stato personale (ticket, notifiche, attività) |
| `/dashboard` | Riepilogo completo del profilo utente |
| `/renew` | Menu rinnovi liste |
| `/support` | Menu assistenza clienti |

### Flusso Utente Tipico

1. **Avvio**: `/start` → Menu principale
2. **Ricerca**: Clicca "🔍 Cerca Lista" → Inserisci nome lista
3. **Azioni**: Rinnova, elimina o imposta notifiche
4. **Supporto**: Apri ticket se necessario
5. **Monitoraggio**: Ricevi notifiche automatiche

### Pannello Admin

Accedi al pannello admin dal menu principale (solo per ID admin configurati):

- **📋 Gestisci Liste**: CRUD completo delle liste
- **🎫 Gestisci Ticket**: Monitora e rispondi ai ticket
- **🔄 Richieste Rinnovo**: Approva/rifiuta rinnovi
- **📊 Statistiche**: Metriche di utilizzo
- **💾 Backup**: Download backup database


## 📊 Monitoraggio e Uptime

### Health Checks
- **Endpoint**: `GET /` e `GET /ping`
- **Render Integration**: Automatic health monitoring
- **Keep-alive System**: Ping interno ogni 5 minuti


### Uptime Garantito 24/7
- Sistema keep-alive interno
- Monitor esterno opzionale
- Gestione errori e restart automatici
- Database connection checks


## 📄 Licenza

Questo progetto è distribuito sotto licenza MIT.


---

**⭐ Se questo progetto ti è utile, metti un like!**

Creato con ❤️ per la comunità streaming italiana.
