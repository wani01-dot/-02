import json, os, re, sys, time
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin
import requests
from bs4 import BeautifulSoup

BASE="https://ticket.fany.lol"
SEARCH="https://ticket.fany.lol/search/event"
UA="Mozilla/5.0 (compatible; NansuiCalendarBot/1.0; +https://github.com/)"

def fetch(url):
    r=requests.get(url,headers={"User-Agent":UA,"Accept-Language":"ja,en;q=0.8"},timeout=30)
    r.raise_for_status()
    return r.text

def clean(s):
    return re.sub(r"\s+"," ",s or "").strip()

def parse_date(s):
    m=re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",s)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None

def event_links(html):
    soup=BeautifulSoup(html,"html.parser")
    out=[]
    for a in soup.find_all("a",href=True):
        href=a["href"]
        if "/event/detail/" not in href: continue
        url=urljoin(BASE,href).split("#")[0]
        if url not in out: out.append(url)
    return out

def extract_result_blocks(html, performer_name):
    soup=BeautifulSoup(html,"html.parser")
    found=[]
    # FANY's search result layout has a title, venue and 出演 section. We locate links and walk up.
    for a in soup.find_all("a",href=True):
        if "/event/detail/" not in a["href"]: continue
        url=urljoin(BASE,a["href"]).split("#")[0]
        node=a
        best=None
        for _ in range(7):
            node=node.parent
            if not node: break
            text=clean(node.get_text(" ",strip=True))
            if "出演" in text and performer_name in text and re.search(r"20\d{2}/\d{1,2}/\d{1,2}",text):
                best=text
                break
        if best:
            found.append((url,best))
    # fallback: use all detail links and let detail-page verification decide
    if not found:
        found=[(u,"") for u in event_links(html)]
    dedup={}
    for u,t in found: dedup[u]=t
    return list(dedup.items())

def parse_detail(url, html, performer):
    soup=BeautifulSoup(html,"html.parser")
    text=clean(soup.get_text(" ",strip=True))
    if performer not in text: return []
    # Prefer actual "日時" fields. Do not collect application-period dates or notice dates.
    date_hits=re.findall(r"日時\s*(20\d{2}/\d{1,2}/\d{1,2})",text)
    dates=list(dict.fromkeys(date_hits))
    if not dates:
        dates=list(dict.fromkeys(re.findall(r"20\d{2}/\d{1,2}/\d{1,2}",text)[:1]))
    # Find the public event title from og:title/title.
    title=""
    og=soup.find("meta",property="og:title")
    if og and og.get("content"): title=clean(og["content"])
    if not title and soup.title: title=clean(soup.title.get_text())
    title=re.sub(r"\s*[|｜].*$","",title).strip()
    venue=""
    vm=re.search(r"会場名\s+(.{1,80}?)(?=\s+(?:出演者|出演|注意事項|問合せ先))",text)
    if vm: venue=clean(vm.group(1))
    # Extract time near each date.
    out=[]
    for ds in dates:
        d=parse_date(ds)
        if not d: continue
        pos=text.find(ds)
        chunk=text[pos:pos+180]
        tm=re.search(r"開場\s*(\d{1,2}:\d{2})\s*開演\s*(\d{1,2}:\d{2})",chunk)
        start=tm.group(2) if tm else ""
        # A detail page can contain old notice dates. Keep only dates in the event calendar area where possible.
        out.append({"date":d,"title":title,"venue":venue,"startTime":start,"sourceUrl":url})
    return out

def scrape_performer(p):
    q=p["name"]
    params={"keywords":q,"search_type":"search_string"}
    html=fetch(SEARCH+"?"+urlencode(params))
    blocks=extract_result_blocks(html,q)
    events=[]
    for url,_ in blocks:
        try:
            detail=fetch(url)
            events += parse_detail(url,detail,q)
            time.sleep(0.25)
        except Exception as e:
            print("detail error",url,e,file=sys.stderr)
    # dedupe
    unique={}
    for e in events:
        key=(p["id"],e["date"],e["title"],e["venue"],e["startTime"])
        e["performerId"]=p["id"]; unique[key]=e
    return list(unique.values())

def main():
    cfg=json.load(open("performers.json", encoding="utf-8"))
    old=json.load(open("events.json",encoding="utf-8"))
    all_events=[]
    for p in cfg["performers"]:
        if "fany" not in p.get("sources",[]): continue
        print("scraping",p["name"])
        all_events += scrape_performer(p)
    # Preserve manual events? Remote data file is intentionally FANY-only.
    # Keep future/past records returned by FANY; the site itself determines availability.
    performers=cfg["performers"]
    payload={"syncedAt":datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),"performers":performers,"events":all_events}
    json.dump(payload,open("events.new.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
    # New-event detection for notifications: compare stable event IDs based on performer/date/title/venue/time.
    def key(e): return "|".join([e.get("performerId",""),e.get("date",""),e.get("title",""),e.get("venue",""),e.get("startTime","")])
    oldkeys={key(e) for e in old.get("events",[])}
    new=[e for e in all_events if key(e) not in oldkeys]
    json.dump(new,open("data/new_events.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print(f"events={len(all_events)} new={len(new)}")
if __name__=="__main__": main()
