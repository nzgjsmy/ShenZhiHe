const path = require('path');
const { chromium } = require(path.join(__dirname, '..', 'site', 'node_modules', 'playwright-core'));
(async () => {
  const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1000, height: 1300 } });
  await p.goto('file:///' + path.join(__dirname, '..', 'site', '神智核.html').replace(/\\/g, '/'), { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1600);
  await p.evaluate(() => go('#/chem/pastpaper'));
  await p.waitForTimeout(1200);
  const out = await p.evaluate(() => {
    const d = SUB._pastpaper.years, res = [];
    for (const [y, qs] of Object.entries(d))
      for (const q of qs)
        if (["pp_chem_2017_q25","pp_chem_2014_q30","pp_chem_2019_q13","pp_chem_2021_q10","pp_chem_2023_q33","pp_chem_PP_q36"].includes(q.id))
          res.push([q.id, q.topic, ppChLab(q.topic)]);
    return res;
  });
  out.forEach(r => console.log(r.join('  →  ')));
  await b.close();
})();
