from collections import defaultdict
import time
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class AdvancedRateLimiter:
    def __init__(self):
        self.user_actions: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self.user_bans: Dict[int, float] = {}  # user_id -> ban_expiry_time
        self.suspicious_activity: Dict[int, int] = defaultdict(int)  # user_id -> suspicious_count

    def is_banned(self, user_id: int) -> bool:
        """Check if user is currently banned"""
        if user_id in self.user_bans:
            if time.time() > self.user_bans[user_id]:
                # Ban expired, remove it
                del self.user_bans[user_id]
                return False
            return True
        return False

    def ban_user(self, user_id: int, duration_seconds: int):
        """Ban a user for specified duration"""
        self.user_bans[user_id] = time.time() + duration_seconds
        logger.warning(f"User {user_id} banned for {duration_seconds} seconds")

    def check_limit(self, user_id: int, action: str, limit: int, window: int) -> bool:
        """Check if user is within rate limits for specific action"""
        # Check if user is banned
        if self.is_banned(user_id):
            logger.warning(f"Rate limit check blocked - user {user_id} is banned")
            return False

        now = time.time()
        actions = self.user_actions[user_id][action]

        # Clean old entries
        actions[:] = [t for t in actions if now - t < window]

        if len(actions) >= limit:
            # Increment suspicious activity counter
            self.suspicious_activity[user_id] += 1

            # Auto-ban if too many violations
            if self.suspicious_activity[user_id] >= 5:
                self.ban_user(user_id, 3600)  # 1 hour ban
                logger.warning(f"User {user_id} auto-banned for excessive rate limit violations")

            return False

        actions.append(now)

        # Reset suspicious counter on successful action
        if self.suspicious_activity[user_id] > 0:
            self.suspicious_activity[user_id] = max(0, self.suspicious_activity[user_id] - 1)

        return True

    def get_remaining_actions(self, user_id: int, action: str, limit: int, window: int) -> int:
        """Get remaining actions allowed for user"""
        if self.is_banned(user_id):
            return 0

        now = time.time()
        actions = self.user_actions[user_id][action]

        # Clean old entries
        actions[:] = [t for t in actions if now - t < window]

        return max(0, limit - len(actions))

    def get_ban_status(self, user_id: int) -> Dict[str, float]:
        """Get ban status for user"""
        if user_id in self.user_bans:
            remaining_time = self.user_bans[user_id] - time.time()
            if remaining_time > 0:
                return {'banned': True, 'remaining_seconds': remaining_time}
            else:
                del self.user_bans[user_id]
        return {'banned': False, 'remaining_seconds': 0}

    def get_reset_time(self, user_id: int, action: str, window: int) -> float:
        """Get time until rate limit resets"""
        actions = self.user_actions[user_id][action]
        if not actions:
            return 0

        now = time.time()
        oldest_action = min(actions)
        return max(0, window - (now - oldest_action))

    def clear_user_limits(self, user_id: int):
        """Clear all rate limits for a user (admin function)"""
        if user_id in self.user_actions:
            del self.user_actions[user_id]
        if user_id in self.user_bans:
            del self.user_bans[user_id]
        if user_id in self.suspicious_activity:
            del self.suspicious_activity[user_id]

    def get_stats(self) -> Dict[str, int]:
        """Get rate limiting statistics"""
        total_users = len(self.user_actions)
        total_actions = sum(len(actions) for user_actions in self.user_actions.values()
                           for actions in user_actions.values())
        active_bans = len([uid for uid, expiry in self.user_bans.items() if time.time() < expiry])
        suspicious_users = len([uid for uid, count in self.suspicious_activity.items() if count > 0])

        return {
            'total_users_tracked': total_users,
            'total_actions_tracked': total_actions,
            'active_bans': active_bans,
            'suspicious_users': suspicious_users
        }

    def adaptive_rate_limiting(self, user_id: int, action: str, base_limit: int, base_window: int) -> bool:
        """Adaptive rate limiting based on user behavior"""
        suspicious_level = self.suspicious_activity.get(user_id, 0)

        # Increase restrictions for suspicious users
        if suspicious_level > 0:
            adjusted_limit = max(1, base_limit // (suspicious_level + 1))
            adjusted_window = base_window // 2  # Shorter window for suspicious users
        else:
            adjusted_limit = base_limit
            adjusted_window = base_window

        return self.check_limit(user_id, action, adjusted_limit, adjusted_window)

# Global rate limiter instance
rate_limiter = AdvancedRateLimiter()

# Rate limit configurations
RATE_LIMITS = {
    'search_list': {'limit': 10, 'window': 60},  # 10 searches per minute
    'open_ticket': {'limit': 3, 'window': 300},  # 3 tickets per 5 minutes
    'send_message': {'limit': 20, 'window': 60},  # 20 messages per minute
    'admin_action': {'limit': 50, 'window': 60},  # 50 admin actions per minute
    'ai_request': {'limit': 5, 'window': 60},     # 5 AI requests per minute
}
