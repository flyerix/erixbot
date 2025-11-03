from typing import Optional, Dict, List
from functools import lru_cache
import hashlib
from datetime import datetime, timezone
from openai import OpenAI
import os
from collections import defaultdict

class AIConversationManager:
    def __init__(self):
        self.conversation_history: Dict[int, List[Dict]] = defaultdict(list)
        self.max_history = 20

    def add_message(self, ticket_id: int, role: str, content: str):
        """Add message to conversation history"""
        history = self.conversation_history[ticket_id]
        history.append({"role": role, "content": content})

        # Keep only recent messages
        if len(history) > self.max_history:
            history.pop(0)

    def get_context(self, ticket_id: int) -> List[Dict]:
        """Get conversation context for AI"""
        return self.conversation_history[ticket_id][-10:]  # Last 10 messages

    def clear_old_history(self, days: int = 7):
        """Clear conversation history older than specified days"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)
        # This would need timestamps on messages to implement properly
        pass

@lru_cache(maxsize=100)
def get_cached_ai_response(problem_hash: str, context_hash: str) -> Optional[str]:
    """Cache AI responses based on problem and context"""
    # Implementation would check database for cached responses
    # For now, return None to always get fresh responses
    return None

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

            # Cache the response (would store in database in production)
            # For now, just return it

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
