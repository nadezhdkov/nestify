"""
nestifypy.pyunix.particles
--------------------------
High-performance particle system with a fluent builder API.

Supports position/velocity variance, color gradients, alpha fade,
size change over lifetime, gravity, burst and continuous emission.

Usage:
    # One-shot burst (explosion)
    fx = ParticleSystem(x=200, y=300)
    fx.configure(
        count=80,
        lifetime=(0.4, 1.2),
        speed=(60, 200),
        angle=(-180, 180),
        start_color=Color.from_hex("#FF6600"),
        end_color=Color(80, 0, 0, 0),
        start_size=6,
        end_size=0,
        gravity=Vector2(0, 120),
    )
    fx.burst()

    # Continuous emitter (fire, smoke)
    smoke = ParticleSystem(x=100, y=400)
    smoke.configure(
        emit_rate=30,
        lifetime=(1.0, 2.0),
        speed=(10, 40),
        angle=(-100, -80),   # upward with variance
        start_color=Color(180, 180, 180, 200),
        end_color=Color(80, 80, 80, 0),
        start_size=4,
        end_size=12,
    )
    smoke.start()

    # In update:
    fx.update(dt)
    smoke.update(dt)

    # In draw:
    fx.draw(screen, Camera.offset)
    smoke.draw(screen, Camera.offset)
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from nestifypy.pyunix.math import Color, Vector2

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False


@dataclass
class _Particle:
    __slots__ = (
        "x", "y", "vx", "vy",
        "lifetime", "age",
        "start_color", "end_color",
        "start_size", "end_size",
        "active",
    )
    x: float
    y: float
    vx: float
    vy: float
    lifetime: float
    age: float
    start_color: Color
    end_color: Color
    start_size: float
    end_size: float
    active: bool


class ParticleSystem:
    """
    Manages a pool of particles with birth/death/update/draw logic.

    Uses a fixed-size object pool — particles are *reactivated* rather than
    allocated/destroyed each frame, which keeps GC pressure near zero even
    at high emission rates.

    Configure once with .configure(), then call .burst() or .start()/.stop()
    for continuous emission.
    """

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x = x
        self.y = y

        # ── Config ─────────────────────────
        self._count:       int               = 50
        self._emit_rate:   float             = 0.0        # particles/sec (0 = burst only)
        self._lifetime:    Tuple[float, float] = (0.5, 1.5)
        self._speed:       Tuple[float, float] = (50.0, 150.0)
        self._angle:       Tuple[float, float] = (-180.0, 180.0)
        self._start_color: Color             = Color.WHITE
        self._end_color:   Color             = Color(255, 255, 255, 0)
        self._start_size:  float             = 4.0
        self._end_size:    float             = 0.0
        self._gravity:     Vector2           = Vector2.zero()
        self._spread:      Tuple[float, float] = (0.0, 0.0)

        # ── Object pool (allocated once, reused forever) ───────────
        self._pool:       List[_Particle] = []
        self._pool_built: bool = False        # pool is rebuilt when count changes
        self._active:     bool = False
        self._emit_accum: float = 0.0

    # ── Pool management ──────────────────────

    def _ensure_pool(self) -> None:
        """Build or resize the fixed pool when count changes."""
        if self._pool_built and len(self._pool) == self._count:
            return
        # Reuse existing slots, add new ones, trim extras
        for p in self._pool:
            p.active = False
        while len(self._pool) < self._count:
            self._pool.append(_Particle(
                x=0, y=0, vx=0, vy=0,
                lifetime=1, age=0,
                start_color=Color.WHITE, end_color=Color.WHITE,
                start_size=4, end_size=0, active=False,
            ))
        del self._pool[self._count:]
        self._pool_built = True

    def _next_inactive(self) -> Optional[_Particle]:
        """Return the first inactive slot in the pool, or None if full."""
        for p in self._pool:
            if not p.active:
                return p
        return None

    # ── Fluent Configuration ─────────────────

    def configure(
        self,
        count: int = 50,
        emit_rate: float = 0.0,
        lifetime: Tuple[float, float] = (0.5, 1.5),
        speed: Tuple[float, float] = (50.0, 150.0),
        angle: Tuple[float, float] = (-180.0, 180.0),
        start_color: Color = None,
        end_color: Color = None,
        start_size: float = 4.0,
        end_size: float = 0.0,
        gravity: Vector2 = None,
        spread: Tuple[float, float] = (0.0, 0.0),
    ) -> "ParticleSystem":
        if count != self._count:
            self._pool_built = False   # pool needs rebuild
        self._count       = count
        self._emit_rate   = emit_rate
        self._lifetime    = lifetime
        self._speed       = speed
        self._angle       = angle
        self._start_color = start_color or Color.WHITE
        self._end_color   = end_color   or Color(255, 255, 255, 0)
        self._start_size  = start_size
        self._end_size    = end_size
        self._gravity     = gravity or Vector2.zero()
        self._spread      = spread
        return self

    # ── Emission ─────────────────────────────

    def burst(self, count: Optional[int] = None) -> None:
        """Immediately spawn `count` particles (defaults to configured count)."""
        self._ensure_pool()
        n = count if count is not None else self._count
        spawned = 0
        for p in self._pool:
            if spawned >= n:
                break
            if not p.active:
                self._activate(p)
                spawned += 1

    def start(self) -> None:
        """Begin continuous emission (emit_rate particles per second)."""
        self._ensure_pool()
        self._active = True

    def stop(self) -> None:
        """Stop continuous emission (existing particles finish naturally)."""
        self._active = False

    def clear(self) -> None:
        """Deactivate all particles immediately without freeing the pool."""
        for p in self._pool:
            p.active = False
        self._emit_accum = 0.0

    @property
    def alive_count(self) -> int:
        return sum(1 for p in self._pool if p.active)

    @property
    def is_finished(self) -> bool:
        """True when emission is stopped and no particles remain alive."""
        return not self._active and self.alive_count == 0

    # ── Lifecycle ────────────────────────────

    def update(self, dt: float) -> None:
        """Advance all particles by `dt` seconds. Call every frame."""
        self._ensure_pool()
        gx, gy = self._gravity.x, self._gravity.y

        for p in self._pool:
            if not p.active:
                continue
            p.age += dt
            if p.age >= p.lifetime:
                p.active = False   # return slot to pool — no allocation
                continue
            p.vx += gx * dt
            p.vy += gy * dt
            p.x  += p.vx * dt
            p.y  += p.vy * dt

        # Continuous emission — reuse inactive pool slots
        if self._active and self._emit_rate > 0:
            self._emit_accum += self._emit_rate * dt
            while self._emit_accum >= 1.0:
                slot = self._next_inactive()
                if slot is not None:
                    self._activate(slot)
                self._emit_accum -= 1.0

    def draw(self, surface: Any, offset: Tuple[float, float] = (0.0, 0.0)) -> None:
        """Render all particles as filled circles on `surface`."""
        if not _HAS_PYGAME:
            return

        ox, oy = offset
        for p in self._pool:
            if not p.active:
                continue
            t = p.age / max(p.lifetime, 0.0001)
            color = p.start_color.lerp(p.end_color, t)
            size  = max(1, int(p.start_size + (p.end_size - p.start_size) * t))
            cx = int(p.x - ox)
            cy = int(p.y - oy)

            # Use alpha surface for semi-transparent circles
            if color.a < 255:
                circle_surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(circle_surf, color.to_rgba(), (size, size), size)
                surface.blit(circle_surf, (cx - size, cy - size))
            else:
                pygame.draw.circle(surface, color.to_rgb(), (cx, cy), size)

    # ── Internal ─────────────────────────────

    def _activate(self, p: _Particle) -> None:
        """Reset an existing pool slot and mark it active — no allocation."""
        ang = math.radians(random.uniform(*self._angle))
        spd = random.uniform(*self._speed)
        p.x  = self.x + random.uniform(-self._spread[0], self._spread[0])
        p.y  = self.y + random.uniform(-self._spread[1], self._spread[1])
        p.vx = math.cos(ang) * spd
        p.vy = math.sin(ang) * spd
        p.lifetime   = random.uniform(*self._lifetime)
        p.age        = 0.0
        p.start_color = self._start_color
        p.end_color   = self._end_color
        p.start_size  = self._start_size
        p.end_size    = self._end_size
        p.active     = True

    def _spawn(self) -> None:
        """Legacy helper kept for any subclasses — delegates to _activate."""
        slot = self._next_inactive()
        if slot is not None:
            self._activate(slot)
