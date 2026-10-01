(() => {
  'use strict';
  const $=selector=>document.querySelector(selector);
  const charts=()=>window.DataUnivcAcademicCharts;
  const state={directorate:'ALL',semester:'',courseId:'',disciplineId:'',filters:null,overview:null,loadingSerial:0};

  const esc=value=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const number=(value,decimals=1)=>value==null?'—':Number(value).toLocaleString('pt-BR',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
  const integer=value=>Number(value||0).toLocaleString('pt-BR');

  async function api(url){
    const response=await window.DataUnivcAuth.fetch(url,{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
    const data=await response.json().catch(()=>null);
    if(response.status===401){location.assign('/');throw new Error('Sua sessão expirou.');}
    if(!response.ok)throw new Error(data?.detail||`Erro HTTP ${response.status}`);
    return data;
  }

  function params(includeSemester=false){
    const p=new URLSearchParams({directorate:state.directorate||'ALL'});
    if(includeSemester&&state.semester)p.set('semester',state.semester);
    if(state.courseId)p.set('course_id',state.courseId);
    if(state.disciplineId)p.set('discipline_id',state.disciplineId);
    return p;
  }

  function option(value,label,selected=false){return `<option value="${esc(value)}" ${selected?'selected':''}>${esc(label)}</option>`;}

  function fillFilters(){
    const f=state.filters||{};
    const semesters=f.semesters||[];
    if(!state.semester||!semesters.includes(state.semester))state.semester=f.latest_semester||semesters[0]||'';
    $('#reitoriaAcademicSemester').innerHTML=semesters.length?semesters.map(v=>option(v,charts().semester(v),v===state.semester)).join(''):option('','Sem dados',true);
    $('#reitoriaAcademicDirectorate').innerHTML=option('ALL','Todas · UNIVC',state.directorate==='ALL')+(f.directorates||[]).map(item=>option(item.code,`${item.code} · ${item.name}`,item.code===state.directorate)).join('');
    const courses=f.courses||[];
    if(state.courseId&&!courses.some(item=>String(item.id)===String(state.courseId)))state.courseId='';
    $('#reitoriaAcademicCourse').innerHTML=option('','Todos os cursos',!state.courseId)+courses.map(item=>option(item.id,`${item.name} · ${item.directorate}`,String(item.id)===String(state.courseId))).join('');
    const disciplines=f.disciplines||[];
    if(state.disciplineId&&!disciplines.some(item=>String(item.id)===String(state.disciplineId)))state.disciplineId='';
    $('#reitoriaAcademicDiscipline').innerHTML=option('','Todas as disciplinas',!state.disciplineId)+disciplines.map(item=>option(item.id,`${item.name} · ${item.course_name}`,String(item.id)===String(state.disciplineId))).join('');
  }

  function setKpi(id,value,sub){const root=$(id);if(!root)return;root.querySelector('strong').textContent=value;root.querySelector('small').textContent=sub||'';}

  function renderKpis(){
    const k=state.overview?.kpis||{};
    const ni=k.nps_institution_students||{}, nc=k.nps_courses||{}, fav=k.faculty_favorability||{}, ap=k.approval||{}, avg=k.average_grade||{}, students=k.distinct_students||{}, nf=k.nps_faculty||{};
    setKpi('#reitoriaKpiNpsInstitution',ni.valor==null?'—':number(ni.valor,1),`${integer(ni.respondentes)} respondentes`);
    setKpi('#reitoriaKpiNpsCourses',nc.valor==null?'—':number(nc.valor,1),`${integer(nc.respondentes)} respostas de cursos`);
    setKpi('#reitoriaKpiFaculty',fav.value==null?'—':`${number(fav.value,1)}%`,`${integer(fav.participations)} participações`);
    setKpi('#reitoriaKpiFacultyParticipations',integer(fav.participations), 'respostas classificadas');
    setKpi('#reitoriaKpiApproval',ap.value==null?'—':`${number(ap.value,1)}%`,`${integer(ap.approved)} de ${integer(ap.finalized)} finalizados`);
    setKpi('#reitoriaKpiAverageGrade',avg.value==null?'—':number(avg.value,2),`${integer(avg.grade_count)} notas válidas`);
    setKpi('#reitoriaKpiStudents',integer(students.value),`${integer(students.result_records)} resultados disciplinares`);
    setKpi('#reitoriaKpiFacultyNps',nf.valor==null?'—':number(nf.valor,1),`${integer(nf.respondentes)} docentes · institucional`);
  }

  function renderScope(){
    const s=state.overview?.scope||{};
    const parts=[s.semester?charts().semester(s.semester):'Sem período',s.directorates?.length===2?'DTNH + DCS':(s.directorates||[]).join(' + '),s.course||'Todos os cursos',s.discipline||'Todas as disciplinas'];
    $('#reitoriaAcademicScope').innerHTML=`<strong>Recorte:</strong> ${parts.map(esc).join(' · ')} <span class="pill read">Somente leitura</span>`;
  }

  function renderNps(){
    const o=state.overview||{}, h=o.histories||{}, c=o.comparisons||{}, d=o.distributions||{};
    charts().line($('#reitoriaChartNpsInstitution'),h.nps_institution_students,{kind:'nps',decimals:1});
    charts().line($('#reitoriaChartNpsCoursesHistory'),h.nps_courses,{kind:'nps',decimals:1});
    charts().bar($('#reitoriaChartNpsCourses'),c.nps_courses,{kind:'nps',decimals:1});
    charts().line($('#reitoriaChartNpsFaculty'),h.nps_faculty,{kind:'nps',decimals:1});
    charts().distribution($('#reitoriaNpsInstitutionDistribution'),d.nps_institution_students);
    charts().distribution($('#reitoriaNpsCourseDistribution'),d.nps_courses);
    charts().distribution($('#reitoriaNpsFacultyDistribution'),d.nps_faculty);
  }

  function renderFaculty(){
    const o=state.overview||{};
    charts().line($('#reitoriaChartFacultyHistory'),o.histories?.faculty_favorability||[],{kind:'percentage',suffix:'%',decimals:1});
    charts().bar($('#reitoriaChartFacultyCourses'),o.comparisons?.faculty_courses||[],{kind:'percentage',suffix:'%',decimals:1});
  }

  function renderResults(){
    const o=state.overview||{};
    charts().line($('#reitoriaChartApprovalHistory'),o.histories?.approval||[],{kind:'percentage',suffix:'%',decimals:1});
    charts().line($('#reitoriaChartGradeHistory'),o.histories?.average_grade||[],{kind:'grade',decimals:2});
    charts().line($('#reitoriaChartStudentsHistory'),o.histories?.distinct_students||[],{kind:'count',decimals:0});
    charts().bar($('#reitoriaChartApprovalCourses'),o.comparisons?.approval_courses||[],{kind:'percentage',suffix:'%',decimals:1});
  }

  function renderNotes(){
    const notes=state.overview?.notes||{};
    $('#reitoriaAcademicMethodology').innerHTML=[notes.nps,notes.faculty,notes.results,notes.institution_nps_course_filter].filter(Boolean).map(text=>`<li>${esc(text)}</li>`).join('');
  }

  function render(){renderScope();renderKpis();renderNps();renderFaculty();renderResults();renderNotes();}

  function renderActivePage(target){
    if(!state.overview)return;
    if(target==='nps')renderNps();
    else if(target==='avaliacao-docente')renderFaculty();
    else if(target==='notas')renderResults();
  }

  function syncAcademicPage(target){
    const academic=['nps','avaliacao-docente','notas'].includes(target);
    if(!academic)return;
    $('#reitoriaAcademicDisciplineField')?.classList.toggle('hidden', target==='nps');
    window.setTimeout(()=>renderActivePage(target),0);
  }

  function setLoading(message='Carregando indicadores acadêmicos…'){$('#reitoriaAcademicStatus').textContent=message;$('#reitoriaAcademicStatus').classList.add('loading');}
  function setReady(){$('#reitoriaAcademicStatus').textContent='Dados consolidados diretamente das bases oficiais do Data UNIVC.';$('#reitoriaAcademicStatus').classList.remove('loading');}
  function setError(error){$('#reitoriaAcademicStatus').textContent=error.message||'Não foi possível carregar os indicadores.';$('#reitoriaAcademicStatus').classList.remove('loading');}

  async function loadFilters(){
    const serial=++state.loadingSerial;
    const data=await api(`/api/reitoria/academic/filters?${params(false)}`);
    if(serial!==state.loadingSerial)return false;
    state.filters=data;fillFilters();return true;
  }

  async function loadOverview(){
    const serial=state.loadingSerial;
    const data=await api(`/api/reitoria/academic/overview?${params(true)}`);
    if(serial!==state.loadingSerial)return false;
    state.overview=data;render();setReady();return true;
  }

  async function reload({filters=true}={}){
    setLoading();
    try{
      if(filters){const ok=await loadFilters();if(!ok)return;}
      await loadOverview();
    }catch(error){console.error(error);setError(error);}
  }

  function bind(){
    $('#reitoriaAcademicSemester')?.addEventListener('change',event=>{state.semester=event.target.value;reload({filters:false});});
    $('#reitoriaAcademicDirectorate')?.addEventListener('change',event=>{state.directorate=event.target.value||'ALL';state.courseId='';state.disciplineId='';reload({filters:true});});
    $('#reitoriaAcademicCourse')?.addEventListener('change',event=>{state.courseId=event.target.value;state.disciplineId='';reload({filters:true});});
    $('#reitoriaAcademicDiscipline')?.addEventListener('change',event=>{state.disciplineId=event.target.value;reload({filters:false});});
    $('#reitoriaAcademicRefresh')?.addEventListener('click',()=>reload({filters:true}));
  }

  async function start(){
    if(!$('#reitoriaAcademicToolbar'))return;
    const identity=await window.DataUnivcIdentity.load();
    if(!identity?.globalAccess)return;
    bind();
    window.addEventListener('reitoria:pagechange',event=>syncAcademicPage(event.detail?.target||'nps'));
    syncAcademicPage(String(location.hash||'#nps').replace(/^#/,''));
    await reload({filters:true});
  }

  start().catch(error=>{console.error(error);setError(error);});
})();
