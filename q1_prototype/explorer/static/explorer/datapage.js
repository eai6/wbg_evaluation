/* Overview artifact = the Scorecard data page (scorecard.worldbank.org/en/data/result-details/<indicator>) for the
   selected results indicator: headline, Countries/Economies map + table, Organizations / Regions / Income Groups /
   WB Financing Institutions, Female and Youth shares, Country Groups, FCS share, and the World Bank Operations
   (projects) table that the numbers are built from. Data: /api/indicators/<code>?fy=<fy> (one request per indicator x FY). */
const DET = {};                                           // cache: "<ind>|<fy>" -> payload
const BD = {_T:'T', F:'F', Y:'Y', D:'D'};                 // S.sex holds the "WBG Results Only" breakdown
const BD_LABEL = {_T:'', F:'female', Y:'youth', D:'disability-inclusive'};
const ORG_LABEL = {WBG:'World Bank Group', WB:'World Bank', IFC:'IFC', MIGA:'MIGA', IBRD:'IBRD', IDA:'IDA'};
const INCOME = [['LIC','Low income'],['LMC','Lower middle income'],['UMC','Upper middle income'],['HIC','High income']];
const GROUPS = [['small_state','Small States'],['sids','Small Island Developing States'],['ldc','Least Developed Countries']];
const COL = {a: () => css('--seq-strong'), e: () => '#9cc9ea', rest: () => css('--surface-2')};

async function detail(){
  const k = S.ind + '|' + S.fy;
  if (!DET[k]) DET[k] = fetch(`/api/indicators/${encodeURIComponent(S.ind)}?fy=${S.fy}`).then(r => r.json());
  return DET[k];
}

/* ---------- areas: real areas plus client-side groups (sum of country values, as the Scorecard does) ---------- */
const isGroup = a => a.startsWith('INC:') || a.startsWith('GRP:');
function groupLabel(a){
  if (a.startsWith('INC:')) return (INCOME.find(x => x[0] === a.slice(4)) || [, a])[1];
  if (a.startsWith('GRP:')) return (GROUPS.find(x => x[0] === a.slice(4)) || [, a])[1];
  return areaName(a);
}
function members(a){                                      // country codes inside an area
  const all = Object.keys(D.areas).filter(isCountry);
  if (a === 'ACW') return all;
  if (REGIONS.includes(a)) return all.filter(c => regionOf(c) === a);
  if (a === 'FCS') return all.filter(c => D.areas[c].fcs);
  if (a.startsWith('INC:')) return all.filter(c => D.areas[c].income === a.slice(4));
  if (a.startsWith('GRP:')) return all.filter(c => D.areas[c][a.slice(4)]);
  return isCountry(a) ? [a] : [];
}
function cell(X, org, area){ return ((((X.V[S.sub] || {})[org] || {})[BD[S.sex]] || {})[area]) || null; }
function sumOf(X, org, codes){                            // [achieved, expected], plus how many members report
  let a = 0, e = 0, n = 0, na = 0;
  for (const c of codes){ const v = cell(X, org, c); if (!v || v[1] == null){ continue; } n++; if (v[0] == null) na++; else a += v[0]; e += v[1]; }
  return n ? {v: [na === n ? null : a, e], n} : null;
}
function value(X, org, area){                             // official row when published, else the sum of its countries
  if (!isGroup(area)) { const v = cell(X, org, area); return v ? {v, official: true} : null; }
  const s = sumOf(X, org, members(area)); return s ? {...s, official: false} : null;
}

