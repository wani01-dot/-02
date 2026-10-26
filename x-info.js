(() => {
  "use strict";
  const TARGETS = [
    {id:"maison",name:"めぞん",terms:["めぞん","吉野おいなり君","原一刻"]},
    {id:"pyuto",name:"ピュート",terms:["ピュート","竹内智也"]},
    {id:"nansui",name:"軟水",terms:["軟水","大川内聡","つるまる"]}
  ];
  // 「ポイント」は一般語のため単独一致では採用しない。
  // 「ピュートのポイント」など、所属が明示された表現だけ採用。
  const pointPattern = /(?:ピュート.{0,8}ポイント|ポイント.{0,8}ピュート)/;
  const escapeHtml = v => String(v ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let posts = [];
  let selected = 'all';
  let initialized = false;
  let visible = false;
  let accounts = [];
  function matches(text) {
    const s=String(text||'');
    return TARGETS.filter(t => t.terms.some(term => s.includes(term)) || (t.id==='pyuto' && pointPattern.test(s))).map(t=>t.id);
  }
  function validUrl(value) {
    try { const u=new URL(value); return u.protocol==='https:' && /^(?:www\.)?(?:x\.com|twitter\.com)$/.test(u.hostname) && /^\/[A-Za-z0-9_]+\/status\/\d+/.test(u.pathname); }catch{return false;}
  }
  function parsePost(p) {
    if(!p || typeof p!=='object') return null;
    const url=String(p.url||p.post_url||'');
    if(!validUrl(url)) return null;
    const account=new URL(url).pathname.split('/')[1].toLowerCase();
    if(!accounts.includes(account)) return null;
    const text=String(p.text||p.content||'').slice(0,5000);
    const groups=matches(text);
    if(!groups.length) return null;
    const date=String(p.created_at||p.date||'');
    return {url,text,account,groups,date};
  }
  function ensure() {
    if(initialized) return;
    const switcher=document.getElementById('calendarModeSwitch');
    const button=document.getElementById('xInfoCalendarMode');
    if(!switcher || !button) return;
    initialized=true;
    const view=document.createElement('section');
    view.id='xInfoCalendarView';
    view.className='x-info-view';
    view.hidden=true;
    const main=document.querySelector('main');
    if(main) main.appendChild(view);
    button.addEventListener('click',()=>show());
    ['normalCalendarMode','streamCalendarMode','presaleCalendarMode'].forEach(id=>{
      document.getElementById(id)?.addEventListener('click',()=>hide());
    });
    render();
  }
  function show() {
    ensure();
    const view=document.getElementById('xInfoCalendarView');
    if(!view)return;
    visible=true;
    document.querySelectorAll('.calendar-mode-button').forEach(b=>b.classList.toggle('active',b.id==='xInfoCalendarMode'));
    ['calendarView','streamCalendarView','presaleCalendarView','pageSection'].forEach(id=>{
      const el=document.getElementById(id);if(el)el.style.display='none';
    });
    const legend=document.getElementById('legend');if(legend)legend.style.display='none';
    view.hidden=false;
    render();
  }
  function hide() {
    if(!visible)return;
    visible=false;
    const view=document.getElementById('xInfoCalendarView');if(view)view.hidden=true;
    const legend=document.getElementById('legend');if(legend)legend.style.display='';
    // 他タブの表示は既存の切替処理に任せる。
    ['calendarView','streamCalendarView','presaleCalendarView','pageSection'].forEach(id=>{
      const el=document.getElementById(id);if(el)el.style.display='';
    });
  }
  function render() {
    const view=document.getElementById('xInfoCalendarView');if(!view)return;
    const filtered=posts.filter(p=>selected==='all'||p.groups.includes(selected));
    const buttons=[{id:'all',name:'すべて'},...TARGETS].map(t=>`<button type="button" class="x-filter ${selected===t.id?'active':''}" data-filter="${t.id}">${escapeHtml(t.name)}</button>`).join('');
    const cards=filtered.map(p=>`<article class="x-post"><div class="x-post-head"><strong>@${escapeHtml(p.account)}</strong><span>${escapeHtml(p.date ? new Date(p.date).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}) : '')}</span></div><div class="x-post-tags">${p.groups.map(id=>`<span>${escapeHtml(TARGETS.find(t=>t.id===id)?.name)}</span>`).join('')}</div><p>${escapeHtml(p.text)}</p><a href="${escapeHtml(p.url)}" target="_blank" rel="noopener noreferrer">Xの元ポストを開く ↗</a></article>`).join('');
    view.innerHTML=`<div class="x-info-inner"><h2>X出演情報</h2><p class="x-description">指定された30アカウントから、対象芸人の名前を含む投稿だけを表示します。</p><div class="x-filters">${buttons}</div><div class="x-count">${filtered.length}件の投稿</div>${cards||'<div class="x-empty">現在、登録された該当ポストはありません。<small>無料で利用可能な自動取得経路は未確保です。現時点では登録済みの投稿だけが表示されます。</small></div>'}</div>`;
    view.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.filter;render();}));
  }
  async function load() {
    try {
      const [a,p]=await Promise.all([fetch('x_accounts.json',{cache:'no-store'}),fetch('x_posts.json',{cache:'no-store'})]);
      if(!a.ok||!p.ok)throw new Error('データ取得失敗');
      const aJson=await a.json(),pJson=await p.json();
      accounts=(Array.isArray(aJson)?aJson:aJson.accounts||[]).map(x=>String(x).toLowerCase());
      const rows=Array.isArray(pJson)?pJson:[];
      const unique=new Map();
      rows.forEach(item=>{const post=parsePost(item);if(post)unique.set(post.url.replace(/\?.*$/,''),post);});
      posts=[...unique.values()].sort((a,b)=>Date.parse(b.date||0)-Date.parse(a.date||0));
    }catch(err){console.warn('X出演情報の読み込みに失敗:',err);}
    render();
  }
  const style=document.createElement('style');
  style.textContent=`
    .x-info-view[hidden]{display:none!important}
    .x-info-view{padding:16px 12px 40px}
    .x-info-inner{max-width:800px;margin:0 auto}
    .x-info-inner h2{font-size:21px;color:#152b3a;margin:8px 0}
    .x-description{font-size:13px;color:#687987;line-height:1.7}
    .x-filters{display:flex;gap:7px;flex-wrap:wrap;margin:18px 0}
    .x-filter{border:1px solid #d9e2e9;border-radius:9px;background:#fff;padding:9px 13px;font-weight:700;color:#425464}
    .x-filter.active{background:#172b3a;color:#fff}
    .x-count{font-size:12px;color:#6a7884;margin:12px 0}
    .x-post{background:#fff;border:1px solid #e2e8ed;border-radius:14px;padding:16px;margin-bottom:12px;overflow-wrap:anywhere}
    .x-post-head{display:flex;justify-content:space-between;gap:10px;align-items:center;font-size:13px}
    .x-post-head span{font-size:11px;color:#788895}
    .x-post-tags{display:flex;gap:6px;margin:10px 0}
    .x-post-tags span{background:#eaf1f5;color:#35566a;border-radius:5px;padding:4px 8px;font-size:11px;font-weight:700}
    .x-post p{white-space:pre-wrap;line-height:1.75;font-size:14px;color:#20313f}
    .x-post a{font-size:13px;font-weight:700;color:#19618e;text-decoration:none}
    .x-empty{background:white;padding:26px 18px;border-radius:12px;text-align:center;color:#647583;line-height:1.7}
    .x-empty small{display:block;margin-top:9px}
    @media(max-width:430px){.calendar-mode-switch{flex-wrap:wrap!important}.calendar-mode-button{font-size:11px!important;min-width:0!important}}
  `;
  document.head.appendChild(style);
  document.addEventListener('DOMContentLoaded',()=>{ensure();load();});
})();
