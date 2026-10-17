/* Shared helpers (formatting mirrors explorer/formatting.py) */
const $ = id => document.getElementById(id);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function compact(v){const a=Math.abs(v);
  if(a>=1e9)return(v/1e9).toFixed(1).replace(/\.0$/,'')+'B'; if(a>=1e6)return(v/1e6).toFixed(a>=1e8?0:1).replace(/\.0$/,'')+'M';
  if(a>=1e3)return(v/1e3).toFixed(1).replace(/\.0$/,'')+'K'; return (Math.round(v*10)/10)+'';}
function fmt(v,u){if(v==null||Number.isNaN(v))return'—'; if(u==='USD')return'$'+compact(v); if(u==='Percentage')return Math.round(v)+'%';
  if(u&&/MtCO2/.test(u))return compact(v*1e6)+' tCO₂e/yr'; if(u&&/Hectare/.test(u))return compact(v)+' ha'; if(u&&/Gigawatt/.test(u))return compact(v)+' GW'; return compact(v);}
const li = (n,s=16) => `<i data-lucide="${n}" style="width:${s}px;height:${s}px"></i>`;
function icons(){ if(window.lucide) lucide.createIcons(); }
function toast(t){const x=$('toast'); if(!x)return; x.textContent=t; x.classList.add('show'); clearTimeout(x._t); x._t=setTimeout(()=>x.classList.remove('show'),2600);}
function csrf(){const m=document.cookie.match(/csrftoken=([^;]+)/); return m?m[1]:(document.querySelector('[name=csrfmiddlewaretoken]')||{}).value||'';}
async function postJSON(url, body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:JSON.stringify(body)});return r.json();}
document.addEventListener('DOMContentLoaded', icons);
