/* Outcome workspace: chat (left) + artifacts (right). The Overview artifact reproduces the Scorecard data page (datapage.js). */
const BOOT = JSON.parse($('boot').textContent);
let D = null;                                      // outcome payload from /api/outcomes/<id>/data
let S = {ind:null, sub:null, org:'WBG', area:'ACW', sex:'_T', fy:null, mapField:0, mapView:'map', tab:'ORG', opsSort:'a', opsQ:'', opsAll:false};
let ARTS = [], ACTIVE = 'overview', busy = false;
const REGIONS = ['AFE','AFW','EAP','ECA','LCR','MENAAP','SAR'];
const TYPEICON = {overview:'layout-dashboard', figure:'bar-chart-3', deck:'presentation'};
const areaName = a => (D.areas[a]||{}).name || a;
const isCountry = a => (D.areas[a]||{}).type === 'COUNTRY';
const regionOf = a => (D.areas[a]||{}).region;

/* ---------------- artifacts panel ---------------- */
function renderTabs(){
  $('tabs').innerHTML = ARTS.map(a=>`<button class="tab ${a.id===ACTIVE?'on':''}" data-id="${a.id}">${li(TYPEICON[a.type]||'file',15)}${esc(a.title.length>28?a.title.slice(0,26)+'…':a.title)}</button>`).join('');
  $('tabs').querySelectorAll('.tab').forEach(b=>b.onclick=()=>showArt(b.dataset.id)); icons();
}
function addArt(a, announce=true, focus=true){
  ARTS.push(a); if (focus) showArt(a.id); else renderTabs();
  if (announce) addMsg('bot', `<div class="artref" data-id="${a.id}"><div class="ai">${li(TYPEICON[a.type],18)}</div><div><b>${esc(a.title)}</b><span>${({figure:'Figure',deck:'3 slides + Jupyter notebook'})[a.type]||''} · built from verified Scorecard data · click to open</span></div></div>`)
    .querySelector('.artref').onclick=()=>showArt(a.id);
  icons();
}
function showArt(id){
  ACTIVE=id; renderTabs(); const a=ARTS.find(x=>x.id===id), bar=$('abar'), body=$('abody'); body.scrollTop=0;
  if (a.type==='overview'){ bar.innerHTML=`<span class="t">Overview · ${esc(D.outcome.name)}</span>`; body.innerHTML=overviewHTML(); renderOverview(); }
  else if (a.type==='figure'){
    bar.innerHTML=`<span class="t">${esc(a.title)}</span><button class="btn-sm" id="png">${li('download',14)}PNG</button>`;
    const h = a.kind==='matrix' ? 520 : Math.max(260, a.rows.length*46+70);
    body.innerHTML=`<div class="chart" id="art-fig" style="height:${h}px"></div><div class="prov">${esc(a.prov)}</div>`;
    a.kind==='matrix' ? matrix('art-fig',a) : bullet('art-fig',a.rows,a.unit,null);
    $('png').onclick=()=>Plotly.downloadImage('art-fig',{format:'png',filename:'scorecard_figure',width:1200,height:h+60});
  }
  else if (a.type==='deck'){
    // a briefing has two views: the slides, and the notebook that rebuilds them (the only notebook export)
    const view=a._view||'slides', nbk=a.notebook;
    bar.innerHTML=`<span class="t">${esc(a.title)}</span>
      ${nbk?`<div class="seg" id="deck-view"><button data-v="slides" class="${view==='slides'?'on':''}">${li('presentation',14)} Slides</button><button data-v="notebook" class="${view==='notebook'?'on':''}">${li('notebook-pen',14)} Notebook</button></div>`:''}
      ${view==='slides'?`<a class="btn-sm" href="/api/artifacts/${a.id}/deck" target="_blank">${li('file-down',14)}Export deck (HTML/PDF)</a>`
        :`<button class="btn-sm" id="copy-all">${li('copy',14)}Copy all code</button><a class="btn" style="padding:6px 14px;text-decoration:none" href="${nbk.download_url}">${li('download',14)} Download .ipynb</a>`}`;
    bar.querySelectorAll('#deck-view button').forEach(b=>b.onclick=()=>{a._view=b.dataset.v; showArt(a.id);});
    if (view==='notebook') renderNotebook(body,nbk.cells);
    else { body.innerHTML='<div class="na">Rendering slides…</div>'; renderDeck(body,a); }
  }
  icons();
}
function renderNotebook(body, cells){
  body.innerHTML=`<div class="na" style="margin-bottom:10px">Rebuilds each slide of this briefing from the public World Bank APIs and checks it against the deck (✓).</div>`
    + cells.map((c,i)=>`<div class="cell ${c.cell_type==='markdown'?'md':''}"><div class="h"><span>${c.cell_type==='markdown'?'Markdown':'In ['+i+']'}</span>${c.cell_type==='code'?`<button class="copy" data-i="${i}" title="Copy this cell">${li('copy',13)}Copy</button>`:''}</div><pre>${esc(c.source.join(''))}</pre></div>`).join('');
  const code=cells.filter(c=>c.cell_type==='code').map(c=>c.source.join('')).join('\n\n');
  body.querySelectorAll('.copy').forEach(b=>b.onclick=()=>copyText(cells[+b.dataset.i].source.join(''),b));
  $('copy-all').onclick=e=>copyText(code,e.currentTarget);
}

