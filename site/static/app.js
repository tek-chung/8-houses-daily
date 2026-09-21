/* ============================================================
   DATA — separated from presentation per spec §13.
   ORGS: real names + real volunteer URLs (from the PoC).
   OPPS: entirely placeholder. provenance.method === "placeholder".
   ============================================================ */
const BUNDLE = window.__DATA__;
const ORGS = BUNDLE.orgs;
const META = BUNDLE.meta;

const COMMIT = [
  {v:"",           l:"any amount of time",  w:0, soon:0},
  {v:"one_off",    l:"one day",             w:1, soon:1},
  {v:"flexible",   l:"a few odd hours",     w:2, soon:2},
  {v:"weekly",     l:"a slot each week",    w:4, soon:3},
  {v:"fortnightly",l:"a slot fortnightly",  w:4, soon:3},
  {v:"monthly",    l:"a few hours a month", w:3, soon:3},
  {v:"long_term",  l:"a serious commitment",w:6, soon:5}
];
const ACT = [
  {v:"cooking_serving",l:"cook and serve"},{v:"befriending",l:"welcome and befriend"},
  {v:"outreach",l:"do outreach"},{v:"advice",l:"give advice or casework"},
  {v:"mentoring",l:"mentor someone"},{v:"teaching",l:"teach a skill"},
  {v:"shop_warehouse",l:"work a shop or warehouse"},{v:"practical",l:"garden, decorate or mend"},{v:"admin",l:"do admin or back office"},
  {v:"fundraising",l:"fundraise or run events"},{v:"campaigning",l:"campaign"},
  {v:"hosting",l:"host someone"},{v:"governance",l:"join a board"},{v:"varies",l:"anything — varies by day"}
];

/* Boroughs are derived from the data, not hard-coded. A role with its own postcode
   district uses that; otherwise it inherits the organisation's coverage. Roles with
   neither are location-unspecified and match any borough, and their card says so. */
function roleAreas(o){
  if(o.postcode_district) return [o.postcode_district];
  const b = ORGS[o.org_id].b || [];
  return b.length ? b : [];
}
const OPPS = BUNDLE.opps.map(o=>({...o, areas: roleAreas(o)}));
const BOROUGHS = [...new Set(OPPS.flatMap(o=>o.areas))].sort();

/* ---------- state ---------- */
/* The page we landed on already knows what it is showing. Read it off <body>
   rather than defaulting, so a deep link renders correctly before any JavaScript
   runs and stays correct afterwards. */
const _ds=document.body.dataset;
const prefersStill=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const S={c:_ds.commitment||"",b:_ds.borough||"",act:_ds.activity||"",
         who:"",remote:"",open:"",sort:"soonest"};

/* Not every page carries every control. bind() no-ops when one is absent, which
   is cheaper than guarding each wiring line and impossible to get half-right. */
const bind=(id,ev,fn)=>{const el=document.getElementById(id); if(el) el[ev]=fn;};
let prevCount=null;

