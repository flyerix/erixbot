import gc
import psutil
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
import threading
import time

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self):
        self.last_cleanup = datetime.now(timezone.utc)
        self.cleanup_interval = 3600  # 1 hour
        self.memory_threshold_mb = 200  # Trigger cleanup at 200MB
        self.memory_history: List[Dict[str, Any]] = []
        self.max_history_size = 100
        self.monitoring_active = False
        self.monitor_thread: threading.Thread = None

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics with enhanced monitoring"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            memory_data = {
                'rss_mb': round(memory_mb, 2),
                'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
                'percent': round(process.memory_percent(), 2),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            # Store in history
            self.memory_history.append(memory_data)
            if len(self.memory_history) > self.max_history_size:
                self.memory_history.pop(0)

            return memory_data
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return {'error': str(e)}

    def should_cleanup(self) -> bool:
        """Check if memory cleanup should be performed"""
        now = datetime.now(timezone.utc)
        time_since_cleanup = (now - self.last_cleanup).total_seconds()

        if time_since_cleanup < self.cleanup_interval:
            return False

        memory_info = self.get_memory_usage()
        if 'rss_mb' in memory_info and memory_info['rss_mb'] > self.memory_threshold_mb:
            return True

        return False

    def perform_cleanup(self) -> Dict[str, Any]:
        """Perform enhanced memory cleanup with monitoring"""
        logger.info("Performing enhanced memory cleanup...")

        memory_before = self.get_memory_usage()

        # Clear various caches and perform garbage collection
        gc.collect()
        gc.collect(2)  # Force cleanup of circular references

        # Clear any accumulated memory history if it's too large
        if len(self.memory_history) > self.max_history_size // 2:
            # Keep only recent history
            self.memory_history = self.memory_history[-self.max_history_size // 2:]

        memory_after = self.get_memory_usage()
        self.last_cleanup = datetime.now(timezone.utc)

        cleanup_info = {
            'memory_before': memory_before,
            'memory_after': memory_after,
            'cleanup_time': self.last_cleanup.isoformat(),
            'garbage_collected': gc.get_count(),
            'history_size': len(self.memory_history)
        }

        memory_saved = memory_before.get('rss_mb', 0) - memory_after.get('rss_mb', 0)
        logger.info(f"Memory cleanup completed. Saved: {memory_saved:.2f} MB")

        return cleanup_info

    def get_memory_trends(self) -> Dict[str, Any]:
        """Analyze memory usage trends"""
        if len(self.memory_history) < 2:
            return {'error': 'Insufficient data for trend analysis'}

        recent_memory = [entry['rss_mb'] for entry in self.memory_history[-10:]]
        avg_memory = sum(recent_memory) / len(recent_memory)
        max_memory = max(recent_memory)
        min_memory = min(recent_memory)

        # Calculate trend (simple linear regression slope)
        if len(recent_memory) > 1:
            n = len(recent_memory)
            x = list(range(n))
            y = recent_memory
            slope = sum((x[i] - sum(x)/n) * (y[i] - sum(y)/n) for i in range(n)) / sum((x[i] - sum(x)/n)**2 for i in range(n)) if n > 1 else 0
            trend = 'increasing' if slope > 0.1 else 'decreasing' if slope < -0.1 else 'stable'
        else:
            trend = 'stable'

        return {
            'average_mb': round(avg_memory, 2),
            'max_mb': max_memory,
            'min_mb': min_memory,
            'trend': trend,
            'data_points': len(recent_memory)
        }

    def start_monitoring(self, interval_seconds: int = 60):
        """Start background memory monitoring"""
        if self.monitoring_active:
            logger.warning("Memory monitoring already active")
            return

        self.monitoring_active = True

        def monitor_loop():
            while self.monitoring_active:
                try:
                    memory_info = self.get_memory_usage()
                    rss_mb = memory_info.get('rss_mb', 0)

                    # Log warning if memory usage is high
                    if rss_mb > self.memory_threshold_mb * 1.5:  # 150% of threshold
                        logger.warning(f"High memory usage detected: {rss_mb:.2f} MB")

                    # Auto-cleanup if memory is too high
                    if rss_mb > self.memory_threshold_mb * 2:  # 200% of threshold
                        logger.critical(f"Critical memory usage: {rss_mb:.2f} MB - triggering emergency cleanup")
                        self.force_cleanup()

                except Exception as e:
                    logger.error(f"Error in memory monitoring: {e}")

                time.sleep(interval_seconds)

        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"Memory monitoring started with {interval_seconds}s interval")

    def stop_monitoring(self):
        """Stop background memory monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Memory monitoring stopped")

    def is_monitoring(self) -> bool:
        """Check if memory monitoring is currently active"""
        return self.monitoring_active

    def force_cleanup(self) -> Dict[str, Any]:
        """Force immediate memory cleanup"""
        logger.info("Forcing memory cleanup...")
        return self.perform_cleanup()

# Global memory manager instance
memory_manager = MemoryManager()
