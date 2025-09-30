const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');
const path = require('path');

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
  if (parts.length !== 3) throw new Error('Data non valida, usa AAAA-MM-GG');
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  if (isNaN(d.getTime())) throw new Error('Data non valida, usa AAAA-MM-GG');
  return d;
}

function formatEuro(amount) {
  const n = Number(amount);
  if (isNaN(n)) return String(amount);
  return n.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
}

// ===== STATE FOR INFO REQUEST =====
const userStates = {};

// ===== BOT LOGIC =====
bot.onText(/^\/start/, (msg) => {
  bot.sendMessage(msg.chat.id, `👋 Benvenuto!
Questo bot tiene traccia dei tuoi abbonamenti: costi, scadenze e rinnovi.

Usa /help per vedere i comandi disponibili.`);
});

bot.onText(/^\/help/, (msg) => {
  bot.sendMessage(msg.chat.id, `🧭 Comandi:
/add Nome 9.99 EUR 2025-10-31 [note] — aggiungi un abbonamento (solo admin)
/list — elenca i tuoi abbonamenti (solo admin)
/info — vedi info dettagliate di un tuo abbonamento
/renew Nome 2026-01-31 — rinnova (aggiorna la scadenza) (solo admin)
/cancel Nome — elimina l'abbonamento (solo admin)
/next — mostra le scadenze nei prossimi 30 giorni (solo admin)

Formato data: AAAA-MM-GG. Valuta consigliata: EUR.`);
});

// /list (solo admin)
bot.onText(/^\/list/, (msg) => {
  if (msg.from.id !== ADMIN_ID) {
    bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questo comando.");
    return;
  }
  const userId = msg.from.id;
  const data = loadData().filter(x => x.userId === userId);
  if (!data.length) {
    bot.sendMessage(msg.chat.id, `🗂 Nessun abbonamento registrato. Usa /add per aggiungerne uno.`);
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
  bot.sendMessage(msg.chat.id, out, { parse_mode: 'HTML' });
});

// ====== NUOVO COMANDO: /info ======
bot.onText(/^\/info$/, (msg) => {
  userStates[msg.from.id] = { awaitingInfo: true };
  bot.sendMessage(msg.chat.id, `✏️ Scrivi il nome dell'abbonamento di cui vuoi vedere le informazioni (come hai inserito con /add):`);
});

// ====== Gestione risposta al comando /info ======
bot.on('message', (msg) => {
  // Se non siamo in attesa, ignora
  if (userStates[msg.from.id] && userStates[msg.from.id].awaitingInfo) {
    const abboName = msg.text.trim();
    const userId = msg.from.id;
    const data = loadData().filter(x => x.userId === userId && x.name.toLowerCase() === abboName.toLowerCase());

    if (!data.length) {
      bot.sendMessage(msg.chat.id, `❌ Nessun abbonamento trovato con nome "<b>${abboName}</b>". Ricorda di scriverlo esattamente come in /add!`, { parse_mode: 'HTML' });
    } else {
      // Mostra info dettagliate (anche più di uno se omonimi)
      data.forEach(r => {
        bot.sendMessage(msg.chat.id, `🔎 <b>${r.name}</b>
Costo: ${formatEuro(r.cost)} ${r.currency}
Scadenza: ${r.dateISO}
${r.note ? 'Note: ' + r.note : ''}
Aggiunto il: ${r.createdAt.substring(0,10)}`, { parse_mode: 'HTML' });
      });
    }
    // Reset stato
    delete userStates[msg.from.id];
    return;
  }

  // Messaggi di default
  if (!msg.text.startsWith('/')) return;
  const known = ['/start','/help','/add','/list','/renew','/cancel','/next','/info'];
  if (!known.some(cmd => msg.text.startsWith(cmd))) {
    bot.sendMessage(msg.chat.id, `❓ Comando non riconosciuto. Usa /help.`);
  }
});

// /add (solo admin)
bot.onText(/^\/add (.+)/, (msg, match) => {
  if (msg.from.id !== ADMIN_ID) {
    bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questo comando.");
    return;
  }
  const args = match[1].split(' ').filter(Boolean);
  if (args.length < 4) {
    bot.sendMessage(msg.chat.id, `❗ Usa: /add Nome 9.99 EUR 2025-10-31 [note]`);
    return;
  }
  const [name, cost, currency, dateISO, ...noteArr] = args;
  let date;
  try {
    date = parseDateISO(dateISO);
  } catch (e) {
    bot.sendMessage(msg.chat.id, "❗ Data non valida, usa AAAA-MM-GG");
    return;
  }
  const note = noteArr.join(' ');
  const userId = msg.from.id;
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
  bot.sendMessage(msg.chat.id, `✅ Aggiunto: <b>${name}</b>
Costo: ${formatEuro(cost)} ${currency}
Scadenza: ${dateISO}
${note ? 'Note: ' + note : ''}`, { parse_mode: 'HTML' });
});

// /renew (solo admin)
bot.onText(/^\/renew (.+)/, (msg, match) => {
  if (msg.from.id !== ADMIN_ID) {
    bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questo comando.");
    return;
  }
  const args = match[1].split(' ').filter(Boolean);
  if (args.length < 2) {
    bot.sendMessage(msg.chat.id, `❗ Usa: /renew Nome 2026-01-31`);
    return;
  }
  const [name, dateISO] = args;
  let date;
  try {
    date = parseDateISO(dateISO);
  } catch (e) {
    bot.sendMessage(msg.chat.id, "❗ Data non valida, usa AAAA-MM-GG");
    return;
  }
  const userId = msg.from.id;
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
    ? `🔁 Rinnovato <b>${name}</b> fino al ${dateISO}`
    : `❌ Abbonamento <b>${name}</b> non trovato.`,
    { parse_mode: 'HTML' });
});

// /cancel (solo admin)
bot.onText(/^\/cancel (.+)/, (msg, match) => {
  if (msg.from.id !== ADMIN_ID) {
    bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questo comando.");
    return;
  }
  const name = match[1].trim();
  if (!name) {
    bot.sendMessage(msg.chat.id, `❗ Usa: /cancel Nome`);
    return;
  }
  const userId = msg.from.id;
  const data = loadData();
  const before = data.length;
  const newData = data.filter(x => !(x.userId === userId && x.name === name));
  saveData(newData);
  bot.sendMessage(msg.chat.id,
    before > newData.length
      ? `🗑 Cancellato <b>${name}</b>.`
      : `❌ Abbonamento <b>${name}</b> non trovato.`, { parse_mode: 'HTML' });
});

// /next (solo admin)
bot.onText(/^\/next/, (msg) => {
  if (msg.from.id !== ADMIN_ID) {
    bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questo comando.");
    return;
  }
  const userId = msg.from.id;
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
    bot.sendMessage(msg.chat.id, `📅 Nessuna scadenza nei prossimi 30 giorni.`);
    return;
  }

  const out = upcoming.map(r => {
    const d = parseDateISO(r.dateISO);
    const daysLeft = Math.ceil((d - now) / (1000*60*60*24));
    return `• <b>${r.name}</b> — ${formatEuro(r.cost)} ${r.currency} — in ${daysLeft} giorni (scade il ${r.dateISO})`;
  }).join('\n');

  bot.sendMessage(msg.chat.id, `⏰ Scadenze prossime:\n${out}`, { parse_mode: 'HTML' });
});

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
    bot.sendMessage(uid, `🔔 Promemoria scadenze:\n${msg}`, { parse_mode: 'HTML' });
  });
}

module.exports = { dailyReminders };
