# ErixCast Bot 🤖

Bot Telegram per gestire liste con supporto AI e pannello admin.

[![Deploy on Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot_API-0088CC?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)

## Cosa fa

- **🔍 Ricerca liste**: Trova liste per nome
- **🎫 Sistema ticket**: Supporto con AI automatica
- **🔔 Notifiche**: Promemoria scadenza personalizzati
- **👑 Pannello admin**: Gestione liste e ticket
- **📊 Dashboard**: Statistiche e monitoraggio

## Deploy semplice

### Su Render (raccomandato)

1. Clicca il pulsante deploy
2. Configura le variabili d'ambiente
3. Il bot è online!

### Variabili richieste

```bash
TELEGRAM_BOT_TOKEN=il_tuo_token_bot
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
ADMIN_IDS=123456789
```

## Come usare

### Per utenti normali
- `/start` - Menu principale
- `/help` - Guida completa
- Cerca liste per nome
- Apri ticket di supporto
- Ricevi notifiche scadenza

### Per amministratori
- Pannello admin completo
- Gestione liste e ticket
- Statistiche e monitoraggio
- Backup automatici

## Deploy

### Su Render
1. Fork questo repo
2. Connetti a Render
3. Configura le variabili d'ambiente
4. Deploy!

### Configurazione minima

```bash
TELEGRAM_BOT_TOKEN=il_token_del_bot
DATABASE_URL=url_database_postgresql
OPENAI_API_KEY=chiave_openai
ADMIN_IDS=id_admin_separati_da_virgola
```

## Comandi principali

| Comando | Descrizione |
|---------|-------------|
| `/start` | Menu principale con statistiche |
| `/help` | Guida completa |
| `/status` | Stato personale (liste, ticket) |
| `/dashboard` | Dashboard dettagliato |
| `/renew` | Rinnova una lista |
| `/support` | Apri ticket supporto |

## Admin features

- Gestione completa delle liste
- Monitoraggio ticket
- Statistiche sistema
- Backup automatici
- Notifiche agli utenti

## Tecnologie

- Python + Telegram Bot API
- PostgreSQL database
- OpenAI GPT per AI
- Deploy su Render

## Licenza

MIT License - sentiti libero di usarlo e modificarlo!


