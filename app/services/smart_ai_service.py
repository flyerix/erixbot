"""
Smart AI Service with Memory and Learning Capabilities
Enhanced AI that learns from interactions and provides contextual responses
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from sqlalchemy import and_, desc
from models import SessionLocal, Ticket, TicketMessage, UserActivity
from services.ai_services import ai_service
import hashlib

logger = logging.getLogger(__name__)

class SmartAIService:
    """Enhanced AI service with memory and learning capabilities"""
    
    def __init__(self):
        self.knowledge_base = {}
        self.user_contexts = {}
        self.success_patterns = {}
        self.load_knowledge_base()
    
    def load_knowledge_base(self):
        """Load AI knowledge base from successful resolutions"""
        try:
            with SessionLocal() as session:
                # Get successful ticket resolutions from the last 30 days
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
                
                successful_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.status.in_(['closed', 'resolved']),
                        Ticket.ai_attempts > 0,
                        Ticket.ai_attempts <= 2,
                        Ticket.updated_at >= cutoff_date
                    )
                ).all()
                
                for ticket in successful_tickets:
                    self._extract_success_pattern(ticket)
                
                logger.info(f"Loaded {len(self.success_patterns)} success patterns into AI knowledge base")
                
        except Exception as e:
            logger.error(f"Error loading knowledge base: {e}")
    
    def _extract_success_pattern(self, ticket):
        """Extract successful resolution patterns from ticket"""
        try:
            # Create a pattern key based on problem type
            problem_key = self._generate_problem_key(ticket.title, ticket.description)
            
            if problem_key not in self.success_patterns:
                self.success_patterns[problem_key] = {
                    'count': 0,
                    'solutions': [],
                    'keywords': set(),
                    'success_rate': 0
                }
            
            # Get the resolution messages
            with SessionLocal() as session:
                messages = session.query(TicketMessage).filter(
                    TicketMessage.ticket_id == ticket.id
                ).order_by(TicketMessage.created_at).all()
                
                for msg in messages:
                    if msg.is_from_admin or msg.is_ai_response:
                        self.success_patterns[problem_key]['solutions'].append({
                            'message': msg.message,
                            'timestamp': msg.created_at,
                            'was_successful': True
                        })
            
            self.success_patterns[problem_key]['count'] += 1
            self._update_keywords(problem_key, ticket.title + " " + ticket.description)
            
        except Exception as e:
            logger.error(f"Error extracting success pattern: {e}")
    
    def _generate_problem_key(self, title, description):
        """Generate a unique key for problem categorization"""
        text = (title + " " + description).lower()
        
        # Common problem categories
        if any(word in text for word in ['streaming', 'video', 'buffer', 'lag']):
            return 'streaming_issues'
        elif any(word in text for word in ['login', 'accesso', 'password', 'account']):
            return 'login_issues'
        elif any(word in text for word in ['payment', 'pagamento', 'abbonamento', 'rinnovo']):
            return 'payment_issues'
        elif any(word in text for word in ['lista', 'canali', 'channel']):
            return 'list_issues'
        elif any(word in text for word in ['app', 'applicazione', 'installazione']):
            return 'app_issues'
        else:
            # Generate hash for unique problems
            return hashlib.md5(text.encode()).hexdigest()[:8]
    
    def _update_keywords(self, problem_key, text):
        """Update keywords for problem pattern"""
        words = text.lower().split()
        common_words = {'il', 'la', 'di', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 'a', 'e', 'o', 'ma', 'se', 'che', 'non', 'un', 'una'}
        
        for word in words:
            if len(word) > 3 and word not in common_words:
                self.success_patterns[problem_key]['keywords'].add(word)
    
    def get_contextual_response(self, user_id, message, ticket_history=None):
        """Get AI response with context and memory"""
        try:
            # Build user context
            user_context = self._build_user_context(user_id)
            
            # Find similar problems in knowledge base
            similar_solutions = self._find_similar_solutions(message)
            
            # Generate enhanced prompt with context
            enhanced_prompt = self._build_enhanced_prompt(
                message, user_context, similar_solutions, ticket_history
            )
            
            # Get AI response
            response = ai_service.get_response(enhanced_prompt)
            
            # Learn from this interaction
            self._learn_from_interaction(user_id, message, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting contextual response: {e}")
            return ai_service.get_response(message)  # Fallback to basic AI
    
    def _build_user_context(self, user_id):
        """Build context for specific user"""
        try:
            with SessionLocal() as session:
                # Get user's recent tickets
                recent_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
                    )
                ).order_by(desc(Ticket.created_at)).limit(5).all()
                
                context = {
                    'user_id': user_id,
                    'recent_issues': [],
                    'preferred_solutions': [],
                    'interaction_count': len(recent_tickets)
                }
                
                for ticket in recent_tickets:
                    context['recent_issues'].append({
                        'title': ticket.title,
                        'status': ticket.status,
                        'ai_attempts': ticket.ai_attempts,
                        'was_escalated': ticket.auto_escalated
                    })
                
                return context
                
        except Exception as e:
            logger.error(f"Error building user context: {e}")
            return {'user_id': user_id, 'recent_issues': [], 'interaction_count': 0}
    
    def _find_similar_solutions(self, message):
        """Find similar solutions from knowledge base"""
        message_lower = message.lower()
        similar_solutions = []
        
        for problem_key, pattern in self.success_patterns.items():
            # Check keyword overlap
            message_words = set(message_lower.split())
            keyword_overlap = len(message_words.intersection(pattern['keywords']))
            
            if keyword_overlap > 0:
                similarity_score = keyword_overlap / len(pattern['keywords']) if pattern['keywords'] else 0
                
                if similarity_score > 0.3:  # 30% similarity threshold
                    similar_solutions.append({
                        'problem_type': problem_key,
                        'similarity': similarity_score,
                        'solutions': pattern['solutions'][-3:],  # Last 3 successful solutions
                        'success_count': pattern['count']
                    })
        
        # Sort by similarity and success count
        similar_solutions.sort(key=lambda x: (x['similarity'], x['success_count']), reverse=True)
        return similar_solutions[:3]  # Top 3 similar solutions
    
    def _build_enhanced_prompt(self, message, user_context, similar_solutions, ticket_history):
        """Build enhanced prompt with context and similar solutions"""
        prompt_parts = [
            "Sei un assistente AI esperto per ErixCast Bot. Rispondi in italiano in modo professionale e utile.",
            f"Messaggio utente: {message}",
        ]
        
        # Add user context
        if user_context['interaction_count'] > 0:
            prompt_parts.append(f"Contesto utente: L'utente ha avuto {user_context['interaction_count']} interazioni recenti.")
            
            if user_context['recent_issues']:
                recent_issue_types = [issue['title'][:50] for issue in user_context['recent_issues'][:2]]
                prompt_parts.append(f"Problemi recenti: {', '.join(recent_issue_types)}")
        
        # Add similar solutions
        if similar_solutions:
            prompt_parts.append("Soluzioni simili che hanno funzionato in passato:")
            for i, solution in enumerate(similar_solutions[:2], 1):
                if solution['solutions']:
                    example_solution = solution['solutions'][0]['message'][:200]
                    prompt_parts.append(f"{i}. {example_solution}...")
        
        # Add ticket history if available
        if ticket_history:
            prompt_parts.append(f"Cronologia conversazione: {ticket_history[-500:]}")  # Last 500 chars
        
        prompt_parts.extend([
            "Fornisci una risposta specifica, pratica e personalizzata.",
            "Se non puoi risolvere il problema, sii onesto e suggerisci di contattare un amministratore.",
            "Mantieni un tono professionale ma amichevole."
        ])
        
        return "\n\n".join(prompt_parts)
    
    def _learn_from_interaction(self, user_id, message, response):
        """Learn from user interaction for future improvements"""
        try:
            # Store interaction for learning
            interaction_key = f"{user_id}_{datetime.now().strftime('%Y%m%d')}"
            
            if interaction_key not in self.user_contexts:
                self.user_contexts[interaction_key] = []
            
            self.user_contexts[interaction_key].append({
                'message': message,
                'response': response,
                'timestamp': datetime.now(timezone.utc),
                'feedback': None  # Will be updated if user provides feedback
            })
            
            # Limit stored interactions per user per day
            if len(self.user_contexts[interaction_key]) > 10:
                self.user_contexts[interaction_key] = self.user_contexts[interaction_key][-10:]
                
        except Exception as e:
            logger.error(f"Error learning from interaction: {e}")
    
    def update_feedback(self, user_id, message_id, feedback_positive):
        """Update feedback for AI response to improve learning"""
        try:
            interaction_key = f"{user_id}_{datetime.now().strftime('%Y%m%d')}"
            
            if interaction_key in self.user_contexts:
                for interaction in self.user_contexts[interaction_key]:
                    if interaction['timestamp'].strftime('%H%M%S') == message_id:
                        interaction['feedback'] = feedback_positive
                        break
            
            # Update success patterns based on feedback
            if feedback_positive:
                self._reinforce_successful_pattern(message_id)
            else:
                self._mark_unsuccessful_pattern(message_id)
                
        except Exception as e:
            logger.error(f"Error updating feedback: {e}")
    
    def _reinforce_successful_pattern(self, message_id):
        """Reinforce successful response patterns"""
        # Implementation for reinforcing successful patterns
        pass
    
    def _mark_unsuccessful_pattern(self, message_id):
        """Mark unsuccessful response patterns"""
        # Implementation for marking unsuccessful patterns
        pass
    
    def get_proactive_suggestions(self, user_id):
        """Get proactive suggestions for user based on their history"""
        try:
            user_context = self._build_user_context(user_id)
            suggestions = []
            
            # Analyze user's recent issues for patterns
            if user_context['recent_issues']:
                issue_types = [issue['title'].lower() for issue in user_context['recent_issues']]
                
                # Suggest preventive measures
                if any('streaming' in issue for issue in issue_types):
                    suggestions.append({
                        'type': 'preventive',
                        'title': '💡 Suggerimento Streaming',
                        'message': 'Per evitare problemi di streaming, assicurati di avere una connessione stabile (almeno 10 Mbps) e chiudi altre app che usano internet.'
                    })
                
                if any('login' in issue for issue in issue_types):
                    suggestions.append({
                        'type': 'security',
                        'title': '🔐 Sicurezza Account',
                        'message': 'Considera di cambiare la password periodicamente e attivare l\'autenticazione a due fattori per maggiore sicurezza.'
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting proactive suggestions: {e}")
            return []
    
    def get_ai_stats(self):
        """Get AI performance statistics"""
        return {
            'knowledge_patterns': len(self.success_patterns),
            'active_user_contexts': len(self.user_contexts),
            'total_learned_solutions': sum(len(p['solutions']) for p in self.success_patterns.values()),
            'last_updated': datetime.now(timezone.utc).isoformat()
        }

# Global smart AI service instance
smart_ai_service = SmartAIService()