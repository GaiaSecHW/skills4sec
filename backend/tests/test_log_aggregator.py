"""日志聚合器测试"""
import pytest
import asyncio
from app.core.harness_logging.processors import LogAggregator


class TestLogAggregator:
    """日志聚合器测试"""

    @pytest.fixture
    async def aggregator(self):
        """创建聚合器实例"""
        agg = LogAggregator(window_seconds=1, max_cache=100)
        output_records = []

        async def output_callback(record):
            output_records.append(record)

        await agg.start(output_callback)
        yield agg, output_records
        await agg.stop()

    @pytest.mark.asyncio
    async def test_first_occurrence_returns_record(self, aggregator):
        """测试首次出现返回完整记录"""
        agg, _ = aggregator
        record = {
            "level": "INFO",
            "module": "test",
            "event": "test_event",
            "message": "test message",
        }
        result = await agg.process(record)
        assert result is not None
        assert result["message"] == "test message"

    @pytest.mark.asyncio
    async def test_duplicate_returns_none(self, aggregator):
        """测试重复日志返回 None"""
        agg, _ = aggregator
        record = {
            "level": "INFO",
            "module": "test",
            "event": "test_event",
            "message": "test message",
        }

        await agg.process(record)
        result = await agg.process(record)
        assert result is None

    @pytest.mark.asyncio
    async def test_error_level_not_aggregated(self, aggregator):
        """测试 ERROR 级别不聚合"""
        agg, _ = aggregator
        record = {
            "level": "ERROR",
            "module": "test",
            "event": "error_event",
            "message": "error message",
        }

        result1 = await agg.process(record)
        result2 = await agg.process(record)
        assert result1 is not None
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_fingerprint_different_module(self, aggregator):
        """测试不同 module 生成不同指纹"""
        agg, _ = aggregator

        record1 = {"level": "INFO", "module": "test1", "event": "event", "message": "msg"}
        record2 = {"level": "INFO", "module": "test2", "event": "event", "message": "msg"}

        await agg.process(record1)
        result = await agg.process(record2)

        assert result is not None

    @pytest.mark.asyncio
    async def test_fingerprint_different_event(self, aggregator):
        """测试不同 event 生成不同指纹"""
        agg, _ = aggregator

        record1 = {"level": "INFO", "module": "test", "event": "event1", "message": "msg"}
        record2 = {"level": "INFO", "module": "test", "event": "event2", "message": "msg"}

        await agg.process(record1)
        result = await agg.process(record2)

        assert result is not None

    @pytest.mark.asyncio
    async def test_flush_outputs_aggregated(self, aggregator):
        """测试 flush 输出聚合日志"""
        agg, output_records = aggregator

        record = {"level": "INFO", "module": "test", "event": "event", "message": "msg"}
        for _ in range(5):
            await agg.process(record)

        await asyncio.sleep(1.5)

        assert len(output_records) == 1
        assert output_records[0]["aggregate"]["count"] == 5

    @pytest.mark.asyncio
    async def test_single_occurrence_not_aggregated(self, aggregator):
        """测试只出现一次的日志不输出聚合

        设计说明：
        - 首次出现：process() 立即返回 record（已通过返回值输出）
        - 重复出现：process() 返回 None（不输出，等待 flush）
        - flush：只输出重复日志的聚合结果（count > 1）

        因此单次出现的日志在 flush 后 output_records 为空，
        因为它已经通过 process() 的返回值输出，不需要 flush 输出。
        """
        agg, output_records = aggregator

        record = {"level": "INFO", "module": "test", "event": "event", "message": "msg"}
        result = await agg.process(record)

        # 首次出现，process() 返回原 record
        assert result is not None
        assert result["message"] == "msg"

        await asyncio.sleep(1.5)

        # 单次出现的日志不会在 flush 时输出（因为已经首次输出了）
        # output_records 只包含 count > 1 的聚合结果
        assert len(output_records) == 0
