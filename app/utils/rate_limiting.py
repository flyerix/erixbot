from collections import defaultdict
import time
from typing import Dict, List, Any

class AdvancedRateLimiter:
    def __init__(self):
        self.user_actions: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    def check_limit(self, user_id: int, action: str, limit: int, window: int) -> bool:
        """Check if user is within rate limits for specific action"""
        now = time.time()
        actions = self.user_actions[user_id][action]

        # Clean old entries
        actions[:] = [t for t in actions if now - t < window]

        if len(actions) >= limit:
            return False

        actions.append(now)
        return True

    def get_remaining_actions(self, user_id: int, action: str, limit: int, window: int) -> int:
        """Get remaining actions allowed for user"""
        now = time.time()
        actions = self.user_actions[user_id][action]

        # Clean old entries
        actions[:] = [t for t in actions if now - t < window]

        return max(0, limit - len(actions))

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

    def get_stats(self) -> Dict[str, int]:
        """Get rate limiting statistics"""
        total_users = len(self.user_actions)
        total_actions = sum(len(actions) for user_actions in self.user_actions.values()
                          for actions in user_actions.values())
        return {
            'total_users_tracked': total_users,
            'total_actions_tracked': total_actions
        }

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
