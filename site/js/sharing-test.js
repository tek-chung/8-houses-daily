/* Share only the requested public page, never saved IDs or preferences. */
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'../..');
const html=fs.readFileSync(path.join(root,'dist/find/index.html'),'utf8')
  .replace('<script src="/assets/discovery.js" defer></script>',
    '<script>'+fs.readFileSync(path.join(root,'site/static/discovery.js'),'utf8')+'</script>');
function boot(share,clipboard,url='https://volunteer.example/find/'){
  const errors=[],console=new VirtualConsole();console.on('jsdomError',e=>errors.push(e.message));
  const dom=new JSDOM(html,{runScripts:'dangerously',url,virtualConsole:console,beforeParse(w){
    if(share)w.navigator.share=share;
    if(clipboard)Object.defineProperty(w.navigator,'clipboard',{value:{writeText:clipboard}});
  }});
  assert.deepEqual(errors,[]);return dom;
}
function click(dom,text){
  const button=[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent===text);
  assert(button,text);button.click();
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  const shared=[],copied=[];
  const native=boot(async data=>shared.push(data),async text=>copied.push(text));
  click(native,'Share role');await settle();
  const role=JSON.parse(native.window.document.querySelector('#discovery-data').textContent)
    .find(r=>r.id===native.window.document.querySelector('.ad').dataset.id);
  assert.equal(shared[0].url,'https://volunteer.example/role/'+role.id+'/');
  assert(shared[0].title.includes(role.charity));
  assert.equal(native.window.document.querySelector('#share-journey'),null);
  assert.deepEqual(Object.keys(shared[0]).sort(),['text','title','url']);
  assert.equal(copied.length,0);
  const cancelled=boot(async()=>{throw Object.assign(new Error('Cancelled'),{name:'AbortError'});},async text=>copied.push(text));
  click(cancelled,'Share role');await settle();assert.equal(copied.length,0,'Cancellation must not copy anything');
  const fallback=boot(null,async text=>copied.push(text));
  click(fallback,'Share role');await settle();assert.match(copied[0],/^https:\/\/volunteer\.example\/role\//);
  const blocked=boot(null,async()=>{throw new Error('Clipboard blocked');});
  click(blocked,'Share role');await settle();
  const field=blocked.window.document.querySelector('.share-link input');
  assert(field.readOnly);assert.match(field.value,/\/role\//);
  const preview=boot(async()=>{throw new Error('Must not share local preview');},async text=>copied.push(text),'http://127.0.0.1:8765/find/');
  click(preview,'Share role');await settle();
  assert.match(preview.window.document.querySelector('#journey-status').textContent,/only works on this device/);
  for(const dom of [native,cancelled,fallback,blocked,preview])dom.window.close();
  console.log('Passed: native sharing, cancellation, copying, manual fallback, preview disclosure and private-state exclusion.');
})().catch(error=>{console.error(error);process.exitCode=1;});
