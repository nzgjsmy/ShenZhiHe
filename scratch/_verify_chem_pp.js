// CDP 验证：化学 DSE 真题 by topic 页面
const { spawn } = require('child_process');
const fs = require('fs');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const htmlPath = process.argv[2];
const PORT = 9365;
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--remote-debugging-port=' + PORT, '--window-size=430,900', 'about:blank'], { stdio: 'ignore' });
  let target = null;
  for (let i = 0; i < 60; i++) {
    await sleep(300);
    try { const l = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json(); target = l.find(t => t.type === 'page'); if (target) break; } catch (e) {}
  }
  if (!target) { chrome.kill(); process.exit(1); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0; const pending = new Map();
  const send = (m, p) => new Promise((res, rej) => { const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method: m, params: p || {} })); });
  await new Promise(r => ws.addEventListener('open', r));
  ws.addEventListener('message', ev => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
  const evalJs = async (e) => (await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result.value;

  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 430, height: 900, deviceScaleFactor: 1, mobile: true });
  await send('Page.navigate', { url: 'file:///' + htmlPath.replace(/\\/g, '/') + '#/chem/pastpaper' });
  await sleep(5000);

  console.log('nav/hash:', await evalJs("location.hash"));
  console.log('页面文本开头:', await evalJs("document.body.innerText.slice(0,320).replace(/\\n+/g,' | ')"));
  console.log('题卡数:', await evalJs("document.querySelectorAll('.pp-card').length"));
  console.log('错误提示:', await evalJs("(function(){var t=document.body.innerText; return (t.match(/错误|異常|undefined|Cannot read/g)||[]).slice(0,5);})()"));
  // 强制加载所有懒加载配图（正常滚动时才加载）
  await evalJs("[...document.querySelectorAll('img.pplazy[data-src]')].forEach(i=>{i.src=i.dataset.src;i.removeAttribute('data-src')})");
  await sleep(2500);
  console.log('配图状态:', await evalJs("JSON.stringify([...document.querySelectorAll('img.pplazy')].map(i=>({src:(i.getAttribute('src')||'').split('/').pop(),ok:i.complete&&i.naturalWidth>0,w:i.naturalWidth})))" ));

  const s = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('scratch/_vfy_chem_pp.png', Buffer.from(s.data, 'base64'));
  chrome.kill();
  process.exit(0);
})();
