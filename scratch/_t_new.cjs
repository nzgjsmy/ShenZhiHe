const path = require('path');
const { chromium } = require(path.join(__dirname, '..', 'site', 'node_modules', 'playwright-core'));
(async () => {
  const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1100, height: 1400 }, deviceScaleFactor: 2 });
  const errs = [];
  p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file:///' + path.join(__dirname, '..', 'site', '神智核.html').replace(/\\/g, '/'), { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1800);

  // 化学首页：课题卡
  await p.evaluate(() => go('#/chem/home'));
  await p.waitForTimeout(1200);
  const cards = await p.evaluate(() => [...document.querySelectorAll('.tcard')].map(c => c.textContent.replace(/\s+/g, ' ').trim().slice(0, 46)));
  console.log('化学课题卡:', cards.length);
  cards.forEach(c => console.log('  ', c));
  await p.screenshot({ path: path.join(__dirname, '_n_home.png'), fullPage: false });

  for (const tid of ['2c', '5']) {
    await p.evaluate(t => go('#/chem/t/' + t), tid);
    await p.waitForTimeout(1400);
    const info = await p.evaluate(() => {
      const h2 = document.querySelector('.view h2') || document.querySelector('h2');
      const secs = [...document.querySelectorAll('.srow, .sech, .sec-h, h3')].slice(0, 14).map(x => x.textContent.replace(/\s+/g, ' ').trim().slice(0, 40));
      return { title: h2 ? h2.textContent.trim() : '', n: document.querySelectorAll('.pt, .point, .pcard2').length, secs, body: document.body.innerText.length };
    });
    console.log(tid, 'title=', info.title, '文本長度', info.body);
    console.log('   章节:', info.secs.join(' | ').slice(0, 300));
    await p.screenshot({ path: path.join(__dirname, '_n_' + tid + '.png'), fullPage: false });
  }
  console.log('JS 错误:', errs.length ? errs.join(' / ') : 'none');
  await b.close();
})();
