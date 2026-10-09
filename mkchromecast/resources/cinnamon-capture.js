// Experimental adapter for Cinnamon 6.4's public org.Cinnamon.Eval method.
// Called with JSON data by screencast_cinnamon.py; no user JavaScript/pipeline.
// Own a separate Recorder. Never change Main.screenRecorder or GSettings.
function mkchromecastCapture(config) {
    const GLib = imports.gi.GLib;
    const Main = imports.ui.main;
    const slot = '_mkchromecastCaptureV1';
    let state = global[slot];
    const monitorKey = () => {
        const m = Main.layoutManager.primaryMonitor;
        return m ? JSON.stringify([m.x, m.y, m.width, m.height]) : null;
    };

    function stop() {
        if (!state)
            return;
        if (state.timer) {
            GLib.source_remove(state.timer);
            state.timer = 0;
        }
        try {
            if (state.recorder.is_recording())
                state.recorder.close();
        } finally {
            if (global[slot] === state)
                delete global[slot];
        }
    }

    if (config.action === 'start') {
        if (state)
            throw new Error('Another MKChromecast Cinnamon capture is active');
        const Cinnamon = imports.gi.Cinnamon;
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            throw new Error('Cinnamon has no primary monitor');
        const recorder = new Cinnamon.Recorder({stage: global.stage, display: global.display});
        recorder.set_framerate(config.fps);
        recorder.set_area(monitor.x, monitor.y, monitor.width, monitor.height);
        recorder.set_pipeline(config.pipeline);
        state = {token: config.token, recorder: recorder, timer: 0,
                 expires: GLib.get_monotonic_time() + 20000000,
                 monitor: monitorKey()};
        global[slot] = state;
        try {
            const result = recorder.record();
            if (!(Array.isArray(result) ? result[0] : result))
                throw new Error('Cinnamon could not start the capture pipeline; check GStreamer plugins');
            state.timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
                if (GLib.get_monotonic_time() > state.expires ||
                    monitorKey() !== state.monitor || !recorder.is_recording()) {
                    state.timer = 0;
                    stop();
                    return GLib.SOURCE_REMOVE;
                }
                return GLib.SOURCE_CONTINUE;
            });
        } catch (error) {
            stop();
            throw error;
        }
        return true;
    }
    // A stale process must never stop or refresh somebody else's recorder.
    if (!state || state.token !== config.token) {
        if (config.action === 'stop')
            return false;
        throw new Error('Cinnamon capture has stopped; restart screen sharing');
    }
    if (config.action === 'stop') {
        stop();
        return true;
    }
    if (config.action === 'heartbeat') {
        if (!state.recorder.is_recording() || monitorKey() !== state.monitor) {
            stop();
            throw new Error('Cinnamon capture stopped or the primary monitor changed');
        }
        state.expires = GLib.get_monotonic_time() + 20000000;
        return true;
    }
    throw new Error('Unknown capture action');
}
