"""Loopback-only preview using the production Cinnamon capture/HTTP pipeline."""
import copy
import shutil
import threading

from mkchromecast.processes import OwnedPipeline


class LocalPreviewSession:
    def __init__(self, settings):
        self.settings = copy.copy(settings)
        self.settings.host = '127.0.0.1'
        self.settings.port = 0  # Server chooses a free local port.
        self.cancel = threading.Event()
        self.sink = self.pipeline = self.player = None
        self.finished = False

    def start(self):
        if shutil.which('ffplay') is None:
            raise ValueError('Local preview needs ffplay; on Mint install the ffmpeg package')
        try:
            from mkchromecast.pulseaudio import AudioSink
            from mkchromecast.video import main
            self.sink = AudioSink().start()
            self.settings.capture_device = self.sink.monitor
            self.pipeline = main(self.settings, cancel=self.cancel)
            if self.cancel.is_set():
                raise RuntimeError('Local preview cancelled')
            url = f'http://127.0.0.1:{self.pipeline.port}/stream'
            self.player = OwnedPipeline([
                'ffplay', '-hide_banner', '-loglevel', 'warning', '-nostats',
                '-fflags', 'nobuffer', '-flags', 'low_delay', '-framedrop',
                '-volume', '0', '-autoexit', '-window_title', 'MKChromecast local latency preview',
                '-x', '960', '-y', '540', url,
            ])
            print('LOCAL PREVIEW: no receiver connection; HTTP is bound to loopback only.', flush=True)
            print('Move the preview to a non-captured monitor. Compare the source clock with the clock inside the preview.', flush=True)
            print('Playback is muted; local decoder/display buffering is included. Wait 10 seconds before comparing. Close the preview or press Ctrl-C to stop.', flush=True)
            return self
        except BaseException:
            self.close()
            raise

    def check(self):
        self.pipeline.check()
        code = self.player.output.poll()
        if code is not None:
            if code != 0:
                raise RuntimeError('Local player failed: ' + self.player.error_summary())
            self.finished = True

    def close(self):
        self.cancel.set()
        errors = []
        for name in ('player', 'pipeline', 'sink'):
            resource = getattr(self, name)
            setattr(self, name, None)
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    errors.append(str(exc))
        if errors:
            print('Local preview cleanup warning: ' + '; '.join(errors), flush=True)
