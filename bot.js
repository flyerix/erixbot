const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const fetch = require('node-fetch');
const cron = require('node-cron');

// === CONFIG ESPANSA ===
const TOKEN = process.env.TELEGRAM_TOKEN;
const WEBHOOK_URL = process.env.WEBHOOK_URL;
const PORT = process.env.PORT || 3000;
const ADMIN_ID = parseInt(process.env.ADMIN_ID) || 691735614;
const DATA_FILE = path.join(__dirname, 'data.json');
const TICKETS_FILE = path.join(__dirname, 'tickets.json');
const USERS_FILE = path.join(__dirname, 'users.json');
const STATS_FILE = path.join(__dirname, 'stats.json');
const LOG_FILE = path.join(__dirname, 'bot.log');
const BASE_TIMEZONE = 'Europe/Rome';
const FOOTBALL_API_KEY = process.env.FOOTBALL_API_KEY;
const NEWS_API_KEY = process.env.NEWS_API_KEY;
const WEATHER_API_KEY = process.env.WEATHER_API_KEY;

// Configurazione multi-admin
const ADMIN_IDS = (process.env.ADMIN_IDS || ADMIN_ID.toString()).split(',').map(id => parseInt(id.trim()));

// === BOT SETUP MIGLIORATO ===
const bot = new TelegramBot(TOKEN, { 
  webHook: true,
  polling: false,
  request: {
    timeout: 10000,
    agent: null
  }
});

const app = express();
app.use(bodyParser.json());

// === SISTEMA DI LOGGING ===
function log(level, message, metadata = {}) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    timestamp,
    level,
    message,
    ...metadata
  };
  
  console.log(`[${timestamp}] ${level}: ${message}`);
  
  // Scrive nel file di log
  fs.appendFileSync(LOG_FILE, JSON.stringify(logEntry) + '\n');
  
  // Invia notifiche importanti all'admin
  if (level === 'ERROR' || level === 'CRITICAL') {
    ADMIN_IDS.forEach(adminId => {
      bot.sendMessage(adminId, `🚨 <b>${level}</b>: ${message}`, { parse_mode: 'HTML' }).catch(console.error);
    });
  }
}

// === UTILS MIGLIORATE ===
function loadData() {
  try {
    if (!fs.existsSync(DATA_FILE)) return [];
    return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  } catch (error) {
    log('ERROR', 'Errore nel caricamento dati', { error: error.message });
    return [];
  }
}

function saveData(data) {
  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
    updateStats();
  } catch (error) {
    log('ERROR', 'Errore nel salvataggio dati', { error: error.message });
  }
}

function loadTickets() {
  try {
    if (!fs.existsSync(TICKETS_FILE)) return [];
    return JSON.parse(fs.readFileSync(TICKETS_FILE, 'utf8'));
  } catch (error) {
    log('ERROR', 'Errore nel caricamento ticket', { error: error.message });
    return [];
  }
}

function saveTickets(tickets) {
  try {
    fs.writeFileSync(TICKETS_FILE, JSON.stringify(tickets, null, 2));
    updateStats();
  } catch (error) {
    log('ERROR', 'Errore nel salvataggio ticket', { error: error.message });
  }
}

function loadUsers() {
  try {
    if (!fs.existsSync(USERS_FILE)) return {};
    return JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'));
  } catch (error) {
    log('ERROR', 'Errore nel caricamento utenti', { error: error.message });
    return {};
  }
}

function saveUsers(users) {
  try {
    fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
    updateStats();
  } catch (error) {
    log('ERROR', 'Errore nel salvataggio utenti', { error: error.message });
  }
}

// === SISTEMA DI STATISTICHE ===
function loadStats() {
  try {
    if (!fs.existsSync(STATS_FILE)) return {
      totalUsers: 0,
      totalSubscriptions: 0,
      totalTickets: 0,
      activeTickets: 0,
      commandsProcessed: 0,
      lastUpdate: new Date().toISOString()
    };
    return JSON.parse(fs.readFileSync(STATS_FILE, 'utf8'));
  } catch (error) {
    return {
      totalUsers: 0,
      totalSubscriptions: 0,
      totalTickets: 0,
      activeTickets: 0,
      commandsProcessed: 0,
      lastUpdate: new Date().toISOString()
    };
  }
}

function saveStats(stats) {
  try {
    fs.writeFileSync(STATS_FILE, JSON.stringify(stats, null, 2));
  } catch (error) {
    log('ERROR', 'Errore nel salvataggio statistiche', { error: error.message });
  }
}

function updateStats() {
  const stats = loadStats();
  const users = loadUsers();
  const data = loadData();
  const tickets = loadTickets();
  
  stats.totalUsers = Object.keys(users).length;
  stats.totalSubscriptions = data.length;
  stats.totalTickets = tickets.length;
  stats.activeTickets = tickets.filter(t => t.status !== 'closed').length;
  stats.lastUpdate = new Date().toISOString();
  
  saveStats(stats);
}

function incrementCommandCount() {
  const stats = loadStats();
  stats.commandsProcessed++;
  saveStats(stats);
}

// === FUNZIONI UTILITÀ MIGLIORATE ===
function getUserPreferences(userId) {
  const users = loadUsers();
  if (!users[userId]) {
    // Crea un profilo utente di default
    users[userId] = { 
      footballTeam: null, 
      wantsFootballUpdates: false,
      language: 'it',
      notifications: true,
      createdAt: new Date().toISOString(),
      lastActivity: new Date().toISOString()
    };
    saveUsers(users);
  }
  return users[userId];
}

function updateUserActivity(userId) {
  const users = loadUsers();
  if (users[userId]) {
    users[userId].lastActivity = new Date().toISOString();
    saveUsers(users);
  }
}

