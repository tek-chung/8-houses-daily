/* Exercise the real built journey and its ranking, including absent information. */
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const {JSDOM, VirtualConsole} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'dist/find/index.html'), 'utf8')
  .replace('<script src="/assets/zone-map.js"></script>',
    '<script>'+fs.readFileSync(path.join(root, 'site/static/zone-map.js'), 'utf8')+'</script>')
  .replace('<script src="/assets/discovery.js" defer></script>',
    '<script>'+fs.readFileSync(path.join(root, 'site/static/discovery.js'), 'utf8')+'</script>');
const key = '8houses-volunteer-discovery-v1';
function boot(source=html, state=null, blocked=false, motion=false) {
  const errors=[], vc=new VirtualConsole(); vc.on('jsdomError', e=>errors.push(e.message));
  const dom=new JSDOM(source,{runScripts:'dangerously',url:'https://example.org/find/',virtualConsole:vc,
    beforeParse(w){
      w.matchMedia=()=>({matches:!motion});
      if(state) w.localStorage.setItem(key,JSON.stringify(state));
      if(blocked) Object.defineProperty(w,'localStorage',{get(){throw new Error('Storage blocked');}});
    }});
  assert.deepEqual(errors,[]);
  return dom;
}
function click(dom,text) {
  const button=[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent===text);
  assert(button,'Missing button: '+text);button.click();
}
const dom=boot(), d=dom.window.document;
click(dom,'Skip');click(dom,'Undo');
assert.equal(d.querySelector('#journey-progress').textContent,'Example 1 of 3');
click(dom,'Save role');click(dom,'Undo');
assert.equal(d.querySelector('#saved-count').textContent,'0');
for(let i=0;i<3;i++)click(dom,'Save role');
assert.match(d.querySelector('#discovery-stage').textContent,/Three roles worth/);
click(dom,'Compare saved roles');assert.equal(d.querySelectorAll('.shortlist-item').length,3);
const state=JSON.parse(dom.window.localStorage.getItem(key));
const restored=boot(html,state);click(restored,'Saved roles 3');
assert.equal(restored.window.document.querySelectorAll('.shortlist-item').length,3);
const remove=restored.window.document.querySelector('.shortlist-item>button');remove.click();
assert.equal(restored.window.document.querySelectorAll('.shortlist-item').length,2);
click(restored,'Clear saved roles');assert.equal(JSON.parse(restored.window.localStorage.getItem(key)).saved.length,0);
click(dom,'Change my answers');
d.querySelector('[name=when][value=weekend_daytime]').checked=true;
d.querySelector('[name=commitment][value=once]').checked=true;
click(dom,'Next question');click(dom,'Next question');
const map=d.querySelector('.discovery-area-map');
assert.equal(map.querySelectorAll('svg [data-zone]').length,33);
map.querySelector('.zone-button[data-zone=central]').click();
map.querySelector('svg [data-zone=east]').dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
assert.equal(map.querySelectorAll('.zone-button[aria-pressed=true]').length,2);
d.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
assert.equal(JSON.parse(dom.window.localStorage.getItem(key)).preferences.commitment,'once');
assert.deepEqual(JSON.parse(dom.window.localStorage.getItem(key)).preferences.zones,['central','east']);
assert.match(d.querySelector('#journey-progress').textContent,/Suggestions/);
assert(d.querySelector('.discovery-notice a.apply').href.startsWith('https://'));

const payload=JSON.parse(d.querySelector('#discovery-data').textContent);
const selected=payload.slice(0,3).map((r,i)=>({...r,commitment:i===0?'weekly':i===1?'unknown':'one_off',
  min_term_months:null,location_type:'in_person',when:i===2?['weekend_daytime']:[],
  areas:i===2?['Southwark']:[],zones:i===2?['central']:i===0?['east']:[],location_basis:'postcode',status:'open',confidence:1}));
const fixture=html.replace(/(<script type="application\/json" id="discovery-data">)[\s\S]*?(<\/script>)/,
  (_,start,end)=>start+JSON.stringify(selected)+end);
const ranked=boot(fixture,{saved:[],preferences:{when:['weekend_daytime'],commitment:'once',zones:['central'],remote:false}});
assert.equal(ranked.window.document.querySelector('.ad').dataset.id,selected[2].id,
  'A stated fit must rank ahead of unknown and conflicting particulars');
