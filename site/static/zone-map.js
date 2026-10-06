/* One area input for discovery and the directory. No external map service. */
(() => {
  'use strict';
  const anchors={central:[48,52],north:[49,24],'north-west':[23,27],east:[76,36],
    'south-east':[73,69],'south-west':[40,79],west:[19,53]};
  window.mountZoneMap=(root,{zones,selected=[],onChange,counts=null})=>{
    let picked=new Set(selected);
    const controls=root.querySelector('.zone-controls');
    const labels=root.querySelector('.zone-map-labels');
    function toggle(id){
      picked.has(id)?picked.delete(id):picked.add(id);
      paint();onChange(zones.filter(z=>picked.has(z.id)).map(z=>z.id));
    }
    const buttons=new Map();
    controls.replaceChildren();labels?.replaceChildren();
    zones.forEach(zone=>{
      const button=document.createElement('button');button.type='button';
      button.className='zone-button';button.dataset.zone=zone.id;
      const name=document.createElement('span');name.textContent=zone.label;button.append(name);
      const places=document.createElement('small');places.textContent=zone.places;button.append(places);
      if(counts){const n=counts[zone.id]||0;const count=document.createElement('small');
        count.textContent=n+' notice'+(n===1?'':'s');button.append(count);}
      button.addEventListener('click',()=>toggle(zone.id));controls.append(button);buttons.set(zone.id,button);
      if(labels){const label=document.createElement('span');label.textContent=zone.label.replace(' London','');
        label.dataset.zone=zone.id;const [x,y]=anchors[zone.id];
        label.style.left=x+'%';label.style.top=y+'%';labels.append(label);}
    });
    root.querySelectorAll('svg [data-zone]').forEach(path=>{
      path.onclick=()=>{if(buttons.has(path.dataset.zone))toggle(path.dataset.zone);};
    });
    // Labels are a visual overlay; the labelled buttons are the keyboard input.
    if(labels)labels.onclick=event=>{const id=event.target.dataset.zone;if(buttons.has(id))toggle(id);};
    function paint(){
      buttons.forEach((button,id)=>button.setAttribute('aria-pressed',String(picked.has(id))));
      root.querySelectorAll('svg [data-zone],.zone-map-labels [data-zone]').forEach(node=>{
        node.classList.toggle('selected',picked.has(node.dataset.zone));
      });
      root.querySelector('.zone-selection').textContent=picked.size
        ? 'Selected: '+zones.filter(z=>picked.has(z.id)).map(z=>z.label).join(', ')
        : 'Anywhere in London / not sure yet';
    }
    paint();
  };
})();
