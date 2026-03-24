# Harness Logging - 日志聚合防刷屏实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现日志聚合功能，同类日志首次完整记录，后续相同日志在时间窗口内计数累积，每分钟输出一次聚合报告

**Architecture:** asyncio 后台任务 + 内存缓存，使用指纹识别重复日志，仅单进程模式启用

**Tech Stack:** Python asyncio, structlog>=23.1.0,<24.0.0

---

## Chunk 1: 日志聚合器实现

### Task 1: 实现 LogAggregator 类

**Files:**
- Modify: `backend/app/core/harness_logging/processors.py`

- [ ] **Step 1: 添加 LogAggregator 类到 processors.py**

```python
# backend/app/core/harness_logging/processors.py - 添加 LogAggregator
import asyncio
import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional, Callable, Awaitable


class LogAggregator:
    """日志聚合器 - 单进程模式

    策略：
    - 首次出现：完整记录日志
    - 重复出现：计数累积，暂不输出
    - 定时输出：每分钟输出一次聚合日志
    """

    def __init__(self, window_seconds: int = 60, max_cache: int = 1000):
        self.window_seconds = window_seconds
        self.max_cache = max_cache
        self._cache: Dict[str, dict] = defaultdict(lambda: {
            "count": 0,
            "first_seen": None,
            "last_seen": None,
            "record": None,
        })
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._output_callback: Optional[Callable[[dict], Awaitable[None]]] = None
        self._running = False

    async def start(self, output_callback: Callable[[dict], Awaitable[None]]) -> None:
        """启动后台聚合任务

        Args:
            output_callback: 异步回调函数，用于输出聚合后的日志
        """
        if self._running:
            return

        self._output_callback = output_callback
        self._running = True
        self._task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """停止聚合任务"""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # 输出剩余的聚合日志
        await self._flush()

    def compute_fingerprint(self, record: dict) -> str:
        """计算日志指纹

        基于 module + level + event + error_code 生成唯一指纹
        """
        key = (
            f"{record.get('module', '')}:"
            f"{record.get('level', '')}:"
            f"{record.get('event', '')}:"
            f"{record.get('error', {}).get('code', '')}"
        )
        return hashlib.md5(key.encode()).hexdigest()[:16]

    async def process(self, record: dict) -> Optional[dict]:
        """处理日志记录

        Args:
            record: 日志记录字典

        Returns:
            None 表示暂不输出（重复日志）
            dict 表示需要输出的日志
        """
        # ERROR 级别不聚合，直接输出
        if record.get("level") == "ERROR":
            return record

        fingerprint = self.compute_fingerprint(record)

        async with self._lock:
            cache_entry = self._cache[fingerprint]
            cache_entry["count"] += 1
            cache_entry["last_seen"] = datetime.utcnow()

            if cache_entry["count"] == 1:
                # 首次出现
                cache_entry["first_seen"] = datetime.utcnow()
                cache_entry["record"] = record.copy()
                return record
            else:
                # 重复出现，暂不输出
                return None

    async def _flush_loop(self) -> None:
        """定时输出聚合日志的后台循环"""
        while self._running:
            await asyncio.sleep(self.window_seconds)
            if self._running:
                await self._flush()

    async def _flush(self) -> None:
        """输出所有聚合日志"""
        if not self._output_callback:
            return

        async with self._lock:
            for fingerprint, entry in list(self._cache.items()):
                if entry["count"] > 1:
                    # 构建聚合日志
                    aggregated = {
                        **entry["record"],
                        "aggregate": {
                            "count": entry["count"],
                            "first_seen": entry["first_seen"].isoformat() + "Z",
                            "last_seen": entry["last_seen"].isoformat() + "Z",
                            "duration_seconds": self.window_seconds,
                        }
                    }
                    await self._output_callback(aggregated)

            # 清空缓存
            self._cache.clear()
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging.processors import LogAggregator; print('OK')"`
Expected: OK

- [ ] **Step 3: 提交**

```bash
git add backend/app/core/harness_logging/processors.py
git commit -m "feat: add LogAggregator class"
```

---

## Chunk 2: 聚合器测试

### Task 2: 编写聚合器测试

