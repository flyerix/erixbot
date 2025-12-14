# Mantenere ErixCast Bot Online 24/7 Gratuitamente

## Strategia Multi-Layer per Uptime Gratuito

### 1. **Configurazione Render (Servizio Principale)**

Il bot è deployato su **Render Piano Gratuito** con le seguenti ottimizzazioni:

#### Configurazione render.yaml:
- `plan: free` - Piano gratuito
- `healthCheckPath: /health` - Endpoint per health check
- `restartPolicy: on_failure` - Riavvio automatico in caso di errore
- `USE_WEBHOOK: true` - Usa webhook invece di polling (più efficiente)

#### Sistema di Ping Interno:
- **3 thread di ping simultanei** con intervalli diversi (5, 7, 10 minuti)
- **Circuit breaker** per gestire fallimenti
- **Auto-restart** dei thread in caso di problemi
- **Database tracking** di tutti i ping per monitoraggio

### 2. **Pinger Esterno (Railway/Heroku)**

Per garantire che Render non vada in sleep, deploy del file `external_pinger.py` su un servizio gratuito separato:

#### Opzioni di Deploy:
1. **Railway** (raccomandato)
2. **Heroku** (piano gratuito limitato)
3. **Fly.io** (piano gratuito)
4. **Vercel** (per funzioni serverless)

#### Come Deployare su Railway:
```bash
# 1. Crea account su railway.app
# 2. Connetti il repository
# 3. Configura variabili d'ambiente:
TARGET_URL=https://erixcastbot.onrender.com
PING_INTERVAL=300
PORT=5000

# 4. Deploy automatico con railway.toml
```

### 3. **Webhook Telegram (Efficienza Massima)**

#### Vantaggi del Webhook vs Polling:
- ✅ **Zero CPU quando inattivo** - il bot riceve solo quando necessario
- ✅ **Risposta istantanea** - nessun delay di polling
- ✅ **Meno risorse** - non fa richieste continue a Telegram
- ✅ **Mantiene Render attivo** - ogni messaggio è una richiesta HTTP

#### Configurazione Webhook:
```python
# Il webhook è configurato automaticamente nel bot
# Endpoint: https://tuobot.onrender.com/webhook/TOKEN_PARTE_1
```

### 4. **Ottimizzazioni per Piano Gratuito Render**

#### Limiti Render Free:
- **512MB RAM** - ottimizzato con pool database ridotto
- **Sleep dopo 15min inattività** - prevenuto con ping system
- **750 ore/mese** - sufficiente per 24/7 con ottimizzazioni

#### Ottimizzazioni Implementate:
```yaml
# Database connection pool ridotto
DATABASE_POOL_SIZE: 3
DATABASE_MAX_OVERFLOW: 2

# Worker Gunicorn ottimizzato
--workers 1 --threads 2

# Memory management
- Cleanup automatico ogni 30 minuti
- Garbage collection ottimizzato
- Cache con TTL per ridurre query DB
```

### 5. **Monitoraggio e Alerting**

#### Sistema di Monitoraggio:
- **UptimePing table** - traccia tutti i ping nel database
- **Logs strutturati** - per debugging e monitoraggio
- **Health check endpoint** - `/health`, `/ping`, `/status`
- **Statistiche real-time** - uptime percentage, response times

#### Alert agli Admin:
```python
# Gli admin ricevono notifiche per:
- Servizio down per più di 10 minuti
- Errori critici del database
- Memory usage > 80%
- Fallimenti consecutivi del ping system
```

### 6. **Backup e Resilienza**

#### Backup Automatici:
- **Backup giornalieri** alle 6:00 e 18:00
- **Retention** - ultimi 10 backup
- **Export dati utente** su richiesta

#### Recovery Automatico:
- **Auto-restart** in caso di crash
- **Circuit breaker** per prevenire cascade failures
- **Graceful shutdown** con cleanup delle risorse

## Setup Completo (Passo-Passo)

### Passo 1: Deploy Bot su Render
1. Fork questo repository
2. Crea account su render.com
3. Connetti il repository
4. Configura le variabili d'ambiente:
   ```
   TELEGRAM_BOT_TOKEN=il_tuo_token
   DATABASE_URL=postgresql://...
   OPENAI_API_KEY=sk-...
   ADMIN_IDS=123456789
   WEBHOOK_URL=https://tuobot.onrender.com
   ```
5. Deploy automatico

### Passo 2: Deploy Pinger Esterno su Railway
1. Crea nuovo progetto su railway.app
2. Connetti lo stesso repository
3. Configura variabili:
   ```
   TARGET_URL=https://tuobot.onrender.com
   PING_INTERVAL=300
   ```
4. Deploy con `external_pinger.py`

### Passo 3: Configurazione Webhook Telegram
Il webhook si configura automaticamente al primo avvio del bot.

### Passo 4: Monitoraggio
- Controlla logs su Render dashboard
- Usa `/admin_health` nel bot per statistiche
- Monitora uptime su Railway dashboard

## Costi Totali: €0/mese

- ✅ **Render Free**: 750 ore/mese (sufficiente per 24/7)
- ✅ **Railway Free**: 500 ore/mese (più che sufficiente per pinger)
- ✅ **Database**: PostgreSQL gratuito su Render
- ✅ **Telegram Bot API**: Gratuita
- ✅ **OpenAI API**: Pay-per-use (costo minimo ~€1-2/mese)

## Risultato Finale

🎯 **Bot online 24/7 con uptime >99%**
💰 **Costo totale: ~€1-2/mese (solo OpenAI)**
🔧 **Manutenzione: Zero**
📊 **Monitoraggio completo incluso**

## Troubleshooting

### Bot va in sleep nonostante i ping:
1. Verifica che il pinger esterno sia attivo
2. Controlla logs per errori nei ping thread
3. Verifica che il webhook riceva traffico

### Pinger esterno non funziona:
1. Controlla che TARGET_URL sia corretto
2. Verifica che Railway/Heroku non sia in sleep
3. Controlla logs del pinger per errori

### Database errors:
1. Verifica DATABASE_URL
2. Controlla connection pool settings
3. Verifica che PostgreSQL sia attivo su Render

Con questa configurazione, il bot rimarrà online 24/7 completamente gratis! 🚀