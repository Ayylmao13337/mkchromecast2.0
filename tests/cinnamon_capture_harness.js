// Run the real bridge against a deterministic fake compositor, no desktop needed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
let now = 0, closes = 0, starts = 0, fail = false, active = false;
const timers = new Map();
let nextId = 0;
const monitor = {index: 1, x: 1920, y: 0, width: 1920, height: 1200};
const other = {index: 0, x: 0, y: 0, width: 1920, height: 1080};
let lastArea;
class Recorder {
    set_framerate(fps) { assert.equal(fps, 25); }
    set_area(...area) { lastArea = area; }
    set_pipeline(pipeline) { assert.equal(pipeline, 'fixture'); }
    record() { starts++; active = !fail; return [!fail, null]; }
    is_recording() { return active; }
    close() { closes++; active = false; }
}
const context = {
    global: {stage: {}, display: {}},
    imports: {
        gi: {Cinnamon: {Recorder}, GLib: {
            PRIORITY_DEFAULT: 0, SOURCE_REMOVE: false, SOURCE_CONTINUE: true,
            get_monotonic_time: () => now,
            timeout_add_seconds: (_p, _s, fn) => { timers.set(++nextId, fn); return nextId; },
            source_remove: id => timers.delete(id),
        }},
        ui: {main: {layoutManager: {primaryMonitor: monitor, monitors: [other, monitor]}}},
    },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../mkchromecast/resources/cinnamon-capture.js'), 'utf8'), context);
const invoke = (action, token='owner') => context.mkchromecastCapture({action, token, fps: 25, pipeline: 'fixture'});
const inventory = invoke('list');
assert.equal(inventory.length, 2);
assert.equal(inventory[0].id, '0');
assert.equal(inventory[1].primary, true);
assert.equal(starts, 0);
invoke('start');
assert.deepEqual(lastArea, [1920, 0, 1920, 1200]);
assert.equal(starts, 1);
assert.throws(() => invoke('start', 'other'), /Another/);
assert.equal(invoke('stop', 'other'), false);
assert.equal(closes, 0);
now = 19000000;
invoke('heartbeat');
assert.equal([...timers.values()][0](), true);
now = 40000000;
assert.equal([...timers.values()][0](), false);
timers.clear(); // GLib removes the source after SOURCE_REMOVE.
assert.equal(closes, 1);
assert.equal(invoke('stop'), false);
assert.throws(() => invoke('heartbeat'), /stopped/);
fail = true;
assert.throws(() => invoke('start'), /could not start/);
assert.equal(context.global._mkchromecastCaptureV1, undefined);
fail = false;
invoke('start');
monitor.width = 1280;
assert.throws(() => invoke('heartbeat'), /monitor changed/);
assert.equal(closes, 2);
assert.equal(timers.size, 0);
context.mkchromecastCapture({action: 'start', token: 'owner', screen: '0', fps: 25, pipeline: 'fixture'});
assert.deepEqual(lastArea, [0, 0, 1920, 1080]);
// Changing an unrelated primary monitor must not interrupt explicit selection.
monitor.width = 1600;
assert.equal(invoke('heartbeat'), true);
other.width = 1280;
assert.throws(() => invoke('heartbeat'), /monitor changed/);
assert.throws(() => context.mkchromecastCapture({action: 'start', token: 'owner', screen: '99'}), /Screen not found/);
