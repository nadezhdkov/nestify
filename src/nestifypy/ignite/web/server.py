"""
nestifypy.ignite.web.server
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Auto-configures and runs the web server by scanning all registered
@Controller beans and wiring their @Get/@Post/… methods as routes.

Currently uses FastAPI + uvicorn when available.
Install the web starter with::

    pip install nestifypy-ignite[web]
    # which pulls in: fastapi uvicorn[standard]
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nestifypy.ignite.core.context import ApplicationContext


class WebServer:
    """
    Scans the container for @Controller beans, discovers their route methods,
    and mounts them on a FastAPI application.
    """

    def __init__(self, context: "ApplicationContext"):
        self._context = context
        self._app = None

    def build(self):
        try:
            from fastapi import FastAPI
        except ImportError:
            raise ImportError(
                "FastAPI is required for the web starter.\n"
                "Install it with: pip install fastapi uvicorn[standard]"
            )

        from nestifypy.ignite.decorators.controller import _CONTROLLER_REGISTRY

        app = FastAPI()

        for cls, base_path in _CONTROLLER_REGISTRY.items():
            if not self._context.container.has(cls):
                continue
            instance = self._context.get_bean(cls)
            self._mount_routes(app, instance, base_path)

        self._app = app
        return app

    def _mount_routes(self, app, instance, base_path: str):
        from fastapi import APIRouter

        router = APIRouter(prefix=base_path.rstrip("/"))

        for name in dir(instance):
            method = getattr(instance, name, None)
            if not callable(method):
                continue
            if not getattr(method, "__nestifypy_route__", False):
                continue

            http_method: str = method.__nestifypy_http_method__
            http_path: str = method.__nestifypy_http_path__

            # Wrap bound method so FastAPI can introspect its signature
            handler = _make_handler(method)

            router.add_api_route(
                http_path,
                handler,
                methods=[http_method],
                name=f"{type(instance).__name__}.{name}",
            )

        app.include_router(router)

    async def run(self):
        if self._app is None:
            self.build()

        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "uvicorn is required to run the web server.\n"
                "Install it with: pip install uvicorn[standard]"
            )

        props = self._context.properties
        host = props.get_str("server.host", "0.0.0.0")
        port = props.get_int("server.port", 8080)
        reload = props.get_bool("server.reload", False)

        config = uvicorn.Config(self._app, host=host, port=port, reload=reload)
        server = uvicorn.Server(config)
        await server.serve()

    @property
    def app(self):
        """Expose the underlying FastAPI app (e.g. for testing with TestClient)."""
        if self._app is None:
            self.build()
        return self._app


def _make_handler(bound_method):
    """
    Wraps a bound controller method into a plain async function that FastAPI
    can register as a route handler, preserving the original signature.
    """
    import functools

    if inspect.iscoroutinefunction(bound_method):
        @functools.wraps(bound_method)
        async def async_handler(*args, **kwargs):
            return await bound_method(*args, **kwargs)
        return async_handler
    else:
        @functools.wraps(bound_method)
        def sync_handler(*args, **kwargs):
            return bound_method(*args, **kwargs)
        return sync_handler
