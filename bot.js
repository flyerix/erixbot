const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');
const path = require('path');
const https = require('https');

const TOKEN = process.env.TELEGRAM_TOKEN;
const DATA_FILE = path.join(__dirname, 'data.json');
const bot = new TelegramBot(TOKEN, { polling: true });
const BASE_TIMEZONE = 'Europe/Rome';
const ADMIN_ID = 691735614;

// ===== UTILS =====
function loadData() {
  if (!fs.existsSync(DATA_FILE)) return [];
  return JSON.parse(fs.readFileSync(DATA_FILE));
}

function saveData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

function nowISO() {
  return new Date().toISOString();
}

function parseDateISO(str) {
  const parts = str.trim().split('-');
  if (parts.length !== 3) throw new Error('📅 Data non valida! Usa il formato AAAA-MM-GG');
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  if (isNaN(d.getTime())) throw new Error('📅 Data non valida! Usa il formato AAAA-MM-GG');
  return d;
}

function formatEuro(amount) {
  const n = Number(amount);
  if (isNaN(n)) return String(amount);
  return n.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
}

function isAdmin(msg) {
  return msg.from && msg.from.id === ADMIN_ID;
}

// ===== STATE FOR INFO REQUEST =====
const userStates = {};

// ===== KEYBOARD OPTIONS =====
function mainMenu(isAdminUser = false) {
  const buttons = [];
  if (isAdminUser) {
    buttons.push([
      { text: "➕ Aggiungi", callback_data: "add" },
      { text: "📖 Lista", callback_data: "list" }
    ]);
    buttons.push([
      { text: "🔁 Rinnova", callback_data: "renew" },
      { text: "🗑 Elimina", callback_data: "cancel" }
    ]);
    buttons.push([
      { text: "⏳ Scadenze", callback_data: "next" }
    ]);
  }
  buttons.push([
    { text: "🔎 Info abbonamento", callback_data: "info" },
    { text: "🛰 Stato servizio", callback_data: "status" }
  ]);
  buttons.push([
    { text: "❓ Aiuto", callback_data: "help" }
  ]);
  return {
    reply_markup: {
      inline_keyboard: buttons
    }
  };
}

// ====== START / MAIN MENU ======
function getAdminTag(msg) {
  return isAdmin(msg) ? "👑 [ADMIN] " : "";
}

bot.onText(/^\/start/, (msg) => {
  const tag = getAdminTag(msg);
  bot.sendMessage(
    msg.chat.id,
    `${tag}🚀 Benvenuto ${msg.from.first_name}!\n\nSono <b>AbboBot</b> 🤖\nGestisco i tuoi abbonamenti in modo semplice e colorato!\n\nCosa vuoi fare oggi? Scegli una funzione:`,
    { ...mainMenu(isAdmin(msg)), parse_mode: "HTML" }
  );
});

bot.onText(/^\/help/, (msg) => {
  const tag = getAdminTag(msg);
  bot.sendMessage(
    msg.chat.id,
    `${tag}❓ <b>Ecco cosa posso fare:</b>
➕ <b>Aggiungi</b> — Inserisci un nuovo abbonamento
📖 <b>Lista</b> — Visualizza i tuoi abbonamenti
🔁 <b>Rinnova</b> — Aggiorna la scadenza
🗑 <b>Elimina</b> — Cancella un abbonamento
⏳ <b>Scadenze</b> — Vedi le scadenze in arrivo
🔎 <b>Info abbonamento</b> — Dettagli di uno specifico abbonamento
🛰 <b>Stato servizio</b> — Stato IPTV
❓ <b>Aiuto</b> — Spiega i comandi

<b>Tip:</b> Usa la tastiera qui sotto per scegliere più velocemente!`,
    { ...mainMenu(isAdmin(msg)), parse_mode: "HTML" }
  );
});

