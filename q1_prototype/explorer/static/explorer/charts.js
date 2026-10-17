/* Charts and deck rendering (Plotly). Colours follow the dataviz palette; achieved/expected uses one sequential ramp. */
const CFG={displayModeBar:false,responsive:true};
const axis=()=>({gridcolor:css('--grid'),linecolor:css('--axis'),tickfont:{color:css('--muted'),size:11},zeroline:false});
const base=(x={})=>({paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{family:css('--font'),color:css('--ink-2'),size:x.__fs||12},
  margin:{l:44,r:16,t:8,b:32},hoverlabel:{bgcolor:'#fff',bordercolor:css('--axis'),font:{color:css('--ink'),family:css('--font')}},showlegend:false,...x});

function bullet(el,rows,unit,hl,opts={}){
  const big=!!opts.big, y=rows.map(x=>x.label);
  const track={type:'bar',orientation:'h',y,x:rows.map(x=>x.v[1]),marker:{color:css('--seq-track')},width:.6,name:'Expected',customdata:rows.map(x=>fmt(x.v[1],unit)),hovertemplate:'%{y}<br>expected %{customdata}<extra></extra>'};
  // hover says plainly when achieved exceeds expected (no delivery rate is meaningful there)
  const fill={type:'bar',orientation:'h',y,x:rows.map(x=>x.v[0]),marker:{color:rows.map(x=>x.key===hl?css('--seq-strong'):css('--seq-fill'))},width:.34,name:'Achieved',customdata:rows.map(x=>fmt(x.v[0],unit)+(x.v[0]!=null&&x.v[1]>0&&x.v[0]>x.v[1]?` (above expected ${fmt(x.v[1],unit)}; no delivery rate)`:'')),hovertemplate:'%{y}<br>achieved %{customdata}<extra></extra>'};
  // the percentage is a delivery rate only when 0 <= achieved <= expected; otherwise the row is a data check
  const ann=rows.map(x=>({x:Math.max(x.v[1]||0,x.v[0]||0),y:x.label,text:x.v[0]!=null&&x.v[1]>0?(x.v[0]>x.v[1]?'  above expected':`  ${Math.round(x.v[0]/x.v[1]*100)}%`):'',showarrow:false,xanchor:'left',font:{size:big?14:11,color:css('--ink-2')}}));
  return Plotly.react(el,[track,fill],base({__fs:big?14:12,barmode:'overlay',showlegend:true,legend:{orientation:'h',y:big?1.08:1.1,x:0,font:{size:big?13:11},traceorder:'reversed'},
    xaxis:{...axis(),tickformat:'~s',range:[0,1.12*Math.max(...rows.map(x=>Math.max(x.v[0]||0,x.v[1]||0)))]},yaxis:{...axis(),autorange:'reversed',gridcolor:'rgba(0,0,0,0)'},
    margin:{l:Math.min(240,10+(big?7.6:6.4)*Math.max(...rows.map(x=>x.label.length))),r:big?130:110,t:30,b:34},annotations:ann}),CFG);}

