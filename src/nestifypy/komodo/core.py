"""
nestifypy.komodo.slogger
-------------------
The `komodo` namespace — all class-level annotation decorators live here.

Each decorator inspects `__annotations__` and modifies the class in-place
at *definition time*, mirroring how Lombok operates via APT (Annotation
Processing Tool) but using Python's metaclass-free, pure-decorator approach.
"""

from __future__ import annotations

import copy
import inspect
import logging
import types
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar

C = TypeVar("C", bound=type)
F = TypeVar("F", bound=Callable[..., Any])

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

_KOMODO_META_ATTR = "__komodo_meta__"


def _get_fields(cls: type) -> Dict[str, Any]:
    """
    Collect annotated fields from the class (not inherited ones).
    Returns {field_name: annotation_type}.
    """
    return {
        k: v
        for k, v in cls.__annotations__.items()
        if not k.startswith("_")
    }


def _get_defaults(cls: type) -> Dict[str, Any]:
    """Return field defaults defined as class attributes."""
    return {
        k: getattr(cls, k)
        for k in _get_fields(cls)
        if hasattr(cls, k)
    }


def _mark(cls: type, feature: str) -> None:
    """Tag a class with which komodo features were applied."""
    if not hasattr(cls, _KOMODO_META_ATTR):
        setattr(cls, _KOMODO_META_ATTR, set())
    getattr(cls, _KOMODO_META_ATTR).add(feature)


def _has(cls: type, feature: str) -> bool:
    return feature in getattr(cls, _KOMODO_META_ATTR, set())


# ─────────────────────────────────────────────────────────────────────────────
#  komodo namespace
# ─────────────────────────────────────────────────────────────────────────────

