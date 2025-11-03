import gc
import psutil
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self):
        self.last_cleanup = datetime.now(timezone.utc)
        self.cleanup_interval = 3600  # 1 hour
        self.memory_threshold_mb = 200  # Trigger cleanup at 200MB

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get current memory usage statistics"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            return {
                'rss_mb': round(memory_mb, 2),
                'vms_mb': round(memory_info.vms / 1024 / 1024, 2),
                'percent': round(process.memory_percent(), 2)
            }
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
        """Perform memory cleanup"""
        logger.info("Performing memory cleanup...")

        memory_before = self.get_memory_usage()

        # Clear various caches and perform garbage collection
        gc.collect()

        # Force cleanup of any circular references
        gc.collect(2)

        memory_after = self.get_memory_usage()
        self.last_cleanup = datetime.now(timezone.utc)

        cleanup_info = {
            'memory_before': memory_before,
            'memory_after': memory_after,
            'cleanup_time': self.last_cleanup.isoformat(),
            'garbage_collected': gc.get_count()
        }

        memory_saved = memory_before.get('rss_mb', 0) - memory_after.get('rss_mb', 0)
        logger.info(f"Memory cleanup completed. Saved: {memory_saved:.2f} MB")

        return cleanup_info

    def force_cleanup(self) -> Dict[str, Any]:
        """Force immediate memory cleanup"""
        logger.info("Forcing memory cleanup...")
        return self.perform_cleanup()

# Global memory manager instance
memory_manager = MemoryManager()
