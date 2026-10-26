(() => {
  'use strict';
  const cfg = window.X_POSTS_SUPABASE || {};
  const ready = /^https:\/\/[a-z0-9-]+\.supabase\.co\/?$/i.test(cfg.url || '') && cfg.anonKey && !cfg.anonKey.startsWith('PASTE_');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const TARGETS = [
    {id:'maison',name:'めぞん',terms:['めぞん','吉野おいなり君','原一刻']},
    {id:'pyuto',name:'ピュート',terms:['ピュート','竹内智也']},
    {id:'nansui',name:'軟水',terms:['軟水','大川内聡','つるまる']}
  ];
  let posts = [], selected = 'all', initialized = false, visible = false, busy = false;
  function parseUrl(input) {
    try {
      const u = new URL(input.trim());
      if(u.protocol !== 'https:' || !['x.com','www.x.com','twitter.com','www.twitter.com'].includes(u.hostname.toLowerCase())) return null;
      const m = u.pathname.match(/^\/([a-zA-Z0-9_]{1,15})\/status\/(\d{5,25})\/?$/);
      if(!m) return null;
      return {post_id:m[2],account:m[1],post_url:`https://x.com/${m[1]}/status/${m[2]}`};
    } catch { return null; }
  }
  async function request(method, path, body) {
    if(!ready) throw new Error('Supabaseの接続設定がまだ完了していません。');
    const res = await fetch(`${cfg.url.replace(/\/$/,'')}/rest/v1/${path}`, {
      method, headers:{'apikey':cfg.anonKey,'Authorization':`Bearer ${cfg.anonKey}`,'Content-Type':'application/json', 'Prefer':method==='POST'?'return=minimal':'return=representation'},
      ...(body ? {body:JSON.stringify(body)} : {}), cache:'no-store'
    });
    if(!res.ok) {
      const info = await res.json().catch(()=>({}));
      if(res.status===409 || info.code==='23505') throw new Error('このポストはすでに登録されています。');
      throw new Error(`保存先へのアクセスに失敗しました (${res.status})。Supabaseの設定を確認してね。`);
    }
    return method==='GET' ? res.json() : null;
  }
  function dateLabel(value) {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? '入力日不明' : new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(d)+'に入力';
  }
  function embed(post) {
    const holder=document.getElementById(`x-embed-${post.post_id}`);
    if(!holder || holder.dataset.started) return;
    holder.dataset.started='1';
    if(window.twttr?.widgets?.createTweet) {
      window.twttr.widgets.createTweet(post.post_id,holder,{lang:'ja',dnt:true,conversation:'none'}).then(result=>{
        if(!result) holder.textContent='埋め込みを表示できません。下のボタンからXで確認してね。';
      }).catch(()=>{holder.textContent='埋め込みを表示できません。下のボタンからXで確認してね。';});
    } else holder.textContent='Xの埋め込みを読み込めません。下のボタンからXで確認してね。';
  }
  function render() {
    const view=document.getElementById('xInfoCalendarView');if(!view)return;
    const filters='';
    // URLだけでは本文・芸人名を判定できないため、全件表示を基本とする。
    const filtered=posts;
    const cards=filtered.map(p=>`<article class="x-post"><div class="x-post-head"><strong>@${esc(p.account)}</strong><span>${esc(dateLabel(p.created_at))}</span></div><div class="x-embed" id="x-embed-${esc(p.post_id)}">ポストを読み込み中…</div><a class="x-open" href="${esc(p.post_url)}" target="_blank" rel="noopener noreferrer">ポストを表示 ↗</a></article>`).join('');
    view.innerHTML=`<div class="x-info-inner"><h2>X出演情報</h2><p class="x-description">XのポストURLを保存して、あとから見返せる記録帳。投稿の本文はXの公式埋め込みから表示します。</p><form id="x-add-form" class="x-add-form"><label for="x-post-url">ポストのURL</label><input id="x-post-url" type="url" required placeholder="https://x.com/アカウント/status/123..." autocomplete="off"><button type="submit" ${busy?'disabled':''}>${busy?'登録中…':'登録して保存'}</button><div id="x-form-message" role="status"></div></form><div class="x-filters">${filters}</div><p class="x-count">${filtered.length}件の投稿</p>${cards||'<div class="x-empty">まだ登録されたポストはありません。</div>'}</div>`;

    view.querySelector('#x-add-form')?.addEventListener('submit',async e=>{
      e.preventDefault(); const data=parseUrl(view.querySelector('#x-post-url').value);
      if(!data){view.querySelector('#x-form-message').textContent='Xの投稿URLを入力してね。';return;}
      if(posts.some(p=>p.post_id===data.post_id)){view.querySelector('#x-form-message').textContent='このポストは登録済みです。';return;}
      busy=true; const button=view.querySelector('#x-add-form button');button.disabled=true;button.textContent='登録中…';
      try {await request('POST','x_saved_posts',data);await load();}
      catch(err){busy=false;button.disabled=false;button.textContent='登録して保存';view.querySelector('#x-form-message').textContent=err.message;}
    });
    if(visible) filtered.forEach(embed);
  }
  async function load() {
    try {posts=await request('GET','x_saved_posts?select=post_id,post_url,account,created_at&order=created_at.desc&limit=1000');}
    catch(err){console.warn('X保存データ:',err);const msg=document.getElementById('x-form-message');if(msg)msg.textContent=err.message;}
    busy=false;render();
  }
  function ensure() {
    if(initialized)return;
    const button=document.getElementById('xInfoCalendarMode');if(!button)return;
    initialized=true;
    const view=document.createElement('section');view.id='xInfoCalendarView';view.className='x-info-view';view.hidden=true;
    document.querySelector('main')?.appendChild(view);
    button.addEventListener('click',show);
    ['normalCalendarMode','streamCalendarMode','presaleCalendarMode'].forEach(id=>document.getElementById(id)?.addEventListener('click',hide));
    render();
  }
  function show() {
    ensure();const view=document.getElementById('xInfoCalendarView');if(!view)return;
    visible=true;
    document.querySelectorAll('.calendar-mode-button').forEach(b=>b.classList.toggle('active',b.id==='xInfoCalendarMode'));
    ['calendarView','streamCalendarView','presaleCalendarView','pageSection'].forEach(id=>{const el=document.getElementById(id);if(el)el.style.display='none';});
    const legend=document.getElementById('legend');if(legend)legend.style.display='none';
    view.hidden=false;render();load();
  }
  function hide() {
    if(!visible)return;visible=false;
    const view=document.getElementById('xInfoCalendarView');if(view)view.hidden=true;
    const legend=document.getElementById('legend');if(legend)legend.style.display='';
    ['calendarView','streamCalendarView','presaleCalendarView','pageSection'].forEach(id=>{const el=document.getElementById(id);if(el)el.style.display='';});
  }
  const css=document.createElement('style');css.textContent=`
    .x-info-view[hidden]{display:none!important}.x-info-view{padding:16px 12px 40px}.x-info-inner{max-width:800px;margin:0 auto}
    .x-info-inner h2{font-size:22px;color:#152b3a;margin:8px 0}.x-description{font-size:13px;color:#687987;line-height:1.7}
    .x-add-form{background:white;border:1px solid #e2e8ed;border-radius:14px;padding:16px;display:grid;gap:10px;margin-top:16px}
    .x-add-form label{font-weight:700;color:#20313f}.x-add-form input{width:100%;box-sizing:border-box;border:1px solid #cdd9e0;border-radius:9px;padding:13px;font-size:16px}
    .x-add-form button,.x-open{border:0;border-radius:9px;background:#172b3a;color:white;padding:12px 14px;text-align:center;font-size:14px;font-weight:700;text-decoration:none}
    #x-form-message{font-size:12px;color:#a22d39}.x-filters{display:flex;gap:7px;flex-wrap:wrap;margin:18px 0}
    .x-filter{border:1px solid #d9e2e9;border-radius:9px;background:#fff;padding:9px 13px;font-weight:700;color:#425464}.x-filter.active{background:#172b3a;color:#fff}
    .x-count{font-size:12px;color:#6a7884;margin:12px 0}.x-post{background:#fff;border:1px solid #e2e8ed;border-radius:14px;padding:16px;margin-bottom:12px;overflow-wrap:anywhere}
    .x-post-head{display:flex;justify-content:space-between;gap:10px;align-items:center;font-size:13px}.x-post-head span{font-size:11px;color:#788895}
    .x-embed{min-height:75px;color:#7b8993;font-size:13px;padding:12px 0}.x-open{display:block;margin-top:12px}
    .x-empty{background:white;padding:26px 18px;border-radius:12px;text-align:center;color:#647583;line-height:1.7}
    @media(max-width:430px){.calendar-mode-switch{flex-wrap:wrap!important}.calendar-mode-button{font-size:11px!important;min-width:0!important}}
  `;document.head.appendChild(css);
  const script=document.createElement('script');script.src='https://platform.twitter.com/widgets.js';script.async=true;document.head.appendChild(script);
  document.addEventListener('DOMContentLoaded',()=>{ensure();load();});
})();
