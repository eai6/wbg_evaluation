/* Outcome workspace: chat (left) + artifacts (right). The Overview artifact reproduces the Scorecard indicator page. */
const BOOT = JSON.parse($('boot').textContent);
let D = null;                                      // outcome payload from /api/outcomes/<id>/data
let S = {ind:null, org:'WBG', area:'ACW', sex:'_T', fy:null, view:'map', mapField:0};
let ARTS = [], ACTIVE = 'overview', busy = false;
const REGIONS = ['AFE','AFW','EAP','ECA','LCR','MENAAP','SAR'];
const TYPEICON = {overview:'layout-dashboard', figure:'bar-chart-3', deck:'presentation', notebook:'notebook-pen'};
const areaName = a => (D.areas[a]||{}).name || a;
const isCountry = a => (D.areas[a]||{}).type === 'COUNTRY';
const regionOf = a => (D.areas[a]||{}).region;

/* ---------------- data access ---------------- */
function val(ind){
  const fy = String(S.fy);
  if (S.org !== 'WBG') return S.area === 'ACW' ? ((D.ORG[fy]||{})[S.org]||{})[ind] : null;
  return (((S.sex==='F'?D.RF:D.R)[fy]||{})[S.area]||{})[ind];
}
function ctxPick(area){
  for (const c of D.context_indicators){ const s=(D.CTX[area]||{})[c.ind_code]; if (s && Object.keys(s).length>=2) return {c,s}; }
  for (const c of D.context_indicators){ const s=(D.CTX.ACW||{})[c.ind_code]; if (s && Object.keys(s).length) return {c,s}; }
  return null;
}

/* ---------------- artifacts panel ---------------- */
function renderTabs(){
  $('tabs').innerHTML = ARTS.map(a=>`<button class="tab ${a.id===ACTIVE?'on':''}" data-id="${a.id}">${li(TYPEICON[a.type]||'file',15)}${esc(a.title.length>28?a.title.slice(0,26)+'…':a.title)}</button>`).join('');
  $('tabs').querySelectorAll('.tab').forEach(b=>b.onclick=()=>showArt(b.dataset.id)); icons();
}
function addArt(a, announce=true){
  ARTS.push(a); showArt(a.id);
  if (announce) addMsg('bot', `<div class="artref" data-id="${a.id}"><div class="ai">${li(TYPEICON[a.type],18)}</div><div><b>${esc(a.title)}</b><span>${({figure:'Figure',deck:'Presentation · 3 slides',notebook:'Jupyter notebook'})[a.type]||''} · built from verified Scorecard data · click to open</span></div></div>`)
    .querySelector('.artref').onclick=()=>showArt(a.id);
  icons();
}
function showArt(id){
  ACTIVE=id; renderTabs(); const a=ARTS.find(x=>x.id===id), bar=$('abar'), body=$('abody'); body.scrollTop=0;
  const nb = `<button class="btn-sm" id="exp-nb">${li('notebook-pen',14)}Export notebook</button>`;
  if (a.type==='overview'){ bar.innerHTML=`<span class="t">Overview · ${esc(D.outcome.name)}</span>${nb}`; body.innerHTML=overviewHTML(); renderOverview(); }
  else if (a.type==='figure'){
    bar.innerHTML=`<span class="t">${esc(a.title)}</span><button class="btn-sm" id="png">${li('download',14)}PNG</button>${nb}`;
    const h = a.kind==='matrix' ? 520 : Math.max(260, a.rows.length*46+70);
    body.innerHTML=`<div class="chart" id="art-fig" style="height:${h}px"></div><div class="prov">${esc(a.prov)}</div>`;
    a.kind==='matrix' ? matrix('art-fig',a) : bullet('art-fig',a.rows,a.unit,null);
    $('png').onclick=()=>Plotly.downloadImage('art-fig',{format:'png',filename:'scorecard_figure',width:1200,height:h+60});
  }
  else if (a.type==='deck'){
    bar.innerHTML=`<span class="t">${esc(a.title)}</span><a class="btn-sm" href="/api/artifacts/${a.id}/deck" target="_blank">${li('file-down',14)}Export deck (HTML/PDF)</a>${nb}`;
    body.innerHTML='<div class="na">Rendering slides…</div>'; renderDeck(body,a);
  }
  else if (a.type==='notebook'){
    bar.innerHTML=`<span class="t">${esc(a.title)}</span><a class="btn" style="padding:6px 14px;text-decoration:none" href="${a.download_url}">${li('download',14)} Download .ipynb</a>`;
    body.innerHTML=a.cells.map((c,i)=>`<div class="cell ${c.cell_type==='markdown'?'md':''}"><div class="h">${c.cell_type==='markdown'?'Markdown':'In ['+i+']'}</div><pre>${esc(c.source.join(''))}</pre></div>`).join('');
  }
  $('exp-nb')?.addEventListener('click',()=>send('Export a Jupyter notebook for this', {silent:false}));
  icons();
}

