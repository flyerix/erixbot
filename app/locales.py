"""
Sistema di localizzazione per il bot Telegram
Supporta italiano e inglese con fallback automatico
"""

import json
import os
from typing import Dict, Any

class LocalizationManager:
    """Gestore della localizzazione per testi del bot"""

    def __init__(self, default_language: str = 'it'):
        self.default_language = default_language
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.load_translations()

    def load_translations(self):
        """Carica i file di traduzione"""
        locales_dir = os.path.join(os.path.dirname(__file__), 'locales')

        # Crea directory se non esiste
        os.makedirs(locales_dir, exist_ok=True)

        # Carica traduzioni per ogni lingua
        for lang_file in ['it.json', 'en.json']:
            lang_code = lang_file.split('.')[0]
            file_path = os.path.join(locales_dir, lang_file)

            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                    print(f"Traduzioni caricate per {lang_code}")
                else:
                    # Crea file di default se non esiste
                    self._create_default_translations(lang_code, file_path)
            except Exception as e:
                print(f"Errore caricamento traduzioni {lang_code}: {e}")
                self.translations[lang_code] = {}

    def _create_default_translations(self, lang_code: str, file_path: str):
        """Crea file di traduzioni di default"""
        if lang_code == 'it':
            translations = {
                "welcome": {
                    "title": "🎉 Benvenuto nel Bot di Gestione Liste!",
                    "stats": "📊 Statistiche Sistema:",
                    "active_lists": "📋 Liste attive: {count}",
                    "open_tickets": "🎫 Ticket aperti: {count}",
                    "actions": "💡 Cosa posso fare per te?"
                },
                "buttons": {
                    "search_list": "🔍 Cerca Lista",
                    "ticket_support": "🎫 Ticket Assistenza",
                    "personal_dashboard": "📊 Dashboard Personale",
                    "help_guide": "❓ Guida & Aiuto",
                    "admin_panel": "⚙️ Admin Panel",
                    "back": "⬅️ Indietro",
                    "continue": "💬 Continua Conversazione",
                    "close_ticket": "✅ Problema Risolto",
                    "contact_admin": "👨‍💼 Parla con Admin"
                },
                "ticket": {
                    "created": "🎫 Ticket #{id} creato!",
                    "ai_response": "🤖 Risposta AI:",
                    "open_conversation": "💬 Questa conversazione rimane aperta!",
                    "escalated": "👨‍💼 Un amministratore ti contatterà presto per assistenza personalizzata."
                },
                "help": {
                    "title": "❓ Guida Completa del Bot",
                    "search_section": "🔍 Cerca Liste:",
                    "ticket_section": "🎫 Sistema Ticket:",
                    "notifications_section": "🔔 Notifiche Scadenza:",
                    "admin_section": "⚙️ Admin Panel (Solo Admin):",
                    "tips": "💡 Suggerimenti:"
                },
                "errors": {
                    "generic": "❌ Si è verificato un errore. Riprova più tardi.",
                    "not_found": "❌ {item} non trovato.",
                    "access_denied": "❌ Accesso negato!",
                    "rate_limit": "⚠️ Troppe richieste! Attendi qualche minuto prima di riprovare."
                }
            }
        else:  # English
            translations = {
                "welcome": {
                    "title": "🎉 Welcome to the List Management Bot!",
                    "stats": "📊 System Statistics:",
                    "active_lists": "📋 Active lists: {count}",
                    "open_tickets": "🎫 Open tickets: {count}",
                    "actions": "💡 What can I do for you?"
                },
                "buttons": {
                    "search_list": "🔍 Search List",
                    "ticket_support": "🎫 Support Ticket",
                    "personal_dashboard": "📊 Personal Dashboard",
                    "help_guide": "❓ Help & Guide",
                    "admin_panel": "⚙️ Admin Panel",
                    "back": "⬅️ Back",
                    "continue": "💬 Continue Conversation",
                    "close_ticket": "✅ Problem Solved",
                    "contact_admin": "👨‍💼 Contact Admin"
                },
                "ticket": {
                    "created": "🎫 Ticket #{id} created!",
                    "ai_response": "🤖 AI Response:",
                    "open_conversation": "💬 This conversation remains open!",
                    "escalated": "👨‍💼 An administrator will contact you soon for personalized assistance."
                },
                "help": {
                    "title": "❓ Complete Bot Guide",
                    "search_section": "🔍 Search Lists:",
                    "ticket_section": "🎫 Ticket System:",
                    "notifications_section": "🔔 Expiry Notifications:",
                    "admin_section": "⚙️ Admin Panel (Admin Only):",
                    "tips": "💡 Tips:"
                },
                "errors": {
                    "generic": "❌ An error occurred. Please try again later.",
                    "not_found": "❌ {item} not found.",
                    "access_denied": "❌ Access denied!",
                    "rate_limit": "⚠️ Too many requests! Please wait a few minutes before trying again."
                }
            }

        # Salva il file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(translations, f, ensure_ascii=False, indent=2)

        self.translations[lang_code] = translations
        print(f"✅ File traduzioni creato per {lang_code}")

    def get_text(self, key: str, language: str = None, **kwargs) -> str:
        """Ottieni testo tradotto con sostituzioni"""
        if not language:
            language = self.default_language

        # Naviga nella struttura delle traduzioni
        keys = key.split('.')
        value = self.translations.get(language, {})

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, {})
            else:
                break

        # Se non trova la traduzione, prova con la lingua di default
        if not value and language != self.default_language:
            value = self.translations.get(self.default_language, {})
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k, {})
                else:
                    break

        # Se ancora non trova, restituisci la chiave
        if not value:
            return key

        # Se è una stringa, applica le sostituzioni
        if isinstance(value, str):
            return value.format(**kwargs)

        return str(value)

    def get_button_text(self, button_key: str, language: str = None) -> str:
        """Ottieni testo per un pulsante"""
        return self.get_text(f"buttons.{button_key}", language)

# Istanza globale del gestore localizzazione
localization = LocalizationManager()