/* ---------- matcher: pure function, spec §12 ---------- */
const DBS_RANK={none:0,basic:1,enhanced:2,unknown:9};
function match(s){
  let out=OPPS.filter(o=>{
    if(s.c && o.commitment!==s.c) return false;
    // A role with no stated location matches any borough — and its card says so.
    // This is not the PoC's london-wide bug: that passed *organisations* through a
    // *location* filter. Here the role genuinely has no location to contradict.
    // own_home and remote roles happen wherever you are, so an area filter must
    // not exclude them. This is not the PoC's london-wide bug: that passed whole
    // organisations through a location filter. These roles have no location to
    // contradict, and their cards say so.
    if(s.b && !["remote","own_home"].includes(o.location_type)
       && o.areas.length && !o.areas.includes(s.b)) return false;
    // A "varies" role is a rotating calendar. When someone asks for a specific
    // activity we exclude it rather than promise a match we cannot support.
    if(s.act && o.activity!==s.act) return false;
    if(s.who==="team_only" && o.who_can_apply!=="team_only") return false;
    if(s.who==="individual" && o.who_can_apply==="team_only") return false;
    if(s.remote==="remote" && !["remote","hybrid"].includes(o.location_type)) return false;
    if(s.open==="open" && o.status!=="open") return false;
    return true;
  });
  const C=v=>COMMIT.find(x=>x.v===v)||{w:9,soon:9};
  const rank=o=>o.status==="open"?0:o.status==="seasonal_closed"?1:2;
  out.sort((a,b)=>{
    if(s.sort==="az") return a.title.localeCompare(b.title);
    if(s.sort==="least") return C(a.commitment).w-C(b.commitment).w||(a.typical_shift_hours||99)-(b.typical_shift_hours||99);
    return rank(a)-rank(b)||C(a.commitment).soon-C(b.commitment).soon
      ||(a.typical_shift_hours||99)-(b.typical_shift_hours||99);
  });
  return out;
}
function countIf(over){return match(Object.assign({},S,over)).length}


/* ================= borough tile map (Phase 2) =================
   A tile cartogram, not a boundary map, and deliberately so.

   1. Precision honesty. Some notices carry a postcode district, some inherit only
      their charity's borough coverage, some have no location at all. Pins on a
      street map would imply an accuracy we do not have; a borough plate says
      exactly as much as we know.
   2. Tap targets. Most London homelessness services sit in small inner boroughs,
      which are the hardest things to hit on a true-shape map. Equal plates make
      Havering no easier to strike than Camden.
   3. No network. No tile server, no key, nothing to rate-limit or pay for.

   Built from HTML and CSS grid rather than SVG. The first version was an SVG with
   a 116-unit viewBox and `font-size:5px` on the labels — but font-size inside SVG
   resolves in user units, so at ~1000px wide it rendered at 43px and every label
   burst out of its plate and over its neighbours. A grid of labelled rectangles
   needs no vector graphics, and real <button> elements are keyboard-operable and
   announceable for free.
   =============================================================== */
/* Postcode districts we hold map onto their borough, so a notice recorded as SE1
   colours Southwark rather than sitting in a category of its own. */
const DISTRICT_BOROUGH={SE1:"Southwark",SE11:"Lambeth",SE27:"Lambeth",
  E1:"Tower Hamlets",E2:"Tower Hamlets",E8:"Hackney",N1:"Islington",N16:"Hackney",
  NW1:"Camden",WC1:"Camden",WC1H:"Camden",SW1:"Westminster",SW1P:"Westminster",
  SW4:"Lambeth",SW9:"Lambeth",SW16:"Lambeth",SW17:"Wandsworth",
  EC1:"Islington",W10:"Kensington and Chelsea"};
const MAP = window.__MAP__ || null;
const BOROUGH_NAMES = MAP ? MAP.boroughs.map(b=>b.name) : [];

function boroughsFor(o){
  if(["remote","own_home"].includes(o.location_type)) return [];
  const out=new Set();
  o.areas.forEach(a=>out.add(DISTRICT_BOROUGH[a]||a));
  return [...out].filter(b=>BOROUGH_NAMES.includes(b));
}

/* ---------- label placement ----------
   Badges sit at borough centroids, and centroids of adjacent boroughs are close
   together — Kensington and Hammersmith are neighbours and both narrow, and
   Wandsworth, Lambeth and Southwark run in a line. Placed naively they overlap
   and become unreadable.

   Worked in percentage-of-container space and estimated from character counts
   rather than measured with getBoundingClientRect. Two reasons: measuring every
   badge forces a layout pass per render, and jsdom computes no layout at all, so
   a measured version could not be tested. Estimation is deterministic and the
   arithmetic is checkable.                                                   */
