const path=require('path');
const {chromium}=require(path.join(__dirname,'..','site','node_modules','playwright-core'));
const T=[9,19,22,26,28,32,33,35];
(async()=>{
const b=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--allow-file-access-from-files']});
const p=await b.newPage({viewport:{width:900,height:1400},deviceScaleFactor:2});
await p.goto('file:///'+path.join(__dirname,'..','site','神智核.html').replace(/\\/g,'/'),{waitUntil:'domcontentloaded'});
await p.waitForTimeout(1500);
await p.evaluate(()=>{try{go('#/chem/pastpaper')}catch(e){location.hash='#/chem/pastpaper'}});
await p.waitForTimeout(1500);
await p.evaluate(()=>{try{showPPView('byyear')}catch(e){}});
await p.waitForTimeout(600);
await p.evaluate(()=>{try{const bx=document.getElementById('ppy-2024'); if(!bx||bx.dataset.open!=='1') ppToggleYear('2024');}catch(e){}});
await p.waitForTimeout(1200);
// 全部题卡灌 src 后量自然尺寸
const info=await p.evaluate(()=>{
  const out=[];
  document.querySelectorAll('#ppy-2024 .ppq').forEach(c=>{
    c.querySelectorAll('img.pplazy[data-src]').forEach(im=>{im.src=im.dataset.src;im.removeAttribute('data-src');});
  });
  return new Promise(res=>setTimeout(()=>{
    document.querySelectorAll('#ppy-2024 .ppq').forEach(c=>{
      const im=c.querySelector('img');
      out.push({id:c.dataset.id, n:im?im.naturalWidth:0, w:im?im.naturalHeight:0, src:im?im.getAttribute('src'):''});
    });
    res(out);
  },1500));
});
console.log('cards:',info.length);
info.forEach(x=>console.log(x.id, x.n+'x'+x.w, x.src));
const bad=info.filter(x=>x.src && (!x.n));
console.log('broken:', bad.length? bad.map(x=>x.id).join(','):'none');
// 逐张截图（含图题）
for(const q of T){
  const id='pp_chem_2024_q'+q;
  const ok=await p.evaluate(id=>{
    const c=[...document.querySelectorAll('#ppy-2024 .ppq')].find(x=>x.dataset.id===id);
    if(!c) return false;
    c.scrollIntoView({block:'center'}); return true;
  },id);
  if(!ok){console.log('!!',id);continue;}
  await p.waitForTimeout(500);
  const el=await p.$('#ppy-2024 .ppq[data-id="'+id+'"]');
  await el.screenshot({path:path.join(__dirname,'c2024_'+q+'.png')});
}
console.log('shots done');
await b.close();
})();