/* ---------------- overview (the two Scorecard figures) ---------------- */
function overviewHTML(){
  const countries=Object.keys(D.R[String(S.fy)]||{}).filter(isCountry).sort((a,b)=>areaName(a).localeCompare(areaName(b)));
  return `<div class="filters">
    <label>Institution</label><select id="f-org"><option value="WBG">World Bank Group</option><option value="WB">World Bank</option><option value="IFC">IFC</option><option value="MIGA">MIGA</option></select>
    <label>Area</label><select id="f-area"><option value="ACW">All countries</option><optgroup label="Regions">${REGIONS.map(a=>`<option value="${a}">${esc(areaName(a))}</option>`).join('')}</optgroup>
      <optgroup label="Country groups"><option value="FCS">Fragile & conflict-affected</option></optgroup><optgroup label="Countries">${countries.map(a=>`<option value="${a}">${esc(areaName(a))}</option>`).join('')}</optgroup></select>
    <label>Sex</label><div class="seg" id="f-sex"><button data-v="_T">All</button><button data-v="F">Female</button></div>
    <label>Snapshot</label><div class="seg" id="f-fy">${D.snapshots.map(s=>`<button data-v="${s.fy}">FY${String(s.fy).slice(2)}</button>`).join('')}</div></div>
    <div class="card"><h2>Client context</h2><div class="two"><div class="stat" id="ctx-stat"></div><div class="chart" id="ctx-chart" style="height:230px"></div></div></div>
    <div class="card"><h2>Results from WBG operations</h2><div class="ind-pick" id="ind-pick"></div><div class="two"><div class="stat" id="res-stat"></div><div><div class="views" id="res-views"></div><div class="chart" id="res-chart" style="height:290px"></div></div></div></div>`;
}
function setF(f, note){
  if (f.org && f.org!=='WBG' && (f.area||S.area)!=='ACW'){ f.area='ACW'; toast('Institution splits are reported for all countries'); }
  if (f.area && f.area!=='ACW' && S.org!=='WBG' && !f.org){ f.org='WBG'; }
  S={...S,...f}; if (ACTIVE!=='overview') showArt('overview'); else renderOverview();
  if (note) addMsg('sys', `${note} · <a class="undo">undo</a>`).querySelector('.undo').onclick=e=>{S={...S,org:'WBG',area:'ACW',sex:'_T',fy:D.latest_fy};renderOverview();e.target.textContent='undone';};
}
function renderOverview(){
  if (!$('f-org')) return;
  $('f-org').value=S.org; $('f-area').value=S.area;
  $('f-org').classList.toggle('set',S.org!=='WBG'); $('f-area').classList.toggle('set',S.area!=='ACW');
  $('f-org').onchange=e=>setF({org:e.target.value}); $('f-area').onchange=e=>setF({area:e.target.value});
  document.querySelectorAll('#f-sex button').forEach(b=>{b.classList.toggle('on',b.dataset.v===S.sex);b.onclick=()=>setF({sex:b.dataset.v});});
  document.querySelectorAll('#f-fy button').forEach(b=>{b.classList.toggle('on',+b.dataset.v===+S.fy);b.onclick=()=>setF({fy:+b.dataset.v});});
  renderContext(); renderResults();
}
function renderContext(){
  const cp=ctxPick(S.area);
  if(!cp){$('ctx-stat').innerHTML='<div class="na">No client-context series for this outcome area.</div>';Plotly.purge('ctx-chart');return;}
  const code=cp.c.ind_code, list=[]; const add=a=>{const s=(D.CTX[a]||{})[code]; if(a&&s&&Object.keys(s).length&&!list.find(x=>x.a===a)) list.push({a,s});};
  add(S.area); if(isCountry(S.area)) add(regionOf(S.area)); add('ACW');
  const main=list[0], last=Object.keys(main.s).at(-1), mv=main.s[last], pctU=cp.c.unit==='Percentage';
  $('ctx-stat').innerHTML=`<div class="label">${esc(cp.c.display_name)}</div><div class="hero-num">${pctU?mv.toFixed(1)+'%':fmt(mv,cp.c.unit)}</div>
    <div class="note">${esc(areaName(main.a))} · ${last}${main.a!==S.area?` · no data for ${esc(areaName(S.area))}`:''}</div>`;
  const cols=['--s1','--s2','--muted'];
  const tr=list.map((x,i)=>({x:Object.keys(x.s).map(Number),y:Object.values(x.s),type:'scatter',mode:Object.keys(x.s).length>1?'lines':'markers',name:areaName(x.a),
    line:{color:css(cols[i]),width:2},marker:{size:8,color:css(cols[i])},hovertemplate:`${esc(areaName(x.a))} %{x}: %{y:.1f}<extra></extra>`}));
  const ann=list.map(x=>({x:+Object.keys(x.s).at(-1),y:Object.values(x.s).at(-1),text:` ${areaName(x.a).split(/[ ,&]/)[0]} ${Object.values(x.s).at(-1).toFixed(1)}`,showarrow:false,xanchor:'left',font:{size:11,color:css('--ink-2')}}));
  Plotly.react('ctx-chart',tr,base({xaxis:{...axis(),tickformat:'d'},yaxis:{...axis(),rangemode:'tozero'},margin:{l:36,r:90,t:10,b:28},annotations:ann,hovermode:'x unified'}),CFG);
}
function renderResults(){
  const inds=D.results_indicators;
  $('ind-pick').innerHTML=inds.length>1?inds.map(r=>`<button class="chip ${r.ind_code===S.ind?'on':''}" data-ind="${r.ind_code}">${esc(r.display_name.length>44?r.display_name.slice(0,42)+'…':r.display_name)}</button>`).join(''):'';
  $('ind-pick').querySelectorAll('.chip').forEach(b=>b.onclick=()=>{S.ind=b.dataset.ind;renderOverview();});
  const r=inds.find(x=>x.ind_code===S.ind)||inds[0]; let v=val(r.ind_code), note='';
  if((!v||v[1]==null)&&S.org==='WBG'&&S.sex==='_T'&&S.area==='ACW'){const s=((D.SUB[String(S.fy)]||{})[r.ind_code]); if(s){v=[s.achieved,s.expected];note=`Shown: ${esc(s.name)}.`;}}
  const p=v&&v[0]!=null&&v[1]?v[0]/v[1]:null;
  $('res-stat').innerHTML=`<div class="label">${esc(r.display_name)}</div>`+(!v||v[1]==null?`<div class="na" style="margin-top:10px">No results reported for this selection.</div>`:
    `<div class="pair"><div>${fmt(v[0],r.unit)}<small>Achieved</small></div><div style="color:var(--ink-2)">${fmt(v[1],r.unit)}<small>Expected</small></div></div>
     ${p!=null&&r.unit!=='Percentage'&&v[1]>0?`<div class="meter"><span style="width:${Math.min(100,p*100)}%"></span></div><div class="meter-row"><span>${esc(areaName(S.area))}</span><span>${Math.round(p*100)}% of expected</span></div>`:''}
     <div class="note">${note} Active portfolio · ${S.org==='WBG'?'World Bank Group':S.org}${S.sex==='F'?' · female':''} · FY${String(S.fy).slice(2)}</div>`);
  const views=[['map','Map'],['region','By region'],['org','By institution'],['fy','Over time']];
  $('res-views').innerHTML=`<div class="seg">${views.map(([k,l])=>`<button data-v="${k}" class="${S.view===k?'on':''}">${l}</button>`).join('')}</div>
    <div class="seg">${S.view==='map'?['Achieved','Expected'].map((l,i)=>`<button data-m="${i}" class="${S.mapField===i?'on':''}">${l}</button>`).join(''):''}</div>`;
  $('res-views').querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>{S.view=b.dataset.v;renderOverview();});
  $('res-views').querySelectorAll('[data-m]').forEach(b=>b.onclick=()=>{S.mapField=+b.dataset.m;renderOverview();});
  drawResults('res-chart',r);
}
function drawResults(el,r){
  const fy=String(S.fy), tbl=(S.sex==='F'?D.RF:D.R)[fy]||{};
  if(S.view==='map'){
    let locs=Object.keys(tbl).filter(a=>isCountry(a)&&tbl[a][r.ind_code]&&tbl[a][r.ind_code][S.mapField]!=null);
    const focus=REGIONS.includes(S.area)?S.area:(isCountry(S.area)?regionOf(S.area):null); if(focus) locs=locs.filter(a=>regionOf(a)===focus);
    if(!locs.length) return empty(el,'No country-level results for this selection.');
    Plotly.react(el,[{type:'choropleth',locations:locs,z:locs.map(a=>tbl[a][r.ind_code][S.mapField]),
      text:locs.map(a=>`<b>${esc(areaName(a))}</b><br>Achieved ${fmt(tbl[a][r.ind_code][0],r.unit)}<br>Expected ${fmt(tbl[a][r.ind_code][1],r.unit)}`),hovertemplate:'%{text}<extra></extra>',
      colorscale:[[0,'#cde7f9'],[.5,'#0071bc'],[1,'#002244']],zmin:0,marker:{line:{color:locs.map(a=>a===S.area?'#0b0b0b':'#ffffff'),width:locs.map(a=>a===S.area?2:.5)}},
      colorbar:{orientation:'h',thickness:8,len:.5,x:.5,y:-.02,tickformat:'~s',tickfont:{size:10,color:css('--muted')},outlinewidth:0}}],
      base({geo:{showframe:false,showcoastlines:false,projection:{type:'natural earth'},bgcolor:'rgba(0,0,0,0)',landcolor:'#e6eaee',showland:true,countrycolor:'#ffffff',showcountries:true,
        fitbounds:focus?'locations':false,lataxis:focus?undefined:{range:[-45,72]}},margin:{l:0,r:0,t:0,b:24}}),CFG).then(()=>{
      const node=$(el); node.removeAllListeners?.('plotly_click'); node.on('plotly_click',ev=>{const a=ev.points[0].location; setF({area:a},`Map click → overview filtered: ${esc(areaName(a))}`);});});
  } else if(S.view==='region'){
    const rows=REGIONS.map(a=>({key:a,label:areaName(a),v:(tbl[a]||{})[r.ind_code]})).filter(x=>x.v&&x.v[1]!=null).sort((a,b)=>b.v[1]-a.v[1]);
    rows.length?bullet(el,rows,r.unit,isCountry(S.area)?regionOf(S.area):S.area):empty(el,'No regional breakdown for this indicator.');
  } else if(S.view==='org'){
    const rows=['WB','IFC','MIGA'].map(k=>({key:k,label:{WB:'World Bank',IFC:'IFC',MIGA:'MIGA'}[k],v:((D.ORG[fy]||{})[k]||{})[r.ind_code]})).filter(x=>x.v&&x.v[1]!=null);
    rows.length?bullet(el,rows,r.unit,S.org):empty(el,'No institution breakdown for this indicator.');
  } else {
    const fys=D.snapshots.map(s=>String(s.fy)), area=S.area, vs=fys.map(f=>(((S.sex==='F'?D.RF:D.R)[f]||{})[area]||{})[r.ind_code]||[null,null]);
    const tr=[['Expected',1,'--s2'],['Achieved',0,'--s1']].map(([n,i,c])=>({type:'scatter',mode:'lines+markers',x:fys.map(f=>'FY'+f.slice(2)),y:vs.map(v=>v[i]),name:n,
      line:{color:css(c),width:2},marker:{size:9,color:css(c),line:{color:'#fff',width:2}},hovertemplate:`${n} %{x}: %{y:.3s}<extra></extra>`}));
    Plotly.react(el,tr,base({showlegend:true,legend:{orientation:'h',y:1.12,font:{size:11}},xaxis:{...axis(),type:'category'},yaxis:{...axis(),tickformat:'~s',rangemode:'tozero'}}),CFG);
  }
}
function empty(el,m){Plotly.purge(el);$(el).innerHTML=`<div class="na" style="padding:60px 0;text-align:center">${m}</div>`;}

