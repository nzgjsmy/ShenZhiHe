/* ---------------- 額外資訊（元素週期表等補充資料） ---------------- */
let PT_ST = null;
/* escJs：把字串安全地放進「單引號 JS 字串」內（用於 onclick="f('...')"）。
   2026-10-25 修：此函式曾被誤刪，導致 viewFiles/viewFile 拋 ReferenceError，
   點「額外資訊」的檔案卡完全沒反應。 */
function escJs(s){
  return String(s==null?"":s).replace(/\\/g,"\\\\").replace(/'/g,"\\'");
}

function extrasOf(){ return (SUB && SUB.extras) || []; }
function extraById(id){ var xs=extrasOf(); for(var i=0;i<xs.length;i++) if(xs[i].id===id) return xs[i]; return null; }

function viewExtras(){
  navOn("extras");
  if(needsContent())return;
  var xs=extrasOf();
  if(!xs.length){
    app.innerHTML="<div class=\"view\"><div class=\"thead\"><button class=\"back\" onclick=\"go(\'#/home\')\">← 返回首頁</button><h2>📎 額外資訊</h2></div>"
      +"<div class=\"emptybox\"><div class=\"e1\">📎</div><h3>這一科還沒有額外資訊</h3>"
      +"<p>把 JSON 放進 <code>f6chem/extras/"+esc(SUB.id)+"/*.json</code>，重新產生網站就會出現在這裡。</p></div></div>";
    return;
  }
  var cards=xs.map(function(x){
    return "<div class=\"extracard\" onclick=\"go(\'#/extras/"+encodeURIComponent(x.id)+"\')\">"
      +"<div class=\"exemoji\">"+(x.emoji||"📎")+"</div>"
      +"<h3>"+esc(x.title||x.id)+"</h3>"
      +"<p>"+esc(x.subtitle||x.intro||"")+"</p>"
      +"<div style=\"margin-top:12px;border-top:1px dashed var(--line);padding-top:9px;font-size:12.5px;color:var(--muted)\">"+esc(x.source||"")+"</div>"
      +"</div>";
  }).join("");
  app.innerHTML="<div class=\"view\"><div class=\"thead\"><button class=\"back\" onclick=\"go(\'#/home\')\">← 返回首頁</button><h2>📎 額外資訊</h2></div>"
    +"<div class=\"tmeta\">本科的補充資料：表格、速查、圖鑑。不計入學習進度，純查閱用。</div>"
    +"<div class=\"extras-grid\">"+cards+"</div></div>";
}

function viewExtra(id, sel){
  navOn("extras");
  if(needsContent())return;
  var x=extraById(id);
  if(!x){ go("#/extras"); return; }
  if(x.type==="ptable"){ viewPtable(x, sel); return; }
  if(x.type==="hot"){ viewHot(x); return; }
  if(x.type==="code"){ viewCodeProg(x); return; }
  if(x.type==="formulas"){ viewFormulas(x); return; }
  if(x.type==="orgnaming"){ viewOrgNaming(x); return; }
if(x.type==="files"){ viewFiles(x); return; }
  app.innerHTML="<div class=\"view\"><div class=\"thead\"><button class=\"back\" onclick=\"go(\'#/extras\')\">← 額外資訊</button><h2>"+esc(x.emoji||"📎")+" "+esc(x.title||x.id)+"</h2></div>"
    +"<div class=\"tmeta\">"+esc(x.subtitle||"")+"</div>"
    +"<div class=\"note\">這個額外資訊的型別（"+esc(x.type||"未指定")+"）還沒有專屬版面，先在下方看原始內容。</div>"
    +"<pre style=\"overflow:auto;background:var(--paper-soft);color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:14px;font-size:13px\">"+esc(JSON.stringify(x,null,1).slice(0,20000))+"</pre></div>";
}

/* ---- 公式表對照：要背 × 不用背 ----
   資料結構（extras/phys/formulas.json）：
     toback[] = 要背的公式，每組 {group, note, items[{f,n,pt,tp,sym[],from[]}]}
     given[]  = 官方公式表隨卷提供、不用背的，每組 {group, note, items[{f,n}]}
   f=公式、n=說明、sym=符號表、pt=對應知識點 id、tp=課題 id、from=由表上哪幾條推導 */
var FM_ST={tab:"back",q:"",group:""};
var CUR_FM=null;
function fmRows(x, tab){
  var rows=[];
  ((tab==="back"?x.toback:x.given)||[]).forEach(function(g){
    (g.items||[]).forEach(function(it){ rows.push({g:g,it:it}); });
  });
  return rows;
}
function fmTopicName(tid){
  if(!tid) return "";
  var t=TMAP[tid];
  return t?t.title:"";
}
function fmFiltered(x){
  var q=(FM_ST.q||"").trim().toLowerCase();
  var gsel=FM_ST.group||"";
  return fmRows(x,FM_ST.tab).filter(function(r){
    if(gsel && r.g.group!==gsel) return false;
    if(!q) return true;
    var it=r.it;
    if(String(it.f||"").toLowerCase().indexOf(q)>=0) return true;
    if(String(it.n||"").toLowerCase().indexOf(q)>=0) return true;
    if((it.sym||[]).some(function(s){ return String(s).toLowerCase().indexOf(q)>=0; })) return true;
    if(fmTopicName(it.tp).toLowerCase().indexOf(q)>=0) return true;
    return false;
  });
}
function fmSetTab(t){ FM_ST.tab=t; FM_ST.group=""; viewFormulas(CUR_FM); }
function fmSetGroup(g){ FM_ST.group=(FM_ST.group===g)?"":g; viewFormulas(CUR_FM); }
function fmSetQ(v){
  FM_ST.q=v;
  // 只重繪清單，避免輸入框失焦（中文輸入法尤其明顯）
  var box=document.getElementById("fmlist");
  if(box) box.innerHTML=fmListHTML(CUR_FM);
}
function fmCard(it){
  // 符號表逐條完整輸出（曾出現把值截斷成 "p= =" 的寫法，這裡一律整串處理後顯示）
  // 走 subify() 讓 c_rms、N_A、F_x 顯示成真正的下標，而不是字面下劃線
  var syms=(it.sym||[]).map(function(s){ return "<li>"+subify(esc(s))+"</li>"; }).join("");
  var badges="";
  if(it.n && it.n.indexOf("🔴")>=0) badges+='<span class="fbadge none">🔴 表上沒有</span>';
  if(it.from && it.from.length) badges+='<span class="fbadge deriv">由 '+esc(it.from.join(" + "))+' 推出</span>';
  var tn=fmTopicName(it.tp);
  // 每張卡用「所屬課題」的顏色（跟首頁課題卡、知識圖譜一致），
  // 這是本站既有的配色體系：colorOf(topicId)，不是隨機色。
  var col=(it.tp && COLORS[it.tp]) ? COLORS[it.tp] : (SUB?SUB.color:"#0f766e");
  var jump=(it.pt && PMAP[it.pt])
    ? '<span class="fjump" style="--tc:'+col+'" onclick="jumpPoint(\''+esc(it.pt)+'\')">筆記 →</span>'
    : "";
  var topicChip=tn
    ? '<span class="ftopic" style="--tc:'+col+'">'+(it.tp&&COLORS[it.tp]?'<i></i>':'')+esc(tn)+'</span>'
    : "";
  return '<div class="fcard" style="--tc:'+col+'">'
    +'<div class="ff">'+subify(esc(it.f||""))+'</div>'
    +(it.n?'<div class="fn">'+subify(esc(it.n))+'</div>':"")
    +(syms?'<ul class="fsym">'+syms+'</ul>':"")
    +((badges||topicChip||jump)?'<div class="ffoot">'+badges+topicChip+jump+'</div>':"")
    +'</div>';
}
/* 分組 emoji：讓每個區塊一眼認出，比純文字標題舒服 */
function fmGroupEmoji(name){
  var M={"熱學":"🌡️","力學":"🧲","波動與光學":"🌈","電磁學":"⚡","放射性與核物理":"☢️",
         "原子世界（E2 選修）":"⚛️","能源應用（E3 選修）":"🔋",
         "數據（常數）":"📐","數學":"➗","直線運動（勻加速）":"🏃",
         "天文學和航天科學":"🪐","醫學物理學（選修）":"🩺"};
  if(M[name]) return M[name];
  var s=String(name);
  if(s.indexOf("·")>=0){ // 「A · 熱學」這種帶字母的官方表分組
    var tail=s.split("·").pop().trim();
    if(M[tail]) return M[tail];
  }
  return "📎";
}
function fmListHTML(x){
  if(!x) return "";
  var shown=fmFiltered(x);
  if(!shown.length) return '<div class="fempty">沒有符合的公式，換個關鍵字試試。</div>';
  // 依原分組順序輸出，空組自動略過
  var order=[], map={}, gmap={};
  shown.forEach(function(r){
    var k=r.g.group||"其他";
    if(!map[k]){ map[k]=[]; order.push(k); }
    map[k].push(r.it);
    gmap[k]=r.g;
  });
  var isBack=(FM_ST.tab==="back");
  return order.map(function(k){
    var g=gmap[k];
    var note=(g&&g.note)?'<span class="gnote">'+esc(g.note)+'</span>':"";
    // 分組標題色＝該組第一條公式所屬課題的顏色，讓每個單元一眼可辨
    var first=map[k][0]||{};
    var gcol=(first.tp && COLORS[first.tp]) ? COLORS[first.tp] : "#5c4a52";
    /* 同一課題的公式聚在一起：依原資料順序做穩定分組，
       讓「氣體」的 6 條連續排列，而不是散落在整組之中。
       有 tp 的才分組；given 分頁沒有 tp，維持原順序。 */
    var seq=[], tmap={};
    map[k].forEach(function(it){
      var tid=it.tp||"";
      if(!tmap[tid]){ tmap[tid]=[]; seq.push(tid); }
      tmap[tid].push(it);
    });
    var body=seq.map(function(tid){
      var arr=tmap[tid];
      var col=(tid && COLORS[tid]) ? COLORS[tid] : gcol;
      // 該組涉及多個課題時，每個課題前加一條小標（單一課題就不加，避免冗餘）
      var head=(seq.length>1 && tid)
        ? '<div class="ftopicrow" style="--tc:'+col+'"><span class="ftopic" style="--tc:'+col+'"><i></i>'+esc(fmTopicName(tid))+'</span><span class="ftopicn">'+arr.length+' 條</span></div>'
        : "";
      return head+'<div class="fgrid">'+arr.map(fmCard).join("")+'</div>';
    }).join("");
    return '<div class="fgroup" style="--tc:'+gcol+'">'
        +'<span class="ge">'+fmGroupEmoji(k)+'</span>'
        +'<span class="gt">'+esc(k)+'</span>'
        +'<span class="gn">'+map[k].length+' 條</span>'
        +'<span class="gline"></span>'
        +note
      +'</div>'
      +body;
  }).join("")+'<div class="hcount">目前顯示 <b>'+shown.length+'</b> 條'+(isBack?"要背":"表上提供")+'的公式</div>';
}
function viewFormulas(x){
  navOn("extras");
  if(needsContent())return;
  CUR_FM=x;
  var backN=fmRows(x,"back").length, givenN=fmRows(x,"given").length;
  var noN=fmRows(x,"back").filter(function(r){ return r.it.n && r.it.n.indexOf("🔴")>=0; }).length;
  var tpN={};
  fmRows(x,"back").forEach(function(r){ if(r.it.tp) tpN[r.it.tp]=1; });
  var isBack=(FM_ST.tab==="back");
  var hero='<div class="fmhero">'
    +'<div class="hrow"><span class="dot"></span><h2>'+(x.emoji||"🧮")+' '+(isBack?"要背":"不用背")+' · '+(isBack?backN:givenN)+' 條</h2>'
    +'<span class="pill">'+(isBack?"考場自己記":"隨卷發放")+'</span></div>'
    +'<p class="lead">'+(isBack
      ? '這些不在考試隨卷發放的公式表上，考場上沒有，必須自己記。每張卡的「<b>筆記 →</b>」可直接跳到對應知識點。'
      : '這些是香港考評局公式表<b>隨卷提供</b>的，不用死背；但要知道它長什麼樣、在哪一頁找得到。')+'</p>'
    +'</div>';
  var stat='<div class="fstat">'
    +'<div class="fc"><div class="n">'+backN+'</div><div class="l">要背的公式</div></div>'
    +'<div class="fc"><div class="n" style="color:#4a9c7a">'+givenN+'</div><div class="l">表上提供 · 不用背</div></div>'
    +'<div class="fc"><div class="n" style="color:#c2415b">'+noN+'</div><div class="l">🔴 表上完全沒有</div></div>'
    +'<div class="fc"><div class="n" style="color:#7a6a8a">'+Object.keys(tpN).length+'</div><div class="l">涉及課題</div></div>'
    +'</div>';
  var tabs='<div class="ftabs">'
    +'<button class="ftab'+(isBack?" on":"")+'" onclick="fmSetTab(\'back\')">✍️ 要背<span class="c">'+backN+'</span></button>'
    +'<button class="ftab given'+(!isBack?" on":"")+'" onclick="fmSetTab(\'given\')">📋 不用背<span class="c">'+givenN+'</span></button>'
    +'</div>';
  // 分組快捷（只在該分頁有多組時列出）
  var gs=[], seen={};
  fmRows(x,FM_ST.tab).forEach(function(r){
    var k=r.g.group||"其他";
    if(!seen[k]){ seen[k]=1; gs.push(k); }
  });
  var chips=(gs.length>1)
    ? '<div class="hchips"><button class="hchip'+(FM_ST.group?"":" on")+'" onclick="fmSetGroup(\'\')">全部</button>'
      +gs.map(function(k){
        return '<button class="hchip'+(FM_ST.group===k?" on":"")+'" onclick="fmSetGroup(\''+esc(k.replace(/'/g,"\\'"))+'\')">'+fmGroupEmoji(k)+' '+esc(k)+'</button>';
      }).join("")+'</div>'
    : "";
  app.innerHTML='<div class="view">'
    +'<div class="thead"><button class="back" onclick="go(\'#/extras\')">← 額外資訊</button>'
    +'<h2>'+esc(x.title||"公式表")+'</h2></div>'
    +hero
    +stat
    +tabs
    +'<div class="hfilter"><input type="search" placeholder="🔍 搜尋公式、符號或課題…" autocomplete="off" value="'+esc(FM_ST.q||"")+'" oninput="fmSetQ(this.value)"></div>'
    +chips
    +'<div id="fmlist">'+fmListHTML(x)+'</div>'
    +'<div class="tmeta" style="margin-top:16px">'+esc(x.subtitle||"")+(x.source?" ｜ 來源："+esc(x.source):"")+'</div>'
    +'</div>';
}

/* ---- 高頻考點報告 ---- */
var HOT_ST={topic:"",q:""};
var CUR_HOT=null;
function hotTopicColor(tid){
  var C={"1a":"#7c3aed","1b":"#0ea5e9","1c":"#f59e0b","2a":"#0f766e","2b":"#ef4444","3a":"#22c55e","3b":"#14b8a6","3c":"#f97316","4a":"#8b5cf6","4b":"#ec4899","6":"#64748b","8":"#a855f7"};
  return C[tid]||"#64748b";
}
function hotLvTag(lv){
  if(lv>=3) return '<span class="hlv3">🔥 必考</span>';
  if(lv===2) return '<span class="hlv2">⭐ 常考</span>';
  return '<span class="hlv1">· 考過</span>';
}
/* ---- 有機化學命名規則（官能基優先順序 × 前綴後綴） ----
   資料結構（extras/chem/orgnaming.json）：
     priority[] = 官能基優先順序 {rank,grp,suffix,prefix,series,pt,tp,note}
     subst[]    = 只能當字首的基團 {grp,prefix,note,pt,tp}
     rules[]    = 命名步驟 {t,d,pt,tp}（d 內含 <b> 標記，需原樣輸出）
     chain[]    = 碳數對照 {n,cn,en}
     examples[] = 命名實例 {name,en,why} */
function onJump(pt, label){
  if(!pt || !PMAP[pt]) return "";
  return '<a onclick="jumpPoint(\''+esc(pt)+'\')">'+esc(label||"筆記")+' →</a>';
}
/* 區塊標題：emoji + 標題 + 小註，跟公式表同一套視覺語言 */
function onSecHead(emoji, title, sub){
  return '<div class="fgroup"><span class="ge">'+emoji+'</span><span class="gt">'+esc(title)+'</span>'
    +(sub?'<span class="gline"></span><span class="gnote">'+esc(sub)+'</span>':'<span class="gline"></span>')
    +'</div>';
}
function viewOrgNaming(x){
  navOn("extras");
  if(needsContent())return;
  var pri=(x.priority||[]).map(function(r){
    return '<tr>'
      +'<td class="rk">'+esc(r.rank)+'</td>'
      +'<td class="grp">'+esc(r.grp)+'</td>'
      +'<td class="sfx">'+esc(r.suffix)+'</td>'
      +'<td class="pfx">'+esc(r.prefix)+'</td>'
      +'<td class="nt">'+esc(r.note||"")+(r.pt&&PMAP[r.pt]?'<br>'+onJump(r.pt):"")+'</td>'
      +'</tr>';
  }).join("");
  var priTbl=pri
    ? onSecHead("🏆","官能基優先順序","rank 越小越優先：最優先的當字尾，其餘全部降為字首")
      +'<div class="onwrap"><table class="onpri"><thead><tr><th>優先</th><th>官能基</th><th>當字尾</th><th>當字首</th><th>說明</th></tr></thead><tbody>'+pri+'</tbody></table></div>'
    : "";
  var subst=(x.subst||[]).map(function(s){
    return '<tr>'
      +'<td class="grp">'+esc(s.grp)+'</td>'
      +'<td class="pfx">'+esc(s.prefix)+'</td>'
      +'<td class="nt">'+esc(s.note||"")+(s.pt&&PMAP[s.pt]?'<br>'+onJump(s.pt):"")+'</td>'
      +'</tr>';
  }).join("");
  var substTbl=subst
    ? onSecHead("🏷️","只能當字首的基團","鹵素、烷基、硝基等沒有字尾形式")
      +'<div class="onwrap"><table class="onpri"><thead><tr><th>基團</th><th>字首寫法</th><th>說明</th></tr></thead><tbody>'+subst+'</tbody></table></div>'
    : "";
  var rules=(x.rules||[]).map(function(r){
    return '<div class="onstep">'
      +'<h4>'+esc(r.t||"")+'</h4>'
      // r.d 由資料作者寫入 <b> 標記，這裡刻意不 esc，只輸出原樣
      +'<p>'+(r.d||"")+'</p>'
      +((r.pt&&PMAP[r.pt])?'<div class="lk">'+onJump(r.pt)+'</div>':"")
      +'</div>';
  }).join("");
  var rulesBox=rules?onSecHead("📝","命名步驟","照這個順序一步步做就不會亂")+rules:"";
  var chain=(x.chain||[]).map(function(c){
    return '<div class="c"><b>'+esc(c.cn)+'</b><span>'+esc(c.en||"")+'</span></div>';
  }).join("");
  var chainBox=chain
    ? onSecHead("🔢","碳數對照","1–10 個碳的中英字首")+'<div class="onchain">'+chain+'</div>'
    : "";
  var exs=(x.examples||[]).map(function(e){
    return '<div class="onex">'
      +'<span class="nm">'+esc(e.name||"")+'</span><span class="en">'+esc(e.en||"")+'</span>'
      +(e.why?'<div class="why">'+esc(e.why)+'</div>':"")
      +'</div>';
  }).join("");
  var exBox=exs?onSecHead("✨","命名實例","每條都標了為什麼這樣命名")+exs:"";
  var hero='<div class="onhero">'
    +'<div class="hrow"><span class="dot"></span><h2>'+(x.emoji||"🧬")+' 有機命名 · 一次搞懂</h2></div>'
    +'<p class="lead">先看<b>誰當字尾</b>（優先順序最高的那個），其餘官能基全部降為字首，再照<b>命名步驟</b>走一遍。每條都附了對應筆記的跳轉。</p>'
    +'</div>';
  app.innerHTML='<div class="view">'
    +'<div class="thead"><button class="back" onclick="go(\'#/extras\')">← 額外資訊</button>'
    +'<h2>'+esc(x.title||"命名規則")+'</h2></div>'
    +hero
    +priTbl+substTbl+rulesBox+chainBox+exBox
    +'<div class="tmeta" style="margin-top:16px">'+esc(x.subtitle||"")+(x.source?" ｜ 來源："+esc(x.source):"")+'</div>'
    +'</div>';
}

function hotItemRow(it){
  var kws=(it.kw||[]).slice(0,6).map(function(k){return '<span class="hkw">'+esc(k)+'</span>';}).join("");
  var yr=(it.years||[]).join(" / ");
  var samp="";
  if(it.samples&&it.samples.length){
    samp='<details class="hsamp"><summary>看 '+it.samples.length+' 條題目實例</summary><ul>'
      +it.samples.map(function(s){return '<li><b>'+esc(s.ref||"")+'</b>：'+esc(s.focus||"")+'</li>';}).join("")
      +'</ul></details>';
  }
  return '<tr>'
    +'<td>'+hotLvTag(it.level)+'</td>'
    +'<td><span class="htag" style="background:'+hotTopicColor(it.topic)+'">'+esc(it.topic)+'</span> '+esc(it.tname||"")+'<div class="hsec">'+esc(it.sec||"")+'</div></td>'
    +'<td><a href="#/t/'+esc(it.topic)+'">'+esc(it.title)+'</a>'+(it.page?'<span class="hpg">P'+esc(it.page)+'</span>':"")+'</td>'
    +'<td class="hyr">'+esc(yr)+'</td>'
    +'<td>'+(kws||'<span class="hdim">—</span>')+samp+'</td>'
    +'</tr>';
}
function hotFiltered(x){
  var rows=[];
  (x.groups||[]).forEach(function(g){ (g.items||[]).forEach(function(it){ rows.push(it); }); });
  var t=HOT_ST.topic, q=(HOT_ST.q||"").trim().toLowerCase();
  return rows.filter(function(it){
    if(t && it.topic!==t) return false;
    if(!q) return true;
    if(String(it.title).toLowerCase().indexOf(q)>=0) return true;
    if(String(it.tname||"").toLowerCase().indexOf(q)>=0) return true;
    if(String(it.sec||"").toLowerCase().indexOf(q)>=0) return true;
    return (it.kw||[]).some(function(k){return String(k).toLowerCase().indexOf(q)>=0;});
  });
}
function hotSetTopic(t){ HOT_ST.topic=(HOT_ST.topic===t)?"":t; viewHot(CUR_HOT); }
function hotSetQ(v){ HOT_ST.q=v; viewHot(CUR_HOT); }
function viewHot(x){
  navOn("extras");
  if(needsContent())return;
  CUR_HOT=x;
  var s=x.summary||{};
  var shown=hotFiltered(x);
  var chips='<button class="hchip'+(HOT_ST.topic?"":" on")+'" onclick="hotSetTopic(\'\')">全部</button>'
    +(x.topics||[]).map(function(t){
      return '<button class="hchip'+(HOT_ST.topic===t.id?" on":"")+'" style="--hc:'+hotTopicColor(t.id)+'" onclick="hotSetTopic(\''+esc(t.id)+'\')">'
        +esc(t.id)+' '+esc(t.name)+' <b>'+t.hits+'</b></button>';
    }).join("");
  var cards=[
    '<div class="hcard"><div class="n">'+(s.points||0)+'</div><div class="l">被考的知識點</div></div>',
    '<div class="hcard"><div class="n">'+(s.hits||0)+'</div><div class="l">命中次數</div></div>',
    '<div class="hcard"><div class="n" style="color:#dc2626">'+(s.lv3||0)+'</div><div class="l">🔥 必考（5年+）</div></div>',
    '<div class="hcard"><div class="n" style="color:#ea580c">'+(s.lv2||0)+'</div><div class="l">⭐ 常考（2-4年）</div></div>',
    '<div class="hcard"><div class="n">'+(s.years?s.years.length:0)+'</div><div class="l">參考年份</div></div>'
  ].join("");
  var yrTbl='<table class="htable"><thead><tr><th>年份</th><th>命中</th><th>涉及課題</th></tr></thead><tbody>'
    +(x.years||[]).map(function(y){
      return '<tr><td><b>'+y.year+'</b></td><td>'+y.hits+'</td><td>'
        +(y.topics||[]).map(function(t){return '<span class="htag" style="background:'+hotTopicColor(t)+'">'+esc(t)+'</span>';}).join("")
        +'</td></tr>';
    }).join("")+'</tbody></table>';
  var kwTbl='<div class="hkwcloud">'+(x.keywords||[]).slice(0,50).map(function(k){
    return '<span class="hkw" style="font-size:'+(12+Math.min(4,k.count))+'px">'+esc(k.text)+' <small>'+k.count+'</small></span>';
  }).join("")+'</div>';
  app.innerHTML="<div class=\"view\">"
    +"<div class=\"thead\"><button class=\"back\" onclick=\"go(\'#/extras\')\">← 額外資訊</button>"
    +"<h2>"+(x.emoji||"🔥")+" "+esc(x.title||"高頻考點")+"</h2></div>"
    +"<div class=\"tmeta\">"+esc(x.subtitle||"")+(x.source?" ｜ 來源："+esc(x.source):"")+"</div>"
    +(x.intro?'<div class="note">'+esc(x.intro)+'</div>':"")
    +'<div class="hcards">'+cards+'</div>'
    +'<div class="hfilter"><input type="search" placeholder="搜尋知識點或得分字眼…" value="'+esc(HOT_ST.q||"")+'" oninput="hotSetQ(this.value)"></div>'
    +'<div class="hchips">'+chips+'</div>'
    +'<div class="hcount">目前顯示 <b>'+shown.length+'</b> 個知識點'+(HOT_ST.topic?'（課題 '+esc(HOT_ST.topic)+'）':'')+'</div>'
    +'<table class="htable"><thead><tr><th>熱度</th><th>課題</th><th>知識點</th><th>考過年份</th><th>得分字眼</th></tr></thead><tbody>'
    +(shown.length?shown.map(hotItemRow).join("")
      :'<tr><td colspan="5" class="hdim">沒有符合的知識點</td></tr>')
    +'</tbody></table>'
    +'<h3 class="hsec-h">各年被考課題覆蓋</h3>'+yrTbl
    +'<h3 class="hsec-h">得分字眼總覽</h3><p class="hdim" style="font-size:13px;margin:4px 0 8px">評卷參考常見的採分表述，答題時務必寫出來；括號是它出現在幾個知識點裡。</p>'+kwTbl
    +(x.note?'<div class="note" style="margin-top:18px">'+esc(x.note)+'</div>':"")
    +"</div>";
}

/* ---- 元素週期表 ---- */
function ptInit(x){
  if(!PT_ST || PT_ST.id!==x.id) PT_ST={id:x.id,cats:{},q:"",sel:null};
  (x.categories||[]).forEach(function(c){ if(PT_ST.cats[c.id]===undefined) PT_ST.cats[c.id]=true; });
}
function viewPtable(x, sel){
  ptInit(x);
  if(sel) PT_ST.sel=parseInt(sel,10)||null;
  app.innerHTML="<div class=\"view\">"
    +"<div class=\"thead\"><button class=\"back\" onclick=\"go(\'#/extras\')\">← 額外資訊</button>"
    +"<h2>"+(x.emoji||"⚛️")+" "+esc(x.title||"元素週期表")+"</h2></div>"
    +"<div class=\"tmeta\">"+esc(x.subtitle||"")+(x.source?" ｜ 來源："+esc(x.source):"")+"</div>"
    +"<div class=\"ptwrap\">"
    +"<div class=\"ptsearch\"><input id=\"ptq\" type=\"search\" placeholder=\"搜尋：氫 / H / hydrogen / 1\" autocomplete=\"off\" value=\""+esc(PT_ST.q)+"\" oninput=\"ptSearch(this.value)\"><button class=\"back\" onclick=\"ptClear()\">清除</button></div>"
    +"<div class=\"ptlegend\" id=\"ptlegend\"></div>"
    +"<div class=\"ptscroll\"><div class=\"ptgrid\" id=\"ptgrid\"></div></div>"
    +"<div style=\"font-size:12.5px;color:var(--muted);margin-top:8px\">手機上表格可左右滑動；點格子看詳細資料。"+(x.massNote?" "+esc(x.massNote):"")+"</div>"
    +"</div>"
    +"<div id=\"ptdetail\"></div>"
    +"</div>";
  renderLegend(x); renderGrid(x); renderDetail(x);
}
function ptMatch(e){
  if(!PT_ST.cats[e.cat]) return false;
  var q=(PT_ST.q||"").trim().toLowerCase();
  if(!q) return true;
  return e.sym.toLowerCase().indexOf(q)>=0 || e.cn.indexOf(q)>=0 || e.en.toLowerCase().indexOf(q)>=0 || String(e.z)===q;
}
function ptCell(e,CATCOL){
  var on=(PT_ST.sel===e.z)?" on":"";
  var dim=ptMatch(e)?"":" dim";
  var bg=CATCOL[e.cat]||"#eeeeee";
  var nonh=(e.hkeaa===false)?" nonh":"";
  return "<div class=\"ptcell"+on+dim+nonh+"\" data-z=\""+e.z+"\" style=\"background:"+bg+"\" onclick=\"ptPick("+e.z+")\">"
    +"<div class=\"z\">"+e.z+"</div>"
    +"<div class=\"sym\">"+esc(e.sym)+"</div>"
    +"<div class=\"cn\">"+esc(e.cn)+"</div>"
    +"<div class=\"ms\">"+esc(e.mass)+"</div>"
    +"<div class=\"st\">"+esc(e.state)+"</div>"
    +"</div>";
}
function renderGrid(x){
  var el=document.getElementById("ptgrid"); if(!el)return;
  var map={}; (x.elements||[]).forEach(function(e){ map[e.row+"-"+e.col]=e; });
  var CATCOL={}; (x.categories||[]).forEach(function(c){ CATCOL[c.id]=c.color; });
  var s="";
  for(var r=1;r<=7;r++){
    for(var c=1;c<=18;c++){
      var e=map[r+"-"+c];
      s += e ? ptCell(e,CATCOL) : "<div></div>";
    }
  }
  s+="<div class=\"ptgap\"></div>";
  for(var r2=8;r2<=9;r2++){
    s+="<div class=\"ptrowlabel\" style=\"grid-column:1/3\">"+(r2===8?"鑭系":"錒系")+"</div>";
    for(var c2=3;c2<=17;c2++){
      var e2=map[r2+"-"+c2];
      s += e2 ? ptCell(e2,CATCOL) : "<div></div>";
    }
    s+="<div></div>";
  }
  el.innerHTML=s;
}
function renderLegend(x){
  var el=document.getElementById("ptlegend"); if(!el)return;
  el.innerHTML=(x.categories||[]).map(function(c){
    return "<span class=\""+((PT_ST.cats[c.id]||false)?"":"off")+"\" onclick=\"ptToggle(\'"+c.id+"\')\"><i style=\"background:"+c.color+"\"></i>"+esc(c.name)+"</span>";
  }).join("")+"<span style=\"border-style:dashed\" onclick=\"ptAllCats()\">全部顯示</span>";
}
function renderDetail(x){
  var el=document.getElementById("ptdetail"); if(!el)return;
  var cats={}; (x.categories||[]).forEach(function(c){ cats[c.id]=c; });
  var e=null;
  (x.elements||[]).forEach(function(v){ if(v.z===PT_ST.sel) e=v; });
  if(!e){ el.innerHTML="<div class=\"ptempty\">"+(x.intro||"點表格裡的元素看詳細資料。")+"</div>"; return; }
  var c=cats[e.cat]||{name:e.cat,color:"#eeeeee"};
  var posTxt = e.row<=7 ? ("第 "+e.period+" 週期"+(e.group?(" · 第 "+e.group+" 族"):"")) : (e.row===8?"鑭系元素":"錒系元素");
  el.innerHTML="<div class=\"ptdetail\"><div class=\"pth\">"
    +"<div class=\"box\" style=\"background:"+c.color+"\"><span>"+e.z+"</span><b>"+esc(e.sym)+"</b></div>"
    +"<div><h3>"+esc(e.cn)+" <span style=\"font-size:15px;color:var(--muted);font-weight:400\">"+esc(e.en)+"</span></h3>"
    +"<div style=\"font-size:13.5px;color:var(--muted)\">"+esc(c.name)+" · "+esc(posTxt)+"</div></div>"
    +"<button class=\"qbtn\" style=\"margin-left:auto\" onclick=\"ptFindNotes("+e.z+")\">🔍 在筆記裡找這個元素</button>"
    +"</div>"
    +"<div class=\"kv\">"
    +"<div><b>原子序</b><span>"+e.z+"</span></div>"
    +"<div><b>相對原子質量</b><span>"+esc(e.mass)+"</span></div>"
    +"<div><b>常溫狀態</b><span>"+esc(e.state==="氣"?"氣體":(e.state==="液"?"液體":"固體"))+"</span></div>"
    +"<div><b>類別</b><span>"+esc(c.name)+"</span></div>"
    +"</div>"
    +((e.hkeaa===false)?"<div style=\"font-size:12.5px;color:var(--amber);margin-top:8px\">⚠️ 這個元素不在香港考評局週期表內，相對原子質量為現代公認值，僅供參考。</div>":"")
    +(x.note?"<div style=\"font-size:13px;color:var(--muted);margin-top:10px\">"+esc(x.note)+"</div>":"")+"</div>";
}
function ptPick(z){
  PT_ST.sel=(PT_ST.sel===z?null:z);
  var x=extraById(PT_ST.id); renderGrid(x); renderDetail(x);
  if(PT_ST.sel) go("#/extras/"+PT_ST.id+"@"+PT_ST.sel);
}
/* ---- 程式碼速查（計算機程式等） ---- */
var CUR_PROG = null;
function viewCodeProg(x){
  navOn("extras");
  if(needsContent())return;
  CUR_PROG = x;
  var gs = x.groups || [];
  var cards = gs.map(function(g,i){ return progCardHTML(g,i); }).join("");
  var io = (x.io||[]).map(function(r){
    return '<div class="pkvrow"><b>'+esc(r.k||"")+'</b><span>'+esc(r.v||"")+'</span></div>';
  }).join("");
  var bytes = (x.bytes_table||[]).map(function(r){
    return '<tr><td><b>'+esc(r.area||"")+'</b></td><td>'+esc(r.what||"")+'</td><td>'+esc(r.bytes||"")+'</td></tr>';
  }).join("");
  app.innerHTML = '<div class="view">'
    +'<div class="thead"><button class="back" onclick="go(\'#/extras\')">← 額外資訊</button>'
    +'<h2>'+(x.emoji||"🖩")+' '+esc(x.title||"程式碼")+'</h2></div>'
    +'<div class="tmeta">'+esc(x.subtitle||"")+(x.source?" ｜ 來源："+esc(x.source):"")+'</div>'
    +(x.note?'<div class="note">'+esc(x.note)+'</div>':"")
    +(io?'<div class="progkv">'+io+'</div>':"")
    +cards
    +(x.quick?'<h3 class="hsec-h">速查條（可抄到機背）</h3><pre class="progquick">'+esc(x.quick)+'</pre>':"")
    +(bytes?'<h3 class="hsec-h">字節佔用</h3><table class="htable"><thead><tr><th>區</th><th>內容</th><th>字節</th></tr></thead><tbody>'+bytes+'</tbody></table>':"")
    +'</div>';
}
function progCardHTML(g,i){
  var io = (g.io||[]).map(function(r){
    return '<div class="pkvrow"><b>'+esc(r.k||"")+'</b><span>'+esc(r.v||"")+'</span></div>';
  }).join("");
  var pit = (g.pitfalls||[]).map(function(p){
    return '<li>'+esc(p)+'</li>';
  }).join("");
  return '<div class="progcard" id="prog'+i+'">'
    +'<div class="proghead">'
    +'<span class="progarea">'+esc(g.area||("P"+(i+1)))+'</span>'
    +'<h3>'+esc(g.title||"")+'</h3>'
    +(g.bytes?'<span class="progbytes">'+esc(g.bytes)+' 字節</span>':"")
    +'</div>'
    +(g.desc?'<div class="progdesc">'+esc(g.desc)+'</div>':"")
    +'<div class="progcodewrap">'
    +'<button class="pcopy" id="pcopy'+i+'" onclick="copyProg('+i+')">📋 複製程式碼</button>'
    +'<pre class="progcode">'+esc(g.code||"")+'</pre>'
    +'</div>'
    +(io?'<div class="progio">'+io+'</div>':"")
    +(g.verify?'<div class="progverify"><b>驗收：</b>'+esc(g.verify)+'</div>':"")
    +(pit?'<div class="progpit"><b>注意</b><ul>'+pit+'</ul></div>':"")
    +'</div>';
}
function copyProg(i){
  if(!CUR_PROG)return;
  var g=(CUR_PROG.groups||[])[i];
  if(!g)return;
  var txt=g.code||"";
  var btn=document.getElementById("pcopy"+i);
  var flash=function(ok){
    if(!btn)return;
    btn.textContent = ok ? "✅ 已複製" : "⚠️ 長按選取";
    setTimeout(function(){ btn.textContent="📋 複製程式碼"; }, 1800);
  };
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(function(){flash(true);}, function(){flash(false);});
  }else{
    flash(false);
  }
}

function ptSearch(v){ PT_ST.q=v||""; var x=extraById(PT_ST.id); renderGrid(x); renderDetail(x); }
function ptClear(){ PT_ST.q=""; var i=document.getElementById("ptq"); if(i)i.value=""; var x=extraById(PT_ST.id); renderGrid(x); renderDetail(x); }
function ptToggle(cid){ PT_ST.cats[cid]=!PT_ST.cats[cid]; var x=extraById(PT_ST.id); renderLegend(x); renderGrid(x); }
function ptAllCats(){ var x=extraById(PT_ST.id); (x.categories||[]).forEach(function(c){ PT_ST.cats[c.id]=true; }); renderLegend(x); renderGrid(x); }
function ptFindNotes(z){
  var x=extraById(PT_ST.id); var e=null;
  (x.elements||[]).forEach(function(v){ if(v.z===z) e=v; });
  if(!e)return;
  go("#/search@"+encodeURIComponent(e.cn));
}


/* ---------------- 額外資訊：檔案列表（html/xlsx/pdf 等補充檔案） ---------------- */
function viewFiles(x){
  navOn("extras");
  var cards=x.files||[];
  var html='<div class="view"><div class="thead"><button class="back" onclick="go(\'#/extras\')">← 額外資訊</button><h2>'+esc(x.emoji||"📎")+' '+esc(x.title||x.id)+'</h2></div>';
  html+='<div class="tmeta">'+esc(x.subtitle||"")+'</div>';
  if(x.intro){ html+='<div class="note" style="margin:12px 0;padding:14px;border-radius:12px;line-height:1.6;white-space:pre-wrap;">'+esc(x.intro)+'</div>'; }
  html+='<div class="extras-grid">';
  cards.forEach(function(f){
    var icon = f.type==="html"?'🌐':(f.type==="xlsx"?'📊':(f.type==="pdf"?'📄':'📎'));
    var sizeText = f.size ? ' ('+(f.size<1024?f.size+' B':f.size<1024*1024?(f.size/1024).toFixed(1)+' KB':(f.size/1024/1024).toFixed(2)+' MB)') : '';
    html+='<div class="extracard" style="cursor:default">';
    html+='<div class="exemoji">'+icon+'</div>';
    html+='<h3 style="margin:8px 0 4px;">'+esc(f.title||f.name)+'</h3>';
    html+='<p style="margin:6px 0 8px;font-size:14px;color:var(--text-soft);">'+esc(f.desc||"")+sizeText+'</p>';
    html+='<div style="margin-top:12px;border-top:1px dashed var(--line);padding-top:8px;display:flex;gap:8px;">';
    if(f.type==="html"){
      html+='<button onclick="viewFile(\''+escJs(f.name)+'\', \''+escJs(x.id)+'\')" style="flex:1;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--paper-soft);color:var(--ink);cursor:pointer;font-size:14px;">🔍 在頁中查看</button>';
    }
    html+='<a href="files/'+encodeURIComponent(f.name)+'" download style="flex:1;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--paper-soft);color:var(--accent);text-decoration:none;text-align:center;font-size:14px;">⬇️ 下載</a>';
    html+='</div></div>';
  });
  html+='</div></div>';
  app.innerHTML=html;
}

function viewFile(fileName, extraId){
  var x=extraById(extraId);
  if(!x){ go("#/extras"); return; }
  var f=(x.files||[]).find(function(it){ return it.name===fileName; });
  if(!f){ go("#/extras/"+extraId); return; }
  var ext=fileName.slice(fileName.lastIndexOf('.')).toLowerCase();
  navOn("extras");
  var html='<div class="view"><div class="thead"><button class="back" onclick="viewFilesData(\''+escJs(extraId)+'\')">← '+esc(x.title||x.id)+'</button><h2>'+esc(f.title||fileName)+'</h2></div>';
  if(ext===".html"){
    html+='<div class="tmeta">'+esc(f.desc||"")+'</div>';
    html+='<iframe src="files/'+encodeURIComponent(fileName)+'" style="width:100%;height:70vh;border:none;border-radius:12px;background:#fff;"></iframe>';
  } else {
    html+='<div class="note">此檔案類型（'+ext+'）無法直接在頁中預覽，請下載後查看。</div>';
    html+='<div style="margin-top:20px;text-align:center;"><a href="files/'+encodeURIComponent(fileName)+'" download style="padding:12px 24px;border:1px solid var(--line);border-radius:8px;background:var(--paper-soft);color:var(--accent);text-decoration:none;font-size:15px;">⬇️ 下載 '+esc(f.name)+'</a></div>';
  }
  html+='</div>';
  app.innerHTML=html;
}

function viewFilesData(extraId){
  /* 2026-10-25 修：viewFile 不改 hash（URL 仍是 #/<sid>/extras/<id>），
     這裡再 go("#/extras/"+id) 會被 normalizeHash 補成同一個 hash →
     不會觸發 hashchange → 按鈕看起來完全沒反應。改為直接重繪清單。 */
  var x=extraById(extraId);
  if(x){ viewFiles(x); return; }
  go("#/extras");
}
