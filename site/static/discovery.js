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
  function loadImage(src){
    return new Promise(done=>{if(!src)return done(null);const img=new Image();
      img.onload=()=>done(img);img.onerror=()=>done(null);img.src=src;});
  }
  async function socialImage(role) {
    const [brandLogo,charityLogo]=await Promise.all([loadImage('/assets/brand/symbol-reverse.png'),loadImage(role.logo)]);
    const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1350;
    const ctx=canvas.getContext('2d');
    if(!ctx){message('Image unavailable. You can still share the role link.');return;}
    const SERIF="'Fraunces',Georgia,serif",SANS="'Archivo',Arial,sans-serif";
    ctx.fillStyle='#FBF7F0';ctx.fillRect(0,0,1080,1350);
    ctx.fillStyle='#30282A';ctx.strokeStyle='#30282A';ctx.lineWidth=3;
    ctx.strokeRect(44,44,992,1262);
    function line(y){ctx.beginPath();ctx.moveTo(86,y);ctx.lineTo(994,y);ctx.stroke();}
    function text(value,y,size=32,font=SERIF,colour='#30282A'){
      ctx.font=`${font===SERIF?'600 ':''}${size}px ${font}`;ctx.fillStyle=colour;ctx.fillText(value,86,y);
    }
    function wrapped(value,y,size,maxLines,font=SERIF,x=86,width=900){
      ctx.font=`${size}px ${font}`;ctx.fillStyle='#30282A';
      const words=String(value).split(/\s+/);let row='',rows=[];
      for(const word of words){const candidate=row?row+' '+word:word;
        if(ctx.measureText(candidate).width>width && row){rows.push(row);row=word;}else row=candidate;}
      if(row)rows.push(row);
      rows.slice(0,maxLines).forEach((row,i)=>{
        if(i===maxLines-1 && rows.length>maxLines){
          while(ctx.measureText(row+'…').width>width)row=row.slice(0,-1);row+='…';
        }
        ctx.fillText(row,x,y+i*size*1.22);
      });return y+Math.min(rows.length,maxLines)*size*1.22;
    }
    // Same particulars as the role card on the page: where, when, commitment,
    // screening, requirements and recruitment status.
    function fact(label,value,x,y,width,maxLines=2){
      ctx.font=`600 19px ${SANS}`;ctx.fillStyle='#723A3D';ctx.fillText(label.toUpperCase(),x,y);
      return wrapped(value,y+34,26,maxLines,SERIF,x,width);
    }
    text('The 8 Houses Daily',124,48,SERIF);line(159);
    text('LONDON VOLUNTEERING · A SMALL STEP. A REAL DIFFERENCE.',214,22,SANS,'#723A3D');
    let y=wrapped(role.title,292,52,3);y+=16;
    y=wrapped(role.charity,y+14,28,1,SANS)+10;
    ctx.font=`600 20px ${SANS}`;ctx.fillStyle='#723A3D';ctx.fillText((role.state||'').toUpperCase(),86,y+14);y+=50;
    y=wrapped(role.summary,y,28,4)+22;line(y);y+=44;
    const colWidth=430,rightX=86+colWidth+48;
    const rowOne=Math.max(fact('Where',role.where||'Confirm location',86,y,colWidth),
      fact('When',role.timing||'Times not stated',rightX,y,colWidth));
    y=rowOne+24;
    const rowTwo=Math.max(fact('Commitment',role.frequency||'Confirm commitment',86,y,colWidth),
      fact('Screening',role.screening||'Not stated',rightX,y,colWidth));
    y=rowTwo+24;
    let yEnd=y-24;
    if(role.requirements&&role.requirements.length)yEnd=fact('Before you save',role.requirements.join(' · '),86,y,900);
    // The charity's own mark fills the space between the particulars and the footer.
    // Logos are drawn exactly as supplied: no filter, tint or blending. Marks that are
    // white on transparent (which vanish on white) go on a Charcoal plate instead.
    (function placedBy(){
      const top=yEnd+44,bottom=1090,room=bottom-top;
      if(room<150)return;
      const plateH=Math.min(300,room),plateY=top+(room-plateH)/2,plateX=86,plateW=908;
      let light=false;
      if(charityLogo){try{
        const probe=document.createElement('canvas');probe.width=probe.height=48;
        const pc=probe.getContext('2d');pc.drawImage(charityLogo,0,0,48,48);
        const px=pc.getImageData(0,0,48,48).data;let seen=0,clear=0,sum=0;
        for(let k=0;k<px.length;k+=4){const a=px[k+3];if(a<250)clear++;if(a>20){seen+=a;sum+=a*(0.3*px[k]+0.59*px[k+1]+0.11*px[k+2]);}}
        light=clear>px.length/4*0.1&&seen>0&&sum/seen>215;
      }catch(_){}
      if(role.logo_dark)light=true;}
      ctx.fillStyle=light?'#30282A':'#FFFFFF';ctx.fillRect(plateX,plateY,plateW,plateH);
      if(!light){ctx.strokeStyle='#D8C9BF';ctx.lineWidth=2;ctx.strokeRect(plateX,plateY,plateW,plateH);}
      if(charityLogo){
        const boxW=plateW-96,boxH=plateH-80,nw=charityLogo.naturalWidth||150,nh=charityLogo.naturalHeight||150;
        const scale=Math.min(boxW/nw,boxH/nh,4),w=nw*scale,h=nh*scale;
        ctx.save();
        ctx.drawImage(charityLogo,plateX+(plateW-w)/2,plateY+(plateH-h)/2,w,h);ctx.restore();
      }else{
        ctx.font=`600 44px ${SERIF}`;ctx.fillStyle='#30282A';ctx.textAlign='center';
        ctx.fillText(role.charity,plateX+plateW/2,plateY+plateH/2+30,plateW-64);ctx.textAlign='left';
      }
    })();
    line(1120);text('Interested? Enquire with the charity.',1180,32);
    // Supplied circular reverse 8 Houses mark, bottom right: square artwork clipped to a circle.
    if(brandLogo){
      const d=90;ctx.save();ctx.beginPath();ctx.arc(994-d/2,1133+d/2,d/2,0,Math.PI*2);ctx.clip();
      ctx.drawImage(brandLogo,994-d,1133,d,d);ctx.restore();
    }
    const preview=['localhost','127.0.0.1','[::1]'].includes(location.hostname);
    text(preview?'LOCAL PREVIEW · PUBLIC LINK AVAILABLE AFTER LAUNCH':location.host+' · role link in caption',1233,preview?21:24,SANS);
    text('Confirm current availability and requirements.',1270,22,SANS,'#723A3D');
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
        const coverage=['charity_coverage','role_areas'].includes(role.location_basis);score+=coverage?12:25;
        reasons.push((coverage?'The charity covers ':'The listed postcode is in ')+overlaps.map(id=>zoneLabels.get(id)).join(' or ')+'.');
        if(coverage)cautions.push('Coverage does not confirm a venue in your chosen area.');
      } else if(p.remote && !p.zones.length){conflicts++;cautions.push('This role is not listed as remote.');}
      else if(role.location_basis==='london_wide' && !['remote','own_home'].includes(role.location_type)) reasons.push('The charity says this runs across London.');
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
    box.append(el('summary','Suggestions based on your answers'));
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
    progress.hidden=true;
    if (!role) {
      const box=panel('You’ve seen the roles that may fit.', 'Change your answers or explore beyond them.');
      box.append(button('Change my answers',questions,'primary'),button('Compare saved roles',showShortlist),button('Show skipped roles again',()=>{skipped.clear();render();}));
      if(!includeOther) box.append(button('Explore roles outside my preferences',()=>{includeOther=true;render();}));
      return;
    }
    const box = panel(phase === 'examples' ? 'Could this fit?' : 'A role to consider');
    box.classList.add('role-panel');box.querySelector('h2').classList.add('sr');
    const directions=el('div','','swipe-directions');
    directions.append(el('span','← Swipe to skip'),el('span','Swipe to save →'));box.append(directions);
    if(includeOther)box.append(el('p','Outside your preferences. Check the differences below.','discovery-hint'));
    const paperSlot=el('div','','paper-slot');
    const card=notice(role);paperSlot.append(card);box.append(paperSlot);
    // Browser link/image dragging must not take over the paper gesture.
    card.querySelectorAll('a,img').forEach(node=>{node.draggable=false;});
    card.addEventListener('dragstart',event=>event.preventDefault());
    const cue=el('span','','paper-choice');cue.setAttribute('aria-hidden','true');card.append(cue);
    const actions=el('div','','discovery-actions role-actions');
    let tearing=false, start=null, suppressClick=false;
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
    // Order under the card: Skip/Save, the suggestions, Change my answers, then Browse all roles.
    box.append(actions,reasons(role));
    const navigation=el('div','','matching-navigation');
    const answers=el('div','','matching-answers');
    answers.append(button(phase === 'examples' ? 'Answer the questions now' : 'Change my answers',questions));
    const browse=el('a','Browse all roles →');browse.href='/all/';
    navigation.append(answers,browse);box.append(navigation);
    card.addEventListener('pointerdown',e=>{
      if(tearing || !e.isPrimary || (e.pointerType==='mouse' && e.button!==0) || e.target.closest('input,select,textarea'))return;
      suppressClick=false;
      resetPaper();start={x:e.clientX,y:e.clientY,id:e.pointerId,horizontal:false};
    });
    card.addEventListener('pointermove',e=>{
      if(!start || e.pointerId!==start.id)return;
      const dx=e.clientX-start.x,dy=e.clientY-start.y;
      if(!start.horizontal){
        if(Math.abs(dy)>Math.abs(dx)*1.5 && Math.abs(dy)>12){start=null;resetPaper();return;}
        if(Math.abs(dx)<8 || Math.abs(dx)<=Math.abs(dy)*1.5)return;
        start.horizontal=true;
      }
      suppressClick=true;
      if(!card.hasPointerCapture?.(e.pointerId))card.setPointerCapture?.(e.pointerId);
      card.classList.add('paper-dragging');
      card.style.setProperty('--drag-x',dx+'px');
      card.style.setProperty('--drag-angle',(reducedMotion()?0:Math.max(-9,Math.min(9,dx/20)))+'deg');
      card.dataset.choice=dx>0?'save':'skip';cue.textContent=dx>0?'Keep this!':'Next…';
    });
    card.addEventListener('pointerup',e=>{
      if(!start || e.pointerId!==start.id)return;
      const dx=e.clientX-start.x,dy=e.clientY-start.y;start=null;
      suppressClick=Math.abs(dx)>8 && Math.abs(dx)>Math.abs(dy)*1.5;
      if(card.hasPointerCapture?.(e.pointerId))card.releasePointerCapture(e.pointerId);
      if(Math.abs(dx)>90 && Math.abs(dx)>Math.abs(dy)*1.5)tear(dx>0);
      else {resetPaper();card.classList.add('paper-returning');}
    });
    card.addEventListener('click',event=>{
      if(suppressClick && event.detail!==0){event.preventDefault();event.stopImmediatePropagation();suppressClick=false;}
    },true);
    card.addEventListener('pointercancel',()=>{start=null;suppressClick=false;resetPaper();});
    card.addEventListener('lostpointercapture',event=>{
      // Touch browsers initially capture the child under the finger. Its capture
      // loss bubbles here when we transfer capture to the whole card.
      if(event.target===card && start){start=null;resetPaper();}
    });
  }
  function questions() {
    phase='questions';progress.hidden=false;progress.textContent='Three questions about your life';
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
      includeOther=false;persist();phase='ranked';message('');render();
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
