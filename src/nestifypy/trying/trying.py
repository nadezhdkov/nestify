"""
nestifypy.trying
----------------
Try – Tratamento funcional de erros para o Nestifypy.

Elimina blocos try/except espalhados pelo código através de uma API
fluente, encadeável e inspirada em Java/Kotlin/Rust.

Exemplo rápido
--------------
::

    from nestifypy.trying import Try

    Try.of(load_user) \\
       .filter(lambda user: user.active, "Inactive user") \\
       .map(lambda user: user.name) \\
       .recover(lambda ex: "Guest") \\
       .on_success(print) \\
       .on_failure(log_error)

Comparação com Python tradicional
----------------------------------

Antes::

    try:
        user = load_user()
        if not user.active:
            raise Exception("Inactive")
        print(user.name)
    except Exception:
        print("Guest")

Depois::

    Try.of(load_user) \\
       .filter(lambda u: u.active, "Inactive") \\
       .map(lambda u: u.name) \\
       .recover(lambda ex: "Guest") \\
       .on_success(print)
"""

from __future__ import annotations

import traceback
from typing import (
    Any, Callable, Generic, Iterator, List, Optional,
    Tuple, Type, TypeVar, Union,
)

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E", bound=BaseException)

# ─────────────────────────────────────────────────────────────────────────────
#  Excepções
# ─────────────────────────────────────────────────────────────────────────────

class TryError(Exception):
    """Base exception for Try failures."""


class FilterError(TryError):
    """Raised when a .filter() predicate fails."""

    def __init__(self, message: str = "Filter predicate not satisfied") -> None:
        super().__init__(message)
        self.message = message


class EmptyValueError(TryError):
    """Raised by .get() on a Failure when no default is given."""


# ─────────────────────────────────────────────────────────────────────────────
#  Try base + Success / Failure
# ─────────────────────────────────────────────────────────────────────────────

