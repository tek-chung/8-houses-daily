/* Guided discovery uses explicit preferences, never guessed swipe preferences.
   Saved IDs and answers stay in localStorage. No requests or enquiry tracking. */
(() => {
  'use strict';
  const data = document.getElementById('discovery-data');
  if (!data) return;
  const roles = JSON.parse(data.textContent);
  const geography=JSON.parse(document.getElementById('discovery-locations').textContent);
  const zoneLabels=new Map(geography.zones.map(zone=>[zone.id,zone.label]));
  const byId = new Map(roles.map(r => [r.id, r]));
  const templates = new Map([...document.querySelectorAll('template[data-role]')]
    .map(t => [t.dataset.role, t]));
  const stage = document.getElementById('discovery-stage');
  const status = document.getElementById('journey-status');
  const progress = document.getElementById('journey-progress');
  const storageKey = '8houses-volunteer-discovery-v1';
  let saved = [], preferences = null, persistent = true;
  try {
    const state = JSON.parse(localStorage.getItem(storageKey) || '{}');
    saved = Array.isArray(state.saved) ? [...new Set(state.saved.filter(id => byId.has(id)))] : [];
    const p = state.preferences;
    if (p && ['any','once','regular'].includes(p.commitment) && Array.isArray(p.when)) {
      if(Array.isArray(p.zones)) preferences={when:p.when,commitment:p.commitment,
        zones:[...new Set(p.zones.filter(id=>zoneLabels.has(id)))],remote:p.remote===true};
      else if(typeof p.area==='string') {
        const zone=geography.borough_zones[p.area];
        if(['any','remote'].includes(p.area)||zone) preferences={when:p.when,commitment:p.commitment,
          zones:zone?[zone]:[],remote:p.area==='remote'};
      }
    }
  } catch (_) { persistent = false; }
  let phase = preferences ? 'ranked' : 'examples', exampleIndex = 0;
  let initialising = true, includeOther = false;
  let cancelTear = null;
  const reducedMotion = () => !window.matchMedia || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const history = [];
  const skipped = new Set();
  let prompted = saved.length >= 3;
  const examples = [];
  for (const activity of ['cooking_serving','befriending','hosting']) {
    const role = roles.filter(r => r.activity === activity && !saved.includes(r.id))
      .sort((a,b) => (b.status === 'open') - (a.status === 'open') || b.confidence-a.confidence)[0];
    if (role) examples.push(role.id);
  }

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, fn, className) {
    const node = el('button', text, className); node.type = 'button';
    node.addEventListener('click', fn); return node;
  }
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify({saved, preferences})); }
    catch (_) { persistent = false; }
    document.getElementById('saved-count').textContent = saved.length;
    document.getElementById('undo-action').disabled = !history.length;
  }
  function message(text) {
    status.textContent = text + (!persistent ? ' Saved for this visit only; browser storage is unavailable.' : '');
  }
  async function share(title, text, path, container) {
    const url = new URL(path, location.origin).href;
    const preview = ['localhost','127.0.0.1','[::1]'].includes(location.hostname);
    if (navigator.share && !preview) {
      try { await navigator.share({title,text,url}); return; }
      catch (error) { if(error.name === 'AbortError')return; }
    }
    try {
      await navigator.clipboard.writeText(url);
      message(preview ? 'Preview link copied. It only works on this device.' : 'Link copied. Ready to paste into a message or post.');
    } catch (_) {
      container.querySelector('.share-link')?.remove();
      const box=el('label','Copy this link','share-link');
      const input=el('input');input.type='url';input.value=url;input.readOnly=true;
      box.append(input);container.append(box);input.focus();input.select();
      message(preview ? 'This preview link only works on this device.' : 'Copy the link to share this role.');
    }
  }
  function socialImage(role) {
    const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1350;
    const ctx=canvas.getContext('2d');
    if(!ctx){message('Image unavailable. You can still share the role link.');return;}
    ctx.fillStyle='#f2ede1';ctx.fillRect(0,0,1080,1350);
    ctx.fillStyle='#201c16';ctx.strokeStyle='#201c16';ctx.lineWidth=3;
    ctx.strokeRect(44,44,992,1262);
    function line(y){ctx.beginPath();ctx.moveTo(86,y);ctx.lineTo(994,y);ctx.stroke();}
    function text(value,y,size=32,font='Georgia',colour='#201c16'){
      ctx.font=`${size}px ${font}`;ctx.fillStyle=colour;ctx.fillText(value,86,y);
    }
    function wrapped(value,y,size,maxLines,font='Georgia'){
      ctx.font=`${size}px ${font}`;ctx.fillStyle='#201c16';
      const words=value.split(/\s+/);let row='',rows=[];
      for(const word of words){const candidate=row?row+' '+word:word;
        if(ctx.measureText(candidate).width>900 && row){rows.push(row);row=word;}else row=candidate;}
      if(row)rows.push(row);
      rows.slice(0,maxLines).forEach((row,i)=>{
        if(i===maxLines-1 && rows.length>maxLines){
          while(ctx.measureText(row+'…').width>900)row=row.slice(0,-1);row+='…';
        }
        ctx.fillText(row,86,y+i*size*1.22);
      });return y+Math.min(rows.length,maxLines)*size*1.22;
    }
    text('THE 8 HOUSES DAILY',124,48,'Georgia');line(159);
    text('A SMALL STEP. A REAL DIFFERENCE.',220,25,'Arial','#8c392b');
    let y=wrapped(role.title,328,64,3);y+=42;
    y=wrapped(role.charity,y,30,2,'Arial')+48;
    y=wrapped(role.summary,y,34,3)+35;line(y);y+=54;
    const frequency={one_off:'One-off',weekly:'Weekly',fortnightly:'Fortnightly',monthly:'Monthly',long_term:'Ongoing',flexible:'Flexible frequency',unknown:'Confirm commitment'}[role.commitment];
    y=wrapped(frequency+(role.min_term_months?' · at least '+role.min_term_months+' months':''),y,29,2,'Arial')+14;
    const area=role.location_type==='own_home'?'Your own home':role.location_type==='remote'?'Remote':role.areas.join(', ')||'Confirm location';
    wrapped(area,y,29,2,'Arial');
    line(1120);text('Interested? Enquire with the charity.',1180,32);
    const preview=['localhost','127.0.0.1','[::1]'].includes(location.hostname);
    text(preview?'LOCAL PREVIEW · PUBLIC LINK AVAILABLE AFTER LAUNCH':location.host+' · role link in caption',1233,preview?21:24,'Arial');
    text('Confirm current availability and requirements.',1270,22,'Arial','#8c392b');
    const overlay=el('div','','social-overlay'),dialog=el('section','','social-dialog');
    dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label','Share image');
    const previous=document.activeElement;
    const background=[...document.body.children].map(node=>[node,node.hasAttribute('inert')]);
    background.forEach(([node])=>node.setAttribute('inert',''));
    function close(){overlay.remove();background.forEach(([node,wasInert])=>{if(!wasInert)node.removeAttribute('inert');});previous?.focus();}
    const heading=el('h2','Ready to share');heading.tabIndex=-1;
    dialog.append(heading,el('p','Save this image for an Instagram or LinkedIn post. Add the role link to your caption or story.'));
    const picture=el('img');picture.src=canvas.toDataURL('image/png');picture.alt=role.title+' at '+role.charity;
    picture.width=1080;picture.height=1350;dialog.append(picture);
    const actions=el('div','','social-actions');
    const download=el('a','Download image','primary');download.href=picture.src;download.download=role.id+'.png';
    actions.append(download,button('Close',close));dialog.append(actions);overlay.append(dialog);document.body.append(overlay);
    const controls=[...dialog.querySelectorAll('a,button')];heading.focus({preventScroll:true});
    overlay.addEventListener('keydown',event=>{
      if(event.key==='Escape')close();
      if(event.key==='Tab'){event.preventDefault();const index=controls.indexOf(document.activeElement);
        controls[index<0?(event.shiftKey?controls.length-1:0):(index+(event.shiftKey?-1:1)+controls.length)%controls.length].focus();}
    });
  }
  function panel(title, intro) {
    cancelTear?.();
    stage.classList.remove('scrapbook');
    stage.replaceChildren();
    const box = el('section', '', 'discovery-panel');
    const heading = el('h2', title); heading.tabIndex = -1;
    box.append(heading);
    if (intro) box.append(el('p', intro));
    stage.append(box); if (!initialising) heading.focus();
    return box;
  }
  function fit(role) {
    let score = 0, conflicts = 0; const reasons = [], cautions = [];
    if (role.status === 'open') score += 8;
    else if (role.status === 'seasonal_closed') cautions.push('Seasonal role: check when the next intake opens.');
    else if (role.status === 'oversubscribed') cautions.push('Oversubscribed: ask about the waiting list.');
    else cautions.push('Current recruitment is not confirmed.');
    if (!preferences) return {score, reasons, cautions, conflicts};
    const p = preferences;
    if (p.commitment !== 'any') {
      const ongoing = role.min_term_months > 0 || role.location_type === 'own_home';
      const matches = p.commitment === 'once' ? role.commitment === 'one_off' && !ongoing
        : ['weekly','fortnightly','monthly','long_term'].includes(role.commitment);
      if (matches) { score += 30; reasons.push(p.commitment === 'once' ? 'Listed as a one-off role.' : 'Listed as a regular commitment.'); }
      else if (p.commitment === 'once' && ongoing) {
        conflicts++; cautions.push('This involves an ongoing commitment, rather than a one-off visit.');
      }
      else if (role.commitment === 'flexible') cautions.push(p.commitment === 'once'
        ? 'Flexible frequency does not confirm that a single visit is possible.'
        : 'Ask whether a regular slot is available.');
      else if (role.commitment === 'unknown') cautions.push('How often you would volunteer is not stated.');
      else {conflicts++; cautions.push('The commitment differs from your preference.');}
    }
    if (p.when.length) {
      if (role.when.some(w => p.when.includes(w))) {score += 25; reasons.push('The stated timing overlaps your availability.');}
      else if (role.when.includes('flexible')) cautions.push('Timing is flexible; ask whether your available hours work.');
      else if (!role.when.length) cautions.push('Timing needs checking with the charity.');
      else {conflicts++; cautions.push('The stated timing differs from your availability.');}
    }
    if (p.zones.length || p.remote) {
      const overlaps=(role.zones||[]).filter(zone=>p.zones.includes(zone));
      if(p.remote && ['remote','hybrid'].includes(role.location_type)) {
        score+=25;reasons.push('Includes remote volunteering.');
        if(role.location_type==='hybrid')cautions.push('Some attendance may be in person.');
      } else if(role.location_type==='remote' && p.zones.length){score+=15;reasons.push('Remote: no journey to a venue.');}
      else if(role.location_type==='own_home' && p.zones.length){cautions.push('Hosting takes place at home; check whether your address is covered.');}
      else if(overlaps.length){
        const coverage=role.location_basis==='charity_coverage';score+=coverage?12:25;
        reasons.push((coverage?'The charity covers ':'The listed postcode is in ')+overlaps.map(id=>zoneLabels.get(id)).join(' or ')+'.');
        if(coverage)cautions.push('Coverage does not confirm a venue in your chosen area.');
      } else if(p.remote && !p.zones.length){conflicts++;cautions.push('This role is not listed as remote.');}
      else if(!(role.zones||[]).length && !['remote','own_home'].includes(role.location_type)) cautions.push('The location needs checking with the charity.');
      else {conflicts++;cautions.push('The listed location is outside your chosen areas.');}
    }
    return {score, reasons, cautions, conflicts};
  }
  function ranked() {
    return roles.filter(r => !saved.includes(r.id) && !skipped.has(r.id))
      .filter(r => includeOther || !fit(r).conflicts)
      .sort((a,b) => fit(a).conflicts-fit(b).conflicts || fit(b).score-fit(a).score
        || b.confidence-a.confidence || a.title.localeCompare(b.title));
  }
  function reasons(role) {
    const f = fit(role), box = el('details','','fit-reasons');
    if (!preferences) return el('div');
    box.append(el('summary','Why this role?'));
    if(f.conflicts)box.open=true;
    box.append(el('p', f.reasons.length ? 'Why this may fit: '+f.reasons.join(' ') : 'Explore this role and check the particulars below.'));
    if (f.cautions.length) box.append(el('p','Before enquiring: '+f.cautions.join(' ')));
    return box;
  }
  function notice(role) {
    const wrap = el('div','','discovery-notice');
    wrap.append(templates.get(role.id).content.cloneNode(true));
    const tools=el('div','','role-share');
    tools.append(button('Share role',()=>share(role.title+' — '+role.charity,'Could this volunteering role suit someone you know?','/role/'+role.id+'/',wrap)),
      button('Save image',()=>socialImage(role)));
    wrap.append(tools);
    return wrap;
  }
  function shortlistPrompt() {
    phase = 'prompt'; progress.textContent = 'Three possibilities, one next step';
    const box = panel('Three roles worth a closer look.', 'Compare your shortlist, or keep exploring.');
    const actions = el('div','','discovery-actions');
    actions.append(button('Compare saved roles',showShortlist,'primary'), button('Keep exploring',()=>{phase = preferences ? 'ranked' : 'examples'; render();}));
    box.append(actions);
  }
  function choose(role, save) {
    history.push({saved:[...saved],skipped:[...skipped],phase,exampleIndex,prompted,preferences});
    if (save && !saved.includes(role.id)) saved.push(role.id);
    else if (!save) skipped.add(role.id);
    if (phase === 'examples') exampleIndex++;
    persist(); message(save ? 'Saved '+role.title+'. Saving does not contact the charity.' : 'Skipped. You can still find this role in the directory.');
    if (saved.length >= 3 && !prompted) {prompted=true;shortlistPrompt();return;}
    render();
  }
  function undo() {
    const previous=history.pop(); if(!previous)return;
    saved=previous.saved;skipped.clear();previous.skipped.forEach(id=>skipped.add(id));
    phase=previous.phase;exampleIndex=previous.exampleIndex;prompted=previous.prompted;
    preferences=previous.preferences;persist();message('Last choice undone.');render();
  }
  function render() {
    while (phase === 'examples' && saved.includes(examples[exampleIndex])) exampleIndex++;
    if (phase === 'examples' && exampleIndex >= examples.length) {questions();return;}
    const role = phase === 'examples' ? byId.get(examples[exampleIndex]) : ranked()[0];
    progress.textContent = phase === 'examples' ? `Example ${exampleIndex+1} of ${examples.length}` : 'Suggestions based on your answers';
    if (!role) {
      const box=panel('You’ve seen the roles that may fit.', 'Change your answers or explore beyond them.');
      box.append(button('Change my answers',questions,'primary'),button('Compare saved roles',showShortlist),button('Show skipped roles again',()=>{skipped.clear();render();}));
      if(!includeOther) box.append(button('Explore roles outside my preferences',()=>{includeOther=true;render();}));
      return;
    }
    const box = panel(phase === 'examples' ? 'Could this fit?' : 'A role to consider',
      phase === 'examples' ? 'Skip or save. Three quick questions come next.'
        : includeOther ? 'Outside your preferences. Check the differences below.' : 'Chosen using your answers.');
    box.append(reasons(role));
    const paperSlot=el('div','','paper-slot');
    const card=notice(role);paperSlot.append(card);box.append(paperSlot);
    const cue=el('span','','paper-choice');cue.setAttribute('aria-hidden','true');card.append(cue);
    const actions=el('div','','discovery-actions role-actions');
    let tearing=false, start=null;
    function resetPaper() {
      card.classList.remove('paper-dragging','paper-returning');
      card.style.removeProperty('--drag-x');card.style.removeProperty('--drag-angle');
      card.removeAttribute('data-choice');cue.textContent='';
    }
    function tear(save) {
      if(tearing)return;
      if(reducedMotion()){choose(role,save);return;}
      tearing=true;start=null;
      card.classList.remove('paper-dragging','paper-returning');
      card.dataset.choice=save?'save':'skip';cue.textContent=save?'Keep this!':'Next…';
      card.classList.add(save?'paper-tear-right':'paper-tear-left');
      actions.querySelectorAll('button').forEach(node=>{node.disabled=true;});
      let timer;
      function cleanup(){clearTimeout(timer);card.removeEventListener('animationend',finished);cancelTear=null;}
      function finished(event){
        if(event && event.target!==card)return;
        cleanup();if(card.isConnected)choose(role,save);
      }
      cancelTear=cleanup;
      card.addEventListener('animationend',finished);
      timer=setTimeout(finished,560);
    }
    actions.append(button('Skip',()=>tear(false)),button('Save role',()=>tear(true),'primary'));
    box.append(actions,el('p','Swipe left to skip · right to save','discovery-hint'));
    box.append(button(phase === 'examples' ? 'Answer the questions now' : 'Change my answers',questions,'discovery-text-button'));
    card.addEventListener('pointerdown',e=>{
      if(tearing || !e.isPrimary || (e.pointerType==='mouse' && e.button!==0) || e.target.closest('a,button,summary,input,select,label'))return;
      resetPaper();start={x:e.clientX,y:e.clientY,id:e.pointerId};
      card.setPointerCapture?.(e.pointerId);
    });
    card.addEventListener('pointermove',e=>{
      if(!start || e.pointerId!==start.id)return;
      const dx=e.clientX-start.x,dy=e.clientY-start.y;
      if(Math.abs(dy)>Math.abs(dx)*1.5 && Math.abs(dy)>12){start=null;resetPaper();return;}
      if(reducedMotion() || Math.abs(dx)<8)return;
      card.classList.add('paper-dragging');
      card.style.setProperty('--drag-x',Math.max(-180,Math.min(180,dx))+'px');
      card.style.setProperty('--drag-angle',Math.max(-9,Math.min(9,dx/20))+'deg');
      card.dataset.choice=dx>0?'save':'skip';cue.textContent=dx>0?'Keep this!':'Next…';
    });
    card.addEventListener('pointerup',e=>{
      if(!start || e.pointerId!==start.id)return;
      const dx=e.clientX-start.x,dy=e.clientY-start.y;start=null;
      if(card.hasPointerCapture?.(e.pointerId))card.releasePointerCapture(e.pointerId);
      if(Math.abs(dx)>90 && Math.abs(dx)>Math.abs(dy)*1.5)tear(dx>0);
      else {resetPaper();card.classList.add('paper-returning');}
    });
    card.addEventListener('pointercancel',()=>{start=null;resetPaper();});
    card.addEventListener('lostpointercapture',()=>{if(start){start=null;resetPaper();}});
  }
  function questions() {
    phase='questions';progress.textContent='Three questions about your life';
    const box=panel('What works for you?', '“Not sure” is fine. You can change these later.');
    const form=el('form');
    function group(legend) {const field=el('fieldset','','discovery-question');field.append(el('legend',legend));form.append(field);return field;}
    function choice(field,name,value,text,type,checked) {
      const label=el('label','','discovery-choice'),input=el('input');
      Object.assign(input,{type,name,value,checked});label.append(input,el('span',text));field.append(label);
    }
    const times=[['weekday_daytime','Weekdays during the day'],['weekday_evening','Weekday evenings'],['weekend_daytime','Weekend days'],['weekend_evening','Weekend evenings'],['overnight','Overnight']];
    const first=group('1. When could you help?');
    times.forEach(([v,t])=>choice(first,'when',v,t,'checkbox',!!preferences?.when.includes(v)));
    first.append(el('p','Leave these blank if you are not sure yet.','discovery-hint'));
    const second=group('2. How often would you like to help?');
    [['once','Try it once'],['regular','Volunteer regularly'],['any','Either / not sure yet']].forEach(([v,t])=>choice(second,'commitment',v,t,'radio',(preferences?.commitment||'any')===v));
    const third=group('3. Which areas can you comfortably reach?');
    third.append(el('p','Choose several if useful. Leave blank for anywhere / not sure.','discovery-hint'));
    const mapInput=el('div','','discovery-area-map');
    mapInput.append(document.getElementById('discovery-zone-map').content.cloneNode(true));third.append(mapInput);
    geography.zones.forEach(zone=>{
      const input=el('input');Object.assign(input,{type:'checkbox',name:'zones',value:zone.id,
        checked:!!preferences?.zones.includes(zone.id)});input.hidden=true;third.append(input);
    });
    window.mountZoneMap(mapInput,{zones:geography.zones,selected:preferences?.zones||[],onChange:ids=>{
      third.querySelectorAll('[name=zones]').forEach(input=>{input.checked=ids.includes(input.value);});
    }});
    choice(third,'remote','yes','Remote volunteering','checkbox',!!preferences?.remote);
    const travel=el('a','Check a journey with TfL →');travel.href='https://tfl.gov.uk/plan-a-journey/';travel.target='_blank';travel.rel='noopener';
    third.append(el('p','Choose places that work with your usual train, Tube or bus route.','discovery-hint'),travel);
    let step=0;
    const fields=[first,second,third];
    const actions=el('div','','discovery-actions');
    const back=button('Back',()=>{step--;showQuestion();});
    const submit=el('button','Next question','primary');submit.type='submit';actions.append(back,submit);form.append(actions);
    function showQuestion(){
      fields.forEach((field,i)=>{field.hidden=i!==step;});
      progress.textContent=`Question ${step+1} of 3`;
      back.hidden=step===0;submit.textContent=step===2?'Show my suggestions':'Next question';
    }
    showQuestion();
    form.addEventListener('submit',e=>{
      e.preventDefault();if(step<2){step++;showQuestion();return;}const answers=new FormData(form);
      preferences={when:answers.getAll('when'),commitment:answers.get('commitment'),zones:answers.getAll('zones'),remote:answers.has('remote')};
      includeOther=false;persist();phase='ranked';message('Suggestions reordered using your answers. You can change them at any time.');render();
    });box.append(form);
    box.append(button('Reset answers',()=>{
      preferences=null;exampleIndex=0;skipped.clear();history.length=0;includeOther=false;phase='examples';
      persist();message('Answers reset. Your saved roles are kept.');render();
    },'discovery-text-button'));
  }
  function showShortlist() {
    cancelTear?.();
    phase='shortlist';progress.textContent='Your saved roles';
    stage.replaceChildren();stage.classList.add('scrapbook');
    stage.append(el('p','Clippings for a little good','scrapbook-kicker'));
    const heading=el('h2','Your volunteering scrapbook.');heading.tabIndex=-1;stage.append(heading);heading.focus({preventScroll:true});
    stage.append(el('p',saved.length?'A few possibilities, kept together. Compare the essentials and enquire directly with the charity.':'Your first clipping goes here. Save a role that catches your eye.','scrapbook-intro'));
    stage.append(el('p',saved.length?'Something to come back to ♡':'Find a role → save it here','crayon-note scrapbook-note'));
    const grid=el('div','','shortlist-grid');
    saved.forEach((id,index)=>{
      const role=byId.get(id),item=el('section','','shortlist-item');
      item.append(el('p','Clipping '+String(index+1).padStart(2,'0'),'scrapbook-number'),reasons(role),notice(role));
      item.append(el('p',['Worth a closer look','Check the little details','A possible next step'][index%3],'crayon-note clipping-note'));
      item.append(button('Remove '+role.title,()=>{saved=saved.filter(x=>x!==id);history.length=0;persist();message('Removed from your shortlist.');showShortlist();}));grid.append(item);
    });stage.append(grid);
    const actions=el('div','','discovery-actions');actions.append(button('Keep exploring',()=>{phase=preferences?'ranked':'examples';render();},'primary'),button('Change my answers',questions));stage.append(actions);
    if(saved.length)stage.append(button('Clear saved roles',()=>{saved=[];prompted=false;history.length=0;persist();message('Saved roles cleared from this browser.');showShortlist();},'discovery-text-button'));
  }
  document.getElementById('show-shortlist').addEventListener('click',showShortlist);
  document.getElementById('undo-action').addEventListener('click',undo);
  persist();message('');render();initialising=false;
})();
