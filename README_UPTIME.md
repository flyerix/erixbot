# Guida per Mantenere il Bot Sempre Attivo su Render (24/7)

## 🎯 Obiettivo
Questa guida spiega come configurare il bot Telegram per rimanere sempre attivo e disponibile 24 ore su 24, 7 giorni su 7, gratuitamente utilizzando Render.

## 📋 Modifiche Implementate

### 1. Server Flask per Health Check
- **File modificato:** `app/main.py`
- **Funzionalità:** Server HTTP Flask che risponde alle richieste di health check di Render
- **Endpoint:**
  - `/` - Health check principale (restituisce JSON con status)
  - `/ping` - Endpoint semplice per ping esterni

### 2. Sistema Keep-Alive Interno
- **File modificato:** `app/bot.py`
- **Funzionalità:** Thread separato che effettua ping interni ogni 5 minuti
- **Vantaggi:** Mantiene attivo il servizio internamente

### 3. Monitor Uptime Esterno
- **File creato:** `uptime_monitor.py`
- **Funzionalità:** Script Python per pingare il servizio da un host esterno
- **Utilizzo:** Da eseguire su un servizio gratuito come Railway, Heroku, o VPS

### 4. Configurazione Render Ottimizzata
- **File modificato:** `render.yaml`
- **Miglioramenti:** Timeout e delay ottimizzati per stabilità

## 🚀 Come Utilizzare

### Opzione 1: Solo con Render (Raccomandato)
1. **Deploy su Render** con le modifiche attuali
2. **Configura variabili d'ambiente:**
   - `STARTUP_DELAY=60` (già presente)
   - `PORT=10000` (già presente)
3. **Il bot rimarrà attivo** grazie al sistema interno di keep-alive

### Opzione 2: Con Monitor Esterno (Massima Affidabilità)
1. **Deploy del bot su Render** come sopra
2. **Deploy del monitor uptime** su un servizio gratuito:
   - **Railway:** Crea un nuovo progetto, carica `uptime_monitor.py`
   - **Heroku:** Crea app e deploya il monitor
   - **VPS gratuito:** Esegui lo script con cron job

3. **Configura variabili per il monitor:**
   ```
   RENDER_URL=https://erixcastbot.onrender.com
   PING_INTERVAL=300
   ```

## 📊 Monitoraggio dello Status

### Tramite Render Dashboard
- Vai su https://dashboard.render.com
- Seleziona il tuo servizio
- Controlla la sezione "Events" per vedere i restart
- Il servizio dovrebbe rimanere "Active" continuamente

### Tramite Endpoint Health Check
- `https://erixcastbot.onrender.com/` - Status JSON
- `https://erixcastbot.onrender.com/ping` - Ping semplice

### Log del Bot
- Controlla i log su Render per messaggi di keep-alive
- Cerca: "✅ Internal health check passed"
- Cerca: "🌐 External ping successful"

## 🔧 Troubleshooting

### Il Bot si Addormenta
**Sintomi:** Il bot non risponde ai messaggi
**Soluzioni:**
1. Controlla se il servizio è attivo su Render
2. Verifica i log per errori
3. Riavvia manualmente se necessario

### Errori di Connessione
**Sintomi:** Errori di rete nei log
**Soluzioni:**
1. Aumenta i timeout in `render.yaml`
2. Verifica la stabilità della connessione internet
3. Implementa retry logic se necessario

### Conflitti di Istanza
**Sintomi:** "Conflict error" nei log
**Soluzioni:**
1. Assicurati che ci sia solo una istanza attiva
2. Aumenta `STARTUP_DELAY` se necessario
3. Controlla che non ci siano deploy concorrenti

## 💡 Suggerimenti per Massima Uptime

1. **Monitora regolarmente** i log di Render
2. **Imposta notifiche** per quando il servizio va giù
3. **Mantieni aggiornato** il codice e le dipendenze
4. **Testa periodicamente** la funzionalità del bot
5. **Backup regolari** dei dati (già implementato)

## 🎉 Risultato Atteso

Con queste modifiche, il bot dovrebbe:
- ✅ Rimane attivo 24/7 su Render free tier
- ✅ Gestire correttamente i restart automatici
- ✅ Rispondere sempre ai messaggi degli utenti
- ✅ Mantenere la stabilità anche con carichi variabili
- ✅ Loggare adeguatamente tutti gli eventi importanti

## 📞 Supporto

Se riscontri problemi:
1. Controlla i log su Render
2. Verifica la configurazione delle variabili d'ambiente
3. Testa gli endpoint health check manualmente
4. Contatta il supporto tecnico se necessario