class Try(Generic[T]):
    """
    Representa o resultado de uma operação que pode ter sucesso ou falhar.

    Nunca instancie diretamente — use :meth:`Try.of` ou :meth:`Try.success` /
    :meth:`Try.failure`.

    Dois estados internos
    ---------------------
    * ``Success(value)`` — operação bem-sucedida.
    * ``Failure(error)`` — operação falhou.

    Todos os métodos de encadeamento nunca lançam exceções — erros são
    capturados e convertidos em ``Failure``.
    """

    # ── factories ─────────────────────────────────────────────────────────────

    @classmethod
    def of(cls, fn: Callable[[], T]) -> "Try[T]":
        """
        Executa ``fn`` e encapsula o resultado num Try.

        ::

            Try.of(load_user)
            Try.of(lambda: int("42"))
            Try.of(lambda: risky_operation())
        """
        try:
            return Success(fn())
        except BaseException as exc:
            return Failure(exc)

    @classmethod
    def success(cls, value: T) -> "Try[T]":
        """Cria um Try já bem-sucedido com ``value``."""
        return Success(value)

    @classmethod
    def failure(cls, error: BaseException) -> "Try[Any]":
        """Cria um Try já falhado com ``error``."""
        return Failure(error)

    @classmethod
    def of_nullable(cls, value: Optional[T], message: str = "Value is None") -> "Try[T]":
        """
        Encapsula um valor que pode ser None.
        Se for None, cria um Failure com ``message``.

        ::

            Try.of_nullable(user_or_none, "User not found")
               .map(lambda u: u.name)
               .or_else("Unknown")
        """
        if value is None:
            return Failure(EmptyValueError(message))
        return Success(value)

    # ── estado ────────────────────────────────────────────────────────────────

    def is_success(self) -> bool:
        """Verdadeiro se a operação foi bem-sucedida."""
        raise NotImplementedError

    def is_failure(self) -> bool:
        """Verdadeiro se a operação falhou."""
        return not self.is_success()

    # aliases semânticos para a spec
    def success_state(self) -> bool:
        return self.is_success()

    def failure_state(self) -> bool:
        return self.is_failure()

    # ── obtenção de valor ─────────────────────────────────────────────────────

    def get(self) -> T:
        """
        Retorna o valor ou lança a exceção original.

        ::

            value = Try.of(load_user).get()
        """
        raise NotImplementedError

    def get_or_none(self) -> Optional[T]:
        """
        Retorna o valor ou ``None`` em caso de falha.

        ::

            user = Try.of(load_user).get_or_none()
        """
        raise NotImplementedError

    def get_or_default(self, default: U) -> Union[T, U]:
        """
        Retorna o valor ou ``default`` em caso de falha.

        ::

            name = Try.of(load_user).map(lambda u: u.name).get_or_default("Guest")
        """
        raise NotImplementedError

    def or_else(self, default: U) -> Union[T, U]:
        """
        Alias de :meth:`get_or_default` — mais fluente no final de cadeias.

        ::

            name = (
                Try.of(load_user)
                   .map(lambda u: u.name)
                   .or_else("Guest")
            )
        """
        return self.get_or_default(default)

    def get_error(self) -> Optional[BaseException]:
        """
        Retorna a exceção capturada ou ``None`` se bem-sucedido.

        ::

            err = Try.of(risky).get_error()
            if err: print(type(err).__name__)
        """
        raise NotImplementedError

    # ── transformação ─────────────────────────────────────────────────────────

    def map(self, fn: Callable[[T], U]) -> "Try[U]":
        """
        Transforma o valor se for Success. Em Failure, é ignorado.

        ::

            Try.of(load_user).map(lambda u: u.name).map(str.upper)
        """
        raise NotImplementedError

    def flat_map(self, fn: Callable[[T], "Try[U]"]) -> "Try[U]":
        """
        Como :meth:`map`, mas ``fn`` deve retornar outro Try.
        Permite encadeamento de operações que também podem falhar.

        ::

            Try.of(load_user).flat_map(lambda u: Try.of(lambda: load_profile(u)))
        """
        raise NotImplementedError

    def map_error(self, fn: Callable[[BaseException], BaseException]) -> "Try[T]":
        """
        Transforma a exceção se for Failure. Em Success, é ignorado.
        Útil para normalizar tipos de erro.

        ::

            Try.of(db_query) \\
               .map_error(lambda e: DatabaseError(str(e)))
        """
        raise NotImplementedError

    # ── filtragem ─────────────────────────────────────────────────────────────

    def filter(
        self,
        predicate: Callable[[T], bool],
        message: str = "Filter predicate not satisfied",
    ) -> "Try[T]":
        """
        Transforma Success em Failure se o predicado não for satisfeito.
        Failure passa sem alteração.

        ::

            Try.of(load_user) \\
               .filter(lambda u: u.active, "Inactive user") \\
               .filter(lambda u: u.age >= 18, "User must be 18+")
        """
        raise NotImplementedError

    def filter_not(
        self,
        predicate: Callable[[T], bool],
        message: str = "Inverse filter predicate not satisfied",
    ) -> "Try[T]":
        """
        Inverso de :meth:`filter` — falha se o predicado for True.

        ::

            Try.of(load_user).filter_not(lambda u: u.banned, "User is banned")
        """
        return self.filter(lambda v: not predicate(v), message)

    # ── recuperação ───────────────────────────────────────────────────────────

    def recover(self, fn: Callable[[BaseException], U]) -> "Try[Union[T, U]]":
        """
        Transforma um Failure em Success usando ``fn``.
        Se ``fn`` lançar exceção, o resultado é um novo Failure.

        ::

            Try.of(load_user).recover(lambda ex: GuestUser())
        """
        raise NotImplementedError

    def recover_with(self, fn: Callable[[BaseException], "Try[U]"]) -> "Try[Union[T, U]]":
        """
        Como :meth:`recover`, mas ``fn`` deve retornar outro Try.

        ::

            Try.of(load_user) \\
               .recover_with(lambda ex: Try.of(load_cached_user))
        """
        raise NotImplementedError

    def recover_if(
        self,
        exc_type: Type[E],
        fn: Callable[[E], U],
    ) -> "Try[Union[T, U]]":
        """
        Recupera apenas se a exceção for do tipo ``exc_type``.
        Outros tipos de erro passam sem alteração.

        ::

            Try.of(load_user) \\
               .recover_if(ConnectionError, lambda e: load_cached_user())
        """
        raise NotImplementedError

    # ── captura seletiva ──────────────────────────────────────────────────────

    def catch(
        self,
        exc_type: Type[E],
        handler: Callable[[E], Any],
    ) -> "Try[T]":
        """
        Executa ``handler`` se a exceção for do tipo ``exc_type``.
        Não muda o estado do Try — use :meth:`recover` para transformar.

        ::

            Try.of(load_user) \\
               .catch(ValueError, lambda e: log.warn(str(e))) \\
               .catch(FileNotFoundError, lambda e: log.error(str(e)))
        """
        raise NotImplementedError

    # ── callbacks ─────────────────────────────────────────────────────────────

    def on_success(self, fn: Callable[[T], Any]) -> "Try[T]":
        """
        Executa ``fn`` com o valor se for Success. Retorna self (para continuar a cadeia).

        ::

            Try.of(load_user).on_success(print)
        """
        raise NotImplementedError

    def on_failure(self, fn: Callable[[BaseException], Any]) -> "Try[T]":
        """
        Executa ``fn`` com a exceção se for Failure. Retorna self.

        ::

            Try.of(load_user).on_failure(log_error)
        """
        raise NotImplementedError

    def on_complete(self, fn: Callable[["Try[T]"], Any]) -> "Try[T]":
        """
        Sempre executado — recebe o Try inteiro (Success ou Failure).

        ::

            Try.of(load_user).on_complete(lambda t: print("done, ok=", t.is_success()))
        """
        raise NotImplementedError

    def tap(self, fn: Callable[[T], Any]) -> "Try[T]":
        """
        Alias de :meth:`on_success` — executa side-effect e retorna self sem alterar valor.
        Útil para logging no meio de uma cadeia.

        ::

            Try.of(load_user) \\
               .tap(lambda u: log.debug("loaded:", u.id)) \\
               .map(lambda u: u.name)
        """
        return self.on_success(fn)

    # ── conversão ─────────────────────────────────────────────────────────────

    def to_optional(self) -> Optional[T]:
        """
        Converte para Optional — retorna o valor ou None.

        ::

            user: Optional[User] = Try.of(load_user).to_optional()
        """
        return self.get_or_none()

    def to_list(self) -> List[T]:
        """
        Converte para lista com um elemento (Success) ou lista vazia (Failure).

        ::

            items = Try.of(load_user).to_list()  # [user] ou []
        """
        raise NotImplementedError

    def to_promise(self) -> Any:
        """
        Converte para Promise (requer nestifypy.promise).

        ::

            promise = Try.of(load_user).to_promise()
        """
        try:
            from nestifypy.promise import Promise  # type: ignore[import]
        except ImportError:
            try:
                import sys, os
                sys.path.insert(0, os.path.dirname(__file__))
                from promise import Promise  # type: ignore[import]
            except ImportError:
                raise ImportError(
                    "nestifypy.promise não encontrado. "
                    "Instale nestifypy-promise ou coloque promise.py no mesmo diretório."
                )
        if self.is_success():
            return Promise.resolved(self.get())
        return Promise.rejected(self.get_error())  # type: ignore[arg-type]

    # ── iteração ──────────────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[T]:
        """
        Permite usar Try num for-loop — itera 0 ou 1 vezes.

        ::

            for user in Try.of(load_user):
                print(user.name)
        """
        return iter(self.to_list())

    # ── repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        raise NotImplementedError

    def __bool__(self) -> bool:
        """Try é truthy se for Success."""
        return self.is_success()


