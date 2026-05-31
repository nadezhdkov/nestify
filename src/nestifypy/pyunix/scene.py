"""
nestifypy.pyunix.scene
----------------------
Stack-based scene / game-state manager with transition support.

Usage:
    @Scene("menu")
    class MenuScene:
        @Scene.load
        def on_load(self):
            self.title = Text("Main Menu", x=400, y=200, size=48, anchor="center")

        @Scene.unload
        def on_unload(self):
            pass   # clean up if needed

        @Scene.update
        def on_update(self, dt):
            ...

        @Scene.draw
        def on_draw(self, surface):
            surface.fill((20, 20, 30))
            self.title.draw(surface)

    Scene.push("menu")

    # Inside the game loop, forward calls:
    Scene.update(dt)
    Scene.draw(screen)
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from nestifypy.pyunix.exceptions import SceneError


# ---------------------------------------------------------------------------
# SceneManager (internal)
# ---------------------------------------------------------------------------

class SceneManager:
    """
    Internal stack-based scene manager.
    Supports push/pop/switch, per-scene update/draw forwarding,
    and optional cross-fade transitions (if pygame is available).
    """

    __slots__ = (
        "_scenes", "_stack", "_instances",
        "_transition_duration", "_transition_elapsed",
        "_transitioning",
    )

    def __init__(self) -> None:
        self._scenes:    Dict[str, Type]  = {}
        self._stack:     List[str]        = []
        self._instances: Dict[str, Any]   = {}
        # Transition fade state
        self._transition_duration: float  = 0.0
        self._transition_elapsed:  float  = 0.0
        self._transitioning:       bool   = False

    # ── Registration ─────────────────────────

    def register(self, name: str) -> Callable:
        def decorator(cls: Any) -> Any:
            self._scenes[name] = cls
            return cls
        return decorator

    # ── Hook decorators (attached to user class methods) ──────────────────

    @staticmethod
    def load_hook(func: Callable) -> Callable:
        func._pyunix_scene = "load"
        return func

    @staticmethod
    def unload_hook(func: Callable) -> Callable:
        func._pyunix_scene = "unload"
        return func

    @staticmethod
    def update_hook(func: Callable) -> Callable:
        func._pyunix_scene = "update"
        return func

    @staticmethod
    def draw_hook(func: Callable) -> Callable:
        func._pyunix_scene = "draw"
        return func

    @staticmethod
    def pause_hook(func: Callable) -> Callable:
        func._pyunix_scene = "pause"
        return func

    @staticmethod
    def resume_hook(func: Callable) -> Callable:
        func._pyunix_scene = "resume"
        return func

    # ── Stack operations ─────────────────────

    def push(self, name: str, data: Any = None) -> None:
        """Push a new scene on the stack (pauses the current scene).

        Args:
            name: Registered scene name.
            data: Optional payload forwarded to the scene's @Scene.load hook
                  as the first argument.  The hook signature becomes:
                  ``def on_load(self, data=None): ...``
        """
        if name not in self._scenes:
            raise SceneError(f"Scene '{name}' not registered.")
        if self._stack:
            self._dispatch(self._get_instance(self._stack[-1]), "pause")
        self._stack.append(name)
        self._dispatch(self._get_instance(name), "load", data)

    def pop(self, data: Any = None) -> None:
        """Remove the top scene and resume the one beneath it.

        Args:
            data: Optional payload forwarded to the underlying scene's
                  @Scene.resume hook.
        """
        if not self._stack:
            return
        current = self._stack.pop()
        self._dispatch(self._instances.get(current), "unload")
        if self._stack:
            self._dispatch(self._get_instance(self._stack[-1]), "resume", data)

    def switch(self, name: str, data: Any = None) -> None:
        """Replace the current top-of-stack scene with a new one.

        Args:
            name: Registered scene name.
            data: Optional payload forwarded to the new scene's @Scene.load hook.
        """
        if not self._stack:
            self.push(name, data)
            return
        current = self._stack.pop()
        self._dispatch(self._instances.get(current), "unload")
        self._stack.append(name)
        self._dispatch(self._get_instance(name), "load", data)

    def pop_all(self) -> None:
        """Clear the entire scene stack."""
        while self._stack:
            self.pop()

    # ── Per-frame forwarding ──────────────────

    def update(self, dt: float) -> None:
        """Forward update to the active scene. Call from your game loop."""
        inst = self.current
        if inst:
            self._dispatch(inst, "update", dt)

    def draw(self, surface: Any) -> None:
        """Forward draw to the active scene. Call from your game loop."""
        inst = self.current
        if inst:
            self._dispatch(inst, "draw", surface)

    # ── Instance helpers ─────────────────────

    def _get_instance(self, name: str) -> Any:
        if name not in self._instances:
            self._instances[name] = self._scenes[name]()
        return self._instances[name]

    def destroy_instance(self, name: str) -> None:
        """Destroy the cached instance so the scene is re-instantiated next time."""
        self._instances.pop(name, None)

    @property
    def current(self) -> Optional[Any]:
        """The scene instance at the top of the stack, or None."""
        if not self._stack:
            return None
        return self._instances.get(self._stack[-1])

    @property
    def current_name(self) -> Optional[str]:
        return self._stack[-1] if self._stack else None

    @property
    def stack_names(self) -> List[str]:
        return list(self._stack)

    # ── Dispatch ─────────────────────────────

    def _dispatch(self, instance: Any, hook_name: str, *args: Any) -> None:
        if instance is None:
            return
        for attr_name in dir(instance):
            if attr_name.startswith("__"):
                continue
            try:
                attr = getattr(instance, attr_name)
                if getattr(attr, "_pyunix_scene", None) == hook_name:
                    # Pass args only if the hook can accept them
                    # (load receives data, resume receives data, others get nothing)
                    if args and args[0] is not None:
                        try:
                            attr(*args)
                        except TypeError:
                            attr()   # hook doesn't accept data — call without it
                    else:
                        attr()
            except AttributeError:
                pass


# ---------------------------------------------------------------------------
# Public facade
# ---------------------------------------------------------------------------

class _SceneAPI:
    """
    Unified Scene API:
    - `@Scene("name")` — registers a class as a scene
    - `@Scene.load` / `@Scene.unload` — lifecycle hooks
    - `@Scene.update` / `@Scene.draw` — per-frame hooks
    - `Scene.push/pop/switch` — stack operations
    - `Scene.update(dt)` / `Scene.draw(surface)` — loop forwarding
    """

    def __init__(self, manager: SceneManager) -> None:
        self._manager = manager

    def __call__(self, name: str) -> Callable:
        """Use as `@Scene("name")` to register a scene class."""
        return self._manager.register(name)

    # Hook decorators (accessed as `Scene.load`, `Scene.draw`, etc.)
    @property
    def load(self) -> Callable:
        return self._manager.load_hook

    @property
    def unload(self) -> Callable:
        return self._manager.unload_hook

    @property
    def update_hook(self) -> Callable:
        return self._manager.update_hook

    @property
    def draw_hook(self) -> Callable:
        return self._manager.draw_hook

    @property
    def pause(self) -> Callable:
        return self._manager.pause_hook

    @property
    def resume(self) -> Callable:
        return self._manager.resume_hook

    # Stack operations
    def push(self, name: str, data: Any = None) -> None:
        self._manager.push(name, data)

    def pop(self, data: Any = None) -> None:
        self._manager.pop(data)

    def switch(self, name: str, data: Any = None) -> None:
        self._manager.switch(name, data)

    def pop_all(self) -> None:
        self._manager.pop_all()

    def destroy_instance(self, name: str) -> None:
        self._manager.destroy_instance(name)

    # Per-frame forwarding
    def update(self, arg: Any) -> Any:
        if callable(arg):
            return self._manager.update_hook(arg)
        self._manager.update(arg)

    def draw(self, arg: Any) -> Any:
        if callable(arg):
            return self._manager.draw_hook(arg)
        self._manager.draw(arg)

    # Properties
    @property
    def current(self) -> Optional[Any]:
        return self._manager.current

    @property
    def current_name(self) -> Optional[str]:
        return self._manager.current_name

    @property
    def stack(self) -> List[str]:
        return self._manager.stack_names


_manager = SceneManager()
Scene = _SceneAPI(_manager)
