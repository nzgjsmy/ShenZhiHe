const path = require('path');
const { chromium } = require(path.join(__dirname, '..', 'site', 'node_modules', 'playwright-core'));
(async () => {
  const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1000, height: 1200 }, deviceScaleFactor: 2 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file:///' + path.join(__dirname, '..', 'site', '神智核.html').replace(/\\/g, '/'), { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1800);
  await p.evaluate(() => go('#/bio/lq'));
  await p.waitForTimeout(700);
  await p.evaluate(() => lqSetPaper(1));
  await p.waitForTimeout(700);
  const chips = await p.evaluate(() => [...document.querySelectorAll('.ppchip')].map(c => c.textContent.replace(/\s+/g,' ').trim()));
  console.log('年份 chips:', chips.join(' | '));
  await p.evaluate(() => lqSetYear('PP'));
  await p.waitForTimeout(1200);
  const info = await p.evaluate(() => {
    const cards = [...document.querySelectorAll('.lq-card')];
    return { n: cards.length, first: cards[0].textContent.replace(/\s+/g,' ').slice(0,70),
             last: cards[cards.length-1].textContent.replace(/\s+/g,' ').slice(0,70) };
  });
  console.log('PP 卡片:', info.n, '| 首:', info.first, '| 末:', info.last);
  // 打开 Q6 的参考答案
  const ok = await p.evaluate(() => {
    const cards = [...document.querySelectorAll('.lq-card')];
    const card = cards.find(c => /^\s*6\s/.test(c.textContent.replace(/\s+/g,' ').trim()));
    if (!card) return false;
    card.scrollIntoView({block:'start'});
    const btn = card.querySelector('.lq-btn'); if (btn) btn.click();
    return true;
  });
  await p.waitForTimeout(900);
  const g = await p.evaluate(() => {
    const gd = document.querySelector('.lq-guide');
    const im = document.querySelectorAll('.lq-page img, .lqcard img').length;
    return { has: !!gd, len: gd ? gd.innerText.length : 0, head: gd ? gd.innerText.slice(0,60) : '', imgs: im };
  });
  console.log('Q6 题解:', JSON.stringify(g), 'ok=', ok);
  await p.screenshot({ path: path.join(__dirname, '_pp_q6.png'), fullPage: false });
  console.log('JS 错误:', errs.length ? errs.join(' / ') : 'none');
  await b.close();
})();
