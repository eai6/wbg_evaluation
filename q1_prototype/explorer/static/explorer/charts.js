/* Charts and deck rendering (Plotly). Colours follow the dataviz palette; achieved/expected uses one sequential ramp. */
const CFG={displayModeBar:false,responsive:true};
const axis=()=>({gridcolor:css('--grid'),linecolor:css('--axis'),tickfont:{color:css('--muted'),size:11},zeroline:false});
const base=(x={})=>({paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{family:css('--font'),color:css('--ink-2'),size:x.__fs||12},
  margin:{l:44,r:16,t:8,b:32},hoverlabel:{bgcolor:'#fff',bordercolor:css('--axis'),font:{color:css('--ink'),family:css('--font')}},showlegend:false,...x});

function bullet(el,rows,unit,hl,opts={}){
  const big=!!opts.big, y=rows.map(x=>x.label);
  const track={type:'bar',orientation:'h',y,x:rows.map(x=>x.v[1]),marker:{color:css('--seq-track')},width:.6,name:'Expected',customdata:rows.map(x=>fmt(x.v[1],unit)),hovertemplate:'%{y}<br>expected %{customdata}<extra></extra>'};
  const fill={type:'bar',orientation:'h',y,x:rows.map(x=>x.v[0]),marker:{color:rows.map(x=>x.key===hl?css('--seq-strong'):css('--seq-fill'))},width:.34,name:'Achieved',customdata:rows.map(x=>fmt(x.v[0],unit)),hovertemplate:'%{y}<br>achieved %{customdata}<extra></extra>'};
  const ann=rows.map(x=>({x:Math.max(x.v[1]||0,x.v[0]||0),y:x.label,text:x.v[0]!=null&&x.v[1]>0?`  ${Math.round(x.v[0]/x.v[1]*100)}%`:'',showarrow:false,xanchor:'left',font:{size:big?14:11,color:css('--ink-2')}}));
  return Plotly.react(el,[track,fill],base({__fs:big?14:12,barmode:'overlay',showlegend:!big,legend:{orientation:'h',y:1.1,x:0,font:{size:11}},
    xaxis:{...axis(),tickformat:'~s'},yaxis:{...axis(),autorange:'reversed',gridcolor:'rgba(0,0,0,0)'},
    margin:{l:Math.min(240,10+(big?7.6:6.4)*Math.max(...rows.map(x=>x.label.length))),r:50,t:big?6:30,b:34},annotations:ann}),CFG);}

function matrix(el,spec,opts={}){
  const big=!!opts.big, unit=spec.unit;
  const grp=(g,name,col,sized)=>{const p=spec.points.filter(x=>x.group===g);return{type:'scatter',mode:'markers+text',name,
    x:p.map(x=>Math.max(x.x,spec.xlog?1e4:0)),y:p.map(x=>Math.max(x.y||0,1e4)),text:p.map(x=>g==='other'?'':x.label),textposition:'top center',textfont:{size:big?13:10.5,color:css('--ink')},
    marker:{size:p.map(x=>sized?Math.max(9,Math.min(30,6+Math.sqrt((x.size||0)/1e6)/2.2)):7),color:col,opacity:sized?.92:.55,line:{color:'#fff',width:1.5}},
    customdata:p.map(x=>[x.label,fmt(x.x),x.y?fmt(x.y,unit):'none',x.ratio!=null?Math.round(x.ratio*100)+'%':'—',x.n_active]),
    hovertemplate:'<b>%{customdata[0]}</b><br>need %{customdata[1]}<br>expected %{customdata[2]} · delivered %{customdata[3]}<br>active sector projects %{customdata[4]}<extra></extra>'};};
  return Plotly.react(el,[grp('other','Other client countries',css('--axis'),false),grp('accelerate','Accelerate delivery',css('--s2'),true),grp('expand','Expand footprint',css('--s1'),true)],
    base({__fs:big?13:12,showlegend:!big,legend:{orientation:'h',y:1.1,x:0,font:{size:11}},
      xaxis:{...axis(),type:spec.xlog?'log':'linear',tickformat:'~s',title:{text:spec.xlab,font:{size:big?13:11}}},
      yaxis:{...axis(),type:'log',tickformat:'~s',title:{text:spec.ylab,font:{size:big?13:11}}},margin:big?{l:70,r:14,t:10,b:54}:{l:60,r:12,t:30,b:44}}),CFG);}

