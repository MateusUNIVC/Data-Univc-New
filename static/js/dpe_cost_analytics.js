(function(){
  if(!state.costAnalytics) state.costAnalytics={periodId:null,window:12,courseKey:null,data:null,loaded:false,bound:false};

  const COLORS={revenue:'#0e8058',expense:'#4f6570',result:'#2f6fa3',margin:'#6f5b9b',previous:'#aab6b0',teaching:'#0e8058',direct:'#4477a6',shared:'#d6a93f',unclassified:'#8a8f94'};
  const SERIES_COLORS=[COLORS.revenue,COLORS.expense,COLORS.result,COLORS.margin,'#9b7420','#7c8694'];

  function data(){return state.costAnalytics.data||{cards:{},trend:[],courses:[],expenses_by_category:[],expenses_by_sector:[],category_comparison:[],course_history:[],waterfall:{},course_options:[],limitations:[]};}
  function periodId(){return state.costAnalytics.periodId||state.dpeV2?.periodId||state.costEngine?.selectedPeriodId||null;}
  function money(v,decimals=0){if(v===null||v===undefined||Number.isNaN(Number(v)))return '—';return Number(v).toLocaleString('pt-BR',{style:'currency',currency:'BRL',minimumFractionDigits:decimals,maximumFractionDigits:decimals});}
  function compact(v){if(v===null||v===undefined||Number.isNaN(Number(v)))return '—';return formatCompactMoney(Number(v));}
  function pct(v){if(v===null||v===undefined||Number.isNaN(Number(v)))return '—';return `${Number(v).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}%`;}
  function integer(v){if(v===null||v===undefined||Number.isNaN(Number(v)))return '—';return Number(v).toLocaleString('pt-BR',{maximumFractionDigits:0});}
  function periodLabel(value){const text=String(value||'');if(!/^\d{4}-\d{2}$/.test(text))return text;return `${text.slice(5)}/${text.slice(2,4)}`;}
  function short(value,max=22){const text=String(value||'');return text.length>max?`${text.slice(0,max-1)}…`:text;}
  function esc(value){return escapeHtml(value===null||value===undefined?'':String(value));}

  function emptyChart(root,message){if(!root)return;root.innerHTML=`<div class="dpe-analytics-empty"><strong>Sem dados suficientes</strong><span>${esc(message)}</span></div>`;}
  function chartSvg(root,width,height,body){if(!root)return;root.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Visualização analítica">${body}</svg>`;}
  function domain(values,{includeZero=true}={}){
    const nums=values.filter(v=>v!==null&&v!==undefined&&Number.isFinite(Number(v))).map(Number);
    if(!nums.length)return null;
    let min=Math.min(...nums),max=Math.max(...nums);
    if(includeZero){min=Math.min(0,min);max=Math.max(0,max);}
    if(min===max){const pad=Math.abs(min||1)*.1||1;min-=pad;max+=pad;}
    const pad=(max-min)*.08;return {min:min-pad,max:max+pad};
  }
  function yScale(v,d,top,bottom){return top+(d.max-Number(v))/(d.max-d.min)*(bottom-top);}
  function xScale(v,d,left,right){return left+(Number(v)-d.min)/(d.max-d.min)*(right-left);}
  function axisMoney(v){return Math.abs(Number(v))>=1000?compact(v):money(v,0);}

  function lineChart(root,rows,series,{formatter=axisMoney,includeZero=true}={}){
    if(!root)return;
    const activeSeries=series.filter(s=>rows.some(r=>r[s.key]!==null&&r[s.key]!==undefined));
    const values=[];activeSeries.forEach(s=>rows.forEach(r=>{if(r[s.key]!==null&&r[s.key]!==undefined)values.push(Number(r[s.key]));}));
    const d=domain(values,{includeZero});
    if(!rows.length||!activeSeries.length||!d){emptyChart(root,'Registre pelo menos dois meses para construir a evolução.');return;}
    const W=760,H=300,L=72,R=20,T=42,B=48,plotBottom=H-B,plotRight=W-R;
    let body='';
    for(let i=0;i<=4;i++){
      const value=d.max-(d.max-d.min)*i/4;const y=T+(plotBottom-T)*i/4;
      body+=`<line x1="${L}" x2="${plotRight}" y1="${y}" y2="${y}" class="analytics-grid"/><text x="${L-10}" y="${y+4}" text-anchor="end" class="analytics-axis-label">${esc(formatter(value))}</text>`;
    }
    const xPos=index=>rows.length===1?(L+plotRight)/2:L+(plotRight-L)*index/(rows.length-1);
    const step=Math.max(1,Math.ceil(rows.length/8));
    rows.forEach((row,i)=>{if(i%step===0||i===rows.length-1)body+=`<text x="${xPos(i)}" y="${H-16}" text-anchor="middle" class="analytics-axis-label">${esc(periodLabel(row.period))}</text>`;});
    activeSeries.forEach((s,si)=>{
      const points=rows.map((row,i)=>row[s.key]===null||row[s.key]===undefined?null:[xPos(i),yScale(row[s.key],d,T,plotBottom),row[s.key],row.period]);
      let path='';let penDown=false;
      points.forEach(point=>{if(!point){penDown=false;return;}path+=`${penDown?' L':'M'} ${point[0].toFixed(1)} ${point[1].toFixed(1)}`;penDown=true;});
      if(path)body+=`<path d="${path}" fill="none" stroke="${s.color||SERIES_COLORS[si%SERIES_COLORS.length]}" stroke-width="2.4" class="analytics-series"/>`;
      points.forEach(point=>{if(!point)return;body+=`<circle cx="${point[0]}" cy="${point[1]}" r="3.4" fill="${s.color||SERIES_COLORS[si%SERIES_COLORS.length]}"><title>${esc(`${s.label} · ${point[3]} · ${formatter(point[2])}`)}</title></circle>`;});
    });
    let lx=L;activeSeries.forEach((s,si)=>{body+=`<rect x="${lx}" y="12" width="12" height="3" rx="1.5" fill="${s.color||SERIES_COLORS[si%SERIES_COLORS.length]}"/><text x="${lx+17}" y="18" class="analytics-legend">${esc(s.label)}</text>`;lx+=Math.max(96,s.label.length*7+34);});
    chartSvg(root,W,H,body);
  }

  function horizontalBars(root,rows,field,{formatter=axisMoney,limit=12,color=COLORS.revenue,labelKey='key'}={}){
    if(!root)return;const filtered=rows.filter(r=>r[field]!==null&&r[field]!==undefined).slice(0,limit);
    if(!filtered.length){emptyChart(root,'Ainda não há valores completos para esta leitura.');return;}
    const vals=filtered.map(r=>Number(r[field]));const d=domain(vals,{includeZero:true});
    const W=760,rowH=34,T=18,B=26,L=190,R=78,H=Math.max(220,T+B+filtered.length*rowH),plotRight=W-R;
    const zero=xScale(0,d,L,plotRight);let body=`<line x1="${zero}" x2="${zero}" y1="${T-5}" y2="${H-B+5}" class="analytics-zero"/>`;
    filtered.forEach((row,i)=>{const y=T+i*rowH;const x=xScale(row[field],d,L,plotRight);const bx=Math.min(zero,x),bw=Math.max(1,Math.abs(x-zero));body+=`<text x="${L-10}" y="${y+16}" text-anchor="end" class="analytics-bar-label"><title>${esc(row[labelKey])}</title>${esc(short(row[labelKey],26))}</text><rect x="${bx}" y="${y+5}" width="${bw}" height="15" rx="4" fill="${color}" class="analytics-bar"><title>${esc(`${row[labelKey]} · ${formatter(row[field])}`)}</title></rect><text x="${row[field]>=0?Math.min(plotRight+6,x+7):Math.max(L-4,x-7)}" y="${y+17}" text-anchor="${row[field]>=0?'start':'end'}" class="analytics-value-label">${esc(formatter(row[field]))}</text>`;});
    chartSvg(root,W,H,body);
  }

  function groupedBars(root,rows,series,{formatter=axisMoney,limit=10,labelKey='key'}={}){
    const filtered=rows.slice(0,limit);const values=[];series.forEach(s=>filtered.forEach(r=>values.push(Number(r[s.key]||0))));const d=domain(values,{includeZero:true});
    if(!filtered.length||!d){emptyChart(root,'É necessário ter o mês atual e um mês anterior para comparar.');return;}
    const W=760,rowH=44,T=40,B=24,L=190,R=70,H=Math.max(230,T+B+filtered.length*rowH),plotRight=W-R,zero=xScale(0,d,L,plotRight);let body=`<line x1="${zero}" x2="${zero}" y1="${T-7}" y2="${H-B}" class="analytics-zero"/>`;
    let lx=L;series.forEach((s,i)=>{body+=`<rect x="${lx}" y="10" width="11" height="11" rx="2" fill="${s.color||SERIES_COLORS[i]}"/><text x="${lx+16}" y="20" class="analytics-legend">${esc(s.label)}</text>`;lx+=120;});
    filtered.forEach((row,i)=>{const y=T+i*rowH;body+=`<text x="${L-10}" y="${y+17}" text-anchor="end" class="analytics-bar-label">${esc(short(row[labelKey],25))}</text>`;series.forEach((s,si)=>{const value=Number(row[s.key]||0),x=xScale(value,d,L,plotRight),bx=Math.min(zero,x),bw=Math.max(1,Math.abs(x-zero)),yy=y+si*15;body+=`<rect x="${bx}" y="${yy+2}" width="${bw}" height="11" rx="3" fill="${s.color||SERIES_COLORS[si]}"><title>${esc(`${row[labelKey]} · ${s.label} · ${formatter(value)}`)}</title></rect>`;});});
    chartSvg(root,W,H,body);
  }

  function stackedCosts(root,rows){
    const filtered=rows.filter(r=>r.allocated_cost!==null&&r.allocated_cost!==undefined).sort((a,b)=>Number(b.allocated_cost)-Number(a.allocated_cost)).slice(0,10);
    if(!filtered.length){emptyChart(root,'Oficialize uma distribuição reconciliada para comparar a composição dos custos.');return;}
    const max=Math.max(...filtered.map(r=>Number(r.allocated_cost||0)),1);const W=760,rowH=38,T=42,B=24,L=190,R=78,H=T+B+filtered.length*rowH,plotW=W-L-R;let body='';
    const legend=[['Docentes',COLORS.teaching],['Diretos',COLORS.direct],['Compartilhados',COLORS.shared]];let lx=L;legend.forEach(([label,color])=>{body+=`<rect x="${lx}" y="10" width="11" height="11" rx="2" fill="${color}"/><text x="${lx+16}" y="20" class="analytics-legend">${label}</text>`;lx+=120;});
    filtered.forEach((row,i)=>{const y=T+i*rowH;body+=`<text x="${L-10}" y="${y+16}" text-anchor="end" class="analytics-bar-label">${esc(short(row.course,25))}</text>`;let x=L;[['teaching_cost',COLORS.teaching,'Docentes'],['direct_cost',COLORS.direct,'Diretos'],['shared_cost',COLORS.shared,'Compartilhados']].forEach(([key,color,label])=>{const value=Number(row[key]||0),w=value/max*plotW;if(w>0){body+=`<rect x="${x}" y="${y+4}" width="${Math.max(1,w)}" height="17" fill="${color}"><title>${esc(`${row.course} · ${label} · ${money(value)}`)}</title></rect>`;x+=w;}});body+=`<text x="${W-R+7}" y="${y+17}" class="analytics-value-label">${esc(compact(row.allocated_cost))}</text>`;});
    chartSvg(root,W,H,body);
  }

  function waterfall(root,wf){
    if(!wf||wf.total_revenue===null||wf.total_revenue===undefined||wf.operating_result===null||wf.operating_result===undefined){emptyChart(root,'Complete as receitas e despesas do mês para visualizar a formação do resultado.');return;}
    const steps=[{label:'Receita total',type:'total',value:Number(wf.total_revenue)}];
    if(Number(wf.teaching_cost||0))steps.push({label:'Docência',type:'delta',value:-Number(wf.teaching_cost||0)});
    if(Number(wf.direct_cost||0))steps.push({label:'Diretas',type:'delta',value:-Number(wf.direct_cost||0)});
    if(Number(wf.shared_cost||0))steps.push({label:'Compartilhadas',type:'delta',value:-Number(wf.shared_cost||0)});
    if(Number(wf.institutional_cost||0))steps.push({label:'Institucionais',type:'delta',value:-Number(wf.institutional_cost||0)});
    if(Number(wf.unclassified_cost||0))steps.push({label:'Outras',type:'delta',value:-Number(wf.unclassified_cost||0)});
    steps.push({label:'Resultado',type:'total',value:Number(wf.operating_result)});
    let running=0;const rendered=[];steps.forEach(step=>{if(step.type==='total'){const start=0,end=step.value;running=step.value;rendered.push({...step,start,end});}else{const start=running,end=running+step.value;running=end;rendered.push({...step,start,end});}});
    const values=rendered.flatMap(step=>[step.start,step.end]);const d=domain(values,{includeZero:true});const W=820,H=330,L=55,R=20,T=30,B=78,plotBottom=H-B,plotRight=W-R,n=rendered.length,slot=(plotRight-L)/n,barW=Math.min(54,slot*.58);let body='';
    for(let i=0;i<=4;i++){const value=d.max-(d.max-d.min)*i/4,y=yScale(value,d,T,plotBottom);body+=`<line x1="${L}" x2="${plotRight}" y1="${y}" y2="${y}" class="analytics-grid"/><text x="${L-8}" y="${y+4}" text-anchor="end" class="analytics-axis-label">${esc(axisMoney(value))}</text>`;}
    rendered.forEach((step,i)=>{const cx=L+slot*(i+.5),y1=yScale(step.start,d,T,plotBottom),y2=yScale(step.end,d,T,plotBottom),top=Math.min(y1,y2),h=Math.max(2,Math.abs(y2-y1));const color=step.type==='total'?COLORS.revenue:(step.value<0?'#b1645b':COLORS.result);body+=`<rect x="${cx-barW/2}" y="${top}" width="${barW}" height="${h}" rx="4" fill="${color}"><title>${esc(`${step.label} · ${money(step.type==='delta'?Math.abs(step.value):step.value)}`)}</title></rect><text x="${cx}" y="${H-48}" text-anchor="middle" class="analytics-waterfall-label">${esc(short(step.label,15))}</text><text x="${cx}" y="${Math.max(T+12,top-6)}" text-anchor="middle" class="analytics-value-label">${esc(compact(step.type==='delta'?Math.abs(step.value):step.value))}</text>`;if(i<rendered.length-1){const nextCx=L+slot*(i+1.5),connectorY=yScale(step.end,d,T,plotBottom);body+=`<line x1="${cx+barW/2}" x2="${nextCx-barW/2}" y1="${connectorY}" y2="${connectorY}" class="analytics-connector"/>`;}});
    chartSvg(root,W,H,body);
  }

  function comparisonLabel(card){const cmp=card?.comparison||{};const previous=data().previous_period?.period;if(cmp.percent===null||cmp.percent===undefined||!previous)return 'Sem mês anterior comparável';const arrow=cmp.direction==='UP'?'↑':cmp.direction==='DOWN'?'↓':'→';return `${arrow} ${Math.abs(Number(cmp.percent)).toLocaleString('pt-BR',{minimumFractionDigits:1,maximumFractionDigits:1})}% vs ${periodLabel(previous)}`;}
  function analyticsCard(label,key,formatter,help){const card=data().cards?.[key]||{};return `<article class="metric-card dpe-analytics-card"><div class="metric-top"><span class="metric-label">${esc(label)}</span></div><strong class="metric-value">${esc(formatter(card.value))}</strong><span class="metric-sub dpe-analytics-comparison">${esc(comparisonLabel(card))}</span><small>${esc(help)}</small></article>`;}

  function renderCards(){const root=$('#dpeAnalyticsCards');if(!root)return;root.innerHTML=[
    analyticsCard('Receita total','total_revenue',money,'Cursos + receitas institucionais'),
    analyticsCard('Receita dos cursos','course_revenue',money,'Receitas explicitamente atribuídas aos cursos'),
    analyticsCard('Receita institucional','institutional_revenue',money,'Receitas sem vínculo com curso'),
    analyticsCard('Despesas','expense_total',money,'Todas as despesas oficiais da competência'),
    analyticsCard('Resultado','economic_result',money,'Receita total menos despesas'),
    analyticsCard('Margem operacional','operating_margin_percent',pct,'Resultado ÷ receita total'),
    analyticsCard('Alunos ativos','active_students',integer,'Dado auxiliar informado por curso/contexto'),
  ].join('');}

  function renderLimitations(){const root=$('#dpeAnalyticsLimitations');if(!root)return;const rows=data().limitations||[];root.innerHTML=rows.length?rows.map(text=>`<div><span>i</span><p>${esc(text)}</p></div>`).join(''):'';}
  function renderTrend(){const rows=data().trend||[];$('#dpeAnalyticsTrendContext').textContent=`${rows.length} mês(es)`;lineChart($('#dpeAnalyticsTrendChart'),rows,[{key:'total_revenue',label:'Receita',color:COLORS.revenue},{key:'expense_total',label:'Despesas',color:COLORS.expense},{key:'economic_result',label:'Resultado',color:COLORS.result}],{formatter:axisMoney});lineChart($('#dpeAnalyticsMarginChart'),rows,[{key:'operating_margin_percent',label:'Margem operacional',color:COLORS.margin}],{formatter:pct,includeZero:true});}
  function renderExpenses(){horizontalBars($('#dpeAnalyticsCategoryChart'),data().expenses_by_category||[],'amount',{formatter:axisMoney,color:COLORS.expense,limit:12});horizontalBars($('#dpeAnalyticsSectorChart'),data().expenses_by_sector||[],'amount',{formatter:axisMoney,color:COLORS.revenue,limit:12});const current=data().selected_period?.period||'',previous=data().previous_period?.period||'';$('#dpeAnalyticsCategoryCompareContext').textContent=previous?`${periodLabel(current)} × ${periodLabel(previous)}`:'Sem mês anterior';groupedBars($('#dpeAnalyticsCategoryCompareChart'),data().category_comparison||[],[{key:'current',label:periodLabel(current)||'Atual',color:COLORS.revenue},{key:'previous',label:periodLabel(previous)||'Anterior',color:COLORS.previous}],{formatter:axisMoney,limit:12});}
  function renderCourses(){const rows=data().courses||[];const byRevenue=[...rows].sort((a,b)=>Number(b.revenue??-Infinity)-Number(a.revenue??-Infinity));const byResult=[...rows].sort((a,b)=>Number(b.economic_result??-Infinity)-Number(a.economic_result??-Infinity));const byMargin=[...rows].sort((a,b)=>Number(b.margin_percent??-Infinity)-Number(a.margin_percent??-Infinity));const byRevenueStudent=[...rows].sort((a,b)=>Number(b.revenue_per_active_student??-Infinity)-Number(a.revenue_per_active_student??-Infinity));horizontalBars($('#dpeAnalyticsCourseRevenueChart'),byRevenue,'revenue',{formatter:axisMoney,color:COLORS.revenue,limit:12,labelKey:'course'});horizontalBars($('#dpeAnalyticsCourseResultChart'),byResult,'economic_result',{formatter:axisMoney,color:COLORS.result,limit:12,labelKey:'course'});horizontalBars($('#dpeAnalyticsCourseMarginChart'),byMargin,'margin_percent',{formatter:pct,color:COLORS.margin,limit:12,labelKey:'course'});horizontalBars($('#dpeAnalyticsCourseTicketChart'),byRevenueStudent,'revenue_per_active_student',{formatter:v=>money(v,0),color:'#9b7420',limit:12,labelKey:'course'});groupedBars($('#dpeAnalyticsCostTicketChart'),rows.filter(r=>r.cost_per_active_student!==null&&r.revenue_per_active_student!==null).sort((a,b)=>Number(b.revenue_per_active_student)-Number(a.revenue_per_active_student)),[{key:'cost_per_active_student',label:'Custo/aluno',color:COLORS.expense},{key:'revenue_per_active_student',label:'Receita/aluno',color:COLORS.revenue}],{formatter:v=>money(v,0),limit:10,labelKey:'course'});stackedCosts($('#dpeAnalyticsCompositionChart'),rows);$('#dpeAnalyticsCourseContext').textContent=`${rows.length} curso(s)`;$('#dpeAnalyticsCourseTable').innerHTML=rows.length?rows.map(row=>`<tr><td><strong>${esc(row.course)}</strong><small class="table-subtitle">${row.offering_count} contexto(s)</small></td><td>${integer(row.active_students)}</td><td>${money(row.revenue)}</td><td>${money(row.allocated_cost)}</td><td>${money(row.economic_result)}</td><td>${pct(row.margin_percent)}</td><td>${money(row.revenue_per_active_student,2)}</td><td>${money(row.cost_per_active_student,2)}</td></tr>`).join(''):dpeEmptyRow(8,'Ainda não há cursos com dados','Complete receitas e distribuição de custos para liberar a análise econômica por curso.');}
  function renderWaterfallAndHistory(){waterfall($('#dpeAnalyticsWaterfallChart'),data().waterfall||{});$('#dpeAnalyticsWaterfallNote').textContent=data().waterfall?.note||'';const select=$('#dpeAnalyticsCourseSelect');const options=data().course_options||[];if(select){select.innerHTML=options.length?options.map(row=>option(row.key,row.label,row.key===data().selected_course_key)).join(''):'<option value="">Sem cursos</option>';if(data().selected_course_key)select.value=data().selected_course_key;}lineChart($('#dpeAnalyticsCourseHistoryChart'),data().course_history||[],[{key:'revenue',label:'Receita',color:COLORS.revenue},{key:'allocated_cost',label:'Custo',color:COLORS.expense},{key:'economic_result',label:'Resultado',color:COLORS.result}],{formatter:axisMoney});}
  function renderAll(){renderCards();renderLimitations();renderTrend();renderExpenses();renderCourses();renderWaterfallAndHistory();}

  async function refresh({periodId:pid=null,window=null,courseKey=null}={}){
    const targetPeriod=pid||periodId();if(window!==null)state.costAnalytics.window=Number(window)||12;if(courseKey!==null)state.costAnalytics.courseKey=courseKey||null;
    const params={window_months:state.costAnalytics.window};if(targetPeriod)params.period_id=targetPeriod;if(state.costAnalytics.courseKey)params.course_key=state.costAnalytics.courseKey;
    const payload=await api('/api/dpe/cost-engine/analytics',{},params);state.costAnalytics.data=payload;state.costAnalytics.periodId=payload.selected_period?.id||targetPeriod||null;state.costAnalytics.courseKey=payload.selected_course_key||null;state.costAnalytics.loaded=true;renderAll();return payload;
  }

  function bind(){if(state.costAnalytics.bound)return;state.costAnalytics.bound=true;$('#dpeAnalyticsWindow')?.addEventListener('change',async event=>{setLoading(true);try{await refresh({window:Number(event.target.value)||12});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});$('#dpeAnalyticsRefresh')?.addEventListener('click',async()=>{setLoading(true);try{await refresh({periodId:periodId()});showAlert('Análises atualizadas.','success',2200);}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});$('#dpeAnalyticsCourseSelect')?.addEventListener('change',async event=>{setLoading(true);try{await refresh({courseKey:event.target.value||null});}catch(error){showAlert(error.message,'error',0);}finally{setLoading(false);}});}

  window.refreshDPECostAnalytics=refresh;
  window.initializeDPECostAnalytics=async function(){bind();await refresh({periodId:state.dpeV2?.periodId||state.costEngine?.selectedPeriodId||null,window:Number($('#dpeAnalyticsWindow')?.value||12)});};
})();
