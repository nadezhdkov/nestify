"""
nestifypy.pyunix.sprite
-----------------------
Entity-Component foundation — the heart of every game object.

`Entity` is the base class for all game objects. It owns a `Transform` for
spatial data, an optional `Animator` for sprite animation, physics components,
alpha/tint for rendering, and a component map for arbitrary user components.

`SpriteGroup` batches update/draw calls across many entities.

The `@Sprite` decorator namespace lets you tag methods to fire at specific
lifecycle moments — exactly like MonoBehaviour in Unity or Node in Godot.

Usage:
    class Player(Entity):
        @Sprite.ready
        def setup(self):
            self.animator.add_clip("idle", frames, fps=8).play("idle")

        @Sprite.update
        def move(self, dt):
            self.transform.x += Input.get_axis("horizontal") * 150 * dt
            self.animator.update(dt)

        @Sprite.draw
        def render(self, surface):
            self.draw_self(surface, Camera.offset)

        @Sprite.on_collision_enter
        def hit(self, info):
            print(f"Hit: {info.other}")
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

from nestifypy.pyunix.math import Vector2, Color
from nestifypy.pyunix.transform import Transform
from nestifypy.pyunix.animation import Animator

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False

T = TypeVar("T")

# Lazy import to avoid circular
def _physics_world():
    from nestifypy.pyunix.physics import PhysicsWorld
    return PhysicsWorld


# ---------------------------------------------------------------------------
# SpriteSystem (decorator namespace)
# ---------------------------------------------------------------------------

class SpriteSystem:
    """Decorator namespace for Entity lifecycle hooks."""

    _HOOKS = frozenset({
        "ready", "update", "fixed_update", "draw", "destroy",
        "on_collision_enter", "on_collision_stay", "on_collision_exit",
        "on_trigger_enter", "on_trigger_exit",
        "pause", "resume",
    })

    def _make_hook(self, name: str) -> staticmethod:
        def decorator(func: Callable) -> Callable:
            func._pyunix_sprite = name
            return func
        decorator.__doc__ = f"Mark method as `{name}` lifecycle hook."
        return staticmethod(decorator)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    # Explicit decorators (for IDE autocomplete / docs)

    @staticmethod
    def ready(func: Callable) -> Callable:
        """Called once when the entity is fully constructed."""
        func._pyunix_sprite = "ready"
        return func

    @staticmethod
    def update(func: Callable) -> Callable:
        """Called every frame with `dt`."""
        func._pyunix_sprite = "update"
        return func

    @staticmethod
    def fixed_update(func: Callable) -> Callable:
        """Called at a fixed timestep for physics-safe logic."""
        func._pyunix_sprite = "fixed_update"
        return func

    @staticmethod
    def draw(func: Callable) -> Callable:
        """Called every frame for custom rendering. Receives `surface`."""
        func._pyunix_sprite = "draw"
        return func

    @staticmethod
    def destroy(func: Callable) -> Callable:
        """Called right before the entity is removed."""
        func._pyunix_sprite = "destroy"
        return func

    @staticmethod
    def on_collision_enter(func: Callable) -> Callable:
        """Fired on the first frame two colliders overlap."""
        func._pyunix_sprite = "on_collision_enter"
        return func

    @staticmethod
    def on_collision_stay(func: Callable) -> Callable:
        """Fired every frame while two colliders remain overlapping."""
        func._pyunix_sprite = "on_collision_stay"
        return func

    @staticmethod
    def on_collision_exit(func: Callable) -> Callable:
        """Fired when two colliders stop overlapping."""
        func._pyunix_sprite = "on_collision_exit"
        return func

    @staticmethod
    def on_trigger_enter(func: Callable) -> Callable:
        """Fired on entry into a trigger zone."""
        func._pyunix_sprite = "on_trigger_enter"
        return func

    @staticmethod
    def on_trigger_exit(func: Callable) -> Callable:
        """Fired on exit from a trigger zone."""
        func._pyunix_sprite = "on_trigger_exit"
        return func

    @staticmethod
    def pause(func: Callable) -> Callable:
        """Called when the game is paused."""
        func._pyunix_sprite = "pause"
        return func

    @staticmethod
    def resume(func: Callable) -> Callable:
        """Called when the game is resumed."""
        func._pyunix_sprite = "resume"
        return func


Sprite = SpriteSystem()


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

class Entity:
    """
    Base class for all game objects.

    Every Entity automatically owns:
    - ``transform``  — position, rotation, scale + parent/child hierarchy
    - ``animator``   — sprite-sheet animation controller (lazy-created)
    - ``image``      — current pygame Surface for rendering (can be None)
    - ``alpha``      — opacity 0–255 (applied during draw_self)
    - ``tint``       — Color tint applied at render time (None = no tint)
    - ``visible``    — toggle rendering without destroying
    - ``active``     — toggle update + rendering
    - ``tag``        — string identifier for group queries
    - ``layer``      — collision/render layer name
    - physics slots  — rigidbody, collider (set manually or via constructor)
    - ``components`` — arbitrary component dictionary
    """

    def __init__(
        self,
        x: float = 0.0,
        y: float = 0.0,
        rotation: float = 0.0,
        scale: Vector2 = None,
        layer: str = "default",
        tag: str = "",
        rigidbody: Any = None,
        collider: Any = None,
        image: Any = None,
    ) -> None:
        # ── Core Components ──────────────────
        self.transform = Transform(
            position=Vector2(x, y),
            rotation=rotation,
            scale=scale or Vector2.one(),
        )
        self.transform._entity_ref = self

        self._animator: Optional[Animator] = None   # lazy init

        # ── Rendering ────────────────────────
        self.image: Optional[Any] = image
        self.alpha: float = 255.0            # 0 = invisible, 255 = opaque
        self.tint: Optional[Color] = None    # Color to multiply onto image
        self.visible: bool = True
        self.active: bool = True

        # ── Identity ─────────────────────────
        self.tag: str = tag
        self.layer: str = layer

        # ── Physics ──────────────────────────
        self.rigidbody = rigidbody
        self.collider = collider

        if self.rigidbody:
            self.rigidbody.entity = self
        if self.rigidbody or self.collider:
            _physics_world().register(self)

        # ── Component map ────────────────────
        self._components: Dict[str, Any] = {}

        # ── Lifecycle hooks ──────────────────
        self._hooks: Dict[str, List[Callable]] = {
            "ready": [], "update": [], "fixed_update": [],
            "draw": [], "destroy": [],
            "on_collision_enter": [], "on_collision_stay": [], "on_collision_exit": [],
            "on_trigger_enter": [], "on_trigger_exit": [],
            "pause": [], "resume": [],
        }
        self._register_hooks()
        self._dispatch("ready")

    # ── Animator (lazy) ──────────────────────

    @property
    def animator(self) -> Animator:
        """Auto-creates the Animator on first access."""
        if self._animator is None:
            self._animator = Animator(self)
        return self._animator

    # ── Transform convenience shortcuts ──────

    @property
    def x(self) -> float:
        return self.transform.position.x

    @x.setter
    def x(self, value: float) -> None:
        self.transform.x = value

    @property
    def y(self) -> float:
        return self.transform.position.y

    @y.setter
    def y(self, value: float) -> None:
        self.transform.y = value

    @property
    def position(self) -> Vector2:
        return self.transform.position

    @position.setter
    def position(self, value: Vector2) -> None:
        self.transform.position = value

    @property
    def rotation(self) -> float:
        return self.transform.rotation

    @rotation.setter
    def rotation(self, value: float) -> None:
        self.transform.rotation = value

    @property
    def scale(self) -> Vector2:
        return self.transform.scale

    @scale.setter
    def scale(self, value: Vector2) -> None:
        self.transform.scale = value

    # ── Components ───────────────────────────

    def add_component(self, key: str, component: Any) -> Any:
        """
        Attach an arbitrary component (any object) under `key`.

        Returns the component for convenience.
        """
        self._components[key] = component
        return component

    def get_component(self, key: str, default: Any = None) -> Any:
        """Retrieve a previously attached component by key."""
        return self._components.get(key, default)

    def has_component(self, key: str) -> bool:
        return key in self._components

    def remove_component(self, key: str) -> None:
        self._components.pop(key, None)

    # ── Physics helpers ──────────────────────

    def set_velocity(self, vx: float, vy: float) -> None:
        if self.rigidbody:
            self.rigidbody.velocity.x = vx
            self.rigidbody.velocity.y = vy

    def add_force(self, force: Vector2) -> None:
        if self.rigidbody:
            self.rigidbody.add_force(force)

    # ── Rendering ────────────────────────────

    def get_rect(self) -> Any:
        """Return a pygame.Rect at world position, sized to the current image."""
        if not _HAS_PYGAME:
            return None
        if self.image:
            r = self.image.get_rect()
            r.center = (int(self.transform.position.x), int(self.transform.position.y))
            return r
        return pygame.Rect(int(self.transform.position.x), int(self.transform.position.y), 0, 0)

    def draw_self(self, surface: Any, offset: Tuple[float, float] = (0.0, 0.0)) -> None:
        """
        Blit `self.image` onto `surface` with transform (rotation, scale, alpha, tint, offset).

        This is a batteries-included renderer. Call it from your `@Sprite.draw` method.

        Args:
            surface: pygame Surface to draw onto.
            offset:  Camera offset (x, y) — typically Camera.offset.
        """
        if not _HAS_PYGAME or not self.visible or self.image is None:
            return

        img = self.image
        ws = self.transform.scale

        # Scale
        if ws.x != 1.0 or ws.y != 1.0:
            new_w = max(1, int(img.get_width() * abs(ws.x)))
            new_h = max(1, int(img.get_height() * abs(ws.y)))
            img = pygame.transform.scale(img, (new_w, new_h))

        # Flip from negative scale
        flip_x = ws.x < 0
        flip_y = ws.y < 0
        if flip_x or flip_y:
            img = pygame.transform.flip(img, flip_x, flip_y)

        # Rotation
        rot = self.transform.rotation
        if rot != 0:
            img = pygame.transform.rotate(img, -rot)  # pygame rotates CCW

        # Tint
        if self.tint is not None:
            img = img.copy()
            tint_surface = pygame.Surface(img.get_size(), pygame.SRCALPHA)
            tint_surface.fill(self.tint.to_rgba())
            img.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        # Alpha
        if self.alpha < 255:
            img = img.copy()
            img.set_alpha(int(self.alpha))

        # Position (centered on transform.position)
        rect = img.get_rect()
        pos = self.transform.position
        rect.center = (int(pos.x - offset[0]), int(pos.y - offset[1]))

        surface.blit(img, rect)

    # ── Collision helpers ────────────────────

    def collides_with(self, other: "Entity") -> bool:
        """Simple image-bounds AABB check (no physics collider required)."""
        if not _HAS_PYGAME:
            return False
        r1 = self.get_rect()
        r2 = other.get_rect()
        if r1 and r2:
            return bool(r1.colliderect(r2))
        return False

    def distance_to(self, other: "Entity") -> float:
        return self.transform.position.distance_to(other.transform.position)

    # ── Lifecycle ────────────────────────────

    def _register_hooks(self) -> None:
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(self, attr_name)
                hook = getattr(attr, "_pyunix_sprite", None)
                if hook and hook in self._hooks:
                    self._hooks[hook].append(attr)
            except AttributeError:
                pass

    def _dispatch(self, hook: str, *args: Any, **kwargs: Any) -> None:
        if not self.active and hook not in ("destroy",):
            return
        for func in self._hooks[hook]:
            func(*args, **kwargs)

    def destroy(self) -> None:
        """Trigger the destroy hook then unregister from PhysicsWorld."""
        self._dispatch("destroy")
        _physics_world().unregister(self)
        self.active = False
        self.visible = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(pos={self.transform.position}, tag={self.tag!r})"


# ---------------------------------------------------------------------------
# SpriteGroup
# ---------------------------------------------------------------------------

class SpriteGroup:
    """
    An ordered collection of Entities with batched lifecycle dispatching.

    Usage:
        enemies = SpriteGroup()
        enemies.add(Goblin(), Goblin())
        enemies.update(dt)
        enemies.draw(screen, Camera.offset)
    """

    def __init__(self) -> None:
        self.sprites: List[Entity] = []

    def add(self, *sprites: Entity) -> "SpriteGroup":
        """Add entities; duplicates are ignored. Returns self for chaining."""
        for s in sprites:
            if s not in self.sprites:
                self.sprites.append(s)
        return self

    def remove(self, *sprites: Entity) -> None:
        for s in sprites:
            if s in self.sprites:
                self.sprites.remove(s)

    def clear(self) -> None:
        self.sprites.clear()

    def update(self, dt: float) -> None:
        for s in list(self.sprites):
            if s.active:
                s._dispatch("update", dt)

    def fixed_update(self) -> None:
        for s in list(self.sprites):
            if s.active:
                s._dispatch("fixed_update")

    def draw(self, surface: Any, offset: Tuple[float, float] = (0.0, 0.0)) -> None:
        """
        Dispatch the draw hook for all visible, active sprites.

        If a sprite has NO @Sprite.draw method but has an image, draw_self is
        called automatically as a fallback.  Sprites that define @Sprite.draw
        are expected to call self.draw_self() themselves — this prevents the
        double-render bug where draw_self ran both inside the hook AND here.
        """
        for s in self.sprites:
            if not (s.visible and s.active):
                continue
            if s._hooks["draw"]:
                # User-defined draw hook — let it handle rendering
                s._dispatch("draw", surface)
            elif s.image and _HAS_PYGAME:
                # No hook defined: auto-render as a convenience fallback
                s.draw_self(surface, offset)

    def find_by_tag(self, tag: str) -> List[Entity]:
        """Return all entities with the given tag."""
        return [s for s in self.sprites if s.tag == tag]

    def find_first_by_tag(self, tag: str) -> Optional[Entity]:
        """Return the first entity with the given tag, or None."""
        return next((s for s in self.sprites if s.tag == tag), None)

    def purge_destroyed(self) -> None:
        """Remove all inactive (destroyed) entities from the group."""
        self.sprites = [s for s in self.sprites if s.active]

    def __len__(self) -> int:
        return len(self.sprites)

    def __iter__(self):
        return iter(self.sprites)

    def __contains__(self, item: Entity) -> bool:
        return item in self.sprites