click(ranked,'Skip');
assert.equal(ranked.window.document.querySelector('.ad').dataset.id,selected[1].id);
assert.match(ranked.window.document.querySelector('.fit-reasons').textContent,/not stated/);
assert.doesNotMatch(ranked.window.document.querySelector('.fit-reasons').textContent,/one-off or flexible commitment/);
const blocked=boot(html,null,true);click(blocked,'Save role');
assert.match(blocked.window.document.querySelector('#journey-status').textContent,/this visit only/);
click(ranked,'Skip');
assert.equal(ranked.window.document.querySelector('.ad'),null,'Known conflicting roles must not silently fill the queue');
click(ranked,'Explore roles outside my preferences');
assert.equal(ranked.window.document.querySelector('.ad').dataset.id,selected[0].id);
const flexibleFixture=fixture.replace(JSON.stringify(selected),JSON.stringify(selected.map(r=>({...r,commitment:'flexible',min_term_months:6}))));
const flexible=boot(flexibleFixture,{saved:[],preferences:{when:[],commitment:'once',area:'any'}});
assert.equal(flexible.window.document.querySelector('.ad'),null,'An ongoing flexible role is not a one-off match');
const multiple=boot(fixture,{saved:[],preferences:{when:[],commitment:'any',zones:['central','east'],remote:false}});
const firstArea=multiple.window.document.querySelector('.ad').dataset.id;click(multiple,'Skip');
const secondArea=multiple.window.document.querySelector('.ad').dataset.id;
assert.deepEqual(new Set([firstArea,secondArea]),new Set([selected[0].id,selected[2].id]),
  'Both selected areas must rank ahead of an unknown location');
const legacy=boot(fixture,{saved:[],preferences:{when:[],commitment:'any',area:'Westminster'}});
assert.deepEqual(JSON.parse(legacy.window.localStorage.getItem(key)).preferences.zones,['central'],
  'Existing borough answers must migrate without losing saved roles');
const remoteOnly=boot(fixture,{saved:[],preferences:{when:[],commitment:'any',zones:[],remote:true}});
assert.equal(remoteOnly.window.document.querySelector('.ad'),null,'Known in-person roles do not fit remote-only');
const coverageRoles=selected.map((r,i)=>({...r,commitment:'weekly',when:[],zones:['central'],location_basis:i===0?'charity_coverage':i===1?'unknown':'postcode'}));
coverageRoles[1].zones=[];
const coverageFixture=fixture.replace(JSON.stringify(selected),JSON.stringify(coverageRoles));
const coverage=boot(coverageFixture,{saved:[],preferences:{when:[],commitment:'any',zones:['central'],remote:false}});
assert.equal(coverage.window.document.querySelector('.ad').dataset.id,selected[2].id,
  'A stated venue district ranks ahead of broad charity coverage');
click(coverage,'Skip');assert.match(coverage.window.document.querySelector('.fit-reasons').textContent,/does not confirm a venue/);
flexible.window.close();
for(const instance of [dom,restored,ranked,blocked,multiple,legacy,remoteOnly,coverage])instance.window.close();
console.log('Passed: undo, shortlist, persistence, questions, ranking, conflicts, flexible commitments and blocked storage.');

