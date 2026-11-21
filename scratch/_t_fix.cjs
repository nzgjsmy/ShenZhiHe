const path = require('path');
const { chromium } = require(path.join(__dirname, '..', 'site', 'node_modules', 'playwright-core'));
(async () => {
  const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 980, height: 1500 }, deviceScaleFactor: 2 });
  await p.goto('file:///' + path.join(__dirname, '..', 'site', '神智核.html').replace(/\\/g, '/'), { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1500);
  await p.evaluate(() => go('#/chem/pastpaper'));
  await p.waitForTimeout(1200);
  const jobs = [['3b','pp_chem_2013_q30'], ['3b','pp_chem_2019_q10'], ['2a','pp_chem_2015_q13'], ['3b','pp_chem_2020_q27']];
  let cur = '';
  for (const [topic, id] of jobs) {
    if (cur !== topic) { await p.evaluate(t => ppSetTopic(t), topic); await p.waitForTimeout(900); cur = topic; }
    const ok = await p.evaluate(id => {
      const c = [...document.querySelectorAll('.ppq')].find(x => x.dataset.id === id);
      if (!c) return false;
      c.scrollIntoView({ block: 'center' });
      const t = c.querySelector('.ppbtn'), ans = c.querySelector('.ppans');
      if (t && ans && !ans.classList.contains('open')) ppToggle(t);
      c.querySelectorAll('img.pplazy[data-src]').forEach(im => { im.src = im.dataset.src; im.removeAttribute('data-src'); });
      return true;
    }, id);
    if (!ok) { console.log('!! not found', id); continue; }
    await p.waitForTimeout(900);
    const r = await p.evaluate(id => {
      const c = [...document.querySelectorAll('.ppq')].find(x => x.dataset.id === id);
      const rc = c.getBoundingClientRect();
      const im = c.querySelector('img');
      return { x: rc.x, y: rc.y, w: rc.width, h: rc.height, iw: im ? im.naturalWidth : 0, ih: im ? im.naturalHeight : 0, src: im ? im.getAttribute('src') : '' };
    }, id);
    console.log(id, 'h=' + Math.round(r.h), 'img=' + r.iw + 'x' + r.ih, r.src);
    await p.screenshot({ path: path.join(__dirname, '_fx_' + id.replace('pp_chem_', '') + '.png'), clip: { x: Math.max(0, r.x - 6), y: Math.max(0, r.y - 6), width: Math.min(980, r.w + 12), height: Math.min(1500, r.h + 12) } });
  }
  await b.close();
})();