/* ---------- projects (World Bank operations) ---------- */
function projects(X){
  const C = X.project_cols, ix = Object.fromEntries(C.map((c, i) => [c, i]));
  const scope = new Set(members(S.area));
  const inScope = p => S.area === 'ACW' || scope.has(p[ix.area]) || (REGIONS.includes(S.area) && !isCountry(p[ix.area]) && p[ix.region] === S.area);
  const fin = S.org === 'IBRD' || S.org === 'IDA' ? S.org.toLowerCase() : null;
  return X.projects.filter(p => p[ix.sub] === S.sub && p[ix.bd] === BD[S.sex] && inScope(p))
    .map(p => ({id: p[ix.proj_id], name: p[ix.name], area: p[ix.area], region: p[ix.region], url: p[ix.url], overlap: p[ix.overlap],
                a: fin ? p[ix[fin + '_achieved']] : p[ix.achieved], e: fin ? p[ix[fin + '_expected']] : p[ix.expected]}))
    .filter(p => !fin || (p.e || p.a));
}
const projArea = p => isCountry(p.area) ? areaName(p.area) : `Multi-country (${p.area})${p.region ? ' · ' + areaName(p.region) : ''}`;
function countText(ps){                                   // the Scorecard's wording: "More than 220 projects in 95 countries/economies"
  const n = new Set(ps.map(p => p.id)).size, m = new Set(ps.map(p => p.area)).size;
  if (!n) return '';
  const shown = n > 10 && n % 10 ? n - n % 10 : n;
  return `${shown !== n ? 'More than ' : ''}<b>${shown}</b> project${n > 1 ? 's' : ''} in <b>${m}</b> ${m > 1 ? 'countries/economies' : 'country/economy'}`;
}
/* ---------- layout ---------- */
function overviewHTML(){
  const countries = Object.keys(D.areas).filter(isCountry).sort((a, b) => areaName(a).localeCompare(areaName(b)));
  return `<div class="filters">
    <label>Fiscal year</label><div class="seg" id="f-fy">${D.snapshots.map(s => `<button data-v="${s.fy}">FY${String(s.fy).slice(2)}</button>`).join('')}</div>
    <label>Institution</label><select id="f-org">${Object.entries(ORG_LABEL).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select>
    <label>Area</label><select id="f-area"><option value="ACW">All countries</option>
      <optgroup label="WBG regions">${REGIONS.map(a => `<option value="${a}">${esc(areaName(a))}</option>`).join('')}</optgroup>
      <optgroup label="Income groups">${INCOME.map(([k, l]) => `<option value="INC:${k}">${l}</option>`).join('')}</optgroup>
      <optgroup label="Country groups"><option value="FCS">Fragile and conflict-affected situations</option>${GROUPS.map(([k, l]) => `<option value="GRP:${k}">${l}</option>`).join('')}</optgroup>
      <optgroup label="Countries/economies">${countries.map(a => `<option value="${a}">${esc(areaName(a))}</option>`).join('')}</optgroup></select>
    <label>WBG results only</label><div class="seg" id="f-sex">${[['_T', 'All'], ['F', 'Female'], ['Y', 'Youth'], ['D', 'Disability-inclusive']].map(([k, l]) => `<button data-v="${k}">${l}</button>`).join('')}</div></div>
    <div class="ind-pick" id="ind-pick"></div>
    <div id="dp"><div class="na">Loading Scorecard data…</div></div>
    <div class="card"><h2>Client context</h2><div class="two"><div class="stat" id="ctx-stat"></div><div class="chart" id="ctx-chart" style="height:230px"></div></div></div>`;
}

let RENDER = 0;
async function renderOverview(){
  if (!$('f-org')) return;
  $('f-org').value = S.org; $('f-area').value = S.area;
  $('f-org').classList.toggle('set', S.org !== 'WBG'); $('f-area').classList.toggle('set', S.area !== 'ACW');
  $('f-org').onchange = e => setF({org: e.target.value}); $('f-area').onchange = e => setF({area: e.target.value});
  document.querySelectorAll('#f-sex button').forEach(b => { b.classList.toggle('on', b.dataset.v === S.sex); b.onclick = () => setF({sex: b.dataset.v}); });
  document.querySelectorAll('#f-fy button').forEach(b => { b.classList.toggle('on', +b.dataset.v === +S.fy); b.onclick = () => setF({fy: +b.dataset.v}); });
  const inds = D.results_indicators;
  $('ind-pick').innerHTML = inds.length > 1 ? inds.map(r => `<button class="chip ${r.ind_code === S.ind ? 'on' : ''}" data-ind="${r.ind_code}" title="${esc(r.display_name)}">${esc(r.display_name.length > 46 ? r.display_name.slice(0, 44) + '…' : r.display_name)}</button>`).join('') : '';
  $('ind-pick').querySelectorAll('.chip').forEach(b => b.onclick = () => { S.ind = b.dataset.ind; S.sub = null; renderOverview(); });
  renderContext();
  const token = ++RENDER, X = await detail();
  if (token !== RENDER || !$('dp')) return;
  if (S.sub == null || !X.V[S.sub]) S.sub = X.V[''] ? '' : (Object.keys(X.subs)[0] ?? '');
  $('dp').innerHTML = dataPageHTML(X);
  drawDataPage(X);
  icons();
}

