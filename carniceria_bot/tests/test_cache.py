"""
Unit Tests for Cache Manager
"""

import pytest
import time
from bot_sales.core.cache_manager import CacheManager, cached, invalidate_cache


class TestCacheManager:
    """Tests for CacheManager"""
    
    @pytest.fixture
    def cache(self):
        return CacheManager()
    
    def test_set_and_get(self, cache):
        cache.set('test_key', 'test_value', ttl=60)
        value = cache.get('test_key')
        
        assert value == 'test_value'
    
    def test_get_nonexistent_key(self, cache):
        value = cache.get('nonexistent_key')
        
        assert value is None
    
    def test_ttl_expiry(self, cache):
        cache.set('expiring_key', 'value', ttl=1)
        
        # Should exist immediately
        assert cache.get('expiring_key') == 'value'
        
        # Wait for expiry
        time.sleep(1.5)
        
        # Should be expired
        assert cache.get('expiring_key') is None
    
    def test_delete(self, cache):
        cache.set('delete_me', 'value')
        assert cache.get('delete_me') == 'value'
        
        cache.delete('delete_me')
        assert cache.get('delete_me') is None
    
    def test_clear_prefix(self, cache):
        cache.set('product:1', {'id': 1})
        cache.set('product:2', {'id': 2})
        cache.set('user:1', {'id': 1})
        
        count = cache.clear_prefix('product')
        
        assert count == 2
        assert cache.get('product:1') is None
        assert cache.get('product:2') is None
        assert cache.get('user:1') is not None  # Different prefix
    
    def test_stats(self, cache):
        # Reset stats
        cache.cache_stats = {'hits': 0, 'misses': 0, 'sets': 0, 'deletes': 0}
        
        cache.set('key1', 'value1')
        cache.get('key1')  # Hit
        cache.get('nonexistent')  # Miss
        
        stats = cache.get_stats()
        
        assert stats['hits'] >= 1
        assert stats['misses'] >= 1
        assert stats['sets'] >= 1
    
    def test_cache_dict_values(self, cache):
        data = {'name': 'Test', 'count': 123}
        cache.set('dict_key', data)
        
        retrieved = cache.get('dict_key')
        assert retrieved == data


class TestCacheDecorator:
    """Tests for @cached decorator"""
    
    def test_cached_decorator(self):
        call_count = {'count': 0}
        
        @cached('test_func', ttl=60)
        def expensive_function(x):
            call_count['count'] += 1
            return x * 2
        
        # First call - cache miss
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count['count'] == 1
        
        # Second call - cache hit
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count['count'] == 1  # Function not called again
    
    def test_cached_different_args(self):
        @cached('test_func2', ttl=60)
        def add(a, b):
            return a + b
        
        result1 = add(1, 2)
        result2 = add(3, 4)
        
        assert result1 == 3
        assert result2 == 7
    
    def test_invalidate_cache(self):
        call_count = {'count': 0}
        
        @cached('invalidate_test', ttl=60)
        def get_data():
            call_count['count'] += 1
            return 'data'
        
        # First call
        get_data()
        assert call_count['count'] == 1
        
        # Second call - cached
        get_data()
        assert call_count['count'] == 1
        
        # Invalidate cache
        invalidate_cache('invalidate_test')
        
        # Third call - cache miss after invalidation
        get_data()
        assert call_count['count'] == 2