/* ---------------- chat (Server-Sent Events over fetch) ---------------- */
function addMsg(kind, html){const d=document.createElement('div'); d.className='msg '+kind; d.innerHTML=html; $('msgs').appendChild(d); $('msgs').scrollTop=1e9; return d;}
async function send(text, opts={}){
  if (!text || busy) return; busy=true; if(!opts.silent) addMsg('user', esc(text));
  const status=addMsg('bot',`<div class="status"><span class="dots"><i></i><i></i><i></i></span><span class="st">Thinking…</span></div>`);
  let plan=null;
  try{
    const resp=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},
      body:JSON.stringify({message:text,outcome_id:BOOT.outcome_id,ind_code:S.ind,filters:{area:S.area,sex:S.sex,org:S.org,fy:S.fy},active_artifact:ACTIVE})});
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
      const warn=ev.stats&&ev.stats.failed&&ev.stats.failed.length?`<div class="legend-v">⚠ ${ev.stats.failed.length} number(s) could not be verified and are marked.</div>`:'';
      const m=addMsg('bot',`<div>${ev.html}</div>${warn}${how}${fu?`<div class="fu">${fu}</div>`:''}`);
      m.querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>send(b.dataset.q));
    }
    else if(ev.type==='artifact'){ addArt(ev.artifact); }
    else if(ev.type==='error'){ addMsg('bot',`<div class="na">${esc(ev.text)}</div>`); }
  }
}