# ─────────────────────────────────────────────────────────────────────────────
#  Success
# ─────────────────────────────────────────────────────────────────────────────

class Success(Try[T]):
    """Subclasse interna que representa uma operação bem-sucedida."""

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        self._value = value

    # ── estado ────────────────────────────────────────────────────────────────

    def is_success(self) -> bool:
        return True

    # ── obtenção ──────────────────────────────────────────────────────────────

    def get(self) -> T:
        return self._value

    def get_or_none(self) -> Optional[T]:
        return self._value

    def get_or_default(self, default: Any) -> T:
        return self._value

    def get_error(self) -> None:
        return None

    # ── transformação ─────────────────────────────────────────────────────────

    def map(self, fn: Callable[[T], U]) -> "Try[U]":
        try:
            return Success(fn(self._value))
        except BaseException as exc:
            return Failure(exc)

    def flat_map(self, fn: Callable[[T], "Try[U]"]) -> "Try[U]":
        try:
            result = fn(self._value)
            if not isinstance(result, Try):
                return Success(result)  # type: ignore[arg-type]
            return result
        except BaseException as exc:
            return Failure(exc)

    def map_error(self, fn: Callable[[BaseException], BaseException]) -> "Try[T]":
        return self  # nada a transformar num Success

    # ── filtragem ─────────────────────────────────────────────────────────────

    def filter(self, predicate: Callable[[T], bool], message: str = "Filter predicate not satisfied") -> "Try[T]":
        try:
            if predicate(self._value):
                return self
            return Failure(FilterError(message))
        except BaseException as exc:
            return Failure(exc)

    # ── recuperação ───────────────────────────────────────────────────────────

    def recover(self, fn: Callable[[BaseException], Any]) -> "Try[T]":
        return self  # nada a recuperar num Success

    def recover_with(self, fn: Callable[[BaseException], "Try[Any]"]) -> "Try[T]":
        return self

    def recover_if(self, exc_type: Type[Any], fn: Callable[[Any], Any]) -> "Try[T]":
        return self

    # ── captura seletiva ──────────────────────────────────────────────────────

    def catch(self, exc_type: Type[Any], handler: Callable[[Any], Any]) -> "Try[T]":
        return self  # nada a capturar num Success

    # ── callbacks ─────────────────────────────────────────────────────────────

    def on_success(self, fn: Callable[[T], Any]) -> "Try[T]":
        try:
            fn(self._value)
        except Exception:
            pass
        return self

    def on_failure(self, fn: Callable[[BaseException], Any]) -> "Try[T]":
        return self  # não falhou

    def on_complete(self, fn: Callable[["Try[T]"], Any]) -> "Try[T]":
        try:
            fn(self)
        except Exception:
            pass
        return self

    # ── conversão ─────────────────────────────────────────────────────────────

    def to_list(self) -> List[T]:
        return [self._value]

    # ── repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Success({self._value!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Success) and other._value == self._value

    def __hash__(self) -> int:
        try:
            return hash(("Success", self._value))
        except TypeError:
            return hash(("Success", id(self._value)))