// ====== STATUS ======
bot.onText(/^\/status/, (msg) => {
  const tag = getAdminTag(msg);
  checkServiceStatus().then(status => {
    if (status === "ONLINE") {
      bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è ONLINE!</b> ✅`, { parse_mode: "HTML" });
    } else {
      bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è OFFLINE!</b> ❌`, { parse_mode: "HTML" });
    }
  }).catch(() => {
    bot.sendMessage(msg.chat.id, `${tag}⚠️ Impossibile verificare lo stato del servizio.`, { parse_mode: "HTML" });
  });
});

function checkServiceStatus() {
  return new Promise((resolve, reject) => {
    https.get("https://miglioriptvreseller.xyz/", (res) => {
      if (res.statusCode === 200) {
        resolve("ONLINE");
      } else {
        resolve("OFFLINE");
      }
    }).on('error', () => {
      resolve("OFFLINE");
    });
  });
}

// ====== CALLBACK QUERY HANDLER (bottoni) ======
bot.on('callback_query', async query => {
  const msg = query.message;
  const userId = query.from.id;
  const tag = getAdminTag(query);

  switch (query.data) {
    case "add":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      userStates[userId] = { awaitingAdd: true };
      bot.sendMessage(msg.chat.id, `${tag}➕ <b>Scrivi i dati per aggiungere:</b>\n<code>Nome 9.99 EUR 2025-10-31 [note]</code>`, { parse_mode: "HTML" });
      break;
    case "list":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      sendList(msg, userId, tag);
      break;
    case "renew":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      userStates[userId] = { awaitingRenew: true };
      bot.sendMessage(msg.chat.id, `${tag}🔁 <b>Scrivi:</b>\n<code>Nome 2026-01-31</code>`, { parse_mode: "HTML" });
      break;
    case "cancel":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      userStates[userId] = { awaitingCancel: true };
      bot.sendMessage(msg.chat.id, `${tag}🗑 <b>Scrivi il nome dell'abbonamento da eliminare:</b>`, { parse_mode: "HTML" });
      break;
    case "next":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      sendNext(msg, userId, tag);
      break;
    case "info":
      userStates[userId] = { awaitingInfo: true };
      bot.sendMessage(msg.chat.id, `${tag}🔎 <b>Scrivi il nome dell'abbonamento di cui vuoi vedere le info:</b>`, { parse_mode: "HTML" });
      break;
    case "status":
      checkServiceStatus().then(status => {
        if (status === "ONLINE") {
          bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è ONLINE!</b> ✅`, { parse_mode: "HTML" });
        } else {
          bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è OFFLINE!</b> ❌`, { parse_mode: "HTML" });
        }
      });
      break;
    case "help":
      bot.sendMessage(msg.chat.id, `${tag}❓ <b>Ecco cosa posso fare:</b>
➕ <b>Aggiungi</b> — Inserisci un nuovo abbonamento
📖 <b>Lista</b> — Visualizza i tuoi abbonamenti
🔁 <b>Rinnova</b> — Aggiorna la scadenza
🗑 <b>Elimina</b> — Cancella un abbonamento
⏳ <b>Scadenze</b> — Vedi le scadenze in arrivo
🔎 <b>Info abbonamento</b> — Dettagli di uno specifico abbonamento
🛰 <b>Stato servizio</b> — Stato IPTV
❓ <b>Aiuto</b> — Spiega i comandi

<b>Tip:</b> Usa la tastiera qui sotto per scegliere più velocemente!`,
        { ...mainMenu(isAdmin(query)), parse_mode: "HTML" }
      );
      break;
  }
  bot.answerCallbackQuery(query.id);
});

