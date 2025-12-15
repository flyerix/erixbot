import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any, List, Dict
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class BackgroundTaskManager:
    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: List[asyncio.Task] = []
        self.max_concurrent_tasks = max_workers * 2
        self.task_stats: Dict[str, Dict[str, Any]] = {}
        self.task_queue = asyncio.Queue(maxsize=100)  # Limit queue size

    async def run_in_background(self, coro: Callable[..., Any], *args, **kwargs) -> None:
        """Run coroutine in background with enhanced monitoring"""
        task_id = f"{coro.__name__}_{time.time()}"
        start_time = time.time()

        # Track task statistics
        self.task_stats[task_id] = {
            'name': coro.__name__,
            'start_time': start_time,
            'status': 'queued'
        }

        if len(self.tasks) >= self.max_concurrent_tasks:
            logger.warning(f"Max concurrent tasks reached ({self.max_concurrent_tasks}), task queued")
            # Try to add to queue instead of immediate execution
            try:
                await self.task_queue.put((coro, args, kwargs, task_id))
                self.task_stats[task_id]['status'] = 'queued'
                logger.info(f"Task {task_id} queued for background execution")
                return
            except asyncio.QueueFull:
                logger.error(f"Task queue full, dropping task {task_id}")
                return

        # Execute immediately
        task = asyncio.create_task(self._execute_task(coro, args, kwargs, task_id))
        self.tasks.append(task)
        task.add_done_callback(lambda t: self._cleanup_task(t, task_id))

        logger.info(f"Background task started: {task_id}")

    async def _execute_task(self, coro: Callable[..., Any], args, kwargs, task_id: str):
        """Execute task with monitoring"""
        try:
            self.task_stats[task_id]['status'] = 'running'
            result = await coro(*args, **kwargs)
            self.task_stats[task_id]['status'] = 'completed'
            self.task_stats[task_id]['end_time'] = time.time()
            self.task_stats[task_id]['duration'] = self.task_stats[task_id]['end_time'] - self.task_stats[task_id]['start_time']
            logger.info(f"Task {task_id} completed successfully in {self.task_stats[task_id]['duration']:.2f}s")
            return result
        except Exception as e:
            self.task_stats[task_id]['status'] = 'failed'
            self.task_stats[task_id]['error'] = str(e)
            self.task_stats[task_id]['end_time'] = time.time()
            logger.error(f"Task {task_id} failed: {e}")
            raise

    def _cleanup_task(self, task: asyncio.Task, task_id: str):
        """Clean up completed task"""
        try:
            self.tasks.remove(task)
        except ValueError:
            pass  # Task already removed

        # Clean up old task stats (keep last 1000)
        if len(self.task_stats) > 1000:
            oldest_tasks = sorted(self.task_stats.keys(),
                                key=lambda k: self.task_stats[k].get('start_time', 0))[:100]
            for old_task in oldest_tasks:
                del self.task_stats[old_task]

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

    def get_task_stats(self) -> Dict[str, Any]:
        """Get comprehensive task statistics"""
        active_tasks = self.get_active_task_count()
        queued_tasks = self.task_queue.qsize()

        completed_tasks = len([stats for stats in self.task_stats.values() if stats.get('status') == 'completed'])
        failed_tasks = len([stats for stats in self.task_stats.values() if stats.get('status') == 'failed'])

        # Calculate average task duration
        durations = [stats.get('duration', 0) for stats in self.task_stats.values() if stats.get('status') == 'completed']
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            'active_tasks': active_tasks,
            'queued_tasks': queued_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks,
            'avg_task_duration': f"{avg_duration:.2f}s",
            'total_tracked_tasks': len(self.task_stats)
        }

    async def process_queued_tasks(self):
        """Process tasks from the queue when slots become available"""
        try:
            while not self.task_queue.empty() and len(self.tasks) < self.max_concurrent_tasks:
                try:
                    coro, args, kwargs, task_id = self.task_queue.get_nowait()
                    task = asyncio.create_task(self._execute_task(coro, args, kwargs, task_id))
                    self.tasks.append(task)
                    task.add_done_callback(lambda t: self._cleanup_task(t, task_id))
                    logger.info(f"Processed queued task: {task_id}")
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    logger.error(f"Error processing queued task: {e}")
        except Exception as e:
            logger.error(f"Error in process_queued_tasks: {e}")
            # Ensure this method always completes without raising exceptions

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
