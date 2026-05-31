"""
nestifypy.pyunix.physics
------------------------
2D rigidbody physics: DYNAMIC / KINEMATIC / STATIC bodies,
AABB + Circle collision detection, restitution, friction, layer masks,
trigger zones, and sensor queries.

Improvements over v1:
- Circle vs Circle and Circle vs Box collision detection
- Friction applied during velocity resolution
- Proper mass-weighted impulse distribution
- overlap_circle() sensor query
- raycast() line-of-sight query
- Configurable gravity per-body via gravity_scale
- Sleeping bodies (skip integration when velocity ≈ 0)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from nestifypy.pyunix.math import Vector2

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class BodyType(Enum):
    STATIC    = 0   # Never moves; infinite effective mass
    KINEMATIC = 1   # Moved manually; ignores forces but collides
    DYNAMIC   = 2   # Full physics simulation


@dataclass(slots=True)
class PhysicsMaterial:
    """Surface properties shared by a collider."""
    friction:    float = 0.3
    bounciness:  float = 0.0


@dataclass(slots=True)
class CollisionInfo:
    """Payload delivered to on_collision_* hooks."""
    other:      Any        # The other Entity involved
    normal:     Vector2    # Collision normal (points away from `other`)
    depth:      float      # Penetration depth in pixels
    is_trigger: bool = False


# ---------------------------------------------------------------------------
# Colliders
# ---------------------------------------------------------------------------

class Collider:
    """Abstract base for collision shapes."""
    __slots__ = ("offset", "is_trigger", "material")

    def __init__(
        self,
        offset: Vector2 = None,
        is_trigger: bool = False,
        material: PhysicsMaterial = None,
    ) -> None:
        self.offset:     Vector2         = offset   or Vector2.zero()
        self.is_trigger: bool            = is_trigger
        self.material:   PhysicsMaterial = material or PhysicsMaterial()


class BoxCollider(Collider):
    """Axis-Aligned Bounding Box (AABB) collider."""
    __slots__ = ("width", "height")

    def __init__(
        self,
        width: float,
        height: float,
        offset: Vector2 = None,
        is_trigger: bool = False,
        material: PhysicsMaterial = None,
    ) -> None:
        super().__init__(offset, is_trigger, material)
        self.width  = width
        self.height = height

    def get_bounds(self, pos: Vector2) -> Tuple[float, float, float, float]:
        """Return (left, top, right, bottom) in world space."""
        cx = pos.x + self.offset.x
        cy = pos.y + self.offset.y
        hw = self.width  / 2
        hh = self.height / 2
        return (cx - hw, cy - hh, cx + hw, cy + hh)

    def center(self, pos: Vector2) -> Vector2:
        return Vector2(pos.x + self.offset.x, pos.y + self.offset.y)


class CircleCollider(Collider):
    """Circle collider."""
    __slots__ = ("radius",)

    def __init__(
        self,
        radius: float,
        offset: Vector2 = None,
        is_trigger: bool = False,
        material: PhysicsMaterial = None,
    ) -> None:
        super().__init__(offset, is_trigger, material)
        self.radius = radius

    def center(self, pos: Vector2) -> Vector2:
        return Vector2(pos.x + self.offset.x, pos.y + self.offset.y)


# ---------------------------------------------------------------------------
# Rigidbody
# ---------------------------------------------------------------------------

class Rigidbody:
    """Physical body component attached to an Entity."""
    __slots__ = (
        "entity", "body_type", "velocity", "acceleration",
        "mass", "drag", "angular_drag", "gravity_scale",
        "layer", "mask", "freeze_x", "freeze_y",
        "_sleeping", "_sleep_timer",
    )

    _SLEEP_THRESHOLD  = 1.0    # px/s below which a body may sleep
    _SLEEP_TIME_LIMIT = 0.5    # seconds at threshold before sleeping

    def __init__(
        self,
        body_type:     BodyType       = BodyType.DYNAMIC,
        mass:          float          = 1.0,
        drag:          float          = 0.0,
        angular_drag:  float          = 0.0,
        gravity_scale: float          = 1.0,
        layer:         str            = "default",
        mask:          Set[str]       = None,
        freeze_x:      bool           = False,
        freeze_y:      bool           = False,
    ) -> None:
        self.entity        = None
        self.body_type     = body_type
        self.velocity      = Vector2.zero()
        self.acceleration  = Vector2.zero()
        self.mass          = max(mass, 0.0001)
        self.drag          = drag
        self.angular_drag  = angular_drag
        self.gravity_scale = gravity_scale
        self.layer         = layer
        self.mask          = mask if mask is not None else {"default"}
        self.freeze_x      = freeze_x
        self.freeze_y      = freeze_y
        self._sleeping     = False
        self._sleep_timer  = 0.0

    # ── Force API ────────────────────────────

    def add_force(self, force: Vector2) -> None:
        """Apply a force (mass-scaled velocity impulse)."""
        if self.body_type != BodyType.DYNAMIC:
            return
        self._wake()
        self.velocity.x += force.x / self.mass
        self.velocity.y += force.y / self.mass

    def add_impulse(self, impulse: Vector2) -> None:
        """Apply a direct velocity change (ignores mass)."""
        if self.body_type != BodyType.DYNAMIC:
            return
        self._wake()
        self.velocity.x += impulse.x
        self.velocity.y += impulse.y

    def set_velocity(self, vx: float, vy: float) -> None:
        self._wake()
        self.velocity.x = vx
        self.velocity.y = vy

    def stop(self) -> None:
        self.velocity.x = 0.0
        self.velocity.y = 0.0

    # ── Sleep ────────────────────────────────

    def _wake(self) -> None:
        self._sleeping    = False
        self._sleep_timer = 0.0

    def _check_sleep(self, dt: float) -> None:
        if self.body_type != BodyType.DYNAMIC:
            return
        spd = self.velocity.magnitude
        if spd < self._SLEEP_THRESHOLD:
            self._sleep_timer += dt
            if self._sleep_timer >= self._SLEEP_TIME_LIMIT:
                self._sleeping = True
        else:
            self._wake()


# ---------------------------------------------------------------------------
# Collision detection helpers
# ---------------------------------------------------------------------------

def _box_vs_box(
    c1: BoxCollider, p1: Vector2,
    c2: BoxCollider, p2: Vector2,
) -> Optional[Tuple[Vector2, float]]:
    """Return (normal, depth) if overlapping, else None."""
    b1 = c1.get_bounds(p1)
    b2 = c2.get_bounds(p2)
    if not (b1[0] < b2[2] and b1[2] > b2[0] and b1[1] < b2[3] and b1[3] > b2[1]):
        return None
    ox = min(b1[2], b2[2]) - max(b1[0], b2[0])
    oy = min(b1[3], b2[3]) - max(b1[1], b2[1])
    if ox < oy:
        normal = Vector2(-1, 0) if p1.x < p2.x else Vector2(1, 0)
        return (normal, ox)
    else:
        normal = Vector2(0, -1) if p1.y < p2.y else Vector2(0, 1)
        return (normal, oy)


def _circle_vs_circle(
    c1: CircleCollider, p1: Vector2,
    c2: CircleCollider, p2: Vector2,
) -> Optional[Tuple[Vector2, float]]:
    center1 = c1.center(p1)
    center2 = c2.center(p2)
    diff    = center1 - center2
    dist    = diff.magnitude
    radii   = c1.radius + c2.radius
    if dist >= radii or dist == 0:
        return None
    normal = diff.normalized
    depth  = radii - dist
    return (normal, depth)


def _circle_vs_box(
    cc: CircleCollider, cp: Vector2,
    bc: BoxCollider,   bp: Vector2,
) -> Optional[Tuple[Vector2, float]]:
    """Circle (first) vs Box (second). Returns (normal pointing away from box, depth)."""
    center  = cc.center(cp)
    b       = bc.get_bounds(bp)
    # Clamp circle center to box bounds
    closest_x = max(b[0], min(center.x, b[2]))
    closest_y = max(b[1], min(center.y, b[3]))
    diff  = center - Vector2(closest_x, closest_y)
    dist  = diff.magnitude
    if dist >= cc.radius:
        return None
    if dist == 0:
        # Center inside box — push out the shortest axis
        box_cx = (b[0] + b[2]) / 2
        box_cy = (b[1] + b[3]) / 2
        diff   = center - Vector2(box_cx, box_cy)
        dist   = diff.magnitude or 0.001
    normal = diff.normalized
    depth  = cc.radius - dist
    return (normal, depth)


# ---------------------------------------------------------------------------
# PhysicsWorld
# ---------------------------------------------------------------------------

class PhysicsWorldSystem:
    """Global 2D physics simulation manager."""

    def __init__(self) -> None:
        self.gravity:     Vector2 = Vector2(0, 980.0)
        self.fixed_dt:    float   = 1.0 / 60.0
        self.debug_draw:  bool    = False
        self._bodies:     List[Any]                      = []
        self._active_collisions: Set[Tuple[int, int]]    = set()
        # Spatial hash cell size — tune to roughly 2× the largest collider
        self._cell_size: float = 64.0

    # ── Registration ─────────────────────────

    def set_gravity(self, x: float, y: float) -> None:
        self.gravity = Vector2(x, y)

    def set_cell_size(self, size: float) -> None:
        """
        Set the spatial hash cell size in pixels.

        A good value is roughly 2× the average collider dimension.
        Smaller cells = fewer false-positive pairs but more memory.
        Larger cells = more pairs tested but cheaper to build.
        Default is 64.
        """
        self._cell_size = max(1.0, size)

    def register(self, entity: Any) -> None:
        if entity not in self._bodies:
            self._bodies.append(entity)

    def unregister(self, entity: Any) -> None:
        if entity in self._bodies:
            self._bodies.remove(entity)
        eid = id(entity)
        self._active_collisions = {
            p for p in self._active_collisions
            if p[0] != eid and p[1] != eid
        }

    # ── Spatial Hash ─────────────────────────

    def _cell(self, x: float, y: float) -> Tuple[int, int]:
        cs = self._cell_size
        return (int(x // cs), int(y // cs))

    def _cells_for_entity(self, entity: Any) -> List[Tuple[int, int]]:
        """Return all grid cells overlapped by the entity's collider AABB."""
        col = getattr(entity, "collider", None)
        if col is None:
            return []
        pos = Vector2(entity.x, entity.y)
        if isinstance(col, BoxCollider):
            l, t, r, b = col.get_bounds(pos)
        elif isinstance(col, CircleCollider):
            c = col.center(pos)
            r_val = col.radius
            l, t, r, b = c.x - r_val, c.y - r_val, c.x + r_val, c.y + r_val
        else:
            return [self._cell(entity.x, entity.y)]

        cs = self._cell_size
        cells = []
        cx = int(l // cs)
        while cx * cs <= r:
            cy = int(t // cs)
            while cy * cs <= b:
                cells.append((cx, cy))
                cy += 1
            cx += 1
        return cells or [self._cell(entity.x, entity.y)]

    def _broad_phase(self) -> List[Tuple[Any, Any]]:
        """
        Build candidate collision pairs using spatial hashing.

        Returns a deduplicated list of (e1, e2) pairs that share at least
        one grid cell — a necessary (but not sufficient) condition for overlap.
        """
        grid: dict = {}
        for entity in self._bodies:
            if getattr(entity, "collider", None) is None:
                continue
            for cell in self._cells_for_entity(entity):
                grid.setdefault(cell, []).append(entity)

        seen: Set[Tuple[int, int]] = set()
        pairs = []
        for occupants in grid.values():
            n = len(occupants)
            for i in range(n):
                for j in range(i + 1, n):
                    key = tuple(sorted((id(occupants[i]), id(occupants[j]))))
                    if key not in seen:
                        seen.add(key)
                        pairs.append((occupants[i], occupants[j]))
        return pairs

    # ── Step ─────────────────────────────────

    def step(self) -> None:
        """Integrate velocities and resolve all collisions."""
        dt = self.fixed_dt
        current_collisions: Set[Tuple[int, int]] = set()

        # ── Integration ──────────────────────
        for entity in self._bodies:
            rb = getattr(entity, "rigidbody", None)
            if not rb or rb.body_type == BodyType.STATIC:
                continue
            if rb._sleeping:
                continue

            if rb.body_type == BodyType.DYNAMIC:
                # Gravity
                rb.velocity.x += self.gravity.x * rb.gravity_scale * dt
                rb.velocity.y += self.gravity.y * rb.gravity_scale * dt
                # Drag
                if rb.drag > 0:
                    factor = max(0.0, 1.0 - rb.drag * dt)
                    rb.velocity.x *= factor
                    rb.velocity.y *= factor

            if not rb.freeze_x:
                entity.x += rb.velocity.x * dt
            if not rb.freeze_y:
                entity.y += rb.velocity.y * dt

            rb._check_sleep(dt)

        # ── Collision Detection (spatial hash broad phase) ────────────
        for e1, e2 in self._broad_phase():
            rb1 = getattr(e1, "rigidbody", None)
            c1  = getattr(e1, "collider",  None)
            rb2 = getattr(e2, "rigidbody", None)
            c2  = getattr(e2, "collider",  None)
            if not c1 or not c2:
                continue

            # Layer mask check
            if not self._can_collide(e1, rb1, e2, rb2):
                continue

            p1 = Vector2(e1.x, e1.y)
            p2 = Vector2(e2.x, e2.y)
            result = self._detect(c1, p1, c2, p2)
            if result is None:
                continue

            normal, depth = result
            is_trigger = c1.is_trigger or c2.is_trigger
            pair_id = tuple(sorted((id(e1), id(e2))))
            current_collisions.add(pair_id)

            ci1 = CollisionInfo(e2,  normal, depth, is_trigger)
            ci2 = CollisionInfo(e1, -normal, depth, is_trigger)

            hook = "on_collision_enter" if pair_id not in self._active_collisions else "on_collision_stay"
            trig_hook = "on_trigger_enter" if pair_id not in self._active_collisions else None

            if is_trigger:
                e1._dispatch(trig_hook or "on_trigger_enter", ci1)
                e2._dispatch(trig_hook or "on_trigger_enter", ci2)
            else:
                e1._dispatch(hook, ci1)
                e2._dispatch(hook, ci2)
                self._resolve(e1, rb1, c1, e2, rb2, c2, normal, depth)

        # ── Exit callbacks ────────────────────
        for pair in (self._active_collisions - current_collisions):
            id1, id2 = pair
            e1 = next((e for e in self._bodies if id(e) == id1), None)
            e2 = next((e for e in self._bodies if id(e) == id2), None)
            if e1 and e2:
                col = getattr(e1, "collider", None)
                is_trig = getattr(col, "is_trigger", False)
                ci1 = CollisionInfo(e2, Vector2.zero(), 0.0)
                ci2 = CollisionInfo(e1, Vector2.zero(), 0.0)
                hook = "on_trigger_exit" if is_trig else "on_collision_exit"
                e1._dispatch(hook, ci1)
                e2._dispatch(hook, ci2)

        self._active_collisions = current_collisions

    # ── Detection dispatch ────────────────────

    def _detect(
        self,
        c1: Collider, p1: Vector2,
        c2: Collider, p2: Vector2,
    ) -> Optional[Tuple[Vector2, float]]:
        if isinstance(c1, BoxCollider) and isinstance(c2, BoxCollider):
            return _box_vs_box(c1, p1, c2, p2)
        if isinstance(c1, CircleCollider) and isinstance(c2, CircleCollider):
            return _circle_vs_circle(c1, p1, c2, p2)
        if isinstance(c1, CircleCollider) and isinstance(c2, BoxCollider):
            r = _circle_vs_box(c1, p1, c2, p2)
            return r
        if isinstance(c1, BoxCollider) and isinstance(c2, CircleCollider):
            r = _circle_vs_box(c2, p2, c1, p1)
            if r:
                return (-r[0], r[1])
        return None

    # ── Resolution ───────────────────────────

    def _resolve(
        self,
        e1: Any, rb1: Optional[Rigidbody], c1: Collider,
        e2: Any, rb2: Optional[Rigidbody], c2: Collider,
        normal: Vector2, depth: float,
    ) -> None:
        m1 = rb1.body_type == BodyType.DYNAMIC if rb1 else False
        m2 = rb2.body_type == BodyType.DYNAMIC if rb2 else False
        if not m1 and not m2:
            return

        # ── Positional correction (Baumgarte) ─
        slop       = 0.01
        percent    = 0.8
        correction = max(depth - slop, 0.0) * percent

        if m1 and m2:
            total = (rb1.mass or 1) + (rb2.mass or 1)
            r1    = (rb2.mass or 1) / total
            r2    = (rb1.mass or 1) / total
            if not rb1.freeze_x: e1.x += normal.x * correction * r1
            if not rb1.freeze_y: e1.y += normal.y * correction * r1
            if not rb2.freeze_x: e2.x -= normal.x * correction * r2
            if not rb2.freeze_y: e2.y -= normal.y * correction * r2
        elif m1:
            if not rb1.freeze_x: e1.x += normal.x * correction
            if not rb1.freeze_y: e1.y += normal.y * correction
        else:
            if not rb2.freeze_x: e2.x -= normal.x * correction
            if not rb2.freeze_y: e2.y -= normal.y * correction

        # ── Impulse resolution ────────────────
        v1  = rb1.velocity if rb1 else Vector2.zero()
        v2  = rb2.velocity if rb2 else Vector2.zero()
        rel = v1 - v2
        vel_n = rel.dot(normal)

        if vel_n > 0:   # already separating
            return

        bounce = min(c1.material.bounciness, c2.material.bounciness)
        inv_m1 = (1.0 / rb1.mass) if (rb1 and m1) else 0.0
        inv_m2 = (1.0 / rb2.mass) if (rb2 and m2) else 0.0
        inv_sum = inv_m1 + inv_m2
        if inv_sum == 0:
            return

        j = -(1 + bounce) * vel_n / inv_sum

        if m1:
            if not rb1.freeze_x: v1.x += j * normal.x * inv_m1
            if not rb1.freeze_y: v1.y += j * normal.y * inv_m1
        if m2:
            if not rb2.freeze_x: v2.x -= j * normal.x * inv_m2
            if not rb2.freeze_y: v2.y -= j * normal.y * inv_m2

        # ── Friction ─────────────────────────
        tangent = rel - normal * rel.dot(normal)
        if tangent.magnitude > 0.001:
            tan_n   = tangent.normalized
            jt      = -rel.dot(tan_n) / inv_sum
            mu      = (c1.material.friction + c2.material.friction) * 0.5
            friction_impulse = tan_n * (jt if abs(jt) < j * mu else -j * mu)
            if m1:
                if not rb1.freeze_x: v1.x += friction_impulse.x * inv_m1
                if not rb1.freeze_y: v1.y += friction_impulse.y * inv_m1
            if m2:
                if not rb2.freeze_x: v2.x -= friction_impulse.x * inv_m2
                if not rb2.freeze_y: v2.y -= friction_impulse.y * inv_m2

    # ── Layer masking ─────────────────────────

    @staticmethod
    def _can_collide(
        e1: Any, rb1: Optional[Rigidbody],
        e2: Any, rb2: Optional[Rigidbody],
    ) -> bool:
        l1 = getattr(e1, "layer", "default")
        l2 = getattr(e2, "layer", "default")
        if rb1 and rb2:
            return l2 in rb1.mask or l1 in rb2.mask
        if rb1:
            return l2 in rb1.mask
        if rb2:
            return l1 in rb2.mask
        return True

    # ── Sensor Queries ────────────────────────

    def overlap_rect(
        self,
        rect: Tuple[float, float, float, float],
        mask: Set[str] = None,
    ) -> List[Any]:
        """Return all entities whose BoxCollider overlaps the AABB (l, t, r, b)."""
        rx1, ry1, rx2, ry2 = rect
        hits = []
        for e in self._bodies:
            if mask and getattr(e, "layer", "default") not in mask:
                continue
            col = getattr(e, "collider", None)
            if isinstance(col, BoxCollider):
                b = col.get_bounds(Vector2(e.x, e.y))
                if rx1 < b[2] and rx2 > b[0] and ry1 < b[3] and ry2 > b[1]:
                    hits.append(e)
        return hits

    def overlap_circle(
        self,
        center: Vector2,
        radius: float,
        mask: Set[str] = None,
    ) -> List[Any]:
        """Return all entities within `radius` pixels of `center`."""
        hits = []
        for e in self._bodies:
            if mask and getattr(e, "layer", "default") not in mask:
                continue
            col = getattr(e, "collider", None)
            ep  = Vector2(e.x, e.y)
            if isinstance(col, CircleCollider):
                c = col.center(ep)
                if c.distance_to(center) <= radius + col.radius:
                    hits.append(e)
            elif isinstance(col, BoxCollider):
                bc = col.center(ep)
                if bc.distance_to(center) <= radius + max(col.width, col.height) / 2:
                    hits.append(e)
        return hits

    def raycast(
        self,
        origin: Vector2,
        direction: Vector2,
        max_distance: float,
        mask: Set[str] = None,
    ) -> Optional[Tuple[Any, Vector2, float]]:
        """
        Cast a ray and return the first solid entity hit.

        Args:
            origin:       World-space start position.
            direction:    Unit vector (normalized) direction.
            max_distance: Maximum ray length in pixels.
            mask:         Layer mask (None = hit all layers).

        Returns:
            (entity, hit_point, distance) or None if nothing was hit.
        """
        best_dist = max_distance
        best_hit  = None
        best_pt   = None
        d = direction.normalized

        for e in self._bodies:
            if mask and getattr(e, "layer", "default") not in mask:
                continue
            col = getattr(e, "collider", None)
            if not isinstance(col, BoxCollider):
                continue
            b = col.get_bounds(Vector2(e.x, e.y))
            # Slab method AABB vs ray
            inv_dx = 1.0 / d.x if d.x != 0 else float("inf")
            inv_dy = 1.0 / d.y if d.y != 0 else float("inf")
            tx1 = (b[0] - origin.x) * inv_dx
            tx2 = (b[2] - origin.x) * inv_dx
            ty1 = (b[1] - origin.y) * inv_dy
            ty2 = (b[3] - origin.y) * inv_dy
            tmin = max(min(tx1, tx2), min(ty1, ty2))
            tmax = min(max(tx1, tx2), max(ty1, ty2))
            if tmax < 0 or tmin > tmax or tmin > best_dist:
                continue
            t = max(tmin, 0.0)
            if t < best_dist:
                best_dist = t
                best_hit  = e
                best_pt   = origin + d * t

        if best_hit:
            return (best_hit, best_pt, best_dist)
        return None

    # ── Debug Draw ────────────────────────────

    def draw_debug(self, surface: Any, offset: Tuple[float, float] = (0.0, 0.0)) -> None:
        """Draw wireframe outlines for all registered colliders."""
        if not _HAS_PYGAME:
            return
        ox, oy = offset
        for e in self._bodies:
            col = getattr(e, "collider", None)
            rb  = getattr(e, "rigidbody", None)
            pos = Vector2(e.x, e.y)
            if isinstance(col, BoxCollider):
                b = col.get_bounds(pos)
                color = (0, 255, 0) if rb and rb.body_type == BodyType.DYNAMIC else (100, 100, 255)
                if col.is_trigger:
                    color = (255, 200, 0)
                r = pygame.Rect(b[0]-ox, b[1]-oy, col.width, col.height)
                pygame.draw.rect(surface, color, r, 1)
            elif isinstance(col, CircleCollider):
                c = col.center(pos)
                pygame.draw.circle(surface, (0, 200, 255),
                                   (int(c.x - ox), int(c.y - oy)), int(col.radius), 1)


PhysicsWorld = PhysicsWorldSystem()