function saveUserPreferences(userId, preferences) {
  const users = loadUsers();
  users[userId] = { ...getUserPreferences(userId), ...preferences, lastActivity: new Date().toISOString() };
  saveUsers(users);
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

function isAdmin(msg) {
  return msg.from && ADMIN_IDS.includes(msg.from.id);
}

function getAdminTag(msg) {
  return isAdmin(msg) ? "👑 [ADMIN] " : "";
}

function generateTicketId() {
  return 'T' + Date.now() + Math.random().toString(36).substr(2, 5).toUpperCase();
}

// === SISTEMA DI BACKUP AUTOMATICO ===
function createBackup() {
  const backupDir = path.join(__dirname, 'backups');
  if (!fs.existsSync(backupDir)) {
    fs.mkdirSync(backupDir);
  }
  
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filesToBackup = [DATA_FILE, TICKETS_FILE, USERS_FILE, STATS_FILE];
  
  filesToBackup.forEach(file => {
    if (fs.existsSync(file)) {
      const fileName = path.basename(file);
      const backupFile = path.join(backupDir, `${timestamp}_${fileName}`);
      fs.copyFileSync(file, backupFile);
    }
  });
  
  log('INFO', 'Backup creato automaticamente', { timestamp });
}

// Pianifica backup giornalieri alle 2:00
cron.schedule('0 2 * * *', () => {
  createBackup();
});

// === SISTEMA DI NOTIFICHE METEOROLOGICHE ===
async function getWeather(city = 'Roma') {
  try {
    if (!WEATHER_API_KEY) {
      return {
        temperature: 20 + Math.floor(Math.random() * 15),
        condition: 'sole',
        humidity: 60 + Math.floor(Math.random() * 30),
        city: city
      };
    }

    const response = await fetch(`https://api.openweathermap.org/data/2.5/weather?q=${encodeURIComponent(city)}&appid=${WEATHER_API_KEY}&units=metric&lang=it`);
    
    if (!response.ok) {
      throw new Error('Errore API meteo');
    }
    
    const data = await response.json();
    
    return {
      temperature: Math.round(data.main.temp),
      condition: data.weather[0].description,
      humidity: data.main.humidity,
      city: data.name
    };
  } catch (error) {
    log('ERROR', 'Errore nel recupero dati meteo', { error: error.message });
    return null;
  }
}

// === MAPPATURE ESPANSE ===
const TEAM_MAPPING = {
  'milan': 'AC Milan',
  'ac milan': 'AC Milan',
  'inter': 'FC Internazionale Milano',
  'internazionale': 'FC Internazionale Milano',
  'juventus': 'Juventus FC',
  'juve': 'Juventus FC',
  'roma': 'AS Roma',
  'as roma': 'AS Roma',
  'napoli': 'SSC Napoli',
  'fiorentina': 'ACF Fiorentina',
  'lazio': 'SS Lazio',
  'atalanta': 'Atalanta BC',
  'bologna': 'Bologna FC 1909',
  'torino': 'Torino FC',
  'genoa': 'Genoa CFC',
  'sampdoria': 'UC Sampdoria',
  'udinese': 'Udinese Calcio',
  'sassuolo': 'US Sassuolo Calcio',
  'cagliari': 'Cagliari Calcio',
  'verona': 'Hellas Verona FC',
  'lecce': 'US Lecce',
  'empoli': 'Empoli FC',
  'monza': 'AC Monza',
  'frosinone': 'Frosinone Calcio',
  'salernitana': 'Salernitana Calcio',
  // Squadre internazionali
  'real madrid': 'Real Madrid',
  'barcellona': 'FC Barcelona',
  'barcelona': 'FC Barcelona',
  'bayern': 'Bayern Munich',
  'bayern monaco': 'Bayern Munich',
  'psg': 'Paris Saint-Germain',
  'manchester united': 'Manchester United',
  'man utd': 'Manchester United',
  'manchester city': 'Manchester City',
  'man city': 'Manchester City',
  'liverpool': 'Liverpool FC',
  'chelsea': 'Chelsea FC',
  'arsenal': 'Arsenal FC'
};

// Funzione per normalizzare il nome della squadra
function normalizeTeamName(teamName) {
  const lowerName = teamName.toLowerCase().trim();
  return TEAM_MAPPING[lowerName] || teamName;
}

// Funzione per ottenere informazioni sulla squadra
async function getTeamInfo(teamName) {
  try {
    const normalizedTeamName = normalizeTeamName(teamName);
    
    if (!FOOTBALL_API_KEY) {
      console.log('Football API key non configurata, uso dati mock');
      return getMockTeamInfo(normalizedTeamName);
    }

    console.log(`Cerco squadra: ${normalizedTeamName}`);
    
    // Prima cerca tra le squadre italiane conosciute
    const searchResponse = await fetch(`https://api.football-data.org/v4/teams?areas=2077`, {
      headers: { 'X-Auth-Token': FOOTBALL_API_KEY },
      timeout: 10000
    });
    
    if (!searchResponse.ok) {
      console.log('Errore API football:', searchResponse.status);
      return getMockTeamInfo(normalizedTeamName);
    }
    
    const searchData = await searchResponse.json();
    if (!searchData.teams || searchData.teams.length === 0) {
      return getMockTeamInfo(normalizedTeamName);
    }
    
    // Cerca la squadra per nome
    const foundTeam = searchData.teams.find(team => 
      team.name.toLowerCase().includes(normalizedTeamName.toLowerCase()) ||
      team.shortName.toLowerCase().includes(normalizedTeamName.toLowerCase()) ||
      team.tla.toLowerCase() === normalizedTeamName.toLowerCase().substring(0, 3)
    );
    
    if (!foundTeam) {
      console.log(`Squadra "${normalizedTeamName}" non trovata`);
      return getMockTeamInfo(normalizedTeamName);
    }
    
    const teamId = foundTeam.id;
    console.log(`Trovata squadra: ${foundTeam.name} (ID: ${teamId})`);
    
    // Ottieni le prossime partite
    const matchesResponse = await fetch(`https://api.football-data.org/v4/teams/${teamId}/matches?status=SCHEDULED&limit=5`, {
      headers: { 'X-Auth-Token': FOOTBALL_API_KEY },
      timeout: 10000
    });
    
    let matches = [];
    if (matchesResponse.ok) {
      const matchesData = await matchesResponse.json();
      matches = matchesData.matches || [];
    } else {
      console.log('Errore nel recupero partite:', matchesResponse.status);
    }
    
    // Ottieni notizie
    const news = await getTeamNews(foundTeam.name);
    
    return {
      team: {
        id: foundTeam.id,
        name: foundTeam.name,
        shortName: foundTeam.shortName,
        crest: foundTeam.crest,
        venue: foundTeam.venue,
        founded: foundTeam.founded,
        colors: foundTeam.clubColors
      },
      matches: matches.map(match => ({
        id: match.id,
        competition: match.competition?.name,
        homeTeam: match.homeTeam?.name,
        awayTeam: match.awayTeam?.name,
        date: match.utcDate,
        status: match.status
      })),
      news: news
    };
  } catch (error) {
    console.error('Errore nel recupero info squadra:', error);
    return getMockTeamInfo(teamName);
  }
}

// Funzione per ottenere notizie sulla squadra
async function getTeamNews(teamName) {
  try {
    if (!NEWS_API_KEY) {
      return getMockNews(teamName);
    }

    const newsResponse = await fetch(`https://newsapi.org/v2/everything?q=${encodeURIComponent(teamName)}+calcio&language=it&sortBy=publishedAt&pageSize=3&apiKey=${NEWS_API_KEY}`, {
      timeout: 10000
    });
    
    if (!newsResponse.ok) {
      console.log('Errore API news:', newsResponse.status);
      return getMockNews(teamName);
    }
    
    const newsData = await newsResponse.json();
    return newsData.articles?.map(article => ({
      title: article.title,
      description: article.description,
      url: article.url,
      publishedAt: article.publishedAt,
      source: article.source?.name
    })) || [];
  } catch (error) {
    console.error('Errore nel recupero notizie:', error);
    return getMockNews(teamName);
  }
}

// Funzioni mock migliorate
function getMockTeamInfo(teamName) {
  const italianTeams = {
    'AC Milan': { stadium: 'San Siro', founded: 1899, colors: 'Rosso-Nero' },
    'FC Internazionale Milano': { stadium: 'San Siro', founded: 1908, colors: 'Nero-Azzurro' },
    'Juventus FC': { stadium: 'Allianz Stadium', founded: 1897, colors: 'Bianco-Nero' },
    'AS Roma': { stadium: 'Stadio Olimpico', founded: 1927, colors: 'Giallo-Rosso' },
    'SSC Napoli': { stadium: 'Diego Armando Maradona', founded: 1926, colors: 'Azzurro' },
    'ACF Fiorentina': { stadium: 'Artemio Franchi', founded: 1926, colors: 'Viola' },
    'SS Lazio': { stadium: 'Stadio Olimpico', founded: 1900, colors: 'Bianco-Celeste' }
  };

  const teamInfo = italianTeams[teamName] || { 
    stadium: 'Stadio ' + teamName, 
    founded: 1900, 
    colors: 'Vari' 
  };

  // Crea partite mock realistiche per squadre italiane
  const opponents = ['Juventus', 'Inter', 'Milan', 'Roma', 'Napoli', 'Lazio', 'Fiorentina'];
  const mockMatches = [
    {
      id: 1,
      competition: "Serie A",
      homeTeam: teamName,
      awayTeam: opponents[Math.floor(Math.random() * opponents.length)],
      date: new Date(Date.now() + 86400000 * 3).toISOString(),
      status: "SCHEDULED"
    },
    {
      id: 2,
      competition: "Coppa Italia",
      homeTeam: opponents[Math.floor(Math.random() * opponents.length)],
      awayTeam: teamName,
      date: new Date(Date.now() + 86400000 * 7).toISOString(),
      status: "SCHEDULED"
    }
  ];

  return {
    team: {
      id: 999,
      name: teamName,
      shortName: teamName.split(' ').map(word => word[0]).join('').toUpperCase(),
      crest: null,
      venue: teamInfo.stadium,
      founded: teamInfo.founded,
      colors: teamInfo.colors
    },
    matches: mockMatches,
    news: getMockNews(teamName)
  };
}

function getMockNews(teamName) {
  const newsTemplates = [
    {
      title: `${teamName}: ultime notizie e aggiornamenti`,
      description: `Segui tutte le ultime novità sulla ${teamName} nella nostra rubrica speciale.`,
      url: "https://www.gazzetta.it/calcio",
      publishedAt: new Date().toISOString(),
      source: "La Gazzetta dello Sport"
    },
    {
      title: `Calciomercato ${teamName}: le voci di oggi`,
      description: `Tutte le ultime voci di calciomercato riguardanti la ${teamName}.`,
      url: "https://www.corrieredellosport.it/",
      publishedAt: new Date(Date.now() - 86400000).toISOString(),
      source: "Corriere dello Sport"
    },
    {
      title: `Prossime partite per la ${teamName}`,
      description: `Calendario completo delle prossime gare della ${teamName} in Serie A e coppe.`,
      url: "https://www.tuttosport.com/",
      publishedAt: new Date(Date.now() - 172800000).toISOString(),
      source: "Tuttosport"
    }
  ];

  return newsTemplates;
}

// === SISTEMA DI RICONOSCIMENTO LINGUE ===
const translations = {
  it: {
    welcome: "🚀 Benvenuto {name}!",
    help: "❓ <b>Ecco cosa posso fare:</b>",
    menu: "🚀 <b>Menu Principale</b>\n\nCosa vuoi fare?",
    // ... altre traduzioni
  },
  en: {
    welcome: "🚀 Welcome {name}!",
    help: "❓ <b>Here's what I can do:</b>",
    menu: "🚀 <b>Main Menu</b>\n\nWhat do you want to do?",
    // ... altre traduzioni
  }
};

function getTranslation(userId, key, params = {}) {
  const preferences = getUserPreferences(userId);
  const lang = preferences.language || 'it';
  let text = translations[lang]?.[key] || translations['it'][key] || key;
  
  // Sostituisce i parametri
  Object.keys(params).forEach(param => {
    text = text.replace(`{${param}}`, params[param]);
  });
  
  return text;
}

// === FUNZIONALITÀ AGGIUNTIVE ===

// Sistema di reminder automatici per scadenze
function checkExpiringSubscriptions() {
  const data = loadData();
  const now = new Date();
  const sevenDaysFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  
  const expiring = data.filter(sub => {
    try {
      const expDate = parseDateISO(sub.dateISO);
      return expDate <= sevenDaysFromNow && expDate > now;
    } catch {
      return false;
    }
  });
  
  expiring.forEach(sub => {
    const daysLeft = Math.ceil((parseDateISO(sub.dateISO) - now) / (1000 * 60 * 60 * 24));
    
    bot.sendMessage(
      ADMIN_ID,
      `⏰ <b>Promemoria Scadenza</b>\n\n` +
      `📅 <b>${sub.name}</b> scade tra ${daysLeft} giorni\n` +
      `📆 Data scadenza: ${sub.dateISO}\n` +
      `💸 Costo: ${formatEuro(sub.cost)}`,
      { parse_mode: 'HTML' }
    ).catch(console.error);
  });
}

// Pianifica controllo giornaliero alle 9:00
cron.schedule('0 9 * * *', () => {
  checkExpiringSubscriptions();
});

// === MENU E INTERFACCE MIGLIORATE ===
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
      { text: "⏳ Scadenze", callback_data: "next" },
      { text: "📊 Statistiche", callback_data: "stats" }
    ]);
  }
  
  buttons.push([
    { text: "🔎 Info abbonamento", callback_data: "info" },
    { text: "🛰 Stato servizio", callback_data: "status" }
  ]);
  buttons.push([
    { text: "⚽ Calcio", callback_data: "football" },
    { text: "🌤 Meteo", callback_data: "weather" }
  ]);
  buttons.push([
    { text: "🎫 Supporto", callback_data: "support" },
    { text: "⚙️ Impostazioni", callback_data: "settings" }
  ]);
  buttons.push([
    { text: "❓ Aiuto", callback_data: "help" }
  ]);
  
  return {
    reply_markup: {
      inline_keyboard: buttons,
      resize_keyboard: true
    }
  };
}