/* ---------------- overview filters (the data page itself is drawn by datapage.js) ---------------- */
function setF(f, note){
  if (f.sex && !BD[f.sex]) delete f.sex;
  S={...S,...f,opsAll:false}; if (ACTIVE!=='overview') showArt('overview'); else renderOverview();
  if (note) addMsg('sys', `${note} · <a class="undo">undo</a>`).querySelector('.undo').onclick=e=>{S={...S,org:'WBG',area:'ACW',sex:'_T',fy:D.latest_fy};renderOverview();e.target.textContent='undone';};
}

/* ---------------- chat (Server-Sent Events over fetch) ---------------- */
function addMsg(kind, html){const d=document.createElement('div'); d.className='msg '+kind; d.innerHTML=html; $('msgs').appendChild(d); $('msgs').scrollTop=1e9; return d;}
async function send(text, opts={}){
  if (!text || busy) return; busy=true; if(!opts.silent) addMsg('user', esc(text));
  const status=addMsg('bot',`<div class="status"><span class="dots"><i></i><i></i><i></i></span><span class="st">Thinking…</span></div>`);
  let plan=null, gotArt=false;   // only the first artifact of a response takes focus
  try{
    const resp=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},
      body:JSON.stringify({message:text,outcome_id:BOOT.outcome_id,ind_code:S.ind,filters:{area:isGroup(S.area)?'ACW':S.area,sex:S.sex==='F'?'F':'_T',org:['IBRD','IDA'].includes(S.org)?'WB':S.org,fy:S.fy},active_artifact:ACTIVE})});
    const reader=resp.body.getReader(), dec=new TextDecoder(); let buf='';
    while(true){
      const {value,done}=await reader.read(); if(done) break; buf+=dec.decode(value,{stream:true});
      let i; while((i=buf.indexOf('\n\n'))>=0){ const line=buf.slice(0,i); buf=buf.slice(i+2); if(line.startsWith('data: ')) handle(JSON.parse(line.slice(6))); }
    }
  }catch(e){ addMsg('bot','<div class="na">Connection problem. Please try again.</div>'); }
  status.remove(); busy=false; icons();

  function handle(ev){
    if(ev.type==='status'){ status.querySelector('.st').textContent=ev.text; $('msgs').appendChild(status); }
    else if(ev.type==='filters'){ const f={...ev.filters}; setF(f); }
    else if(ev.type==='navigate'){ location.href=ev.url; }
    else if(ev.type==='plan'){ plan=addMsg('bot',`<div class="acard"><div class="t">${li('bot',13)} Research agent · plan</div><ol style="margin:6px 0 0;padding-left:20px;font-size:13.5px">${ev.steps.map((s,i)=>`<li data-i="${i}" style="opacity:.45">${esc(s)}<div class="na" style="font-size:12px"></div></li>`).join('')}</ol></div>`); icons(); }
    else if(ev.type==='plan_step'&&plan){ const li_=plan.querySelector(`[data-i="${ev.index}"]`); if(li_){li_.style.opacity=1; li_.querySelector('.na').textContent='✓ '+ev.detail;} }
    else if(ev.type==='message'){
      if(ev.kind==='sys'){ addMsg('sys',ev.html); return; }
      const fu=(ev.followups||[]).map(t=>`<button class="chip" data-q="${esc(t)}">${esc(t)}</button>`).join('');
      const how=ev.how?`<div class="how"><details><summary>How I got this</summary>${esc(ev.how)}</details></div>`:'';
      const dropped=ev.stats&&ev.stats.prose_dropped&&(Array.isArray(ev.stats.prose_dropped)?ev.stats.prose_dropped.length:1);
      const warn=dropped?`<div class="legend-v">Some interpretation text was withheld because it failed a check (details under “How I got this”).</div>`:'';
      const m=addMsg('bot',`<div>${ev.html}</div>${warn}${how}${fu?`<div class="fu">${fu}</div>`:''}`);
      m.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>send(b.dataset.q));
    }
    else if(ev.type==='artifact'){ addArt(ev.artifact, true, !gotArt); gotArt=true; }
    else if(ev.type==='choices'){ addMsg('bot',`<div>${esc(ev.text)}</div><div class="fu" style="flex-direction:column;align-items:flex-start">${ev.options.map(o=>`<a class="chip" href="${o.url}" style="text-decoration:none"><b>${esc(o.label)}</b>&nbsp;<span class="na">${esc(o.detail)}</span></a>`).join('')}</div>`); }
    else if(ev.type==='error'){ addMsg('bot',`<div class="na">${esc(ev.text)}</div>`); }
  }
}

