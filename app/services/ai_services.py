from typing import Optional, Dict, List, Any
from functools import lru_cache
import hashlib
from datetime import datetime, timezone, timedelta
from openai import OpenAI
import os
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class AIConversationManager:
    def __init__(self):
        self.conversation_history: Dict[int, List[Dict[str, str]]] = defaultdict(list)
        self.max_history = 20
        self.user_context_cache: Dict[int, Dict[str, Any]] = {}
        self.context_cache_size = 100

    def add_message(self, ticket_id: int, role: str, content: str):
        """Add message to conversation history with timestamp"""
        history = self.conversation_history[ticket_id]
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        history.append(message)

        # Keep only recent messages
        if len(history) > self.max_history:
            history.pop(0)

    def get_context(self, ticket_id: int) -> List[Dict[str, str]]:
        """Get conversation context for AI with enhanced context awareness"""
        history = self.conversation_history[ticket_id][-10:]  # Last 10 messages

        # Add context awareness based on user behavior
        if ticket_id in self.user_context_cache:
            user_context = self.user_context_cache[ticket_id]
            context_messages = []

            # Add common issues context
            if 'common_issues' in user_context and user_context['common_issues']:
                context_messages.append({
                    "role": "system",
                    "content": f"L'utente ha avuto problemi simili in passato: {', '.join(user_context['common_issues'][:3])}"
                })

            # Add behavioral context
            if 'behavior_patterns' in user_context:
                context_messages.append({
                    "role": "system",
                    "content": f"Pattern comportamentali: {user_context['behavior_patterns']}"
                })

            return context_messages + history

        return history

    def update_user_context(self, user_id: int, issue_keywords: List[str], behavior_pattern: Optional[str] = None):
        """Update user context for better AI responses"""
        if user_id not in self.user_context_cache:
            self.user_context_cache[user_id] = {
                'common_issues': [],
                'behavior_patterns': '',
                'last_updated': datetime.now(timezone.utc)
            }

        context = self.user_context_cache[user_id]

        # Update common issues
        context['common_issues'].extend(issue_keywords)
        context['common_issues'] = list(set(context['common_issues'][-10:]))  # Keep last 10 unique issues

        # Update behavior patterns
        if behavior_pattern:
            context['behavior_patterns'] = behavior_pattern

        context['last_updated'] = datetime.now(timezone.utc)

        # Clean cache if too large
        if len(self.user_context_cache) > self.context_cache_size:
            oldest_user = min(self.user_context_cache.keys(),
                            key=lambda x: self.user_context_cache[x]['last_updated'])
            del self.user_context_cache[oldest_user]

    def clear_old_history(self, days: int = 7):
        """Clear conversation history older than specified days"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        for ticket_id in list(self.conversation_history.keys()):
            history = self.conversation_history[ticket_id]
            # Filter out old messages
            filtered_history = [
                msg for msg in history
                if datetime.fromisoformat(msg['timestamp']) > cutoff_time
            ]

            if filtered_history:
                self.conversation_history[ticket_id] = filtered_history
            else:
                del self.conversation_history[ticket_id]

        logger.info(f"Cleared old conversation history older than {days} days")

class AIResponseCache:
    def __init__(self, max_size: int = 500):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_size = max_size

    def get(self, problem_hash: str, context_hash: str) -> Optional[str]:
        """Get cached AI response"""
        cache_key = f"{problem_hash}:{context_hash}"
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            # Check if cache entry is still valid (24 hours)
            if datetime.now(timezone.utc) - datetime.fromisoformat(entry['timestamp']) < timedelta(hours=24):
                return entry['response']
            else:
                # Remove expired entry
                del self.cache[cache_key]
        return None

    def set(self, problem_hash: str, context_hash: str, response: str):
        """Cache AI response"""
        cache_key = f"{problem_hash}:{context_hash}"

        # Clean cache if too large
        if len(self.cache) >= self.max_size:
            # Remove oldest entries
            oldest_keys = sorted(self.cache.keys(),
                               key=lambda k: self.cache[k]['timestamp'])[:50]
            for key in oldest_keys:
                del self.cache[key]

        self.cache[cache_key] = {
            'response': response,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

# Global AI response cache
ai_response_cache = AIResponseCache()

@lru_cache(maxsize=100)
def get_cached_ai_response(problem_hash: str, context_hash: str) -> Optional[str]:
    """Cache AI responses based on problem and context"""
    return ai_response_cache.get(problem_hash, context_hash)

def generate_content_hash(content: str) -> str:
    """Generate hash for content caching"""
    return hashlib.md5(content.encode()).hexdigest()

class EnhancedAIService:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            # Initialize without client for testing/development
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
        self.conversation_manager = AIConversationManager()
        self.model = "gpt-3.5-turbo"
        self.max_tokens = 400

    def get_ai_response(self, problem_description: str, is_followup: bool = False, ticket_id: Optional[int] = None, user_id: Optional[int] = None) -> Optional[str]:
        """Get AI response with enhanced context and caching"""
        try:
            # Return mock response if no client (for testing)
            if not self.client:
                return "Risposta AI simulata per test - configurare OPENAI_API_KEY per risposte reali."

            # Check cache first
            problem_hash = generate_content_hash(problem_description)
            context_hash = "none"
            if ticket_id:
                context = self.conversation_manager.get_context(ticket_id)
                context_hash = generate_content_hash(str(context))

            cached_response = get_cached_ai_response(problem_hash, context_hash)
            if cached_response:
                # Update metrics for cache hit
                if hasattr(self, 'metrics_collector'):
                    self.metrics_collector.record_ai_response(0.0, cached=True)
                return cached_response

            system_prompt = """Sei un assistente tecnico specializzato nel supporto clienti per un'applicazione installata su Amazon Firestick.

