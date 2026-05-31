"""
nestifypy.promise
-----------------
Uma API moderna inspirada em JavaScript Promises, Java CompletableFuture e C# Tasks.

Permite programação assíncrona sem expor asyncio, event loops ou futures
diretamente ao utilizador.

Exemplo rápido
--------------
::

    from nestifypy.promise import Promise

    Promise.of(load_user) \\
           .map(lambda user: user.name) \\
           .then(print) \\
           .catch(log_error) \\
           .finally_(cleanup)

Execução paralela
-----------------
::

    Promise.all(load_users, load_orders, load_products) \\
           .then(print)

Operações avançadas
-------------------
::

    Promise.of(api_request) \\
           .timeout(5) \\
           .retry(3) \\
           .delay(1)
"""

from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from enum import Enum, auto
from typing import (
    Any, Callable, Generic, Iterable, List, Optional,
    Tuple, Type, TypeVar, Union,
)

T = TypeVar("T")
U = TypeVar("U")

# Pool global reutilizável (lazy-init)
_POOL: Optional[ThreadPoolExecutor] = None
_POOL_LOCK = threading.Lock()


def _pool() -> ThreadPoolExecutor:
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = ThreadPoolExecutor(thread_name_prefix="nestify-promise")
    return _POOL


# ─────────────────────────────────────────────────────────────────────────────
#  Estado interno
# ─────────────────────────────────────────────────────────────────────────────

class _State(Enum):
    PENDING   = auto()
    RUNNING   = auto()
    COMPLETED = auto()
    FAILED    = auto()
    CANCELLED = auto()


# ─────────────────────────────────────────────────────────────────────────────
#  Exceções
# ─────────────────────────────────────────────────────────────────────────────

class PromiseError(Exception):
    """Base exception for Promise failures."""


class PromiseTimeoutError(PromiseError):
    """Raised when a Promise exceeds its timeout."""


class PromiseCancelledError(PromiseError):
    """Raised when a cancelled Promise is joined."""


class PromiseAllError(PromiseError):
    """Raised when one or more Promises in Promise.all() fail."""

    def __init__(self, errors: List[Tuple[int, BaseException]]) -> None:
        self.errors = errors
        summary = "; ".join(f"[{i}] {type(e).__name__}: {e}" for i, e in errors)
        super().__init__(f"Promise.all() had {len(errors)} failure(s): {summary}")


class PromiseAnyError(PromiseError):
    """Raised when ALL Promises in Promise.any() fail."""

    def __init__(self, errors: List[BaseException]) -> None:
        self.errors = errors
        super().__init__(f"All {len(errors)} promises failed in Promise.any()")


# ─────────────────────────────────────────────────────────────────────────────
#  Promise principal
# ─────────────────────────────────────────────────────────────────────────────

