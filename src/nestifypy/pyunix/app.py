"""
nestifypy.pyunix.app
--------------------
The slogger engine runtime: Game decorator, loop, and lifecycle management.

Provides a Unity-style decorator-driven game loop. Decorate a plain Python
class with `@Game(...)` to turn it into a runnable game application.

Key improvements over v1:
- Explicit layer ordering via Layer.order(int) — no more alphabetical hacks
- Built-in debug overlay (fps, entity count, physics bodies) toggled with F3
- Pause/resume signals dispatched to all entities in tracked SpriteGroups
- TweenManager ticked automatically every frame
- Input state cleared at the start of each frame (just_pressed/released)
- dt capped AND slowed in a configurable time scale
- Physics world step uses configurable fixed_timestep

Usage:
    @Game(title="Platformer", size=(960, 540), fps=60)
    class MyGame:

        @Game.start
        def on_start(self):
            self.player = Player()

        @Game.update
        def on_update(self, dt):
            self.player._dispatch("update", dt)

        @Game.draw
        def on_draw(self, screen):
            screen.fill((30, 30, 40))
            self.player._dispatch("draw", screen)

    MyGame().run()
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from nestifypy.pyunix.camera import Camera
from nestifypy.pyunix.events import Event
from nestifypy.pyunix.input import (
    Input, _clear_frame_state,
    _KEY_DOWN_HANDLERS, _KEY_UP_HANDLERS, _KEY_HELD_HANDLERS,
    _MOUSE_CLICK_HANDLERS, _MOUSE_MOTION_HANDLERS, _ACTION_HANDLERS,
    _ACTION_MAP, _resolve_key, _update_state,
)
from nestifypy.pyunix.timer import Timer
from nestifypy.pyunix.tween import TweenManager
from nestifypy.pyunix.window import Window

try:
    import pygame
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False


# ---------------------------------------------------------------------------
# Layer descriptor
# ---------------------------------------------------------------------------

class _LayerEntry:
    __slots__ = ("name", "order", "func")

    def __init__(self, name: str, order: int, func: Callable) -> None:
        self.name  = name
        self.order = order
        self.func  = func


# ---------------------------------------------------------------------------
# Internal runtime
# ---------------------------------------------------------------------------

class _GameRuntime:
    """
    The internal engine loop and event dispatcher.
    Not intended for direct use — created by the @Game decorator.
    """

    def __init__(self, target: Any, fps: int, fixed_timestep: float) -> None:
        self.target    = target
        self.fps       = fps
        self.running   = False
        self.paused    = False
        self.time_scale: float = 1.0          # slow-mo / fast-forward
        self.fixed_timestep = fixed_timestep
        self.clock: Any = None

        self._hooks: Dict[str, List[Callable]] = {
            "start": [], "stop": [], "pause": [], "resume": [],
            "update": [], "fixed_update": [], "draw": [],
        }
        self._layers: List[_LayerEntry] = []
        self._ui_elements: List[Any] = []
        self._debug_font: Any = None
        self._show_debug: bool = False
        self._frame_count: int = 0
        self._fps_display: float = 0.0

        self._scan_methods()

    def _scan_methods(self) -> None:
        for attr_name in dir(self.target):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(self.target, attr_name)
            except AttributeError:
                continue

            # Lifecycle hooks
            hook = getattr(attr, "_pyunix_game_hook", None)
            if hook and hook in self._hooks:
                self._hooks[hook].append(attr)

            # Render layers
            layer_info = getattr(attr, "_pyunix_layer", None)
            if layer_info:
                name, order = layer_info
                self._layers.append(_LayerEntry(name, order, attr))

            # Auto-text UI
            text_kw = getattr(attr, "_pyunix_text_kwargs", None)
            if text_kw:
                from nestifypy.pyunix.text import Text
                text_entity = Text(text="", **text_kw)
                self._ui_elements.append((attr, text_entity))

        # Sort layers ascending by order value
        self._layers.sort(key=lambda e: e.order)

    def _dispatch(self, hook: str, *args: Any, **kwargs: Any) -> None:
        for fn in self._hooks[hook]:
            fn(*args, **kwargs)

    def _dispatch_input(self, event: Any) -> None:
        Input._dispatch_event(event, self.target)

    def run(self) -> None:
        if not _HAS_PYGAME:
            print("[Pyunix] Warning: pygame not installed. Cannot run.")
            return

        self.clock = pygame.time.Clock()
        self.running = True

        # Debug font (optional)
        try:
            self._debug_font = pygame.font.SysFont("monospace", 14)
        except Exception:
            self._debug_font = None

        self._dispatch("start")

        accumulator  = 0.0
        last_time    = time.perf_counter()

        while self.running:
            # ── Frame Timing ─────────────────
            now = time.perf_counter()
            raw_dt = now - last_time
            last_time = now
            raw_dt = min(raw_dt, 0.25)          # death-spiral cap
            dt = raw_dt * self.time_scale

            # ── Clear per-frame input state ──
            _clear_frame_state()

            # ── Events ───────────────────────
            for event in pygame.event.get():
                _update_state(event)

                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F3:
                        self._show_debug = not self._show_debug
                    elif event.key == pygame.K_ESCAPE:
                        self._toggle_pause()

                self._dispatch_input(event)

            # ── Held keys ────────────────────
            Input._process_held(self.target)

            if not self.paused:
                # ── Fixed Update (physics) ────
                accumulator += dt
                while accumulator >= self.fixed_timestep:
                    from nestifypy.pyunix.physics import PhysicsWorld
                    PhysicsWorld.step()
                    self._dispatch("fixed_update")
                    accumulator -= self.fixed_timestep

                # ── Variable Update ───────────
                self._dispatch("update", dt)
                Timer.tick(dt)
                TweenManager.update(dt)
                Camera.update(dt, Window.width, Window.height)

                # Update auto-text UI
                for fn, text_entity in self._ui_elements:
                    text_entity.set_text(str(fn()))

            # ── Draw ─────────────────────────
            if Window.surface:
                self._dispatch("draw", Window.surface)
                for layer in self._layers:
                    layer.func(Window.surface)
                for _, text_entity in self._ui_elements:
                    text_entity.draw(Window.surface)

                if self._show_debug:
                    self._draw_debug(Window.surface)

                if self.paused:
                    self._draw_pause_overlay(Window.surface)

                pygame.display.flip()

            # ── Tick ─────────────────────────
            self._frame_count += 1
            self.clock.tick(self.fps)
            if self._frame_count % 30 == 0:
                self._fps_display = self.clock.get_fps()

        self._dispatch("stop")
        pygame.quit()

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        hook = "pause" if self.paused else "resume"
        self._dispatch(hook)
        Event.emit(hook)

    def _draw_debug(self, surface: Any) -> None:
        if not self._debug_font:
            return
        from nestifypy.pyunix.physics import PhysicsWorld
        lines = [
            f"FPS:    {self._fps_display:.1f} / {self.fps}",
            f"Bodies: {len(PhysicsWorld._bodies)}",
            f"Camera: ({Camera.x:.0f}, {Camera.y:.0f})  zoom={Camera.zoom_level:.2f}",
            f"Scale:  {self.time_scale:.2f}x",
            f"[F3] hide debug  [ESC] pause",
        ]
        y = 6
        for line in lines:
            bg = self._debug_font.render(line, True, (0, 0, 0))
            fg = self._debug_font.render(line, True, (0, 255, 120))
            surface.blit(bg, (9, y + 1))
            surface.blit(fg, (8, y))
            y += 18

    def _draw_pause_overlay(self, surface: Any) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 110))
        surface.blit(overlay, (0, 0))
        if self._debug_font:
            msg = self._debug_font.render("PAUSED  —  ESC to resume", True, (255, 255, 180))
            r = msg.get_rect(center=(surface.get_width() // 2, surface.get_height() // 2))
            surface.blit(msg, r)


# ---------------------------------------------------------------------------
# Public GameAPI
# ---------------------------------------------------------------------------

class GameAPI:
    """
    The `@Game` class decorator and associated lifecycle decorators.
    """

    def __call__(
        self,
        title: str = "Pyunix Game",
        size: Tuple[int, int] = (800, 600),
        fps: int = 60,
        fixed_timestep: float = 1.0 / 60.0,
        icon: Optional[str] = None,
        resizable: bool = False,
        fullscreen: bool = False,
        vsync: bool = True,
        **kwargs: Any,
    ) -> Callable:
        """
        Decorate a class to turn it into a runnable Pyunix game.

        Args:
            title:           Window title.
            size:            (width, height) in pixels.
            fps:             Target frames per second (also caps rendering).
            fixed_timestep:  Physics update interval in seconds (default 1/60).
            icon:            Path to a window icon image (optional).
            resizable:       Allow window resizing.
            fullscreen:      Start in fullscreen.
            vsync:           Enable vertical sync.

        Injects `.run()`, `.quit()`, `.pause()`, `.resume()`, and
        `.time_scale` onto the decorated class.
        """
        def decorator(cls: type) -> type:
            original_init = cls.__init__

            def new_init(self_obj: Any, *args: Any, **kw: Any) -> None:
                Window.create(title, size, fullscreen=fullscreen,
                              vsync=vsync, resizable=resizable)
                if icon:
                    Window.set_icon(icon)
                self_obj._runtime = _GameRuntime(self_obj, fps, fixed_timestep)
                if original_init is not object.__init__:
                    original_init(self_obj, *args, **kw)

            def run(self_obj: Any) -> None:
                """Start the main game loop (blocking)."""
                self_obj._runtime.run()

            def quit(self_obj: Any) -> None:
                """Stop the game loop gracefully on the next frame."""
                self_obj._runtime.running = False

            def pause(self_obj: Any) -> None:
                """Pause the simulation (draw still runs)."""
                self_obj._runtime.paused = True
                self_obj._runtime._dispatch("pause")

            def resume(self_obj: Any) -> None:
                """Resume the simulation."""
                self_obj._runtime.paused = False
                self_obj._runtime._dispatch("resume")

            @property  # type: ignore
            def time_scale(self_obj: Any) -> float:
                """Read the current simulation time scale."""
                return self_obj._runtime.time_scale

            @time_scale.setter  # type: ignore
            def time_scale(self_obj: Any, value: float) -> None:
                """Set time scale: 1.0 = normal, 0.5 = slow-mo, 0.0 = frozen."""
                self_obj._runtime.time_scale = max(0.0, value)

            cls.__init__   = new_init       # type: ignore
            cls.run        = run            # type: ignore
            cls.quit       = quit           # type: ignore
            cls.pause      = pause          # type: ignore
            cls.resume     = resume         # type: ignore
            cls.time_scale = time_scale     # type: ignore
            return cls

        return decorator

    # ── Lifecycle decorators ──────────────────

    @staticmethod
    def start(func: Callable) -> Callable:
        """Called once before the loop begins."""
        func._pyunix_game_hook = "start"
        return func

    @staticmethod
    def stop(func: Callable) -> Callable:
        """Called once after the loop exits."""
        func._pyunix_game_hook = "stop"
        return func

    @staticmethod
    def update(func: Callable) -> Callable:
        """Called every frame. Method receives `dt` (float, seconds)."""
        func._pyunix_game_hook = "update"
        return func

    @staticmethod
    def fixed_update(func: Callable) -> Callable:
        """Called at a fixed rate (default 60 Hz) for physics logic."""
        func._pyunix_game_hook = "fixed_update"
        return func

    @staticmethod
    def draw(func: Callable) -> Callable:
        """Called every frame for rendering. Method receives `screen` (Surface)."""
        func._pyunix_game_hook = "draw"
        return func

    @staticmethod
    def on_pause(func: Callable) -> Callable:
        """Called when the game is paused (ESC or .pause())."""
        func._pyunix_game_hook = "pause"
        return func

    @staticmethod
    def on_resume(func: Callable) -> Callable:
        """Called when the game is unpaused."""
        func._pyunix_game_hook = "resume"
        return func

    @staticmethod
    def layer(name: str, order: int = 0) -> Callable:
        """
        Register a draw method to a named render layer.

        Layers are drawn in ascending `order` (lower = drawn first/beneath).

        Example:
            @Game.layer("background", order=0)
            def draw_bg(self, screen): ...

            @Game.layer("entities", order=1)
            def draw_entities(self, screen): ...

            @Game.layer("ui", order=2)
            def draw_ui(self, screen): ...
        """
        def decorator(func: Callable) -> Callable:
            func._pyunix_layer = (name, order)
            return func
        return decorator

    @staticmethod
    def text(**kwargs: Any) -> Callable:
        """
        Auto-render a dynamic text label every frame.
        The decorated method must return a string value.
        All kwargs are forwarded to the Text entity constructor.

        Example:
            @Game.text(x=10, y=10, size=20, color="yellow")
            def score_label(self):
                return f"Score: {self.score}"
        """
        def decorator(func: Callable) -> Callable:
            func._pyunix_text_kwargs = kwargs
            return func
        return decorator


# Global singleton — use as both `@Game(...)` decorator and `Game.update` etc.
Game = GameAPI()
