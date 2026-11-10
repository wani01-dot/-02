import argparse, json, re, uuid
from pathlib import Path
p=Path("manual_events.json")
parser=argparse.ArgumentParser()
for field in ("title","date","time","venue","performers","url","category"):
    parser.add_argument("--"+field,required=(field in ("title","date","time","performers","category")),default="")
a=parser.parse_args()
if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",a.date): raise SystemExit("日付はYYYY-MM-DD")
if not re.fullmatch(r"\d{2}:\d{2}",a.time): raise SystemExit("時刻はHH:MM")
from datetime import datetime
datetime.strptime(a.date+" "+a.time,"%Y-%m-%d %H:%M")
if a.category not in ("live","stream"): raise SystemExit("category must be live or stream")
if a.url and not a.url.startswith(("https://","http://")): raise SystemExit("URLが不正です")
ids=[]
for word,pid in (("めぞん","maison"),("ピュート","pyuto"),("軟水","nansui")):
    if word in a.performers: ids.append(pid)
if not ids: raise SystemExit("出演者にめぞん・ピュート・軟水のいずれかを含めてください")
data=json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"events":[]}
events=data if isinstance(data,list) else data.get("events",[])
for pid in ids:
    key=(a.date,a.time,a.title,pid,a.category)
    if any((e.get("date"),e.get("startTime"),e.get("title"),e.get("performerId"),e.get("category","live"))==key for e in events):
        print("同一の手動公演は登録済み",key);continue
    e={"id":"manual-"+uuid.uuid4().hex[:12],"date":a.date,"startTime":a.time,"title":a.title,"venue":a.venue,"performerId":pid,"performerIds":ids,"performersText":a.performers,"source":"manual","sourceUrl":a.url,"category":a.category,"ticketOptions":[],"publishedVia":"manual"}
    events.append(e)
p.write_text(json.dumps({"events":events},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("手動公演数:",len(events))
