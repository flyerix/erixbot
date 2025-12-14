"""
Security and Anti-Abuse System
Advanced security system with spam detection and user reputation management
"""
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from sqlalchemy import and_, desc, func
from models import SessionLocal, Ticket, UserActivity, AuditLog
import hashlib
import re
import json

logger = logging.getLogger(__name__)

class SecurityService:
    """Advanced security service with anti-abuse capabilities"""
    
    def __init__(self):
        self.user_reputation = {}
        self.spam_patterns = self._load_spam_patterns()
        self.rate_limits = defaultdict(lambda: deque(maxlen=100))
        self.suspicious_activities = defaultdict(list)
        self.blocked_users = set()
        self.trusted_users = set()
        self.captcha_required = set()
        
    def _load_spam_patterns(self):
        """Load spam detection patterns"""
        return {
            'repeated_chars': re.compile(r'(.)\1{4,}'),  # 5+ repeated characters
            'excessive_caps': re.compile(r'[A-Z]{10,}'),  # 10+ consecutive caps
            'suspicious_urls': re.compile(r'(bit\.ly|tinyurl|t\.co|goo\.gl)'),
            'spam_keywords': [
                'free money', 'click here', 'limited time', 'act now',
                'soldi gratis', 'clicca qui', 'tempo limitato', 'agisci ora'
            ],
            'phone_numbers': re.compile(r'\+?\d{10,}'),
            'email_addresses': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        }
    
    def check_message_security(self, user_id, message, message_type='general'):
        """Comprehensive security check for messages"""
        try:
            security_result = {
                'allowed': True,
                'risk_score': 0,
                'flags': [],
                'action_required': None,
                'reason': None
            }
            
            # Check if user is blocked
            if user_id in self.blocked_users:
                security_result.update({
                    'allowed': False,
                    'risk_score': 100,
                    'flags': ['blocked_user'],
                    'action_required': 'block',
                    'reason': 'User is blocked'
                })
                return security_result
            
            # Skip checks for trusted users
            if user_id in self.trusted_users:
                security_result['risk_score'] = 0
                return security_result
            
            # Rate limiting check
            rate_check = self._check_rate_limit(user_id, message_type)
            if not rate_check['allowed']:
                security_result.update({
                    'allowed': False,
                    'risk_score': 60,
                    'flags': ['rate_limit_exceeded'],
                    'action_required': 'rate_limit',
                    'reason': rate_check['reason']
                })
                return security_result
            
            # Spam detection
            spam_score = self._detect_spam(message)
            security_result['risk_score'] += spam_score
            
            if spam_score > 0:
                security_result['flags'].append('potential_spam')
            
            # Behavioral analysis
            behavior_score = self._analyze_user_behavior(user_id, message)
            security_result['risk_score'] += behavior_score
            
            if behavior_score > 30:
                security_result['flags'].append('suspicious_behavior')
            
            # Reputation check
            reputation_score = self._get_user_reputation(user_id)
            if reputation_score < 30:
                security_result['risk_score'] += 20
                security_result['flags'].append('low_reputation')
            
            # Determine final action
            if security_result['risk_score'] >= 80:
                security_result.update({
                    'allowed': False,
                    'action_required': 'block',
                    'reason': 'High risk score'
                })
                self._handle_high_risk_user(user_id, security_result)
                
            elif security_result['risk_score'] >= 50:
                security_result.update({
                    'allowed': True,
                    'action_required': 'captcha',
                    'reason': 'Medium risk - captcha required'
                })
                self.captcha_required.add(user_id)
                
            elif security_result['risk_score'] >= 30:
                security_result.update({
                    'allowed': True,
                    'action_required': 'monitor',
                    'reason': 'Low risk - monitoring required'
                })
            
            # Log security check
            self._log_security_check(user_id, message_type, security_result)
            
            return security_result
            
        except Exception as e:
            logger.error(f"Error in security check: {e}")
            return {'allowed': True, 'risk_score': 0, 'flags': [], 'error': str(e)}
    
    def _check_rate_limit(self, user_id, message_type):
        """Check rate limiting for user"""
        try:
            now = datetime.now(timezone.utc)
            user_key = f"{user_id}_{message_type}"
            
            # Rate limits per message type
            limits = {
                'general': {'count': 20, 'window': 60},      # 20 messages per minute
                'ticket': {'count': 5, 'window': 300},       # 5 tickets per 5 minutes
                'search': {'count': 15, 'window': 60},       # 15 searches per minute
                'admin': {'count': 100, 'window': 60}        # 100 admin actions per minute
            }
            
            limit_config = limits.get(message_type, limits['general'])
            window_start = now - timedelta(seconds=limit_config['window'])
            
            # Clean old entries
            while (self.rate_limits[user_key] and 
                   self.rate_limits[user_key][0] < window_start):
                self.rate_limits[user_key].popleft()
            
            # Check current count
            current_count = len(self.rate_limits[user_key])
            
            if current_count >= limit_config['count']:
                return {
                    'allowed': False,
                    'reason': f'Rate limit exceeded: {current_count}/{limit_config["count"]} in {limit_config["window"]}s'
                }
            
            # Add current request
            self.rate_limits[user_key].append(now)
            
            return {'allowed': True, 'current_count': current_count + 1}
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return {'allowed': True}
    
    def _detect_spam(self, message):
        """Detect spam patterns in message"""
        spam_score = 0
        message_lower = message.lower()
        
        try:
            # Check for repeated characters
            if self.spam_patterns['repeated_chars'].search(message):
                spam_score += 15
            
            # Check for excessive caps
            if self.spam_patterns['excessive_caps'].search(message):
                spam_score += 10
            
            # Check for suspicious URLs
            if self.spam_patterns['suspicious_urls'].search(message):
                spam_score += 25
            
            # Check for spam keywords
            for keyword in self.spam_patterns['spam_keywords']:
                if keyword in message_lower:
                    spam_score += 20
                    break
            
            # Check for phone numbers (suspicious in support context)
            if self.spam_patterns['phone_numbers'].search(message):
                spam_score += 15
            
            # Check for email addresses (suspicious in support context)
            if self.spam_patterns['email_addresses'].search(message):
                spam_score += 10
            
            # Check message length patterns
            if len(message) < 5:
                spam_score += 5  # Very short messages
            elif len(message) > 2000:
                spam_score += 10  # Very long messages
            
            # Check for excessive punctuation
            punctuation_count = sum(1 for char in message if char in '!?.')
            if punctuation_count > len(message) * 0.1:  # More than 10% punctuation
                spam_score += 10
            
            return min(spam_score, 50)  # Cap at 50
            
        except Exception as e:
            logger.error(f"Error detecting spam: {e}")
            return 0
    
    def _analyze_user_behavior(self, user_id, message):
        """Analyze user behavior patterns"""
        behavior_score = 0
        
        try:
            with SessionLocal() as session:
                now = datetime.now(timezone.utc)
                
                # Check recent activity frequency
                recent_activities = session.query(UserActivity).filter(
                    and_(
                        UserActivity.user_id == user_id,
                        UserActivity.timestamp >= now - timedelta(hours=1)
                    )
                ).count()
                
                if recent_activities > 50:  # More than 50 actions per hour
                    behavior_score += 30
                elif recent_activities > 20:  # More than 20 actions per hour
                    behavior_score += 15
                
                # Check for rapid ticket creation
                recent_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.created_at >= now - timedelta(minutes=30)
                    )
                ).count()
                
                if recent_tickets > 5:  # More than 5 tickets in 30 minutes
                    behavior_score += 25
                elif recent_tickets > 3:  # More than 3 tickets in 30 minutes
                    behavior_score += 10
                
                # Check for identical messages
                recent_messages = session.query(Ticket).filter(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.created_at >= now - timedelta(hours=24)
                    )
                ).all()
                
                message_hash = hashlib.md5(message.encode()).hexdigest()
                identical_count = sum(1 for ticket in recent_messages 
                                    if hashlib.md5(ticket.description.encode()).hexdigest() == message_hash)
                
                if identical_count > 3:  # Same message more than 3 times
                    behavior_score += 40
                elif identical_count > 1:  # Same message more than once
                    behavior_score += 15
                
                return min(behavior_score, 50)  # Cap at 50
                
        except Exception as e:
            logger.error(f"Error analyzing user behavior: {e}")
            return 0
    
    def _get_user_reputation(self, user_id):
        """Get user reputation score"""
        if user_id not in self.user_reputation:
            self.user_reputation[user_id] = self._calculate_initial_reputation(user_id)
        
        return self.user_reputation[user_id]
    
    def _calculate_initial_reputation(self, user_id):
        """Calculate initial reputation for new user"""
        try:
            with SessionLocal() as session:
                # Base reputation
                reputation = 50
                
                # Account age bonus
                first_activity = session.query(func.min(Ticket.created_at)).filter(
                    Ticket.user_id == user_id
                ).scalar()
                
                if first_activity:
                    days_active = (datetime.now(timezone.utc) - first_activity).days
                    reputation += min(days_active * 2, 30)  # Up to 30 points for account age
                
                # Successful interactions bonus
                resolved_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.status.in_(['resolved', 'closed']),
                        Ticket.ai_attempts <= 2  # Resolved without escalation
                    )
                ).count()
                
                reputation += min(resolved_tickets * 5, 25)  # Up to 25 points for good interactions
                
                # Penalty for escalated tickets
                escalated_tickets = session.query(Ticket).filter(
                    and_(
                        Ticket.user_id == user_id,
                        Ticket.auto_escalated == True
                    )
                ).count()
                
                reputation -= escalated_tickets * 3  # -3 points per escalation
                
                return max(0, min(reputation, 100))  # Keep between 0-100
                
        except Exception as e:
            logger.error(f"Error calculating reputation: {e}")
            return 50  # Default reputation
    
    def _handle_high_risk_user(self, user_id, security_result):
        """Handle high-risk user detection"""
        try:
            # Add to suspicious activities
            self.suspicious_activities[user_id].append({
                'timestamp': datetime.now(timezone.utc),
                'risk_score': security_result['risk_score'],
                'flags': security_result['flags'],
                'action': 'blocked'
            })
            
            # Temporary block (can be reviewed by admin)
            self.blocked_users.add(user_id)
            
            # Log security incident
            self._log_security_incident(user_id, security_result)
            
            logger.warning(f"High-risk user {user_id} blocked: {security_result}")
            
        except Exception as e:
            logger.error(f"Error handling high-risk user: {e}")
    
    def _log_security_check(self, user_id, message_type, result):
        """Log security check for audit trail"""
        try:
            with SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=user_id,
                    action=f'security_check_{message_type}',
                    details=json.dumps({
                        'risk_score': result['risk_score'],
                        'flags': result['flags'],
                        'allowed': result['allowed'],
                        'action_required': result.get('action_required')
                    }),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
                
        except Exception as e:
            logger.error(f"Error logging security check: {e}")
    
    def _log_security_incident(self, user_id, security_result):
        """Log security incident for admin review"""
        try:
            with SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=user_id,
                    action='security_incident',
                    details=json.dumps({
                        'risk_score': security_result['risk_score'],
                        'flags': security_result['flags'],
                        'reason': security_result['reason'],
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
                
                logger.warning(f"Security incident logged for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error logging security incident: {e}")
    
    def update_user_reputation(self, user_id, change, reason):
        """Update user reputation score"""
        try:
            current_reputation = self._get_user_reputation(user_id)
            new_reputation = max(0, min(current_reputation + change, 100))
            
            self.user_reputation[user_id] = new_reputation
            
            # Log reputation change
            with SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=user_id,
                    action='reputation_update',
                    details=json.dumps({
                        'old_reputation': current_reputation,
                        'new_reputation': new_reputation,
                        'change': change,
                        'reason': reason
                    }),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
            
            logger.info(f"Updated reputation for user {user_id}: {current_reputation} -> {new_reputation} ({reason})")
            
        except Exception as e:
            logger.error(f"Error updating user reputation: {e}")
    
    def add_trusted_user(self, user_id, admin_id):
        """Add user to trusted list"""
        try:
            self.trusted_users.add(user_id)
            self.user_reputation[user_id] = 100  # Max reputation for trusted users
            
            # Remove from blocked/captcha lists if present
            self.blocked_users.discard(user_id)
            self.captcha_required.discard(user_id)
            
            # Log action
            with SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=admin_id,
                    action='add_trusted_user',
                    details=json.dumps({'trusted_user_id': user_id}),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
            
            logger.info(f"User {user_id} added to trusted list by admin {admin_id}")
            
        except Exception as e:
            logger.error(f"Error adding trusted user: {e}")
    
    def unblock_user(self, user_id, admin_id):
        """Unblock a user (admin action)"""
        try:
            self.blocked_users.discard(user_id)
            self.captcha_required.discard(user_id)
            
            # Reset reputation to neutral
            self.user_reputation[user_id] = 50
            
            # Log action
            with SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=admin_id,
                    action='unblock_user',
                    details=json.dumps({'unblocked_user_id': user_id}),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
            
            logger.info(f"User {user_id} unblocked by admin {admin_id}")
            
        except Exception as e:
            logger.error(f"Error unblocking user: {e}")
    
    def get_security_stats(self):
        """Get security system statistics"""
        return {
            'blocked_users': len(self.blocked_users),
            'trusted_users': len(self.trusted_users),
            'users_requiring_captcha': len(self.captcha_required),
            'users_with_reputation': len(self.user_reputation),
            'suspicious_activities': sum(len(activities) for activities in self.suspicious_activities.values()),
            'rate_limit_entries': sum(len(entries) for entries in self.rate_limits.values())
        }
    
    def get_user_security_info(self, user_id):
        """Get security information for specific user"""
        return {
            'user_id': user_id,
            'reputation': self._get_user_reputation(user_id),
            'is_blocked': user_id in self.blocked_users,
            'is_trusted': user_id in self.trusted_users,
            'requires_captcha': user_id in self.captcha_required,
            'suspicious_activities': len(self.suspicious_activities.get(user_id, [])),
            'recent_rate_limits': len([entry for entry in self.rate_limits.get(f"{user_id}_general", []) 
                                     if (datetime.now(timezone.utc) - entry).total_seconds() < 3600])
        }

# Global security service instance
security_service = SecurityService()