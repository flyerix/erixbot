import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any, List
import logging

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: List[asyncio.Task] = []
        self.max_concurrent_tasks = max_workers * 2

    async def run_in_background(self, coro: Callable[..., Any], *args, **kwargs) -> None:
        """Run coroutine in background"""
        if len(self.tasks) >= self.max_concurrent_tasks:
            logger.warning(f"Max concurrent tasks reached ({self.max_concurrent_tasks}), task queued")
            # Clean up completed tasks
            self.tasks = [task for task in self.tasks if not task.done()]

        task = asyncio.create_task(coro(*args, **kwargs))
        self.tasks.append(task)
        task.add_done_callback(self.tasks.remove)

        # Log task creation
        logger.info(f"Background task started: {coro.__name__}")

    def run_in_thread(self, func: Callable[..., Any], *args, **kwargs) -> asyncio.Future:
        """Run function in thread pool"""
        return asyncio.get_event_loop().run_in_executor(self.executor, func, *args, **kwargs)

    async def wait_for_all_tasks(self, timeout: float = 30.0) -> None:
        """Wait for all background tasks to complete"""
        if self.tasks:
            try:
                await asyncio.wait(self.tasks, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for tasks to complete ({timeout}s)")
            finally:
                # Clean up any remaining tasks
                for task in self.tasks:
                    if not task.done():
                        task.cancel()
                self.tasks.clear()

    def get_active_task_count(self) -> int:
        """Get count of active background tasks"""
        return len([task for task in self.tasks if not task.done()])

    def shutdown(self) -> None:
        """Shutdown the task manager"""
        self.executor.shutdown(wait=True)
        # Cancel all pending tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        self.tasks.clear()
        logger.info("Background task manager shutdown complete")

# Global task manager instance
task_manager = BackgroundTaskManager()
