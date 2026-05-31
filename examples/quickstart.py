"""
Nestifypy Quickstart Example
"""

from nestifypy.slogger import Logger, Constants
from nestifypy.decorators import benchmark, cache, retry, event, emit
from nestifypy.types import Vector2, Color, Rect
from nestifypy.utils import Strings, Random, Math, Time, Validator
from nestifypy.console import Console
from nestifypy.flow import Flow

# Logger
Logger.info("Nestifypy starting up!")
Logger.warn("Watch out!")
Logger.success("Ready!")

# Decorators
@benchmark
def heavy(n: int) -> int:
    return sum(range(n))

heavy(100_000)

@cache
def fib(n: int) -> int:
    if n <= 1: return n
    return fib(n-1) + fib(n-2)

Logger.info(f"fib(30) = {fib(30)}")

@event("start")
def on_start(level: int) -> None:
    Logger.info(f"Game started at level {level}")

emit("start", level=1)

# Types
v1 = Vector2(0, 0)
v2 = Vector2(100, 100)
Logger.debug(f"Distance: {v1.distance_to(v2):.2f}")
Logger.debug(f"Lerp 50%: {v1.lerp(v2, 0.5)}")

rect = Rect(0, 0, 100, 100)
Logger.debug(f"Contains (50,50): {rect.contains(50, 50)}")

# Utils
Logger.info(Strings.slugify("Hello World! This is Nestifypy."))
Logger.info(f"UUID: {Random.uuid()}")
Logger.info(f"Clamped: {Math.clamp(150, 0, 100)}")
Logger.info(f"Now: {Time.format()}")

# Console
Console.rule()
Console.success("All systems go")
Console.table(
    [
        {"module": "slogger",       "status": "stable",  "phase": 1},
        {"module": "yaml",       "status": "stable",  "phase": 1},
        {"module": "env",        "status": "stable",  "phase": 1},
        {"module": "console",    "status": "stable",  "phase": 1},
        {"module": "flow",       "status": "stable",  "phase": 1},
        {"module": "decorators", "status": "stable",  "phase": 1},
        {"module": "types",      "status": "stable",  "phase": 1},
        {"module": "pyunix",     "status": "planned", "phase": 2},
        {"module": "ai",         "status": "planned", "phase": 5},
    ],
    title="Nestifypy Modules",
)
Console.rule()

# Flow
@Flow.repeat(3)
def tick() -> None:
    Logger.debug("tick")

tick()

@Flow.once
def init() -> None:
    Logger.info("Init (once)")

init()
init()  # no-op

Logger.success("Quickstart complete!")
