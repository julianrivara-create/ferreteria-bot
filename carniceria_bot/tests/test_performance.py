"""
Performance Benchmarks
Track performance improvements over time
"""

import time
import pytest
from bot_sales.core.cache_manager import cached, get_cache
from bot_sales.core.database import Database


class TestPerformance:
    """Performance benchmark tests"""
    
    def test_cache_speedup(self, benchmark):
        """Measure cache performance improvement"""
        call_count = {'count': 0}
        
        @cached('perf_test', ttl=60)
        def expensive_calculation(n):
            call_count['count'] += 1
            time.sleep(0.01)  # Simulate slow operation
            return n * 2
        
        # Warm up
        expensive_calculation(5)
        
        # Benchmark cached call (should be much faster)
        result = benchmark(expensive_calculation, 5)
        
        assert result == 10
        # Should only be called once (cached)
        assert call_count['count'] == 1
    
    def test_database_query_speed(self, temp_db, benchmark):
        """Benchmark database query performance"""
        
        def query_products():
            return temp_db.get_all_products()
        
        result = benchmark(query_products)
        
        # Should complete in reasonable time
        assert benchmark.stats['mean'] < 0.1  # Less than 100ms
    
    def test_index_performance(self, temp_db):
        """Verify indices improve query performance"""
        # This would compare queries with/without indices
        # Current: indices exist, should be fast
        
        start = time.time()
        products = temp_db.find_matches("iPhone 15", None, None)
        elapsed = time.time() - start
        
        # With indices, should be fast
        assert elapsed < 0.05  # Less than 50ms


# Performance targets
PERFORMANCE_TARGETS = {
    'api_response_p95': 500,  # ms
    'cache_hit_rate': 60,  # percentage
    'db_query_avg': 50,  # ms
    'startup_time': 5,  # seconds
}


def measure_startup_time():
    """Measure application startup time"""
    start = time.time()
    
    # Simulate app startup
    from bot_sales.core.database import Database
    from bot_sales.core.business_logic import BusinessLogic
    from bot_sales.core.cache_manager import get_cache
    from bot_sales.core.monitoring import get_monitoring
    
    # Initialize components
    cache = get_cache()
    monitoring = get_monitoring()
    
    elapsed = time.time() - start
    
    print(f"Startup time: {elapsed:.2f}s")
    assert elapsed < PERFORMANCE_TARGETS['startup_time']
    
    return elapsed


if __name__ == '__main__':
    # Run performance measurements
    startup_time = measure_startup_time()
    
    print("\n📊 Performance Report:")
    print(f"Startup Time: {startup_time:.2f}s (target: <{PERFORMANCE_TARGETS['startup_time']}s)")
    print("\nRun 'pytest tests/test_performance.py --benchmark-only' for detailed benchmarks")
