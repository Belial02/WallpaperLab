#!/usr/bin/env python3
"""Opt-in desktop regression for monitor controls, zoom-out, palette source and UI lifetime.

Uses disposable XDG state, managed media and owned renderers. Requires Hyprland,
two outputs, grim, ydotool and the optional Caelestia palette dependencies.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import time
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument('--desktop', action='store_true')
p.add_argument('--app', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
if not a.desktop:
    p.error('--desktop required: exercises a disposable window and background surfaces')
app, out = a.app.resolve(), a.output.resolve()
out.mkdir(parents=True, exist_ok=True)
root = Path(__file__).resolve().parents[1]
helper = root / 'assets/caelestia_palette.py'
env = os.environ | {f'XDG_{k}_HOME': str(out / k.lower()) for k in ['CONFIG', 'STATE', 'DATA', 'CACHE']}
socket = Path(os.environ['XDG_RUNTIME_DIR']) / f'wallpaper-monitor-test-{os.getpid()}.sock'
env |= {'WALLPAPER_LAB_CAELESTIA_HELPER': str(helper), 'WALLPAPER_LAB_UI_STATE': str(out / 'ui.json'), 'YDOTOOL_SOCKET': str(socket)}
config = out / 'config/wallpaper-lab/settings.json'
config.parent.mkdir(parents=True, exist_ok=True)
steam = out / 'empty-steam'
steam.mkdir(exist_ok=True)
config.write_text(json.dumps({'mode': 'single', 'screen': 0, 'fps': 30, 'muted': True, 'fullscreen_policy': 0,
                             'transition_type': 0, 'workshop_path': str(steam), 'caelestia_enabled': True}))
log = (out / 'desktop.log').open('w')
ui = daemon = None
results = {}

def run(*args, **kwargs):
    return subprocess.check_output([str(x) for x in args], env=env, text=True, timeout=45, **kwargs)

def wait(fn, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = fn()
            if value:
                return value
        except (FileNotFoundError, json.JSONDecodeError, StopIteration):
            pass
        time.sleep(.08)
    raise AssertionError('Condition timeout')

def read(file):
    return json.loads(file.read_text())

def preferences(**values):
    data = read(config)
    data.update(values)
    config.write_text(json.dumps(data))

def geometry():
    return read(out / 'ui.json.geometry')

def window():
    return next((w for w in json.loads(run('hyprctl', 'clients', '-j')) if w['pid'] == ui.pid), None)

def click(x, y):
    w = window()
    run('hyprctl', 'eval', f'hl.dispatch(hl.dsp.focus({{window="pid:{ui.pid}"}}))')
    run('hyprctl', 'eval', f'hl.dispatch(hl.dsp.cursor.move({{x={round(w["at"][0]+x)},y={round(w["at"][1]+y)},relative=false}}))')
    time.sleep(.15)
    run('ydotool', 'click', '0xC0')
    time.sleep(.3)

def choose(id, index):
    click(*geometry()['choices'][str(id)]['control'])
    wait(lambda: geometry()['choice_open'] == id)
    click(*geometry()['choices'][str(id)]['options'][index])
    wait(lambda: geometry()['choice_open'] != id)

def palette():
    return read(out / 'state/caelestia/scheme.json')

personal = Path.home() / '.local/bin/wallpaper-lab'
before = subprocess.check_output([str(personal), '--status'])
personal_scheme = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'caelestia/scheme.json'
def fingerprint():
    return hashlib.sha256(personal_scheme.read_bytes()).hexdigest() if personal_scheme.exists() else None
original_fingerprint = fingerprint()
paths = []
for name, colour in [('red', '#df3455'), ('blue', '#246dc0')]:
    file = out / f'{name}.png'
    Image.new('RGB', (1280, 720), colour).save(file)
    paths.append(json.loads(run(app, '--import', file))[0])
original = {'name': 'test-original', 'colours': {'primary': '112233', 'surface': '000000'}}
scheme = out / 'state/caelestia/scheme.json'
scheme.parent.mkdir(parents=True, exist_ok=True)
scheme.write_text(json.dumps(original))
try:
    displays = json.loads(run(app, '--display-layout'))['outputs']
    assert len(displays) >= 2
    assert all(d['name'] and d['model'] for d in displays)
    results['monitor_models_and_connectors_available'] = True
    run(app, '--caelestia-source', displays[0]['name'])
    run(app, '--apply', paths[0])
    red_palette = palette()
    preferences(screen=1)
    run(app, '--apply', paths[1])
    assert palette() == red_palette, 'Applying another monitor replaced the chosen colour source'
    run(app, '--caelestia-source', displays[1]['name'])
    assert palette()['colours']['primary'] != red_palette['colours']['primary']
    assert read(config)['caelestia_output'] == displays[1]['name']
    results['palette_source_is_independent_and_persistent'] = True
    # Each output owns a different renderer; a failed replacement preserves both.
    running = json.loads(run(app, '--status'))
    assert len(running['outputs']) == 2
    owned_pids = [r['pid'] for r in running['outputs'].values()]
    broken = out / 'broken'
    broken.mkdir(exist_ok=True)
    (broken / 'project.json').write_text(json.dumps({'title': 'Broken', 'type': 'scene', 'file': 'scene.json'}))
    (broken / 'scene.json').write_text('{invalid')
    bad = subprocess.run([str(app), '--apply', str(broken)], env=env | {'WALLPAPER_LAB_LIBRARY': str(out)}, capture_output=True, timeout=45)
    assert bad.returncode != 0
    assert json.loads(run(app, '--status'))['outputs'] == running['outputs']
    results['failed_replacement_preserves_both_renderers'] = True
    # Check real framebuffer padding, not only the stored slider value.
    profiles = out / 'config/wallpaper-lab/wallpaper_profiles.json'
    data = read(profiles) if profiles.exists() else {}
    data[paths[1]] = {'position': {'x': 0, 'y': 0, 'zoom': .5}}
    profiles.write_text(json.dumps(data))
    plan = json.loads(run(app, '--plan', paths[1]))
    assert json.loads(plan[plan.index('--lab-position') + 1])['zoom'] == .5
    feed = Path(plan[plan.index('--lab-feed-dir') + 1])
    frame = feed / ('frame-' + displays[1]['name'] + '.bin')
    def shrink_frame():
        (feed / 'request.json').write_text(json.dumps({'path': paths[1], 'output': displays[1]['name']}))
        raw = frame.read_bytes()
        magic, pid, w, h, seq = struct.unpack('=5I', raw[:20])
        assert magic == 0x574c4631
        image = Image.frombytes('RGB', (w, h), raw[20:])
        corner = image.getpixel((w//10, h//10))
        center = image.getpixel((w//2, h//2))
        return image if max(corner) < 8 and center[2] > 100 else None
    wait(lambda: feed.exists())
    image = wait(shrink_frame)
    image.save(out / 'zoom-50-percent.png')
    results['zoom_out_has_black_padding_and_visible_center'] = True
    daemon = subprocess.Popen(['ydotoold', '--socket-path=' + str(socket)], stdout=log, stderr=log)
    wait(socket.exists)
    time.sleep(1)
    ui = subprocess.Popen([str(app), '--display-settings'], env=env, stdout=log, stderr=log)
    wait(window)
    wait(lambda: (out / 'ui.json.geometry').exists())
    for arg in [[], ['--display-settings'], ['--appearance-settings'], ['--workshop']]:
        second = subprocess.run([str(app), *arg], env=env, stdout=log, stderr=log, timeout=15)
        assert second.returncode == 0
    assert ui.poll() is None
    assert len([w for w in json.loads(run('hyprctl', 'clients', '-j')) if w['pid'] in [ui.pid]]) == 1
    assert json.loads(run(app, '--status'))['outputs'] == running['outputs']
    results['duplicate_launches_exit_without_affecting_renderers'] = True
    choose(4, 0)
    wait(lambda: geometry()['screen'] == 0)
    choose(4, 1)
    wait(lambda: geometry()['screen'] == 1)
    results['two_monitor_selector_uses_named_dropdown'] = True
    w = window()
    run('grim', '-g', f'{w["at"][0]},{w["at"][1]} {w["size"][0]}x{w["size"][1]}', out / 'monitor-selection.png')
    click(*geometry()['settings_tabs'][7])
    choose(80, 0)
    wait(lambda: read(config)['caelestia_output'] == displays[0]['name'])
    wait(lambda: palette()['colours']['primary'] == red_palette['colours']['primary'])
    choose(80, 1)
    wait(lambda: read(config)['caelestia_output'] == displays[1]['name'])
    wait(lambda: palette()['colours']['primary'] != red_palette['colours']['primary'])
    results['palette_source_dropdown_updates_global_palette'] = True
    w = window()
    run('grim', '-g', f'{w["at"][0]},{w["at"][1]} {w["size"][0]}x{w["size"][1]}', out / 'caelestia-source.png')
    # Close settings, then use the explicit stop action in the main header.
    run('ydotool', 'key', '1:1', '1:0')
    time.sleep(.35)
    click(*geometry()['stop_and_quit'])
    ui.wait(timeout=20)
    assert ui.returncode == 0
    assert not json.loads(run(app, '--status'))['alive']
    assert all(not Path(f'/proc/{pid}/exe').exists() for pid in owned_pids)
    assert palette() == original
    results['stop_and_quit_stops_all_outputs_and_restores_palette'] = True
    # Kernel lock release also permits launching again after an abrupt termination.
    ui = subprocess.Popen([str(app)], env=env, stdout=log, stderr=log)
    wait(window)
    ui.kill()
    ui.wait(timeout=8)
    ui = subprocess.Popen([str(app)], env=env, stdout=log, stderr=log)
    wait(window)
    results['selector_reopens_after_exit_and_crash'] = True
finally:
    if ui and ui.poll() is None:
        w = window()
        if w:
            run('grim', '-g', f'{w["at"][0]},{w["at"][1]} {w["size"][0]}x{w["size"][1]}', out / 'last-ui.png')
        ui.terminate()
        ui.wait(timeout=10)
    if daemon:
        daemon.terminate()
        daemon.wait(timeout=8)
    socket.unlink(missing_ok=True)
    run(app, '--stop')
    log.close()
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
assert subprocess.check_output([str(personal), '--status']) == before
assert fingerprint() == original_fingerprint
results['personal_renderers_and_palette_preserved'] = True
(out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
