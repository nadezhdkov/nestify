"""
tests/test_nestifypy.py
--------------------
Basic test suite for Nestifypy slogger modules.
Run with: pytest
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─────────────────────────────────────────────
#  slogger
# ─────────────────────────────────────────────

class TestLogger:
    def test_log_levels_do_not_crash(self) -> None:
        from nestifypy.slogger import Logger
        Logger.info("test")
        Logger.warn("test")
        Logger.error("test")
        Logger.debug("test")
        Logger.success("test")


class TestRegistry:
    def test_register_and_get(self) -> None:
        from nestifypy.slogger import Registry
        Registry.register("test_cat", "my_item", 42)
        assert Registry.get("test_cat", "my_item") == 42

    def test_duplicate_raises(self) -> None:
        from nestifypy.slogger import Registry, RegistryError
        Registry.clear("dup_test")
        Registry.register("dup_test", "x", 1)
        with pytest.raises(RegistryError):
            Registry.register("dup_test", "x", 2)

    def test_missing_raises(self) -> None:
        from nestifypy.slogger import Registry, RegistryError
        with pytest.raises(RegistryError):
            Registry.get("nonexistent", "key")


class TestPlugin:
    def test_register_decorator(self) -> None:
        from nestifypy.slogger import Plugin

        @Plugin.register
        class MyPlugin:
            pass

        assert "MyPlugin" in Plugin.all()

    def test_info_decorator(self) -> None:
        from nestifypy.slogger import Plugin

        @Plugin.info(name="TestPlugin", version="2.0")
        @Plugin.register
        class AnotherPlugin:
            pass

        assert AnotherPlugin._plugin_meta.version == "2.0"


# ─────────────────────────────────────────────
#  decorators
# ─────────────────────────────────────────────

class TestDecorators:
    def test_debug_preserves_name(self) -> None:
        from nestifypy.decorators import debug

        @debug
        def my_func():
            return 42

        assert my_func.__name__ == "my_func"

    def test_benchmark_returns_value(self) -> None:
        from nestifypy.decorators import benchmark

        @benchmark
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_retry_succeeds_eventually(self) -> None:
        from nestifypy.decorators import retry

        calls = {"n": 0}

        @retry(times=3)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("Not yet")
            return "ok"

        assert flaky() == "ok"
        assert calls["n"] == 3

    def test_retry_raises_on_exhaustion(self) -> None:
        from nestifypy.decorators import retry

        @retry(times=2)
        def always_fails():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            always_fails()

    def test_cache_memoizes(self) -> None:
        from nestifypy.decorators import cache

        calls = {"n": 0}

        @cache
        def compute(x):
            calls["n"] += 1
            return x * 2

        assert compute(5) == 10
        assert compute(5) == 10
        assert calls["n"] == 1

    def test_singleton(self) -> None:
        from nestifypy.decorators import singleton

        @singleton
        class MyClass:
            pass

        a = MyClass()
        b = MyClass()
        assert a is b

    def test_event_and_emit(self) -> None:
        from nestifypy.decorators import event, emit, _EVENTS

        received = []

        @event("test_event")
        def handler(val):
            received.append(val)

        emit("test_event", 99)
        assert 99 in received

    def test_validate_min(self) -> None:
        from nestifypy.decorators import validate

        @validate(min_value=0)
        def set_hp(value):
            return value

        with pytest.raises(ValueError):
            set_hp(-1)

        assert set_hp(50) == 50

    def test_not_null(self) -> None:
        from nestifypy.decorators import not_null

        @not_null
        def process(x):
            return x

        with pytest.raises(ValueError):
            process(None)

    def test_safe_catches_error(self) -> None:
        from nestifypy.decorators import safe

        @safe
        def boom():
            raise RuntimeError("crash")

        result = boom()
        assert result is None

    def test_startup_shutdown(self) -> None:
        from nestifypy.decorators import startup, shutdown, run_startup, run_shutdown

        log = []

        @startup
        def on_start():
            log.append("start")

        @shutdown
        def on_stop():
            log.append("stop")

        run_startup()
        run_shutdown()
        assert "start" in log
        assert "stop" in log


# ─────────────────────────────────────────────
#  types
# ─────────────────────────────────────────────

class TestVector2:
    def test_add(self) -> None:
        from nestifypy.types import Vector2
        v = Vector2(1, 2) + Vector2(3, 4)
        assert v.x == 4 and v.y == 6

    def test_distance(self) -> None:
        from nestifypy.types import Vector2
        v1 = Vector2(0, 0)
        v2 = Vector2(3, 4)
        assert abs(v1.distance_to(v2) - 5.0) < 1e-9

    def test_lerp(self) -> None:
        from nestifypy.types import Vector2
        v1 = Vector2(0, 0)
        v2 = Vector2(10, 10)
        mid = v1.lerp(v2, 0.5)
        assert mid.x == 5.0

    def test_normalized(self) -> None:
        from nestifypy.types import Vector2
        import math
        v = Vector2(3, 4).normalized()
        assert abs(v.length() - 1.0) < 1e-9

    def test_zero(self) -> None:
        from nestifypy.types import Vector2
        v = Vector2.zero()
        assert v.x == 0 and v.y == 0


class TestColor:
    def test_from_hex(self) -> None:
        from nestifypy.types import Color
        c = Color.from_hex("#ff0000")
        assert c.r == 255 and c.g == 0 and c.b == 0

    def test_lerp(self) -> None:
        from nestifypy.types import Color
        red = Color(255, 0, 0)
        blue = Color(0, 0, 255)
        mid = red.lerp(blue, 0.5)
        assert mid.r == 127 or mid.r == 128

    def test_presets(self) -> None:
        from nestifypy.types import Color
        assert Color.RED.r == 255
        assert Color.BLUE.b == 255


class TestRect:
    def test_contains(self) -> None:
        from nestifypy.types import Rect
        r = Rect(0, 0, 100, 100)
        assert r.contains(50, 50)
        assert not r.contains(150, 50)

    def test_intersects(self) -> None:
        from nestifypy.types import Rect
        a = Rect(0, 0, 50, 50)
        b = Rect(25, 25, 50, 50)
        c = Rect(100, 100, 50, 50)
        assert a.intersects(b)
        assert not a.intersects(c)


# ─────────────────────────────────────────────
#  utils
# ─────────────────────────────────────────────

class TestUtils:
    def test_slugify(self) -> None:
        from nestifypy.utils import Strings
        assert Strings.slugify("Hello World!") == "hello-world"

    def test_clamp(self) -> None:
        from nestifypy.utils import Math
        assert Math.clamp(150, 0, 100) == 100
        assert Math.clamp(-10, 0, 100) == 0
        assert Math.clamp(50, 0, 100) == 50

    def test_lerp(self) -> None:
        from nestifypy.utils import Math
        assert Math.lerp(0, 10, 0.5) == 5.0

    def test_uuid(self) -> None:
        from nestifypy.utils import Random
        u1 = Random.uuid()
        u2 = Random.uuid()
        assert u1 != u2
        assert len(u1) == 36

    def test_email_validator(self) -> None:
        from nestifypy.utils import Validator
        assert Validator.email("test@example.com")
        assert not Validator.email("not-an-email")

    def test_snake_camel(self) -> None:
        from nestifypy.utils import Strings
        assert Strings.snake_to_camel("hello_world") == "helloWorld"
        assert Strings.camel_to_snake("helloWorld") == "hello_world"


# ─────────────────────────────────────────────
#  flow
# ─────────────────────────────────────────────

class TestFlow:
    def test_repeat(self) -> None:
        from nestifypy.flow import Flow

        calls = []

        @Flow.repeat(5)
        def tick():
            calls.append(1)
            return 1

        tick()
        assert len(calls) == 5

    def test_once(self) -> None:
        from nestifypy.flow import Flow

        calls = []

        @Flow.once
        def init():
            calls.append(1)

        init()
        init()
        init()
        assert len(calls) == 1

    def test_throttle(self) -> None:
        from nestifypy.flow import Flow
        import time

        calls = []

        @Flow.throttle(wait=0.5)
        def on_input():
            calls.append(1)

        on_input()
        on_input()  # throttled
        assert len(calls) == 1

    def test_after(self) -> None:
        from nestifypy.flow import Flow

        results = []

        @Flow.after(calls=3)
        def on_third():
            results.append("hit")

        on_third()
        on_third()
        on_third()  # fires here
        assert results == ["hit"]

    def test_parallel(self) -> None:
        from nestifypy.flow import Flow

        results = Flow.parallel(
            lambda: 1 + 1,
            lambda: 2 + 2,
            lambda: 3 + 3,
        )
        assert sorted(results) == [2, 4, 6]
