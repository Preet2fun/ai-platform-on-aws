# app/core/task_registry.py
"""Background task registry for graceful shutdown.

Tracks all fire-and-forget asyncio tasks so they can be cancelled
when the application shuts down (ECS task replacement, deploy, etc.).

Usage:
    from app.core.task_registry import track_task
    track_task(asyncio.create_task(my_coroutine()))
"""

import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)

_active_tasks: Set[asyncio.Task] = set()


def track_task(task: asyncio.Task) -> asyncio.Task:
    """Register a background task for shutdown cancellation.
    
    The task is automatically removed from the registry when it completes
    (whether successfully, with an error, or via cancellation).
    """
    _active_tasks.add(task)
    task.add_done_callback(_active_tasks.discard)
    return task


async def cancel_all_tasks() -> None:
    """Cancel all tracked in-flight tasks. Called during shutdown."""
    if not _active_tasks:
        return
    logger.info("Cancelling %d in-flight background tasks", len(_active_tasks))
    for task in _active_tasks:
        task.cancel()
    await asyncio.gather(*_active_tasks, return_exceptions=True)
    _active_tasks.clear()
    logger.info("All background tasks cancelled")


def active_task_count() -> int:
    """Return the number of currently tracked tasks."""
    return len(_active_tasks)