// Exercise deferred choices, interrupted tears and actual pointer directions.
const animated=boot(html,null,false,true), ad=animated.window.document;
function pointer(card,type,x,y=0,id=1){
  const event=new animated.window.Event(type,{bubbles:true});
  Object.assign(event,{clientX:x,clientY:y,pointerId:id,isPrimary:true,pointerType:'touch'});
  card.dispatchEvent(event);
}
let paper=ad.querySelector('.paper-slot .discovery-notice');
assert.equal(paper.querySelector('h3 a').draggable,false,'Links must not steal the paper drag');
const nativeDrag=new animated.window.Event('dragstart',{bubbles:true,cancelable:true});
paper.querySelector('h3 a').dispatchEvent(nativeDrag);
assert(nativeDrag.defaultPrevented,'Native dragging is suppressed across the card');
pointer(paper,'pointerdown',0);pointer(paper,'pointermove',320);
assert.equal(paper.style.getPropertyValue('--drag-x'),'320px','Paper follows the full drag without a distance cap');
pointer(paper,'pointercancel',320);
pointer(paper,'pointerdown',0);pointer(paper,'pointermove',120);
assert.equal(paper.dataset.choice,'save');
pointer(paper,'pointerup',120);
assert(paper.classList.contains('paper-tear-right'));
assert.equal(ad.querySelector('#saved-count').textContent,'0','Save waits for the tear');
paper.dispatchEvent(new animated.window.Event('animationend'));
assert.equal(ad.querySelector('#saved-count').textContent,'1');
paper.dispatchEvent(new animated.window.Event('animationend'));
assert.equal(ad.querySelector('#saved-count').textContent,'1','Animation commits once');
paper=ad.querySelector('.paper-slot .discovery-notice');
pointer(paper,'pointerdown',160);pointer(paper,'pointermove',20);pointer(paper,'pointerup',20);
assert(paper.classList.contains('paper-tear-left'));
paper.dispatchEvent(new animated.window.Event('animationend'));
assert.equal(ad.querySelector('#journey-progress').textContent,'Example 3 of 3');
click(animated,'Undo');
paper=ad.querySelector('.paper-slot .discovery-notice');
pointer(paper,'pointerdown',0);pointer(paper,'pointermove',40);pointer(paper,'pointercancel',40);
assert(!paper.hasAttribute('data-choice'));
pointer(paper,'pointerdown',0);pointer(paper,'pointermove',10,120);pointer(paper,'pointerup',120,130);
assert(!paper.classList.contains('paper-tear-right'),'Vertical scrolling never saves');
const summary=paper.querySelector('.role-details summary');
summary.click();assert(paper.querySelector('.role-details').open,'A tap still expands requirements');
summary.click();assert(!paper.querySelector('.role-details').open);
pointer(summary,'pointerdown',160);pointer(summary,'pointermove',20);pointer(summary,'pointerup',20);
assert(paper.classList.contains('paper-tear-left'),'Swiping from the requirements heading skips');
const swipeClick=new animated.window.MouseEvent('click',{bubbles:true,cancelable:true,detail:1});
summary.dispatchEvent(swipeClick);assert(swipeClick.defaultPrevented,'Swipe must not also expand requirements');
paper.dispatchEvent(new animated.window.Event('animationend'));
click(animated,'Undo');paper=ad.querySelector('.paper-slot .discovery-notice');
const titleLink=paper.querySelector('h3 a');
pointer(titleLink,'pointerdown',0);pointer(titleLink,'pointermove',20);
titleLink.dispatchEvent(new animated.window.Event('lostpointercapture',{bubbles:true}));
pointer(paper,'pointermove',240);
assert.equal(paper.style.getPropertyValue('--drag-x'),'240px','Implicit touch capture transfers from a child without cancelling the swipe');
pointer(paper,'pointerup',240);
assert(paper.classList.contains('paper-tear-right'),'The title link responds to swipes');
click(animated,'Saved roles 1');click(animated,'Keep exploring');
paper=ad.querySelector('.paper-slot .discovery-notice');
click(animated,'Save role');
click(animated,'Saved roles 1');
paper.dispatchEvent(new animated.window.Event('animationend'));
assert.equal(ad.querySelector('#saved-count').textContent,'1','Leaving the card cancels its pending choice');
assert(ad.querySelector('#discovery-stage.scrapbook'));
assert.equal(ad.querySelectorAll('.shortlist-item .clipping-note').length,1);
click(animated,'Keep exploring');assert(!ad.querySelector('#discovery-stage.scrapbook'));
animated.window.close();
const reduced=boot();const reducedPaper=reduced.window.document.querySelector('.paper-slot .discovery-notice');
pointer(reducedPaper,'pointerdown',0);pointer(reducedPaper,'pointermove',200);
assert.equal(reducedPaper.style.getPropertyValue('--drag-x'),'200px','Reduced motion still follows direct dragging');
pointer(reducedPaper,'pointerup',200);
assert.equal(reduced.window.document.querySelector('#saved-count').textContent,'1');
reduced.window.close();
console.log('Passed: left/right tears, single save, cancellation, vertical scrolling and scrapbook navigation.');
