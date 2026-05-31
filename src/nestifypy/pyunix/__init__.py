"""
nestifypy.pyunix
----------------
A professional, decorator-driven 2D game framework built on pygame.

Designed to feel like a lightweight blend of Unity and Godot in pure Python.

Quick start:
    from nestifypy.pyunix import *

    @Game(title="My Game", size=(960, 540))
    class MyGame:

        @Game.start
        def on_start(self):
            self.player = Player()
            Input.bind_action("jump", "SPACE", "W")
            Input.bind_axis("move", positive="RIGHT", negative="LEFT")

        @Game.update
        def on_update(self, dt):
            self.player._dispatch("update", dt)

        @Game.draw
        def on_draw(self, screen):
            Window.clear((30, 30, 40))
            self.player._dispatch("draw", screen)

    MyGame().run()
"""

# ── Core ──────────────────────────────────────────────────────────────────
from nestifypy.pyunix.exceptions import (
    PyunixError,
    WindowError,
    AssetError,
    SceneError,
    InputError,
    AudioError,
    AnimationError,
    ComponentError,
)

# ── Math ─────────────────────────────────────────────────────────────────
from nestifypy.pyunix.math import Vector2, Color

# ── Transform ────────────────────────────────────────────────────────────
from nestifypy.pyunix.transform import Transform

# ── App / Window ─────────────────────────────────────────────────────────
from nestifypy.pyunix.app import Game
from nestifypy.pyunix.window import Window

# ── Input ────────────────────────────────────────────────────────────────
from nestifypy.pyunix.input import Input

# ── Assets ───────────────────────────────────────────────────────────────
from nestifypy.pyunix.assets import Assets
from nestifypy.pyunix.fonts import Fonts
from nestifypy.pyunix.audio import Audio

# ── Entities & Groups ────────────────────────────────────────────────────
from nestifypy.pyunix.sprite import Entity, Sprite, SpriteGroup

# ── Animation & Tweening ─────────────────────────────────────────────────
from nestifypy.pyunix.animation import Animator, AnimationClip
from nestifypy.pyunix.tween import Tween, TweenManager, Ease

# ── Camera ───────────────────────────────────────────────────────────────
from nestifypy.pyunix.camera import Camera

# ── Rendering helpers ────────────────────────────────────────────────────
from nestifypy.pyunix.text import Text
from nestifypy.pyunix.particles import ParticleSystem

# ── Tilemap ──────────────────────────────────────────────────────────────
from nestifypy.pyunix.tilemap import TileMap, TileSet

# ── Physics ──────────────────────────────────────────────────────────────
from nestifypy.pyunix.physics import (
    BodyType,
    BoxCollider,
    CircleCollider,
    Collider,
    CollisionInfo,
    PhysicsMaterial,
    PhysicsWorld,
    Rigidbody,
)

# ── Save ─────────────────────────────────────────────────────────────────
from nestifypy.pyunix.save import SaveSystem, Save

# ── Scene management ─────────────────────────────────────────────────────
from nestifypy.pyunix.scene import Scene

# ── Events & Timers ──────────────────────────────────────────────────────
from nestifypy.pyunix.events import Event
from nestifypy.pyunix.timer import Timer


__all__ = [
    # Errors
    "PyunixError", "WindowError", "AssetError", "SceneError",
    "InputError", "AudioError", "AnimationError", "ComponentError",
    # Math
    "Vector2", "Color",
    # Transform
    "Transform",
    # App / Window
    "Game", "Window",
    # Input
    "Input",
    # Assets / Audio
    "Assets", "Fonts", "Audio",
    # Entities
    "Entity", "Sprite", "SpriteGroup",
    # Animation
    "Animator", "AnimationClip",
    # Tweening
    "Tween", "TweenManager", "Ease",
    # Camera
    "Camera",
    # Rendering
    "Text", "ParticleSystem",
    # Tilemap
    "TileMap", "TileSet",
    # Physics
    "BodyType", "BoxCollider", "CircleCollider", "Collider",
    "CollisionInfo", "PhysicsMaterial", "PhysicsWorld", "Rigidbody",
    # Save
    "Save", "SaveSystem",
    # Scenes
    "Scene",
    # Events & Timers
    "Event", "Timer",
]

__version__ = "2.0.1"