function settingsMenu(userId) {
  const preferences = getUserPreferences(userId);
  
  return {
    reply_markup: {
      inline_keyboard: [
        [
          { text: preferences.notifications ? "🔔 Notifiche ON" : "🔕 Notifiche OFF", 
            callback_data: "toggle_notifications" }
        ],
        [
          { text: "🌍 Lingua", callback_data: "change_language" }
        ],
        [
          { text: "📊 Le mie statistiche", callback_data: "my_stats" }
        ],
        [
          { text: "🔙 Menu Principale", callback_data: "main_menu" }
        ]
      ]
    }
  };
}

function supportMenu(isAdminUser = false, ticketId = null) {
  const buttons = [];
  
  if (!isAdminUser) {
    buttons.push([{ text: "📝 Apri Ticket", callback_data: "open_ticket" }]);
    buttons.push([{ text: "📋 I miei Ticket", callback_data: "my_tickets" }]);
  } else {
    buttons.push([{ text: "📋 Ticket Aperti", callback_data: "admin_tickets_open" }]);
    buttons.push([{ text: "📥 Ticket Assegnati", callback_data: "admin_tickets_assigned" }]);
    buttons.push([{ text: "✅ Ticket Chiusi", callback_data: "admin_tickets_closed" }]);
  }
  
  if (ticketId) {
    buttons.push([
      { text: "👤 Assegna a me", callback_data: `assign_${ticketId}` },
      { text: "💬 Rispondi", callback_data: `reply_${ticketId}` }
    ]);
    buttons.push([
      { text: "✅ Chiudi", callback_data: `close_${ticketId}` },
      { text: "📋 Lista Ticket", callback_data: "admin_tickets_open" }
    ]);
  }
  
  buttons.push([{ text: "🔙 Menu Principale", callback_data: "main_menu" }]);
  
  return {
    reply_markup: {
      inline_keyboard: buttons
    }
  };
}

// Menu per il calcio
function footballMenu(hasTeam = false, wantsUpdates = false) {
  const buttons = [];
  
  if (!hasTeam) {
    buttons.push([{ text: "⚽ Imposta squadra preferita", callback_data: "set_football_team" }]);
  } else {
    buttons.push([{ text: "🔄 Cambia squadra", callback_data: "set_football_team" }]);
    
    if (wantsUpdates) {
      buttons.push([{ text: "🔔 Disattiva notifiche", callback_data: "disable_football_updates" }]);
    } else {
      buttons.push([{ text: "🔔 Attiva notifiche", callback_data: "enable_football_updates" }]);
    }
    
    buttons.push([{ text: "📰 Ultime notizie", callback_data: "football_news" }]);
    buttons.push([{ text: "📅 Prossime partite", callback_data: "football_matches" }]);
    buttons.push([{ text: "ℹ️ Info squadra", callback_data: "football_info" }]);
  }
  
  buttons.push([{ text: "🔙 Menu Principale", callback_data: "main_menu" }]);
  
  return {
    reply_markup: {
      inline_keyboard: buttons
    }
  };
}

// === FUNZIONI PER LA GESTIONE DEI TICKET ===

// Mostra i ticket all'admin
function showAdminTickets(msg, status) {
  const tickets = loadTickets();
  const filteredTickets = tickets.filter(ticket => ticket.status === status);
  
  if (filteredTickets.length === 0) {
    let statusText = '';
    switch (status) {
      case 'open': statusText = 'aperti'; break;
      case 'assigned': statusText = 'assegnati'; break;
      case 'closed': statusText = 'chiusi'; break;
    }
    bot.sendMessage(
      msg.chat.id,
      `📋 <b>Nessun ticket ${statusText} trovato</b>`,
      { 
        ...supportMenu(true),
        parse_mode: "HTML" 
      }
    );
    return;
  }

  let message = '';
  switch (status) {
    case 'open':
      message = '📋 <b>Ticket Aperti</b>\n\n';
      break;
    case 'assigned':
      message = '📥 <b>Ticket Assegnati a Te</b>\n\n';
      break;
    case 'closed':
      message = '✅ <b>Ticket Chiusi</b>\n\n';
      break;
  }

  filteredTickets.forEach((ticket, index) => {
    const date = new Date(ticket.createdAt).toLocaleDateString('it-IT');
    message += `<b>${index + 1}. Ticket ${ticket.id}</b>\n`;
    message += `👤 <b>Utente:</b> ${ticket.userName}\n`;
    message += `📅 <b>Data:</b> ${date}\n`;
    message += `📝 <b>Richiesta:</b> ${ticket.subject.substring(0, 100)}${ticket.subject.length > 100 ? '...' : ''}\n`;
    
    if (ticket.assignedAdmin) {
      message += `👨‍💼 <b>Assegnato a:</b> ${ticket.assignedAdmin}\n`;
    }
    
    message += `\n────────────────────\n\n`;
  });

  // Crea i bottoni per i ticket
  const buttons = [];
  filteredTickets.forEach(ticket => {
    buttons.push([
      { 
        text: `📋 Ticket ${ticket.id}`, 
        callback_data: `view_${ticket.id}` 
      }
    ]);
  });
  
  buttons.push([{ text: "🔙 Menu Supporto", callback_data: "support" }]);

  bot.sendMessage(msg.chat.id, message, {
    parse_mode: "HTML",
    reply_markup: {
      inline_keyboard: buttons
    }
  });
}

// Mostra i ticket dell'utente
function showUserTickets(msg, userId) {
  const tickets = loadTickets();
  const userTickets = tickets.filter(ticket => ticket.userId === userId);
  
  if (userTickets.length === 0) {
    bot.sendMessage(
      msg.chat.id,
      `📋 <b>Non hai alcun ticket aperto</b>\n\nApri un nuovo ticket se hai bisogno di assistenza.`,
      { 
        ...supportMenu(false),
        parse_mode: "HTML" 
      }
    );
    return;
  }

  let message = '📋 <b>I tuoi Ticket</b>\n\n';

  userTickets.forEach((ticket, index) => {
    const date = new Date(ticket.createdAt).toLocaleDateString('it-IT');
    let statusEmoji = '🟡';
    let statusText = 'Aperto';
    
    if (ticket.status === 'assigned') {
      statusEmoji = '🔵';
      statusText = 'In lavorazione';
    } else if (ticket.status === 'closed') {
      statusEmoji = '✅';
      statusText = 'Chiuso';
    }

    message += `<b>${index + 1}. Ticket ${ticket.id}</b> ${statusEmoji}\n`;
    message += `📅 <b>Data:</b> ${date}\n`;
    message += `📝 <b>Richiesta:</b> ${ticket.subject.substring(0, 100)}${ticket.subject.length > 100 ? '...' : ''}\n`;
    message += `🔄 <b>Stato:</b> ${statusText}\n`;
    
    if (ticket.assignedAdmin) {
      message += `👨‍💼 <b>Assegnato a:</b> ${ticket.assignedAdmin}\n`;
    }
    
    message += `\n────────────────────\n\n`;
  });

  bot.sendMessage(msg.chat.id, message, {
    parse_mode: "HTML",
    ...supportMenu(false)
  });
}

