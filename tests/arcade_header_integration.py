#!/usr/bin/env python3
"""Opt-in visual regression for header spacing, physical arcade buttons and motion.

Uses a read-only fixture catalog and isolated XDG state. Requires an unlocked
Hyprland session and grim. Does not apply wallpapers or change personal settings.
"""
import argparse, json, os, pathlib, subprocess, time
from PIL import Image, ImageChops

p = argparse.ArgumentParser()
p.add_argument('--app', type=pathlib.Path, required=True)
p.add_argument('--output', type=pathlib.Path, required=True)
a = p.parse_args()
app, out = a.app.resolve(), a.output.resolve()
out.mkdir(parents=True, exist_ok=True)
root = pathlib.Path(__file__).resolve().parents[1]
config = out / 'config/wallpaper-lab'
config.mkdir(parents=True, exist_ok=True)
library = out / 'library'
library.mkdir(exist_ok=True)
env = os.environ | {f'XDG_{kind}_HOME': str(out / kind.lower()) for kind in ['CONFIG', 'STATE', 'DATA', 'CACHE']}
env |= {'WALLPAPER_LAB_LIBRARY': str(library), 'WALLPAPER_LAB_UI_READ_ONLY': '1', 'WALLPAPER_LAB_UI_STATE': str(out / 'ui.json'),
        'LD_LIBRARY_PATH': ':'.join([str(root / 'local/sysroot/usr/lib'), str(root / 'build-engine/output'), os.environ.get('LD_LIBRARY_PATH', '')])}
for index, colour in enumerate(['#273c82', '#ab3469', '#146b62']):
    fixture = library / str(index)
    fixture.mkdir(exist_ok=True)
    (fixture / 'project.json').write_text(json.dumps({'type': 'web', 'title': 'Arcade visual fixture ' + str(index), 'file': 'index.html', 'preview': 'preview.png'}))
    (fixture / 'index.html').write_text('<html>Read-only UI fixture</html>')
    Image.new('RGB', (480, 270), colour).save(fixture / 'preview.png')
ui = None
log = (out / 'log').open('w')
results = {}
def run(*args):
    return subprocess.check_output([str(x) for x in args], env=env, text=True, timeout=25)
def wait(fn):
    end = time.monotonic() + 20
    while time.monotonic() < end:
        try:
            found = fn()
            if found: return found
        except (FileNotFoundError, json.JSONDecodeError): pass
        if ui and ui.poll() is not None: raise AssertionError('UI exited: ' + (out / 'log').read_text()[-2000:])
        time.sleep(.08)
    raise AssertionError('UI condition timeout')
def read(file): return json.loads(file.read_text())
def geometry(): return read(out / 'ui.json.geometry')
def window(): return next((w for w in json.loads(run('hyprctl', 'clients', '-j')) if w['pid'] == ui.pid), None)
def overlap(a, b): return min(a[0]+a[2], b[0]+b[2]) > max(a[0], b[0]) and min(a[1]+a[3], b[1]+b[3]) > max(a[1], b[1])
def capture(name):
    w = window(); file = out / (name + '.png')
    run('grim', '-g', f'{w["at"][0]},{w["at"][1]} {w["size"][0]}x{w["size"][1]}', file)
    return Image.open(file).convert('RGB')
def resize(width):
    run('hyprctl', 'eval', f'hl.dispatch(hl.dsp.window.resize({{window="pid:{ui.pid}",x={width},y=900,relative=false}}));hl.dispatch(hl.dsp.window.center({{window="pid:{ui.pid}"}}))')
    wait(lambda: abs(window()['size'][0]-width)<2 and abs(geometry()['power_rect'][0] - (window()['size'][0]-68)) < 2)
    time.sleep(1.1)
installed = pathlib.Path.home() / '.local/bin/wallpaper-lab'
before = subprocess.check_output([installed, '--status'])
monitor = max(json.loads(run('hyprctl', 'monitors', '-j')), key=lambda m: m['width'])
try:
    for design in range(4):
        (config / 'settings.json').write_text(json.dumps({'theme_scoped_v3': True, 'ui_design': design, 'ui_theme': [14,0,3,17][design], 'language': 'en', 'reduce_motion': True}))
        ui = subprocess.Popen([app], env=env, stdout=log, stderr=log)
        wait(window)
        run('hyprctl', 'eval', f'hl.dispatch(hl.dsp.window.move({{window="pid:{ui.pid}",workspace="{monitor["activeWorkspace"]["id"]}",follow=false}}));hl.dispatch(hl.dsp.window.float({{action="on",window="pid:{ui.pid}"}}))')
        wait(lambda: read(out / 'ui.json.style')['design'] == design)
        for width in [1000, 1440, min(2200, monitor['width']-80)]:
            resize(width)
            g = geometry(); power = g['power_rect']; decoration = g['header_decoration']
            assert power[2:4] == [44,38]
            if decoration[2] > 0: assert not overlap(power, decoration)
            for key in ['library','carousel','workshop','settings']:
                cx, cy = g['header'][key]
                assert cx+22 < power[0]-4, (design, width, key, power)
            capture(f'design-{design}-width-{width}')
        results[f'header_design_{design}_three_widths'] = True
        if design == 3:
            resize(1440)
            lane = geometry()['header_decoration']; x,y,w,h = lane
            box = tuple(round(v) for v in (x,y,x+w,y+h))
            a1 = capture('arcade-still-a'); time.sleep(.45); a2 = capture('arcade-still-b')
            assert ImageChops.difference(a1.crop(box), a2.crop(box)).getbbox() is None
            run(app, '--ui-option', 'reduce_motion', 0)
            wait(lambda: not read(config / 'settings.json')['reduce_motion'])
            time.sleep(.5)
            a1 = capture('arcade-moving-a'); time.sleep(.45); a2 = capture('arcade-moving-b')
            assert ImageChops.difference(a1.crop(box), a2.crop(box)).getbbox() is not None
            results['arcade_characters_move_and_reduced_motion_freezes'] = True
            # Capture the round power control under the pointer for visual inspection.
            power = geometry()['power_rect']; win = window()
            run('hyprctl', 'eval', f'hl.dispatch(hl.dsp.focus({{window="pid:{ui.pid}"}}));hl.dispatch(hl.dsp.cursor.move({{x={round(win["at"][0]+power[0]+power[2]/2)},y={round(win["at"][1]+power[1]+power[3]/2)},relative=false}}))')
            time.sleep(.3); capture('arcade-power-hover')
        ui.terminate(); ui.wait(12); ui = None
    assert not (out / 'state/wallpaper-lab/running.json').exists()
finally:
    if ui and ui.poll() is None: ui.terminate(); ui.wait(12)
    log.close()
    (out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
assert subprocess.check_output([installed, '--status']) == before
results['personal_renderer_preserved'] = True
(out / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