function dataPageHTML(X){
  const I = X.indicator, h = value(X, S.org, S.area), ps = projects(X);
  const scope = `${esc(groupLabel(S.area))} · ${ORG_LABEL[S.org]}${BD_LABEL[S.sex] ? ' · ' + BD_LABEL[S.sex] : ''} · FY${String(S.fy).slice(2)}`;
  const subs = Object.keys(X.subs).length ? `<div class="ind-pick">${(X.V[''] ? [['', 'Total']] : []).concat(Object.entries(X.subs)).map(([k, l]) => `<button class="chip ${k === S.sub ? 'on' : ''}" data-sub="${k}">${esc(l)}</button>`).join('')}</div>` : '';
  const head = !h || h.v[1] == null ? `<div class="na" style="margin:8px 0">No results reported for ${scope}.</div>` :
    `<div class="apr"><div class="k">Active Portfolio Results</div>
       <div class="pair2"><span><b>${fmt(h.v[0], I.unit)}</b> Achieved</span><span><b>${fmt(h.v[1], I.unit)}</b> Expected</span></div>
       ${h.official ? '' : `<div class="na">Sum of ${h.n} country values, as the Scorecard computes groups.</div>`}</div>`;
  const cnt = ['WBG', 'WB', 'IBRD', 'IDA'].includes(S.org) ? countText(ps) : '';
  return `<div class="card dhead">
      <div class="tags"><span class="tag">RESULTS</span><span>${esc(I.vertical || '')}</span><span>${esc(D.outcome.name)}</span></div>
      <h3>${esc(I.display_name)}</h3>${subs}
      <div class="na" style="margin:-4px 0 8px">${scope}</div>${head}
      ${cnt ? `<div class="cnt">${cnt}</div>` : ''}
      ${I.description ? `<p class="def">${esc(I.description)}</p>` : ''}
      ${I.definition ? `<details class="fulldef"><summary>Full definition (Scorecard metadata)</summary><p>${esc(I.definition)}</p></details>` : ''}
    </div>
    <div class="card"><div class="ch"><h2>Countries/Economies</h2><div class="seg" id="map-field">${['Achieved', 'Expected'].map((l, i) => `<button data-m="${i}" class="${S.mapField === i ? 'on' : ''}">${l}</button>`).join('')}</div>
      <div class="seg" id="map-view"><button data-v="map" class="${S.mapView !== 'table' ? 'on' : ''}">${li('map-pin', 14)}</button><button data-v="table" class="${S.mapView === 'table' ? 'on' : ''}">${li('table', 14)}</button></div></div>
      <div id="map-box"></div></div>
    <div class="card"><div class="ch"><div class="seg" id="bd-tab">${[['ORG', 'Organizations'], ['REGION', 'Regions'], ['INCOME', 'Income Groups'], ['FIN', 'WB Financing Institutions']].map(([k, l]) => `<button data-t="${k}" class="${S.tab === k ? 'on' : ''}">${l}</button>`).join('')}</div></div>
      <div class="chart" id="bd-chart" style="height:250px"></div><div class="na" id="bd-note"></div></div>
    <div class="grid3"><div class="card"><h2>Female</h2><div class="chart" id="sh-f" style="height:200px"></div><div class="na" id="sh-f-n"></div></div>
      <div class="card"><h2>Youth</h2><div class="chart" id="sh-y" style="height:200px"></div><div class="na" id="sh-y-n"></div></div>
      <div class="card"><h2>Fragile and conflict-affected</h2><div class="chart" id="sh-fcs" style="height:200px"></div><div class="na" id="sh-fcs-n"></div></div></div>
    <div class="card"><h2>Country Groups</h2><div class="chart" id="cg" style="height:220px"></div><div class="na">Sum of country values in each group.</div></div>
    <div class="card" id="ops">${opsHTML(X, ps)}</div>`;
}