const BADGE_PX = 11.5;        // font-size of a badge
const CHAR_PX  = 6.15;        // mean advance of Archivo at that size
const BADGE_PAD = 20;         // horizontal padding, border and the count gap
const BADGE_H_PX = 20;

function placeBadges(items, field){
  const W = (field && field.getBoundingClientRect().width) || 1000;
  const H = W * 773 / 1000;
  const pctW = t => (t.length*CHAR_PX + BADGE_PAD) / W * 100;
  const hPct = BADGE_H_PX / H * 100;

  let bs = items.map(it => ({
    ...it, x: it.ax, y: it.ay, terse:false,
    w: pctW(String(it.n) + " " + it.short), h: hPct
  }));

  const overlap = (a,b) =>
    Math.abs(a.x-b.x) < (a.w+b.w)/2 + 0.4 &&
    Math.abs(a.y-b.y) < (a.h+b.h)/2 + 0.4;

  /* Separate, then if anything is still colliding drop the crowded ones to their
     count alone — a number in the right place beats a name in the wrong one. */
  for(let pass=0; pass<2; pass++){
    for(let iter=0; iter<80; iter++){
      let moved=false;
      for(let i=0;i<bs.length;i++){
        for(let j=i+1;j<bs.length;j++){
          const a=bs[i], b=bs[j];
          if(!overlap(a,b)) continue;
          moved=true;
          /* Push along whichever axis needs least movement. Badges are wide and
             short, so that is almost always vertical, which also keeps them
             nearer their own borough than sliding sideways would. */
          const needY=(a.h+b.h)/2 + 0.6 - Math.abs(a.y-b.y);
          const needX=(a.w+b.w)/2 + 0.6 - Math.abs(a.x-b.x);
          if(needY <= needX){
            const d=(a.y<=b.y? -1 : 1) * needY/2;
            a.y+=d; b.y-=d;
          } else {
            const d=(a.x<=b.x? -1 : 1) * needX/2;
            a.x+=d; b.x-=d;
          }
        }
      }
      /* Keep them on the sheet. */
      bs.forEach(b=>{
        b.x=Math.min(100-b.w/2-0.5, Math.max(b.w/2+0.5, b.x));
        b.y=Math.min(100-b.h/2-0.5, Math.max(b.h/2+0.5, b.y));
      });
      if(!moved) break;
    }
    const still=bs.filter(a=>bs.some(b=>a!==b&&overlap(a,b)));
    if(!still.length) break;
    still.forEach(a=>{ a.terse=true; a.w=pctW(String(a.n)); a.x=a.ax; a.y=a.ay; });
  }
  return bs;
}

/* ---------- the district map ----------
   Real borough outlines, with the Thames taken from the seam where north-bank and
   south-bank boroughs meet — same source as the shapes, so it lies on the banks.

   No text inside the SVG. Font-size in a scaled viewBox resolves in user units,
   which is how an earlier version came to render its labels at 43px; the counts
   are HTML positioned by percentage over the top. The SVG is aria-hidden and the
   chips beneath are the real control, so a keyboard user is not walked through 33
   duplicate tab stops to reach a view of what the chips already do.        */