// Visualizza un ticket specifico
function viewTicket(msg, ticketId, isAdmin) {
  const tickets = loadTickets();
  const ticket = tickets.find(t => t.id === ticketId);
  
  if (!ticket) {
    bot.sendMessage(msg.chat.id, "❌ Ticket non trovato!");
    return;
  }

  // Controlla i permessi
  if (!isAdmin && ticket.userId !== msg.from.id) {
    bot.sendMessage(msg.chat.id, "❌ Non hai i permessi per visualizzare questo ticket!");
    return;
  }

  const date = new Date(ticket.createdAt).toLocaleDateString('it-IT');
  let statusEmoji = '🟡';
  let statusText = 'Aperto';
  
  if (ticket.status === 'assigned') {
    statusEmoji = '🔵';
    statusText = 'In lavorazione';
  } else if (ticket.status === 'closed') {
    statusEmoji = '✅';
    statusText = 'Chiuso';
  }

  let message = `🎫 <b>Ticket ${ticket.id}</b> ${statusEmoji}\n\n`;
  message += `👤 <b>Utente:</b> ${ticket.userName}\n`;
  message += `📅 <b>Data apertura:</b> ${date}\n`;
  message += `🔄 <b>Stato:</b> ${statusText}\n`;
  
  if (ticket.assignedAdmin) {
    message += `👨‍💼 <b>Assegnato a:</b> ${ticket.assignedAdmin}\n`;
  }
  
  message += `\n📝 <b>Richiesta:</b>\n${ticket.subject}\n`;

  // Mostra le risposte
  if (ticket.replies && ticket.replies.length > 0) {
    message += `\n💬 <b>Cronologia conversazione:</b>\n`;
    
    // Ordina le risposte per data
    const sortedReplies = ticket.replies.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    
    sortedReplies.forEach((reply, index) => {
      const replyDate = new Date(reply.timestamp).toLocaleDateString('it-IT', {
        hour: '2-digit',
        minute: '2-digit'
      });
      
      if (reply.type === 'admin') {
        message += `\n👨‍💼 <b>Staff (${reply.adminName}) - ${replyDate}:</b>\n${reply.message}\n`;
      } else {
        message += `\n👤 <b>Utente - ${replyDate}:</b>\n${reply.message}\n`;
      }
    });
  } else {
    message += `\n💬 <b>Nessuna risposta ancora.</b>\n`;
  }

  if (isAdmin) {
    bot.sendMessage(msg.chat.id, message, {
      parse_mode: "HTML",
      ...supportMenu(true, ticketId)
    });
  } else {
    // Menu per l'utente con possibilità di rispondere se il ticket non è chiuso
    const userButtons = [];
    
    if (ticket.status !== 'closed') {
      userButtons.push([{ text: "💬 Rispondi", callback_data: `user_reply_${ticketId}` }]);
    }
    
    userButtons.push([{ text: "🔙 Menu Supporto", callback_data: "support" }]);
    
    bot.sendMessage(msg.chat.id, message, {
      parse_mode: "HTML",
      reply_markup: {
        inline_keyboard: userButtons
      }
    });
  }
}

// Assegna un ticket all'admin
function assignTicket(msg, ticketId, adminId, adminName) {
  const tickets = loadTickets();
  const ticketIndex = tickets.findIndex(t => t.id === ticketId);
  
  if (ticketIndex === -1) {
    bot.sendMessage(msg.chat.id, "❌ Ticket non trovato!");
    return;
  }

  tickets[ticketIndex].status = 'assigned';
  tickets[ticketIndex].assignedTo = adminId;
  tickets[ticketIndex].assignedAdmin = adminName;
  tickets[ticketIndex].updatedAt = nowISO();
  
  saveTickets(tickets);

  // Conferma all'admin
  bot.sendMessage(
    msg.chat.id,
    `✅ <b>Ticket ${ticketId} assegnato a te!</b>`,
    { 
      ...supportMenu(true, ticketId),
      parse_mode: "HTML" 
    }
  );

  // Notifica all'utente
  bot.sendMessage(
    tickets[ticketIndex].userId,
    `🎫 <b>Il tuo ticket ${ticketId} è stato preso in carico!</b>\n\nLo staff ti risponderà al più presto.`,
    { parse_mode: "HTML" }
  );
}

// Invia una risposta dell'admin e imposta lo stato per la risposta dell'utente
function sendAdminReply(msg, ticketId, replyText, adminName) {
  const tickets = loadTickets();
  const ticketIndex = tickets.findIndex(t => t.id === ticketId);
  
  if (ticketIndex === -1) {
    bot.sendMessage(msg.chat.id, "❌ Ticket non trovato!");
    return;
  }

  // Aggiungi la risposta dell'admin
  if (!tickets[ticketIndex].replies) {
    tickets[ticketIndex].replies = [];
  }
  
  tickets[ticketIndex].replies.push({
    type: 'admin',
    message: replyText,
    timestamp: nowISO(),
    adminName: adminName
  });
  
  tickets[ticketIndex].updatedAt = nowISO();
  tickets[ticketIndex].status = 'assigned'; // Cambia stato in "in lavorazione"
  saveTickets(tickets);

  // Conferma all'admin
  bot.sendMessage(
    msg.chat.id,
    `✅ <b>Risposta inviata per il ticket ${ticketId}!</b>`,
    { parse_mode: "HTML" }
  );

  // Invia la risposta all'utente con un pulsante per rispondere
  const replyMessage = `🎫 <b>Risposta dal Supporto - Ticket ${ticketId}</b>\n\n${replyText}\n\nPuoi rispondere a questo messaggio utilizzando il pulsante qui sotto.`;
  
  bot.sendMessage(
    tickets[ticketIndex].userId,
    replyMessage,
    {
      parse_mode: "HTML",
      reply_markup: {
        inline_keyboard: [
          [{ text: "💬 Rispondi al Supporto", callback_data: `user_reply_${ticketId}` }],
          [{ text: "📋 Vedi Ticket Completo", callback_data: `view_${ticketId}` }]
        ]
      }
    }
  );
}

// Invia una risposta dell'utente e imposta lo stato per la risposta dell'admin
function sendUserReply(msg, ticketId, replyText) {
  const tickets = loadTickets();
  const ticketIndex = tickets.findIndex(t => t.id === ticketId);
  
  if (ticketIndex === -1) {
    bot.sendMessage(msg.chat.id, "❌ Ticket non trovato!");
    return;
  }

  // Verifica che l'utente sia il proprietario del ticket
  if (tickets[ticketIndex].userId !== msg.from.id) {
    bot.sendMessage(msg.chat.id, "❌ Non puoi rispondere a questo ticket!");
    return;
  }

  // Verifica che il ticket non sia chiuso
  if (tickets[ticketIndex].status === 'closed') {
    bot.sendMessage(msg.chat.id, "❌ Il ticket è chiuso, non puoi rispondere!");
    return;
  }

  // Aggiungi la risposta dell'utente
  if (!tickets[ticketIndex].replies) {
    tickets[ticketIndex].replies = [];
  }
  
  tickets[ticketIndex].replies.push({
    type: 'user',
    message: replyText,
    timestamp: nowISO()
  });
  
  tickets[ticketIndex].updatedAt = nowISO();
  saveTickets(tickets);

  // Conferma all'utente
  bot.sendMessage(
    msg.chat.id,
    `✅ <b>Risposta inviata per il ticket ${ticketId}!</b>\n\nLo staff ti risponderà al più presto.`,
    { parse_mode: "HTML" }
  );

  // Notifica all'admin con pulsante per rispondere
  const adminMessage = `🎫 <b>Nuova risposta dal cliente - Ticket ${ticketId}</b>\n\n<b>Utente:</b> ${tickets[ticketIndex].userName}\n<b>Messaggio:</b>\n${replyText}`;
  
  bot.sendMessage(
    ADMIN_ID,
    adminMessage,
    {
      parse_mode: "HTML",
      reply_markup: {
        inline_keyboard: [
          [{ text: "💬 Rispondi al Cliente", callback_data: `reply_${ticketId}` }],
          [{ text: "📋 Vedi Ticket Completo", callback_data: `view_${ticketId}` }]
        ]
      }
    }
  );
}

