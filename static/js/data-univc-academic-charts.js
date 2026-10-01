(() => {
  'use strict';

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const num = (value, decimals = 1) => Number(value ?? 0).toLocaleString('pt-BR', {minimumFractionDigits:decimals, maximumFractionDigits:decimals});
  const semester = value => {
    const text = String(value || '');
    const match = text.match(/^(\d{4})-SEM([12])$/);
    return match ? `${match[1]}/${match[2]}` : text || '—';
  };

  const PRESETS = Object.freeze({
    percentage: {min:0,max:100,ticks:[0,25,50,75,100]},
    nps: {min:-100,max:100,ticks:[-100,-50,0,50,100]},
    grade: {min:0,max:10,ticks:[0,2,4,6,8,10]},
  });

  function niceStep(value) {
    const raw = Math.max(1, Number(value) || 1);
    const power = 10 ** Math.floor(Math.log10(raw));
    const scaled = raw / power;
    return (scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10) * power;
  }

  function scale(values, kind = 'auto') {
    if (PRESETS[kind]) return {kind, ...PRESETS[kind], fixed:true};
    const finite = (values || []).map(Number).filter(Number.isFinite);
    if (kind === 'count') {
      const observed = Math.max(0, ...finite);
      const step = niceStep(Math.max(1, observed) / 4);
      const max = Math.max(step * 4, Math.ceil(observed / step) * step);
      const ticks=[]; for(let v=0;v<=max+step/2;v+=step) ticks.push(v);
      return {kind,min:0,max,ticks,fixed:true};
    }
    let min = Math.min(...finite), max = Math.max(...finite);
    if (!Number.isFinite(min) || !Number.isFinite(max)) { min=0; max=1; }
    if (min === max) { min-=1; max+=1; }
    const pad = (max-min)*.18 || 1; min-=pad; max+=pad;
    return {kind:'auto',min,max,ticks:Array.from({length:5},(_,i)=>min+(max-min)*(i/4)),fixed:false};
  }

  function clamp(value, bounds) {
    const number = Number(value);
    if (!Number.isFinite(number)) return bounds.min;
    return bounds.fixed ? Math.max(bounds.min, Math.min(bounds.max, number)) : number;
  }

  function tickText(value, opts) {
    const decimals = opts.kind === 'count' ? 0 : (opts.decimals ?? 1);
    return `${opts.prefix || ''}${num(value,decimals)}${opts.suffix || ''}`;
  }

  function empty(container, message='Sem dados para exibir neste recorte.') {
    if (container) container.innerHTML = `<div class="reitoria-chart-empty">${esc(message)}</div>`;
  }

  function line(container, data, opts = {}) {
    if (!container) return;
    const rows=(data||[]).filter(row=>row && row.periodo && row.valor!==null && row.valor!==undefined);
    if(!rows.length){empty(container);return;}
    const width=Math.max(container.clientWidth||560,360), height=250;
    const margin={top:18,right:18,bottom:46,left:54};
    const bounds=scale(rows.map(row=>row.valor),opts.kind||'auto');
    const range=bounds.max-bounds.min||1;
    const plotW=width-margin.left-margin.right, plotH=height-margin.top-margin.bottom;
    const x=i=>margin.left+(rows.length===1?plotW/2:(i*plotW/(rows.length-1)));
    const y=value=>margin.top+(bounds.max-clamp(value,bounds))*plotH/range;
    const grid=bounds.ticks.map(v=>`<line x1="${margin.left}" x2="${width-margin.right}" y1="${y(v)}" y2="${y(v)}" stroke="#e6ece9"/><text x="${margin.left-8}" y="${y(v)+4}" text-anchor="end" font-size="9" fill="#718078">${esc(tickText(v,{...opts,kind:bounds.kind}))}</text>`).join('');
    const path=rows.map((row,i)=>`${i?'L':'M'} ${x(i)} ${y(row.valor)}`).join(' ');
    const points=rows.map((row,i)=>`<circle cx="${x(i)}" cy="${y(row.valor)}" r="4.5" fill="#0e8058" stroke="#fff" stroke-width="2"><title>${esc(semester(row.periodo))}: ${esc(tickText(row.valor,opts))}</title></circle>`).join('');
    const every=rows.length>12?2:1;
    const labels=rows.map((row,i)=>(i%every===0||i===rows.length-1)?`<text x="${x(i)}" y="${height-15}" text-anchor="middle" font-size="9" fill="#718078">${esc(semester(row.periodo))}</text>`:'').join('');
    container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" width="100%" height="250" role="img">${grid}<path d="${path}" fill="none" stroke="#0e8058" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${points}${labels}</svg>`;
  }

  function wrap(value,max=34){
    const words=String(value||'—').split(/\s+/); const lines=[]; let current='';
    for(const word of words){const candidate=current?`${current} ${word}`:word;if(candidate.length<=max)current=candidate;else{if(current)lines.push(current);current=word;}}
    if(current)lines.push(current); return lines;
  }

  function bar(container,data,opts={}){
    if(!container)return;
    const rows=(data||[]).filter(row=>row && row.valor!==null && row.valor!==undefined);
    if(!rows.length){empty(container);return;}
    const sorted=[...rows].sort((a,b)=>Number(b.valor)-Number(a.valor));
    const width=Math.max(container.clientWidth||720,520);
    const bounds=scale(sorted.map(row=>row.valor),opts.kind||'auto');
    const left=Math.min(320,Math.max(200,width*.38)), right=72, top=bounds.fixed?28:10;
    const lines=sorted.map(row=>wrap(`${row.curso || '—'}${row.diretoria?` · ${row.diretoria}`:''}`,Math.max(24,Math.floor((left-30)/5.7))));
    const rowHeights=lines.map(items=>Math.max(38,items.length*12+16)); let cursor=top; const tops=[]; rowHeights.forEach(h=>{tops.push(cursor);cursor+=h;});
    const height=cursor+12, plotRight=width-right, range=bounds.max-bounds.min||1;
    const x=value=>left+(clamp(value,bounds)-bounds.min)*(plotRight-left)/range; const zero=x(0);
    const guides=bounds.ticks.map(v=>`<line x1="${x(v)}" x2="${x(v)}" y1="${top-8}" y2="${height}" stroke="#edf2ef"/><text x="${x(v)}" y="12" text-anchor="middle" font-size="9" fill="#718078">${esc(tickText(v,{...opts,kind:bounds.kind}))}</text>`).join('');
    const svgRows=sorted.map((row,i)=>{
      const h=rowHeights[i], rowTop=tops[i], barY=rowTop+(h-22)/2, end=x(row.valor), bx=Math.min(zero,end), bw=Math.max(2,Math.abs(end-zero));
      const firstY=rowTop+h/2-((lines[i].length-1)*12)/2+3;
      const tspans=lines[i].map((lineText,j)=>`<tspan x="${left-10}" ${j?`dy="12"`:''}>${esc(lineText)}</tspan>`).join('');
      return `<text x="${left-10}" y="${firstY}" text-anchor="end" font-size="10" fill="#2b3d35"><title>${esc(row.curso||'—')}</title>${tspans}</text><rect x="${bx}" y="${barY}" width="${bw}" height="22" rx="5" fill="#0e8058"><title>${esc(row.curso||'—')}: ${esc(tickText(row.valor,opts))}</title></rect><text x="${width-5}" y="${barY+15}" text-anchor="end" font-size="10" font-weight="700" fill="#5b6d64">${esc(tickText(row.valor,opts))}</text>`;
    }).join('');
    container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" width="100%" height="${Math.max(280,height)}" role="img">${guides}<line x1="${zero}" x2="${zero}" y1="${top-8}" y2="${height}" stroke="#bfcfc7"/>${svgRows}</svg>`;
  }

  function distribution(container,payload){
    if(!container)return;
    if(!payload?.available||!Array.isArray(payload.items)||!payload.items.length){empty(container,'Distribuição 0–10 indisponível para este semestre.');return;}
    const items=Array.from({length:11},(_,score)=>{const found=payload.items.find(item=>Number(item.score)===score)||{};return{score,count:Number(found.count||0),percentage:Number(found.percentage||0)}});
    const max=Math.max(1,...items.map(item=>item.count));
    const columns=items.map(item=>{const tone=item.score>=9?'promoter':item.score>=7?'neutral':'detractor';const height=item.count?Math.max(5,item.count/max*100):0;return `<div class="reitoria-nps-score ${tone}" title="Nota ${item.score}: ${item.count} resposta(s) · ${num(item.percentage,1)}%"><span>${item.count}</span><div class="reitoria-nps-track"><i style="height:${height}%"></i></div><strong>${item.score}</strong><small>${num(item.percentage,1)}%</small></div>`}).join('');
    container.innerHTML=`<div class="reitoria-nps-summary"><div><span>Respondentes</span><strong>${Number(payload.total||0).toLocaleString('pt-BR')}</strong></div><div><span>Média 0–10</span><strong>${payload.mean==null?'—':`${num(payload.mean,2)} / 10`}</strong></div><div><span>NPS</span><strong>${payload.nps==null?'—':num(payload.nps,1)}</strong></div></div><div class="reitoria-nps-distribution">${columns}</div><div class="reitoria-nps-groups"><span>0–6 · Detratores</span><span>7–8 · Neutros</span><span>9–10 · Promotores</span></div>`;
  }

  window.DataUnivcAcademicCharts=Object.freeze({scale,line,bar,distribution,semester,formatNumber:num});
})();
