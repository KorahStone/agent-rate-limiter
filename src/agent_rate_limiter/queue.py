"""Priority queue for rate-limited requests."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional, TypeVar

from .models import Priority, QueueFullError, QueueTimeoutError

T = TypeVar("T")


@dataclass(order=True)
class QueueItem:
    """An item in the priority queue."""
    
    priority: int
    timestamp: float
    request_id: str = field(compare=False)
    future: asyncio.Future[Any] = field(compare=False)
    
    # Request details
    method: str = field(compare=False, default="GET")
    url: str = field(compare=False, default="")
    kwargs: dict[str, Any] = field(compare=False, default_factory=dict)


class PriorityQueue:
    """Async priority queue for rate-limited requests."""
    
    def __init__(
        self,
        max_size: int = 1000,
        default_timeout: float = 300.0,
    ):
        self._max_size = max_size
        self._default_timeout = default_timeout
        self._queue: list[QueueItem] = []
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Condition()
        self._request_counter = 0
        self._processing = False
    
    @property
    def size(self) -> int:
        """Current queue size."""
        return len(self._queue)
    
    @property
    def is_full(self) -> bool:
        """Check if queue is at max capacity."""
        return len(self._queue) >= self._max_size
    
    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._queue) == 0
    
    async def put(
        self,
        method: str,
        url: str,
        priority: Priority = Priority.NORMAL,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Any:
        """Add a request to the queue and wait for result.
        
        Args:
            method: HTTP method
            url: Request URL
            priority: Request priority
            timeout: Timeout for waiting in queue
            **kwargs: Additional request arguments
            
        Returns:
            The result when the request is processed
            
        Raises:
            QueueFullError: If queue is at max capacity
            QueueTimeoutError: If timeout is reached before processing
        """
        async with self._lock:
            if self.is_full:
                raise QueueFullError(f"Queue is full (max size: {self._max_size})")
            
            self._request_counter += 1
            request_id = f"req-{self._request_counter}"
            
            future: asyncio.Future[Any] = asyncio.Future()
            
            item = QueueItem(
                priority=priority.value,
                timestamp=time.time(),
                request_id=request_id,
                future=future,
                method=method,
                url=url,
                kwargs=kwargs,
            )
            
            # Insert in priority order (lower priority value = higher priority)
            self._insert_sorted(item)
        
        # Notify that queue is not empty
        async with self._not_empty:
            self._not_empty.notify()
        
        # Wait for result with timeout
        timeout = timeout or self._default_timeout
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # Remove from queue if still there
            await self._remove_item(request_id)
            raise QueueTimeoutError(f"Request {request_id} timed out after {timeout}s")
    
    def _insert_sorted(self, item: QueueItem) -> None:
        """Insert item maintaining sorted order."""
        # Binary search for insertion point
        lo, hi = 0, len(self._queue)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._queue[mid] < item:
                lo = mid + 1
            else:
                hi = mid
        self._queue.insert(lo, item)
    
    async def get(self) -> Optional[QueueItem]:
        """Get the highest priority item from the queue.
        
        Returns:
            The highest priority item, or None if queue is empty
        """
        async with self._lock:
            if self._queue:
                return self._queue.pop(0)
            return None
    
    async def wait_for_item(self, timeout: Optional[float] = None) -> Optional[QueueItem]:
        """Wait for an item to be available.
        
        Args:
            timeout: Max time to wait
            
        Returns:
            The highest priority item, or None if timeout
        """
        async with self._not_empty:
            if self.is_empty:
                try:
                    await asyncio.wait_for(
                        self._not_empty.wait(),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    return None
        
        return await self.get()
    
    async def _remove_item(self, request_id: str) -> bool:
        """Remove an item from the queue by request ID."""
        async with self._lock:
            for i, item in enumerate(self._queue):
                if item.request_id == request_id:
                    self._queue.pop(i)
                    return True
            return False
    
    def complete(self, request_id: str, result: Any) -> None:
        """Mark a request as complete with a result."""
        for item in self._queue:
            if item.request_id == request_id:
                if not item.future.done():
                    item.future.set_result(result)
                return
    
    def fail(self, request_id: str, error: Exception) -> None:
        """Mark a request as failed with an error."""
        for item in self._queue:
            if item.request_id == request_id:
                if not item.future.done():
                    item.future.set_exception(error)
                return
    
    async def clear(self) -> int:
        """Clear all items from the queue.
        
        Returns:
            Number of items cleared
        """
        async with self._lock:
            count = len(self._queue)
            for item in self._queue:
                if not item.future.done():
                    item.future.cancel()
            self._queue.clear()
            return count
    
    def get_stats(self) -> dict[str, Any]:
        """Get queue statistics."""
        priority_counts = {p.name: 0 for p in Priority}
        for item in self._queue:
            for p in Priority:
                if p.value == item.priority:
                    priority_counts[p.name] += 1
                    break
        
        return {
            "size": self.size,
            "max_size": self._max_size,
            "is_full": self.is_full,
            "total_requests": self._request_counter,
            "by_priority": priority_counts,
        }