/* ---------- 3-slide deck: fixed 1280x720 canvas, scaled to fit the panel ---------- */
function deckHTML(d){
  const L=d.lists||{accelerate:[],expand:[]}, s=d.slides;
  const src=`<div class="src">${esc(d.source)}</div>`;
  return `<div class="slidewrap"><div class="slide"><div class="kick">${esc(d.kicker)}</div><h3>${s[0].title_html}</h3>
      <div class="kpis">${d.kpis.map(k=>`<div class="kpi"><div class="v">${k.v_html}</div><div class="l">${esc(k.l)}</div></div>`).join('')}</div>
      <ul>${s[0].bullets_html.map(b=>`<li>${b}</li>`).join('')}</ul>${src}<div class="n">1 / 3</div></div></div>
    <div class="slidewrap"><div class="slide"><div class="kick">Where the gaps are</div><h3>${s[1].title_html}</h3>
      <div class="sgrid"><div class="dchart" data-chart="regions"></div><div><ul>${s[1].bullets_html.map(b=>`<li>${b}</li>`).join('')}</ul>
      <div class="note">Bars: achieved (dark) within expected (light). “Expected” reflects the active portfolio, not a corporate target.</div></div></div>${src}<div class="n">2 / 3</div></div></div>
    <div class="slidewrap"><div class="slide"><div class="kick">Three-year priorities</div><h3>${s[2].title_html}</h3>
      <div class="sgrid"><div class="dchart" data-chart="matrix"></div><div>
        <div class="slab" style="color:var(--s2)">● Accelerate delivery <span style="font-weight:400;color:var(--muted)">(large portfolio, &lt;40% delivered)</span></div>
        <ul>${L.accelerate.map(x=>`<li><b>${esc(x.name)}</b>: ${x.html}</li>`).join('')}</ul>
        <div class="slab" style="color:var(--s1);margin-top:10px">● Expand footprint <span style="font-weight:400;color:var(--muted)">(highest unmet need)</span></div>
        <ul>${L.expand.map(x=>`<li><b>${esc(x.name)}</b>: ${x.html}</li>`).join('')}</ul>
        <ul style="margin-top:6px">${s[2].bullets_html.map(b=>`<li>${b}</li>`).join('')}</ul></div></div>${src}<div class="n">3 / 3</div></div></div>`;}
async function renderDeck(container,d,opts={}){
  container.innerHTML=deckHTML(d);
  const draw=(el,kind)=>kind==='regions'?bullet(el,d.regions,d.unit,d.focus,{big:true}):matrix(el,d.matrix,{big:true});
  for(const slot of container.querySelectorAll('.dchart')){
    slot.style.cssText='width:690px;height:430px';
    if(opts.exportMode){ await draw(slot,slot.dataset.chart); continue; }
    // in the panel the slide is CSS-scaled, so render each chart off-screen at full size and show it as an image
    const tmp=document.createElement('div'); tmp.style.cssText='position:absolute;left:-10000px;top:0;width:690px;height:430px'; document.body.appendChild(tmp);
    await draw(tmp,slot.dataset.chart); const src=await Plotly.toImage(tmp,{format:'png',width:690,height:430,scale:2}); Plotly.purge(tmp); tmp.remove();
    slot.innerHTML=`<img src="${src}" style="width:690px;height:430px" alt="${slot.dataset.chart==='regions'?'Achieved vs expected by region':'Opportunity matrix'}">`;
  }
  if(!opts.exportMode) fitSlides(container);
}
function fitSlides(root=document){root.querySelectorAll('.slidewrap').forEach(w=>{const s=w.clientWidth/1280;w.style.height=(720*s)+'px';w.firstElementChild.style.transform=`scale(${s})`;});}
window.addEventListener('resize',()=>fitSlides());
