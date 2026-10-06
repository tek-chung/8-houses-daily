/* Exercise the real built journey and its ranking, including absent information. */
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const {JSDOM, VirtualConsole} = require('jsdom');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'dist/find/index.html'), 'utf8')
  .replace('<script src="/assets/discovery.js" defer></script>',
    '<script>'+fs.readFileSync(path.join(root, 'site/static/discovery.js'), 'utf8')+'</script>');
const key = '8houses-volunteer-discovery-v1';
function boot(source=html, state=null, blocked=false) {
  const errors=[], vc=new VirtualConsole(); vc.on('jsdomError', e=>errors.push(e.message));
  const dom=new JSDOM(source,{runScripts:'dangerously',url:'https://example.org/find/',virtualConsole:vc,
    beforeParse(w){
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
d.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
assert.equal(JSON.parse(dom.window.localStorage.getItem(key)).preferences.commitment,'once');
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
