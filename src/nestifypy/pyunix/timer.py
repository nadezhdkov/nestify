"""
nestifypy.pyunix.timer
----------------------
Frame-rate-independent timer system ticked by the engine loop.

Usage:
    t = Timer.after(2.0, lambda: print("Boom!"))
    r = Timer.every(1.0, lambda: print("Tick"))
    Timer.cancel(r)
    Timer.clear()
"""
from __future__ import annotations

from typing import Callable, List, Optional


class _TimerEntry:
    __slots__ = ("delay", "callback", "repeat", "elapsed", "active", "tag")

    def __init__(self, delay: float, callback: Callable, repeat: bool, tag: str) -> None:
        self.delay    = delay
        self.callback = callback
        self.repeat   = repeat
        self.elapsed  = 0.0
        self.active   = True
        self.tag      = tag

    def tick(self, dt: float) -> bool:
        if not self.active:
            return False
        self.elapsed += dt
        if self.elapsed >= self.delay:
            self.callback()
            if self.repeat:
                self.elapsed -= self.delay
            else:
                self.active = False
            return True
        return False


class TimerManager:

    def __init__(self) -> None:
        self._timers: List[_TimerEntry] = []
        self._paused: bool = False

    def pause(self) -> None:
        """Freeze all timers — tick() calls are ignored while paused."""
        self._paused = True

    def resume(self) -> None:
        """Resume all timers from where they stopped."""
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    def after(self, seconds: float, callback: Callable, tag: str = "") -> _TimerEntry:
        """Fire `callback` once after `seconds` seconds."""
        entry = _TimerEntry(seconds, callback, repeat=False, tag=tag)
        self._timers.append(entry)
        return entry

    def every(self, seconds: float, callback: Callable, tag: str = "") -> _TimerEntry:
        """Fire `callback` repeatedly every `seconds` seconds."""
        entry = _TimerEntry(seconds, callback, repeat=True, tag=tag)
        self._timers.append(entry)
        return entry

    def cancel(self, entry: _TimerEntry) -> None:
        """Cancel a specific timer."""
        entry.active = False

    def cancel_tag(self, tag: str) -> None:
        """Cancel all timers with the given tag."""
        for t in self._timers:
            if t.tag == tag:
                t.active = False

    def tick(self, dt: float) -> None:
        """Advance all active timers. Called automatically by the engine."""
        if self._paused:
            return
        self._timers = [t for t in self._timers if t.active]
        for timer in list(self._timers):
            timer.tick(dt)

    def clear(self) -> None:
        self._timers.clear()

    @property
    def count(self) -> int:
        return len([t for t in self._timers if t.active])


Timer = TimerManager()
