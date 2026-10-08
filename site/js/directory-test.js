const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const dist=path.resolve(__dirname,'../../dist');
for(const route of ['one-day','weekly','bigger','all']){
  let html=fs.readFileSync(path.join(dist,route,'index.html'),'utf8');
  const before=(html.match(/class="ad"/g)||[]).length;
  html=html.replace(/<script\b[^>]*src="([^"?]+)[^"]*"[^>]*><\/script>/g,
    (_,src)=>'<script>'+fs.readFileSync(path.join(dist,src),'utf8')+'</script>');
  const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
  const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://example.org/'+route+'/',virtualConsole:vc});
  assert.deepEqual(errors,[]);
  assert.equal(dom.window.document.querySelectorAll('.ad:not([hidden])').length,before,
    route+' must keep every generated notice after JavaScript runs');
  assert.equal(dom.window.eval('OPPS.every(o => "typical_shift_hours" in o)'),true);
  const area=dom.window.document.querySelector('#b2');
  if(route!=='all')assert.equal(area.options.length,8,'Seven areas plus the unfiltered choice');
  if(route==='all'){
    assert.equal(area,null,'Location has no separate lookup');
    assert.equal(dom.window.document.querySelector('#role-search'),null);
    const when=dom.window.document.querySelector('[name=browse-when][value=weekend_daytime]');
    when.checked=true;when.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
    assert.equal(dom.window.eval('match(S).every(o=>!o.when.length || o.when.includes("weekend_daytime"))'),true);
    const once=dom.window.document.querySelector('[name=browse-frequency][value=once]');
    once.checked=true;once.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
    assert.equal(dom.window.eval('match(S).every(o=>!o.min_term_months && ["one_off","flexible","unknown"].includes(o.commitment))'),true);
    assert.match(dom.window.location.search,/frequency=once/);
    dom.window.document.querySelector('#rstall').click();
    assert.equal(when.checked,false);
    const advanced=dom.window.document.querySelector('.advanced-filters');
    assert(!advanced.open,'Advanced filters start collapsed');
    const activity=advanced.querySelector('#b3');
    activity.value='cooking_serving';activity.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
    assert.equal(dom.window.eval('match(S).every(o=>o.activity==="cooking_serving")'),true);
    const who=advanced.querySelector('#rWho');
    who.value='individual';who.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
    assert.equal(dom.window.eval('match(S).every(o=>o.who_can_apply!=="team_only")'),true);
    dom.window.document.querySelector('#rstall').click();
    assert.equal(activity.value,'');assert.equal(who.value,'');
    const map=dom.window.document.querySelector('#area-map');
    map.querySelector('.zone-button[data-zone=central]').click();
    const ids=[...dom.window.document.querySelectorAll('.ad:not([hidden])')].map(card=>card.dataset.id);
    assert(ids.length>0);
    assert.equal(dom.window.eval('match(S).every(o => o.zones.includes("central") || ["remote","own_home"].includes(o.location_type))'),true);
    assert.equal(ids.length,dom.window.eval('match(S).length'));
    assert.equal(dom.window.location.search,'?area=central');
    assert.equal(dom.window.eval('canonicalPath(S)'),'/all/?area=central');
    const root=dom.window.document.querySelector('#area-map');
    root.querySelector('.zone-button[data-zone=east]').click();
    assert.equal(dom.window.eval('S.z'),'central,east');
    assert.equal(dom.window.eval('match(S).every(o=>o.zones.some(z=>["central","east"].includes(z)) || ["remote","own_home"].includes(o.location_type))'),true);
    assert.equal(root.querySelectorAll('.zone-button[aria-pressed=true]').length,2);
    // The SVG survives rerenders: its handlers must not accumulate.
    root.querySelector('svg [data-zone=central]').dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
    assert.equal(dom.window.eval('S.z'),'east');
    root.querySelector('svg [data-zone=central]').dispatchEvent(new dom.window.MouseEvent('click',{bubbles:true}));
    assert.equal(dom.window.eval('S.z'),'central,east');
    dom.window.eval('S.z="";S.b="Camden";render()');
    assert.equal(dom.window.eval('match(S).some(o=>o.postcode_district==="NW5")'),true,
      'Exact borough map selection must include its postcode districts');
  }
  dom.window.close();
}
console.log('Passed: generated and interactive directory groups agree; shift lengths are shipped for sorting.');