function drawMap(){
  const box=$("tilemap"); if(!box) return;

  /* Counted with the district blank ignored, so each borough shows what choosing
     it would give rather than what has already been chosen. */
  const base=match(Object.assign({},S,{b:""}));
  const counts={};
  base.forEach(o=>boroughsFor(o).forEach(b=>counts[b]=(counts[b]||0)+1));
  const anywhere=base.filter(o=>!boroughsFor(o).length).length;
  const lit=Object.keys(counts).sort();

  /* --- shapes --- */
  const svg=$("boroughs");
  if(svg){
    const max=Math.max(1,...Object.values(counts));
    svg.querySelectorAll("path.bo").forEach(el=>{
      const n=counts[el.dataset.name]||0;
      el.classList.toggle("lit",n>0);
      el.classList.toggle("on",S.b===el.dataset.name);
      /* Four steps rather than a continuous ramp: with a handful of notices a
         smooth scale is a lie about precision nobody can read anyway. */
      el.classList.remove("q1","q2","q3");
      if(n>0) el.classList.add("q"+Math.min(3,Math.ceil(n/max*3)));
      el.style.cursor=n?"pointer":"default";
    });
  }

  /* --- count badges, in HTML over the shapes --- */
  const bad=$("badges"), leadSvg=$("leaders");
  if(bad && MAP){
    bad.innerHTML="";
    if(leadSvg) leadSvg.innerHTML="";
    const placed=placeBadges(
      MAP.boroughs.filter(b=>counts[b.name]).map(b=>({
        name:b.name, short:b.short, n:counts[b.name], ax:b.cx, ay:b.cy
      })), $("mapfield"));

    placed.forEach(pb=>{
      const el=document.createElement("span");
      el.className="badge"+(S.b===pb.name?" on":"")+(pb.terse?" terse":"");
      el.style.left=pb.x+"%";
      el.style.top=pb.y+"%";
      /* Kept for the tests: jsdom computes no layout, so the placement can only
         be checked against the rectangles the algorithm actually used. */
      el.dataset.x=pb.x.toFixed(2); el.dataset.y=pb.y.toFixed(2);
      el.dataset.w=pb.w.toFixed(2); el.dataset.h=pb.h.toFixed(2);
      el.dataset.name=pb.name;
      el.innerHTML=pb.terse ? '<b>'+pb.n+'</b>'
                            : '<b>'+pb.n+'</b> '+pb.short;
      bad.appendChild(el);

      /* A leader line where a badge has been pushed clear of its borough, so the
         reader can still tell which shape it belongs to. */
      if(leadSvg && Math.hypot(pb.x-pb.ax, pb.y-pb.ay) > 1.6){
        const ln=document.createElementNS("http://www.w3.org/2000/svg","line");
        ln.setAttribute("x1",pb.ax); ln.setAttribute("y1",pb.ay);
        ln.setAttribute("x2",pb.x);  ln.setAttribute("y2",pb.y);
        ln.setAttribute("class","leader");
        leadSvg.appendChild(ln);
      }
    });
  }

  /* --- chips: the control, and the whole map on a phone --- */
  box.innerHTML="";
  if(!lit.length){
    const p=document.createElement("p");
    p.className="nodistrict";
    p.textContent="No notice in this set sits in a named district.";
    box.appendChild(p);
  }
  lit.forEach(name=>{
    const n=counts[name];
    const b=document.createElement("button");
    b.type="button";
    b.className="bt lit"+(S.b===name?" on":"");
    b.title=name;
    b.setAttribute("aria-pressed",S.b===name?"true":"false");
    b.setAttribute("aria-label",`${name}: ${n} notice${n===1?"":"s"}`);
    const short=(MAP&&(MAP.boroughs.find(x=>x.name===name)||{}).short)||name;
    b.innerHTML='<span class="bt-name">'+short+'</span><span class="bt-n">'+n+'</span>';
    b.addEventListener("click",()=>{S.b=(S.b===name?"":name);render()});
    box.appendChild(b);
  });

  const ms=$("mapsub");
  if(ms) ms.textContent = S.b ? `showing ${S.b} only`
    : `${lit.length} district${lit.length===1?"":"s"} carry notices`;
  const mc=$("mapclear"); if(mc) mc.hidden = !S.b;
  const note=$("mapnote");
  if(note) note.textContent = anywhere
    ? `${anywhere} notice${anywhere===1?" does":"s do"} not sit in any one district \u2014 remote, at your own home, or their page does not say. Those are printed whichever district you choose.`
    : "";
}


/* ---------- the coupon ---------- */
/* Filling a slot inks it red. Completion is rewarded rather than merely recorded,
   which is the whole point of making it a form you fill in. */
