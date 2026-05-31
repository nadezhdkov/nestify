"""
nestifypy.input.exceptions — Custom exception hierarchy for nestifypy.input.
"""


class InputError(Exception):
    """Base exception for all nestifypy.input errors."""


class InputValidationError(InputError):
    """
    Raised when the user's input fails a validation rule.

    Attributes:
        message: Human-readable description of the failure.
        raw_value: The raw string value that was entered.
        field: Optional label/prompt that was shown to the user.
    """

    def __init__(self, message: str, raw_value: str = "", field: str = "") -> None:
        self.raw_value = raw_value
        self.field = field
        super().__init__(message)


class InputCancelledError(InputError):
    """
    Raised when the user interrupts the prompt (Ctrl+C / Ctrl+D / EOF).
    """

    def __init__(self, prompt: str = "") -> None:
        self.prompt = prompt
        super().__init__(f"Input cancelled by user{f' at prompt: {prompt!r}' if prompt else ''}.")


class InputTimeoutError(InputError):
    """
    Raised when `ask(...).timeout(n)` expires before the user submits input.

    Attributes:
        seconds: How many seconds the prompt waited.
    """

    def __init__(self, seconds: float, prompt: str = "") -> None:
        self.seconds = seconds
        self.prompt = prompt
        super().__init__(
            f"Input timed out after {seconds}s{f' at prompt: {prompt!r}' if prompt else ''}."
        )


class InputConversionError(InputValidationError):
    """
    Raised when type-conversion of a raw string value fails.

    Attributes:
        target_type: The Python type that conversion was attempted to.
    """

    def __init__(self, raw_value: str, target_type: type, field: str = "") -> None:
        self.target_type = target_type
        super().__init__(
            f"Cannot convert {raw_value!r} to {target_type.__name__}.",
            raw_value=raw_value,
            field=field,
        )