// Chiude un ticket
function closeTicket(msg, ticketId, adminId) {
  const tickets = loadTickets();
  const ticketIndex = tickets.findIndex(t => t.id === ticketId);
  
  if (ticketIndex === -1) {
    bot.sendMessage(msg.chat.id, "❌ Ticket non trovato!");
    return;
  }

  // Verifica che l'admin abbia i permessi (sia assegnato o sia admin)
  if (tickets[ticketIndex].assignedTo !== adminId && tickets[ticketIndex].assignedTo !== null) {
    bot.sendMessage(msg.chat.id, "❌ Puoi chiudere solo i ticket assegnati a te!");
    return;
  }

  tickets[ticketIndex].status = 'closed';
  tickets[ticketIndex].updatedAt = nowISO();
  
  saveTickets(tickets);

  // Conferma all'admin
  bot.sendMessage(
    msg.chat.id,
    `✅ <b>Ticket ${ticketId} chiuso!</b>`,
    { 
      ...supportMenu(true),
      parse_mode: "HTML" 
    }
  );

  // Notifica all'utente
  bot.sendMessage(
    tickets[ticketIndex].userId,
    `🎫 <b>Il tuo ticket ${ticketId} è stato chiuso.</b>\n\nSe hai altri problemi, apri un nuovo ticket. Grazie!`,
    { parse_mode: "HTML" }
  );
}

// === FUNZIONI AMMINISTRATIVE ESPANSE ===
function showStats(msg) {
  const stats = loadStats();
  const users = loadUsers();
  const tickets = loadTickets();
  
  // Calcola statistiche aggiuntive
  const activeUsers = Object.values(users).filter(user => {
    const lastActivity = new Date(user.lastActivity);
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    return lastActivity > thirtyDaysAgo;
  }).length;
  
  const openTickets = tickets.filter(t => t.status === 'open').length;
  const assignedTickets = tickets.filter(t => t.status === 'assigned').length;
  
  const message = `📊 <b>Statistiche Bot</b>\n\n` +
    `👥 <b>Utenti totali:</b> ${stats.totalUsers}\n` +
    `👤 <b>Utenti attivi (30gg):</b> ${activeUsers}\n` +
    `📋 <b>Abbonamenti:</b> ${stats.totalSubscriptions}\n` +
    `🎫 <b>Ticket totali:</b> ${stats.totalTickets}\n` +
    `🔴 <b>Ticket aperti:</b> ${openTickets}\n` +
    `🟡 <b>Ticket in lavorazione:</b> ${assignedTickets}\n` +
    `📈 <b>Comandi processati:</b> ${stats.commandsProcessed}\n` +
    `🕒 <b>Ultimo aggiornamento:</b> ${new Date(stats.lastUpdate).toLocaleString('it-IT')}\n\n` +
    `⚙️ <b>Configurazione:</b>\n` +
    `• Admin: ${ADMIN_IDS.length}\n` +
    `• API Calcio: ${FOOTBALL_API_KEY ? '✅' : '❌'}\n` +
    `• API News: ${NEWS_API_KEY ? '✅' : '❌'}\n` +
    `• API Meteo: ${WEATHER_API_KEY ? '✅' : '❌'}`;
  
  bot.sendMessage(msg.chat.id, message, { 
    parse_mode: 'HTML',
    ...mainMenu(true)
  });
}

// === FUNZIONI PER IL CALCIO ===
async function sendFootballNews(msg, userId) {
  const preferences = getUserPreferences(userId);
  
  if (!preferences.footballTeam) {
    bot.sendMessage(msg.chat.id, "❌ Prima imposta la tua squadra preferita!");
    return;
  }
  
  const loadingMsg = await bot.sendMessage(msg.chat.id, "📰 <b>Ricerca notizie in corso...</b>", { parse_mode: "HTML" });
  
  const teamInfo = await getTeamInfo(preferences.footballTeam);
  
  await bot.deleteMessage(msg.chat.id, loadingMsg.message_id);
  
  if (!teamInfo || !teamInfo.news || teamInfo.news.length === 0) {
    bot.sendMessage(
      msg.chat.id,
      `❌ Nessuna notizia recente trovata per <b>${preferences.footballTeam}</b>.\n\nProva più tardi o verifica il nome della squadra.`,
      { parse_mode: "HTML" }
    );
    return;
  }
  
  let message = `📰 <b>Ultime notizie per ${teamInfo.team.name}</b>\n\n`;
  
  teamInfo.news.forEach((article, index) => {
    message += `<b>${index + 1}. ${article.title}</b>\n`;
    if (article.description) {
      message += `${article.description}\n`;
    }
    message += `<a href="${article.url}">🔗 Leggi articolo completo</a>\n`;
    message += `📰 <i>${article.source}</i> | 📅 ${new Date(article.publishedAt).toLocaleDateString('it-IT')}\n\n`;
  });
  
  bot.sendMessage(msg.chat.id, message, {
    parse_mode: "HTML",
    disable_web_page_preview: false,
    ...footballMenu(true, preferences.wantsFootballUpdates)
  });
}

async function sendFootballMatches(msg, userId) {
  const preferences = getUserPreferences(userId);
  
  if (!preferences.footballTeam) {
    bot.sendMessage(msg.chat.id, "❌ Prima imposta la tua squadra preferita!");
    return;
  }
  
  const loadingMsg = await bot.sendMessage(msg.chat.id, "📅 <b>Ricerca partite in corso...</b>", { parse_mode: "HTML" });
  
  const teamInfo = await getTeamInfo(preferences.footballTeam);
  
  await bot.deleteMessage(msg.chat.id, loadingMsg.message_id);
  
  if (!teamInfo || !teamInfo.matches || teamInfo.matches.length === 0) {
    bot.sendMessage(
      msg.chat.id,
      `❌ Nessuna partita in programma trovata per <b>${preferences.footballTeam}</b>.\n\nPotrebbe essere fuori stagione o verifica il nome della squadra.`,
      { parse_mode: "HTML" }
    );
    return;
  }
  
  let message = `📅 <b>Prossime partite di ${teamInfo.team.name}</b>\n\n`;
  
  teamInfo.matches.forEach((match, index) => {
    const matchDate = new Date(match.date).toLocaleDateString('it-IT', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
    
    message += `<b>${index + 1}. ${match.homeTeam} vs ${match.awayTeam}</b>\n`;
    message += `🏆 ${match.competition || "Competizione"}\n`;
    message += `📅 ${matchDate}\n`;
    message += `🔵 ${match.status}\n\n`;
  });
  
  bot.sendMessage(msg.chat.id, message, {
    parse_mode: "HTML",
    ...footballMenu(true, preferences.wantsFootballUpdates)
  });
}

async function sendFootballInfo(msg, userId) {
  const preferences = getUserPreferences(userId);
  
  if (!preferences.footballTeam) {
    bot.sendMessage(msg.chat.id, "❌ Prima imposta la tua squadra preferita!");
    return;
  }
  
  const loadingMsg = await bot.sendMessage(msg.chat.id, "⚽ <b>Ricerca informazioni in corso...</b>", { parse_mode: "HTML" });
  
  const teamInfo = await getTeamInfo(preferences.footballTeam);
  
  await bot.deleteMessage(msg.chat.id, loadingMsg.message_id);
  
  if (!teamInfo) {
    bot.sendMessage(
      msg.chat.id,
      `❌ Impossibile trovare informazioni per <b>${preferences.footballTeam}</b>.\n\nVerifica il nome della squadra e riprova.`,
      { parse_mode: "HTML" }
    );
    return;
  }
  
  let message = `⚽ <b>Informazioni su ${teamInfo.team.name}</b>\n\n`;
  
  if (teamInfo.team.crest) {
    message += `<a href="${teamInfo.team.crest}">🔰</a> `;
  }
  
  message += `<b>Nome completo:</b> ${teamInfo.team.name}\n`;
  message += `<b>Nome abbreviato:</b> ${teamInfo.team.shortName}\n`;
  
  if (teamInfo.team.venue) {
    message += `<b>Stadio:</b> ${teamInfo.team.venue}\n`;
  }
  
  if (teamInfo.team.founded) {
    message += `<b>Fondazione:</b> ${teamInfo.team.founded}\n`;
  }
  
  if (teamInfo.team.colors) {
    message += `<b>Colori:</b> ${teamInfo.team.colors}\n`;
  }
  
  message += `\n<b>Prossime partite:</b>\n`;
  
  if (teamInfo.matches && teamInfo.matches.length > 0) {
    teamInfo.matches.slice(0, 3).forEach(match => {
      const matchDate = new Date(match.date).toLocaleDateString('it-IT', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
      
      message += `• ${match.homeTeam} vs ${match.awayTeam} (${matchDate})\n`;
    });
  } else {
    message += `Nessuna partita in programma\n`;
  }
  
  message += `\n<b>Ultime notizie:</b> ${teamInfo.news && teamInfo.news.length > 0 ? `${teamInfo.news.length} articoli recenti` : 'Nessuna notizia recente'}`;
  
  // Aggiungi avviso se stiamo usando dati mock
  if (!FOOTBALL_API_KEY) {
    message += `\n\n⚠️ <i>Dati dimostrativi - Configura FOOTBALL_API_KEY per informazioni reali</i>`;
  }
  
  bot.sendMessage(msg.chat.id, message, {
    parse_mode: "HTML",
    ...footballMenu(true, preferences.wantsFootballUpdates)
  });
}

// === BOT LOGIC ===
const userStates = {};

bot.onText(/^\/start/, (msg) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
  const tag = getAdminTag(msg);
  bot.sendMessage(
    msg.chat.id,
    `${tag}🚀 Benvenuto ${msg.from.first_name}!\n\nIo sono <b>ErixBot</b> 🤖\nSono qui per aiutarti!\n\nCosa vuoi fare oggi? Scegli una funzione:`,
    { ...mainMenu(isAdmin(msg)), parse_mode: "HTML" }
  );
});

bot.onText(/^\/help/, (msg) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
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
⚽ <b>Calcio</b> — Info sulla tua squadra preferita
🌤 <b>Meteo</b> — Informazioni meteorologiche
🎫 <b>Supporto</b> — Sistema di ticket di supporto
⚙️ <b>Impostazioni</b> — Configura le tue preferenze
📊 <b>Statistiche</b> — Statistiche del bot (solo admin)
❓ <b>Aiuto</b> — Spiega i comandi

<b>Se l'applicazione IPTV non funziona:</b>
• 📱 <b>Controlla il tuo stato di rete</b> - Assicurati di avere una connessione internet stabile
• 🔄 <b>Riavvia il dispositivo</b> - Spegni il dispositivo per 5-10 minuti e poi riprova
• 📺 <b>Riavvia l'applicazione</b> - Chiudi completamente l'app e riaprilia
• 🔌 <b>Controlla i cavi</b> - Verifica che tutti i cavi di rete siano collegati correttamente

<b>Se il problema persiste, apri un ticket di supporto tramite il menu "🎫 Supporto"</b>

<b>Tip:</b> Usa la tastiera qui sotto per scegliere più velocemente!`,
    { ...mainMenu(isAdmin(msg)), parse_mode: "HTML" }
  );
});

bot.onText(/^\/status/, async (msg) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
  const tag = getAdminTag(msg);
  const status = await checkServiceStatus();
  if (status === "ONLINE") {
    bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è ONLINE!</b> ✅`, { parse_mode: "HTML" });
  } else if (status === "OFFLINE") {
    bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è OFFLINE!</b> ❌`, { parse_mode: "HTML" });
  } else {
    bot.sendMessage(msg.chat.id, `${tag}⚠️ Impossibile verificare lo stato del servizio.`, { parse_mode: "HTML" });
  }
});

bot.onText(/^\/support/, (msg) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
  const tag = getAdminTag(msg);
  if (isAdmin(msg)) {
    bot.sendMessage(
      msg.chat.id,
      `${tag}🎫 <b>Pannello Supporto - Admin</b>\n\nGestisci i ticket di supporto degli utenti.`,
      { ...supportMenu(true), parse_mode: "HTML" }
    );
  } else {
    bot.sendMessage(
      msg.chat.id,
      `🎫 <b>Supporto Clienti</b>\n\nHai bisogno di assistenza? Apri un ticket e ti aiuteremo al più presto!`,
      { ...supportMenu(false), parse_mode: "HTML" }
    );
  }
});

bot.onText(/^\/calcio/, (msg) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
  const preferences = getUserPreferences(msg.from.id);
  let footballMessage = `⚽ <b>Menu Calcio</b>\n\n`;
  
  if (preferences.footballTeam) {
    footballMessage += `La tua squadra preferita: <b>${preferences.footballTeam}</b>\n`;
    footballMessage += `Notifiche: ${preferences.wantsFootballUpdates ? '🔔 ATTIVE' : '🔕 DISATTIVATE'}\n\n`;
    footballMessage += `Scegli un'opzione qui sotto:`;
  } else {
    footballMessage += `Non hai ancora impostato una squadra preferita.\n\nImpostala ora per ricevere notizie e informazioni sulle prossime partite!`;
  }
  
  bot.sendMessage(msg.chat.id, footballMessage, {
    ...footballMenu(!!preferences.footballTeam, preferences.wantsFootballUpdates),
    parse_mode: "HTML"
  });
});

