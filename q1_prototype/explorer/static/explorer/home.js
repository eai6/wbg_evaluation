/* Landing page: vertical filters. */
(function(){
  document.querySelectorAll('#vfilters .chip').forEach(b=>b.addEventListener('click',()=>{
    const vert=b.dataset.vert; document.querySelectorAll('#vfilters .chip').forEach(x=>x.classList.toggle('on',x===b));
    document.querySelectorAll('#tiles .tile').forEach(t=>t.classList.toggle('dim',vert!=='All'&&t.dataset.vert!==vert));}));
})();
