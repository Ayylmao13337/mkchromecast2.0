"""Isolated Linux Open Screen build. Does not install system packages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

OPENSCREEN = '8978b74badf042795c07fcf99d0a53dccbd3dcf6'
DEPOT_TOOLS = 'b184a46054cc2ca5e4eff2ebf4de3dff7603b6f0'
LIBRARIES = ['libavcodec', 'libavformat', 'libavutil', 'libswresample', 'opus', 'vpx', 'sdl2']
GN_ARGS = ('is_debug=false use_sysroot=false have_ffmpeg=true have_libopus=true '
           'have_libvpx=true have_libsdl2=true treat_warnings_as_errors=false')


def run(args, cwd, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=1800)


def checkout(url, revision, path):
    run(['git', 'init', str(path)], path.parent)
    run(['git', 'remote', 'add', 'origin', url], path)
    run(['git', 'fetch', '--depth=1', 'origin', revision], path)
    run(['git', 'checkout', '--detach', 'FETCH_HEAD'], path)


def instrument(source):
    """One explicit event after ANSWER validation; never implies TV playback."""
    needle = '  current_negotiation_ =\n      std::make_unique<SenderSession::ConfiguredSenders>(std::move(senders));'
    if source.count(needle) != 1:
        raise ValueError('Pinned OnNegotiated source changed; refusing to patch')
    return source.replace(needle, '  OSP_LOG_INFO << "MKCAST_EVENT negotiated";\n' + needle)


def build(root):
    for name in ('git', 'pkg-config', 'python3'):
        if shutil.which(name) is None:
            raise ValueError(f'Missing build prerequisite: {name}; see experimental/cast_streaming/README.md')
    versions = subprocess.check_output(['pkg-config', '--modversion', *LIBRARIES], text=True).splitlines()
    root = root.resolve()
    if root.exists():
        raise ValueError('Choose a new build directory; existing checkouts are never overwritten')
    root.mkdir(parents=True)
    depot = root / 'depot_tools'
    checkout('https://chromium.googlesource.com/chromium/tools/depot_tools.git', DEPOT_TOOLS, depot)
    env = dict(os.environ, PATH=str(depot) + os.pathsep + os.environ.get('PATH', ''),
               DEPOT_TOOLS_UPDATE='0', DEPOT_TOOLS_METRICS='0')
    (root / '.gclient').write_text('solutions = [{"name": "openscreen", "url": '
        '"https://chromium.googlesource.com/openscreen", "managed": False, "custom_deps": {}, '
        '"custom_vars": {"checkout_clang_coverage_tools": False}}]\n')
    run([str(depot / 'gclient'), 'sync', '--no-history', '--revision', 'openscreen@' + OPENSCREEN], root, env)
    source = root / 'openscreen'
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if actual != OPENSCREEN:
        raise ValueError('Unexpected Open Screen revision: ' + actual)
    target = source / 'cast/standalone_sender/looping_file_cast_agent.cc'
    patched = instrument(target.read_text())
    target.write_text(patched)
    run([str(source / 'buildtools/linux64/gn'), 'gen', 'out/mkcast', '--args=' + GN_ARGS], source, env)
    run([str(depot / 'autoninja'), '-C', 'out/mkcast', 'cast_sender', 'cast_receiver', 'openscreen_unittests'], source, env)
    output = source / 'out/mkcast'
    (output / 'mkcast-build.json').write_text(json.dumps(dict(
        openscreen=OPENSCREEN, depot_tools=DEPOT_TOOLS, gn_args=GN_ARGS,
        library_versions=dict(zip(LIBRARIES, versions)),
        instrumented_source_sha256=hashlib.sha256(patched.encode()).hexdigest()), indent=2))
    run([str(output / 'openscreen_unittests')], source, env)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        print(build(args.directory))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'Native build failed: {exc}\n')
