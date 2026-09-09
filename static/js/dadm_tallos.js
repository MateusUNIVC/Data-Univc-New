(() => {
  'use strict';

  const q = (selector, root=document) => root.querySelector(selector);
  const qa = (selector, root=document) => [...root.querySelectorAll(selector)];
  const COLORS = ['#0e8058','#4477a6','#c49622','#b34848','#7a63a8','#5d8876'];
  const TALLOS_SECTIONS = new Set(['tallos-overview','tallos-operators','tallos-departments','tallos-experience','tallos-sync']);

  const state = {
    user: null,
    access: null,
    start: '',
    end: '',
    comparison: 'none',
    grain: 'month',
    startMonth: '',
    endMonth: '',
    filters: {department:'', employee:'', channel:'', status:'', tabulation:''},
    dashboard: null,
    filterOptions: null,
    sort: {key:'attendances', dir:-1},
    compareEmployees: new Set(),
    departmentMaps: [],
    currentSection: 'dashboard',
    connection: null,
    loading: 0,
  };

  function escapeHtml(value='') { return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch])); }
  function iso(d){ return d.toISOString().slice(0,10); }
  function todayLocal(){ const now=new Date(); return new Date(now.getFullYear(),now.getMonth(),now.getDate()); }
  function monthValue(d){ return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`; }
  function monthFirst(value){ return `${value}-01`; }
  function monthLast(value){ const [y,m]=String(value).split('-').map(Number);const d=new Date(y,m,0);return `${y}-${String(m).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
  function setMonthRange(startMonth,endMonth){
    state.startMonth=startMonth;state.endMonth=endMonth;state.start=monthFirst(startMonth);state.end=monthLast(endMonth);
    if(q('#tallosFilterStartMonth'))q('#tallosFilterStartMonth').value=startMonth;
    if(q('#tallosFilterEndMonth'))q('#tallosFilterEndMonth').value=endMonth;
  }
  function apiUrl(path, params={}) { const u=new URL(path,location.origin);u.searchParams.set('diretoria','DADM');Object.entries(params).forEach(([k,v])=>{if(v!==undefined&&v!==null&&v!=='')u.searchParams.set(k,v)});return u.pathname+u.search; }
  async function api(path, options={}, params={}) {
    const response=await fetch(apiUrl(path,params),{credentials:'same-origin',...options,headers:{Accept:'application/json',...(options.headers||{})}});
    if(response.status===401){ location.assign('/'); throw new Error('Sessão expirada.'); }
    if(!response.ok){ let payload=null;try{payload=await response.json()}catch{}const detail=payload?.detail;const message=typeof detail==='string'?detail:detail?.erro||payload?.erro||`Erro HTTP ${response.status}`;const error=new Error(message);error.payload=payload;throw error; }
    return response.json();
  }
  function setLoading(active){ state.loading += active?1:-1; state.loading=Math.max(0,state.loading); q('#dadmLoading')?.classList.toggle('hidden',state.loading===0); }
  function alert(message,kind='error',timeout=6500){ const box=q('#dadmTallosAlert');if(!box)return;box.textContent=message;box.className=`dadm-tallos-alert ${kind}`;box.classList.remove('hidden');if(timeout)setTimeout(()=>box.classList.add('hidden'),timeout); }
  function hasNumericValue(value){ return value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value)); }
  function formatInt(value){ return value===null||value===undefined?'—':Number(value).toLocaleString('pt-BR',{maximumFractionDigits:0}); }
  function formatNumber(value,decimals=1){ return !hasNumericValue(value)?'—':Number(value).toLocaleString('pt-BR',{minimumFractionDigits:decimals,maximumFractionDigits:decimals}); }
  function formatPct(value,decimals=1){ return value===null||value===undefined?'—':`${formatNumber(value,decimals)}%`; }
  function formatDuration(value){
    if(value===null||value===undefined||!Number.isFinite(Number(value)))return'—';
    let s=Math.max(0,Math.round(Number(value)));const d=Math.floor(s/86400);s%=86400;const h=Math.floor(s/3600);s%=3600;const m=Math.floor(s/60);const sec=s%60;
    if(d)return`${d}d ${h}h ${m}m`;if(h)return`${h}h ${m}m`;if(m)return`${m}m ${sec}s`;return`${sec}s`;
  }
  function formatMetric(metric,value){ if(['tma','tme'].includes(metric))return formatDuration(value);if(metric==='rating')return value===null?'—':`${formatNumber(value,2)} / 10`;return formatInt(value); }
  function periodLabel(value){ if(!value)return'';if(/^\d{4}-\d{2}$/.test(value)){const[y,m]=value.split('-');return`${m}/${y.slice(-2)}`;}if(/^\d{4}-\d{2}-\d{2}$/.test(value)){const[y,m,d]=value.split('-');return`${d}/${m}`;}return value; }
  function deltaHtml(value,{lowerBetter=false,neutral=false}={}){
    if(value===null||value===undefined||!Number.isFinite(Number(value)))return'<span class="dadm-tallos-delta neutral">sem comparação</span>';
    const n=Number(value);let klass='neutral';if(!neutral&&Math.abs(n)>=.01)klass=(lowerBetter?n<0:n>0)?'good':'bad';const arrow=n>0?'↑':n<0?'↓':'→';return`<span class="dadm-tallos-delta ${klass}">${arrow} ${formatNumber(Math.abs(n),1)}%</span>`;
  }
  function empty(target,message='Sem dados no recorte selecionado.'){ const el=typeof target==='string'?q(target):target;if(el)el.innerHTML=`<div class="empty-state">${escapeHtml(message)}</div>`; }

  function readFilters(){
    const startMonth=q('#tallosFilterStartMonth')?.value||state.startMonth||monthValue(todayLocal());
    const endMonth=q('#tallosFilterEndMonth')?.value||state.endMonth||startMonth;
    if(startMonth>endMonth)throw new Error('O mês inicial não pode ser posterior ao mês final.');
    setMonthRange(startMonth,endMonth);
    state.comparison=q('#tallosFilterComparison')?.value||'none';
    state.grain='month';
    state.filters={department:q('#tallosFilterDepartment')?.value||'',employee:q('#tallosFilterEmployee')?.value||'',channel:q('#tallosFilterChannel')?.value||'',status:q('#tallosFilterStatus')?.value||'',tabulation:q('#tallosFilterTabulation')?.value||''};
  }
  function params(extra={}){ return {inicio:state.start,fim:state.end,departamento:state.filters.department,operador:state.filters.employee,canal:state.filters.channel,status:state.filters.status,tabulacao:state.filters.tabulation,comparacao:state.comparison,granularidade:state.grain,...extra}; }
  function option(value,label,selected){ return `<option value="${escapeHtml(value)}"${selected?' selected':''}>${escapeHtml(label)}</option>`; }
  function fillSelect(id,items,selected,blank){ const el=q(id);if(!el)return;el.innerHTML=option('',blank,!selected)+(items||[]).map(item=>option(item.value,item.label,item.value===selected)).join(''); }

  async function loadFilterOptions(){
    const payload=await api('/api/dadm/tallos/filters',{}, {inicio:state.start,fim:state.end});state.filterOptions=payload;
    fillSelect('#tallosFilterDepartment',payload.departments,state.filters.department,'Todos');fillSelect('#tallosFilterEmployee',payload.employees,state.filters.employee,'Todos');fillSelect('#tallosFilterChannel',payload.channels,state.filters.channel,'Todos');fillSelect('#tallosFilterStatus',payload.statuses,state.filters.status,'Todos');fillSelect('#tallosFilterTabulation',payload.tabulations,state.filters.tabulation,'Todas');
    const range=payload.available_range||{};q('#tallosDataRange').textContent=range.start&&range.end?`Base disponível: ${range.start} → ${range.end}`:'Base TALLOS ainda não sincronizada';
  }

  async function refreshAll({filters=true}={}){
    readFilters();setLoading(true);
    try{
      if(filters)await loadFilterOptions();
      state.dashboard=await api('/api/dadm/tallos/dashboard',{},params());
      renderAll();
      if(state.currentSection==='tallos-experience')await loadRatingAudit();
    }catch(error){ alert(error.message,'error',0);renderNoData(); }
    finally{setLoading(false);}
  }

  function renderNoData(){
    ['#tallosExecutiveCards','#tallosOverviewCards','#tallosExperienceCards','#tallosDADM01Cards','#tallosDADM02Cards'].forEach(sel=>{const el=q(sel);if(el)el.innerHTML='<article class="metric-card"><div class="metric-top"><span class="metric-label">TALLOS</span></div><strong class="metric-value">—</strong><span class="metric-sub">Sincronize um período para começar.</span></article>';});
    ['#tallosExecutiveVolume','#tallosExecutiveTimes','#tallosTimeTimeline','#tallosRatingTimeline','#tallosVolumeTimeline','#tallosOperatorBars','#tallosOperatorScatter','#tallosOperatorRatingBars','#tallosDepartmentBars','#tallosDepartmentRatingBars','#tallosRatingDonut','#tallosRatingHero','#tallosRatingBars','#tallosSentiment','#tallosExperienceRatingTimeline','#tallosChannelDonut','#tallosTabulationBars','#tallosDADM01Timeline','#tallosDADM01Operators','#tallosDADM02Timeline','#tallosDADM02Distribution','#tallosRatingAuditSummary'].forEach(sel=>empty(sel));
  }

  function card(label,value,sub,icon,deltaKey,opts={}){const d=state.dashboard?.deltas_pct?.[deltaKey];return`<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(label)}</span></div><strong class="metric-value">${value}</strong><span class="metric-sub">${escapeHtml(sub)}</span>${deltaHtml(d,opts)}</article>`;}
  function renderCards(){
    const s=state.dashboard?.summary||{};
    const common=[
      card('Atendimentos',formatInt(s.attendances),'sessões/linhas operacionais','A','attendances',{neutral:true}),
      card('Protocolos',formatInt(s.protocols),'conversas distintas','P','protocols',{neutral:true}),
      card('Pessoas',formatInt(s.people),'clientes distintos por ID opaco','U','people',{neutral:true}),
      card('Finalizados',formatInt(s.finalized),`${formatPct(s.finalization_rate_pct)} do volume`,'✓','finalized',{neutral:true}),
      card('Em aberto',formatInt(s.open),'atendimentos ainda ativos','○','open',{lowerBetter:true}),
      card('Tempo Médio de Espera (TME)',formatDuration(s.tme_avg_seconds),'espera até o início · mapeamento provisório','E','tme_avg_seconds',{lowerBetter:true}),
      card('Tempo Médio de Atendimento (TMA)',formatDuration(s.tma_avg_seconds),'duração após o início · campo validado','T','tma_avg_seconds',{lowerBetter:true}),
      card('Mediana do Tempo de Atendimento',formatDuration(s.tma_median_seconds),'metade dos atendimentos abaixo deste tempo','M',null,{lowerBetter:true}),
      card('P90 do Tempo de Atendimento',formatDuration(s.tma_p90_seconds),'90% dos atendimentos abaixo deste tempo','90',null,{lowerBetter:true}),
      card('Avaliação média',s.rating_avg===null||s.rating_avg===undefined?'—':`${formatNumber(s.rating_avg,2)} / 10`,`${formatInt(s.rating_count)} avaliações válidas · ${formatPct(s.rating_coverage_pct)} cobertura`,'10','rating_avg'),
    ].join('');
    q('#tallosOverviewCards').innerHTML=common;
    q('#tallosExecutiveCards').innerHTML=[
      card('Atendimentos',formatInt(s.attendances),'sessões no recorte','A','attendances',{neutral:true}),
      card('Pessoas',formatInt(s.people),'pessoas distintas','U','people',{neutral:true}),
      card('Tempo Médio de Atendimento (TMA)',formatDuration(s.tma_avg_seconds),'duração média após o início','T','tma_avg_seconds',{lowerBetter:true}),
      card('Avaliação média',s.rating_avg==null?'—':`${formatNumber(s.rating_avg,2)} / 10`,`${formatInt(s.rating_count)} respostas válidas`,'10','rating_avg'),
      card('Em aberto',formatInt(s.open),`${formatPct(s.finalization_rate_pct)} finalizados`,'○','open',{lowerBetter:true}),
    ].join('');
    q('#tallosExperienceCards').innerHTML=[
      card('Avaliação média',s.rating_avg==null?'—':`${formatNumber(s.rating_avg,2)} / 10`,'somente avaliações válidas · escala 1–10','10','rating_avg'),
      card('Avaliações válidas',formatInt(s.rating_count),`${formatPct(s.rating_coverage_pct)} dos atendimentos`,'✓','rating_count',{neutral:true}),
      card('Sem avaliação',formatInt(s.rating_missing),`${formatPct(s.rating_missing_pct)} dos atendimentos`,'—',null,{neutral:true}),
      card('Faixa observada',s.rating_min==null?'—':`${formatInt(s.rating_min)}–${formatInt(s.rating_max)}`,'mínimo e máximo válidos no recorte','↕',null,{neutral:true}),
    ].join('');
    q('#tallosExecutivePeriod').textContent=`${state.start} → ${state.end}`;
  }

  function lineChart(target,rows,defs,{yFormat=v=>formatNumber(v,1),height=285,minValue=null,maxValue=null}={}){
    const el=typeof target==='string'?q(target):target;if(!el)return;if(!rows?.length){empty(el);return}
    const width=760,m={l:54,r:20,t:30,b:55};const values=[];rows.forEach(r=>defs.forEach(d=>{const raw=r[d.key];if(hasNumericValue(raw))values.push(Number(raw))}));if(!values.length){empty(el);return}
    let min=minValue!==null?minValue:Math.min(...values),max=maxValue!==null?maxValue:Math.max(...values);if(min===max){min-=1;max+=1}if(minValue===null){const p=(max-min)*.12;min=Math.max(0,min-p);max+=p}
    const x=i=>m.l+(rows.length===1?(width-m.l-m.r)/2:(width-m.l-m.r)*i/(rows.length-1));const y=v=>height-m.b-(Number(v)-min)/(max-min)*(height-m.t-m.b);
    let grid='';for(let i=0;i<4;i++){const v=min+(max-min)*i/3,yy=y(v);grid+=`<line x1="${m.l}" x2="${width-m.r}" y1="${yy}" y2="${yy}" stroke="#e4ece8"/><text x="${m.l-8}" y="${yy+3}" text-anchor="end" font-size="9" fill="#718079">${escapeHtml(yFormat(v))}</text>`}
    const paths=defs.map((d,idx)=>{
      const color=d.color||COLORS[idx%COLORS.length];
      const points=rows.map((r,i)=>hasNumericValue(r[d.key])?{x:x(i),y:y(r[d.key]),v:r[d.key],r}:null);
      const segments=[];let current=[];
      points.forEach(point=>{if(point)current.push(point);else if(current.length){segments.push(current);current=[];}});if(current.length)segments.push(current);
      if(!segments.length)return'';
      return segments.map(segment=>{const path=segment.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' ');const circles=segment.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="3.5" fill="${color}"><title>${escapeHtml(d.label)} · ${escapeHtml(periodLabel(p.r.period))}: ${escapeHtml(yFormat(p.v))}${d.key==='rating_avg'&&p.r.rating_count!=null?` · ${formatInt(p.r.rating_count)} avaliações`:''}</title></circle>`).join('');return`<path d="${path}" fill="none" stroke="${color}" stroke-width="2.2"/>${circles}`}).join('');
    }).join('');
    const labels=rows.map((r,i)=>`<text x="${x(i)}" y="${height-26}" text-anchor="middle" font-size="9" fill="#718079">${escapeHtml(periodLabel(r.period))}</text>`).join('');const legend=defs.map((d,i)=>`<g transform="translate(${m.l+i*145},12)"><circle cx="0" cy="0" r="4" fill="${d.color||COLORS[i%COLORS.length]}"/><text x="8" y="3" font-size="9" fill="#52635c">${escapeHtml(d.label)}</text></g>`).join('');
    el.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img">${grid}${paths}${labels}${legend}</svg>`;
  }

  function stackedVolume(target,rows){const el=typeof target==='string'?q(target):target;if(!el)return;if(!rows?.length){empty(el);return}const width=760,height=285,m={l:48,r:18,t:28,b:55},max=Math.max(...rows.map(r=>Number(r.attendances)||0),1),slot=(width-m.l-m.r)/rows.length,bar=Math.max(9,Math.min(38,slot*.62));const y=v=>height-m.b-(Number(v)/max)*(height-m.t-m.b);let grid='';for(let i=0;i<4;i++){const v=max*i/3,yy=y(v);grid+=`<line x1="${m.l}" x2="${width-m.r}" y1="${yy}" y2="${yy}" stroke="#e4ece8"/><text x="${m.l-6}" y="${yy+3}" text-anchor="end" font-size="9" fill="#718079">${formatInt(v)}</text>`}const bars=rows.map((r,i)=>{const x=m.l+i*slot+(slot-bar)/2,finalized=Number(r.finalized)||0,open=Number(r.open)||0,fh=(finalized/max)*(height-m.t-m.b),oh=(open/max)*(height-m.t-m.b),base=height-m.b;return`<g><rect x="${x}" y="${base-fh}" width="${bar}" height="${fh}" rx="3" fill="${COLORS[0]}"><title>${periodLabel(r.period)} · finalizados ${formatInt(finalized)}</title></rect><rect x="${x}" y="${base-fh-oh}" width="${bar}" height="${oh}" rx="3" fill="${COLORS[2]}"><title>${periodLabel(r.period)} · abertos ${formatInt(open)}</title></rect><text x="${x+bar/2}" y="${height-27}" text-anchor="middle" font-size="9" fill="#718079">${periodLabel(r.period)}</text></g>`}).join('');el.innerHTML=`<svg viewBox="0 0 ${width} ${height}">${grid}${bars}<g transform="translate(${m.l},13)"><circle r="4" fill="${COLORS[0]}"/><text x="8" y="3" font-size="9" fill="#52635c">Finalizados</text><circle cx="90" r="4" fill="${COLORS[2]}"/><text x="98" y="3" font-size="9" fill="#52635c">Abertos</text></g></svg>`;}

  function bars(target,rows,{label='label',value='count',formatter=formatInt,limit=12}={}){const el=typeof target==='string'?q(target):target;if(!el)return;const data=(rows||[]).filter(r=>hasNumericValue(r[value])).slice(0,limit);if(!data.length){empty(el);return}const max=Math.max(...data.map(r=>Number(r[value])),1);el.innerHTML=data.map(r=>`<div class="dadm-tallos-bar-row"><span class="dadm-tallos-bar-label" title="${escapeHtml(r[label])}">${escapeHtml(r[label])}</span><div class="dadm-tallos-bar-track"><div class="dadm-tallos-bar-fill" style="width:${Math.max(1,Number(r[value])/max*100)}%"></div></div><span class="dadm-tallos-bar-value">${formatter(r[value],r)}</span></div>`).join('');}

  function donut(target,rows,{labelFn=r=>r.label,value='count',center=''}={}){const el=typeof target==='string'?q(target):target;if(!el)return;const data=(rows||[]).filter(r=>(Number(r[value])||0)>0);if(!data.length){empty(el);return}const total=data.reduce((a,r)=>a+(Number(r[value])||0),0);let cursor=0;const stops=[];data.forEach((r,i)=>{const pct=(Number(r[value])||0)/total*100;stops.push(`${COLORS[i%COLORS.length]} ${cursor}% ${cursor+pct}%`);cursor+=pct});const legend=data.map((r,i)=>`<div class="dadm-tallos-donut-row"><span class="dadm-tallos-legend-dot" style="background:${COLORS[i%COLORS.length]}"></span><span>${escapeHtml(labelFn(r))}</span><span class="dadm-tallos-legend-count">${formatInt(r[value])} · ${formatNumber((Number(r[value])||0)/total*100,1)}%</span></div>`).join('');el.innerHTML=`<div class="dadm-tallos-donut" style="background:conic-gradient(${stops.join(',')})"><div class="dadm-tallos-donut-center"><strong>${escapeHtml(center||formatInt(total))}</strong><span>total</span></div></div><div class="dadm-tallos-donut-legend">${legend}</div>`;}

  function scatter(target,rows){const el=typeof target==='string'?q(target):target;if(!el)return;const data=(rows||[]).filter(r=>hasNumericValue(r.tma_avg_seconds)&&hasNumericValue(r.rating_avg)&&Number(r.rating_count||0)>0);if(!data.length){empty(el,'Sem operadores com TMA e avaliação no mesmo recorte.');return}const width=760,height=330,m={l:58,r:24,t:28,b:55},maxX=Math.max(...data.map(r=>Number(r.tma_avg_seconds)),1)*1.08,minY=1,maxY=10,x=v=>m.l+Number(v)/maxX*(width-m.l-m.r),y=v=>height-m.b-(Number(v)-minY)/(maxY-minY)*(height-m.t-m.b),maxVol=Math.max(...data.map(r=>r.attendances),1);let grid='';for(let i=0;i<6;i++){const val=minY+(maxY-minY)*i/5,yy=y(val);grid+=`<line x1="${m.l}" x2="${width-m.r}" y1="${yy}" y2="${yy}" stroke="#e5ece8"/><text x="${m.l-8}" y="${yy+3}" text-anchor="end" font-size="9" fill="#718079">${formatNumber(val,0)}</text>`}const bubbles=data.map((r,i)=>{const radius=5+Math.sqrt(r.attendances/maxVol)*12;return`<circle cx="${x(r.tma_avg_seconds)}" cy="${y(r.rating_avg)}" r="${radius}" fill="${COLORS[i%COLORS.length]}" fill-opacity=".72"><title>${escapeHtml(r.employee_name)} · TMA ${escapeHtml(formatDuration(r.tma_avg_seconds))} · avaliação ${escapeHtml(formatNumber(r.rating_avg,2))}/10 · ${formatInt(r.rating_count)} avaliações · ${formatInt(r.attendances)} atendimentos</title></circle>`}).join('');el.innerHTML=`<svg viewBox="0 0 ${width} ${height}">${grid}<line x1="${m.l}" x2="${width-m.r}" y1="${height-m.b}" y2="${height-m.b}" stroke="#9cafa5"/><text x="${width/2}" y="${height-12}" text-anchor="middle" font-size="10" fill="#52635c">TMA — Tempo Médio de Atendimento →</text>${bubbles}</svg>`;}

  function renderRatingDetails(){
    const d=state.dashboard||{},s=d.summary||{},ratings=[...(d.ratings||[])].sort((a,b)=>Number(b.rating)-Number(a.rating));
    const hero=q('#tallosRatingHero');
    if(hero){
      if(s.rating_avg==null||!s.rating_count){empty(hero,'Nenhuma avaliação válida no recorte. Registros sem avaliação não entram na média.');}
      else{
        const fill=Math.max(0,Math.min(100,Number(s.rating_avg)/10*100));
        hero.innerHTML=`<div class="dadm-tallos-rating-score">${formatNumber(s.rating_avg,2)} <span>/ 10</span></div><div class="dadm-tallos-score-meter" aria-label="${formatNumber(s.rating_avg,2)} de 10"><span style="width:${fill}%"></span></div><div class="dadm-tallos-rating-meta"><strong>${formatInt(s.rating_count)}</strong> avaliações válidas · <strong>${formatPct(s.rating_coverage_pct)}</strong> de cobertura<br><strong>${formatInt(s.rating_missing)}</strong> atendimentos sem avaliação (${formatPct(s.rating_missing_pct)})<br><span class="dadm-tallos-table-note">A média usa somente <code>level</code> entre 1 e 10; S/A, nulo e level=0 ficam fora do cálculo.</span></div>`;
      }
    }
    const barsEl=q('#tallosRatingBars');
    if(barsEl){
      const valid=ratings.filter(r=>Number(r.count)>0);
      if(!valid.length)empty(barsEl,'Nenhuma avaliação válida no recorte.');
      else barsEl.innerHTML=ratings.map(r=>`<div class="dadm-tallos-rating-row"><span class="dadm-tallos-rating-label">Nota ${formatInt(r.rating)}</span><div class="dadm-tallos-rating-track"><div class="dadm-tallos-rating-fill" style="width:${Math.max(0,Math.min(100,Number(r.pct)||0))}%"></div></div><span class="dadm-tallos-rating-value">${formatInt(r.count)} · ${formatPct(r.pct)}</span></div>`).join('');
    }
    const diagnostic=q('#tallosSentiment');
    if(diagnostic){
      if(!s.attendances)empty(diagnostic,'Nenhum atendimento no recorte.');
      else diagnostic.innerHTML=`<div class="dadm-tallos-sentiment-card good"><span>Avaliações válidas · escala 1–10</span><strong>${formatInt(s.rating_count)}</strong><small>${formatPct(s.rating_coverage_pct)} dos atendimentos possuem nota</small></div><div class="dadm-tallos-sentiment-card neutral"><span>Sem avaliação</span><strong>${formatInt(s.rating_missing)}</strong><small>${formatPct(s.rating_missing_pct)} dos atendimentos · não entram na média</small></div><div class="dadm-tallos-sentiment-card"><span>Faixa observada</span><strong>${s.rating_min==null?'—':`${formatInt(s.rating_min)} a ${formatInt(s.rating_max)}`}</strong><small>mínimo e máximo entre as avaliações válidas do recorte</small></div>`;
    }
    lineChart('#tallosExperienceRatingTimeline',d.timeline||[],[{key:'rating_avg',label:'Avaliação média',color:COLORS[0]}],{yFormat:v=>`${formatNumber(v,1)}/10`,minValue:1,maxValue:10});
  }

  function renderDadmTallosIndicators(){
    const d=state.dashboard||{},s=d.summary||{},timeline=d.timeline||[],monthly=d.operators_monthly||[];
    const d1=q('#tallosDADM01Cards');if(d1)d1.innerHTML=[
      card('Tempo Médio de Espera (TME)',formatDuration(s.tme_avg_seconds),'espera até o início · mapeamento provisório','', 'tme_avg_seconds',{lowerBetter:true}),
      card('Tempo Médio de Atendimento (TMA)',formatDuration(s.tma_avg_seconds),'duração após o início · validado','', 'tma_avg_seconds',{lowerBetter:true}),
      card('Mediana do TMA',formatDuration(s.tma_median_seconds),'metade dos atendimentos abaixo deste tempo','',null,{neutral:true}),
      card('P90 do TMA',formatDuration(s.tma_p90_seconds),'90% dos atendimentos abaixo deste tempo','',null,{neutral:true}),
      card('Atendimentos finalizados',formatInt(s.finalized),`${formatPct(s.finalization_rate_pct)} do volume`,'','finalized',{neutral:true}),
    ].join('');
    lineChart('#tallosDADM01Timeline',timeline,[{key:'tme_avg_seconds',label:'Tempo Médio de Espera (TME)',color:COLORS[1]},{key:'tma_avg_seconds',label:'Tempo Médio de Atendimento (TMA)',color:COLORS[0]}],{yFormat:formatDuration});
    bars('#tallosDADM01Operators',(d.operators||[]).filter(r=>r.tma_avg_seconds!=null).map(r=>({label:r.employee_name,value:r.tma_avg_seconds,tme:r.tme_avg_seconds})),{value:'value',formatter:(v,r)=>`TMA ${formatDuration(v)} · TME ${formatDuration(r.tme)}`});

    const executive01=q('#tallosExecutiveDadm01');if(executive01)executive01.innerHTML=`<div class="dadm-tallos-indicator-kpis"><div><span>Tempo Médio de Espera (TME)</span><strong>${formatDuration(s.tme_avg_seconds)}</strong><small>espera até o início</small></div><div><span>Tempo Médio de Atendimento (TMA)</span><strong>${formatDuration(s.tma_avg_seconds)}</strong><small>duração após o início</small></div></div>`;
    const executive02=q('#tallosExecutiveDadm02');if(executive02)executive02.innerHTML=`<div class="dadm-tallos-indicator-kpis"><div><span>Avaliação média</span><strong>${s.rating_avg==null?'—':`${formatNumber(s.rating_avg,2)} / 10`}</strong><small>${formatInt(s.rating_count)} avaliações válidas</small></div><div><span>Cobertura</span><strong>${formatPct(s.rating_coverage_pct)}</strong><small>S/A e ausências ficam fora da média</small></div></div>`;

    const d2=q('#tallosDADM02Cards');if(d2)d2.innerHTML=[
      card('Avaliação média no período',s.rating_avg==null?'—':`${formatNumber(s.rating_avg,2)} / 10`,'somente avaliações válidas de 1 a 10','', 'rating_avg'),
      card('Avaliações válidas',formatInt(s.rating_count),'notas que entram na média','', 'rating_count',{neutral:true}),
      card('Sem avaliação',formatInt(s.rating_missing),'S/A, nulo e level=0','',null,{neutral:true}),
      card('Cobertura das avaliações',formatPct(s.rating_coverage_pct),'avaliações válidas ÷ atendimentos','', 'rating_coverage_pct',{neutral:true}),
    ].join('');
    lineChart('#tallosDADM02Timeline',timeline,[{key:'rating_avg',label:'Avaliação média',color:COLORS[0]}],{yFormat:v=>`${formatNumber(v,1)}/10`,minValue:1,maxValue:10});
    const dist=(d.ratings||[]).slice().sort((a,b)=>b.rating-a.rating);const distEl=q('#tallosDADM02Distribution');if(distEl)distEl.innerHTML=dist.map(r=>`<div class="dadm-tallos-rating-row"><span class="dadm-tallos-rating-label">Nota ${formatInt(r.rating)}</span><div class="dadm-tallos-rating-track"><div class="dadm-tallos-rating-fill" style="width:${Math.max(0,Math.min(100,Number(r.pct)||0))}%"></div></div><span class="dadm-tallos-rating-value">${formatInt(r.count)} · ${formatPct(r.pct)}</span></div>`).join('');
    const monthlyEl=q('#tallosDADM02Monthly');if(monthlyEl)monthlyEl.innerHTML=monthly.length?monthly.map(r=>`<tr><td>${escapeHtml(periodLabel(r.period))}</td><td>${escapeHtml(r.employee_name)}</td><td>${r.rating_avg==null?'—':`${formatNumber(r.rating_avg,2)} / 10`}</td><td>${formatInt(r.rating_count)}</td><td>${formatInt(r.rating_missing)}</td><td>${formatPct(r.rating_coverage_pct)}</td></tr>`).join(''):'<tr><td colspan="6">Sem dados mensais no período.</td></tr>';
  }

  async function loadRatingAudit(){
    const summary=q('#tallosRatingAuditSummary'),table=q('#tallosRatingAuditTable');if(!summary||!table||!state.connection?.data_available)return;
    try{const payload=await api('/api/dadm/tallos/rating-audit',{},params({comparacao:'',granularidade:''}));
      summary.innerHTML=`<div><strong>${formatInt(payload.valid_count)}</strong><span>avaliações válidas 1–10</span></div><div><strong>${payload.valid_average==null?'—':`${formatNumber(payload.valid_average,2)}/10`}</strong><span>média auditada</span></div><div><strong>${formatInt(payload.raw_zero_count)}</strong><span>level=0 tratados como ausência</span></div><div><strong>${formatInt(payload.raw_missing_count)}</strong><span>nulos/S/A no payload</span></div>`;
      const rows=payload.samples||[];table.innerHTML=rows.length?rows.map(r=>`<tr><td>${escapeHtml(periodLabel(r.period))}</td><td>${escapeHtml(r.employee_name)}</td><td><code>${escapeHtml(r.protocol||'—')}</code></td><td>${r.raw_level==null?'—':escapeHtml(r.raw_level)}</td><td>${r.normalized_rating==null?'—':escapeHtml(r.normalized_rating)}</td><td>${escapeHtml(r.classification)}</td></tr>`).join(''):'<tr><td colspan="6">Nenhuma avaliação numérica no período.</td></tr>';
    }catch(e){empty(summary,'Não foi possível carregar a auditoria de avaliações.');table.innerHTML='<tr><td colspan="6">Auditoria indisponível.</td></tr>';}
  }

  function renderAll(){const d=state.dashboard;if(!d){renderNoData();return}renderCards();const timeline=d.timeline||[];lineChart('#tallosTimeTimeline',timeline,[{key:'tme_avg_seconds',label:'Tempo Médio de Espera (TME)',color:COLORS[1]},{key:'tma_avg_seconds',label:'Tempo Médio de Atendimento (TMA)',color:COLORS[0]}],{yFormat:formatDuration});lineChart('#tallosExecutiveTimes',timeline,[{key:'tme_avg_seconds',label:'Tempo Médio de Espera (TME)',color:COLORS[1]},{key:'tma_avg_seconds',label:'Tempo Médio de Atendimento (TMA)',color:COLORS[0]}],{yFormat:formatDuration});lineChart('#tallosRatingTimeline',timeline,[{key:'rating_avg',label:'Avaliação média',color:COLORS[0]}],{yFormat:v=>`${formatNumber(v,1)}/10`,minValue:1,maxValue:10});stackedVolume('#tallosVolumeTimeline',timeline);stackedVolume('#tallosExecutiveVolume',timeline);bars('#tallosOperatorBars',(d.operators||[]).map(r=>({label:r.employee_name,count:r.attendances})),{});renderOperators();renderDepartments();renderExperience();renderRatingDetails();renderDadmTallosIndicators();renderBridges();renderContext();renderFieldStatus();renderLastSync();}

  function renderOperators(){
    const monthly=[...(state.dashboard?.operators_monthly||[])];
    q('#tallosOperatorsTable').innerHTML=monthly.length?monthly.map(r=>`<tr><td>${escapeHtml(periodLabel(r.period))}</td><td><button class="dadm-tallos-link-button" data-tallos-employee="${escapeHtml(r.employee_id)}">${escapeHtml(r.employee_name)}</button></td><td>${formatInt(r.attendances)}</td><td>${formatInt(r.protocols)}</td><td>${formatDuration(r.tme_avg_seconds)}</td><td>${formatDuration(r.tma_avg_seconds)}</td><td>${r.rating_avg==null?'—':`${formatNumber(r.rating_avg,2)} / 10`}</td><td>${formatInt(r.rating_count)}</td><td>${formatInt(r.rating_missing)}</td><td>${formatPct(r.rating_coverage_pct)}</td></tr>`).join(''):'<tr><td colspan="10">Nenhum operador no período selecionado.</td></tr>';
    const rows=state.dashboard?.operators||[];
    const latestPeriod=monthly.length?[...new Set(monthly.map(r=>r.period))].sort().at(-1):null;
    const latestRows=latestPeriod?monthly.filter(r=>r.period===latestPeriod):[];
    const periodBadge=q('#tallosOperatorRatingPeriod');if(periodBadge)periodBadge.textContent=latestPeriod?`mês ${periodLabel(latestPeriod)}`:'sem mês';
    const scatterBadge=q('#tallosOperatorScatterPeriod');if(scatterBadge)scatterBadge.textContent=latestPeriod?`mês ${periodLabel(latestPeriod)}`:'sem mês';
    bars('#tallosOperatorRatingBars',latestRows.filter(r=>r.rating_avg!=null).sort((a,b)=>b.rating_avg-a.rating_avg).map(r=>({label:r.employee_name,value:r.rating_avg,rating_count:r.rating_count})),{value:'value',formatter:(v,r)=>`${formatNumber(v,2)}/10 · n=${formatInt(r.rating_count)}`});
    scatter('#tallosOperatorScatter',latestRows);renderOperatorChoices();
  }
  function renderOperatorChoices(){const top=(state.dashboard?.operators||[]).slice(0,12);q('#tallosOperatorCompareChoices').innerHTML=top.length?top.map(r=>`<label class="dadm-tallos-choice"><input type="checkbox" value="${escapeHtml(r.employee_id)}" ${state.compareEmployees.has(String(r.employee_id))?'checked':''}><span>${escapeHtml(r.employee_name)}</span></label>`).join(''):'<span class="table-subtitle">Sem operadores para comparar.</span>';}

  async function compareOperators(){const selected=qa('#tallosOperatorCompareChoices input:checked').map(x=>x.value).slice(0,4);state.compareEmployees=new Set(selected);if(selected.length<2){empty('#tallosOperatorComparisonChart','Selecione pelo menos dois operadores.');return}const metric=q('#tallosCompareMetric').value;setLoading(true);try{const payload=await api('/api/dadm/tallos/operator-comparison',{},params({operadores:selected.join(','),metrica:metric,comparacao:'',granularidade:''}));renderComparisonChart(payload.series||[],metric)}catch(e){alert(e.message)}finally{setLoading(false)}}
  function renderComparisonChart(rows,metric){const periods=[...new Set(rows.map(r=>r.period))].sort(),employees=[...new Map(rows.map(r=>[r.employee_id,r.employee_name])).entries()];if(!rows.length||!periods.length){empty('#tallosOperatorComparisonChart');return}const matrix=periods.map(period=>{const obj={period};employees.forEach(([id])=>{const r=rows.find(x=>x.period===period&&x.employee_id===id);obj[id]=r?.value??null});return obj});lineChart('#tallosOperatorComparisonChart',matrix,employees.map(([id,name],i)=>({key:id,label:name,color:COLORS[i%COLORS.length]})),{yFormat:v=>formatMetric(metric,v),minValue:metric==='rating'?1:null,maxValue:metric==='rating'?10:null});}

  function renderDepartments(){const rows=state.dashboard?.departments||[];q('#tallosDepartmentsTable').innerHTML=rows.length?rows.map(r=>`<tr><td><button class="dadm-tallos-link-button" data-tallos-department="${escapeHtml(r.department)}">${escapeHtml(r.department_name)}</button></td><td>${formatInt(r.attendances)}</td><td>${formatInt(r.protocols)}</td><td>${formatInt(r.operators)}</td><td>${formatDuration(r.tme_avg_seconds)}</td><td>${formatDuration(r.tma_avg_seconds)}</td><td>${r.rating_avg==null?'—':`${formatNumber(r.rating_avg,2)} / 10`}</td><td>${formatInt(r.rating_count)}</td></tr>`).join(''):'<tr><td colspan="8">Nenhum departamento no recorte.</td></tr>';bars('#tallosDepartmentBars',rows.map(r=>({label:r.department_name,count:r.attendances})),{});bars('#tallosDepartmentRatingBars',rows.filter(r=>r.rating_avg!=null).sort((a,b)=>b.rating_avg-a.rating_avg).map(r=>({label:r.department_name,value:r.rating_avg,n:r.rating_count})),{value:'value',formatter:(v,r)=>`${formatNumber(v,2)}/10 · n=${formatInt(r.n)}`});}

  function renderExperience(){const d=state.dashboard,s=d?.summary||{};donut('#tallosRatingDonut',d?.ratings||[],{labelFn:r=>`Nota ${formatInt(r.rating)}`,center:s.rating_avg==null?'—':`${formatNumber(s.rating_avg,2)}/10`});donut('#tallosChannelDonut',d?.channels||[],{center:formatInt(s.attendances)});bars('#tallosTabulationBars',d?.tabulations||[],{});}

  function renderBridges(){const s=state.dashboard?.summary||{};const period=`${state.start} → ${state.end}`;q('#tallosDADM01Bridge').innerHTML=`<div class="dadm-tallos-bridge-card"><span>Protocolos</span><strong>${formatInt(s.protocols)}</strong><small>unidade institucional sugerida</small></div><div class="dadm-tallos-bridge-card"><span>Tempo Médio de Espera (TME)</span><strong>${formatDuration(s.tme_avg_seconds)}</strong><small>provisório até validação final</small></div><div class="dadm-tallos-bridge-card"><span>Tempo Médio de Atendimento (TMA)</span><strong>${formatDuration(s.tma_avg_seconds)}</strong><small>campo TALLOS validado</small></div><div class="dadm-tallos-bridge-card"><span>Em aberto</span><strong>${formatInt(s.open)}</strong><small>${formatPct(s.finalization_rate_pct)} finalizados</small></div><p class="dadm-tallos-bridge-note">Leitura TALLOS ${escapeHtml(period)}. O SLA institucional continua dependente das metas oficiais configuradas no DADM-01.</p>`;q('#tallosDADM02Bridge').innerHTML=`<div class="dadm-tallos-bridge-card"><span>Avaliação média</span><strong>${s.rating_avg==null?'—':`${formatNumber(s.rating_avg,2)} / 10`}</strong><small>escala TALLOS 1–10</small></div><div class="dadm-tallos-bridge-card"><span>Avaliações válidas</span><strong>${formatInt(s.rating_count)}</strong><small>${formatPct(s.rating_coverage_pct)} de cobertura</small></div><div class="dadm-tallos-bridge-card"><span>Sem avaliação</span><strong>${formatInt(s.rating_missing)}</strong><small>não entram na média</small></div><div class="dadm-tallos-bridge-card"><span>Faixa observada</span><strong>${s.rating_min==null?'—':`${formatInt(s.rating_min)}–${formatInt(s.rating_max)}`}</strong><small>menor e maior nota válida</small></div><p class="dadm-tallos-bridge-note">Leitura TALLOS ${escapeHtml(period)}. A escala operacional válida é 1–10; level=0 representa ausência na homologação atual. O sistema não converte automaticamente essa escala para a regra institucional do DADM-02 sem uma regra aprovada.</p>`;}

  function renderContext(){const f=[];if(state.filters.department)f.push(q('#tallosFilterDepartment').selectedOptions[0]?.textContent);if(state.filters.employee)f.push(q('#tallosFilterEmployee').selectedOptions[0]?.textContent);if(state.filters.channel)f.push(state.filters.channel);if(state.filters.status)f.push(state.filters.status);if(state.filters.tabulation)f.push(state.filters.tabulation);const comp={previous_period:'período anterior equivalente',previous_month:'janela deslocada 1 mês',previous_year:'mesmo período do ano anterior',none:'sem comparação'}[state.comparison]||state.comparison;q('#tallosFilterContext').textContent=`${periodLabel(state.startMonth)} → ${periodLabel(state.endMonth)} · ${comp}${f.length?` · ${f.join(' · ')}`:''}`;}
  function renderLastSync(){const sync=state.dashboard?.last_sync,top=q('#dadmTallosTopState');if(sync?.finished_at){const text=`TALLOS ${new Date(sync.finished_at).toLocaleString('pt-BR')}`;top.innerHTML=`<span class="status-dot"></span> ${escapeHtml(text)}`;}else top.innerHTML='<span class="status-dot"></span> TALLOS sem sincronização';}

  const FIELD_LABELS={employee:['Operador','employee.name'],tma:['Tempo Médio de Atendimento (TMA)','tma.value'],rating:['Avaliação 1–10','level'],channel:['Canal','channel'],tabulation:['Tabulação','to_tabulation'],messages:['Mensagens','total_send/receive_messages'],initiated_by:['Iniciado por','initiation_info.initiated_by'],tme:['Tempo Médio de Espera (TME)','tme.value'],department:['Departamento','to_department'],tmro:['TMRO','operational_metrics.tmro'],tmrc:['TMRC','operational_metrics.tmrc'],status:['Status','derivado']};
  const STATUS_LABELS={validated:['Validado','good'],validated_1_10:['Validado · 1–10','good'],provisional:['Provisório','attention'],experimental:['Experimental','info'],mapping_required:['Mapeamento','attention'],derived:['Derivado','info']};
  function renderFieldStatus(){const status=state.dashboard?.field_status||{};q('#tallosFieldStatusCards').innerHTML=Object.entries(status).map(([key,value])=>{const [name,field]=FIELD_LABELS[key]||[key,key],[label,klass]=STATUS_LABELS[value]||[value,'info'];return`<article class="metric-card"><div class="metric-top"><span class="metric-label">${escapeHtml(name)}</span></div><code>${escapeHtml(field)}</code><span class="status-chip ${klass}">${escapeHtml(label)}</span></article>`}).join('');}

  async function loadRuns(){try{const payload=await api('/api/dadm/tallos/sync-runs',{}, {limit:25}),rows=payload.items||[];renderRuns(rows);renderSyncProgress(rows[0]||null);return rows}catch(e){alert(e.message);return[]}}
  function renderRuns(rows){q('#tallosSyncRunsTable').innerHTML=rows.length?rows.map(r=>`<tr><td>${r.id}</td><td>${escapeHtml(r.start_date)} → ${escapeHtml(r.end_date)}</td><td><span class="status-chip ${r.status==='completed'?'good':r.status==='failed'?'critical':r.status==='running'?'attention':'info'}">${escapeHtml(r.status)}</span>${r.error_message?`<span class="dadm-tallos-table-note">${escapeHtml(r.error_message)}</span>`:''}</td><td>${formatInt(r.pages_processed)}</td><td>${formatInt(r.records_received)}</td><td>${formatInt(r.records_inserted)}</td><td>${formatInt(r.records_updated)}</td><td>${formatInt(r.records_unchanged)}</td><td>${formatInt(r.records_failed)}</td><td>${r.finished_at?new Date(r.finished_at).toLocaleString('pt-BR'):'—'}</td></tr>`).join(''):'<tr><td colspan="10">Nenhuma sincronização registrada.</td></tr>';}
  function updateStep(selector,status){const el=q(selector);if(!el)return;el.classList.remove('done','current');if(status)el.classList.add(status);}
  function renderConnectionStatus(){
    const s=state.connection||{},badge=q('#tallosTokenState'),summary=q('#tallosConnectionSummary'),local=q('#tallosLocalTokenControls'),managed=q('#tallosManagedTokenNotice'),tools=q('#tallosLocalHomologTools');
    if(badge){badge.textContent=s.configured?'Token configurado':'Token não configurado';badge.className=`status-chip ${s.configured?'good':'attention'}`;}
    if(summary){const source={local_env_file:'arquivo .env local',server_environment:'ambiente do servidor',not_configured:'não configurado'}[s.token_source]||'backend';summary.innerHTML=s.configured?`<strong>Token disponível no backend.</strong><br>Origem: <strong>${escapeHtml(source)}</strong> · ambiente: ${escapeHtml(s.environment||'—')} · endpoint de relatórios: <code>/v4/reports</code> · limite ${formatInt(s.page_limit||49)} por página.<br><span class="dadm-tallos-table-note">O valor do token nunca é devolvido ao navegador.</span>`:`<strong>A TALLOS ainda não está conectada.</strong><br>${s.token_management_enabled?'Cole o token abaixo, teste a conexão e salve para iniciar a homologação. Ele será salvo no <code>.env</code> local do backend.':'Configure <code>TALLOS_API_TOKEN</code> no ambiente do servidor.'}`;}
    local?.classList.toggle('hidden',!s.token_management_enabled);managed?.classList.toggle('hidden',Boolean(s.token_management_enabled));tools?.classList.toggle('hidden',!s.local_reset_enabled);
    const start=q('#tallosStartSync');if(start)start.disabled=!s.configured;
    renderOnboarding();
  }
  function renderOnboarding(){
    const box=q('#tallosOnboarding');if(!box)return;const s=state.connection||{};const relevant=state.currentSection==='dashboard'||isTallosSection(state.currentSection);
    if(!relevant){box.classList.add('hidden');return}
    const configured=Boolean(s.configured),hasData=Boolean(s.data_available);
    box.classList.remove('hidden');
    updateStep('#tallosStepConnection',configured?'done':'current');updateStep('#tallosStepSync',!configured?'':hasData?'done':'current');updateStep('#tallosStepValidate',hasData?'current':'');
    const title=q('#tallosOnboardingTitle'),text=q('#tallosOnboardingText'),actions=q('#tallosOnboardingActions'),eye=q('#tallosOnboardingEyebrow');
    if(!configured){eye.textContent='Homologação · etapa 1 de 3';title.textContent='Conecte a TALLOS para começar';text.textContent='A base local inicia limpa. Configure o token, valide a conexão e depois sincronize o primeiro período real.';actions.innerHTML='<button class="button primary" data-onboarding-action="connect">Configurar conexão</button>';}
    else if(!hasData){eye.textContent='Homologação · etapa 2 de 3';title.textContent='Conexão pronta. A base TALLOS está vazia';text.textContent='Escolha o intervalo real na área de Sincronização. Para a homologação, agosto/2026 continua sendo a referência conhecida.';actions.innerHTML='<button class="button primary" data-onboarding-action="sync">Ir para sincronização</button>';}
    else{box.classList.add('hidden');return;}
  }
  async function checkTallosStatus(){try{state.connection=await api('/api/dadm/tallos/status');renderConnectionStatus();return state.connection;}catch(e){state.connection=null;const badge=q('#tallosTokenState');if(badge){badge.textContent='Status indisponível';badge.className='status-chip critical';}return null;}}
  async function testTallosConnection(){const input=q('#tallosTokenInput'),token=input?.value.trim()||'';if(!token&&!state.connection?.configured){alert('Cole o token TALLOS antes de testar a conexão.','info');return}setLoading(true);try{const result=await api('/api/dadm/tallos/test-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token||null})});alert(result.mensagem||'Conexão validada.','success');}catch(e){alert(e.message,'error',0)}finally{setLoading(false)}}
  async function saveTallosToken(){const input=q('#tallosTokenInput'),token=input?.value.trim()||'';if(!token){alert('Cole o token TALLOS para salvar a configuração local.','info');return}setLoading(true);try{const result=await api('/api/dadm/tallos/config/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});input.value='';alert(result.mensagem||'Token salvo.','success');await checkTallosStatus();}catch(e){alert(e.message,'error',0)}finally{setLoading(false)}}
  async function removeLocalToken(){if(!confirm('Remover o token TALLOS salvo neste ambiente local?'))return;setLoading(true);try{const result=await api('/api/dadm/tallos/config/token',{method:'DELETE'});alert(result.mensagem||'Token removido.','success');await checkTallosStatus();}catch(e){alert(e.message,'error',0)}finally{setLoading(false)}}
  async function clearLocalData(){if(!confirm('Limpar todos os atendimentos, mapeamentos e históricos de sincronização TALLOS deste ambiente local? Os indicadores oficiais DADM-01/DADM-02 não serão alterados.'))return;setLoading(true);try{const result=await api('/api/dadm/tallos/local-data',{method:'DELETE'});alert(result.mensagem||'Base TALLOS local limpa.','success');state.dashboard=null;state.departmentMaps=[];await Promise.all([checkTallosStatus(),loadRuns(),loadDepartmentMaps()]);await refreshAll();}catch(e){alert(e.message,'error',0)}finally{setLoading(false)}}
  async function startSync(){const inicio=q('#tallosSyncStart').value,fim=q('#tallosSyncEnd').value;if(!state.connection?.configured){alert('Configure e valide o token TALLOS antes de sincronizar.','info');go('tallos-sync');return}if(!inicio||!fim){alert('Informe o início e o fim da sincronização.');return}setLoading(true);try{const result=await api('/api/dadm/tallos/sync',{method:'POST'},{inicio,fim});alert(result.mensagem||'Sincronização iniciada.','success');await loadRuns();pollSync();}catch(e){alert(e.message)}finally{setLoading(false)}}
  function renderSyncProgress(run){const box=q('#tallosSyncProgress'),badge=q('#tallosSyncState');if(!box||!badge)return;if(!run){box.classList.add('hidden');badge.textContent='Aguardando';badge.className='status-chip info';return}const active=['queued','running'].includes(run.status),done=run.status==='completed',failed=run.status==='failed';badge.textContent=active?'Sincronizando':done?'Concluído':failed?'Falhou':run.status;badge.className=`status-chip ${active?'attention':done?'good':failed?'critical':'info'}`;if(!active&&!failed){box.classList.add('hidden');return}box.classList.remove('hidden');const expected=Number(run.total_expected)||0,received=Number(run.records_received)||0,pct=expected?Math.max(0,Math.min(100,received/expected*100)):0;q('#tallosSyncProgressTitle').textContent=failed?`Sincronização #${run.id} falhou`:`Sincronização #${run.id} em andamento`;q('#tallosSyncProgressPct').textContent=expected?`${formatNumber(pct,0)}%`:'em andamento';q('#tallosSyncProgressBar').style.width=`${expected?pct:Math.min(92,8+(Number(run.pages_processed)||0)*3)}%`;q('#tallosSyncProgressMeta').textContent=`${formatInt(run.pages_processed)} páginas · ${formatInt(received)} recebidos · ${formatInt(run.records_inserted)} novos · ${formatInt(run.records_updated)} atualizados · ${formatInt(run.records_unchanged)} inalterados${run.error_message?` · ${run.error_message}`:''}`;}
  async function pollSync(){let attempts=0;const timer=setInterval(async()=>{attempts++;const runs=await loadRuns();const active=runs.some(r=>['queued','running'].includes(r.status));if(!active||attempts>=240){clearInterval(timer);await Promise.all([checkTallosStatus(),refreshAll()]);}},2500);}

  async function loadDepartmentMaps(){try{state.departmentMaps=(await api('/api/dadm/tallos/department-map')).items||[];renderDepartmentMaps()}catch(e){alert(e.message)}}
  function renderDepartmentMaps(){const canWrite=Boolean(state.access?.canEdit);q('#tallosDepartmentMapTable').innerHTML=state.departmentMaps.length?state.departmentMaps.map(r=>`<tr data-map-key="${escapeHtml(r.source_key)}"><td><code>${escapeHtml(r.source_key)}</code></td><td>${canWrite?`<input class="dadm-tallos-map-input" data-map-name value="${escapeHtml(r.display_name)}">`:escapeHtml(r.display_name)}</td><td>${canWrite?`<input class="dadm-tallos-map-check" data-map-active type="checkbox" ${r.active?'checked':''}>`:(r.active?'Sim':'Não')}</td><td>${canWrite?`<input class="dadm-tallos-map-input" data-map-notes value="${escapeHtml(r.notes||'')}">`:escapeHtml(r.notes||'—')}</td><td>${canWrite?'<button class="button secondary compact" data-map-save>Salvar</button>':''}</td></tr>`).join(''):'<tr><td colspan="5">Nenhum identificador de departamento coletado.</td></tr>';}
  async function saveDepartmentMap(row){const key=row.dataset.mapKey,name=q('[data-map-name]',row).value.trim(),active=q('[data-map-active]',row).checked,notes=q('[data-map-notes]',row).value.trim();if(!name){alert('Informe o nome exibido.');return}setLoading(true);try{await api(`/api/dadm/tallos/department-map/${encodeURIComponent(key)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({display_name:name,active,notes:notes||null})});alert('Departamento atualizado.','success');await Promise.all([loadDepartmentMaps(),refreshAll()]);}catch(e){alert(e.message)}finally{setLoading(false)}}

  function isTallosSection(section){return TALLOS_SECTIONS.has(section)}
  function onSection(section){state.currentSection=section;const filterSections=new Set(['tallos-overview','tallos-operators','tallos-departments','tallos-experience','dadm01','dadm02']);q('#dadmTallosFilterPanel')?.classList.toggle('hidden',!(filterSections.has(section)&&state.connection?.data_available));if(section==='tallos-sync'){loadRuns();checkTallosStatus()}if(section==='governanca')loadDepartmentMaps();if(section==='tallos-experience')loadRatingAudit();renderOnboarding();}
  function go(section){const button=q(`.nav-item[data-section="${section}"]`);if(button)button.click();}

  function bind(){
    qa('.nav-item[data-section]').forEach(button=>button.addEventListener('click',()=>onSection(button.dataset.section)));
    qa('[data-tallos-go]').forEach(button=>button.addEventListener('click',()=>go(button.dataset.tallosGo)));
    q('#tallosApplyFilters')?.addEventListener('click',()=>refreshAll().catch(e=>alert(e.message)));
    q('#tallosCompareOperators')?.addEventListener('click',compareOperators);
    q('#tallosOperatorCompareChoices')?.addEventListener('change',event=>{if(event.target.matches('input[type="checkbox"]')){const checked=qa('#tallosOperatorCompareChoices input:checked');if(checked.length>4){event.target.checked=false;alert('Compare no máximo quatro operadores.','info');}}});
    qa('[data-tallos-sort]').forEach(th=>th.addEventListener('click',()=>{const key=th.dataset.tallosSort;if(state.sort.key===key)state.sort.dir*=-1;else state.sort={key,dir:key==='employee_name'?1:-1};renderOperators()}));
    document.addEventListener('click',event=>{const employee=event.target.closest('[data-tallos-employee]');if(employee){state.filters.employee=employee.dataset.tallosEmployee;q('#tallosFilterEmployee').value=state.filters.employee;go('tallos-overview');refreshAll({filters:false});return}const dept=event.target.closest('[data-tallos-department]');if(dept){state.filters.department=dept.dataset.tallosDepartment;q('#tallosFilterDepartment').value=state.filters.department;go('tallos-overview');refreshAll({filters:false});return}const onboarding=event.target.closest('[data-onboarding-action]');if(onboarding){const action=onboarding.dataset.onboardingAction;if(action==='connect'||action==='sync')go('tallos-sync');else if(action==='overview')go('tallos-overview');return}const save=event.target.closest('[data-map-save]');if(save)saveDepartmentMap(save.closest('tr'));});
    q('#tallosStartSync')?.addEventListener('click',startSync);q('#tallosTestConnection')?.addEventListener('click',testTallosConnection);q('#tallosSaveToken')?.addEventListener('click',saveTallosToken);q('#tallosRemoveLocalToken')?.addEventListener('click',removeLocalToken);q('#tallosClearLocalData')?.addEventListener('click',clearLocalData);
  }

  async function initialize(){
    const now=todayLocal();setMonthRange(monthValue(now),monthValue(now));const week=new Date(now);week.setDate(now.getDate()-6);q('#tallosSyncStart').value=iso(week);q('#tallosSyncEnd').value=iso(now);bind();
    try{const identity=await window.DataUnivcIdentity.load();if(identity){state.user=identity;state.access=identity.directorateFor('DADM');}}
    catch{}
    const status=await checkTallosStatus();
    if(status?.available_end){const latest=String(status.available_end).slice(0,7);setMonthRange(latest,latest);}
    await Promise.all([loadRuns(),loadDepartmentMaps()]);
    await refreshAll();
    onSection(q('.nav-item.active[data-section]')?.dataset.section || 'dashboard');
  }

  window.DadmTallos={refresh:refreshAll,go};
  document.addEventListener('DOMContentLoaded',initialize);
})();
