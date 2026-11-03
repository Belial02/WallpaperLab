#!/usr/bin/env python3
"""Compile the UTF-8 translation catalog; reject missing cells or unsafe formats."""
import json,pathlib,re,sys
source,target=map(pathlib.Path,sys.argv[1:]);data=json.loads(source.read_text());pattern=re.compile(r'%(?:[-+#0 ]*\d*(?:\.\d+)?)?[diuoxXfFeEgGsc]')
for key,values in data.items():
 if len(values)!=21 or not all(isinstance(v,str) and v for v in values):raise SystemExit('Incomplete translation: '+key)
 formats=pattern.findall(key)
 for text in values:
  if pattern.findall(text)!=formats:raise SystemExit('Mismatched format: '+key+' -> '+text)
raw=json.dumps(data,ensure_ascii=False,separators=(',',':'))
if ')translations"' in raw:raise SystemExit('Invalid raw-string delimiter')
rules=json.loads((source.parent/'ui_messages.json').read_text())
for key in rules.values():
 if key not in data:raise SystemExit('Untranslated diagnostic: '+key)
rules_raw=json.dumps(rules,ensure_ascii=False,separators=(',',':'))
if ')messages"' in rules_raw:raise SystemExit('Invalid message delimiter')
target.parent.mkdir(parents=True,exist_ok=True);target.write_text('#pragma once\nstatic const char* translationsData=R"translations('+raw+')translations";\nstatic const char* uiMessagesData=R"messages('+rules_raw+')messages";\n')