function inkSlots(){
  [["b1","c"],["b2","b"],["b3","act"]].forEach(([id,key])=>{
    const sel=document.getElementById(id);
    if(!sel) return;
    const slot=sel.closest(".slot");
    if(slot) slot.classList.toggle("filled", !!S[key]);
  });
}

/* ---------- routing ---------- */
const SLUG=s=>s.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"");
const DOOR={one_off:"one-day",flexible:"flexible",weekly:"weekly",
  fortnightly:"fortnightly",monthly:"monthly",long_term:"bigger"};

function canonicalPath(s){
  const parts=[s.c?DOOR[s.c]:"all"];
  if(s.b) parts.push(SLUG(s.b));
  if(s.act) parts.push(SLUG(s.act));
  return "/"+parts.join("/")+"/";
}

function setNoindex(on){
  let m=document.querySelector('meta[name="robots"][data-dynamic]');
  if(on&&!m){m=document.createElement("meta");m.name="robots";
    m.dataset.dynamic="1";m.content="noindex,follow";document.head.appendChild(m);}
  else if(!on&&m) m.remove();
}

/* ---------- render ---------- */
const $=id=>document.getElementById(id);
const cap=s=>s.charAt(0).toUpperCase()+s.slice(1);
const dbsLabel=d=>d==="none"?"No DBS needed":d==="basic"?"Basic DBS":d==="enhanced"?"Enhanced DBS":d==="required_unspecified"?"DBS check required — level not stated":"Screening not stated — worth asking";
const MONTH=[,"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function fillSelect(el,items,{placeholder,counts}={}){
  el.innerHTML="";
  if(placeholder){const o=document.createElement("option");o.value="";o.textContent=placeholder;el.appendChild(o)}
  items.forEach(it=>{
    const o=document.createElement("option");o.value=it.v;
    const n=counts?counts(it.v):null;
    o.textContent=n===null?it.l:`${it.l} (${n})`;
    if(n===0) o.disabled=true;
    el.appendChild(o);
  });
}

function buildSentence(){
  fillSelect($("b1"),COMMIT,{counts:v=>countIf({c:v})});
  fillSelect($("b2"),BOROUGHS.map(b=>({v:b,l:b})),
    {placeholder:"add a borough",counts:v=>countIf({b:v})});
  fillSelect($("b3"),ACT,{placeholder:"anything",counts:v=>countIf({act:v})});
  $("b1").value=S.c; $("b2").value=S.b; $("b3").value=S.act;
}
function render(){
  const rows=match(S);
  const n=rows.length;

  const cn=$("cnum");
  if(cn) cn.textContent = n===0 ? "No notices answer this"
    : `${n} notice${n===1?"":"s"}`;
  const d=$("cdelta");
  if(d){
    d.textContent=(prevCount!==null&&prevCount!==n)
      ? `Stop press \u2014 was ${prevCount}` : "";
    /* re-trigger the flash by remounting the node */
    if(d.textContent){const c=d.cloneNode(true);d.replaceWith(c);}
  }
  prevCount=n;

  buildSentence();
  inkSlots();
  ["rWho","rOpen","rRemote"].forEach(id=>{
    $(id).classList.toggle("on",!!$(id).value);
  });

  const path=canonicalPath(S);
  const uo=$("urlout"); if(uo) uo.textContent=path;
  /* One- and two-blank states are pre-rendered and indexable. Three-blank states
     exist only to be shared, so they get noindex (spec §14). */
  setNoindex([S.c,S.b,S.act].filter(Boolean).length>2);
  try{ if(location.pathname!==path) history.replaceState(null,"",path); }catch(e){}

  drawMap();

  const L=$("list");
  if(!L) return;
  const eb=$("empty"); if(eb) eb.hidden = n>0;

  /* Filter the cards the server already rendered rather than rebuilding them.
     There was a second copy of the card markup here, and it had drifted from
     build.py's card() — old class names, old copy. One renderer, one truth.
     Every results page contains exactly its own notices, so any refinement is a
     subset of what is on the page; changing the commitment leaves that subset,
     so that one navigates to the pre-rendered page instead. */
  const wanted = new Set(rows.map(o => o.id));
  const nodes = [...L.querySelectorAll(".ad")];
  nodes.forEach(el => { el.hidden = !wanted.has(el.dataset.id); });

  /* Re-order to match the chosen sort, moving nodes rather than recreating them. */
  rows.forEach(o => {
    const el = nodes.find(n => n.dataset.id === o.id);
    if (el) L.appendChild(el);
  });

  const staticEmpty = document.querySelector(".empty:not(#empty)");
  if (staticEmpty) staticEmpty.hidden = n > 0;
  if (n === 0) renderEmpty();
}

