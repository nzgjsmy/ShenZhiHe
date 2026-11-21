const path = require('path');
const { chromium } = require(path.join(__dirname, '..', 'site', 'node_modules', 'playwright-core'));
(async () => {
  const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1000, height: 1300 }, deviceScaleFactor: 2 });
  const errs = []; p.on('pageerror', e => errs.push(String(e)));
  await p.goto('file:///' + path.join(__dirname, '..', 'site', '神智核.html').replace(/\\/g, '/'), { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1800);
  for (const tid of ['2c', '5']) {
    await p.evaluate(t => go('#/chem/t/' + t), tid);
    await p.waitForTimeout(1200);
    const n = await p.evaluate(t => (SUB.quiz && SUB.quiz[t] ? SUB.quiz[t].length : 0), tid);
    console.log(tid, '题库题数', n);
    await p.evaluate(t => startQuiz({ mode: 'topic', id: t }), tid);
    await p.waitForTimeout(1200);
    const info = await p.evaluate(() => {
      const q = document.querySelector('.qtext, .qz-q, .question, h2');
      const opts = document.querySelectorAll('.opt, .qz-opt, .optbtn').length;
      return { head: q ? q.textContent.replace(/\s+/g, ' ').trim().slice(0, 80) : '(no q)', opts, len: document.body.innerText.length };
    });
    console.log('   ', JSON.stringify(info));
    await p.screenshot({ path: path.join(__dirname, '_q_' + tid + '.png') });
  }
  console.log('JS 错误:', errs.length ? errs.join(' / ') : 'none');
  await b.close();
})();
