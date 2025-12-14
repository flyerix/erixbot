"""
Gamification and Engagement System
Points, badges, achievements, and rewards system
"""
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from sqlalchemy import and_, desc, func
from models import SessionLocal, Ticket, UserActivity, AuditLog
import json

logger = logging.getLogger(__name__)

class GamificationService:
    """Gamification service for user engagement"""
    
    def __init__(self):
        self.user_points = defaultdict(int)
        self.user_badges = defaultdict(list)
        self.user_achievements = defaultdict(list)
        self.leaderboard = []
        self.achievement_definitions = self._load_achievements()
        self.badge_definitions = self._load_badges()
        self.point_rules = self._load_point_rules()
        
    def _load_achievements(self):
        """Load achievement definitions"""
        return {
            'first_ticket': {
                'name': '🎫 Primo Ticket',
                'description': 'Hai creato il tuo primo ticket di assistenza',
                'points': 10,
                'icon': '🎫',
                'category': 'beginner'
            },
            'problem_solver': {
                'name': '🔧 Problem Solver',
                'description': 'Hai risolto 5 ticket senza escalation',
                'points': 50,
                'icon': '🔧',
                'category': 'expert',
                'requirement': {'resolved_tickets': 5}
            },
            'speed_demon': {
                'name': '⚡ Speed Demon',
                'description': 'Hai risolto un ticket in meno di 5 minuti',
                'points': 25,
                'icon': '⚡',
                'category': 'speed'
            },
            'loyal_user': {
                'name': '👑 Utente Fedele',
                'description': 'Hai utilizzato il bot per 30 giorni consecutivi',
                'points': 100,
                'icon': '👑',
                'category': 'loyalty',
                'requirement': {'consecutive_days': 30}
            },
            'helper': {
                'name': '🤝 Helper',
                'description': 'Hai fornito feedback utile su 10 ticket',
                'points': 75,
                'icon': '🤝',
                'category': 'community',
                'requirement': {'feedback_count': 10}
            },
            'explorer': {
                'name': '🗺️ Explorer',
                'description': 'Hai utilizzato tutte le funzionalità del bot',
                'points': 150,
                'icon': '🗺️',
                'category': 'exploration'
            },
            'streak_master': {
                'name': '🔥 Streak Master',
                'description': 'Hai mantenuto una streak di 7 giorni',
                'points': 200,
                'icon': '🔥',
                'category': 'consistency',
                'requirement': {'streak_days': 7}
            },
            'ai_whisperer': {
                'name': '🤖 AI Whisperer',
                'description': 'L\'AI ha risolto 20 tuoi problemi al primo tentativo',
                'points': 300,
                'icon': '🤖',
                'category': 'ai_expert',
                'requirement': {'ai_first_success': 20}
            }
        }
    
    def _load_badges(self):
        """Load badge definitions"""
        return {
            'bronze_supporter': {
                'name': '🥉 Bronze Supporter',
                'description': 'Hai raggiunto 100 punti',
                'threshold': 100,
                'icon': '🥉',
                'color': '#CD7F32'
            },
            'silver_supporter': {
                'name': '🥈 Silver Supporter',
                'description': 'Hai raggiunto 500 punti',
                'threshold': 500,
                'icon': '🥈',
                'color': '#C0C0C0'
            },
            'gold_supporter': {
                'name': '🥇 Gold Supporter',
                'description': 'Hai raggiunto 1000 punti',
                'threshold': 1000,
                'icon': '🥇',
                'color': '#FFD700'
            },
            'platinum_supporter': {
                'name': '💎 Platinum Supporter',
                'description': 'Hai raggiunto 2500 punti',
                'threshold': 2500,
                'icon': '💎',
                'color': '#E5E4E2'
            },
            'diamond_supporter': {
                'name': '💠 Diamond Supporter',
                'description': 'Hai raggiunto 5000 punti',
                'threshold': 5000,
                'icon': '💠',
                'color': '#B9F2FF'
            }
        }
    
    def _load_point_rules(self):
        """Load point earning rules"""
        return {
            'create_ticket': 5,
            'resolve_ticket_ai': 10,
            'resolve_ticket_fast': 15,  # Resolved in < 1 hour
            'provide_feedback': 8,
            'daily_login': 2,
            'weekly_streak': 20,
            'help_other_user': 25,
            'perfect_ai_interaction': 30,  # AI resolved on first try
            'long_term_user': 50,  # Using bot for 30+ days
            'referral': 100  # Refer new user
        }
    
    def award_points(self, user_id, action, amount=None, details=None):
        """Award points to user for specific action"""
        try:
            if amount is None:
                amount = self.point_rules.get(action, 0)
            
            if amount <= 0:
                return False
            
            old_points = self.user_points[user_id]
            self.user_points[user_id] += amount
            new_points = self.user_points[user_id]
            
            # Check for new badges
            new_badges = self._check_new_badges(user_id, old_points, new_points)
            
            # Check for new achievements
            new_achievements = self._check_new_achievements(user_id, action, details)
            
            # Log points award
            self._log_points_award(user_id, action, amount, details)
            
            # Update leaderboard
            self._update_leaderboard()
            
            logger.info(f"Awarded {amount} points to user {user_id} for {action}")
            
            return {
                'points_awarded': amount,
                'total_points': new_points,
                'new_badges': new_badges,
                'new_achievements': new_achievements
            }
            
        except Exception as e:
            logger.error(f"Error awarding points: {e}")
            return False
    
    def _check_new_badges(self, user_id, old_points, new_points):
        """Check if user earned new badges"""
        new_badges = []
        
        for badge_id, badge_info in self.badge_definitions.items():
            threshold = badge_info['threshold']
            
            # Check if user crossed the threshold
            if old_points < threshold <= new_points:
                if badge_id not in self.user_badges[user_id]:
                    self.user_badges[user_id].append({
                        'badge_id': badge_id,
                        'name': badge_info['name'],
                        'description': badge_info['description'],
                        'icon': badge_info['icon'],
                        'earned_at': datetime.now(timezone.utc).isoformat()
                    })
                    new_badges.append(badge_info)
        
        return new_badges
    
    def _check_new_achievements(self, user_id, action, details):
        """Check if user earned new achievements"""
        new_achievements = []
        
        try:
            with SessionLocal() as session:
                # Get user statistics
                user_stats = self._get_user_stats(user_id, session)
                
                for achievement_id, achievement_info in self.achievement_definitions.items():
                    # Skip if already earned
                    if any(a['achievement_id'] == achievement_id for a in self.user_achievements[user_id]):
                        continue
                    
                    # Check achievement conditions
                    if self._check_achievement_condition(achievement_id, achievement_info, user_stats, action, details):
                        self.user_achievements[user_id].append({
                            'achievement_id': achievement_id,
                            'name': achievement_info['name'],
                            'description': achievement_info['description'],
                            'icon': achievement_info['icon'],
                            'points': achievement_info['points'],
                            'earned_at': datetime.now(timezone.utc).isoformat()
                        })
                        
                        # Award achievement points
                        self.user_points[user_id] += achievement_info['points']
                        
                        new_achievements.append(achievement_info)
                        
                        logger.info(f"User {user_id} earned achievement: {achievement_info['name']}")
                
                return new_achievements
                
        except Exception as e:
            logger.error(f"Error checking achievements: {e}")
            return []
    
    def _check_achievement_condition(self, achievement_id, achievement_info, user_stats, action, details):
        """Check if achievement condition is met"""
        try:
            if achievement_id == 'first_ticket' and action == 'create_ticket':
                return user_stats['total_tickets'] == 1
            
            elif achievement_id == 'problem_solver':
                return user_stats['resolved_without_escalation'] >= 5
            
            elif achievement_id == 'speed_demon' and action == 'resolve_ticket_fast':
                return details and details.get('resolution_time_minutes', 999) < 5
            
            elif achievement_id == 'loyal_user':
                return user_stats['consecutive_active_days'] >= 30
            
            elif achievement_id == 'helper':
                return user_stats['feedback_provided'] >= 10
            
            elif achievement_id == 'explorer':
                required_actions = ['create_ticket', 'search_lists', 'contact_admin', 'provide_feedback']
                return all(action in user_stats['actions_used'] for action in required_actions)
            
            elif achievement_id == 'streak_master':
                return user_stats['current_streak'] >= 7
            
            elif achievement_id == 'ai_whisperer':
                return user_stats['ai_first_success_count'] >= 20
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking achievement condition: {e}")
            return False
    
    def _get_user_stats(self, user_id, session):
        """Get comprehensive user statistics"""
        try:
            now = datetime.now(timezone.utc)
            
            # Basic ticket stats
            total_tickets = session.query(Ticket).filter(Ticket.user_id == user_id).count()
            
            resolved_tickets = session.query(Ticket).filter(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.status.in_(['resolved', 'closed'])
                )
            ).count()
            
            resolved_without_escalation = session.query(Ticket).filter(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.status.in_(['resolved', 'closed']),
                    Ticket.auto_escalated == False
                )
            ).count()
            
            ai_first_success = session.query(Ticket).filter(
                and_(
                    Ticket.user_id == user_id,
                    Ticket.status.in_(['resolved', 'closed']),
                    Ticket.ai_attempts == 1
                )
            ).count()
            
            # Activity stats
            activities = session.query(UserActivity).filter(
                UserActivity.user_id == user_id
            ).all()
            
            actions_used = set(activity.action for activity in activities)
            
            # Calculate streaks and consecutive days
            consecutive_days = self._calculate_consecutive_days(user_id, session)
            current_streak = self._calculate_current_streak(user_id, session)
            
            return {
                'total_tickets': total_tickets,
                'resolved_tickets': resolved_tickets,
                'resolved_without_escalation': resolved_without_escalation,
                'ai_first_success_count': ai_first_success,
                'actions_used': actions_used,
                'consecutive_active_days': consecutive_days,
                'current_streak': current_streak,
                'feedback_provided': 0  # Would need feedback tracking
            }
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}
    
    def _calculate_consecutive_days(self, user_id, session):
        """Calculate consecutive active days"""
        try:
            # Get distinct activity dates for last 60 days
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=60)
            
            activities = session.query(func.date(UserActivity.timestamp)).filter(
                and_(
                    UserActivity.user_id == user_id,
                    UserActivity.timestamp >= cutoff_date
                )
            ).distinct().order_by(func.date(UserActivity.timestamp).desc()).all()
            
            if not activities:
                return 0
            
            consecutive_days = 1
            current_date = activities[0][0]
            
            for i in range(1, len(activities)):
                prev_date = activities[i][0]
                if (current_date - prev_date).days == 1:
                    consecutive_days += 1
                    current_date = prev_date
                else:
                    break
            
            return consecutive_days
            
        except Exception as e:
            logger.error(f"Error calculating consecutive days: {e}")
            return 0
    
    def _calculate_current_streak(self, user_id, session):
        """Calculate current activity streak"""
        # For now, same as consecutive days
        # In a full implementation, this would track daily goals/activities
        return self._calculate_consecutive_days(user_id, session)
    
    def _update_leaderboard(self):
        """Update the global leaderboard"""
        try:
            # Sort users by points
            sorted_users = sorted(
                self.user_points.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            self.leaderboard = []
            for rank, (user_id, points) in enumerate(sorted_users[:50], 1):  # Top 50
                badges = len(self.user_badges[user_id])
                achievements = len(self.user_achievements[user_id])
                
                self.leaderboard.append({
                    'rank': rank,
                    'user_id': user_id,
                    'points': points,
                    'badges': badges,
                    'achievements': achievements
                })
                
        except Exception as e:
            logger.error(f"Error updating leaderboard: {e}")
    
    def _log_points_award(self, user_id, action, amount, details):
        """Log points award for audit trail"""
        try:
            with SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=user_id,
                    action='points_awarded',
                    details=json.dumps({
                        'action': action,
                        'points': amount,
                        'details': details,
                        'total_points': self.user_points[user_id]
                    }),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
                
        except Exception as e:
            logger.error(f"Error logging points award: {e}")
    
    def get_user_profile(self, user_id):
        """Get complete user gamification profile"""
        try:
            user_rank = next(
                (item['rank'] for item in self.leaderboard if item['user_id'] == user_id),
                None
            )
            
            # Get next badge threshold
            current_points = self.user_points[user_id]
            next_badge = None
            
            for badge_id, badge_info in self.badge_definitions.items():
                if current_points < badge_info['threshold']:
                    if next_badge is None or badge_info['threshold'] < next_badge['threshold']:
                        next_badge = badge_info
            
            return {
                'user_id': user_id,
                'points': current_points,
                'rank': user_rank,
                'badges': self.user_badges[user_id],
                'achievements': self.user_achievements[user_id],
                'next_badge': next_badge,
                'progress_to_next_badge': {
                    'current': current_points,
                    'target': next_badge['threshold'] if next_badge else None,
                    'remaining': (next_badge['threshold'] - current_points) if next_badge else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return None
    
    def get_leaderboard(self, limit=10):
        """Get current leaderboard"""
        return self.leaderboard[:limit]
    
    def get_user_rewards(self, user_id):
        """Get available rewards for user"""
        try:
            points = self.user_points[user_id]
            badges = len(self.user_badges[user_id])
            
            available_rewards = []
            
            # Point-based rewards
            if points >= 100:
                available_rewards.append({
                    'type': 'priority_support',
                    'name': '⚡ Supporto Prioritario',
                    'description': 'I tuoi ticket vengono gestiti con priorità',
                    'cost': 0,  # Free for bronze supporters
                    'available': True
                })
            
            if points >= 500:
                available_rewards.append({
                    'type': 'custom_theme',
                    'name': '🎨 Tema Personalizzato',
                    'description': 'Personalizza l\'interfaccia del bot',
                    'cost': 0,  # Free for silver supporters
                    'available': True
                })
            
            if points >= 1000:
                available_rewards.append({
                    'type': 'early_access',
                    'name': '🚀 Accesso Anticipato',
                    'description': 'Prova le nuove funzionalità in anteprima',
                    'cost': 0,  # Free for gold supporters
                    'available': True
                })
            
            # Badge-based rewards
            if badges >= 3:
                available_rewards.append({
                    'type': 'exclusive_lists',
                    'name': '💎 Liste Esclusive',
                    'description': 'Accesso a liste premium riservate',
                    'cost': 0,
                    'available': True
                })
            
            return available_rewards
            
        except Exception as e:
            logger.error(f"Error getting user rewards: {e}")
            return []
    
    def redeem_reward(self, user_id, reward_type):
        """Redeem a reward for user"""
        try:
            rewards = self.get_user_rewards(user_id)
            reward = next((r for r in rewards if r['type'] == reward_type), None)
            
            if not reward:
                return False, "Reward not available"
            
            if not reward['available']:
                return False, "Reward not available for your level"
            
            # Process reward redemption
            success = self._process_reward_redemption(user_id, reward_type)
            
            if success:
                # Log redemption
                with SessionLocal() as session:
                    audit_log = AuditLog(
                        user_id=user_id,
                        action='reward_redeemed',
                        details=json.dumps({
                            'reward_type': reward_type,
                            'reward_name': reward['name']
                        }),
                        timestamp=datetime.now(timezone.utc)
                    )
                    session.add(audit_log)
                    session.commit()
                
                return True, f"Reward '{reward['name']}' redeemed successfully"
            else:
                return False, "Failed to redeem reward"
                
        except Exception as e:
            logger.error(f"Error redeeming reward: {e}")
            return False, str(e)
    
    def _process_reward_redemption(self, user_id, reward_type):
        """Process the actual reward redemption"""
        try:
            # In a full implementation, this would:
            # - Enable priority support flags
            # - Unlock custom themes
            # - Grant early access permissions
            # - Add to exclusive lists
            
            logger.info(f"Processed reward redemption: {reward_type} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing reward redemption: {e}")
            return False
    
    def get_gamification_stats(self):
        """Get overall gamification statistics"""
        return {
            'total_users': len(self.user_points),
            'total_points_awarded': sum(self.user_points.values()),
            'total_badges_earned': sum(len(badges) for badges in self.user_badges.values()),
            'total_achievements_earned': sum(len(achievements) for achievements in self.user_achievements.values()),
            'leaderboard_size': len(self.leaderboard),
            'most_common_achievement': self._get_most_common_achievement(),
            'average_points_per_user': sum(self.user_points.values()) / len(self.user_points) if self.user_points else 0
        }
    
    def _get_most_common_achievement(self):
        """Get the most commonly earned achievement"""
        try:
            achievement_counts = defaultdict(int)
            
            for user_achievements in self.user_achievements.values():
                for achievement in user_achievements:
                    achievement_counts[achievement['achievement_id']] += 1
            
            if achievement_counts:
                most_common_id = max(achievement_counts.items(), key=lambda x: x[1])[0]
                return {
                    'achievement_id': most_common_id,
                    'name': self.achievement_definitions[most_common_id]['name'],
                    'count': achievement_counts[most_common_id]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting most common achievement: {e}")
            return None

# Global gamification service instance
gamification_service = GamificationService()