bot.onText(/^\/stats/, (msg) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
  if (!isAdmin(msg)) {
    bot.sendMessage(msg.chat.id, "⛔ Solo gli amministratori possono vedere le statistiche.");
    return;
  }
  showStats(msg);
});

bot.onText(/^\/broadcast (.+)/, (msg, match) => {
  updateUserActivity(msg.from.id);
  incrementCommandCount();
  
  if (!isAdmin(msg)) {
    bot.sendMessage(msg.chat.id, "⛔ Solo gli amministratori possono usare il broadcast.");
    return;
  }
  
  const broadcastMessage = match[1];
  const users = loadUsers();
  const userIds = Object.keys(users);
  
  let sent = 0;
  let failed = 0;
  
  userIds.forEach(userId => {
    bot.sendMessage(userId, `📢 <b>Annuncio</b>\n\n${broadcastMessage}`, { 
      parse_mode: 'HTML' 
    }).then(() => {
      sent++;
    }).catch(() => {
      failed++;
    });
  });
  
  // Report dopo 5 secondi
  setTimeout(() => {
    bot.sendMessage(
      msg.chat.id,
      `📊 <b>Risultato Broadcast</b>\n\n` +
      `✅ Inviati: ${sent}\n` +
      `❌ Falliti: ${failed}\n` +
      `👥 Totale: ${userIds.length}`,
      { parse_mode: "HTML" }
    );
  }, 5000);
});

async function checkServiceStatus() {
  try {
    const res = await fetch("https://miglioriptvreseller.xyz/", { timeout: 5000 });
    const body = await res.text();
    if (
      res.status === 200 &&
      /iptv|reseller|login|username|abbonamento|dashboard|accesso|servizio/i.test(body)
    ) {
      return "ONLINE";
    } else {
      return "OFFLINE";
    }
  } catch (e) {
    return "OFFLINE";
  }
}