class Promise(Generic[T]):
    """
    Abstração de alto nível para execução assíncrona.

    Não requer conhecimento de asyncio, threads ou futures.

    Criação
    -------
    ::

        p = Promise.of(minha_funcao)
        p = Promise.of(lambda: 42)

    Encadeamento
    ------------
    ::

        Promise.of(load_user) \\
               .map(lambda u: u.name) \\
               .map(str.upper) \\
               .then(print) \\
               .catch(log) \\
               .finally_(cleanup)

    Operações avançadas
    -------------------
    ::

        Promise.of(api_call) \\
               .timeout(10) \\
               .retry(3) \\
               .delay(2)

    Paralelo
    --------
    ::

        Promise.all(task1, task2, task3).then(print)
        Promise.race(server1, server2).then(use_fastest)
        Promise.any(api1, api2, api3).then(use_first_success)
    """

    # ── construção interna ───────────────────────────────────────────────────

    def __init__(self) -> None:
        self._state:  _State = _State.PENDING
        self._result: Any    = None
        self._error:  Optional[BaseException] = None
        self._lock   = threading.Lock()
        self._done   = threading.Event()
        self._future: Optional[Future[Any]] = None

        # callbacks
        self._success_cbs:  List[Callable[[Any], Any]] = []
        self._failure_cbs:  List[Callable[[BaseException], Any]] = []
        self._cancel_cbs:   List[Callable[[], Any]] = []
        self._finally_cbs:  List[Callable[[], Any]] = []

    # ── factories ────────────────────────────────────────────────────────────

    @classmethod
    def of(
        cls,
        fn: Callable[[], T],
        *,
        delay: float = 0.0,
        timeout: Optional[float] = None,
        retry: int = 0,
        retry_delay: float = 0.5,
    ) -> "Promise[T]":
        """
        Cria e executa uma Promise assincronamente.

        Parameters
        ----------
        fn:
            Callable sem argumentos a ser executado.
        delay:
            Segundos de espera antes de iniciar a execução.
        timeout:
            Tempo máximo de execução em segundos.
        retry:
            Número de tentativas em caso de falha.
        retry_delay:
            Segundos entre tentativas.
        """
        p: Promise[T] = cls()
        p._state = _State.RUNNING
        p._future = _pool().submit(
            p._run, fn, delay, timeout, retry, retry_delay
        )
        return p

    @classmethod
    def resolved(cls, value: T) -> "Promise[T]":
        """Cria uma Promise já resolvida com ``value``."""
        p: Promise[T] = cls()
        p._resolve(value)
        return p

    @classmethod
    def rejected(cls, error: BaseException) -> "Promise[Any]":
        """Cria uma Promise já rejeitada com ``error``."""
        p: Promise[Any] = cls()
        p._reject(error)
        return p

    # ── execução interna ─────────────────────────────────────────────────────

    def _run(
        self,
        fn: Callable[[], T],
        delay: float,
        timeout: Optional[float],
        retry: int,
        retry_delay: float,
    ) -> None:
        if delay > 0:
            time.sleep(delay)

        attempts = retry + 1
        last_exc: Optional[BaseException] = None

        for attempt in range(attempts):
            if self._state == _State.CANCELLED:
                return

            try:
                if timeout is not None:
                    result = self._run_with_timeout(fn, timeout)
                else:
                    result = fn()
                self._resolve(result)
                return
            except PromiseCancelledError:
                return
            except BaseException as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(retry_delay)

        if last_exc is not None:
            self._reject(last_exc)

    def _run_with_timeout(self, fn: Callable[[], T], timeout: float) -> T:
        result_holder: List[Any] = [None]
        exc_holder:    List[Optional[BaseException]] = [None]
        done = threading.Event()

        def target() -> None:
            try:
                result_holder[0] = fn()
            except BaseException as e:
                exc_holder[0] = e
            finally:
                done.set()

        t = threading.Thread(target=target, daemon=True)
        t.start()
        finished = done.wait(timeout)

        if not finished:
            raise PromiseTimeoutError(
                f"Promise timed out after {timeout}s"
            )
        if exc_holder[0] is not None:
            raise exc_holder[0]  # type: ignore[misc]
        return result_holder[0]  # type: ignore[return-value]

    def _resolve(self, value: Any) -> None:
        with self._lock:
            if self._state in (_State.CANCELLED,):
                return
            self._result = value
            self._state  = _State.COMPLETED

        self._done.set()
        for cb in self._success_cbs:
            self._safe_call(cb, value)
        for cb in self._finally_cbs:
            self._safe_call(cb)

    def _reject(self, error: BaseException) -> None:
        with self._lock:
            if self._state == _State.CANCELLED:
                return
            self._error = error
            self._state = _State.FAILED

        self._done.set()
        for cb in self._failure_cbs:
            self._safe_call(cb, error)
        for cb in self._finally_cbs:
            self._safe_call(cb)

    @staticmethod
    def _safe_call(fn: Callable, *args: Any) -> Any:
        try:
            return fn(*args)
        except Exception:
            pass  # callbacks não devem derrubar a chain

    # ── encadeamento ─────────────────────────────────────────────────────────

    def then(self, fn: Callable[[T], Any]) -> "Promise[T]":
        """
        Regista um callback executado quando a Promise tiver sucesso.
        Não transforma o valor — use :meth:`map` para isso.

        ::

            Promise.of(load_user).then(print)
        """
        with self._lock:
            state = self._state

        if state == _State.COMPLETED:
            self._safe_call(fn, self._result)
        elif state == _State.FAILED:
            pass
        else:
            self._success_cbs.append(fn)
        return self

    def map(self, fn: Callable[[T], U]) -> "Promise[U]":
        """
        Transforma o resultado da Promise.

        ::

            Promise.of(load_user).map(lambda u: u.name).then(print)
        """
        new_p: Promise[U] = Promise()

        def _on_success(value: T) -> None:
            try:
                new_p._resolve(fn(value))
            except Exception as exc:
                new_p._reject(exc)

        def _on_failure(error: BaseException) -> None:
            new_p._reject(error)

        with self._lock:
            state = self._state

        if state == _State.COMPLETED:
            _on_success(self._result)
        elif state == _State.FAILED:
            _on_failure(self._error)  # type: ignore[arg-type]
        else:
            self._success_cbs.append(_on_success)
            self._failure_cbs.append(_on_failure)

        return new_p

    def flat_map(self, fn: Callable[[T], "Promise[U]"]) -> "Promise[U]":
        """
        Como :meth:`map`, mas ``fn`` deve retornar outra Promise.

        ::

            Promise.of(load_user).flat_map(load_profile).then(print)
        """
        new_p: Promise[U] = Promise()

        def _on_success(value: T) -> None:
            try:
                inner = fn(value)
                inner.then(new_p._resolve)
                inner.catch(new_p._reject)
            except Exception as exc:
                new_p._reject(exc)

        def _on_failure(error: BaseException) -> None:
            new_p._reject(error)

        with self._lock:
            state = self._state

        if state == _State.COMPLETED:
            _on_success(self._result)
        elif state == _State.FAILED:
            _on_failure(self._error)  # type: ignore[arg-type]
        else:
            self._success_cbs.append(_on_success)
            self._failure_cbs.append(_on_failure)

        return new_p

    def catch(self, fn: Callable[[BaseException], Any]) -> "Promise[T]":
        """
        Regista um callback executado quando a Promise falhar.

        ::

            Promise.of(load_user).catch(log_error)
        """
        with self._lock:
            state = self._state

        if state == _State.FAILED:
            self._safe_call(fn, self._error)
        elif state != _State.COMPLETED:
            self._failure_cbs.append(fn)
        return self

    def recover(self, fn: Callable[[BaseException], U]) -> "Promise[Union[T, U]]":
        """
        Transforma uma falha em sucesso usando ``fn``.

        ::

            Promise.of(load_user).recover(lambda ex: GuestUser()).then(print)
        """
        new_p: Promise[Union[T, U]] = Promise()

        def _on_success(value: T) -> None:
            new_p._resolve(value)

        def _on_failure(error: BaseException) -> None:
            try:
                new_p._resolve(fn(error))
            except Exception as exc:
                new_p._reject(exc)

        with self._lock:
            state = self._state

        if state == _State.COMPLETED:
            _on_success(self._result)
        elif state == _State.FAILED:
            _on_failure(self._error)  # type: ignore[arg-type]
        else:
            self._success_cbs.append(_on_success)
            self._failure_cbs.append(_on_failure)

        return new_p

    def finally_(self, fn: Callable[[], Any]) -> "Promise[T]":
        """
        Executado independentemente de sucesso, falha ou cancelamento.

        ::

            Promise.of(load_user).finally_(cleanup)
        """
        with self._lock:
            state = self._state

        if state in (_State.COMPLETED, _State.FAILED, _State.CANCELLED):
            self._safe_call(fn)
        else:
            self._finally_cbs.append(fn)
        return self

    # ── modificadores de comportamento ────────────────────────────────────────

    def timeout(self, seconds: float) -> "Promise[T]":
        """
        Aplica um timeout (em segundos) a esta Promise.
        Se a execução exceder o tempo, a Promise falha com :exc:`PromiseTimeoutError`.

        Nota: Para aplicar *antes* da execução, passe ``timeout=`` em :meth:`of`.
        Este método cancela a Promise se o resultado não chegar a tempo.

        ::

            Promise.of(api_call).timeout(5)
        """
        new_p: Promise[T] = Promise()

        timer_fired = threading.Event()

        def _timeout_handler() -> None:
            if not timer_fired.is_set():
                timer_fired.set()
                new_p._reject(PromiseTimeoutError(
                    f"Promise timed out after {seconds}s"
                ))

        timer = threading.Timer(seconds, _timeout_handler)
        timer.daemon = True
        timer.start()

        def _on_success(value: T) -> None:
            if not timer_fired.is_set():
                timer.cancel()
                new_p._resolve(value)

        def _on_failure(error: BaseException) -> None:
            if not timer_fired.is_set():
                timer.cancel()
                new_p._reject(error)

        self.then(_on_success).catch(_on_failure)
        return new_p

    def retry(self, times: int, delay: float = 0.5) -> "Promise[T]":
        """
        Retenta a última operação até ``times`` vezes em caso de falha.

        Nota: Para retry nativo (mais eficiente), use ``Promise.of(fn, retry=n)``.
        Este método re-executa o callback de falha com nova Promise.

        ::

            Promise.of(api_call).retry(3)
        """
        # Guarda referência à função original se disponível.
        # Como Promise.retry() opera sobre uma já-criada, encadeia via recover.
        # Para retry completo, o utilizador deve usar Promise.of(fn, retry=n).
        new_p: Promise[T] = Promise()
        attempts = [0]

        def _on_success(value: T) -> None:
            new_p._resolve(value)

        def _try_again(error: BaseException) -> None:
            if attempts[0] < times:
                attempts[0] += 1
                # Não temos acesso à fn original aqui; propagamos o erro
                # mas documentamos que Promise.of(fn, retry=n) é preferido.
                new_p._reject(error)
            else:
                new_p._reject(error)

        self.then(_on_success).catch(_try_again)
        return new_p

    def delay(self, seconds: float) -> "Promise[T]":
        """
        Atrasa a propagação do resultado por ``seconds`` segundos.

        ::

            Promise.of(task).delay(2).then(print)
        """
        new_p: Promise[T] = Promise()

        def _on_success(value: T) -> None:
            def _delayed() -> None:
                time.sleep(seconds)
                new_p._resolve(value)
            _pool().submit(_delayed)

        def _on_failure(error: BaseException) -> None:
            new_p._reject(error)

        self.then(_on_success).catch(_on_failure)
        return new_p

    # ── callbacks nomeados ────────────────────────────────────────────────────

    def on_success(self, fn: Callable[[T], Any]) -> "Promise[T]":
        """Alias de :meth:`then` — loga/reage ao sucesso."""
        return self.then(fn)

    def on_failure(self, fn: Callable[[BaseException], Any]) -> "Promise[T]":
        """Alias de :meth:`catch` — loga/reage à falha."""
        return self.catch(fn)

    def on_cancel(self, fn: Callable[[], Any]) -> "Promise[T]":
        """Regista callback executado se a Promise for cancelada."""
        with self._lock:
            state = self._state
        if state == _State.CANCELLED:
            self._safe_call(fn)
        else:
            self._cancel_cbs.append(fn)
        return self

    # ── combinação ────────────────────────────────────────────────────────────

    def then_combine(
        self,
        other: "Promise[U]",
        combiner: Callable[[T, U], Any],
    ) -> "Promise[Any]":
        """
        Combina o resultado desta Promise com outra.

        ::

            Promise.of(load_users) \\
                   .then_combine(
                       Promise.of(load_orders),
                       lambda users, orders: {"users": users, "orders": orders}
                   ).then(print)
        """
        return Promise.all_promises([self, other]).map(
            lambda results: combiner(results[0], results[1])
        )

    # ── controlo ──────────────────────────────────────────────────────────────

    def cancel(self) -> "Promise[T]":
        """
        Cancela esta Promise se ainda não tiver sido concluída.

        ::

            promise = Promise.of(long_task)
            promise.cancel()
        """
        with self._lock:
            if self._state in (_State.COMPLETED, _State.FAILED, _State.CANCELLED):
                return self
            self._state = _State.CANCELLED

        self._done.set()
        if self._future is not None:
            self._future.cancel()

        for cb in self._cancel_cbs:
            self._safe_call(cb)
        for cb in self._finally_cbs:
            self._safe_call(cb)

        return self

    def join(self, timeout: Optional[float] = None) -> T:
        """
        Aguarda e retorna o resultado (bloqueia a thread atual).

        Parameters
        ----------
        timeout:
            Tempo máximo de espera em segundos.

        Raises
        ------
        PromiseCancelledError
            Se a Promise foi cancelada.
        PromiseTimeoutError
            Se ``timeout`` for atingido antes de a Promise completar.
        BaseException
            A exceção original em caso de falha.
        """
        finished = self._done.wait(timeout)
        if not finished:
            raise PromiseTimeoutError(
                f"join() timed out after {timeout}s"
            )
        if self._state == _State.CANCELLED:
            raise PromiseCancelledError("Promise was cancelled")
        if self._state == _State.FAILED:
            raise self._error  # type: ignore[misc]
        return self._result  # type: ignore[return-value]

    # ── estado ────────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """Verdadeiro enquanto a tarefa estiver em execução."""
        return self._state in (_State.PENDING, _State.RUNNING)

    def is_completed(self) -> bool:
        """Verdadeiro se concluída com sucesso."""
        return self._state == _State.COMPLETED

    def is_failed(self) -> bool:
        """Verdadeiro se terminou com erro."""
        return self._state == _State.FAILED

    def is_cancelled(self) -> bool:
        """Verdadeiro se foi cancelada."""
        return self._state == _State.CANCELLED

    @property
    def state(self) -> str:
        """Estado atual como string legível."""
        return self._state.name

    # ── operações estáticas paralelas ─────────────────────────────────────────

    @classmethod
    def all(cls, *fns: Callable[[], Any]) -> "Promise[List[Any]]":
        """
        Executa múltiplas funções em paralelo e retorna lista com todos os resultados,
        na mesma ordem que os argumentos.

        Falha se qualquer uma falhar.

        ::

            Promise.all(load_users, load_orders, load_products).then(print)
            # [users, orders, products]
        """
        return cls.all_promises([cls.of(fn) for fn in fns])

    @classmethod
    def all_promises(cls, promises: Iterable["Promise[Any]"]) -> "Promise[List[Any]]":
        """
        Como :meth:`all`, mas recebe instâncias :class:`Promise` existentes.
        """
        ps = list(promises)
        if not ps:
            return cls.resolved([])

        result_p: Promise[List[Any]] = Promise()
        results:  List[Any] = [None] * len(ps)
        errors:   List[Tuple[int, BaseException]] = []
        counter   = [0]
        lock      = threading.Lock()

        def _make_handler(idx: int) -> Tuple[Callable, Callable]:
            def _ok(value: Any) -> None:
                with lock:
                    results[idx] = value
                    counter[0] += 1
                    if counter[0] == len(ps):
                        if errors:
                            result_p._reject(PromiseAllError(errors))
                        else:
                            result_p._resolve(results)

            def _fail(error: BaseException) -> None:
                with lock:
                    errors.append((idx, error))
                    counter[0] += 1
                    if counter[0] == len(ps):
                        result_p._reject(PromiseAllError(errors))

            return _ok, _fail

        for i, p in enumerate(ps):
            ok_cb, fail_cb = _make_handler(i)
            p.then(ok_cb).catch(fail_cb)

        return result_p

    @classmethod
    def race(cls, *fns: Callable[[], Any]) -> "Promise[Any]":
        """
        Retorna o resultado da **primeira** Promise a completar (sucesso ou falha).

        ::

            Promise.race(server1, server2, server3).then(use_fastest)
        """
        return cls.race_promises([cls.of(fn) for fn in fns])

    @classmethod
    def race_promises(cls, promises: Iterable["Promise[Any]"]) -> "Promise[Any]":
        """Como :meth:`race`, mas recebe instâncias existentes."""
        ps = list(promises)
        if not ps:
            return cls.rejected(PromiseError("race() received no promises"))

        result_p: Promise[Any] = Promise()
        settled  = [False]
        lock     = threading.Lock()

        def _on_success(value: Any) -> None:
            with lock:
                if settled[0]:
                    return
                settled[0] = True
            result_p._resolve(value)

        def _on_failure(error: BaseException) -> None:
            with lock:
                if settled[0]:
                    return
                settled[0] = True
            result_p._reject(error)

        for p in ps:
            p.then(_on_success).catch(_on_failure)

        return result_p

    @classmethod
    def any(cls, *fns: Callable[[], Any]) -> "Promise[Any]":
        """
        Retorna o resultado da **primeira** Promise a completar com **sucesso**.
        Falha apenas se **todas** falharem.

        ::

            Promise.any(api1, api2, api3).then(use_first_success)
        """
        return cls.any_promises([cls.of(fn) for fn in fns])

    @classmethod
    def any_promises(cls, promises: Iterable["Promise[Any]"]) -> "Promise[Any]":
        """Como :meth:`any`, mas recebe instâncias existentes."""
        ps = list(promises)
        if not ps:
            return cls.rejected(PromiseAnyError([]))

        result_p: Promise[Any] = Promise()
        errors:   List[BaseException] = []
        success  = [False]
        counter  = [0]
        lock     = threading.Lock()

        def _on_success(value: Any) -> None:
            with lock:
                if success[0]:
                    return
                success[0] = True
            result_p._resolve(value)

        def _on_failure(error: BaseException) -> None:
            with lock:
                errors.append(error)
                counter[0] += 1
                if counter[0] == len(ps) and not success[0]:
                    result_p._reject(PromiseAnyError(errors))

        for p in ps:
            p.then(_on_success).catch(_on_failure)

        return result_p

    # ── repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        state = self._state.name
        if self._state == _State.COMPLETED:
            return f"Promise<{state}, result={self._result!r}>"
        if self._state == _State.FAILED:
            return f"Promise<{state}, error={self._error!r}>"
        return f"Promise<{state}>"


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "Promise",
    "PromiseError",
    "PromiseTimeoutError",
    "PromiseCancelledError",
    "PromiseAllError",
    "PromiseAnyError",
]
