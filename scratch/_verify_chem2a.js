// CDP 验证：化学 2a-q3 酚酞 pH=12 判分与题解
const { spawn } = require('child_process');
const fs = require('fs');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const htmlPath = process.argv[2];
const PORT = 9362;
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
  await send('Page.navigate', { url: 'file:///' + htmlPath.replace(/\\/g, '/') + '#/chem/quiz' });
  await sleep(5000);

  console.log('题目:', await evalJs(`(function(){
    var q=(QUIZ['2a']||[]).filter(function(x){return x.id==='2a-q3';})[0];
    if(!q) return 'missing';
    return JSON.stringify({id:q.id, ans:q.answer, correct:q.options[q.answer], opts:q.options});
  })()`));

  // 选 C（粉紅色，index 2）应当判对
  await evalJs(`(function(){
    var q=(QUIZ['2a']||[]).filter(function(x){return x.id==='2a-q3';})[0];
    QZ={i:0,pool:[q],score:0,log:[],answered:false,nextDue:null};
    renderQ();
    setTimeout(function(){ answerMc(2); }, 400);
  })()`);
  await sleep(1800);
  console.log('判分结果:', await evalJs(`(function(){
    var e=document.getElementById('expl');
    return JSON.stringify({score:(typeof QZ!=='undefined'?QZ.score:null), answered:(typeof QZ!=='undefined'?QZ.answered:null),
      expl: e? e.innerText.slice(0,90):'none'});
  })()`));
  const s = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('scratch/_vfy_chem2a.png', Buffer.from(s.data, 'base64'));

  chrome.kill();
  process.exit(0);
})();
