(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const charts = () => window.DataUnivcAcademicCharts;
  const state = {directorate:'ALL', semester:'', courseId:'', disciplineId:'', filters:null, overview:null, loadingSerial:0, section:'nps-institution'};

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const number = (value, decimals=1) => value == null ? '—' : Number(value).toLocaleString('pt-BR',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
  const integer = value => Number(value || 0).toLocaleString('pt-BR');

  const sectionMeta = {
    'nps-institution': ['NPS da instituição','NPS da Instituição · Alunos','Acompanhe a percepção dos alunos sobre a instituição em DTNH e DCS.'],
    'nps-course': ['NPS dos cursos','NPS dos Cursos','Compare os cursos de DTNH e DCS e acompanhe a evolução consolidada do NPS discente.'],
    'nps-faculty': ['NPS da instituição · docentes','NPS da Instituição · Docentes','Acompanhe o NPS institucional dos docentes, preservando o caráter anônimo do indicador.'],
    'faculty': ['Avaliação docente','Avaliação do Professor pelo Aluno','Acompanhe favorabilidade, participação e comparação entre os cursos de DTNH e DCS.'],
    'results': ['Aprovação e notas','Aprovação, Notas e Alunos','Acompanhe aprovação, médias e alunos de todos os cursos de DTNH e DCS.'],
  };

  async function api(url) {
    const response = await window.DataUnivcAuth.fetch(url,{cache:'no-store',credentials:'same-origin',headers:{Accept:'application/json'}});
    const data = await response.json().catch(() => null);
    if (response.status === 401) { location.assign('/'); throw new Error('Sua sessão expirou.'); }
    if (!response.ok) throw new Error(data?.detail || `Erro HTTP ${response.status}`);
    return data;
  }

  function setAvatar(element, identity) {
    if (!element) return;
    const name = String(identity?.name || 'Reitoria').trim();
    const initials = name.split(/\s+/).filter(Boolean).slice(0,2).map(item => item[0]).join('').toUpperCase() || 'R';
    element.textContent = initials;
    const avatar = String(identity?.avatar_url || '').trim();
    if (avatar) {
      element.style.backgroundImage = `url("${avatar.replace(/"/g,'')}")`;
      element.style.backgroundSize = 'cover';
      element.style.backgroundPosition = 'center';
      element.textContent = '';
    }
  }

  function params(includeSemester=false) {
    const p = new URLSearchParams({directorate:state.directorate || 'ALL'});
    if (includeSemester && state.semester) p.set('semester',state.semester);
    if (state.courseId) p.set('course_id',state.courseId);
    if (state.disciplineId) p.set('discipline_id',state.disciplineId);
    return p;
  }

  function option(value,label,selected=false){ return `<option value="${esc(value)}" ${selected?'selected':''}>${esc(label)}</option>`; }

  function fillFilters() {
    const f = state.filters || {};
    const semesters = f.semesters || [];
    if (!state.semester || !semesters.includes(state.semester)) state.semester = f.latest_semester || semesters[0] || '';
    $('#reitoriaAcademicSemester').innerHTML = semesters.length ? semesters.map(v => option(v,charts().semester(v),v===state.semester)).join('') : option('','Sem dados',true);
    $('#reitoriaAcademicDirectorate').innerHTML = option('ALL','Todas · UNIVC',state.directorate==='ALL') + (f.directorates || []).map(item => option(item.code,`${item.code} · ${item.name}`,item.code===state.directorate)).join('');
    const courses = f.courses || [];
    if (state.courseId && !courses.some(item => String(item.id) === String(state.courseId))) state.courseId = '';
    $('#reitoriaAcademicCourse').innerHTML = option('','Todos os cursos',!state.courseId) + courses.map(item => option(item.id,`${item.name} · ${item.directorate}`,String(item.id)===String(state.courseId))).join('');
    window.DataUNIVC?.searchableSelect?.attach($('#reitoriaAcademicCourse'));
    const disciplines = f.disciplines || [];
    if (state.disciplineId && !disciplines.some(item => String(item.id) === String(state.disciplineId))) state.disciplineId = '';
    $('#reitoriaAcademicDiscipline').innerHTML = option('','Todas as disciplinas',!state.disciplineId) + disciplines.map(item => option(item.id,`${item.name} · ${item.course_name}`,String(item.id)===String(state.disciplineId))).join('');
    window.DataUNIVC?.searchableSelect?.attach($('#reitoriaAcademicDiscipline'));
  }

  function setKpi(id,value,sub) {
    const root = $(id); if (!root) return;
    const valueEl = root.querySelector('.metric-value') || root.querySelector('strong');
    const subEl = root.querySelector('.metric-sub') || root.querySelector('small');
    if (valueEl) valueEl.textContent = value;
    if (subEl) subEl.textContent = sub || '';
  }

  function renderKpis() {
    const k = state.overview?.kpis || {};
    const ni=k.nps_institution_students||{}, nc=k.nps_courses||{}, fav=k.faculty_favorability||{}, ap=k.approval||{}, avg=k.average_grade||{}, students=k.distinct_students||{}, nf=k.nps_faculty||{};
    setKpi('#reitoriaKpiNpsInstitution',ni.valor==null?'—':number(ni.valor,1),`${integer(ni.respondentes)} respondentes`);
    setKpi('#reitoriaKpiNpsCourses',nc.valor==null?'—':number(nc.valor,1),`${integer(nc.respondentes)} respostas de cursos`);
    setKpi('#reitoriaKpiFaculty',fav.value==null?'—':`${number(fav.value,1)}%`,`${integer(fav.participations)} participações`);
    setKpi('#reitoriaKpiFacultyParticipations',integer(fav.participations),'respostas classificadas');
    setKpi('#reitoriaKpiApproval',ap.value==null?'—':`${number(ap.value,1)}%`,`${integer(ap.approved)} de ${integer(ap.finalized)} finalizados`);
    setKpi('#reitoriaKpiAverageGrade',avg.value==null?'—':number(avg.value,2),`${integer(avg.grade_count)} notas válidas`);
    setKpi('#reitoriaKpiStudents',integer(students.value),`${integer(students.result_records)} resultados disciplinares`);
    setKpi('#reitoriaKpiFacultyNps',nf.valor==null?'—':number(nf.valor,1),`${integer(nf.respondentes)} docentes · institucional`);
  }

  function renderScope() {
    const s = state.overview?.scope || {};
    const parts = [s.semester?charts().semester(s.semester):'Sem período',s.directorates?.length===2?'DTNH + DCS':(s.directorates||[]).join(' + '),s.course||'Todos os cursos'];
    if (state.section === 'faculty' || state.section === 'results') parts.push(s.discipline || 'Todas as disciplinas');
    $('#reitoriaAcademicScope').innerHTML = `<strong>Recorte:</strong> ${parts.map(esc).join(' · ')}`;
  }

  function renderNpsInstitution(){ const o=state.overview||{}; const opts={kind:'nps',metric:'nps',unit:'pontos',decimals:1}; charts().line($('#reitoriaChartNpsInstitution'),o.histories?.nps_institution_students||[],opts); charts().bar($('#reitoriaChartNpsInstitutionCourses'),o.comparisons?.nps_institution_courses||[],opts); charts().distribution($('#reitoriaNpsInstitutionDistribution'),o.distributions?.nps_institution_students); }
  function renderNpsCourse(){ const o=state.overview||{}; const opts={kind:'nps',metric:'nps',unit:'pontos',decimals:1}; charts().line($('#reitoriaChartNpsCoursesHistory'),o.histories?.nps_courses||[],opts); charts().bar($('#reitoriaChartNpsCourses'),o.comparisons?.nps_courses||[],opts); charts().distribution($('#reitoriaNpsCourseDistribution'),o.distributions?.nps_courses); }
  function renderNpsFaculty(){ const o=state.overview||{}; charts().line($('#reitoriaChartNpsFaculty'),o.histories?.nps_faculty||[],{kind:'nps',metric:'nps',unit:'pontos',decimals:1}); charts().distribution($('#reitoriaNpsFacultyDistribution'),o.distributions?.nps_faculty); }
  function renderFaculty(){ const o=state.overview||{}; const opts={kind:'percentage',metric:'faculty',unit:'favorabilidade',suffix:'%',decimals:1}; charts().line($('#reitoriaChartFacultyHistory'),o.histories?.faculty_favorability||[],opts); charts().bar($('#reitoriaChartFacultyCourses'),o.comparisons?.faculty_courses||[],opts); }
  function renderResults(){ const o=state.overview||{}; charts().line($('#reitoriaChartApprovalHistory'),o.histories?.approval||[],{kind:'percentage',metric:'approval',unit:'aprovação',suffix:'%',decimals:1}); charts().line($('#reitoriaChartGradeHistory'),o.histories?.average_grade||[],{kind:'grade',metric:'grade',unit:'média',decimals:2}); charts().line($('#reitoriaChartStudentsHistory'),o.histories?.distinct_students||[],{kind:'count',metric:'students',unit:'alunos',decimals:0}); charts().bar($('#reitoriaChartApprovalCourses'),o.comparisons?.approval_courses||[],{kind:'percentage',metric:'approval',unit:'aprovação',suffix:'%',decimals:1}); }

  function renderMethodology(){ const notes=state.overview?.notes||{}; $('#reitoriaAcademicMethodology').innerHTML=[notes.nps,notes.faculty,notes.results,notes.institution_nps_course_filter].filter(Boolean).map(text=>`<li>${esc(text)}</li>`).join(''); }
  function renderActive(){ if(!state.overview)return; renderKpis(); renderScope(); if(state.section==='nps-institution')renderNpsInstitution(); else if(state.section==='nps-course')renderNpsCourse(); else if(state.section==='nps-faculty')renderNpsFaculty(); else if(state.section==='faculty')renderFaculty(); else if(state.section==='results')renderResults(); renderMethodology(); }

  function navigate(section) {
    if (!sectionMeta[section]) section = 'nps-institution';
    state.section = section;
    $$('[data-academic-section]').forEach(item => item.classList.toggle('active',item.dataset.academicSection===section));
    $$('[data-academic-page]').forEach(page => page.classList.toggle('active',page.dataset.academicPage===section));
    const meta = sectionMeta[section];
    $('#academicPageTitle').textContent = meta[0];
    $('#academicSectionHeading').textContent = meta[1];
    $('#academicSectionDescription').textContent = meta[2];
    const disciplineVisible = section === 'faculty' || section === 'results';
    $('#reitoriaAcademicDisciplineField').classList.toggle('hidden',!disciplineVisible);
    if (!disciplineVisible && state.disciplineId) {
      state.disciplineId='';
      $('#reitoriaAcademicDiscipline').value='';
      window.DataUNIVC?.searchableSelect?.sync($('#reitoriaAcademicDiscipline'));
    }
    history.replaceState(null,'',`/reitoria/academico?secao=${encodeURIComponent(section)}`);
    closeMobileSidebar();
    window.setTimeout(renderActive,0);
  }

  function setLoading(message='Carregando indicadores acadêmicos…'){ $('#reitoriaAcademicStatus').textContent=message; $('#reitoriaAcademicStatus').classList.add('loading'); }
  function setReady(){ $('#reitoriaAcademicStatus').textContent='Dados consolidados diretamente das bases oficiais do Data UNIVC.'; $('#reitoriaAcademicStatus').classList.remove('loading'); }
  function setError(error){ $('#reitoriaAcademicStatus').textContent=error.message||'Não foi possível carregar os indicadores.'; $('#reitoriaAcademicStatus').classList.remove('loading'); }

  async function loadFilters(){ const serial=++state.loadingSerial; const data=await api(`/api/reitoria/academic/filters?${params(false)}`); if(serial!==state.loadingSerial)return false; state.filters=data; fillFilters(); return true; }
  async function loadOverview(){ const serial=state.loadingSerial; const data=await api(`/api/reitoria/academic/overview?${params(true)}`); if(serial!==state.loadingSerial)return false; state.overview=data; renderActive(); setReady(); return true; }
  async function reload({filters=true}={}){ setLoading(); try{ if(filters){const ok=await loadFilters(); if(!ok)return;} await loadOverview(); } catch(error){ console.error(error); setError(error); } }

  function closeMobileSidebar(){ const sidebar=$('#academicSidebar'), backdrop=$('#academicSidebarBackdrop'); sidebar?.classList.remove('open'); backdrop?.classList.remove('open'); }
  function bindNavigation(){
    $$('[data-academic-section]').forEach(item => item.addEventListener('click',()=>navigate(item.dataset.academicSection)));
    $('#academicMenuToggle')?.addEventListener('click',()=>{ const sidebar=$('#academicSidebar'), backdrop=$('#academicSidebarBackdrop'); const open=!sidebar.classList.contains('open'); sidebar.classList.toggle('open',open); backdrop.classList.toggle('open',open); });
    $('#academicSidebarBackdrop')?.addEventListener('click',closeMobileSidebar);
  }

  function bindFilters(){
    $('#reitoriaAcademicSemester')?.addEventListener('change',event=>{state.semester=event.target.value;reload({filters:false});});
    $('#reitoriaAcademicDirectorate')?.addEventListener('change',event=>{state.directorate=event.target.value||'ALL';state.courseId='';state.disciplineId='';reload({filters:true});});
    $('#reitoriaAcademicCourse')?.addEventListener('change',event=>{state.courseId=event.target.value;state.disciplineId='';reload({filters:true});});
    $('#reitoriaAcademicDiscipline')?.addEventListener('change',event=>{state.disciplineId=event.target.value;reload({filters:false});});
    $('#reitoriaAcademicRefresh')?.addEventListener('click',()=>reload({filters:true}));
  }

  async function start(){
    const identity=await window.DataUnivcIdentity.load();
    if(!identity?.globalAccess){location.assign('/');return;}
    $('#academicUserName').textContent=identity.name||'Reitoria';
    $('#academicUserEmail').textContent=identity.email||'';
    setAvatar($('#academicUserAvatar'),identity);
    $('#academicLogout').addEventListener('click',async()=>{await window.DataUnivcAuth.logout(); location.assign('/');});
    bindNavigation(); bindFilters();
    const initial=new URLSearchParams(location.search).get('secao')||'nps-institution';
    navigate(initial);
    await reload({filters:true});
  }

  start().catch(error=>{console.error(error);setError(error);});
})();