// === CALLBACK QUERY HANDLER (bottoni) ===
bot.on('callback_query', async query => {
  const msg = query.message;
  const userId = query.from.id;
  const tag = getAdminTag(query);
  
  // Aggiorna attività utente
  updateUserActivity(userId);
  incrementCommandCount();

  try {
    switch (query.data) {
      case "add":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        userStates[userId] = { awaitingAdd: true };
        bot.sendMessage(msg.chat.id, `${tag}➕ <b>Scrivi i dati per aggiungere:</b>\n<code>Nome 9.99 EUR 2025-10-31 [note]</code>`, { parse_mode: "HTML" });
        break;
      case "list":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        sendList(msg, userId, tag);
        break;
      case "renew":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        userStates[userId] = { awaitingRenew: true };
        bot.sendMessage(msg.chat.id, `${tag}🔁 <b>Scrivi:</b>\n<code>Nome 2026-01-31</code>`, { parse_mode: "HTML" });
        break;
      case "cancel":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        userStates[userId] = { awaitingCancel: true };
        bot.sendMessage(msg.chat.id, `${tag}🗑 <b>Scrivi il nome dell'abbonamento da eliminare:</b>`, { parse_mode: "HTML" });
        break;
      case "next":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        sendNext(msg, userId, tag);
        break;
      case "info":
        userStates[userId] = { awaitingInfo: true };
        bot.sendMessage(msg.chat.id, `${tag}🔎 <b>Scrivi il nome dell'abbonamento di cui vuoi vedere le info:</b>`, { parse_mode: "HTML" });
        break;
      case "status":
        const status = await checkServiceStatus();
        if (status === "ONLINE") {
          bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è ONLINE!</b> ✅`, { parse_mode: "HTML" });
        } else if (status === "OFFLINE") {
          bot.sendMessage(msg.chat.id, `${tag}🛰 <b>Il servizio IPTV è OFFLINE!</b> ❌`, { parse_mode: "HTML" });
        } else {
          bot.sendMessage(msg.chat.id, `${tag}⚠️ Impossibile verificare lo stato del servizio.`, { parse_mode: "HTML" });
        }
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
⚽ <b>Calcio</b> — Info sulla tua squadra preferita
🌤 <b>Meteo</b> — Informazioni meteorologiche
🎫 <b>Supporto</b> — Sistema di ticket di supporto
⚙️ <b>Impostazioni</b> — Configura le tue preferenze
📊 <b>Statistiche</b> — Statistiche del bot (solo admin)
❓ <b>Aiuto</b> — Spiega i comandi

<b>Se l'applicazione IPTV non funziona:</b>
• 📱 <b>Controlla il tuo stato di rete</b> - Assicurati di avere una connessione internet stabile
• 🔄 <b>Riavvia il dispositivo</b> - Spegni il dispositivo per 5-10 minuti e poi riprova
• 📺 <b>Riavvia l'applicazione</b> - Chiudi completamente l'app e riaprilia
• 🔌 <b>Controlla i cavi</b> - Verifica che tutti i cavi di rete siano collegati correttamente

<b>Se il problema persiste, apri un ticket di supporto tramite il menu "🎫 Supporto"</b>

<b>Tip:</b> Usa la tastiera qui sotto per scegliere più velocemente!`,
          { ...mainMenu(isAdmin(query)), parse_mode: "HTML" }
        );
        break;
      case "support":
        if (isAdmin(query)) {
          bot.sendMessage(
            msg.chat.id,
            `${tag}🎫 <b>Pannello Supporto - Admin</b>\n\nGestisci i ticket di supporto degli utenti.`,
            { ...supportMenu(true), parse_mode: "HTML" }
          );
        } else {
          bot.sendMessage(
            msg.chat.id,
            `🎫 <b>Supporto Clienti</b>\n\nHai bisogno di assistenza? Apri un ticket e ti aiuteremo al più presto!`,
            { ...supportMenu(false), parse_mode: "HTML" }
          );
        }
        break;
      case "football":
        const preferences = getUserPreferences(userId);
        let footballMessage = `⚽ <b>Menu Calcio</b>\n\n`;
        
        if (preferences.footballTeam) {
          footballMessage += `La tua squadra preferita: <b>${preferences.footballTeam}</b>\n`;
          footballMessage += `Notifiche: ${preferences.wantsFootballUpdates ? '🔔 ATTIVE' : '🔕 DISATTIVATE'}\n\n`;
          footballMessage += `Scegli un'opzione qui sotto:`;
        } else {
          footballMessage += `Non hai ancora impostato una squadra preferita.\n\nImpostala ora per ricevere notizie e informazioni sulle prossime partite!`;
        }
        
        bot.sendMessage(msg.chat.id, footballMessage, {
          ...footballMenu(!!preferences.footballTeam, preferences.wantsFootballUpdates),
          parse_mode: "HTML"
        });
        break;
      case "main_menu":
        bot.sendMessage(
          msg.chat.id,
          `${tag}🚀 <b>Menu Principale</b>\n\nCosa vuoi fare?`,
          { ...mainMenu(isAdmin(query)), parse_mode: "HTML" }
        );
        break;
      case "open_ticket":
        if (isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "❌ Gli admin non possono aprire ticket!", show_alert: true });
          return;
        }
        userStates[userId] = { awaitingTicket: true };
        bot.sendMessage(
          msg.chat.id,
          `📝 <b>Apri un Ticket di Supporto</b>\n\nDescrivi il tuo problema o la tua richiesta. Sarai ricontattato al più presto!`,
          { parse_mode: "HTML" }
        );
        break;
      case "my_tickets":
        if (isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "❌ Funzione solo per utenti!", show_alert: true });
          return;
        }
        showUserTickets(msg, userId);
        break;
      case "admin_tickets_open":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        showAdminTickets(msg, 'open');
        break;
      case "admin_tickets_assigned":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        showAdminTickets(msg, 'assigned');
        break;
      case "admin_tickets_closed":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        showAdminTickets(msg, 'closed');
        break;
      case "set_football_team":
        userStates[userId] = { awaitingFootballTeam: true };
        bot.sendMessage(
          msg.chat.id,
          `⚽ <b>Imposta la tua squadra preferita</b>\n\nScrivi il nome della tua squadra di calcio preferita:\n\n<code>Esempi: Milan, Inter, Juventus, Roma, Napoli, Lazio, Fiorentina, Atalanta, Bologna</code>`,
          { parse_mode: "HTML" }
        );
        break;
      case "enable_football_updates":
        saveUserPreferences(userId, { wantsFootballUpdates: true });
        bot.sendMessage(
          msg.chat.id,
          `🔔 <b>Notifiche calcio attivate!</b>\n\nRiceverai aggiornamenti sulla tua squadra preferita.`,
          { ...footballMenu(true, true), parse_mode: "HTML" }
        );
        break;
      case "disable_football_updates":
        saveUserPreferences(userId, { wantsFootballUpdates: false });
        bot.sendMessage(
          msg.chat.id,
          `🔕 <b>Notifiche calcio disattivate!</b>\n\nNon riceverai più aggiornamenti automatici.`,
          { ...footballMenu(true, false), parse_mode: "HTML" }
        );
        break;
      case "football_news":
        await sendFootballNews(msg, userId);
        break;
      case "football_matches":
        await sendFootballMatches(msg, userId);
        break;
      case "football_info":
        await sendFootballInfo(msg, userId);
        break;
      case "football_info_now":
        await sendFootballInfo(msg, userId);
        break;
      case "weather":
        const weather = await getWeather();
        if (weather) {
          const emoji = weather.condition.includes('sole') ? '☀️' : 
                       weather.condition.includes('piogg') ? '🌧️' : 
                       weather.condition.includes('nuvol') ? '☁️' : '🌈';
          
          bot.sendMessage(
            msg.chat.id,
            `${emoji} <b>Meteo a ${weather.city}</b>\n\n` +
            `🌡️ Temperatura: ${weather.temperature}°C\n` +
            `☁️ Condizioni: ${weather.condition}\n` +
            `💧 Umidità: ${weather.humidity}%`,
            { parse_mode: 'HTML' }
          );
        } else {
          bot.sendMessage(msg.chat.id, "❌ Impossibile recuperare i dati meteo.");
        }
        break;
      case "settings":
        bot.sendMessage(
          msg.chat.id,
          "⚙️ <b>Impostazioni</b>\n\nConfigura le tue preferenze:",
          { 
            parse_mode: 'HTML',
            ...settingsMenu(userId)
          }
        );
        break;
      case "toggle_notifications":
        const prefs = getUserPreferences(userId);
        saveUserPreferences(userId, { notifications: !prefs.notifications });
        
        bot.sendMessage(
          msg.chat.id,
          `✅ Notifiche ${!prefs.notifications ? 'attivate' : 'disattivate'}!`,
          { 
            parse_mode: 'HTML',
            ...settingsMenu(userId)
          }
        );
        break;
      case "my_stats":
        const userStats = getUserPreferences(userId);
        const userTickets = loadTickets().filter(t => t.userId === userId);
        
        const statsMessage = `📊 <b>Le tue Statistiche</b>\n\n` +
          `👤 <b>Utente dal:</b> ${new Date(userStats.createdAt).toLocaleDateString('it-IT')}\n` +
          `🕒 <b>Ultima attività:</b> ${new Date(userStats.lastActivity).toLocaleDateString('it-IT')}\n` +
          `🎫 <b>Ticket aperti:</b> ${userTickets.length}\n` +
          `⚽ <b>Squadra preferita:</b> ${userStats.footballTeam || 'Non impostata'}\n` +
          `🔔 <b>Notifiche:</b> ${userStats.notifications ? 'ON' : 'OFF'}`;
        
        bot.sendMessage(msg.chat.id, statsMessage, { 
          parse_mode: 'HTML',
          ...settingsMenu(userId)
        });
        break;
      case "stats":
        if (!isAdmin(query)) {
          bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
          return;
        }
        showStats(msg);
        break;
    }

    // Gestione azioni sui ticket
    if (query.data.startsWith('assign_')) {
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
        return;
      }
      const ticketId = query.data.replace('assign_', '');
      assignTicket(msg, ticketId, userId, query.from.first_name);
    }
    
    if (query.data.startsWith('reply_')) {
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
        return;
      }
      const ticketId = query.data.replace('reply_', '');
      userStates[userId] = { awaitingTicketReply: ticketId };
      bot.sendMessage(
        msg.chat.id,
        `💬 <b>Rispondi al Ticket ${ticketId}</b>\n\nScrivi la tua risposta:`,
        { parse_mode: "HTML" }
      );
    }
    
    if (query.data.startsWith('close_')) {
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo gli amministratori!", show_alert: true });
        return;
      }
      const ticketId = query.data.replace('close_', '');
      closeTicket(msg, ticketId, userId);
    }
    
    if (query.data.startsWith('view_')) {
      const ticketId = query.data.replace('view_', '');
      viewTicket(msg, ticketId, isAdmin(query));
    }

    // Gestione risposta utente ai ticket
    if (query.data.startsWith('user_reply_')) {
      const ticketId = query.data.replace('user_reply_', '');
      
      // Verifica che l'utente sia il proprietario del ticket
      const tickets = loadTickets();
      const ticket = tickets.find(t => t.id === ticketId);
      
      if (!ticket) {
        bot.answerCallbackQuery(query.id, { text: "❌ Ticket non trovato!", show_alert: true });
        return;
      }
      
      if (ticket.userId !== userId) {
        bot.answerCallbackQuery(query.id, { text: "❌ Non puoi rispondere a questo ticket!", show_alert: true });
        return;
      }
      
      if (ticket.status === 'closed') {
        bot.answerCallbackQuery(query.id, { text: "❌ Il ticket è chiuso, non puoi rispondere!", show_alert: true });
        return;
      }
      
      userStates[userId] = { awaitingUserTicketReply: ticketId };
      bot.sendMessage(
        msg.chat.id,
        `💬 <b>Rispondi al Ticket ${ticketId}</b>\n\nScrivi la tua risposta per lo staff:`,
        { parse_mode: "HTML" }
      );
    }
  } catch (error) {
    log('ERROR', 'Errore nel callback handler', { 
      userId: query.from.id, 
      data: query.data,
      error: error.message 
    });
    
    bot.answerCallbackQuery(query.id, { 
      text: "❌ Si è verificato un errore. Riprova più tardi.", 
      show_alert: true 
    });
  }

  bot.answerCallbackQuery(query.id);
});

