"""
nestifypy.json.exceptions
-------------------------
Custom exceptions for the JSON module.
"""
from nestifypy.slogger import ConfigError


class JsonError(ConfigError):
    """Base exception for all JSON-related errors."""
    pass


class JsonParseError(JsonError):
    """Raised when JSON parsing or type coercion fails."""
    pass


class JsonValidationError(JsonError):
    """Raised when schema or field-level validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors: list[str] = errors or []


class JsonSerializationError(JsonError):
    """Raised when a Python object cannot be serialised to JSON."""
    pass


class JsonMappingError(JsonError):
    """Raised when ``from_dict`` / ``from_json`` cannot map data to a class."""
    pass


__all__ = [
    "JsonError",
    "JsonParseError",
    "JsonValidationError",
    "JsonSerializationError",
    "JsonMappingError",
]