La nostra applicazione offre contenuti streaming premium. Gli utenti possono avere problemi con:

🔧 **Problemi Comuni Firestick:**
• Applicazione che non si avvia
• Video che si blocca o buffering
• Audio fuori sincrono
• Login che non funziona
• Aggiornamenti che falliscono
• Connessione internet instabile
• Problemi di compatibilità Firestick

🔧 **Problemi Comuni App:**
• Contenuto che non carica
• Qualità video bassa
• Sottotitoli che non funzionano
• Account bloccato/sospeso
• Pagamenti non elaborati
• Liste di riproduzione vuote

📋 **Procedure Standard:**
1. Riavvia l'applicazione
2. Riavvia il Firestick (premi e tieni Select + Play per 5 secondi)
3. Controlla connessione internet (minimo 10 Mbps)
4. Cancella cache dell'app
5. Verifica aggiornamenti disponibili
6. Controlla spazio di archiviazione Firestick

Rispondi SEMPRE in italiano, in modo amichevole e professionale. Se il problema è troppo complesso o richiede intervento manuale, dì chiaramente "Questo problema richiede assistenza tecnica specializzata. Un tecnico ti contatterà presto."

NON dire mai "non posso aiutare" - invece guida l'utente attraverso i passaggi di risoluzione."""

            messages = [{"role": "system", "content": system_prompt}]

            # Add conversation history for context
            if is_followup and ticket_id:
                history = self.conversation_manager.get_context(ticket_id)
                for msg in history[-6:]:  # Last 6 messages for context
                    messages.append(msg)

            messages.append({"role": "user", "content": f"Problema: {problem_description}"})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens
            )

            ai_text = response.choices[0].message.content.strip()

            # Cache the response
            ai_response_cache.set(problem_hash, context_hash, ai_text)

            # Se l'AI dice che non può risolvere, restituisci None per escalation
            escalation_keywords = [
                "richiede assistenza tecnica specializzata",
                "tecnico ti contatterà",
                "non posso risolvere",
                "troppo complesso",
                "intervento manuale"
            ]

            if any(keyword in ai_text.lower() for keyword in escalation_keywords):
                return None

            return ai_text

        except Exception as e:
            print(f"AI response error: {e}")
            return None

# Global AI service instance
ai_service = EnhancedAIService()
