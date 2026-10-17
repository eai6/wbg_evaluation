/* Landing page: vertical filters, stories toggle, Ask (routes to a workspace or answers cross-area questions). */
(function(){
  let vert='All', highlight=null;
  function applyTiles(){document.querySelectorAll('#tiles .tile').forEach(t=>{
    const id=+t.dataset.outcome, dim=(vert!=='All'&&t.dataset.vert!==vert)||(highlight&&!highlight.includes(id));
    t.classList.toggle('dim',dim); t.classList.toggle('hl',!!(highlight&&highlight.includes(id)));});}
  document.querySelectorAll('#vfilters .chip').forEach(b=>b.addEventListener('click',()=>{
    vert=b.dataset.vert; document.querySelectorAll('#vfilters .chip').forEach(x=>x.classList.toggle('on',x===b)); applyTiles();}));
  const tog=$('stories-toggle'); let all=false;
  tog?.addEventListener('click',()=>{all=!all; document.querySelectorAll('[data-more]').forEach(s=>s.hidden=!all); tog.textContent=all?'Show fewer':'See all';});

  async function ask(text){
    const box=$('home-answer'); if(!text) return; $('home-q').value=text;
    box.style.display='block'; box.innerHTML='<div class="status"><span class="dots"><i></i><i></i><i></i></span> Thinking…</div>';
    try{
      const r=await postJSON('/api/route',{message:text});
      if(r.action==='navigate'){ if(r.html){box.innerHTML=`<div class="status">${li('bot',14)} Research agent</div><p style="margin:6px 0 0">${r.html}</p>`;icons();setTimeout(()=>location.href=r.url,1300);} else location.href=r.url; return; }
      highlight=r.highlight||null; applyTiles();
      box.innerHTML=r.html+(highlight?`<div class="legend-v" style="margin-top:8px">Highlighted below. <a id="clear-hl">Clear</a></div>`:'');
      $('clear-hl')?.addEventListener('click',()=>{highlight=null;applyTiles();box.style.display='none';});
    }catch(e){ box.innerHTML='Something went wrong. Please try again.'; }
  }
  $('home-form').addEventListener('submit',e=>{e.preventDefault(); ask($('home-q').value.trim());});
  document.querySelectorAll('[data-ask]').forEach(b=>b.addEventListener('click',()=>ask(b.dataset.ask)));
})();
