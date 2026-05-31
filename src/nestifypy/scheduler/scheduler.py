"""
nestifypy.scheduler
--------------------
Scheduler – Sistema de agendamento de tarefas para o Nestifypy.

API fluente para execução única, periódica, cron jobs, persistência,
grupos e integração com Promise/Try. Sem asyncio, sem dependências externas.

Exemplos rápidos
----------------
::

    from nestifypy.scheduler import Scheduler

    # Execução única após delay
    Scheduler.after(5).seconds(task)

    # Execução periódica
    Scheduler.every(10).minutes(task)

    # Cron job
    Scheduler.cron("0 8 * * 1")(send_report)   # segunda-feira às 08:00

    # Decorator
    @Scheduler.every(30).seconds
    def clean_cache():
        print("Cache limpa")

    # Cadeia completa
    Scheduler.every(15).minutes(sync_db) \\
             .named("db-sync") \\
             .timeout(60) \\
             .repeat(10) \\
             .log() \\
             .async_()
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any, Callable, Dict, Iterator, List, Optional,
    Tuple, Type, TypeVar, Union,
)

F = TypeVar("F", bound=Callable[..., Any])

# Pool global para execução async de jobs
_ASYNC_POOL: Optional[ThreadPoolExecutor] = None
_POOL_LOCK = threading.Lock()


def _async_pool() -> ThreadPoolExecutor:
    global _ASYNC_POOL
    if _ASYNC_POOL is None:
        with _POOL_LOCK:
            if _ASYNC_POOL is None:
                _ASYNC_POOL = ThreadPoolExecutor(
                    max_workers=16,
                    thread_name_prefix="nestify-scheduler",
                )
    return _ASYNC_POOL


# ─────────────────────────────────────────────────────────────────────────────
#  Enums e constantes
# ─────────────────────────────────────────────────────────────────────────────

class JobState(Enum):
    PENDING   = auto()
    RUNNING   = auto()
    PAUSED    = auto()
    CANCELLED = auto()
    COMPLETED = auto()  # atingiu repeat limit


class MissedStrategy(Enum):
    """Estratégia de recuperação para jobs persistentes com execuções perdidas."""
    CATCHUP = "catchup"  # executa todas as perdidas
    SKIP    = "skip"     # ignora todas as perdidas
    LATEST  = "latest"   # executa apenas a mais recente


class JobMode(Enum):
    ONCE     = auto()   # executa uma vez após delay
    PERIODIC = auto()   # executa em intervalos
    CRON     = auto()   # expressão cron


# ─────────────────────────────────────────────────────────────────────────────
#  Excepções
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerError(Exception):
    """Base exception for Scheduler errors."""


class JobNotFoundError(SchedulerError):
    """Raised when a named job cannot be found."""


class CronParseError(SchedulerError):
    """Raised when a cron expression cannot be parsed."""


class JobTimeoutError(SchedulerError):
    """Raised when a job execution exceeds its timeout."""


# ─────────────────────────────────────────────────────────────────────────────
#  Cron parser (sem dependências externas)
# ─────────────────────────────────────────────────────────────────────────────

class _CronField:
    """Parse e avaliação de um único campo cron."""

    RANGES = {
        "minute": (0, 59),
        "hour":   (0, 23),
        "dom":    (1, 31),   # day of month
        "month":  (1, 12),
        "dow":    (0, 6),    # day of week (0=Sun)
    }

    MONTH_NAMES = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    DOW_NAMES = {
        "sun": 0, "mon": 1, "tue": 2, "wed": 3,
        "thu": 4, "fri": 5, "sat": 6,
    }

    def __init__(self, expr: str, field: str) -> None:
        self.expr  = expr
        self.field = field
        lo, hi     = self.RANGES[field]
        self.values: set[int] = self._parse(expr, lo, hi, field)

    def _resolve_name(self, token: str, field: str) -> str:
        lw = token.lower()
        if field == "month" and lw in self.MONTH_NAMES:
            return str(self.MONTH_NAMES[lw])
        if field == "dow" and lw in self.DOW_NAMES:
            return str(self.DOW_NAMES[lw])
        return token

    def _parse(self, expr: str, lo: int, hi: int, field: str) -> set[int]:
        result: set[int] = set()
        for part in expr.split(","):
            part = self._resolve_name(part, field)
            if part == "*":
                result.update(range(lo, hi + 1))
            elif part.startswith("*/"):
                step = int(part[2:])
                result.update(range(lo, hi + 1, step))
            elif "/" in part:
                rng, step = part.split("/", 1)
                start, end = (int(x) for x in rng.split("-", 1)) if "-" in rng else (lo, hi)
                result.update(range(start, end + 1, int(step)))
            elif "-" in part:
                start, end = (int(self._resolve_name(x, field)) for x in part.split("-", 1))
                result.update(range(start, end + 1))
            else:
                result.add(int(self._resolve_name(part, field)))
        return result

    def matches(self, value: int) -> bool:
        return value in self.values


class CronExpression:
    """
    Representa e avalia uma expressão cron de 5 campos:
    ``minute hour dom month dow``

    Suporta: ``*``, ``*/n``, ``n-m``, ``n,m``, nomes (jan-dec, sun-sat).
    """

    def __init__(self, expression: str) -> None:
        self.expression = expression
        parts = expression.strip().split()
        if len(parts) != 5:
            raise CronParseError(
                f"Expressão cron inválida: '{expression}'. "
                f"Esperados 5 campos, recebidos {len(parts)}."
            )
        try:
            self._minute = _CronField(parts[0], "minute")
            self._hour   = _CronField(parts[1], "hour")
            self._dom    = _CronField(parts[2], "dom")
            self._month  = _CronField(parts[3], "month")
            self._dow    = _CronField(parts[4], "dow")
        except (ValueError, KeyError) as exc:
            raise CronParseError(f"Erro ao parsear '{expression}': {exc}") from exc

    def matches(self, dt: Optional[datetime] = None) -> bool:
        """Verifica se ``dt`` (default: agora) satisfaz esta expressão."""
        dt = dt or datetime.now()
        return (
            self._minute.matches(dt.minute)
            and self._hour.matches(dt.hour)
            and self._dom.matches(dt.day)
            and self._month.matches(dt.month)
            and self._dow.matches(dt.weekday() + 1 if dt.weekday() < 6 else 0)
        )

    def next_after(self, dt: Optional[datetime] = None) -> datetime:
        """Retorna o próximo instante após ``dt`` que satisfaz a expressão."""
        dt = (dt or datetime.now()).replace(second=0, microsecond=0)
        dt += timedelta(minutes=1)
        # Avança minuto a minuto — máximo 366 dias para encontrar um match
        for _ in range(366 * 24 * 60):
            if self.matches(dt):
                return dt
            dt += timedelta(minutes=1)
        raise SchedulerError(
            f"Não foi possível calcular o próximo instante para '{self.expression}'"
        )

    def __repr__(self) -> str:
        return f"CronExpression({self.expression!r})"


# ─────────────────────────────────────────────────────────────────────────────
#  Eventos
# ─────────────────────────────────────────────────────────────────────────────

class JobEvent:
    """Evento emitido pelo ciclo de vida de um Job."""

    __slots__ = ("kind", "job", "timestamp", "error", "duration_ms")

    def __init__(
        self,
        kind: str,
        job: "Job",
        error: Optional[BaseException] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        self.kind        = kind          # "start" | "complete" | "error" | "cancel" | "timeout"
        self.job         = job
        self.timestamp   = datetime.now()
        self.error       = error
        self.duration_ms = duration_ms

    def __repr__(self) -> str:
        return f"JobEvent({self.kind!r}, job={self.job.name!r}, ts={self.timestamp:%H:%M:%S})"


# ─────────────────────────────────────────────────────────────────────────────
#  Job
# ─────────────────────────────────────────────────────────────────────────────

class Job:
    """
    Representa uma tarefa agendada.

    Retornado por todos os métodos de agendamento:
    ``Scheduler.after()``, ``Scheduler.every()``, ``Scheduler.cron()``.

    Métodos de controlo
    -------------------
    ::

        job.cancel()
        job.pause()
        job.resume()
        job.run_now()

    Configuração (encadeável)
    -------------------------
    ::

        Scheduler.every(5).minutes(task) \\
                 .named("my-job") \\
                 .timeout(30) \\
                 .repeat(10) \\
                 .delay(5) \\
                 .group("db") \\
                 .log() \\
                 .async_() \\
                 .persistent()
    """

    def __init__(
        self,
        fn: Callable[[], Any],
        mode: JobMode,
        interval_seconds: float = 0.0,
        cron: Optional[CronExpression] = None,
    ) -> None:
        self._id              = str(uuid.uuid4())[:8]
        self._fn              = fn
        self._mode            = mode
        self._interval        = interval_seconds   # segundos entre execuções (PERIODIC/ONCE delay)
        self._cron            = cron

        # Configuração encadeável
        self._name:           Optional[str]          = None
        self._timeout:        Optional[float]        = None
        self._repeat_limit:   Optional[int]          = None
        self._initial_delay:  float                  = 0.0
        self._group_name:     Optional[str]          = None
        self._do_log:         bool                   = False
        self._is_async:       bool                   = False
        self._is_process:     bool                   = False
        self._persist_path:   Optional[Path]         = None
        self._missed_strategy: MissedStrategy        = MissedStrategy.SKIP

        # Estado interno
        self._state:          JobState    = JobState.PENDING
        self._run_count:      int         = 0
        self._last_run:       Optional[datetime] = None
        self._next_run:       Optional[datetime] = None
        self._lock            = threading.Lock()
        self._thread:         Optional[threading.Thread] = None
        self._pause_event     = threading.Event()
        self._pause_event.set()   # inicia sem pausa
        self._stop_event      = threading.Event()

        # Listeners de eventos
        self._listeners: List[Callable[[JobEvent], Any]] = []

        # Callbacks de ciclo de vida
        self._on_start_cbs:    List[Callable[[], Any]]               = []
        self._on_complete_cbs: List[Callable[[Any], Any]]            = []
        self._on_error_cbs:    List[Callable[[BaseException], Any]]  = []
        self._on_cancel_cbs:   List[Callable[[], Any]]               = []

    # ── propriedades públicas ─────────────────────────────────────────────────

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name or f"job-{self._id}"

    @property
    def run_count(self) -> int:
        return self._run_count

    @property
    def last_run(self) -> Optional[datetime]:
        return self._last_run

    @property
    def next_run(self) -> Optional[datetime]:
        return self._next_run

    # ── estado ────────────────────────────────────────────────────────────────

    def running(self) -> bool:
        return self._state == JobState.RUNNING

    def paused(self) -> bool:
        return self._state == JobState.PAUSED

    def cancelled(self) -> bool:
        return self._state == JobState.CANCELLED

    def completed(self) -> bool:
        return self._state == JobState.COMPLETED

    def is_active(self) -> bool:
        """Verdadeiro se ainda pode executar (não cancelado/completado)."""
        return self._state not in (JobState.CANCELLED, JobState.COMPLETED)

    # ── configuração encadeável ───────────────────────────────────────────────

    def named(self, name: str) -> "Job":
        """Dá um nome ao job para posterior identificação."""
        self._name = name
        Scheduler._register_named(name, self)
        return self

    def timeout(self, seconds: float) -> "Job":
        """Cancela a execução se demorar mais do que ``seconds``."""
        self._timeout = seconds
        return self

    def repeat(self, times: int) -> "Job":
        """Limita o número total de execuções."""
        self._repeat_limit = times
        return self

    def delay(self, seconds: float) -> "Job":
        """Atrasa a primeira execução em ``seconds`` segundos."""
        self._initial_delay = seconds
        return self

    def group(self, name: str) -> "Job":
        """Associa o job a um grupo."""
        self._group_name = name
        Scheduler._add_to_group(name, self)
        return self

    def log(self) -> "Job":
        """Activa logging automático de início, fim e duração."""
        self._do_log = True
        return self

    def async_(self) -> "Job":
        """Executa o job numa thread separada (não bloqueia o scheduler)."""
        self._is_async = True
        return self

    def process(self) -> "Job":
        """Executa o job num processo separado (CPU-bound tasks)."""
        self._is_process = True
        return self

    def persistent(
        self,
        strategy: Union[str, MissedStrategy] = MissedStrategy.SKIP,
        path: Union[str, Path, None] = None,
    ) -> "Job":
        """
        Persiste o estado do job em disco.

        Ao reiniciar a aplicação, o Scheduler detecta execuções perdidas
        e aplica a estratégia escolhida.

        Parameters
        ----------
        strategy:
            ``"catchup"`` executa todas as perdidas.
            ``"skip"`` ignora todas.
            ``"latest"`` executa apenas a mais recente.
        path:
            Pasta de persistência (default: ``.nestifypy/scheduler``).
        """
        if isinstance(strategy, str):
            strategy = MissedStrategy(strategy)
        self._missed_strategy = strategy

        base = Path(path) if path else Path(".nestifypy") / "scheduler"
        base.mkdir(parents=True, exist_ok=True)
        self._persist_path = base / f"{self.name}.json"
        self._load_persist_state()
        return self

    # ── callbacks de ciclo de vida ────────────────────────────────────────────

    def on_start(self, fn: Callable[[], Any]) -> "Job":
        self._on_start_cbs.append(fn)
        return self

    def on_complete(self, fn: Callable[[Any], Any]) -> "Job":
        self._on_complete_cbs.append(fn)
        return self

    def on_error(self, fn: Callable[[BaseException], Any]) -> "Job":
        self._on_error_cbs.append(fn)
        return self

    def on_cancel(self, fn: Callable[[], Any]) -> "Job":
        self._on_cancel_cbs.append(fn)
        return self

    def listen(self, fn: Callable[[JobEvent], Any]) -> "Job":
        """Regista um listener de todos os eventos deste job."""
        self._listeners.append(fn)
        return self

    # ── controlo ──────────────────────────────────────────────────────────────

    def cancel(self) -> "Job":
        """Cancela o job permanentemente."""
        with self._lock:
            if self._state in (JobState.CANCELLED, JobState.COMPLETED):
                return self
            self._state = JobState.CANCELLED
        self._stop_event.set()
        self._pause_event.set()   # desbloqueia se estava pausado
        Scheduler._unregister(self)
        for cb in self._on_cancel_cbs:
            _safe_call(cb)
        self._emit(JobEvent("cancel", self))
        return self

    def pause(self) -> "Job":
        """Pausa o job — a próxima execução aguarda até :meth:`resume`."""
        with self._lock:
            if self._state == JobState.RUNNING:
                self._state = JobState.PAUSED
                self._pause_event.clear()
        return self

    def resume(self) -> "Job":
        """Retoma um job pausado."""
        with self._lock:
            if self._state == JobState.PAUSED:
                self._state = JobState.RUNNING
                self._pause_event.set()
        return self

    def run_now(self) -> "Job":
        """Executa imediatamente, fora do ciclo normal."""
        threading.Thread(
            target=self._execute,
            daemon=True,
            name=f"nestify-runnow-{self.name}",
        ).start()
        return self

    # ── arranque interno ──────────────────────────────────────────────────────

    def _start(self) -> "Job":
        """Inicia o loop do job numa thread de background."""
        self._state = JobState.RUNNING
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"nestify-job-{self.name}",
        )
        self._thread.start()
        Scheduler._all_jobs[self._id] = self
        return self

    # ── loop principal ────────────────────────────────────────────────────────

    def _loop(self) -> None:
        # Delay inicial
        if self._initial_delay > 0:
            if self._stop_event.wait(self._initial_delay):
                return

        if self._mode == JobMode.ONCE:
            self._execute()
            with self._lock:
                self._state = JobState.COMPLETED
            Scheduler._unregister(self)
            return

        if self._mode == JobMode.PERIODIC:
            self._periodic_loop()
        elif self._mode == JobMode.CRON:
            self._cron_loop()

    def _periodic_loop(self) -> None:
        while not self._stop_event.is_set():
            # Aguarda pausa se necessário
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            self._next_run = datetime.now() + timedelta(seconds=self._interval)
            self._execute()

            if self._repeat_limit is not None and self._run_count >= self._repeat_limit:
                with self._lock:
                    self._state = JobState.COMPLETED
                Scheduler._unregister(self)
                break

            # Espera até o próximo intervalo (interruptível)
            self._stop_event.wait(self._interval)

    def _cron_loop(self) -> None:
        assert self._cron is not None
        while not self._stop_event.is_set():
            self._pause_event.wait()
            if self._stop_event.is_set():
                break

            now  = datetime.now()
            next_dt = self._cron.next_after(now)
            self._next_run = next_dt
            wait_s = (next_dt - datetime.now()).total_seconds()

            if wait_s > 0:
                if self._stop_event.wait(wait_s):
                    break

            if self._stop_event.is_set():
                break

            # Verifica se ainda bate (pode ter dormido mais do que o previsto)
            if self._cron.matches():
                self._execute()

            if self._repeat_limit is not None and self._run_count >= self._repeat_limit:
                with self._lock:
                    self._state = JobState.COMPLETED
                Scheduler._unregister(self)
                break

    # ── execução de uma iteração ──────────────────────────────────────────────

    def _execute(self) -> None:
        if self._stop_event.is_set():
            return

        t0 = time.perf_counter()
        self._last_run = datetime.now()

        # Callbacks de início
        for cb in self._on_start_cbs:
            _safe_call(cb)
        self._emit(JobEvent("start", self))

        if self._do_log:
            _log_info(f"[Scheduler] {self.name} started")

        result_holder: list[Any]    = [None]
        error_holder:  list[Any]    = [None]
        done = threading.Event()

        def _run() -> None:
            try:
                result_holder[0] = self._fn()
            except BaseException as exc:
                error_holder[0] = exc
            finally:
                done.set()

        if self._is_async or self._is_process:
            _async_pool().submit(_run)
            # fire-and-forget; non-blocking — não aguarda resultado
            self._run_count += 1
            self._save_persist_state()
            return

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        finished = done.wait(self._timeout)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        self._run_count += 1
        self._save_persist_state()

        if not finished:
            err = JobTimeoutError(
                f"Job '{self.name}' timed out after {self._timeout}s"
            )
            for cb in self._on_error_cbs:
                _safe_call(cb, err)
            self._emit(JobEvent("timeout", self, error=err, duration_ms=elapsed_ms))
            if self._do_log:
                _log_warn(f"[Scheduler] {self.name} timed out ({self._timeout}s)")
            return

        if error_holder[0] is not None:
            exc = error_holder[0]
            for cb in self._on_error_cbs:
                _safe_call(cb, exc)
            self._emit(JobEvent("error", self, error=exc, duration_ms=elapsed_ms))
            if self._do_log:
                _log_error(f"[Scheduler] {self.name} failed: {exc}")
            return

        for cb in self._on_complete_cbs:
            _safe_call(cb, result_holder[0])
        self._emit(JobEvent("complete", self, duration_ms=elapsed_ms))

        if self._do_log:
            _log_info(f"[Scheduler] {self.name} completed in {elapsed_ms:.1f} ms")

    def _emit(self, event: JobEvent) -> None:
        for fn in self._listeners:
            _safe_call(fn, event)
        for fn in Scheduler._global_listeners:
            _safe_call(fn, event)

    # ── persistência ──────────────────────────────────────────────────────────

    def _save_persist_state(self) -> None:
        if not self._persist_path:
            return
        state = {
            "name":       self.name,
            "run_count":  self._run_count,
            "last_run":   self._last_run.isoformat() if self._last_run else None,
            "interval":   self._interval,
            "mode":       self._mode.name,
            "cron":       self._cron.expression if self._cron else None,
        }
        try:
            with open(self._persist_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2)
        except OSError:
            pass

    def _load_persist_state(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            with open(self._persist_path, encoding="utf-8") as fh:
                state = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return

        self._run_count = state.get("run_count", 0)
        last_run_str    = state.get("last_run")
        if last_run_str:
            self._last_run = datetime.fromisoformat(last_run_str)

        self._handle_missed(state)

    def _handle_missed(self, state: dict) -> None:
        """Aplica a estratégia de recuperação para execuções perdidas."""
        if self._mode not in (JobMode.PERIODIC, JobMode.CRON):
            return
        last_run = self._last_run
        if not last_run:
            return

        now     = datetime.now()
        missed: List[datetime] = []

        if self._mode == JobMode.PERIODIC and self._interval > 0:
            t = last_run + timedelta(seconds=self._interval)
            while t <= now:
                missed.append(t)
                t += timedelta(seconds=self._interval)

        elif self._mode == JobMode.CRON and self._cron:
            t = last_run
            while True:
                try:
                    t = self._cron.next_after(t)
                except SchedulerError:
                    break
                if t > now:
                    break
                missed.append(t)

        if not missed:
            return

        if self._do_log:
            _log_warn(
                f"[Scheduler] {self.name}: {len(missed)} execução(ões) perdida(s) "
                f"desde {last_run:%Y-%m-%d %H:%M:%S}"
            )

        if self._missed_strategy == MissedStrategy.CATCHUP:
            for _ in missed:
                threading.Thread(target=self._execute, daemon=True).start()
        elif self._missed_strategy == MissedStrategy.LATEST:
            threading.Thread(target=self._execute, daemon=True).start()
        # SKIP: não faz nada

    # ── repr ──────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        mode = self._mode.name
        state = self._state.name
        return (
            f"Job(name={self.name!r}, mode={mode}, state={state}, "
            f"runs={self._run_count})"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  _FluentInterval  (builder intermediário)
# ─────────────────────────────────────────────────────────────────────────────

class _FluentInterval:
    """
    Builder retornado por ``Scheduler.every(n)`` e ``Scheduler.after(n)``.
    Especifica a unidade de tempo e a função a executar.
    """

    def __init__(self, amount: float, is_once: bool = False) -> None:
        self._amount  = amount
        self._is_once = is_once

    # ── unidades de tempo ──────────────────────────────────────────────────────

    def _make(self, seconds: float) -> "_UnitProxy":
        return _UnitProxy(seconds, self._is_once)

    @property
    def second(self)  -> "_UnitProxy": return self._make(self._amount)
    @property
    def seconds(self) -> "_UnitProxy": return self._make(self._amount)
    @property
    def minute(self)  -> "_UnitProxy": return self._make(self._amount * 60)
    @property
    def minutes(self) -> "_UnitProxy": return self._make(self._amount * 60)
    @property
    def hour(self)    -> "_UnitProxy": return self._make(self._amount * 3600)
    @property
    def hours(self)   -> "_UnitProxy": return self._make(self._amount * 3600)
    @property
    def day(self)     -> "_UnitProxy": return self._make(self._amount * 86400)
    @property
    def days(self)    -> "_UnitProxy": return self._make(self._amount * 86400)
    @property
    def week(self)    -> "_UnitProxy": return self._make(self._amount * 604800)
    @property
    def weeks(self)   -> "_UnitProxy": return self._make(self._amount * 604800)


class _UnitProxy:
    """
    Proxy final que pode ser:
    - chamado como função: ``.seconds(task)`` → agenda e retorna Job
    - usado como decorator: ``@scheduler.every(5).seconds`` → decora função
    """

    def __init__(self, seconds: float, is_once: bool) -> None:
        self._seconds = seconds
        self._is_once = is_once

    def __call__(self, fn: Callable[[], Any]) -> "Job":
        """Agenda ``fn`` e retorna o Job."""
        mode = JobMode.ONCE if self._is_once else JobMode.PERIODIC
        job  = Job(fn, mode=mode, interval_seconds=self._seconds)
        job._start()
        return job

    # Suporte a decorator sem parênteses: @Scheduler.every(5).seconds
    def __get__(self, obj: Any, objtype: Any = None) -> "_UnitProxy":
        return self


# ─────────────────────────────────────────────────────────────────────────────
#  _CronProxy  (builder para cron)
# ─────────────────────────────────────────────────────────────────────────────

class _CronProxy:
    """Retornado por ``Scheduler.cron(expr)``."""

    def __init__(self, cron: CronExpression) -> None:
        self._cron = cron

    def __call__(self, fn: Callable[[], Any]) -> "Job":
        """Agenda ``fn`` com a expressão cron e retorna o Job."""
        job = Job(fn, mode=JobMode.CRON, cron=self._cron)
        job._start()
        return job


# ─────────────────────────────────────────────────────────────────────────────
#  Group
# ─────────────────────────────────────────────────────────────────────────────

class Group:
    """
    Agrupa jobs para controlo em conjunto.

    ::

        Scheduler.every(5).minutes(sync_users).group("database")
        Scheduler.every(10).minutes(sync_orders).group("database")

        Scheduler.group("database").pause_all()
        Scheduler.group("database").resume_all()
        Scheduler.group("database").cancel_all()
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._jobs: List[Job] = []

    def add(self, job: Job) -> None:
        self._jobs.append(job)

    def jobs(self) -> List[Job]:
        return [j for j in self._jobs if j.is_active()]

    def cancel_all(self) -> None:
        for job in list(self._jobs):
            job.cancel()

    def pause_all(self) -> None:
        for job in self._jobs:
            job.pause()

    def resume_all(self) -> None:
        for job in self._jobs:
            job.resume()

    def run_all_now(self) -> None:
        for job in self._jobs:
            job.run_now()

    def count(self) -> int:
        return len(self.jobs())

    def __repr__(self) -> str:
        return f"Group({self.name!r}, jobs={self.count()})"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers de logging (sem depender do slogger)
