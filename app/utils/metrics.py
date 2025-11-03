from dataclasses import dataclass, field
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

@dataclass
class BotMetrics:
    total_users: int = 0
    active_tickets: int = 0
    ai_responses: int = 0
    avg_response_time: float = 0.0
    error_rate: float = 0.0
    total_messages: int = 0
    admin_actions: int = 0
    backup_count: int = 0
    memory_usage_mb: float = 0.0
    rate_limit_violations: int = 0
    ai_cache_hits: int = 0
    ai_cache_misses: int = 0
    background_tasks_completed: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_admin_only_metrics(self) -> Dict[str, Any]:
        """Get metrics that should only be visible to admins"""
        return {
            'memory_usage_mb': f"{self.memory_usage_mb:.2f} MB",
            'rate_limit_violations': self.rate_limit_violations,
            'ai_cache_hits': self.ai_cache_hits,
            'ai_cache_misses': self.ai_cache_misses,
            'ai_cache_hit_rate': f"{(self.ai_cache_hits / max(1, self.ai_cache_hits + self.ai_cache_misses)) * 100:.1f}%" if (self.ai_cache_hits + self.ai_cache_misses) > 0 else "0%",
            'background_tasks_completed': self.background_tasks_completed,
            'error_rate': f"{self.error_rate:.2%}",
            'avg_response_time': f"{self.avg_response_time:.2f}s"
        }

class MetricsCollector:
    def __init__(self):
        self.metrics = BotMetrics()
        self.response_times: List[float] = []
        self.errors_count = 0
        self.total_requests = 0

    def record_ai_response(self, response_time: float, cached: bool = False):
        """Record AI response time"""
        self.response_times.append(response_time)
        self.metrics.ai_responses += 1
        self.total_requests += 1

        # Track cache performance
        if cached:
            self.metrics.ai_cache_hits += 1
        else:
            self.metrics.ai_cache_misses += 1

        # Keep only last 100 response times
        if len(self.response_times) > 100:
            self.response_times.pop(0)

        self.metrics.avg_response_time = sum(self.response_times) / len(self.response_times)
        self.metrics.last_updated = datetime.now(timezone.utc)

    def record_error(self):
        """Record an error"""
        self.errors_count += 1
        self.total_requests += 1
        self.metrics.error_rate = self.errors_count / max(1, self.total_requests)
        self.metrics.last_updated = datetime.now(timezone.utc)

    def record_rate_limit_violation(self):
        """Record a rate limit violation"""
        self.metrics.rate_limit_violations += 1
        self.metrics.last_updated = datetime.now(timezone.utc)

    def record_background_task_completion(self):
        """Record background task completion"""
        self.metrics.background_tasks_completed += 1
        self.metrics.last_updated = datetime.now(timezone.utc)

    def update_memory_usage(self, memory_mb: float):
        """Update memory usage"""
        self.metrics.memory_usage_mb = memory_mb
        self.metrics.last_updated = datetime.now(timezone.utc)

    def record_message(self):
        """Record a user message"""
        self.metrics.total_messages += 1
        self.metrics.last_updated = datetime.now(timezone.utc)

    def record_admin_action(self):
        """Record an admin action"""
        self.metrics.admin_actions += 1
        self.metrics.last_updated = datetime.now(timezone.utc)

    def record_backup(self):
        """Record a backup operation"""
        self.metrics.backup_count += 1
        self.metrics.last_updated = datetime.now(timezone.utc)

    def update_user_count(self, count: int):
        """Update total user count"""
        self.metrics.total_users = count
        self.metrics.last_updated = datetime.now(timezone.utc)

    def update_ticket_count(self, count: int):
        """Update active ticket count"""
        self.metrics.active_tickets = count
        self.metrics.last_updated = datetime.now(timezone.utc)

    def get_metrics(self) -> Dict[str, Any]:
        """Get all metrics"""
        return {
            'total_users': self.metrics.total_users,
            'active_tickets': self.metrics.active_tickets,
            'ai_responses': self.metrics.ai_responses,
            'avg_response_time': f"{self.metrics.avg_response_time:.2f}s",
            'error_rate': f"{self.metrics.error_rate:.2%}",
            'total_messages': self.metrics.total_messages,
            'admin_actions': self.metrics.admin_actions,
            'backup_count': self.metrics.backup_count,
            'uptime': self._calculate_uptime(),
            'last_updated': self.metrics.last_updated.isoformat()
        }

    def _calculate_uptime(self) -> str:
        """Calculate bot uptime (simplified)"""
        # This would need to be implemented with actual start time tracking
        return "24/7"  # Placeholder

    def reset_counters(self):
        """Reset certain counters (for maintenance)"""
        self.errors_count = 0
        self.total_requests = 0
        self.response_times.clear()
        self.metrics.error_rate = 0.0
        self.metrics.avg_response_time = 0.0
        self.metrics.last_updated = datetime.now(timezone.utc)

# Global metrics collector instance
metrics_collector = MetricsCollector()
