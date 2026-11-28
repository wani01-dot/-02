(() => {
  const api=window.WaraiMonthly, button=document.getElementById("xInfoCalendarMode");
  if(!api||!button)return;
  const view=document.createElement("section");view.id="monthlyListView";view.hidden=true;document.querySelector("main").append(view);
  const style=document.createElement("style");style.textContent=`
  #monthlyListView[hidden]{display:none!important}
  #monthlyListView{background:#fff;color:#111;padding:8px;margin:8px 0}
  .monthly-head,.archive-controls{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:8px 0}
  .monthly-head input,.monthly-head button,.archive-controls select{font:inherit;min-width:0;padding:6px;border:1px solid #ddd;border-radius:5px;background:white;color:#222}
  .monthly-day{display:grid;grid-template-columns:48px minmax(0,1fr);border-bottom:1px solid #ddd;min-height:30px}
  .monthly-date{padding:7px 2px;font-size:13px;white-space:nowrap}
  .monthly-event{display:block;text-align:left;width:100%;background:none;border:0;padding:5px 2px;color:#111;font:inherit;font-size:12px;overflow-wrap:anywhere}
  .monthly-event+.monthly-event{border-top:1px dotted #ddd}
  .monthly-event small{display:block;color:#666}
  .monthly-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:3px}
  .archive-result-date{font-size:12px;color:#666;margin-top:8px}
  `;document.head.append(style);
  let month=api.getMonth(),active=false,filter="";
  const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const pad=n=>String(n).padStart(2,"0");
  function render(){
    if(!active)return;
    const y=month.getFullYear(),m=month.getMonth(),prefix=y+"-"+pad(m+1),ps=api.getPerformers();
    const events=api.getGroups().filter(g=>g.date.startsWith(prefix)&&(!filter||g.trackedPerformers.includes(filter)));
    const map=new Map();events.forEach(g=>{if(!map.has(g.date))map.set(g.date,[]);map.get(g.date).push(g);});
    view.innerHTML=`<div class="monthly-head"><button id="monthlyPrev" aria-label="前の月">‹</button><input id="monthlyMonth" aria-label="年月" type="month" value="${prefix}"><button id="monthlyNext" aria-label="次の月">›</button><select id="monthlyFilter" aria-label="出演者"><option value="">すべて</option>${ps.map(p=>`<option value="${esc(p.id)}" ${filter===p.id?"selected":""}>${esc(p.name)}</option>`).join("")}</select></div>`+
      Array.from({length:new Date(y,m+1,0).getDate()},(_,i)=>{
        const d=i+1,w=new Date(y,m,d).getDay(),key=prefix+"-"+pad(d);
        return `<div class="monthly-day"><div class="monthly-date" style="color:${w===0?"#cf251d":w===6?"#2873c5":"#111"}">${d} ${"日月火水木金土"[w]}</div><div>${(map.get(key)||[]).map(g=>`<button class="monthly-event" data-key="${esc(g.key)}">${ps.filter(p=>g.trackedPerformers.includes(p.id)).map(p=>`<span class="monthly-dot" style="background:${esc(p.color)}"></span>`).join("")}${esc(g.startTime||"--:--")} ${esc(g.title)}<small>${esc(g.venue)}　${esc(ps.filter(p=>g.trackedPerformers.includes(p.id)).map(p=>p.name).join("・"))}</small></button>`).join("")}</div></div>`;
      }).join("");
    view.querySelector("#monthlyPrev").onclick=()=>{month=new Date(y,m-1,1);render();};
    view.querySelector("#monthlyNext").onclick=()=>{month=new Date(y,m+1,1);render();};
    view.querySelector("#monthlyMonth").onchange=e=>{const [yy,mm]=e.target.value.split("-").map(Number);if(yy&&mm){month=new Date(yy,mm-1,1);render();}};
    view.querySelector("#monthlyFilter").onchange=e=>{filter=e.target.value;render();};
    view.querySelectorAll("[data-key]").forEach(el=>el.onclick=()=>api.open(el.dataset.key));
  }
  function hide(){if(!active)return;active=false;view.hidden=true;document.getElementById("legend").style.display="";document.getElementById("pageSection").style.display="";}
  button.addEventListener("click",()=>{
    document.getElementById("normalCalendarMode").click();
    active=true;month=api.getMonth();view.hidden=false;
    document.querySelectorAll(".calendar-mode-button").forEach(b=>b.classList.toggle("active",b===button));
    ["calendarView","streamCalendarView","presaleCalendarView","pageSection","legend"].forEach(id=>{const el=document.getElementById(id);if(el)el.style.display="none";});render();
  });
  ["normalCalendarMode","streamCalendarMode","presaleCalendarMode"].forEach(id=>document.getElementById(id)?.addEventListener("click",hide,true));
  document.querySelectorAll(".drawer-item").forEach(el=>el.addEventListener("click",()=>{if(active){hide();document.getElementById("normalCalendarMode").click();}},true));
  document.addEventListener("warai-data-updated",render);
})();