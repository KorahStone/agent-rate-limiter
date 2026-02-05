"""Tests for priority queue."""

import pytest
import asyncio

from agent_rate_limiter.queue import PriorityQueue, QueueItem
from agent_rate_limiter.models import Priority, QueueFullError, QueueTimeoutError


class TestQueueItem:
    """Tests for QueueItem dataclass."""
    
    def test_ordering(self):
        """Test queue items are ordered by priority then timestamp."""
        import time
        
        item1 = QueueItem(
            priority=Priority.HIGH.value,
            timestamp=time.time(),
            request_id="req-1",
            future=asyncio.Future(),
        )
        
        item2 = QueueItem(
            priority=Priority.LOW.value,
            timestamp=time.time(),
            request_id="req-2",
            future=asyncio.Future(),
        )
        
        # Higher priority (lower value) should come first
        assert item1 < item2
    
    def test_same_priority_ordered_by_timestamp(self):
        """Test same priority items ordered by timestamp."""
        import time
        
        item1 = QueueItem(
            priority=Priority.NORMAL.value,
            timestamp=1.0,
            request_id="req-1",
            future=asyncio.Future(),
        )
        
        item2 = QueueItem(
            priority=Priority.NORMAL.value,
            timestamp=2.0,
            request_id="req-2",
            future=asyncio.Future(),
        )
        
        # Earlier timestamp should come first
        assert item1 < item2


class TestPriorityQueue:
    """Tests for PriorityQueue class."""
    
    def test_init(self):
        """Test queue initialization."""
        queue = PriorityQueue(max_size=100)
        assert queue.size == 0
        assert queue.is_empty is True
        assert queue.is_full is False
    
    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Test basic put and get."""
        queue = PriorityQueue()
        
        # Start a task that will complete the request
        async def completer():
            await asyncio.sleep(0.1)
            item = await queue.get()
            if item:
                item.future.set_result({"status": "ok"})
        
        task = asyncio.create_task(completer())
        
        result = await queue.put("GET", "https://api.example.com", timeout=5.0)
        assert result == {"status": "ok"}
        
        await task
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Test items are returned in priority order."""
        queue = PriorityQueue()
        
        # Directly add items to queue for testing ordering
        import time
        
        async with queue._lock:
            for priority, name in [
                (Priority.LOW, "low"),
                (Priority.HIGH, "high"),
                (Priority.NORMAL, "normal"),
                (Priority.CRITICAL, "critical"),
            ]:
                queue._request_counter += 1
                item = QueueItem(
                    priority=priority.value,
                    timestamp=time.time(),
                    request_id=f"req-{queue._request_counter}",
                    future=asyncio.Future(),
                    method="GET",
                    url=f"https://api.example.com/{name}",
                )
                queue._insert_sorted(item)
        
        # Get items - should be in priority order
        urls = []
        while not queue.is_empty:
            item = await queue.get()
            if item:
                urls.append(item.url.split("/")[-1])
                item.future.cancel()  # Cancel to cleanup
        
        # Should be ordered: critical, high, normal, low
        assert urls == ["critical", "high", "normal", "low"]
    
    @pytest.mark.asyncio
    async def test_queue_full_error(self):
        """Test QueueFullError when queue is full."""
        queue = PriorityQueue(max_size=2)
        
        # Fill the queue (use background tasks)
        async def fill():
            try:
                await queue.put("GET", "https://api.example.com/1", timeout=10)
            except:
                pass
        
        task1 = asyncio.create_task(fill())
        task2 = asyncio.create_task(fill())
        
        await asyncio.sleep(0.01)  # Let items get added
        
        # Third item should fail
        with pytest.raises(QueueFullError):
            await queue.put("GET", "https://api.example.com/3", timeout=0.1)
        
        # Cleanup
        task1.cancel()
        task2.cancel()
        try:
            await task1
        except:
            pass
        try:
            await task2
        except:
            pass
    
    @pytest.mark.asyncio
    async def test_queue_timeout(self):
        """Test QueueTimeoutError on timeout."""
        queue = PriorityQueue()
        
        with pytest.raises(QueueTimeoutError):
            await queue.put("GET", "https://api.example.com", timeout=0.01)
    
    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing the queue."""
        queue = PriorityQueue()
        
        # Add items
        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                queue.put("GET", f"https://api.example.com/{i}", timeout=10)
            )
            tasks.append(task)
        
        await asyncio.sleep(0.01)
        assert queue.size == 3
        
        # Clear
        cleared = await queue.clear()
        assert cleared == 3
        assert queue.size == 0
        
        # Tasks should be cancelled
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    def test_get_stats(self):
        """Test getting queue statistics."""
        queue = PriorityQueue(max_size=100)
        stats = queue.get_stats()
        
        assert "size" in stats
        assert "max_size" in stats
        assert "is_full" in stats
        assert "total_requests" in stats
        assert "by_priority" in stats
        
        assert stats["max_size"] == 100
        assert stats["is_full"] is False
    
    @pytest.mark.asyncio
    async def test_wait_for_item_timeout(self):
        """Test wait_for_item with timeout."""
        queue = PriorityQueue()
        
        # Should return None on timeout
        item = await queue.wait_for_item(timeout=0.01)
        assert item is None
    
    @pytest.mark.asyncio
    async def test_wait_for_item_with_item(self):
        """Test wait_for_item when item is available."""
        queue = PriorityQueue()
        
        # Add an item in background
        async def add_item():
            await asyncio.sleep(0.01)
            # Directly manipulate for testing
            async with queue._lock:
                import time
                queue._request_counter += 1
                item = QueueItem(
                    priority=Priority.NORMAL.value,
                    timestamp=time.time(),
                    request_id=f"req-{queue._request_counter}",
                    future=asyncio.Future(),
                    method="GET",
                    url="https://api.example.com",
                )
                queue._queue.append(item)
            async with queue._not_empty:
                queue._not_empty.notify()
        
        task = asyncio.create_task(add_item())
        
        item = await queue.wait_for_item(timeout=1.0)
        assert item is not None
        assert item.url == "https://api.example.com"
        
        await task
