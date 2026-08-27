import json, os, requests

TOKEN=os.environ.get("LINE_CHANNEL_ACCESS_TOKEN","").strip()
TO=os.environ.get("LINE_TO","").strip()
if not TOKEN or not TO:
    print("LINE credentials not configured; skipping notification.")
    raise SystemExit(0)

events=json.load(open("data/new_events.json",encoding="utf-8"))
targets=set(json.load(open("config/performers.json",encoding="utf-8")).get("notification",{}).get("performer_ids",[]))
events=[e for e in events if e.get("performerId") in targets]
if not events:
    print("No new tracked-performer events.")
    raise SystemExit(0)

lines=["【新しい出演情報】"]
for e in events[:10]:
    lines.append(f"・{e.get('date','')} {e.get('title','')}")
    if e.get("venue"): lines.append(f"  {e['venue']}")
    if e.get("startTime"): lines.append(f"  開演 {e['startTime']}")
    if e.get("sourceUrl"): lines.append(f"  {e['sourceUrl']}")
if len(events)>10: lines.append(f"…ほか{len(events)-10}件")
message="\n".join(lines)
r=requests.post("https://api.line.me/v2/bot/message/push",
    headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json"},
    json={"to":TO,"messages":[{"type":"text","text":message[:5000]}]},timeout=30)
r.raise_for_status()
print(f"LINE sent: {len(events)} events")