class _Komodo:
    """
    Lombok-inspired annotation toolkit for Python classes.

    All methods are static decorators that rewrite a class at definition time.
    Stack multiple decorators to compose behaviour — they are designed to
    be fully composable and idempotent where possible.
    """

    # ── @komodo.data ────────────────────────────────────────────────────────────

    @staticmethod
    def data(cls: C) -> C:
        """
        Generate ``__init__``, ``__repr__``, ``__eq__``, and ``__hash__``
        from annotated fields — equivalent to Lombok's ``@Data``.

        Fields without defaults are required positional args in ``__init__``.
        Fields with class-level defaults become keyword args.

        Example::

            @komodo.data
            class Point:
                x: float
                y: float

            p = Point(1.0, 2.0)
            print(p)           # Point(x=1.0, y=2.0)
            print(p == Point(1.0, 2.0))  # True
        """
        cls = _Komodo.constructor(cls)
        cls = _Komodo.to_str(cls)
        cls = _Komodo.eq(cls)
        _mark(cls, "data")
        return cls

    # ── @komodo.value ───────────────────────────────────────────────────────────

    @staticmethod
    def value(cls: C) -> C:
        """
        Create an immutable value object.  Like Lombok's ``@Value``:
        ``__init__`` is generated, all fields are frozen after construction,
        and ``__hash__`` is based on field values.

        Raises ``AttributeError`` on any attempted mutation.

        Example::

            @komodo.value
            class Money:
                amount: float
                currency: str

            m = Money(9.99, "USD")
            m.amount = 1.0  # AttributeError!
        """
        cls = _Komodo.data(cls)
        cls = _Komodo.immutable(cls)
        _mark(cls, "value")
        return cls

    # ── @komodo.constructor ─────────────────────────────────────────────────────

    @staticmethod
    def constructor(cls: C) -> C:
        """
        Generate ``__init__`` from annotated fields.

        Fields with defaults → keyword arguments.
        Fields without defaults → required positional arguments.

        Also runs ``@komodo.non_null`` style validation when a field is
        annotated with a non-``Optional`` type.

        Example::

            @komodo.constructor
            class Server:
                host: str
                port: int = 8080

            s = Server("localhost")   # port defaults to 8080
            s2 = Server("0.0.0.0", 443)
        """
        fields = _get_fields(cls)
        defaults = _get_defaults(cls)

        # Separate required vs optional fields
        required = [f for f in fields if f not in defaults]
        optional = [f for f in fields if f in defaults]

        # Build the signature programmatically
        params = [inspect.Parameter("self", inspect.Parameter.POSITIONAL_ONLY)]
        for name in required:
            params.append(
                inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                  annotation=fields[name])
            )
        for name in optional:
            params.append(
                inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                  default=defaults[name],
                                  annotation=fields[name])
            )

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            # Bind positional + keyword args to field names
            all_names = required + optional
            all_defaults = {n: defaults[n] for n in optional}

            bound: Dict[str, Any] = dict(all_defaults)
            for i, val in enumerate(args):
                if i < len(all_names):
                    bound[all_names[i]] = val
            bound.update(kwargs)

            # Check required fields were provided
            for name in required:
                if name not in bound:
                    raise TypeError(
                        f"{cls.__name__}.__init__() missing required argument: '{name}'"
                    )

            for name, val in bound.items():
                object.__setattr__(self, name, val)

            # Call user-defined __post_init__ if present
            if hasattr(cls, "__post_init__"):
                cls.__post_init__(self)

        __init__.__signature__ = inspect.Signature(params)  # type: ignore
        __init__.__doc__ = (
            f"Generated by @komodo.constructor for {cls.__name__}.\n"
            f"Fields: {', '.join(fields)}"
        )

        cls.__init__ = __init__  # type: ignore
        _mark(cls, "constructor")
        return cls

    # ── @komodo.to_str ──────────────────────────────────────────────────────────

    @staticmethod
    def to_str(cls: C) -> C:
        """
        Generate ``__repr__`` and ``__str__`` from annotated fields.

        Output format: ``ClassName(field1=value1, field2=value2)``.

        Example::

            @komodo.to_str
            class Config:
                host: str = "localhost"
                port: int = 8080

            print(Config())   # Config(host='localhost', port=8080)
        """
        fields = list(_get_fields(cls))

        def __repr__(self: Any) -> str:
            parts = ", ".join(
                f"{f}={getattr(self, f, '<missing>')!r}" for f in fields
            )
            return f"{self.__class__.__name__}({parts})"

        cls.__repr__ = __repr__  # type: ignore
        cls.__str__ = __repr__   # type: ignore
        _mark(cls, "to_str")
        return cls

    # ── @komodo.eq ──────────────────────────────────────────────────────────────

    @staticmethod
    def eq(cls: C) -> C:
        """
        Generate ``__eq__`` and ``__hash__`` from annotated fields.

        Two instances are equal if they are of the same type and all
        annotated field values match.  ``__hash__`` is computed from
        the tuple of all field values (requires all fields to be hashable).

        Example::

            @komodo.eq
            class Tag:
                name: str

            assert Tag("python") == Tag("python")
            assert Tag("a") != Tag("b")
        """
        fields = list(_get_fields(cls))

        def __eq__(self: Any, other: object) -> bool:
            if not isinstance(other, self.__class__):
                return NotImplemented
            return all(
                getattr(self, f, None) == getattr(other, f, None)
                for f in fields
            )

        def __hash__(self: Any) -> int:
            try:
                return hash(tuple(getattr(self, f, None) for f in fields))
            except TypeError:
                # Unhashable field — fall back to id-based hash
                return id(self)

        cls.__eq__ = __eq__      # type: ignore
        cls.__hash__ = __hash__  # type: ignore
        _mark(cls, "eq")
        return cls

    # ── @komodo.immutable ───────────────────────────────────────────────────────

    @staticmethod
    def immutable(cls: C) -> C:
        """
        Prevent attribute mutation after ``__init__`` completes.

        Raises ``AttributeError`` on any ``setattr`` or ``delattr`` call
        once the object is constructed.  Internally sets a ``_frozen``
        flag on the instance.

        Example::

            @komodo.immutable
            @komodo.constructor
            class Point:
                x: float
                y: float

            p = Point(1.0, 2.0)
            p.x = 99.0  # AttributeError: Point is immutable
        """
        original_init = cls.__init__ if hasattr(cls, "__init__") else None

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            object.__setattr__(self, "_frozen", False)
            if original_init:
                original_init(self, *args, **kwargs)
            object.__setattr__(self, "_frozen", True)

        def __setattr__(self: Any, name: str, value: Any) -> None:
            if getattr(self, "_frozen", False):
                raise AttributeError(
                    f"{self.__class__.__name__} is immutable — "
                    f"cannot set attribute '{name}'"
                )
            object.__setattr__(self, name, value)

        def __delattr__(self: Any, name: str) -> None:
            if getattr(self, "_frozen", False):
                raise AttributeError(
                    f"{self.__class__.__name__} is immutable — "
                    f"cannot delete attribute '{name}'"
                )
            object.__delattr__(self, name)

        cls.__init__ = __init__        # type: ignore
        cls.__setattr__ = __setattr__  # type: ignore
        cls.__delattr__ = __delattr__  # type: ignore
        _mark(cls, "immutable")
        return cls

    # ── @komodo.builder ─────────────────────────────────────────────────────────

    @staticmethod
    def builder(cls: C) -> C:
        """
        Attach a fluent ``Builder`` inner class to the decorated class.

        The builder exposes one setter per annotated field (``with_<field>``)
        and a ``build()`` method that constructs the final instance.

        Access via ``MyClass.Builder()`` or the class-level ``builder()``
        factory method.

        Example::

            @komodo.builder
            class Request:
                url: str
                method: str = "GET"
                timeout: float = 30.0

            req = (
                Request.Builder()
                    .with_url("https://api.example.com")
                    .with_method("POST")
                    .with_timeout(10.0)
                    .build()
            )
        """
        fields = _get_fields(cls)
        defaults = _get_defaults(cls)
        target_cls = cls  # capture for closure

        # ── Inner Builder class ──────────────────────────────────────────────

        class Builder:
            __doc__ = f"Fluent builder for {target_cls.__name__}."

            def __init__(self) -> None:
                for name, default in defaults.items():
                    object.__setattr__(self, f"_{name}", default)
                for name in fields:
                    if name not in defaults:
                        object.__setattr__(self, f"_{name}", _UNSET)

            def build(self) -> Any:
                """Construct and return the target instance."""
                kwargs: Dict[str, Any] = {}
                for name in fields:
                    val = getattr(self, f"_{name}")
                    if val is _UNSET:
                        raise ValueError(
                            f"{target_cls.__name__}.Builder: "
                            f"required field '{name}' was not set"
                        )
                    kwargs[name] = val
                # Use object.__new__ + manual setattr if no __init__ accepts kwargs
                try:
                    return target_cls(**kwargs)
                except TypeError:
                    instance = object.__new__(target_cls)
                    for k, v in kwargs.items():
                        object.__setattr__(instance, k, v)
                    return instance

            def __repr__(self) -> str:
                parts = ", ".join(
                    f"{n}={getattr(self, f'_{n}', _UNSET)!r}" for n in fields
                )
                return f"{target_cls.__name__}.Builder({parts})"

        # Dynamically add `with_<field>` methods to Builder
        def _make_setter(field_name: str) -> Callable:
            def setter(self: Any, value: Any) -> Any:
                object.__setattr__(self, f"_{field_name}", value)
                return self
            setter.__name__ = f"with_{field_name}"
            setter.__doc__ = f"Set the ``{field_name}`` field."
            return setter

        for field_name in fields:
            setattr(Builder, f"with_{field_name}", _make_setter(field_name))

        Builder.__name__ = "Builder"
        Builder.__qualname__ = f"{cls.__name__}.Builder"

        cls.Builder = Builder  # type: ignore

        @staticmethod  # type: ignore
        def builder_factory() -> Builder:  # type: ignore
            """Return a new Builder for this class."""
            return Builder()

        cls.builder = builder_factory  # type: ignore
        _mark(cls, "builder")
        return cls

    # ── @komodo.accessors ───────────────────────────────────────────────────────

    @staticmethod
    def accessors(
        readonly: bool = False,
    ) -> Callable[[C], C]:
        """
        Generate Python ``property`` getters (and optionally setters)
        for all annotated fields — like Lombok's ``@Getter``/``@Setter``.

        Args:
            readonly: If ``True``, only getters are generated (like ``@Getter``).
                      If ``False`` (default), both getters and setters are added.

        Example::

            @komodo.accessors()
            class Persona:
                name: str
                age: int

            p = Persona.__new__(Persona)
            object.__setattr__(p, 'name', 'Alice')
            print(p.name)     # Alice
            p.name = "Bob"    # Works unless readonly=True
        """
        def decorator(cls: C) -> C:
            fields = _get_fields(cls)

            for field_name in fields:
                private = f"_{field_name}"

                # Getter
                def make_getter(fn: str, pn: str) -> property:
                    def fget(self: Any) -> Any:
                        return getattr(self, pn, None)
                    fget.__name__ = fn
                    if readonly:
                        return property(fget)
                    # Setter
                    def fset(self: Any, value: Any) -> None:
                        object.__setattr__(self, pn, value)
                    fset.__name__ = fn
                    return property(fget, fset)

                prop = make_getter(field_name, private)
                setattr(cls, field_name, prop)

            _mark(cls, "accessors")
            return cls

        return decorator

    # ── @komodo.logger ──────────────────────────────────────────────────────────

    @staticmethod
    def logger(cls: C) -> C:
        """
        Inject a class-level ``logger`` attribute (like Lombok's ``@Slf4j``).

        The logger is named after the class and accessible as ``self.logger``
        or ``MyClass.logger``.  Uses the standard ``logging`` module.

        Example::

            @komodo.logger
            class Service:
                def run(self) -> None:
                    self.logger.info("Service started")
        """
        log = logging.getLogger(f"{cls.__module__}.{cls.__name__}")
        cls.logger = log  # type: ignore
        _mark(cls, "logger")
        return cls

    # ── @komodo.non_null ────────────────────────────────────────────────────────

    @staticmethod
    def non_null(cls: C) -> C:
        """
        Wrap ``__init__`` to raise ``ValueError`` for any ``None`` argument
        — equivalent to Lombok's ``@NonNull`` on constructor parameters.

        Works after ``@komodo.constructor`` or any custom ``__init__``.

        Example::

            @komodo.non_null
            @komodo.constructor
            class User:
                name: str
                email: str

            User(name=None, email="x@y.z")  # ValueError!
        """
        original_init = cls.__init__

        @wraps(original_init)
        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            fields = list(_get_fields(cls))
            # Check positional args
            for i, val in enumerate(args):
                if val is None and i < len(fields):
                    raise ValueError(
                        f"{cls.__name__}: field '{fields[i]}' must not be None"
                    )
            # Check keyword args
            for k, v in kwargs.items():
                if v is None:
                    raise ValueError(
                        f"{cls.__name__}: field '{k}' must not be None"
                    )
            original_init(self, *args, **kwargs)

        cls.__init__ = __init__  # type: ignore
        _mark(cls, "non_null")
        return cls

    # ── @komodo.singleton ───────────────────────────────────────────────────────

    @staticmethod
    def singleton(cls: C) -> C:
        """
        Ensure only one instance of the class exists (Singleton pattern).

        The instance is created lazily on first call and reused on all
        subsequent instantiations.

        Example::

            @komodo.singleton
            class AppConfig:
                debug: bool = False

            a = AppConfig()
            b = AppConfig()
            assert a is b
        """
        instances: Dict[type, Any] = {}

        original_new = cls.__new__

        def __new__(klass: type, *args: Any, **kwargs: Any) -> Any:  # type: ignore
            if klass not in instances:
                if original_new is object.__new__:
                    instances[klass] = object.__new__(klass)
                else:
                    instances[klass] = original_new(klass, *args, **kwargs)
            return instances[klass]

        cls.__new__ = __new__  # type: ignore
        cls._instance = property(lambda self: instances.get(cls))  # type: ignore
        _mark(cls, "singleton")
        return cls

    # ── @komodo.copyable ────────────────────────────────────────────────────────

    @staticmethod
    def copyable(cls: C) -> C:
        """
        Add ``copy()`` and ``copy_with(**overrides)`` methods to a class.

        ``copy()`` returns a shallow duplicate.
        ``copy_with(**overrides)`` returns a new instance with selected
        fields replaced — like Kotlin's ``data class copy()``.

        Example::

            @komodo.copyable
            @komodo.data
            class Config:
                host: str = "localhost"
                port: int = 8080

            base = Config("localhost", 8080)
            prod = base.copy_with(host="prod.server.com", port=443)
        """
        fields = list(_get_fields(cls))

        def copy(self: Any) -> Any:
            """Return a shallow copy of this instance."""
            return copy_module.copy(self)

        def copy_with(self: Any, **overrides: Any) -> Any:
            """Return a new instance with specified fields replaced."""
            current = {f: getattr(self, f) for f in fields}
            current.update(overrides)
            return self.__class__(**current)

        cls.copy = copy          # type: ignore
        cls.copy_with = copy_with  # type: ignore
        _mark(cls, "copyable")
        return cls

    # ── @komodo.validated ───────────────────────────────────────────────────────

    @staticmethod
    def validated(cls: C) -> C:
        """
        Enforce runtime type checking on ``__init__`` arguments based
        on ``__annotations__``.

        Raises ``TypeError`` with a detailed message when a value does not
        match its declared type annotation.  Supports ``Optional[X]``
        (accepts ``None``).  Correctly resolves string annotations produced
        by ``from __future__ import annotations``.

        Example::

            @komodo.validated
            @komodo.constructor
            class Point:
                x: float
                y: float

            Point("not a float", 1.0)  # TypeError!
        """
        original_init = cls.__init__

        @wraps(original_init)
        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            # Use get_type_hints to resolve string annotations (PEP 563)
            import typing
            try:
                resolved = typing.get_type_hints(cls)
                hints = {k: v for k, v in resolved.items() if not k.startswith("_")}
            except Exception:
                hints = _get_fields(cls)

            names = list(hints)

            bound: Dict[str, Any] = {}
            for i, val in enumerate(args):
                if i < len(names):
                    bound[names[i]] = val
            bound.update(kwargs)

            for name, val in bound.items():
                expected = hints.get(name)
                if expected is None:
                    continue
                # Unwrap Optional
                origin = getattr(expected, "__origin__", None)
                type_args = getattr(expected, "__args__", ())
                is_optional = origin is type(None) or (
                    origin is not None and type(None) in type_args
                )
                if val is None and is_optional:
                    continue
                if val is None:
                    continue  # non_null handles None separately
                # For plain types (not generic)
                if isinstance(expected, type) and not isinstance(val, expected):
                    raise TypeError(
                        f"{cls.__name__}: field '{name}' expected "
                        f"{expected.__name__}, got {type(val).__name__}"
                    )

            original_init(self, *args, **kwargs)

        cls.__init__ = __init__  # type: ignore
        _mark(cls, "validated")
        return cls

    # ── @komodo.observable ─────────────────────────────────────────────────────

    @staticmethod
    def observable(cls: C) -> C:
        """
        Add ``__setattr__`` interception so that any field mutation notifies
        subscribed callbacks — observer pattern without manual plumbing.

        Use ``instance.on_change(callback)`` to register a listener.
        Callback signature: ``(field_name, old_value, new_value) -> None``.

        Example::

            @komodo.observable
            @komodo.constructor
            class Settings:
                theme: str = "dark"

            s = Settings()
            s.on_change(lambda f, old, new: print(f"{f}: {old} → {new}"))
            s.theme = "light"   # prints: theme: dark → light
        """
        original_setattr = cls.__setattr__ if hasattr(cls, "__setattr__") else None

        def __setattr__(self: Any, name: str, value: Any) -> None:
            if not name.startswith("_"):
                old = getattr(self, name, _UNSET)
                if original_setattr and original_setattr is not object.__setattr__:
                    original_setattr(self, name, value)
                else:
                    object.__setattr__(self, name, value)
                if old is not _UNSET and old != value:
                    for cb in getattr(self, "_observers", []):
                        cb(name, old, value)
            else:
                object.__setattr__(self, name, value)

        def on_change(self: Any, callback: Callable) -> None:
            """Register a change listener: ``(field, old, new) -> None``."""
            if not hasattr(self, "_observers"):
                object.__setattr__(self, "_observers", [])
            self._observers.append(callback)

        def off_change(self: Any, callback: Callable) -> None:
            """Unregister a change listener."""
            if hasattr(self, "_observers"):
                self._observers.remove(callback)

        cls.__setattr__ = __setattr__  # type: ignore
        cls.on_change = on_change      # type: ignore
        cls.off_change = off_change    # type: ignore
        _mark(cls, "observable")
        return cls

    # ── @komodo.delegate ────────────────────────────────────────────────────────

    @staticmethod
    def delegate(field: str, methods: Optional[List[str]] = None) -> Callable[[C], C]:
        """
        Delegate specified methods (or all public methods if ``methods`` is
        ``None``) to a wrapped object stored in ``self.<field>``.

        Inspired by Lombok's ``@Delegate``.

        Args:
            field: Attribute name on ``self`` that holds the delegate object.
            methods: List of method names to proxy; all public methods if None.

        Example::

            class _Engine:
                def start(self): print("Engine started")
                def stop(self):  print("Engine stopped")

            @komodo.delegate("_engine", methods=["start", "stop"])
            class Car:
                def __init__(self):
                    self._engine = _Engine()
        """
        def decorator(cls: C) -> C:
            # We can't introspect the delegate type at class-definition time
            # (the instance doesn't exist yet), so we wrap __init__ to lazily
            # attach delegated methods after construction.
            original_init = cls.__init__ if hasattr(cls, "__init__") else None

            @wraps(original_init or (lambda self: None))
            def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
                if original_init:
                    original_init(self, *args, **kwargs)
                delegate_obj = getattr(self, field, None)
                if delegate_obj is None:
                    return
                target_methods = methods or [
                    m for m in dir(delegate_obj)
                    if not m.startswith("_") and callable(getattr(delegate_obj, m))
                ]
                for method_name in target_methods:
                    if not hasattr(cls, method_name):
                        bound = getattr(delegate_obj, method_name)
                        setattr(self, method_name, bound)

            cls.__init__ = __init__  # type: ignore
            _mark(cls, "delegate")
            return cls

        return decorator

    # ── @komodo.deprecated ─────────────────────────────────────────────────────

    @staticmethod
    def deprecated(
        cls: Optional[C] = None,
        *,
        reason: str = "This class is deprecated.",
        since: str = "",
    ):
        """
        Mark a class as deprecated.  A ``DeprecationWarning`` is emitted
        on every instantiation.

        Can be used with or without arguments::

            @komodo.deprecated
            class OldThing: pass

            @komodo.deprecated(reason="Use NewUser instead", since="2.0")
            class OldUser: pass
        """
        import warnings

        def _apply(klass: C) -> C:
            original_init = klass.__init__ if hasattr(klass, "__init__") else None
            since_str = f" since v{since}" if since else ""
            msg = f"{klass.__name__} is deprecated{since_str}. {reason}"

            @wraps(original_init or (lambda self: None))
            def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                if original_init:
                    original_init(self, *args, **kwargs)

            klass.__init__ = __init__  # type: ignore
            klass.__deprecated__ = msg  # type: ignore
            _mark(klass, "deprecated")
            return klass

        if cls is not None:
            # Used as @komodo.deprecated (no args)
            return _apply(cls)
        # Used as @komodo.deprecated(...) — return the decorator
        return _apply

    # ── @komodo.sealed ─────────────────────────────────────────────────────────

    @staticmethod
    def sealed(cls: C) -> C:
        """
        Prevent any subclassing of the decorated class.

        Raises ``TypeError`` when a subclass is attempted, similar to
        Java's ``sealed`` classes or Kotlin's ``final`` classes.

        Example::

            @komodo.sealed
            class Token:
                value: str

            class JwtToken(Token):  # TypeError!
                pass
        """
        original_init_subclass = cls.__init_subclass__

        @classmethod  # type: ignore
        def __init_subclass__(klass: type, **kwargs: Any) -> None:
            raise TypeError(
                f"{cls.__name__} is sealed and cannot be subclassed."
            )

        cls.__init_subclass__ = __init_subclass__  # type: ignore
        _mark(cls, "sealed")
        return cls

    # ── @komodo.mixin ───────────────────────────────────────────────────────────

    @staticmethod
    def mixin(*mixins: type) -> Callable[[C], C]:
        """
        Dynamically inject mixin classes into a class's MRO at definition time.

        Equivalent to manually listing them as bases but works as a decorator,
        useful when mixins are determined at runtime.

        Example::

            class LogMixin:
                def log(self, msg): print(f"[{self.__class__.__name__}] {msg}")

            @komodo.mixin(LogMixin)
            class Service:
                pass

            Service().log("hello")  # works!
        """
        def decorator(cls: C) -> C:
            new_bases = tuple(
                m for m in mixins if m not in cls.__mro__
            ) + cls.__bases__
            new_cls = types.new_class(
                cls.__name__,
                new_bases,
                {},
                lambda ns: ns.update(cls.__dict__),
            )
            new_cls.__qualname__ = cls.__qualname__
            new_cls.__module__ = cls.__module__
            _mark(new_cls, "mixin")
            return new_cls  # type: ignore

        return decorator


# ─────────────────────────────────────────────────────────────────────────────
#  Sentinel
# ─────────────────────────────────────────────────────────────────────────────

class _Unset:
    """Sentinel for fields that have not been set in a Builder."""
    def __repr__(self) -> str:
        return "<unset>"


_UNSET = _Unset()

# Alias copy module to avoid conflict with our copy method
import copy as copy_module


# ─────────────────────────────────────────────────────────────────────────────
#  Singleton instance
# ─────────────────────────────────────────────────────────────────────────────

komodo = _Komodo()

__all__ = ["komodo"]