// ====== GESTIONE RISPOSTE UTENTE PER STATI ======
bot.on('message', (msg) => {
  const userId = msg.from.id;
  const tag = getAdminTag(msg);

  // ADD
  if (userStates[userId] && userStates[userId].awaitingAdd) {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questa funzione.");
      delete userStates[userId];
      return;
    }
    const args = msg.text.split(' ').filter(Boolean);
    if (args.length < 4) {
      bot.sendMessage(msg.chat.id, `❗ <b>Formato errato!</b>\nScrivi:\n<code>Nome 9.99 EUR 2025-10-31 [note]</code>`, { parse_mode: "HTML" });
      return;
    }
    const [name, cost, currency, dateISO, ...noteArr] = args;
    let date;
    try {
      date = parseDateISO(dateISO);
    } catch (e) {
      bot.sendMessage(msg.chat.id, "📅 <b>Data non valida!</b> Usa il formato AAAA-MM-GG", { parse_mode: "HTML" });
      return;
    }
    const note = noteArr.join(' ');
    const username = msg.from.username || msg.from.first_name || '';
    const data = loadData();
    data.push({
      userId,
      username,
      name,
      cost: Number(cost),
      currency,
      dateISO,
      note,
      createdAt: nowISO(),
      updatedAt: nowISO()
    });
    saveData(data);
    bot.sendMessage(msg.chat.id, `✅ <b>${name}</b> aggiunto!
💸 Costo: ${formatEuro(cost)} ${currency}
📅 Scadenza: ${dateISO}
${note ? '📝 Note: ' + note : ''}
`, { parse_mode: 'HTML' });
    delete userStates[userId];
    return;
  }

  // RENEW
  if (userStates[userId] && userStates[userId].awaitingRenew) {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questa funzione.");
      delete userStates[userId];
      return;
    }
    const args = msg.text.split(' ').filter(Boolean);
    if (args.length < 2) {
      bot.sendMessage(msg.chat.id, `❗ <b>Formato errato!</b>\nScrivi:\n<code>Nome 2026-01-31</code>`, { parse_mode: "HTML" });
      return;
    }
    const [name, dateISO] = args;
    let date;
    try {
      date = parseDateISO(dateISO);
    } catch (e) {
      bot.sendMessage(msg.chat.id, "📅 <b>Data non valida!</b> Usa il formato AAAA-MM-GG", { parse_mode: "HTML" });
      return;
    }
    const data = loadData();
    let updated = false;
    data.forEach((x) => {
      if (x.userId === userId && x.name === name) {
        x.dateISO = dateISO;
        x.updatedAt = nowISO();
        updated = true;
      }
    });
    saveData(data);
    bot.sendMessage(msg.chat.id, updated
      ? `🔁 <b>${name}</b> rinnovato fino al ${dateISO} 🎉`
      : `❌ <b>${name}</b> non trovato!`,
      { parse_mode: 'HTML' });
    delete userStates[userId];
    return;
  }

  // CANCEL
  if (userStates[userId] && userStates[userId].awaitingCancel) {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questa funzione.");
      delete userStates[userId];
      return;
    }
    const name = msg.text.trim();
    if (!name) {
      bot.sendMessage(msg.chat.id, `❗ <b>Scrivi il nome!</b>`, { parse_mode: "HTML" });
      return;
    }
    const data = loadData();
    const before = data.length;
    const newData = data.filter(x => !(x.userId === userId && x.name === name));
    saveData(newData);
    bot.sendMessage(msg.chat.id,
      before > newData.length
        ? `🗑 <b>${name}</b> eliminato!`
        : `❌ <b>${name}</b> non trovato!`, { parse_mode: 'HTML' });
    delete userStates[userId];
    return;
  }

  // INFO (per tutti)
  if (userStates[userId] && userStates[userId].awaitingInfo) {
    const abboName = msg.text.trim();
    const data = loadData().filter(x => x.userId === userId && x.name.toLowerCase() === abboName.toLowerCase());

    if (!data.length) {
      bot.sendMessage(msg.chat.id, `❌ <b>Nessun abbonamento trovato con nome "${abboName}"</b>!`, { parse_mode: 'HTML' });
    } else {
      data.forEach(r => {
        bot.sendMessage(msg.chat.id, `🔎 <b>${r.name}</b>
💸 Costo: ${formatEuro(r.cost)} ${r.currency}
📅 Scadenza: ${r.dateISO}
${r.note ? '📝 Note: ' + r.note : ''}
🆕 Aggiunto il: ${r.createdAt.substring(0,10)}`, { parse_mode: 'HTML' });
      });
    }
    delete userStates[userId];
    return;
  }

  // Messaggi di default solo se non sono callback
  if (!msg.text.startsWith('/') && !msg.text.startsWith('➕') && !msg.text.startsWith('📖') && !msg.text.startsWith('🔁') && !msg.text.startsWith('🗑') && !msg.text.startsWith('⏳') && !msg.text.startsWith('🔎') && !msg.text.startsWith('🛰') && !msg.text.startsWith('❓')) {
    return;
  }
  const known = ['/start','/help','/add','/list','/renew','/cancel','/next','/info','/status'];
  if (!known.some(cmd => msg.text.startsWith(cmd))) {
    bot.sendMessage(msg.chat.id, `🤔 <b>Comando non riconosciuto!</b>\nUsa la tastiera qui sotto 👇`, { ...mainMenu(isAdmin(msg)), parse_mode: "HTML" });
  }
});

