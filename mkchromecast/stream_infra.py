"""HTTP serving and a cancellable child process owned by one casting session."""
from dataclasses import dataclass
import multiprocessing
import os
import queue
import signal
import shutil
import socketserver
import threading
import time
from typing import Callable, Optional, Union

import flask
from werkzeug.serving import ThreadedWSGIServer

from mkchromecast.processes import OwnedPipeline, PipelineError

FlaskViewReturn = Union[str, flask.Response]


@dataclass
class BackendInfo:
    name: Optional[str] = None
    path: Optional[str] = None


class FlaskServer:
    # Compatibility facade for the existing audio/video builders. Every server
    # lives in its own spawn process, so class state cannot cross sessions.
    _app = None
    _video_mode = None
    _pass_fds = ()
    _command_factory = None
    _producer = None
    _direct_file = None
    _cleanup = None

    @staticmethod
    def _init_common(video_mode):
        if FlaskServer._app is not None:
            raise RuntimeError("Flask Server can only be initialized once")
        FlaskServer._app = flask.Flask("mkchromecast")
        FlaskServer._video_mode = video_mode
        FlaskServer._slots = threading.BoundedSemaphore(1)
        FlaskServer._active = set()
        FlaskServer._active_lock = threading.Lock()
        FlaskServer._errors = queue.Queue()
        FlaskServer._producer = None
        FlaskServer._direct_file = None
        FlaskServer._cleanup = None
        FlaskServer._health_check = None
        FlaskServer._command_factory = None
        FlaskServer._pass_fds = ()
        FlaskServer._app.add_url_rule("/stream", view_func=FlaskServer._stream)
        FlaskServer._app.add_url_rule("/health", view_func=lambda: {"ready": True})
        FlaskServer._app.add_url_rule("/", view_func=FlaskServer._index)

        @FlaskServer._app.after_request
        def headers(response):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "Range"
            response.headers["Access-Control-Expose-Headers"] = "Content-Range, Accept-Ranges, Content-Length"
            response.headers["Cache-Control"] = "no-store"
            return response

    @staticmethod
    def init_audio(adevice, backend, bitrate, buffer_size, codec, command,
                   media_type, platform, samplerate, producer=None):
        FlaskServer._init_common(False)
        FlaskServer._command = command
        FlaskServer._producer = producer
        FlaskServer._media_type = media_type
        FlaskServer._chunk_size = buffer_size

    @staticmethod
    def init_video(chunk_size, media_type, command=None, pass_fds=None,
                   command_factory=None, direct_file=None, cleanup=None, health_check=None):
        if command is None and command_factory is None and direct_file is None:
            raise ValueError("init_video needs a command, command_factory or direct_file")
        FlaskServer._init_common(True)
        FlaskServer._chunk_size = max(8192, min(1024 * 1024, chunk_size))
        FlaskServer._command = command
        FlaskServer._pass_fds = pass_fds or ()
        FlaskServer._command_factory = command_factory
        FlaskServer._media_type = media_type
        FlaskServer._direct_file = direct_file
        FlaskServer._cleanup = cleanup
        FlaskServer._health_check = health_check

    @staticmethod
    def _index():
        tag = "video" if FlaskServer._video_mode else "audio"
        return f'<!doctype html><title>MKChromecast</title><{tag} controls src="/stream"></{tag}>'

    @staticmethod
    def _stream():
        if FlaskServer._direct_file:
            return flask.send_file(FlaskServer._direct_file,
                                   mimetype=FlaskServer._media_type, conditional=True)
        # HEAD checks metadata only. It must not prompt for capture or spawn encoders.
        if flask.request.method == "HEAD":
            return flask.Response(mimetype=FlaskServer._media_type)
        if not FlaskServer._slots.acquire(blocking=False):
            return flask.Response("This live stream already has a client", status=503,
                                  headers={"Retry-After": "1"})
        pipeline = None
        try:
            command = FlaskServer._command
            fds = FlaskServer._pass_fds
            if FlaskServer._command_factory:
                command, fds = FlaskServer._command_factory()
            try:
                pipeline = OwnedPipeline(command, producer=FlaskServer._producer, pass_fds=fds)
            finally:
                if FlaskServer._command_factory:
                    for fd in fds:
                        os.close(fd)
            with FlaskServer._active_lock:
                FlaskServer._active.add(pipeline)
        except Exception as exc:
            if pipeline:
                pipeline.close()
            FlaskServer._slots.release()
            FlaskServer._errors.put(str(exc))
            return flask.Response("Could not start the media pipeline", status=503)

        closed = threading.Event()
        close_lock = threading.Lock()

        def close():
            with close_lock:
                if closed.is_set():
                    return
                closed.set()
            pipeline.close()
            with FlaskServer._active_lock:
                FlaskServer._active.discard(pipeline)
            FlaskServer._slots.release()

        def chunks():
            try:
                while not closed.is_set():
                    data = pipeline.read(FlaskServer._chunk_size)
                    if not data:
                        break
                    yield data
            except PipelineError as exc:
                FlaskServer._errors.put(str(exc))
            finally:
                close()

        response = flask.Response(chunks(), mimetype=FlaskServer._media_type)
        response.call_on_close(close)
        return response

    @staticmethod
    def _stream_video():
        return FlaskServer._stream()

    @staticmethod
    def _stream_audio():
        return FlaskServer._stream()

    @staticmethod
    def close():
        if FlaskServer._app is None:
            return
        with FlaskServer._active_lock:
            active = list(FlaskServer._active)
        for pipeline in active:
            pipeline.close()
        if FlaskServer._cleanup:
            FlaskServer._cleanup()
            FlaskServer._cleanup = None


