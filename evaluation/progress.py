"""Terminal progress with elapsed time while individual model calls are running."""

import sys
import threading
import time


class Progress:
    def __init__(self, label, total=None, stream=None):
        self.label, self.total = label, total
        self.stream = stream if stream is not None else sys.stdout
        self.completed = 0
        self.started = time.monotonic()
        self.stop_event = threading.Event()
        self.thread = None
        self.tty = bool(getattr(self.stream, "isatty", lambda: False)())

    def line(self):
        elapsed = int(time.monotonic() - self.started)
        if self.total is None:
            bar = "|/-\\"[elapsed % 4]
            return f"{self.label} [{bar}] elapsed {elapsed}s"
        fraction = self.completed / self.total if self.total else 1
        filled = int(24 * fraction)
        eta = f" | ETA ~{int(elapsed / self.completed * (self.total - self.completed))}s" if self.completed else ""
        return (f"{self.label} [{'#' * filled}{'.' * (24 - filled)}] "
                f"{self.completed}/{self.total} ({fraction:.0%}) | elapsed {elapsed}s{eta}")

    def render(self):
        self.stream.write(("\r\033[2K" if self.tty else "") + self.line() + ("" if self.tty else "\n"))
        self.stream.flush()

    def _heartbeat(self):
        while not self.stop_event.wait(0.25):
            self.render()

    def __enter__(self):
        self.render()
        if self.tty:
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        return self

    def update(self, completed):
        self.completed = completed
        if not self.tty:
            self.render()

    def __exit__(self, *exc):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        if self.tty:
            self.render()
            self.stream.write("\n")
            self.stream.flush()