/* ---------------- boot ---------------- */
(async function(){
  D = await (await fetch(BOOT.data_url)).json();
  S.fy = D.latest_fy; S.ind = (D.results_indicators.find(i=>{const v=((D.R[String(D.latest_fy)]||{}).ACW||{})[i.ind_code]; return v&&v[0]!=null&&i.unit==='Beneficiaries';})||D.results_indicators[0]||{}).ind_code;
  ARTS=[{id:'overview',type:'overview',title:'Overview'}];
  $('quick').innerHTML=[['list-checks','Summarize this view','Summarize this view'],['presentation','3-slide briefing','Make a 3-slide briefing for leadership'],['notebook-pen','Export notebook','Export a Jupyter notebook for this']]
    .map(([i,l,q])=>`<button class="chip ai" data-q="${q}">${li(i,14)}${l}</button>`).join('')
    + ['Girls in Western Africa','Which countries are furthest behind?','What does expected mean?','Three-year priorities'].map(t=>`<button class="chip" data-q="${t}">${t}</button>`).join('');
  $('quick').querySelectorAll('[data-q]').forEach(b=>b.onclick=()=>send(b.dataset.q));
  addMsg('bot',`<div class="welcome"><h3>${esc(D.outcome.name)}</h3><div class="na" style="font-size:14px">${esc(D.outcome.description||'')}</div></div>
    <div>Ask anything about this outcome area. I can filter the overview, compare and rank areas, and create <b>figures</b> and <b>briefing decks</b>, each exportable as a <b>Jupyter notebook</b> with the underlying data.</div>`);
  renderTabs(); showArt('overview');
  fetch('/api/health').then(r=>r.json()).then(h=>{$('llm-status').textContent=h.llm_configured?`LLM: ${h.model.split('/').pop()}`:'LLM not configured · rules mode';});
  $('chat-form').addEventListener('submit',e=>{e.preventDefault(); const t=$('dock-q').value.trim(); $('dock-q').value=''; send(t);});
  $('dock-q').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('chat-form').requestSubmit();}});
  if (BOOT.ask) send(BOOT.research ? BOOT.ask : BOOT.ask);
})();