class StreamingHTTPServer(ThreadedWSGIServer):
    """Bind without HTTPServer's unnecessary blocking reverse-DNS lookup.

    The streaming URL already carries the selected interface address. Resolving
    a display hostname can delay readiness on macOS and disconnected networks.
    Keep Werkzeug's normal request handling, threading and socket activation.
    """

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.host
        self.server_port = self.server_address[1]


def _serve(flask_init, host, port, connection):
    """Spawn entrypoint; no inherited parser, Qt, GLib or socket state."""
    os.setsid()
    server = None
    try:
        flask_init()
        if not FlaskServer._direct_file and not FlaskServer._command_factory:
            for command in (FlaskServer._producer, FlaskServer._command):
                if command and shutil.which(command[0]) is None:
                    raise PipelineError(f"Required program is not installed: {command[0]}")
        server = StreamingHTTPServer(host, port, FlaskServer._app)
        server.timeout = 0.2
        connection.send(("ready", server.server_port))
        while True:
            if connection.poll():
                if connection.recv() == "stop":
                    break
            server.handle_request()
            if FlaskServer._health_check:
                FlaskServer._health_check()
            while not FlaskServer._errors.empty():
                connection.send(("error", FlaskServer._errors.get_nowait()))
    except (EOFError, BrokenPipeError):
        pass  # Parent has exited; close its media resources.
    except BaseException as exc:
        try:
            connection.send(("error", str(exc)))
        except (BrokenPipeError, EOFError):
            pass
    finally:
        FlaskServer.close()
        if server:
            server.server_close()
        connection.close()


class PipelineProcess:
    def __init__(self, flask_init: Callable, host: str, port: int, platform: str):
        ctx = multiprocessing.get_context("spawn")
        self._connection, child = ctx.Pipe()
        self._child_connection = child
        self._proc = ctx.Process(target=_serve, args=(flask_init, host, port, child))
        self._started = False
        self._closed = False
        self.port = port

    def start(self, timeout=330, cancel=None):
        self._proc.start()
        self._started = True
        self._child_connection.close()
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    raise PipelineError("Startup cancelled")
                if self._connection.poll(0.1):
                    kind, value = self._connection.recv()
                    if kind == "ready":
                        self.port = value
                        return self
                    raise PipelineError(value)
                if not self._proc.is_alive():
                    raise PipelineError("Streaming server exited during startup")
            raise PipelineError("Streaming startup timed out")
        except BaseException:
            self.close()
            raise

    def check(self):
        if self._closed:
            return
        if self._connection.poll():
            try:
                kind, value = self._connection.recv()
            except EOFError:
                raise PipelineError("Streaming server exited") from None
            if kind == "error":
                raise PipelineError(value)
        if not self._proc.is_alive():
            raise PipelineError("Streaming server exited")

    def pause(self):
        if self._started and self._proc.is_alive():
            os.killpg(self._proc.pid, signal.SIGSTOP)

    def resume(self):
        if self._started and self._proc.is_alive():
            os.killpg(self._proc.pid, signal.SIGCONT)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._started:
            try:
                self.resume()
                self._connection.send("stop")
            except (OSError, EOFError, BrokenPipeError):
                pass
            self._proc.join(timeout=5)
            if self._proc.is_alive():
                # This child created its own session; only our process group is affected.
                try:
                    os.killpg(self._proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    self._proc.terminate()
                self._proc.join(timeout=2)
                if self._proc.is_alive():
                    try:
                        os.killpg(self._proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        self._proc.kill()
                    self._proc.join(timeout=2)
        self._connection.close()
        self._child_connection.close()
