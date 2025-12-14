"""
Enhanced UI Service
Dynamic and personalized user interface components
"""
import logging
from datetime import datetime, timezone
from collections import defaultdict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from models import SessionLocal, Ticket, List, UserActivity
from sqlalchemy import and_, desc, func

logger = logging.getLogger(__name__)

class UIService:
    """Enhanced UI service with dynamic and personalized interfaces"""
    
    def __init__(self):
        self.user_preferences = {}
        self.quick_actions = {}
        self.custom_shortcuts = defaultdict(list)
        self.ui_themes = {
            'default': {
                'primary_emoji': '🤖',
                'success_emoji': '✅',
                'warning_emoji': '⚠️',
                'error_emoji': '❌',
                'info_emoji': 'ℹ️'
            },
            'dark': {
                'primary_emoji': '🌙',
                'success_emoji': '🟢',
                'warning_emoji': '🟡',
                'error_emoji': '🔴',
                'info_emoji': '🔵'
            },
            'colorful': {
                'primary_emoji': '🌈',
                'success_emoji': '🎉',
                'warning_emoji': '⚡',
                'error_emoji': '💥',
                'info_emoji': '💡'
            }
        }
    
    def get_dynamic_main_menu(self, user_id, user_lang='it'):
        """Generate dynamic main menu based on user behavior and preferences"""
        try:
            # Get user activity patterns
            user_patterns = self._analyze_user_patterns(user_id)
            theme = self._get_user_theme(user_id)
            
            # Base menu items
            menu_items = []
            
            # Most used actions first
            if 'search_lists' in user_patterns['frequent_actions']:
                menu_items.append([
                    InlineKeyboardButton(
                        f"{theme['primary_emoji']} Cerca Liste IPTV",
                        callback_data='search_lists'
                    )
                ])
            
            if 'create_ticket' in user_patterns['frequent_actions']:
                menu_items.append([
                    InlineKeyboardButton(
                        f"🎫 Assistenza Rapida",
                        callback_data='quick_support'
                    )
                ])
            
            # Standard menu items
            menu_items.extend([
                [
                    InlineKeyboardButton("📋 Tutte le Liste", callback_data='view_all_lists'),
                    InlineKeyboardButton("🎫 I Miei Ticket", callback_data='my_tickets')
                ],
                [
                    InlineKeyboardButton("📞 Contatta Admin", callback_data='contact_admin'),
                    InlineKeyboardButton("❓ Aiuto", callback_data='help')
                ]
            ])
            
            # Add personalized shortcuts
            shortcuts = self._get_user_shortcuts(user_id)
            if shortcuts:
                menu_items.append([
                    InlineKeyboardButton("⚡ Azioni Rapide", callback_data='quick_actions')
                ])
            
            # Add settings
            menu_items.append([
                InlineKeyboardButton("⚙️ Impostazioni", callback_data='user_settings')
            ])
            
            return InlineKeyboardMarkup(menu_items)
            
        except Exception as e:
            logger.error(f"Error generating dynamic menu: {e}")
            return self._get_fallback_menu()
    
    def get_smart_ticket_menu(self, user_id, ticket_id=None):
        """Generate smart ticket interface based on context"""
        try:
            theme = self._get_user_theme(user_id)
            menu_items = []
            
            if ticket_id:
                # Existing ticket menu
                menu_items.extend([
                    [
                        InlineKeyboardButton(
                            f"{theme['info_emoji']} Dettagli Ticket",
                            callback_data=f'ticket_details_{ticket_id}'
                        )
                    ],
                    [
                        InlineKeyboardButton("💬 Aggiungi Messaggio", callback_data=f'add_message_{ticket_id}'),
                        InlineKeyboardButton("📎 Allega File", callback_data=f'attach_file_{ticket_id}')
                    ],
                    [
                        InlineKeyboardButton(f"{theme['success_emoji']} Risolto", callback_data=f'close_ticket_{ticket_id}'),
                        InlineKeyboardButton("🔄 Aggiorna", callback_data=f'refresh_ticket_{ticket_id}')
                    ]
                ])
            else:
                # New ticket menu with smart categories
                user_history = self._get_user_issue_history(user_id)
                
                # Suggest categories based on history
                if 'streaming' in user_history:
                    menu_items.append([
                        InlineKeyboardButton("📺 Problema Streaming", callback_data='new_ticket_streaming')
                    ])
                
                if 'login' in user_history:
                    menu_items.append([
                        InlineKeyboardButton("🔐 Problema Accesso", callback_data='new_ticket_login')
                    ])
                
                # Standard categories
                menu_items.extend([
                    [
                        InlineKeyboardButton("💳 Pagamenti", callback_data='new_ticket_payment'),
                        InlineKeyboardButton("📋 Liste", callback_data='new_ticket_lists')
                    ],
                    [
                        InlineKeyboardButton("🔧 Tecnico", callback_data='new_ticket_technical'),
                        InlineKeyboardButton("❓ Altro", callback_data='new_ticket_other')
                    ]
                ])
            
            # Add back button
            menu_items.append([
                InlineKeyboardButton("🔙 Indietro", callback_data='main_menu')
            ])
            
            return InlineKeyboardMarkup(menu_items)
            
        except Exception as e:
            logger.error(f"Error generating ticket menu: {e}")
            return self._get_fallback_ticket_menu()
    
    def get_admin_dashboard_menu(self, admin_id):
        """Generate admin dashboard with priority items first"""
        try:
            theme = self._get_user_theme(admin_id)
            
            # Get urgent items count
            urgent_counts = self._get_urgent_counts()
            
            menu_items = []
            
            # Urgent items first
            if urgent_counts['escalated_tickets'] > 0:
                menu_items.append([
                    InlineKeyboardButton(
                        f"🚨 Ticket Escalati ({urgent_counts['escalated_tickets']})",
                        callback_data='admin_escalated_tickets'
                    )
                ])
            
            if urgent_counts['pending_renewals'] > 0:
                menu_items.append([
                    InlineKeyboardButton(
                        f"📝 Rinnovi Pendenti ({urgent_counts['pending_renewals']})",
                        callback_data='admin_pending_renewals'
                    )
                ])
            
            # Standard admin menu
            menu_items.extend([
                [
                    InlineKeyboardButton("📊 Dashboard Analytics", callback_data='admin_analytics'),
                    InlineKeyboardButton("👥 Gestione Utenti", callback_data='admin_users')
                ],
                [
                    InlineKeyboardButton("📋 Gestione Liste", callback_data='admin_lists'),
                    InlineKeyboardButton("🎫 Tutti i Ticket", callback_data='admin_all_tickets')
                ],
                [
                    InlineKeyboardButton("🛡️ Sicurezza", callback_data='admin_security'),
                    InlineKeyboardButton("⚙️ Impostazioni", callback_data='admin_settings')
                ],
                [
                    InlineKeyboardButton("📈 Report", callback_data='admin_reports'),
                    InlineKeyboardButton("🔧 Manutenzione", callback_data='admin_maintenance')
                ]
            ])
            
            return InlineKeyboardMarkup(menu_items)
            
        except Exception as e:
            logger.error(f"Error generating admin menu: {e}")
            return self._get_fallback_admin_menu()
    
    def get_personalized_list_view(self, user_id, lists_data, page=1, per_page=5):
        """Generate personalized list view with smart sorting"""
        try:
            theme = self._get_user_theme(user_id)
            user_preferences = self._get_user_list_preferences(user_id)
            
            # Sort lists based on user preferences
            sorted_lists = self._sort_lists_for_user(lists_data, user_preferences)
            
            # Pagination
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_lists = sorted_lists[start_idx:end_idx]
            
            menu_items = []
            
            # List items
            for lst in page_lists:
                # Smart list display with user-relevant info
                list_info = self._format_list_info(lst, user_preferences)
                menu_items.append([
                    InlineKeyboardButton(
                        list_info,
                        callback_data=f'list_details_{lst.id}'
                    )
                ])
            
            # Pagination controls
            nav_buttons = []
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton("⬅️ Precedente", callback_data=f'lists_page_{page-1}')
                )
            
            if end_idx < len(sorted_lists):
                nav_buttons.append(
                    InlineKeyboardButton("➡️ Successiva", callback_data=f'lists_page_{page+1}')
                )
            
            if nav_buttons:
                menu_items.append(nav_buttons)
            
            # Action buttons
            menu_items.extend([
                [
                    InlineKeyboardButton("🔍 Cerca", callback_data='search_lists'),
                    InlineKeyboardButton("🔄 Aggiorna", callback_data='refresh_lists')
                ],
                [
                    InlineKeyboardButton("⚙️ Filtri", callback_data='list_filters'),
                    InlineKeyboardButton("🔙 Menu", callback_data='main_menu')
                ]
            ])
            
            return InlineKeyboardMarkup(menu_items)
            
        except Exception as e:
            logger.error(f"Error generating personalized list view: {e}")
            return self._get_fallback_list_menu()
    
    def get_quick_actions_menu(self, user_id):
        """Generate quick actions menu based on user behavior"""
        try:
            shortcuts = self._get_user_shortcuts(user_id)
            theme = self._get_user_theme(user_id)
            
            menu_items = []
            
            # User's custom shortcuts
            for shortcut in shortcuts[:6]:  # Max 6 shortcuts
                menu_items.append([
                    InlineKeyboardButton(
                        f"⚡ {shortcut['name']}",
                        callback_data=shortcut['callback']
                    )
                ])
            
            # Add/Edit shortcuts
            menu_items.extend([
                [
                    InlineKeyboardButton("➕ Aggiungi Scorciatoia", callback_data='add_shortcut'),
                    InlineKeyboardButton("✏️ Modifica", callback_data='edit_shortcuts')
                ],
                [
                    InlineKeyboardButton("🔙 Indietro", callback_data='main_menu')
                ]
            ])
            
            return InlineKeyboardMarkup(menu_items)
            
        except Exception as e:
            logger.error(f"Error generating quick actions menu: {e}")
            return self._get_fallback_menu()
    
    def get_user_settings_menu(self, user_id):
        """Generate user settings menu"""
        try:
            current_theme = self._get_user_theme_name(user_id)
            
            menu_items = [
                [
                    InlineKeyboardButton("🎨 Tema Interfaccia", callback_data='change_theme'),
                    InlineKeyboardButton("🔔 Notifiche", callback_data='notification_settings')
                ],
                [
                    InlineKeyboardButton("⚡ Azioni Rapide", callback_data='shortcut_settings'),
                    InlineKeyboardButton("🌐 Lingua", callback_data='language_settings')
                ],
                [
                    InlineKeyboardButton("📊 Privacy", callback_data='privacy_settings'),
                    InlineKeyboardButton("🔄 Reset Preferenze", callback_data='reset_preferences')
                ],
                [
                    InlineKeyboardButton(f"Tema attuale: {current_theme.title()}", callback_data='current_theme_info')
                ],
                [
                    InlineKeyboardButton("🔙 Menu Principale", callback_data='main_menu')
                ]
            ]
            
            return InlineKeyboardMarkup(menu_items)
            
        except Exception as e:
            logger.error(f"Error generating settings menu: {e}")
            return self._get_fallback_menu()
    
    def _analyze_user_patterns(self, user_id):
        """Analyze user behavior patterns"""
        try:
            with SessionLocal() as session:
                # Get recent activities
                recent_activities = session.query(UserActivity).filter(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.timestamp >= datetime.now(timezone.utc) - timedelta(days=30)
                    )
                ).all()
                
                # Analyze patterns
                action_counts = defaultdict(int)
                for activity in recent_activities:
                    action_counts[activity.action] += 1
                
                # Get most frequent actions
                frequent_actions = [action for action, count in action_counts.items() if count >= 3]
                
                return {
                    'frequent_actions': frequent_actions,
                    'total_activities': len(recent_activities),
                    'most_common': max(action_counts.items(), key=lambda x: x[1])[0] if action_counts else None
                }
                
        except Exception as e:
            logger.error(f"Error analyzing user patterns: {e}")
            return {'frequent_actions': [], 'total_activities': 0, 'most_common': None}
    
    def _get_user_theme(self, user_id):
        """Get user's preferred theme"""
        theme_name = self._get_user_theme_name(user_id)
        return self.ui_themes.get(theme_name, self.ui_themes['default'])
    
    def _get_user_theme_name(self, user_id):
        """Get user's theme name"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {'theme': 'default'}
        
        return self.user_preferences[user_id].get('theme', 'default')
    
    def _get_user_shortcuts(self, user_id):
        """Get user's custom shortcuts"""
        return self.custom_shortcuts.get(user_id, [])
    
    def _get_user_issue_history(self, user_id):
        """Get user's issue history for smart suggestions"""
        try:
            with SessionLocal() as session:
                recent_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.created_at >= datetime.now(timezone.utc) - timedelta(days=90)
                    )
                ).all()
                
                issue_types = []
                for ticket in recent_tickets:
                    title_lower = ticket.title.lower()
                    if any(word in title_lower for word in ['streaming', 'video', 'buffer']):
                        issue_types.append('streaming')
                    elif any(word in title_lower for word in ['login', 'accesso', 'password']):
                        issue_types.append('login')
                    elif any(word in title_lower for word in ['payment', 'pagamento']):
                        issue_types.append('payment')
                
                return list(set(issue_types))
                
        except Exception as e:
            logger.error(f"Error getting user issue history: {e}")
            return []
    
    def _get_urgent_counts(self):
        """Get counts of urgent admin items"""
        try:
            with SessionLocal() as session:
                escalated_tickets = session.query(Ticket).filter(
                    Ticket.auto_escalated == True,
                    Ticket.status == 'escalated'
                ).count()
                
                # Assuming RenewalRequest model exists
                try:
                    from models import RenewalRequest
                    pending_renewals = session.query(RenewalRequest).filter(
                        RenewalRequest.status == 'pending'
                    ).count()
                except ImportError:
                    pending_renewals = 0
                
                return {
                    'escalated_tickets': escalated_tickets,
                    'pending_renewals': pending_renewals
                }
                
        except Exception as e:
            logger.error(f"Error getting urgent counts: {e}")
            return {'escalated_tickets': 0, 'pending_renewals': 0}
    
    def _get_user_list_preferences(self, user_id):
        """Get user's list viewing preferences"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {}
        
        return self.user_preferences[user_id].get('list_preferences', {
            'sort_by': 'expiry_date',  # expiry_date, name, cost
            'show_expired': False,
            'preferred_categories': []
        })
    
    def _sort_lists_for_user(self, lists_data, preferences):
        """Sort lists based on user preferences"""
        try:
            sort_by = preferences.get('sort_by', 'expiry_date')
            
            if sort_by == 'expiry_date':
                return sorted(lists_data, key=lambda x: x.expiry_date or datetime.max.replace(tzinfo=timezone.utc))
            elif sort_by == 'name':
                return sorted(lists_data, key=lambda x: x.name.lower())
            elif sort_by == 'cost':
                return sorted(lists_data, key=lambda x: float(x.cost.replace('€', '').replace(',', '.')) if x.cost else 0)
            else:
                return lists_data
                
        except Exception as e:
            logger.error(f"Error sorting lists: {e}")
            return lists_data
    
    def _format_list_info(self, lst, preferences):
        """Format list information for display"""
        try:
            # Base info
            info = f"📋 {lst.name}"
            
            # Add cost if available
            if lst.cost:
                info += f" - {lst.cost}"
            
            # Add expiry info
            if lst.expiry_date:
                days_left = (lst.expiry_date - datetime.now(timezone.utc)).days
                if days_left < 0:
                    info += " ❌ Scaduta"
                elif days_left <= 7:
                    info += f" ⚠️ {days_left}gg"
                else:
                    info += f" ✅ {days_left}gg"
            
            return info[:64]  # Telegram button text limit
            
        except Exception as e:
            logger.error(f"Error formatting list info: {e}")
            return f"📋 {lst.name}"[:64]
    
    def set_user_theme(self, user_id, theme_name):
        """Set user's preferred theme"""
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {}
        
        if theme_name in self.ui_themes:
            self.user_preferences[user_id]['theme'] = theme_name
            return True
        return False
    
    def add_user_shortcut(self, user_id, name, callback_data):
        """Add custom shortcut for user"""
        if len(self.custom_shortcuts[user_id]) < 10:  # Max 10 shortcuts
            self.custom_shortcuts[user_id].append({
                'name': name,
                'callback': callback_data,
                'created_at': datetime.now(timezone.utc)
            })
            return True
        return False
    
    def remove_user_shortcut(self, user_id, shortcut_index):
        """Remove user shortcut"""
        try:
            if 0 <= shortcut_index < len(self.custom_shortcuts[user_id]):
                del self.custom_shortcuts[user_id][shortcut_index]
                return True
        except (IndexError, KeyError):
            pass
        return False
    
    def _get_fallback_menu(self):
        """Fallback menu in case of errors"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Liste", callback_data='view_all_lists')],
            [InlineKeyboardButton("🎫 Assistenza", callback_data='create_ticket')],
            [InlineKeyboardButton("❓ Aiuto", callback_data='help')]
        ])
    
    def _get_fallback_ticket_menu(self):
        """Fallback ticket menu"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 Nuovo Ticket", callback_data='new_ticket')],
            [InlineKeyboardButton("📋 I Miei Ticket", callback_data='my_tickets')],
            [InlineKeyboardButton("🔙 Menu", callback_data='main_menu')]
        ])
    
    def _get_fallback_admin_menu(self):
        """Fallback admin menu"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🎫 Ticket", callback_data='admin_tickets')],
            [InlineKeyboardButton("📋 Liste", callback_data='admin_lists')],
            [InlineKeyboardButton("👥 Utenti", callback_data='admin_users')]
        ])
    
    def _get_fallback_list_menu(self):
        """Fallback list menu"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Tutte le Liste", callback_data='view_all_lists')],
            [InlineKeyboardButton("🔍 Cerca", callback_data='search_lists')],
            [InlineKeyboardButton("🔙 Menu", callback_data='main_menu')]
        ])

# Global UI service instance
ui_service = UIService()