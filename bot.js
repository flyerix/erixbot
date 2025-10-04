const TelegramBot = require('node-telegram-bot-api');
const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const fetch = require('node-fetch');

// === CONFIG ===
const TOKEN = process.env.TELEGRAM_TOKEN;
const WEBHOOK_URL = process.env.WEBHOOK_URL;
const PORT = process.env.PORT || 3000;
const ADMIN_ID = 691735614;
const DATA_FILE = path.join(__dirname, 'data.json');
const TICKETS_FILE = path.join(__dirname, 'tickets.json');
const USERS_FILE = path.join(__dirname, 'users.json');
const BASE_TIMEZONE = 'Europe/Rome';
const FOOTBALL_API_KEY = process.env.FOOTBALL_API_KEY;
const NEWS_API_KEY = process.env.NEWS_API_KEY;

// === BOT SETUP ===
const bot = new TelegramBot(TOKEN, { webHook: true });
const app = express();
app.use(bodyParser.json());

// === UTILS ===
function loadData() {
  if (!fs.existsSync(DATA_FILE)) return [];
  return JSON.parse(fs.readFileSync(DATA_FILE));
}

function saveData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

function loadTickets() {
  if (!fs.existsSync(TICKETS_FILE)) return [];
  return JSON.parse(fs.readFileSync(TICKETS_FILE));
}

function saveTickets(tickets) {
  fs.writeFileSync(TICKETS_FILE, JSON.stringify(tickets, null, 2));
}

function loadUsers() {
  if (!fs.existsSync(USERS_FILE)) return {};
  return JSON.parse(fs.readFileSync(USERS_FILE));
}

function saveUsers(users) {
  fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
}

function getUserPreferences(userId) {
  const users = loadUsers();
  return users[userId] || { footballTeam: null, wantsFootballUpdates: false };
}

function saveUserPreferences(userId, preferences) {
  const users = loadUsers();
  users[userId] = { ...getUserPreferences(userId), ...preferences };
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
  return msg.from && msg.from.id === ADMIN_ID;
}

function getAdminTag(msg) {
  return isAdmin(msg) ? "👑 [ADMIN] " : "";
}

function generateTicketId() {
  return 'T' + Date.now() + Math.random().toString(36).substr(2, 5).toUpperCase();
}

// Mappatura squadre italiane comuni
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
  'salernitana': 'Salernitana Calcio'
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
    { text: "⚽ Calcio", callback_data: "football" },
    { text: "🎫 Supporto", callback_data: "support" }
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

// === WEBHOOK EXPRESS HANDLER ===
app.post('/', (req, res) => {
  bot.processUpdate(req.body);
  res.sendStatus(200);
});

// === BOT LOGIC ===
const userStates = {};

bot.onText(/^\/start/, (msg) => {
  const tag = getAdminTag(msg);
  bot.sendMessage(
    msg.chat.id,
    `${tag}🚀 Benvenuto ${msg.from.first_name}!\n\nIo sono <b>ErixBot</b> 🤖\nSono qui per aiutarti!\n\nCosa vuoi fare oggi? Scegli una funzione:`,
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
⚽ <b>Calcio</b> — Info sulla tua squadra preferita
🎫 <b>Supporto</b> — Sistema di ticket di supporto
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
🎫 <b>Supporto</b> — Sistema di ticket di supporto
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
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      showAdminTickets(msg, 'open');
      break;
    case "admin_tickets_assigned":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
        return;
      }
      showAdminTickets(msg, 'assigned');
      break;
    case "admin_tickets_closed":
      if (!isAdmin(query)) {
        bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
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
  }

  // Gestione azioni sui ticket
  if (query.data.startsWith('assign_')) {
    if (!isAdmin(query)) {
      bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
      return;
    }
    const ticketId = query.data.replace('assign_', '');
    assignTicket(msg, ticketId, userId, query.from.first_name);
  }
  
  if (query.data.startsWith('reply_')) {
    if (!isAdmin(query)) {
      bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
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
      bot.answerCallbackQuery(query.id, { text: "⛔ Solo l'amministratore!", show_alert: true });
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

  bot.answerCallbackQuery(query.id);
});

// === GESTIONE RISPOSTE UTENTE PER STATI ===
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
    
    // Notifica all'admin
    bot.sendMessage(
      ADMIN_ID,
      `🎫 <b>Nuovo Ticket Aperto!</b>\n\n<b>ID:</b> ${ticketId}\n<b>Utente:</b> ${newTicket.userName}\n<b>Richiesta:</b>\n${ticketText}`,
      { 
        parse_mode: "HTML",
        reply_markup: {
          inline_keyboard: [
            [{ text: "📋 Vedi Ticket", callback_data: `view_${ticketId}` }]
          ]
        }
      }
    );
    
    delete userStates[userId];
    return;
  }
  
  // GESTIONE TICKET - RISPOSTA ADMIN
  if (userStates[userId] && userStates[userId].awaitingTicketReply) {
    if (!isAdmin(msg)) {
      bot.sendMessage(msg.chat.id, "⛔ Solo l'amministratore può usare questa funzione.");
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
  if (!msg.text.startsWith('/') && !msg.text.startsWith('➕') && !msg.text.startsWith('📖') && !msg.text.startsWith('🔁') && !msg.text.startsWith('🗑') && !msg.text.startsWith('⏳') && !msg.text.startsWith('🔎') && !msg.text.startsWith('🛰') && !msg.text.startsWith('🎫') && !msg.text.startsWith('❓') && !msg.text.startsWith('⚽')) {
    return;
  }
  const known = ['/start','/help','/add','/list','/renew','/cancel','/next','/info','/status','/support','/calcio'];
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

// === WEBHOOK SETUP ===
bot.setWebHook(`${WEBHOOK_URL}`);

app.listen(PORT, () => {
  console.log(`Bot server listening on port ${PORT}`);
});