// ====== ADMIN-ONLY COMMANDS ======
function sendList(msg, userId, tag) {
  const data = loadData().filter(x => x.userId === userId);
  if (!data.length) {
    bot.sendMessage(msg.chat.id, `${tag}📖 <b>Nessun abbonamento registrato!</b>`, { ...mainMenu(true), parse_mode: "HTML" });
    return;
  }
  const out = data.map(r => {
    let days = 0;
    try {
      const d = parseDateISO(r.dateISO);
      days = Math.ceil((d - new Date()) / (1000*60*60*24));
    } catch { days = '?'; }
    const status = days < 0 ? '⛔ Scaduto' : days <= 7 ? '⚠ In scadenza' : '✅ Attivo';
    return `• <b>${r.name}</b> — ${formatEuro(r.cost)} ${r.currency} — scade il ${r.dateISO} — ${status}${r.note ? ' — ' + r.note : ''}`;
  }).join('\n');
  bot.sendMessage(msg.chat.id, out, { parse_mode: 'HTML', ...mainMenu(true) });
}

function sendNext(msg, userId, tag) {
  const data = loadData().filter(x => x.userId === userId);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() + 30);
  const now = new Date();

  const upcoming = data.filter(r => {
    try {
      const d = parseDateISO(r.dateISO);
      return d >= now && d <= cutoff;
    } catch { return false; }
  });

  if (!upcoming.length) {
    bot.sendMessage(msg.chat.id, `${tag}⏳ <b>Nessuna scadenza nei prossimi 30 giorni!</b>`, { ...mainMenu(true), parse_mode: "HTML" });
    return;
  }

  const out = upcoming.map(r => {
    const d = parseDateISO(r.dateISO);
    const daysLeft = Math.ceil((d - now) / (1000*60*60*24));
    return `• <b>${r.name}</b> — ${formatEuro(r.cost)} ${r.currency} — in ${daysLeft} giorni (scade il ${r.dateISO})`;
  }).join('\n');

  bot.sendMessage(msg.chat.id, `${tag}⏳ <b>Scadenze prossime:</b>\n${out}`, { parse_mode: 'HTML', ...mainMenu(true) });
}

// Reminder giornaliero e export invariato
function dailyReminders() {
  const data = loadData();
  const today = new Date();
  const usersToNotif = {};

  data.forEach(r => {
    let daysLeft = 0;
    try {
      const d = parseDateISO(r.dateISO);
      daysLeft = Math.ceil((d - today) / (1000*60*60*24));
    } catch { return; }
    if ([7,3,1,0].includes(daysLeft)) {
      if (!usersToNotif[r.userId]) usersToNotif[r.userId] = [];
      usersToNotif[r.userId].push({ ...r, daysLeft });
    }
  });

  Object.keys(usersToNotif).forEach(uid => {
    const msg = usersToNotif[uid].map(x =>
      `• <b>${x.name}</b> — ${formatEuro(x.cost)} ${x.currency} — scade il ${x.dateISO} (in ${x.daysLeft} giorni)`
    ).join('\n');
    bot.sendMessage(uid, `🔔 <b>Promemoria scadenze:</b>\n${msg}`, { parse_mode: 'HTML' });
  });
}

module.exports = { dailyReminders };