// === GESTIONE RISPOSTE UTENTE PER STATI ===
bot.on('message', (msg) => {
  // Ignora i messaggi che non sono testo
  if (!msg.text) return;
  
  const userId = msg.from.id;
  const tag = getAdminTag(msg);

  // Aggiorna attività utente per tutti i messaggi
  updateUserActivity(userId);
  incrementCommandCount();

  // ADD
  if (userStates[userId] && userStates[userId].awaitingAdd) {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "⛔ Solo gli amministratori possono usare questa funzione.");
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
      bot.sendMessage(msg.chat.id, "⛔ Solo gli amministratori possono usare questa funzione.");
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
      bot.sendMessage(msg.chat.id, "⛔ Solo gli amministratori possono usare questa funzione.");
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
    
    let data;
    if (isAdmin(msg)) {
      // Admin vede tutti gli abbonamenti con quel nome
      data = loadData().filter(x => x.name.toLowerCase() === abboName.toLowerCase());
    } else {
      // Utenti normali vedono tutti gli abbonamenti con quel nome (senza filtro userId)
      data = loadData().filter(x => x.name.toLowerCase() === abboName.toLowerCase());
    }

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

  // GESTIONE TICKET - APERTURA
  if (userStates[userId] && userStates[userId].awaitingTicket) {
    if (isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "❌ Gli admin non possono aprire ticket!");
      delete userStates[userId];
      return;
    }
    
    const ticketText = msg.text.trim();
    if (!ticketText) {
      bot.sendMessage(msg.chat.id, "❌ Il messaggio non può essere vuoto!");
      return;
    }
    
    const tickets = loadTickets();
    const ticketId = generateTicketId();
    
    const newTicket = {
      id: ticketId,
      userId: userId,
      userName: msg.from.first_name + (msg.from.username ? ` (@${msg.from.username})` : ''),
      subject: ticketText,
      status: 'open',
      assignedTo: null,
      assignedAdmin: null,
      createdAt: nowISO(),
      updatedAt: nowISO(),
      replies: []
    };
    
    tickets.push(newTicket);
    saveTickets(tickets);
    
    // Conferma all'utente
    bot.sendMessage(
      msg.chat.id,
      `✅ <b>Ticket Aperto!</b>\n\n<b>ID:</b> ${ticketId}\n<b>Stato:</b> 🟡 Aperto\n\nIl nostro staff ti risponderà al più presto. Puoi controllare lo stato dal menu Supporto.`,
      { ...supportMenu(false), parse_mode: "HTML" }
    );
    
    // Notifica agli admin
    ADMIN_IDS.forEach(adminId => {
      bot.sendMessage(
        adminId,
        `🎫 <b>Nuovo Ticket Aperto!</b>\n\n<b>ID:</b> ${ticketId}\n<b>Utente:</b> ${newTicket.userName}\n<b>Richiesta:</b>\n${ticketText}`,
        { 
          parse_mode: "HTML",
          reply_markup: {
            inline_keyboard: [
              [{ text: "📋 Vedi Ticket", callback_data: `view_${ticketId}` }]
            ]
          }
        }
      ).catch(console.error);
    });
    
    delete userStates[userId];
    return;
  }
  
  // GESTIONE TICKET - RISPOSTA ADMIN
  if (userStates[userId] && userStates[userId].awaitingTicketReply) {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "⛔ Solo gli amministratori possono usare questa funzione.");
      delete userStates[userId];
      return;
    }
    
    const ticketId = userStates[userId].awaitingTicketReply;
    const replyText = msg.text.trim();
    
    if (!replyText) {
      bot.sendMessage(msg.chat.id, "❌ La risposta non può essere vuota!");
      return;
    }
    
    sendAdminReply(msg, ticketId, replyText, msg.from.first_name);
    delete userStates[userId];
    return;
  }

  // GESTIONE TICKET - RISPOSTA UTENTE
  if (userStates[userId] && userStates[userId].awaitingUserTicketReply) {
    const ticketId = userStates[userId].awaitingUserTicketReply;
    const replyText = msg.text.trim();
    
    if (!replyText) {
      bot.sendMessage(msg.chat.id, "❌ La risposta non può essere vuota!");
      return;
    }
    
    sendUserReply(msg, ticketId, replyText);
    delete userStates[userId];
    return;
  }

  // GESTIONE SQUADRA DI CALCIO
  if (userStates[userId] && userStates[userId].awaitingFootballTeam) {
    const teamName = msg.text.trim();
    
    if (!teamName) {
      bot.sendMessage(msg.chat.id, "❌ Il nome della squadra non può essere vuoto!");
      return;
    }
    
    // Normalizza il nome della squadra
    const normalizedTeamName = normalizeTeamName(teamName);
    
    // Salva la squadra preferita
    saveUserPreferences(userId, { footballTeam: normalizedTeamName });
    
    // Chiedi se vuole notifiche
    userStates[userId] = { awaitingFootballUpdates: true };
    
    bot.sendMessage(
      msg.chat.id,
      `✅ <b>Squadra impostata:</b> ${normalizedTeamName}\n\nVuoi ricevere notizie e informazioni sulle prossime partite di questa squadra?`,
      {
        reply_markup: {
          inline_keyboard: [
            [
              { text: "✅ Sì, attiva notifiche", callback_data: "enable_football_updates" },
              { text: "❌ No, solo informazioni", callback_data: "football_info_now" }
            ]
          ]
        },
        parse_mode: "HTML"
      }
    );
    return;
  }

  // Messaggi di default solo se non sono callback
  if (!msg.text.startsWith('/') && !msg.text.startsWith('➕') && !msg.text.startsWith('📖') && !msg.text.startsWith('🔁') && !msg.text.startsWith('🗑') && !msg.text.startsWith('⏳') && !msg.text.startsWith('🔎') && !msg.text.startsWith('🛰') && !msg.text.startsWith('🎫') && !msg.text.startsWith('❓') && !msg.text.startsWith('⚽') && !msg.text.startsWith('🌤') && !msg.text.startsWith('⚙️') && !msg.text.startsWith('📊')) {
    return;
  }
  const known = ['/start','/help','/add','/list','/renew','/cancel','/next','/info','/status','/support','/calcio','/stats','/broadcast'];
  if (!known.some(cmd => msg.text.startsWith(cmd))) {
    bot.sendMessage(msg.chat.id, `🤔 <b>Comando non riconosciuto!</b>\nUsa la tastiera qui sotto 👇`, { ...mainMenu(isAdmin(msg)), parse_mode: "HTML" });
  }
});

// === ADMIN-ONLY COMMANDS ===
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

// === WEBHOOK EXPRESS HANDLER ===
app.post('/', (req, res) => {
  bot.processUpdate(req.body);
  res.sendStatus(200);
});

// === MIDDLEWARE DI SICUREZZA ===
app.use((req, res, next) => {
  const ip = req.ip || req.connection.remoteAddress;
  log('INFO', 'Richiesta webhook', { ip, path: req.path });
  next();
});

// === ENDPOINT DI SALUTE ===
app.get('/health', (req, res) => {
  const stats = loadStats();
  res.json({
    status: 'ok',
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    stats: stats
  });
});

// === ENDPOINT PER LOG (solo admin) ===
app.get('/logs', (req, res) => {
  const auth = req.headers.authorization;
  if (!auth || auth !== `Bearer ${process.env.ADMIN_TOKEN}`) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  
  try {
    const logs = fs.existsSync(LOG_FILE) 
      ? fs.readFileSync(LOG_FILE, 'utf8').split('\n').filter(line => line).map(JSON.parse)
      : [];
    
    res.json({ logs });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// === GESTIONE ERRORI GLOBALE ===
process.on('uncaughtException', (error) => {
  log('CRITICAL', 'Eccezione non gestita', { error: error.message, stack: error.stack });
});

process.on('unhandledRejection', (reason, promise) => {
  log('CRITICAL', 'Promise rejection non gestita', { reason: reason.toString() });
});

// === WEBHOOK SETUP ===
bot.setWebHook(`${WEBHOOK_URL}`);

// === INIZIALIZZAZIONE ===
app.listen(PORT, () => {
  log('INFO', `Bot server avviato sulla porta ${PORT}`);
  log('INFO', `Admin IDs configurati: ${ADMIN_IDS.join(', ')}`);
  
  // Backup iniziale
  createBackup();
  
  // Invio notifica di avvio agli admin
  ADMIN_IDS.forEach(adminId => {
    bot.sendMessage(adminId, '🤖 <b>Bot avviato con successo!</b>', { parse_mode: 'HTML' }).catch(console.error);
  });
});