/* ---------- World Bank Operations: the projects the numbers are built from ---------- */
function opsHTML(X, ps){
  const unit = X.indicator.unit;
  if (S.org === 'IFC' || S.org === 'MIGA') return `<h2>World Bank Operations</h2><div class="na">Project-level results are published for World Bank operations only (IFC and MIGA report totals).</div>`;
  const q = (S.opsQ || '').toLowerCase();
  const rows = ps.filter(p => !q || (p.name + ' ' + p.id + ' ' + projArea(p)).toLowerCase().includes(q))
    .sort((a, b) => S.opsSort === 'e' ? (b.e || 0) - (a.e || 0) : S.opsSort === 'c' ? projArea(a).localeCompare(projArea(b)) : (b.a || 0) - (a.a || 0));
  const shown = S.opsAll ? rows : rows.slice(0, 15);
  const sa = ps.reduce((s, p) => s + (p.a || 0), 0), se = ps.reduce((s, p) => s + (p.e || 0), 0);
  const wbOrg = S.org === 'IBRD' || S.org === 'IDA' ? S.org : 'WB', wb = value(X, wbOrg, S.area);
  const close = (x, y) => y != null && Math.abs(x - y) <= 0.005 * Math.abs(y) + 1;
  let check;
  if (!ps.length) check = `<span class="na">No World Bank operations report this indicator for this selection.</span>`;
  else if (unit === 'Percentage' || unit === 'Countries/Economies') check = `<span class="na">The total for this indicator (${esc(unit.toLowerCase())}) is not a sum of project values, so the projects are listed without a sum check.</span>`;
  else if (!wb || wb.v[1] == null) check = `<span class="na">The ${ORG_LABEL[wbOrg]} total is not published for this selection, so the project sum cannot be cross-checked.</span>`;
  else if (close(sa, wb.v[0] ?? 0) && close(se, wb.v[1])) check = `<span class="ok">${li('circle-check', 14)} These ${new Set(ps.map(p => p.id)).size} projects add up to the ${ORG_LABEL[wbOrg]} total for this selection (${fmt(wb.v[0], unit)} achieved, ${fmt(wb.v[1], unit)} expected).</span>`;
  else check = `<span class="warn">${li('triangle-alert', 14)} Listed projects sum to ${fmt(sa, unit)} achieved and ${fmt(se, unit)} expected; the ${ORG_LABEL[wbOrg]} total is ${fmt(wb.v[0], unit)} and ${fmt(wb.v[1], unit)}. The difference is in the Scorecard total but not attributed to projects in the API.</span>`;
  return `<div class="ch"><h2>World Bank Operations</h2><input id="ops-q" class="search" placeholder="Search projects or countries" value="${esc(S.opsQ || '')}"><button class="btn-sm" id="ops-csv">${li('download', 14)}CSV</button></div>
    <div class="check">${check}</div>
    <div class="tblwrap"><table class="ops"><thead><tr><th data-s="c">Country</th><th>Projects</th><th class="n" data-s="a">Achieved${S.opsSort !== 'e' && S.opsSort !== 'c' ? ' ↓' : ''}</th><th class="n" data-s="e">Expected${S.opsSort === 'e' ? ' ↓' : ''}</th>
      <th class="n" title="Results Overlap Flag: Y when this project's result may overlap with another operation's in the same country">Overlap</th></tr></thead>
      <tbody>${shown.map(p => `<tr><td>${esc(projArea(p))}</td><td><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)} (${esc(p.id)})</a></td>
        <td class="n">${fmt(p.a, unit)}</td><td class="n">${fmt(p.e, unit)}</td><td class="n">${p.overlap === 'Y' ? 'Y' : p.overlap === 'N' ? 'N' : '—'}</td></tr>`).join('')}</tbody></table></div>
    ${rows.length > 15 ? `<button class="btn-sm" id="ops-all" style="margin-top:8px">${S.opsAll ? 'Show fewer' : `Show all ${rows.length} rows`}</button>` : ''}
    <div class="na" style="margin-top:6px">Source: Scorecard API getSCResultIndicatorSummary (the Scorecard's “World Bank Operations” table). Each project links to projects.worldbank.org.</div>`;
}
function wireOps(X){
  const ps = projects(X), box = $('ops'), redraw = () => { box.innerHTML = opsHTML(X, ps); wireOps(X); icons(); };
  const q = $('ops-q'); if (!q) return;
  q.oninput = () => { S.opsQ = q.value; const pos = q.selectionStart; redraw(); const n = $('ops-q'); n.focus(); n.setSelectionRange(pos, pos); };
  box.querySelectorAll('th[data-s]').forEach(th => th.onclick = () => { S.opsSort = th.dataset.s; redraw(); });
  $('ops-all')?.addEventListener('click', () => { S.opsAll = !S.opsAll; redraw(); });
  $('ops-csv').onclick = () => {
    const lines = [['country', 'proj_id', 'project', 'achieved', 'expected', 'overlap_flag', 'url'].join(',')]
      .concat(ps.map(p => [projArea(p), p.id, p.name, p.a ?? '', p.e ?? '', p.overlap ?? '', p.url].map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')));
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/csv'}));
    a.download = `${X.indicator.ind_code}_FY${S.fy}_projects.csv`; a.click();
  };
}

/* ---------- charts ---------- */
function drawDataPage(X){
  const unit = X.indicator.unit;
  $('dp').querySelectorAll('[data-sub]').forEach(b => b.onclick = () => { S.sub = b.dataset.sub; renderOverview(); });
  $('map-field').querySelectorAll('button').forEach(b => b.onclick = () => { S.mapField = +b.dataset.m; renderOverview(); });
  $('map-view').querySelectorAll('button').forEach(b => b.onclick = () => { S.mapView = b.dataset.v; renderOverview(); });
  $('bd-tab').querySelectorAll('button').forEach(b => b.onclick = () => { S.tab = b.dataset.t; renderOverview(); });
  drawMap(X, unit); drawBreakdown(X, unit);
  share(X, 'sh-f', 'F', 'Female'); share(X, 'sh-y', 'Y', 'Youth'); fcsShare(X);
  const cg = GROUPS.map(([k, l]) => ({label: l, s: sumOf(X, S.org, members(S.area).filter(c => D.areas[c][k]))})).filter(x => x.s);
  cg.length ? gbar('cg', cg.map(x => ({label: x.label, v: x.s.v})), unit) : empty('cg', 'No country-group values for this selection.');
  wireOps(X);
}
function drawMap(X, unit){
  const locs = members(S.area).filter(c => { const v = cell(X, S.org, c); return v && v[S.mapField] != null; });
  if (S.mapView === 'table'){
    const rows = locs.map(c => ({c, v: cell(X, S.org, c)})).sort((a, b) => (b.v[S.mapField] || 0) - (a.v[S.mapField] || 0));
    const nd = members(S.area).filter(c => { const v = cell(X, S.org, c); return v && v[0] == null && v[1] == null; }).length;
    $('map-box').innerHTML = rows.length ? `<div class="tblwrap" style="max-height:420px"><table class="ops"><thead><tr><th>Country/economy</th><th class="n">Achieved</th><th class="n">Expected</th></tr></thead><tbody>
      ${rows.map(r => `<tr><td><a data-area="${r.c}">${esc(areaName(r.c))}</a></td><td class="n">${fmt(r.v[0], unit)}</td><td class="n">${fmt(r.v[1], unit)}</td></tr>`).join('')}</tbody></table></div>
      ${nd ? `<div class="na" style="margin-top:6px">${nd} countries report this indicator without a disclosed value.</div>` : ''}` : '<div class="na">No country-level values for this selection.</div>';
    $('map-box').querySelectorAll('[data-area]').forEach(a => a.onclick = () => setF({area: a.dataset.area}, `Overview filtered: ${esc(areaName(a.dataset.area))}`));
    return;
  }
  $('map-box').innerHTML = '<div class="chart" id="map" style="height:360px"></div>';
  if (!locs.length) return empty('map', 'No country-level values for this selection.');
  const focus = S.area !== 'ACW' && !isGroup(S.area);
  Plotly.react('map', [{type: 'choropleth', locations: locs, z: locs.map(c => cell(X, S.org, c)[S.mapField]),
    text: locs.map(c => { const v = cell(X, S.org, c); return `<b>${esc(areaName(c))}</b><br>Achieved ${fmt(v[0], unit)}<br>Expected ${fmt(v[1], unit)}`; }),
    hovertemplate: '%{text}<extra></extra>', colorscale: [[0, '#f3efcf'], [.35, '#a9d3c9'], [.7, '#4f95c0'], [1, '#002244']], zmin: 0,
    marker: {line: {color: locs.map(c => c === S.area ? '#0b0b0b' : '#ffffff'), width: locs.map(c => c === S.area ? 2 : .5)}},
    showscale: locs.length > 1, colorbar: {orientation: 'h', thickness: 8, len: .5, x: .5, y: -.02, tickformat: '~s', tickfont: {size: 10, color: css('--muted')}, outlinewidth: 0}}],
    base({geo: {showframe: false, showcoastlines: false, projection: {type: 'natural earth'}, bgcolor: 'rgba(0,0,0,0)', landcolor: '#e6eaee', showland: true,
      countrycolor: '#ffffff', showcountries: true, fitbounds: focus ? 'locations' : false, lataxis: focus ? undefined : {range: [-45, 72]}}, margin: {l: 0, r: 0, t: 0, b: 24}}), CFG)
    .then(() => { const n = $('map'); n.removeAllListeners?.('plotly_click'); n.on('plotly_click', ev => { const a = ev.points[0].location; setF({area: a}, `Map click → overview filtered: ${esc(areaName(a))}`); }); });
}
function drawBreakdown(X, unit){
  let rows = [], note = '';
  if (S.tab === 'REGION'){
    rows = REGIONS.map(a => ({key: a, label: areaName(a), v: (cell(X, S.org, a) || [])})); note = 'WBG regions.';
  } else if (S.tab === 'INCOME'){
    rows = INCOME.map(([k, l]) => ({key: k, label: l, v: (sumOf(X, S.org, members(S.area).filter(c => D.areas[c].income === k)) || {}).v || []}));
    note = 'Sum of country values in each income group.';
  } else if (S.tab === 'FIN'){
    rows = ['IBRD', 'IDA'].map(o => ({key: o, label: o, v: (value(X, o, S.area) || {}).v || []}));
    note = 'World Bank financing institutions. Published for all countries and for regions.';
  } else {
    rows = ['WB', 'IFC', 'MIGA'].map(o => ({key: o, label: ORG_LABEL[o], v: (value(X, o, S.area) || {}).v || []}));
    const ifc = value(X, 'IFC', S.area);
    note = ifc && ifc.v[1] == null ? 'IFC reports this indicator here but does not disclose the value.' : '';
  }
  rows = rows.filter(r => r.v[1] != null);
  $('bd-note').textContent = rows.length ? note : '';
  rows.length ? gbar('bd-chart', rows, unit, S.area) : empty('bd-chart', 'Not published for this selection.');
}
function gbar(el, rows, unit, hl){                        // grouped horizontal bars: achieved / expected
  const y = rows.map(r => r.label);
  const tr = [['Achieved', 0, COL.a()], ['Expected', 1, COL.e()]].map(([n, i, c]) => ({type: 'bar', orientation: 'h', name: n, y, x: rows.map(r => r.v[i]),
    marker: {color: c}, customdata: rows.map(r => fmt(r.v[i], unit)), hovertemplate: `%{y}<br>${n.toLowerCase()} %{customdata}<extra></extra>`}));
  Plotly.react(el, tr, base({barmode: 'group', bargap: .35, showlegend: true, legend: {orientation: 'h', y: -0.18, x: 0, font: {size: 11}},
    xaxis: {...axis(), tickformat: '~s'}, yaxis: {...axis(), autorange: 'reversed', gridcolor: 'rgba(0,0,0,0)'},
    margin: {l: Math.min(230, 12 + 6.4 * Math.max(...y.map(s => s.length))), r: 16, t: 6, b: 46}}), CFG);
}
function shareBars(el, part, whole, label, unit){         // share of the overall total, achieved and expected
  const pct = (i) => part && whole && part[i] != null && whole[i] ? 100 * part[i] / whole[i] : null;
  const s = [pct(0), pct(1)];
  if (s[0] == null && s[1] == null) return false;
  const x = ['Achieved', 'Expected'];
  Plotly.react(el, [
    {type: 'bar', x, y: [100, 100], marker: {color: COL.rest()}, name: 'Overall', hoverinfo: 'skip', width: .35},
    {type: 'bar', x, y: s, marker: {color: COL.a()}, name: label.length > 18 ? 'FCS' : label, width: .35, text: s.map(v => v == null ? '' : Math.round(v) + '%'), textposition: 'outside',
     customdata: [0, 1].map(i => `${fmt(part[i], unit)} of ${fmt(whole[i], unit)}`), hovertemplate: `${label} %{x}: %{customdata}<extra></extra>`}],
    base({barmode: 'overlay', showlegend: true, legend: {orientation: 'h', y: -0.2, x: 0, font: {size: 11}}, yaxis: {...axis(), range: [0, 110], ticksuffix: '%'}, xaxis: axis(), margin: {l: 40, r: 10, t: 10, b: 50}}), CFG);
  return true;
}
function share(X, el, bd, label){
  const v = (b) => { const k = S.sex; S.sex = b; const r = value(X, S.org, S.area); S.sex = k; return r && r.v; };
  const ok = shareBars(el, v(bd), v('_T'), label, X.indicator.unit);
  if (!ok) empty(el, `No ${label.toLowerCase()} breakdown for this selection.`);
  $(el + '-n').textContent = ok ? `Share of the ${ORG_LABEL[S.org]} total.` : '';
}
function fcsShare(X){
  const whole = (value(X, S.org, S.area) || {}).v;
  const part = S.area === 'ACW' ? (cell(X, S.org, 'FCS') || (sumOf(X, S.org, members('FCS')) || {}).v) : (sumOf(X, S.org, members(S.area).filter(c => D.areas[c].fcs)) || {}).v;
  const ok = shareBars('sh-fcs', part, whole, 'Fragile and Conflict-Affected Situations', X.indicator.unit);
  if (!ok) empty('sh-fcs', 'No FCS values for this selection.');
  $('sh-fcs-n').textContent = ok ? (S.area === 'ACW' ? 'FCS row as published, share of the total.' : 'Sum of FCS countries in this area, share of the total.') : '';
}

/* ---------- client context (kept from the outcome page) ---------- */
function ctxPick(area){
  for (const c of D.context_indicators){ const s = (D.CTX[area] || {})[c.ind_code]; if (s && Object.keys(s).length >= 2) return {c, s}; }
  for (const c of D.context_indicators){ const s = (D.CTX.ACW || {})[c.ind_code]; if (s && Object.keys(s).length) return {c, s}; }
  return null;
}
function renderContext(){
  const area = isGroup(S.area) ? 'ACW' : S.area, cp = ctxPick(area);
  $('ctx-chart').style.display = cp ? '' : 'none';
  if (!cp){ $('ctx-stat').innerHTML = '<div class="na">No client-context series for this outcome area.</div>'; return; }
  const code = cp.c.ind_code, list = []; const add = a => { const s = (D.CTX[a] || {})[code]; if (a && s && Object.keys(s).length && !list.find(x => x.a === a)) list.push({a, s}); };
  add(area); if (isCountry(area)) add(regionOf(area)); add('ACW');
  const main = list[0], last = Object.keys(main.s).at(-1), mv = main.s[last], pctU = cp.c.unit === 'Percentage';
  $('ctx-stat').innerHTML = `<div class="label">${esc(cp.c.display_name)}</div><div class="hero-num">${pctU ? mv.toFixed(1) + '%' : fmt(mv, cp.c.unit)}</div>
    <div class="note">${esc(areaName(main.a))} · ${last}${main.a !== area ? ` · no data for ${esc(areaName(area))}` : ''}</div>`;
  const cols = ['--s1', '--s2', '--muted'];
  const tr = list.map((x, i) => ({x: Object.keys(x.s).map(Number), y: Object.values(x.s), type: 'scatter', mode: Object.keys(x.s).length > 1 ? 'lines' : 'markers', name: areaName(x.a),
    line: {color: css(cols[i]), width: 2}, marker: {size: 8, color: css(cols[i])}, hovertemplate: `${esc(areaName(x.a))} %{x}: %{y:.1f}<extra></extra>`}));
  const ann = list.map(x => ({x: +Object.keys(x.s).at(-1), y: Object.values(x.s).at(-1), text: ` ${areaName(x.a).split(/[ ,&]/)[0]} ${Object.values(x.s).at(-1).toFixed(1)}`, showarrow: false, xanchor: 'left', font: {size: 11, color: css('--ink-2')}}));
  Plotly.react('ctx-chart', tr, base({xaxis: {...axis(), tickformat: 'd'}, yaxis: {...axis(), rangemode: 'tozero'}, margin: {l: 36, r: 90, t: 10, b: 28}, annotations: ann, hovermode: 'x unified'}), CFG);
}
function empty(el, m){ Plotly.purge(el); $(el).innerHTML = `<div class="na" style="padding:50px 0;text-align:center">${m}</div>`; }
