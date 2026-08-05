from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from .logging_setup import get_logger

log = get_logger("watch")

RebuildCallback = Callable[[], None]


class DebouncedTrigger:
    def __init__(self, callback: RebuildCallback, debounce_ms: int = 500) -> None:
        self._callback = callback
        self._debounce_s = max(0.05, debounce_ms / 1000.0)
        self._timer: threading.Timer | None = None
        self._running = False
        self._pending = False
        self._state = threading.Condition()

    def notify(self) -> None:
        with self._state:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._state:
            self._timer = None
            if self._running:
                self._pending = True
                log.debug("Change detected while rebuilding; one more pass to come.")
                return
            self._running = True
        handed_back = False
        try:
            while True:
                log.debug("Change detected; rebuilding.")
                self._callback()
                with self._state:
                    if not self._pending:
                        self._running = False
                        self._state.notify_all()
                        handed_back = True
                        return
                    self._pending = False
        finally:
            if not handed_back:
                with self._state:
                    self._running = False
                    self._pending = False
                    self._state.notify_all()

    def cancel(self) -> None:
        with self._state:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = False

    def busy(self) -> bool:
        with self._state:
            return self._running

    def wait_idle(self) -> None:
        with self._state:
            while self._running:
                self._state.wait()


def _unique(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def content_roots(dirs=()) -> list[Path]:
    return _unique(
        [Path(d).resolve() for d in dirs if d is not None and Path(d).is_dir()]
    )


def collect_watch_paths(
    markdown_dir: Path,
    markdown_files: list[str],
    extra_dirs=(),
) -> list[Path]:
    paths: list[Path] = [markdown_dir.resolve()]
    for rel in markdown_files:
        paths.append((markdown_dir / rel).resolve())
    paths.extend(content_roots(extra_dirs))
    return _unique(paths)


def require_watchdog() -> None:
    try:
        import watchdog
    except ImportError as exc:
        raise RuntimeError(
            "watch mode needs the optional watchdog package"
        ) from exc


def run_watch(
    watch_paths: list[Path],
    rebuild: RebuildCallback,
    *,
    debounce_ms: int = 500,
    content_roots=(),
    on_finishing: Callable[[], None] | None = None,
) -> None:
    require_watchdog()
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    trigger = DebouncedTrigger(rebuild, debounce_ms=debounce_ms)
    watch_set = {p.resolve() for p in watch_paths}
    content_set = {Path(p).resolve() for p in content_roots}

    def _under(path: Path, roots) -> bool:
        return any(path.is_relative_to(root) for root in roots)

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            src = Path(event.src_path).resolve()
            if not _under(src, watch_set):
                return
            if src.suffix == ".md" or _under(src, content_set):
                trigger.notify()

    observer = Observer()
    scheduled: set[str] = set()
    for path in watch_paths:
        if path.is_file():
            path = path.parent
        key = str(path.resolve())
        if key in scheduled or not path.is_dir():
            continue
        scheduled.add(key)
        observer.schedule(Handler(), str(path), recursive=True)

    observer.start()
    log.debug("Watching %d path(s).", len(scheduled))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.debug("Watch stopped by the user.")
    finally:
        trigger.cancel()
        observer.stop()
        observer.join()
        trigger.cancel()
        if trigger.busy():
            if on_finishing is not None:
                on_finishing()
            try:
                trigger.wait_idle()
            except KeyboardInterrupt:
                log.debug("Interrupted again; leaving the rebuild to itself.")
