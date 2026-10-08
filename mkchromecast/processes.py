"""Owned subprocess pipelines with bounded diagnostics and deterministic cleanup."""
from collections import deque
import os
import shutil
import subprocess
import threading


class PipelineError(RuntimeError):
    pass


class OwnedPipeline:
    def __init__(self, command, producer=None, pass_fds=()):
        self.processes = []
        self.diagnostics = deque(maxlen=30)
        self._readers = []
        self._closed = False
        self._lock = threading.Lock()
        try:
            upstream = self._spawn(producer) if producer else None
            self.output = self._spawn(command, stdin=upstream.stdout if upstream else None,
                                      pass_fds=pass_fds)
            if upstream:
                upstream.stdout.close()
        except BaseException:
            self.close()
            raise

    def _spawn(self, command, **kwargs):
        if not isinstance(command, (list, tuple)) or not command:
            raise PipelineError("Encoder command must be a non-empty argument list")
        if shutil.which(command[0]) is None:
            raise PipelineError(f"Required program is not installed: {command[0]}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   bufsize=0, **kwargs)
        self.processes.append(process)
        reader = threading.Thread(target=self._drain, args=(process.stderr,), daemon=True)
        reader.start()
        self._readers.append(reader)
        return process

    def _drain(self, pipe):
        # Fixed-size chunks also bound memory if a tool prints no newline.
        try:
            while chunk := pipe.read(2048):
                self.diagnostics.append(chunk.decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            pass

    def read(self, size):
        try:
            data = os.read(self.output.stdout.fileno(), size)
        except (OSError, ValueError):
            if self._closed:
                return b""
            raise
        if not data and not self._closed:
            code = self.output.wait(timeout=5)
            if code:
                raise PipelineError(f"Encoder exited with status {code}. " + self.error_summary())
            for process in self.processes[:-1]:
                code = process.poll()
                if code not in (None, 0):
                    raise PipelineError(f"Source process exited with status {code}. " + self.error_summary())
        return data

    def error_summary(self):
        # Avoid exposing signed URLs/cookies from external tool diagnostics.
        import re
        text = "".join(self.diagnostics)[-4096:]
        return re.sub(r"https?://\S+", "<media URL>", text)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(self.processes):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        for reader in self._readers:
            reader.join(timeout=1)
