/* 本地实测：化学真题页的课题 chips + 题干/题解编号排版 */
const path = require('path');
const { chromium } = require(path.join(__dirname, '..', 'site', 'node_modules', 'playwright-core'));

(async () => {
  const b = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--allow-file-access-from-files'],
  });
  const p = await b.newPage({ viewport: { width: 980, height: 1400 }, deviceScaleFactor: 2 });
  await p.goto('file:///' + path.join(__dirname, '..', 'site', '神智核.html').replace(/\\/g, '/'), { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1500);
  await p.evaluate(() => { try { go('#/chem/pastpaper') } catch (e) { location.hash = '#/chem/pastpaper' } });
  await p.waitForTimeout(1500);

  const chips = await p.evaluate(() => [...document.querySelectorAll('.ppchips')[0].querySelectorAll('.ppchip')].map(x => x.textContent.trim()));
  console.log('chips:', chips.join(' | '));
  const el = await p.$('.ppchips');
  if (el) await el.screenshot({ path: path.join(__dirname, '_lay_chips.png') });

  await p.evaluate(() => ppSetTopic('1a'));
  await p.waitForTimeout(1200);
  const ids = ['pp_chem_2013_q19', 'pp_chem_2014_q15', 'pp_chem_2012_q15'];
  for (const id of ids) {
    const ok = await p.evaluate(id => {
      const c = [...document.querySelectorAll('.ppq')].find(x => x.dataset.id === id);
      if (!c) return false;
      c.scrollIntoView({ block: 'center' });
      const t = c.querySelector('.ppbtn'), ans = c.querySelector('.ppans');
      if (t && ans && !ans.classList.contains('open')) ppToggle(t);
      c.querySelectorAll('img.pplazy[data-src]').forEach(im => { im.src = im.dataset.src; im.removeAttribute('data-src'); });
      return true;
    }, id);
    if (!ok) { console.log('!! 找不到', id); continue; }
    await p.waitForTimeout(1000);
    const r = await p.evaluate(id => {
      const c = [...document.querySelectorAll('.ppq')].find(x => x.dataset.id === id);
      const rc = c.getBoundingClientRect();
      return { x: rc.x, y: rc.y, w: rc.width, h: rc.height };
    }, id);
    console.log('rect', id, Math.round(r.h));
    await p.screenshot({ path: path.join(__dirname, '_lay_' + id.replace('pp_chem_', '') + '.png'), clip: { x: Math.max(0, r.x - 6), y: Math.max(0, r.y - 6), width: Math.min(980, r.w + 12), height: Math.min(1500, r.h + 12) } });
  }
  await b.close();
})();
