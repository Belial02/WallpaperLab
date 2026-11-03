#!/usr/bin/env python3
"""Render a deterministic Steam init failure in every locale using a fake SDK.

No Steam account, network requests, downloads or personal settings are used.
Uses a hidden native window and framebuffer capture; needs an OpenGL display.
"""
import argparse, json, os, pathlib, shutil, subprocess, time
p=argparse.ArgumentParser();p.add_argument('--app',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
app,out=a.app.resolve(),a.output.resolve();out.mkdir(parents=True,exist_ok=True);root=pathlib.Path(__file__).resolve().parents[1]
config=out/'config/wallpaper-lab';config.mkdir(parents=True,exist_ok=True);library=out/'library';library.mkdir(exist_ok=True)
source=out/'fake-steam.c';source.write_text('#include <string.h>\nint SteamAPI_InitFlat(char* error){strcpy(error,"Cannot create IPC pipe to Steam client process. Steam is probably not running.");return 1;}\n')
mock=out/'libfake-steam.so';subprocess.run(['cc','-shared','-fPIC',str(source),'-o',str(mock)],check=True)
codes=['it','en','de','es','fr','pt','nl','pl','ro','sv','zh-CN','zh-TW','ja','ko','hi','ru','ar','bn','id','tr','vi','ur']
key='Steam deve essere aperto con un account che possiede Wallpaper Engine.';catalog=json.loads((root/'src/translations.json').read_text())
env=os.environ|{f'XDG_{k}_HOME':str(out/k.lower())for k in ['CONFIG','STATE','DATA','CACHE']}
env|={'WALLPAPER_LAB_STEAM_API':str(mock),'WALLPAPER_LAB_LIBRARY':str(library),'WALLPAPER_LAB_I18N_TRACE':str(out/'message.json'),'WALLPAPER_LAB_UI_STATE':str(out/'ui.json'),'LD_LIBRARY_PATH':':'.join([str(root/'local/sysroot/usr/lib'),str(root/'build-engine/output'),os.environ.get('LD_LIBRARY_PATH','')])}
captures=out/'captures';captures.mkdir(exist_ok=True);env|={'WALLPAPER_LAB_UI_CAPTURE':str(captures),'WALLPAPER_LAB_UI_HIDDEN':'1'}
log=(out/'log').open('w');ui=None;results={};installed=pathlib.Path.home()/'.local/bin/wallpaper-lab';before=subprocess.check_output([installed,'--status'])
def run(*args):return subprocess.check_output([str(x)for x in args],env=env,text=True,timeout=30)
def wait(fn):
 end=time.monotonic()+20
 while time.monotonic()<end:
  try:
   result=fn()
   if result:return result
  except(FileNotFoundError,json.JSONDecodeError):pass
  assert ui.poll()is None
  time.sleep(.05)
 raise AssertionError('UI message timeout')
try:
 for index,code in enumerate(codes):
  (out/'message.json').unlink(missing_ok=True)
  (config/'settings.json').write_text(json.dumps({'theme_scoped_v3':True,'ui_design':3,'ui_theme':20,'language':code,'reduce_motion':True}))
  ui=subprocess.Popen([app,'--workshop'],env=env,stdout=log,stderr=log)
  wait(lambda:(out/'message.json').exists());data=json.loads((out/'message.json').read_text())
  expected=key if index==0 else catalog[key][index-1]
  assert data['language']==code and data['text'].startswith(expected),(code,data)
  assert 'Cannot create IPC'not in data['text']
  if index:assert not data['text'].startswith('Apri Steam')
  recorded=(out/'state/wallpaper-lab/diagnostics.log').read_text();assert 'Cannot create IPC pipe' in recorded
  # A locale switch must relocalize an already-stored worker error.
  if code=='en':
   run(app,'--ui-option','language',2)
   wait(lambda:json.loads((out/'message.json').read_text())['language']=='de')
   assert json.loads((out/'message.json').read_text())['text'].startswith(catalog[key][1])
   run(app,'--ui-option','language',1)
   wait(lambda:json.loads((out/'message.json').read_text())['language']=='en')
   results['stored_error_relocalizes_without_retry']=True
  native=captures/f'locale-{index}.png';wait(native.exists)
  shutil.copy2(native,out/(code+'.png'))
  results[code]={'rendered_message_localized':True,'raw_diagnostic_preserved_in_log':True}
  ui.terminate();ui.wait(12);ui=None
finally:
 if ui and ui.poll()is None:ui.terminate();ui.wait(12)
 log.close();(out/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
assert before==subprocess.check_output([installed,'--status'])
results['personal_renderer_preserved']=True;(out/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'locales':len(codes),'live_switch':True,'personal_renderer_preserved':True}))