function renderEmpty(){
  const tests=[
    {lab:"Any district",fix:{b:""},k:"b"},
    {lab:"Anything at all",fix:{act:""},k:"act"},
    {lab:"Include those not recruiting",fix:{open:""},k:"open"},
    {lab:"Alone or as a team",fix:{who:""},k:"who"},
    {lab:"Try one-day notices",fix:{c:"one_off"},k:"c"},
    {lab:"Try weekly notices",fix:{c:"weekly"},k:"c"}
  ];
  const live=tests.map(t=>({...t,n:countIf(t.fix)}))
    .filter(t=>t.n>0 && JSON.stringify(t.fix)!==JSON.stringify(
      Object.fromEntries(Object.keys(t.fix).map(k=>[k,S[k]]))))
    .sort((a,b)=>b.n-a.n).slice(0,3);
  const bind=S.b?"the district":S.act?"what you would do":S.who?"how you are applying":S.open?"asking only for those recruiting":"how much time you have";
  $("ehead").textContent="No notices answer this";
  $("ebody").textContent=`In this edition it is ${bind} that rules everything out. Try one of these instead:`;
  const box=$("eopts");box.innerHTML="";
  if(!live.length){
    const b=document.createElement("button");b.textContent="Begin again";
    b.onclick=resetAll;box.appendChild(b);return;
  }
  live.forEach(t=>{
    const b=document.createElement("button");
    b.textContent=`${t.lab} (${t.n})`;
    b.onclick=()=>{Object.assign(S,t.fix);
      $("rWho").value=S.who;$("rOpen").value=S.open;$("rRemote").value=S.remote;
      $("rSort").value=S.sort;render()};
    box.appendChild(b);
  });
}

function resetAll(){
  Object.assign(S,{c:_ds.commitment||"",b:"",act:"",who:"",remote:"",open:"",sort:"soonest"});
  ["rWho","rOpen","rRemote"].forEach(id=>$(id).value="");
  $("rSort").value="soonest";prevCount=null;render();
}

/* ---------- typeahead: closed vocabulary, spec §7.3.2 ---------- */
const VOCAB=[];
Object.entries(ORGS).forEach(([k,o])=>VOCAB.push({label:o.n,kind:"Charity",terms:[o.n,...(o.a||[])],url:o.u}));
BOROUGHS.forEach(b=>VOCAB.push({label:b,kind:"Borough",terms:[b],borough:b}));
OPPS.forEach(o=>VOCAB.push({label:o.title,kind:ORGS[o.org_id].n,terms:[o.title],role:o}));