function matrix(el,spec,opts={}){
  // selection-logic scatter: axes are the ranking measures; dashed lines sit between the N-th and (N+1)-th country.
  // Labels are placed in pixel space so they never overprint each other, the dots, the cut-off lines or the edges.
  const big=!!opts.big, unit=spec.unit, L=spec.legend||{}, node=typeof el==='string'?$(el):el;
  const W=node.clientWidth||690, H=node.clientHeight||430, m=big?{l:70,r:16,t:46,b:56}:{l:62,r:14,t:42,b:48};
  const pw=W-m.l-m.r, ph=H-m.t-m.b, lg=v=>Math.log10(Math.max(v,1e-9)), P=spec.points;
  const xv=v=>spec.xlog?lg(v):v, X=P.map(p=>xv(p.x)), Y=P.map(p=>lg(p.y));
  // extra room on the right: the countries that matter (largest values) cluster there and need space for labels
  const xr=spec.xpct?[-4,112]:[Math.min(...X)-.12,Math.max(...X)+.45], yr=[Math.min(...Y)-.2,Math.max(...Y)+1];  // headroom above the top countries for their labels
  const px=v=>m.l+(xv(v)-xr[0])/(xr[1]-xr[0])*pw, py=v=>m.t+(1-(lg(v)-yr[0])/(yr[1]-yr[0]))*ph;
  const fs=big?13:11, cw=fs*.58, lh=fs+5, boxes=[], ann=[], shapes=[], dash={color:css('--ink-2'),width:1.2,dash:'dash'};
  const hit=b=>b.x0<m.l||b.x1>W-m.r||b.y0<m.t||b.y1>H-m.b||boxes.some(o=>b.x0<o.x1&&b.x1>o.x0&&b.y0<o.y1&&b.y1>o.y0);
  // reserve the dots of highlighted countries and the cut-off line labels first
  const hl=P.filter(p=>p.group!=='other');
  hl.forEach(p=>boxes.push({x0:px(p.x)-8,x1:px(p.x)+8,y0:py(p.y)-8,y1:py(p.y)+8}));
  let lineY=null;
  if(spec.cuts?.y){ const y=py(spec.cuts.y.v), w=spec.cuts.y.label.length*cw+8; lineY=y;
    shapes.push({type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:spec.cuts.y.v,y1:spec.cuts.y.v,line:dash});
    // the line's label goes at whichever end (just above, else just below the line) is free of dots
    const spots=[[m.l,y-lh-2,'left','bottom',0],[W-m.r-w,y-lh-2,'right','bottom',1],[W-m.r-w,y+2,'right','top',1],[m.l,y+2,'left','top',0]];
    const s=spots.find(([x0,y0])=>!hit({x0,x1:x0+w,y0,y1:y0+lh}))||spots[0];
    ann.push({xref:'paper',x:s[4],y:lg(spec.cuts.y.v),yref:'y',text:spec.cuts.y.label,showarrow:false,xanchor:s[2],yanchor:s[3],xshift:s[4]?-4:4,yshift:s[3]==='bottom'?2:-2,font:{size:fs-1,color:css('--ink-2')}});
    boxes.push({x0:s[0],x1:s[0]+w,y0:s[1],y1:s[1]+lh}); }
  if(spec.cuts?.x){ const x=px(spec.cuts.x.v), w=spec.cuts.x.label.length*cw;
    shapes.push({type:'line',yref:'paper',y0:0,y1:1,xref:'x',x0:spec.cuts.x.v,x1:spec.cuts.x.v,line:dash});
    // label runs along the line (vertical), in the middle third where dots are rarest
    ann.push({yref:'paper',y:.5,x:xv(spec.cuts.x.v),xref:'x',text:spec.cuts.x.label,showarrow:false,textangle:-90,xanchor:'right',xshift:-3,font:{size:fs-1,color:css('--ink-2')}});
    boxes.push({x0:x-lh-4,x1:x,y0:m.t+ph/2-w/2,y1:m.t+ph/2+w/2}); }
  if(spec.floor){ const t='little or no remaining gap (delivered, above expected or no results)', w=t.length*(cw-1);
    ann.push({xref:'paper',x:0,y:lg(spec.floor),yref:'y',text:t,showarrow:false,xanchor:'left',yanchor:'bottom',yshift:6,font:{size:fs-2,color:css('--muted')}});
    boxes.push({x0:m.l,x1:m.l+w,y0:py(spec.floor)-lh-6,y1:py(spec.floor)}); }
  // candidate offsets (pixels from the dot to the label centre): close first, then further out with a leader line
  const C=[[0,-1],[0,1],[1,0],[-1,0],[1,-1],[-1,-1],[1,1],[-1,1]], R=[16,34,56,80];
  const put=(p,ox,oy,r)=>ann.push(r>16?{x:xv(p.x),y:lg(p.y),xref:'x',yref:'y',text:p.label,ax:ox,ay:oy,showarrow:true,arrowhead:0,arrowwidth:1,
      arrowcolor:css('--axis'),standoff:7,font:{size:fs,color:css('--ink')}}
    :{x:xv(p.x),y:lg(p.y),xref:'x',yref:'y',text:p.label,showarrow:false,xshift:ox,yshift:-oy,font:{size:fs,color:css('--ink')}});
  [...hl].sort((a,b)=>py(a.y)-py(b.y)).forEach(p=>{
    const w=p.label.length*cw+6, cx=px(p.x), cy=py(p.y);
    let placed=false;
    for(const r of R){ for(const [dx,dy] of C){
      const ox=dx*(r+(dx?w/2:0)), oy=dy*r, b={x0:cx+ox-w/2,x1:cx+ox+w/2,y0:cy+oy-lh/2,y1:cy+oy+lh/2};
      if(hit(b)) continue;
      if(lineY!=null&&(cy<lineY?b.y1>lineY-1:b.y0<lineY+1)) continue;  // a label stays on its dot's side of the cut-off line
      boxes.push(b); put(p,ox,oy,r); placed=true; break;
    } if(placed) break; }
    if(!placed) put(p,0,-34,34);  // never drop a label: fall back to a leader line straight up
  });
  const xfmt=v=>spec.xpct?Math.round(v)+'%':fmt(v);
  // dots on the bottom line are drawn as rings in a separate trace, so legend icons stay solid
  const grp=(g,name,col,sized,floor=false)=>{const p=P.filter(x=>x.group===g&&!!x.floor===floor);return{type:'scatter',mode:'markers',name,showlegend:!floor,legendgroup:g,x:p.map(x=>x.x),y:p.map(x=>x.y),
    marker:{size:sized?(big?14:12):7,color:col,opacity:sized?.95:.45,symbol:floor?'circle-open':'circle',line:{color:floor?col:(sized?'#fff':col),width:floor?2:1.5}},
    customdata:p.map(x=>[x.label,xfmt(x.x),x.gap!=null?fmt(x.gap,unit):'no WBG results',x.ratio!=null?Math.round(x.ratio*100)+'%':(x.flag==='achieved_above_expected'?'achieved above expected':'—')]),
    hovertemplate:`<b>%{customdata[0]}</b><br>${spec.xpct?'delivered':'in need'} %{customdata[1]}<br>still to deliver %{customdata[2]}<br>delivered %{customdata[3]}<extra></extra>`};};
  const groups=[['other','Other countries',css('--axis'),false],['gap',L.gap||'Most still to deliver',css('--s2'),true]];
  if(L.people) groups.push(['people',L.people,css('--s1'),true],['both',L.both||'Both lists',css('--s3'),true]);
  const traces=groups.flatMap(([g,n,c,s])=>[grp(g,n,c,s),grp(g,n,c,s,true)]);
  return Plotly.react(node,traces,
    base({__fs:big?13:12,showlegend:true,legend:{orientation:'h',y:1,yanchor:'bottom',x:0,font:{size:big?12:11},itemsizing:'constant'},shapes,annotations:ann,
      xaxis:{...axis(),type:spec.xlog?'log':'linear',range:xr,tickformat:spec.xpct?'':'~s',ticksuffix:spec.xpct?'%':'',dtick:spec.xlog?'D2':undefined,title:{text:spec.xlab,font:{size:big?13:11}}},
      yaxis:{...axis(),type:'log',range:yr,tickformat:'~s',dtick:'D2',title:{text:spec.ylab,font:{size:big?13:11}}},margin:m,...(big?{width:W,height:H}:{})}),CFG);}