/* ---------------- resizable assistant panel ---------------- */
(function(){
  const ws=document.querySelector('.ws'), sp=$('splitter'); if(!ws||!sp) return;
  const KEY='scorecard.chatWidth', DEF=380;
  const clamp=w=>Math.max(280, Math.min(w, Math.round(ws.clientWidth*0.7)));
  const set=w=>ws.style.setProperty('--chatw', clamp(w)+'px');
  const save=()=>{ try{ localStorage.setItem(KEY, parseInt(getComputedStyle(ws).getPropertyValue('--chatw'))||DEF); }catch(e){} };
  const relayout=()=>window.dispatchEvent(new Event('resize'));   // Plotly charts re-fit on resize
  try{ const w=+localStorage.getItem(KEY); if(w) set(w); }catch(e){}
  sp.addEventListener('pointerdown',e=>{
    e.preventDefault(); sp.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const left=ws.getBoundingClientRect().left;
    const move=ev=>set(ev.clientX-left);
    const up=()=>{ sp.removeEventListener('pointermove',move); sp.removeEventListener('pointerup',up); document.body.classList.remove('resizing'); save(); relayout(); };
    sp.addEventListener('pointermove',move); sp.addEventListener('pointerup',up);
  });
  sp.addEventListener('dblclick',()=>{ set(DEF); save(); relayout(); });
  sp.addEventListener('keydown',e=>{ const cur=parseInt(getComputedStyle(ws).getPropertyValue('--chatw'))||DEF;
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'){ e.preventDefault(); set(cur+(e.key==='ArrowRight'?24:-24)); save(); relayout(); } });
})();

/* ---------------- boot ---------------- */
(async function(){
  D = await (await fetch(BOOT.data_url)).json();
  S.fy = D.latest_fy; S.ind = (D.results_indicators.find(i=>{const v=((D.R[String(D.latest_fy)]||{}).ACW||{})[i.ind_code]; return v&&v[0]!=null&&i.unit==='Beneficiaries';})||D.results_indicators[0]||{}).ind_code;
  const V=BOOT.view||{};
  if (D.results_indicators.some(i=>i.ind_code===V.ind)) S.ind=V.ind;
  if (D.snapshots.some(s=>String(s.fy)===V.fy)) S.fy=+V.fy;
  if (ORG_LABEL[V.org]) S.org=V.org;
  if (V.area && (D.areas[V.area]||/^(INC|GRP):/.test(V.area))) S.area=V.area;
  if (BD[V.sex]) S.sex=V.sex;
  ARTS=[{id:'overview',type:'overview',title:'Overview'}];
  $('quick').innerHTML=[['list-checks','Summarize this view','Summarize this view'],['presentation','3-slide briefing + notebook','Make a 3-slide briefing for leadership']]
    .map(([i,l,q])=>`<button class="chip ai" data-q="${q}">${li(i,14)}${l}</button>`).join('')
    + ['Girls in Western Africa','Which countries are furthest behind?','What does expected mean?','Three-year priorities'].map(t=>`<button class="chip" data-q="${t}">${t}</button>`).join('');
  $('quick').querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>send(b.dataset.q));
  addMsg('bot',`<div class="welcome"><h3>${esc(D.outcome.name)}</h3><div class="na" style="font-size:14px">${esc(D.outcome.description||'')}</div></div>
    <div>Ask anything about this outcome area. I can filter the overview, compare and rank areas, and create <b>figures</b> and <b>3-slide briefings</b>. Each briefing comes with a <b>Jupyter notebook</b> that rebuilds every slide from the public World Bank APIs.</div>`);
  renderTabs(); showArt('overview');
  fetch('/api/health').then(r=>r.json()).then(h=>{$('llm-status').textContent=h.llm_configured?`LLM: ${h.model.split('/').pop()}`:'LLM not configured · rules mode';});
  $('chat-form').addEventListener('submit',e=>{e.preventDefault(); const t=$('dock-q').value.trim(); $('dock-q').value=''; send(t);});
  $('dock-q').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('chat-form').requestSubmit();}});
  if (BOOT.ask) send(BOOT.research ? BOOT.ask : BOOT.ask);
})();