**Files:**
- Create: `backend/tests/test_log_aggregator.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_log_aggregator.py
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

        # 第一次
        await agg.process(record)
        # 第二次
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

        # 多次 ERROR 应该都返回
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

        # 不同 module 应该都返回
        assert result is not None

    @pytest.mark.asyncio
    async def test_fingerprint_different_event(self, aggregator):
        """测试不同 event 生成不同指纹"""
        agg, _ = aggregator

        record1 = {"level": "INFO", "module": "test", "event": "event1", "message": "msg"}
        record2 = {"level": "INFO", "module": "test", "event": "event2", "message": "msg"}

        await agg.process(record1)
        result = await agg.process(record2)

        # 不同 event 应该都返回
        assert result is not None

    @pytest.mark.asyncio
    async def test_flush_outputs_aggregated(self, aggregator):
        """测试 flush 输出聚合日志"""
        agg, output_records = aggregator

        # 发送多次相同日志
        record = {"level": "INFO", "module": "test", "event": "event", "message": "msg"}
        for _ in range(5):
            await agg.process(record)

        # 等待 flush
        await asyncio.sleep(1.5)

        # 检查聚合输出
        assert len(output_records) == 1
        assert output_records[0]["aggregate"]["count"] == 5

    @pytest.mark.asyncio
    async def test_single_occurrence_not_aggregated(self, aggregator):
        """测试只出现一次的日志不输出聚合"""
        agg, output_records = aggregator

        record = {"level": "INFO", "module": "test", "event": "event", "message": "msg"}
        await agg.process(record)

        # 等待 flush
        await asyncio.sleep(1.5)

        # 单次出现不应有 aggregate 字段
        assert len(output_records) == 1
        assert "aggregate" not in output_records[0]
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && py -m pytest tests/test_log_aggregator.py -v`
Expected: All tests passed

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_log_aggregator.py
git commit -m "test: add LogAggregator tests"
```

---

## Chunk 3: 与 HarnessLogger 集成

### Task 3: 集成聚合器到 HarnessLogger

**Files:**
- Modify: `backend/app/core/harness_logging/logger.py`
- Modify: `backend/app/core/harness_logging/config.py`

- [ ] **Step 1: 更新 config.py 添加聚合配置**

```python
# backend/app/core/harness_logging/config.py - 添加聚合配置
class AggregatorConfig:
    """聚合器配置"""
    ENABLED = True
    WINDOW_SECONDS = 60
    MAX_CACHE = 1000
```

- [ ] **Step 2: 修改 HarnessLogger 添加聚合功能**

```python
# backend/app/core/harness_logging/logger.py - 添加聚合器支持
from app.core.harness_logging.processors import LogAggregator

# 全局聚合器实例
_aggregator: Optional[LogAggregator] = None


async def setup_aggregator(config) -> LogAggregator:
    """设置全局聚合器"""
    global _aggregator
    if _aggregator is None and config.AGGREGATION_ENABLED:
        _aggregator = LogAggregator(
            window_seconds=config.AGGREGATION["window_seconds"],
            max_cache=config.AGGREGATION["max_cache"],
        )
        await _aggregator.start(_aggregator_output)
    return _aggregator


async def _aggregator_output(record: dict) -> None:
    """聚合器输出回调"""
    global _loggers
    module = record.get("name", "aggregator")
    if module in _loggers:
        _loggers[module].log(record.get("level", "INFO"), record)


async def stop_aggregator() -> None:
    """停止全局聚合器"""
    global _aggregator
    if _aggregator:
        await _aggregator.stop()
        _aggregator = None


class HarnessLogger:
    # ... 现有代码 ...

    async def _aggregate(self, record: dict) -> Optional[dict]:
        """处理日志聚合"""
        if _aggregator is None:
            return record
        return await _aggregator.process(record)

    def _log(self, level: str, message: str, **kwargs) -> None:
        """内部日志方法"""
        try:
            record = self._build_record(message, level, **kwargs)
            record = mask_sensitive_data(record)

            # 如果有异步聚合器，使用它
            if _aggregator is not None:
                # 创建异步任务（不等待）
                asyncio.create_task(self._aggregate_and_output(record, level))
            else:
                self._logger.log(level, record)
        except Exception as e:
            sys.stderr.write(f"[LOG_ERROR] {e}\n")

    async def _aggregate_and_output(self, record: dict, level: str) -> None:
        """聚合并输出日志"""
        result = await self._aggregate(record)
        if result is not None:
            self._logger.log(level, result)
```

- [ ] **Step 3: 更新 setup_harness_logging**

```python
# backend/app/core/harness_logging/__init__.py - 更新 setup_harness_logging
async def setup_harness_logging(...) -> None:
    """初始化 Harness 日志系统"""
    # ... 现有代码 ...

    # 启动聚合器
    if enable_aggregation:
        await setup_aggregator(LogConfig)
```

- [ ] **Step 4: 验证语法**

Run: `cd backend && py -c "from app.core.harness_logging import setup_harness_logging; print('OK')"`
Expected: OK

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/harness_logging/logger.py
git add backend/app/core/harness_logging/config.py
git add backend/app/core/harness_logging/__init__.py
git commit -m "feat: integrate LogAggregator into HarnessLogger"
```

---

## Chunk 4: 多 Worker 部署说明

### Task 4: 添加配置项说明

**Files:**
- Modify: `backend/app/core/harness_logging/config.py`

- [ ] **Step 1: 添加配置说明注释**

```python
# backend/app/core/harness_logging/config.py - 添加注释
class AggregatorConfig:
    """
    聚合器配置

    注意：
    - 单 Worker 模式：启用内存聚合
    - 多 Worker 模式：禁用聚合（每个 Worker 有独立缓存）
    - 生产环境多 Worker 时设置 AGGREGATION_ENABLED = False
    """
    ENABLED = True
    WINDOW_SECONDS = 60
    MAX_CACHE = 1000
```

- [ ] **Step 2: 提交**

```bash
git add backend/app/core/harness_logging/config.py
git commit -m "docs: add multi-worker deployment notes for aggregator"
```

---

## 依赖关系

此计划依赖：
- Plan 01: 核心基础设施（processors.py 需要先创建）

此计划完成后，可解锁：
- Plan 07: 代码迁移