function fuzzy(q,t){
  q=q.toLowerCase();t=t.toLowerCase();
  if(t.includes(q)) return t.startsWith(q)?0:1;
  let i=0;for(const ch of t){if(ch===q[i])i++;if(i===q.length)return 2}
  return -1;
}
const taIn=$("ta"),taUl=$("talist");let taItems=[],taIdx=-1;
function taRender(q){
  if(!q.trim()){taClose();return}
  taItems=VOCAB.map(v=>{
    const s=Math.min(...v.terms.map(t=>{const r=fuzzy(q,t);return r<0?99:r}));
    return {v,s};
  }).filter(x=>x.s<99).sort((a,b)=>a.s-b.s).slice(0,7).map(x=>x.v);
  if(!taItems.length){taClose();return}
  taUl.innerHTML="";
  taItems.forEach((it,i)=>{
    const li=document.createElement("li");
    li.role="option";li.id="ta-o"+i;li.setAttribute("aria-selected",i===taIdx);
    li.innerHTML=`<span>${it.label}</span><em>${it.kind}</em>`;
    li.onclick=()=>taPick(i);
    taUl.appendChild(li);
  });
  taUl.hidden=false;taIn.setAttribute("aria-expanded","true");
}
function taClose(){taUl.hidden=true;taIn.setAttribute("aria-expanded","false");taIdx=-1;
  taIn.removeAttribute("aria-activedescendant")}
function taPick(i){
  const it=taItems[i];if(!it)return;
  if(it.borough){S.b=it.borough;S.act="";go()}
  else if(it.role){S.c=it.role.commitment;S.b=it.role.areas[0]||"";S.act=it.role.activity;go()}
  else if(it.url) window.open(it.url,"_blank","noopener");
  taIn.value="";taClose();
}
taIn.addEventListener("input",e=>{taIdx=-1;taRender(e.target.value)});
taIn.addEventListener("keydown",e=>{
  if(taUl.hidden)return;
  if(e.key==="ArrowDown"||e.key==="ArrowUp"){
    e.preventDefault();
    taIdx=(taIdx+(e.key==="ArrowDown"?1:-1)+taItems.length)%taItems.length;
    [...taUl.children].forEach((li,i)=>li.setAttribute("aria-selected",i===taIdx));
    taIn.setAttribute("aria-activedescendant","ta-o"+taIdx);
  }
  if(e.key==="Enter"&&taIdx>=0){e.preventDefault();taPick(taIdx)}
  if(e.key==="Escape")taClose();
});
document.addEventListener("click",e=>{if(!e.target.closest(".ta"))taClose()});

/* ---------- wiring ---------- */
function go(){
  prevCount=null;
  if($("results")) render();          // already on a results page
  else location.href=canonicalPath(S); // on the home page: go to the real URL
}

document.querySelectorAll("[data-door]").forEach(b=>{
  if(b.tagName==="A") return;   // on the static home page these are real links
  b.onclick=()=>{S.c=b.dataset.door;S.b="";S.act="";go()};
});
bind("back","onclick",()=>{location.href="/"});
/* A results page holds only its own commitment, so this one is navigation. */
bind("b1","onchange",e=>{S.c=e.target.value;
  if($("results")) location.href=canonicalPath(S); else render();});
bind("b2","onchange",e=>{S.b=e.target.value;render()});
bind("b3","onchange",e=>{S.act=e.target.value;render()});
bind("rOpen","onchange",e=>{S.open=e.target.value;render()});
bind("rWho","onchange",e=>{S.who=e.target.value;render()});
bind("rRemote","onchange",e=>{S.remote=e.target.value;render()});
bind("rSort","onchange",e=>{S.sort=e.target.value;render()});
bind("rstall","onclick",resetAll);
bind("mapclear","onclick",()=>{S.b="";render()});
bind("copy","onclick",()=>{
  navigator.clipboard?.writeText(location.origin+canonicalPath(S)).catch(()=>{});
  $("copy").textContent="copied";
  setTimeout(()=>$("copy").textContent="copy link",1400);
});

function doorCounts(){
  document.querySelectorAll("[data-dc]").forEach(el=>{
    const n=OPPS.filter(o=>o.commitment===el.dataset.dc).length;
    el.textContent=`${n} role${n===1?"":"s"}`;
  });
}
doorCounts();

/* Cards are already server-rendered and correct. Only take over if there is a
   live results region to drive — otherwise leave the static page alone. */
if($("results")&&$("list")) render();
