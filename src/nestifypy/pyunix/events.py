"""
nestifypy.pyunix.events
-----------------------
Type-safe Pub/Sub event bus for decoupled game-wide communication.

Usage:
    @Event.on("player_death")
    def handle_death(data): ...

    Event.emit("player_death", {"score": 100})
    Event.emit_deferred("level_complete")   # fires next frame
    Event.flush()                           # process deferred events
"""
from __future__ import annotations

from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from collections import deque


class EventBus:

    def __init__(self) -> None:
        self._listeners: Dict[str, List[Callable]] = {}
        self._deferred:  Deque[Tuple[str, Any]]    = deque()

    def on(self, event_name: str) -> Callable:
        """
        Decorator: register a listener for `event_name`.

        Works with both plain functions and bound methods:

            # Plain function (decorator style)
            @Event.on("player_death")
            def handle(data): ...

            # Bound method (imperative style — use in __init__)
            Event.on("player_death")(self._on_death)
        """
        def decorator(func: Callable) -> Callable:
            self._listeners.setdefault(event_name, []).append(func)
            return func
        return decorator

    def off(self, event_name: str, func: Callable) -> None:
        """Unregister a specific listener."""
        if event_name in self._listeners:
            self._listeners[event_name] = [
                f for f in self._listeners[event_name] if f is not func
            ]

    def once(self, event_name: str) -> Callable:
        """Decorator: register a listener that fires only once."""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args: Any, **kwargs: Any) -> None:
                func(*args, **kwargs)
                self.off(event_name, wrapper)
            self._listeners.setdefault(event_name, []).append(wrapper)
            return func
        return decorator

    def emit(self, event_name: str, data: Any = None) -> None:
        """Immediately fire all listeners for `event_name`."""
        for cb in list(self._listeners.get(event_name, [])):
            if data is not None:
                cb(data)
            else:
                cb()

    def emit_deferred(self, event_name: str, data: Any = None) -> None:
        """Queue an event to be fired on the next `flush()` call."""
        self._deferred.append((event_name, data))

    def flush(self) -> None:
        """Process all deferred events (called automatically each frame by the engine)."""
        while self._deferred:
            name, data = self._deferred.popleft()
            self.emit(name, data)

    def clear(self, event_name: Optional[str] = None) -> None:
        if event_name:
            self._listeners.pop(event_name, None)
        else:
            self._listeners.clear()

    def listeners(self, event_name: str) -> List[Callable]:
        return list(self._listeners.get(event_name, []))

    def has_listeners(self, event_name: str) -> bool:
        return bool(self._listeners.get(event_name))


Event = EventBus()