/* ---------- 3-slide deck: fixed 1280x720 canvas, scaled to fit the panel ---------- */
function deckHTML(d){
  const s=d.slides, src='';
  const over=(d.regions||[]).filter(r=>r.v[0]!=null&&r.v[1]>0&&r.v[0]>r.v[1]).map(r=>r.label);
  return `<div class="slidewrap"><div class="slide"><div class="kick">${esc(d.kicker)}</div><h3>${s[0].title_html}</h3>
      <div class="kpis">${d.kpis.map(k=>`<div class="kpi"><div class="v">${k.v_html}</div><div class="l">${esc(k.l)}</div></div>`).join('')}</div>
      <div class="sbody">${s[0].body_html}</div>${src}<div class="n">1 / 3</div></div></div>
    <div class="slidewrap"><div class="slide"><div class="kick">Where results remain to be delivered</div><h3>${s[1].title_html}</h3>
      <div class="sgrid"><div class="dchart" data-chart="regions"></div><div class="sbody">${s[1].body_html}
      <div class="note">“Expected” is what the active portfolio is expected to deliver, not a corporate target.${over.length?` ${esc(over.join(', '))}: achieved is above expected, so no delivery rate is given; the source reports more achieved than the active portfolio expects (often in projects flagged for results overlap).`:''}</div></div></div>${src}<div class="n">2 / 3</div></div></div>
    <div class="slidewrap"><div class="slide"><div class="kick">Three-year priorities</div><h3>${s[2].title_html}</h3>
      <div class="sgrid"><div class="dchart" data-chart="${d.matrix?'matrix':'gaps'}"></div><div class="sbody">${s[2].body_html}</div></div>${src}<div class="n">3 / 3</div></div></div>`;}
async function renderDeck(container,d,opts={}){
  container.innerHTML=deckHTML(d);
  const draw=(el,kind)=>kind==='regions'?bullet(el,d.regions,d.unit,null,{big:true}):kind==='gaps'?bullet(el,d.gap_bars,d.unit,null,{big:true}):matrix(el,d.matrix,{big:true});
  for(const slot of container.querySelectorAll('.dchart')){
    slot.style.cssText='width:690px;height:430px';
    // render each chart off-screen at full size and place it as an image: crisp when the slide is CSS-scaled in the
    // panel, and identical in print/PDF (live Plotly divs reflow when printed)
    const tmp=document.createElement('div'); tmp.style.cssText='position:absolute;left:-10000px;top:0;width:690px;height:430px'; document.body.appendChild(tmp);
    await draw(tmp,slot.dataset.chart); const src=await Plotly.toImage(tmp,{format:'png',width:690,height:430,scale:2}); Plotly.purge(tmp); tmp.remove();
    slot.innerHTML=`<img src="${src}" style="width:690px;height:430px" alt="${slot.dataset.chart==='regions'?'Achieved vs expected by region':'Opportunity matrix'}">`;
  }
  if(!opts.exportMode){ container.insertAdjacentHTML('beforeend',`<div class="na" style="margin-top:8px">${esc(d.source)}</div>`); fitSlides(container); }
}
// slides are a fixed 1280x720 canvas scaled to their container; refit whenever the container itself changes size
// (the panel can resize without a window resize, e.g. when the layout or scrollbar changes)
const slideRO=new ResizeObserver(es=>es.forEach(e=>fitOne(e.target)));
function fitOne(w){const s=w.clientWidth/1280; if(!s)return; w.style.height=(720*s)+'px'; w.firstElementChild.style.transform=`scale(${s})`;}
function fitSlides(root=document){root.querySelectorAll('.slidewrap').forEach(w=>{fitOne(w); slideRO.observe(w);});}
