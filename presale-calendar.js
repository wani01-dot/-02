(() => {
  "use strict";
  const DAYS_TO_KEEP = 7;
  const COLORS = { maison:"#E74C3C",pyuto:"#F4C430",nansui:"#3498DB" };
  const NAMES = { maison:"めぞん",pyuto:"ピュート",nansui:"軟水" };
  let entries = [], category = "first", month = new Date();
  month = new Date(month.getFullYear(),month.getMonth(),1);
  const escape = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const dateKey = d => [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-");
  const timeText = d => `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
  const kind = p => {
    const s = [p.category,p.label,p.type].join(" ").toLowerCase();
    if (/抽選|先行|lottery|advance/.test(s) && !/先着|一般|first.?come/.test(s)) return "lottery";
    return "first";
  };
  function periods(e) {
    let list = Array.isArray(e.salePeriods) ? e.salePeriods : [];
    if (!list.length && e.saleStartAt) list=[{startAt:e.saleStartAt,endAt:e.saleEndAt,category:e.saleCategory,label:e.saleCategory}];
    for (const opt of (Array.isArray(e.ticketOptions)?e.ticketOptions:[])) {
      if (Array.isArray(opt.salePeriods)) list=list.concat(opt.salePeriods.map(p=>({...p, label:p.label||opt.name||opt.label})));
    }
    return list;
  }
  function normalize(e) {
    const url=e.sourceUrl||e.ticketUrl||e.url||"";
    const performerIds=Array.isArray(e.trackedPerformers)&&e.trackedPerformers.length?e.trackedPerformers:[e.performerId].filter(Boolean);
    return periods(e).map(p=>{
      const start=new Date(p.startAt||p.start||"");
      if (!Number.isFinite(start.getTime())) return null;
      const end=new Date(p.endAt||p.end||"");
      return {title:e.title||"公演名未設定",date:e.date||"",openTime:e.openTime||"",startTime:e.startTime||"",venue:e.venue||"",performersText:e.performersText||[],url:p.sourceUrl||url,
        performerIds, start, end:Number.isFinite(end.getTime())?end:null,
        label:p.label||p.name||(kind(p)==="lottery"?"抽選受付":"先着販売"),kind:kind(p)};
    }).filter(Boolean);
  }
  function unique(items) {
    const seen=new Map();
    for(const e of items) {
      // 同じ公演・同じ受付は統合。受付開始日時と方式が違えば別件。
      const key=[e.title.trim().replace(/\s+/g,""),e.date,e.start.getTime(),e.kind,e.label.trim()].join("|");
      if(!seen.has(key)) seen.set(key,e);
      else {
        const old=seen.get(key);
        old.performerIds=[...new Set([...old.performerIds,...e.performerIds])];
        if(!old.url && e.url) old.url=e.url;
        if((!old.label || old.label==="抽選受付" || old.label==="先着販売" || old.label==="advance") && e.label) old.label=e.label;
        if(!old.end && e.end) old.end=e.end;
        if(!old.openTime && e.openTime) old.openTime=e.openTime;
        if(!old.startTime && e.startTime) old.startTime=e.startTime;
        if(!old.venue && e.venue) old.venue=e.venue;
        const existing = Array.isArray(old.performersText)?old.performersText:[old.performersText];
        const incoming = Array.isArray(e.performersText)?e.performersText:[e.performersText];
        old.performersText=[...new Set([...existing,...incoming].filter(Boolean))];
      }
    }
    return [...seen.values()].sort((a,b)=>a.start-b.start);
  }
  function ensureView() {
    if(document.getElementById("presaleCalendarView"))return;
    const view=document.createElement("section");
    view.id="presaleCalendarView";
    view.className="presale-view";
    view.innerHTML=`<div class="presale-top"><h2>チケット発売カレンダー</h2><p>発売日・受付開始日ごとに表示</p></div>
      <div class="presale-filters"><button type="button" data-kind="first" class="selected">先着</button><button type="button" data-kind="lottery">抽選</button></div>
      <div class="presale-month"><button type="button" data-move="-1" aria-label="前月">‹</button><strong id="presaleMonthTitle"></strong><button type="button" data-move="1" aria-label="翌月">›</button></div>
      <div id="presaleRows" class="presale-rows"></div>
      <div id="presaleDetail" class="presale-detail-backdrop" hidden><section class="presale-detail-panel" role="dialog" aria-modal="true" aria-label="公演詳細"><button type="button" class="presale-detail-close" aria-label="閉じる">×</button><div id="presaleDetailContent"></div></section></div>`;
    const switcher=document.getElementById("calendarModeSwitch");
    switcher?.insertAdjacentElement("afterend",view);
    view.addEventListener("click",event=>{
      const card=event.target.closest(".presale-entry[data-index]");
      if(card && !event.target.closest("a")) { openDetail(Number(card.dataset.index)); return; }
      const button=event.target.closest("button");
      if(!button)return;
      if(button.classList.contains("presale-detail-close")) { closeDetail(); return; }
      if(button.dataset.kind) {
        category=button.dataset.kind;
        view.querySelectorAll("[data-kind]").forEach(b=>b.classList.toggle("selected",b.dataset.kind===category));
        render();
      }
      if(button.dataset.move) {
        month=new Date(month.getFullYear(),month.getMonth()+Number(button.dataset.move),1);
        render();
      }
    });
    view.addEventListener("keydown",event=>{if((event.key==="Enter"||event.key===" ") && event.target.matches(".presale-entry")){event.preventDefault();openDetail(Number(event.target.dataset.index));}if(event.key==="Escape")closeDetail();});
    view.querySelector("#presaleDetail").addEventListener("click",event=>{
      if(event.target.id==="presaleDetail")closeDetail();
    });
  }
  let shownEntries=[];
  function cleanNames(raw) {
    const list=Array.isArray(raw)?raw:[raw];
    return [...new Set(list.flatMap(x=>String(x||"").replace(/^\[|\]$/g,"").split(/[／/、,，]+/)).map(x=>x.replace(/^[\s'"\[\]]+|[\s'"\[\]]+$/g,"").trim()).filter(x=>x && x.length<=38 && !/[。！？!?：:『』「」]/.test(x) && !/(?:申込|枚数|座席|整理番号|公演数|チケット|受付|販売|先着|抽選|購入|注意事項|まで|可能|開演|開場|ご案内|料金|入場|詳細)/.test(x)))].join(" / ");
  }
  function closeDetail(){const d=document.getElementById("presaleDetail");if(d)d.hidden=true;}
  function openDetail(index){
    const e=shownEntries[index];if(!e)return;
    const panel=document.getElementById("presaleDetail");
    const names=cleanNames(e.performersText)||e.performerIds.map(id=>NAMES[id]).filter(Boolean).join(" / ");
    const url=/^https?:\/\//i.test(e.url)?e.url:"";
    const row=(label,value)=>`<div class="presale-info-row"><strong>${label}</strong><span>${escape(value||"情報未取得")}</span></div>`;
    document.getElementById("presaleDetailContent").innerHTML=`<h2>${escape(e.title)}</h2>
      ${row("開催日",e.date)}${row("開場",e.openTime)}${row("開演",e.startTime)}
      ${row("会場",e.venue)}${row("出演者",names)}${row("販売方式",e.label)}
      ${row("受付開始",`${dateKey(e.start)} ${timeText(e.start)}`)}
      ${e.end?row("受付終了",`${dateKey(e.end)} ${timeText(e.end)}`):""}
      ${url?`<a class="presale-detail-link" href="${escape(url)}" target="_blank" rel="noopener noreferrer">チケット情報を見る ↗</a>`:""}`;
    panel.hidden=false;
  }
  function render() {
    ensureView();
    const label=document.getElementById("presaleMonthTitle");
    const root=document.getElementById("presaleRows");
    if(!label||!root)return;
    label.textContent=`${month.getFullYear()}年${month.getMonth()+1}月`;
    const now=new Date();
    const filtered=entries.filter(e=>{
      const elapsed=now.getTime()-e.start.getTime();
      return e.kind===category && e.start.getFullYear()===month.getFullYear() && e.start.getMonth()===month.getMonth()
        && elapsed < DAYS_TO_KEEP*86400000;
    });
    shownEntries=filtered;
    const byDate=new Map();
    filtered.forEach(e=>{
      const key=dateKey(e.start);
      if(!byDate.has(key))byDate.set(key,[]);
      byDate.get(key).push(e);
    });
    if(!filtered.length) {
      root.innerHTML='<p class="presale-empty">この月の受付情報はありません。<small>販売日時が未取得の公演は表示されません。</small></p>';
      return;
    }
    root.innerHTML=[...byDate].map(([key,items])=>{
      const d=items[0].start;
      const weekday="日月火水木金土"[d.getDay()];
      return `<section class="presale-day"><div class="presale-date"><b>${d.getDate()}</b><span>${weekday}曜日</span></div><div class="presale-day-items">${items.map(e=>{
        const started=e.start<=now;
        const closed=started&&e.end&&e.end<now;
        const state=!started?"発売前":closed?"受付終了":e.kind==="lottery"?"受付開始済み":"発売開始済み";
        const performers=e.performerIds.filter(id=>NAMES[id]).map(id=>`<span class="presale-performer" style="--performer:${COLORS[id]}">${NAMES[id]}</span>`).join("");
        const url=/^https?:\/\//i.test(e.url)?e.url:"";
        return `<article class="presale-entry ${started?"is-started":""}" data-index="${shownEntries.indexOf(e)}" role="button" tabindex="0" aria-label="${escape(e.title)}の公演詳細を見る">
          <div class="presale-entry-top"><span class="presale-time">${timeText(e.start)} 開始</span><span class="presale-state">${state}</span></div>
          <h3>${escape(e.title)}</h3><div class="presale-performers">${performers}</div>
          <p class="presale-detail">${escape(e.label)}${e.venue?" · "+escape(e.venue):""}</p>
          ${e.end?`<p class="presale-detail">受付終了：${e.end.getMonth()+1}/${e.end.getDate()} ${timeText(e.end)}</p>`:""}
          ${url?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">チケット情報を見る ↗</a>`:'<span class="presale-no-url">チケットURL未取得</span>'}
        </article>`;
      }).join("")}</div></section>`;
    }).join("");
  }
  async function load() {
    try {
      const results=await Promise.allSettled(["events.json","discovered_events.json"].map(async path=>{
        const response=await fetch(`${path}?t=${Date.now()}`,{cache:"no-store"});
        if(!response.ok)throw Error(path);
        const data=await response.json();
        return Array.isArray(data)?data:Array.isArray(data.events)?data.events:[];
      }));
      const events=results.filter(r=>r.status==="fulfilled").flatMap(r=>r.value);
      entries=unique(events.flatMap(normalize));
      if(!events.length)document.getElementById("presaleRows").innerHTML='<p class="presale-empty">公演データを取得できませんでした。</p>';
      else render();
    }catch(error){console.error("Presale load failed",error);}
  }
  const style=document.createElement("style");
  style.textContent=`
    .presale-detail-backdrop[hidden]{display:none!important}
    .presale-detail-backdrop{position:fixed;inset:0;z-index:99999;background:rgba(15,25,38,.6);display:flex;align-items:flex-end;justify-content:center}
    .presale-detail-panel{position:relative;background:white;border-radius:22px 22px 0 0;width:min(100%,700px);max-height:88dvh;overflow:auto;padding:28px 22px 36px;box-sizing:border-box}
    .presale-detail-panel h2{font-size:22px;line-height:1.5;margin:20px 40px 24px 0;color:#142235}
    .presale-detail-close{position:absolute;right:17px;top:17px;border:0;border-radius:50%;width:42px;height:42px;font-size:27px;background:#eef1f5;color:#2a75b6}
    .presale-info-row{padding:13px 0;border-bottom:1px solid #e8edf2;display:grid;gap:6px;overflow-wrap:anywhere}
    .presale-info-row strong{font-size:13px;color:#263445}.presale-info-row span{font-size:14px;line-height:1.7;color:#526071}
    .presale-detail-link{display:block;background:#1d658f;color:white!important;text-align:center;border-radius:11px;padding:15px;margin-top:22px;text-decoration:none;font-weight:bold}
    .presale-entry{cursor:pointer}
    .presale-view{display:none;padding:12px 12px 35px;max-width:800px;margin:auto}
    .presale-view.show{display:block}
    .presale-top h2{font-size:20px;margin:8px 0 4px;color:#152b3a}
    .presale-top p{font-size:12px;color:#77828d;margin:0 0 14px}
    .presale-filters{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:15px}
    .presale-filters button{border:1px solid #dbe1e7;background:white;border-radius:11px;padding:12px;font-weight:800;color:#687581}
    .presale-filters button.selected{background:#172b3a;color:white;border-color:#172b3a}
    .presale-month{display:flex;justify-content:space-between;align-items:center;background:white;border-radius:13px;padding:6px 12px;margin-bottom:14px}
    .presale-month button{border:0;background:transparent;font-size:27px;padding:0 15px;color:#172b3a}
    .presale-month strong{font-size:16px}
    .presale-day{display:grid;grid-template-columns:53px minmax(0,1fr);gap:9px;margin-bottom:15px}
    .presale-date{padding-top:8px;text-align:center;color:#182d3a}
    .presale-date b{font-size:24px;display:block}
    .presale-date span{font-size:11px}
    .presale-day-items{display:grid;gap:9px}
    .presale-entry{background:#fff;border:1px solid #e4e8ed;border-radius:14px;padding:14px;min-width:0}
    .presale-entry.is-started{background:#edf0f2;border-color:#dce1e5}
    .presale-entry-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
    .presale-time{font-weight:800;font-size:13px}
    .presale-state{font-size:10px;font-weight:800;background:#e8f3fd;color:#23669a;border-radius:30px;padding:5px 9px}
    .is-started .presale-state{background:#dce1e5;color:#66717b}
    .presale-entry h3{font-size:15px;line-height:1.45;margin:9px 0 8px;overflow-wrap:anywhere}
    .presale-performers{display:flex;flex-wrap:wrap;gap:5px}
    .presale-performer{font-size:10px;border-left:3px solid var(--performer);background:#f5f6f7;padding:4px 7px;border-radius:5px}
    .presale-detail{font-size:11px;color:#697580;margin:8px 0 0;line-height:1.5}
    .presale-entry a{display:inline-block;font-size:12px;font-weight:800;color:#23669a;margin-top:12px;text-decoration:none}
    .presale-no-url{display:block;font-size:11px;color:#89929b;margin-top:10px}
    .presale-empty{text-align:center;padding:30px 12px;color:#73808b;background:white;border-radius:12px}
    .presale-empty small{display:block;margin-top:7px}
    @media(max-width:370px){.calendar-mode-button{font-size:11px!important;padding:10px 2px!important}}
  `;
  document.head.appendChild(style);
  ensureView();
  document.addEventListener("warai:presale-open",render);
  load();
})();
