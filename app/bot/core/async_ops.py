#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Async Operations Module
Provides async wrappers and background job helpers
"""

import asyncio
import logging
import threading
from typing import Callable, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from functools import wraps


# Global thread pool for background tasks
_thread_pool = ThreadPoolExecutor(max_workers=5)


def run_in_background(func: Callable) -> Callable:
    """
    Decorator to run function in background thread
    
    Usage:
        @run_in_background
        def send_email(to, subject, body):
            # Long running task
            ...
        
        # Call returns immediately
        send_email('user@example.com', 'Hi', 'Hello!')
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        future = _thread_pool.submit(func, *args, **kwargs)
        logging.debug(f"Started background task: {func.__name__}")
        return future
    
    return wrapper


def async_to_sync(async_func: Callable) -> Callable:
    """
    Convert async function to sync function
    
    Usage:
        async def fetch_data():
            ...
        
        sync_fetch = async_to_sync(fetch_data)
        result = sync_fetch()  # Runs synchronously
    """
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(async_func(*args, **kwargs))
        finally:
            loop.close()
    
    return wrapper


class BackgroundTaskQueue:
    """
    Simple background task queue for non-critical async operations
    """
    
    def __init__(self, max_workers: int = 3):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks = []
    
    def enqueue(self, func: Callable, *args, **kwargs) -> None:
        """
        Add task to queue
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments for function
        """
        future = self.executor.submit(func, *args, **kwargs)
        self.tasks.append(future)
        logging.info(f"Enqueued background task: {func.__name__}")
    
    def wait_all(self, timeout: Optional[float] = None) -> None:
        """
        Wait for all tasks to complete
        
        Args:
            timeout: Maximum time to wait in seconds
        """
        for future in self.tasks:
            try:
                future.result(timeout=timeout)
            except Exception as e:
                logging.error(f"Background task failed: {e}")
        
        self.tasks.clear()
    
    def shutdown(self) -> None:
        """Shutdown executor gracefully"""
        self.executor.shutdown(wait=True)


# Global task queue
_task_queue = None


def get_task_queue() -> BackgroundTaskQueue:
    """Get or create global task queue"""
    global _task_queue
    if _task_queue is None:
        _task_queue = BackgroundTaskQueue()
    return _task_queue


def queue_task(func: Callable, *args, **kwargs) -> None:
    """
    Queue a function to run in background
    
    Usage:
        queue_task(send_email, 'user@example.com', subject='Hi')
    """
    queue = get_task_queue()
    queue.enqueue(func, *args, **kwargs)


# Helper for async batch operations
async def batch_async(
    items: list,
    async_func: Callable,
    batch_size: int = 10,
    delay: float = 0.1
) -> list:
    """
    Process items in batches asynchronously
    
    Args:
        items: List of items to process
        async_func: Async function to apply to each item
        batch_size: Number of items per batch
        delay: Delay between batches in seconds
        
    Returns:
        List of results
    """
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = await asyncio.gather(*[async_func(item) for item in batch])
        results.extend(batch_results)
        
        if i + batch_size < len(items):
            await asyncio.sleep(delay)
    
    return results