# ─────────────────────────────────────────────────────────────────────────────

def _log_info(msg: str) -> None:
    print(f"\033[34m[{datetime.now():%H:%M:%S}] [INFO ] {msg}\033[0m")

def _log_warn(msg: str) -> None:
    print(f"\033[33m[{datetime.now():%H:%M:%S}] [WARN ] {msg}\033[0m")

def _log_error(msg: str) -> None:
    print(f"\033[31m[{datetime.now():%H:%M:%S}] [ERROR] {msg}\033[0m")

def _safe_call(fn: Callable, *args: Any) -> Any:
    try:
        return fn(*args)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Scheduler (fachada principal)
# ─────────────────────────────────────────────────────────────────────────────

class Scheduler:
    """
    Fachada estática para o sistema de agendamento do Nestifypy.

    Uso
    ---
    ::

        from nestifypy.scheduler import Scheduler

        # Execução única após delay
        Scheduler.after(10).seconds(task)

        # Execução periódica
        Scheduler.every(5).minutes(sync_db)

        # Cron job
        Scheduler.cron("0 0 * * *")(backup)

        # Como decorator
        @Scheduler.every(1).minute
        def heartbeat():
            print("alive")

        # Controlo
        job = Scheduler.every(10).seconds(task).named("t")
        job.pause()
        job.resume()
        job.cancel()

        # Monitoramento
        Scheduler.jobs()
        Scheduler.running_jobs()
        Scheduler.count()
    """

    # Registo global de todos os jobs activos
    _all_jobs:       Dict[str, Job]   = {}
    _named_jobs:     Dict[str, Job]   = {}
    _groups:         Dict[str, Group] = {}
    _global_listeners: List[Callable[[JobEvent], Any]] = []
    _lock = threading.Lock()

    # ── factories ─────────────────────────────────────────────────────────────

    @classmethod
    def after(cls, amount: float) -> _FluentInterval:
        """
        Agenda uma execução única após um delay.

        ::

            Scheduler.after(5).seconds(task)
            Scheduler.after(2).minutes(task)
            Scheduler.after(1).hour(task)
        """
        return _FluentInterval(amount, is_once=True)

    @classmethod
    def every(cls, amount: float) -> _FluentInterval:
        """
        Agenda execução periódica.

        ::

            Scheduler.every(10).seconds(task)
            Scheduler.every(5).minutes(task)
            Scheduler.every(1).hour(task)

            # Como decorator
            @Scheduler.every(30).seconds
            def clean_cache():
                ...
        """
        return _FluentInterval(amount, is_once=False)

    @classmethod
    def cron(cls, expression: str) -> _CronProxy:
        """
        Agenda via expressão cron de 5 campos (minute hour dom month dow).

        ::

            Scheduler.cron("0 0 * * *")(backup)          # todos os dias à meia-noite
            Scheduler.cron("*/5 * * * *")(sync)           # a cada 5 minutos
            Scheduler.cron("0 8 * * 1")(generate_report)  # segunda-feira às 08:00
            Scheduler.cron("0 9-17 * * mon-fri")(ping)    # cada hora entre 09-17, dias úteis
        """
        return _CronProxy(CronExpression(expression))

    # ── gestão de jobs ────────────────────────────────────────────────────────

    @classmethod
    def job(cls, name: str) -> Job:
        """
        Obtém um job registado pelo nome.

        ::

            Scheduler.job("database-sync").cancel()
            Scheduler.job("heartbeat").pause()
        """
        with cls._lock:
            job = cls._named_jobs.get(name)
        if job is None:
            raise JobNotFoundError(f"Job '{name}' não encontrado")
        return job

    @classmethod
    def jobs(cls) -> List[Job]:
        """Retorna todos os jobs activos (não cancelados/completados)."""
        with cls._lock:
            return [j for j in cls._all_jobs.values() if j.is_active()]

    @classmethod
    def all_jobs(cls) -> List[Job]:
        """Retorna todos os jobs incluindo cancelados e completados."""
        with cls._lock:
            return list(cls._all_jobs.values())

    @classmethod
    def running_jobs(cls) -> List[Job]:
        """Retorna apenas jobs em estado RUNNING."""
        return [j for j in cls.jobs() if j.running()]

    @classmethod
    def paused_jobs(cls) -> List[Job]:
        """Retorna apenas jobs em estado PAUSED."""
        return [j for j in cls.jobs() if j.paused()]

    @classmethod
    def count(cls) -> int:
        """Número de jobs activos."""
        return len(cls.jobs())

    @classmethod
    def cancel_all(cls) -> None:
        """Cancela todos os jobs activos."""
        for job in cls.jobs():
            job.cancel()

    @classmethod
    def pause_all(cls) -> None:
        """Pausa todos os jobs activos."""
        for job in cls.jobs():
            job.pause()

    @classmethod
    def resume_all(cls) -> None:
        """Retoma todos os jobs pausados."""
        for job in cls.paused_jobs():
            job.resume()

    # ── grupos ────────────────────────────────────────────────────────────────

    @classmethod
    def group(cls, name: str) -> Group:
        """
        Obtém ou cria um grupo de jobs.

        ::

            Scheduler.group("database").cancel_all()
            Scheduler.group("database").pause_all()
        """
        with cls._lock:
            if name not in cls._groups:
                cls._groups[name] = Group(name)
            return cls._groups[name]

    @classmethod
    def groups(cls) -> Dict[str, Group]:
        """Retorna todos os grupos registados."""
        with cls._lock:
            return dict(cls._groups)

    # ── eventos globais ───────────────────────────────────────────────────────

    @classmethod
    def on_event(cls, fn: Callable[[JobEvent], Any]) -> None:
        """
        Regista um listener global para todos os eventos de todos os jobs.

        ::

            @Scheduler.on_event
            def log_all(event):
                print(event.kind, event.job.name)

            # Ou directamente:
            Scheduler.on_event(lambda e: print(e))
        """
        if callable(fn):
            cls._global_listeners.append(fn)

    # ── decorators ────────────────────────────────────────────────────────────

    @classmethod
    def on_job_start(cls, fn: Callable[[JobEvent], Any]) -> Callable[[JobEvent], Any]:
        """Decorator/função para eventos de início."""
        cls._global_listeners.append(
            lambda e: fn(e) if e.kind == "start" else None
        )
        return fn

    @classmethod
    def on_job_complete(cls, fn: Callable[[JobEvent], Any]) -> Callable[[JobEvent], Any]:
        """Decorator/função para eventos de conclusão."""
        cls._global_listeners.append(
            lambda e: fn(e) if e.kind == "complete" else None
        )
        return fn

    @classmethod
    def on_job_error(cls, fn: Callable[[JobEvent], Any]) -> Callable[[JobEvent], Any]:
        """Decorator/função para eventos de erro."""
        cls._global_listeners.append(
            lambda e: fn(e) if e.kind == "error" else None
        )
        return fn

    # ── monitoramento ─────────────────────────────────────────────────────────

    @classmethod
    def summary(cls) -> str:
        """Retorna um resumo em texto dos jobs activos."""
        lines = [
            f"{'─' * 60}",
            f"  Scheduler — {cls.count()} job(s) activo(s)",
            f"{'─' * 60}",
        ]
        for job in cls.jobs():
            next_run = f"{job.next_run:%H:%M:%S}" if job.next_run else "—"
            last_run = f"{job.last_run:%H:%M:%S}" if job.last_run else "—"
            lines.append(
                f"  {job.name:<30} state={job._state.name:<10} "
                f"runs={job.run_count:<5} last={last_run}  next={next_run}"
            )
        lines.append(f"{'─' * 60}")
        return "\n".join(lines)

    @classmethod
    def print_summary(cls) -> None:
        """Imprime o resumo do Scheduler."""
        print(cls.summary())

    # ── internos ──────────────────────────────────────────────────────────────

    @classmethod
    def _register_named(cls, name: str, job: Job) -> None:
        with cls._lock:
            cls._named_jobs[name] = job

    @classmethod
    def _add_to_group(cls, group_name: str, job: Job) -> None:
        g = cls.group(group_name)
        g.add(job)

    @classmethod
    def _unregister(cls, job: Job) -> None:
        with cls._lock:
            cls._all_jobs.pop(job.id, None)
            if job._name:
                cls._named_jobs.pop(job._name, None)

    @classmethod
    def _reset(cls) -> None:
        """Usado apenas em testes — limpa todo o estado."""
        cls.cancel_all()
        with cls._lock:
            cls._all_jobs.clear()
            cls._named_jobs.clear()
            cls._groups.clear()
            cls._global_listeners.clear()


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "Scheduler",
    "Job",
    "JobState",
    "JobEvent",
    "Group",
    "CronExpression",
    "MissedStrategy",
    "SchedulerError",
    "JobNotFoundError",
    "CronParseError",
    "JobTimeoutError",
]