# ─────────────────────────────────────────────────────────────────────────────
#  Failure
# ─────────────────────────────────────────────────────────────────────────────

class Failure(Try[T]):
    """Subclasse interna que representa uma operação falhada."""

    __slots__ = ("_error", "_traceback")

    def __init__(self, error: BaseException) -> None:
        self._error = error
        # Captura o traceback no momento da criação, se disponível
        self._traceback: Optional[str] = traceback.format_exc() if traceback.format_exc().strip() != "NoneType: None" else None

    # ── estado ────────────────────────────────────────────────────────────────

    def is_success(self) -> bool:
        return False

    # ── obtenção ──────────────────────────────────────────────────────────────

    def get(self) -> T:
        raise self._error

    def get_or_none(self) -> None:
        return None

    def get_or_default(self, default: U) -> U:
        return default

    def get_error(self) -> BaseException:
        return self._error

    def get_traceback(self) -> Optional[str]:
        """Retorna o traceback capturado no momento da falha, se disponível."""
        return self._traceback

    # ── transformação ─────────────────────────────────────────────────────────

    def map(self, fn: Callable[[T], U]) -> "Try[U]":
        return self  # type: ignore[return-value]  # nada a transformar numa falha

    def flat_map(self, fn: Callable[[T], "Try[U]"]) -> "Try[U]":
        return self  # type: ignore[return-value]

    def map_error(self, fn: Callable[[BaseException], BaseException]) -> "Try[T]":
        try:
            return Failure(fn(self._error))
        except BaseException as exc:
            return Failure(exc)

    # ── filtragem ─────────────────────────────────────────────────────────────

    def filter(self, predicate: Callable[[T], bool], message: str = "Filter predicate not satisfied") -> "Try[T]":
        return self  # Failure passa sem alteração

    # ── recuperação ───────────────────────────────────────────────────────────

    def recover(self, fn: Callable[[BaseException], U]) -> "Try[Union[T, U]]":
        try:
            return Success(fn(self._error))
        except BaseException as exc:
            return Failure(exc)

    def recover_with(self, fn: Callable[[BaseException], "Try[U]"]) -> "Try[Union[T, U]]":
        try:
            result = fn(self._error)
            if not isinstance(result, Try):
                return Success(result)  # type: ignore[arg-type]
            return result
        except BaseException as exc:
            return Failure(exc)

    def recover_if(
        self,
        exc_type: Type[E],
        fn: Callable[[E], U],
    ) -> "Try[Union[T, U]]":
        if isinstance(self._error, exc_type):
            try:
                return Success(fn(self._error))  # type: ignore[arg-type]
            except BaseException as exc:
                return Failure(exc)
        return self  # tipo diferente — não recupera

    # ── captura seletiva ──────────────────────────────────────────────────────

    def catch(
        self,
        exc_type: Type[E],
        handler: Callable[[E], Any],
    ) -> "Try[T]":
        if isinstance(self._error, exc_type):
            try:
                handler(self._error)  # type: ignore[arg-type]
            except Exception:
                pass
        return self

    # ── callbacks ─────────────────────────────────────────────────────────────

    def on_success(self, fn: Callable[[T], Any]) -> "Try[T]":
        return self  # não teve sucesso

    def on_failure(self, fn: Callable[[BaseException], Any]) -> "Try[T]":
        try:
            fn(self._error)
        except Exception:
            pass
        return self

    def on_complete(self, fn: Callable[["Try[T]"], Any]) -> "Try[T]":
        try:
            fn(self)
        except Exception:
            pass
        return self

    # ── conversão ─────────────────────────────────────────────────────────────

    def to_list(self) -> List[T]:
        return []

    # ── repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Failure({self._error!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Failure)
            and type(other._error) is type(self._error)
            and str(other._error) == str(self._error)
        )

    def __hash__(self) -> int:
        return hash(("Failure", type(self._error).__name__, str(self._error)))


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "Try",
    "Success",
    "Failure",
    "TryError",
    "FilterError",
    "EmptyValueError",
]
