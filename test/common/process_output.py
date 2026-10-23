import sys
import threading
import time


class ProcessOutput:
    """Wait for subprocess log events without polling or fixed delays."""

    def __init__(self, process, echo=False):
        self.process = process
        self.echo = echo
        self.condition = threading.Condition()
        self.lines = []
        self.finished = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                if self.echo:
                    try:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                    except (OSError, UnicodeError, ValueError):
                        # Console output must not stop draining the child pipe.
                        self.echo = False
                with self.condition:
                    self.lines.append(line)
                    self.condition.notify_all()
        finally:
            with self.condition:
                self.finished = True
                self.condition.notify_all()

    def position(self):
        with self.condition:
            return len(self.lines)

    def has_finished(self):
        with self.condition:
            return self.finished

    def wait_for_any(self, markers, timeout, description, after=0):
        markers = tuple(marker.lower() for marker in markers)
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                for line in self.lines[after:]:
                    lowered = line.lower()
                    if any(marker in lowered for marker in markers):
                        return line

                if self.finished:
                    raise RuntimeError(
                        '%s exited before output %r appeared.\n%s' %
                        (description, markers, self.tail())
                    )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        'Timed out waiting for %r from %s within %d seconds.\n%s' %
                        (markers, description, timeout, self.tail())
                    )
                self.condition.wait(remaining)

    def wait_for(self, marker, timeout=30.0, description='process', after=0):
        return self.wait_for_any((marker,), timeout, description, after)

    def wait_for_count(self, marker, count, timeout=30.0, description='process'):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                matches = sum(marker.lower() in line.lower() for line in self.lines)
                if matches >= count:
                    return
                if self.finished:
                    raise RuntimeError(
                        '%s exited after %d occurrences of %r; expected %d.\n%s' %
                        (description, matches, marker, count, self.tail())
                    )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        'Timed out waiting for %d occurrences of %r from %s.\n%s' %
                        (count, marker, description, self.tail())
                    )
                self.condition.wait(remaining)

    def tail(self):
        with self.condition:
            return ''.join(self.lines[-30:])

    def join(self, timeout=None):
        self.reader.join(timeout)
