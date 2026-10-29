# -*- coding: utf-8 -*-
"""準備 GitHub Pages 發布目錄。

做六件事：
1. 把離線單檔網站複製成 ASCII 檔名 index.html（GitHub Pages 對非 ASCII 檔名連結不友好）
2. 生成 .nojekyll（避免 Jekyll 處理 _ 開頭檔案）
3. 附一個精簡的 README 與 404 提示頁
4. 附上 PWA 資源（manifest.json、service-worker.js、favicon.ico、圖示檔），讓使用者
   可以「加到主畫面」——這同時是 iOS 不清空學習進度的前提
5. 把 service-worker.js 裡的 __SW_VERSION__ 換成站點版號（改版即換快取名）
6. 複製 index.html 引用到的筆記原圖到 img/（圖片外置：HTML 保持 ~2 MB，
   SW 同源緩存天然覆蓋，離線體驗不變）
"""
import io, json, os, re, shutil, sys
sys.stdout.reconfigure(encoding="utf-8")

SITE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(SITE), "gh-pages")

# 站名與版號（改版只動 version.json）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _sitefile import site_meta, stable_html, versioned_html  # noqa: E402
META = site_meta()
SITE_NAME = META["name"]
SITE_VER = META["version"]
SITE_TITLE = "%s %s" % (SITE_NAME, SITE_VER)


README = """# {ST}


化學、物理、生物三科的離線整合版。化學與物理內容已完成；生物分區已建好，內容待補。

**分區互不干擾**：三科各有自己的課題、知識圖譜、測驗與學習進度，
連 localStorage 都是分開的鍵，切科目不會蓋掉彼此的紀錄。

## 建議先「加到主畫面」

用手機開這個網站時，請先加到主畫面（iOS：Safari 分享 → 加入主畫面；
Android：瀏覽器選單 → 安裝應用程式）。這不只是為了像 App，而是**關係到進度會不會消失**：

iOS Safari 會清掉「7 天以上沒打開」的網站的 localStorage，
學習進度、錯題、複習排程會無聲歸零。加到主畫面裝成 App 之後就不會再被清掉。
裝好之後也支援離線使用，斷網、地鐵上都能打開複習。

設定頁有「匯出備份／匯入備份」，換裝置前先匯出，新裝置匯入即可接著學。

## 化學區（已完成）

{NP} 份化學教師版筆記 PDF 的離線整合版。

- **{NPTS}** 個知識點（全部附原 PDF 頁碼）
- **{NQ}** 道測驗題（選擇 {NMC} / 是非 {NTF}，全部點選作答）
- **{NL}** 條跨課題知識串連，互動知識圖譜
- {NT} 個課題：{TOPLIST}

## 物理區（已完成）

牛津《新高中生活與物理（第二版）》課堂工作紙，分**熱學**、**力學**、**波動學**、**電學**、**核物理**與**原子世界**六個分區：

- **熱學**：溫度與溫度計、內能與比熱容量、物態的改變、傳熱方式、氣體定律與分子運動論
- **力學**：長度時間與運動描述、直線運動線圖、牛頓三定律、力矩平衡、功與能量、動量、拋體、圓周運動、萬有引力
- **波動學**：光線與反射、折射與全內反射、透鏡成像、波動基礎、水波與波的現象、光的波動本質與電磁波、縱波與聲音
- **電學**：靜電與電場、電路與電阻、電功率與家居電學、磁場與磁力、電磁感應、交流電與變壓器
- **核物理**：輻射與放射現象、原子結構與放射衰變、核能
- **原子世界**：盧瑟福原子模型與散射實驗、光電效應與愛因斯坦光子模型、原子光譜與玻爾模型、波粒二象性、納米材料與顯微技術

- **{PNPTS}** 個知識點（全部附原 PDF 頁碼與筆記原圖）
- **{PNQ}** 道測驗題（全部點選作答）
- **{PNL}** 條跨課題知識串連
- {PNT} 個課題：{PTOPLIST}

## 原子世界區（新增）

新高中物理選修二《原子世界》課堂工作紙 E2，**39 頁 PDF 全覆蓋**：

- **{ATOPTS}** 個知識點（全部附原 PDF 頁碼與筆記原圖）
- **{ATOQ}** 道測驗題（選擇 {ATOMC} / 是非 {ATOTF}）
- **{ATOL}** 條跨課題知識串連
- 3 個課題：邁向現代原子模型 I、邁向現代原子模型 II、納米材料

課題內容：

- **atomic1**：蓋革—馬斯登散射實驗、盧瑟福原子模型、盧瑟福模型的局限性、散射實驗的重要性、光電效應與光電子、用光電池研究光電效應、波動理論的困難、光子與光強度、功函數和臨界頻率、光子與電子的相互作用、愛因斯坦光電方程、V_s–f 線圖、波粒二象性
- **atomic2**：發射光譜和吸收光譜、玻爾的氫原子模型、能級與量子化、解釋發射光譜和吸收光譜、玻爾模型的局限性、光和物質的波粒二象性、德布羅意波長、電子的駐波
- **atomic3**：不同形態的納米材料、納米材料的物理特性、表面面積與體積之比、光學顯微鏡與瑞利判據、穿透電子顯微鏡、掃描穿隧顯微鏡、兩種顯微鏡比較、蓮花效應、日常生活的應用、潛在危險

## 核物理區（新增）

新高中生活與物理《課堂工作紙5》核物理章節，**36 頁 PDF 全覆蓋**：

- **{NUCPTS}** 個知識點（全部附原 PDF 頁碼與筆記原圖）
- **{NUCQ}** 道測驗題（選擇 {NUCMC} / 是非 {NUCTF}）
- **{NUCL}** 條跨課題知識串連
- 3 個課題：輻射與放射現象、原子結構與放射衰變、核能

課題內容：

- **nuclear1**：致電離輻射、X 射線、核輻射（α/β/γ 完整比較表）、本底輻射、安全措施、致電離能力、擴散雲室、蓋革-彌勒管、射程和穿透能力、在電場和磁場中的偏轉
- **nuclear2**：原子模型、原子中的粒子、原子序數/質量數/中子數、核素與同位素、放射衰變、α/β/γ 衰變、衰變系、放射衰變的特性、半衰期與衰變公式、指數衰變與衰變常數、放射性同位素的應用、碳-14 年代測定法、示蹤物、輻射安全、核廢料
- **nuclear3**：核裂變、核聚變、連鎖反應與臨界質量、原子質量單位、電子伏、質能對等（E=mc²）、核反應能量計算例題、核能、核聚變發電、核聚變能量計算、核武

整站**零第三方依賴**（不連任何外部網址），進度與錯題記錄存在瀏覽器 localStorage。
筆記圖片放在 `img/` 目錄按需載入並由 Service Worker 緩存——HTML 只約 2 MB，
首次打開看過的頁面，之後斷網也照樣能看圖。

## 版權與免責聲明

> ⚠️ **本網站一切資源僅供學習用途，請勿商用。**

- 本網站為個人學習用途的筆記整理，非官方出版品，與任何出版社、考試機構均無隸屬或合作關係。
- 筆記內容、例題與圖表整理自公開教材及歷屆試題，版權歸原作者、出版方及香港考試及評核局所有。
- 所有資源僅供個人學習、複習與教學參考，請勿用於任何商業用途，亦請勿再行散布或用於營利。
- 整理過程雖力求準確，仍可能存在疏漏或錯誤，內容僅供參考，一切以官方教材及考試機構公布為準。
- 本站不對內容的準確性、完整性或適用性作任何保證，使用者須自行判斷並承擔使用後果。
- 學習進度與錯題紀錄僅儲存在使用者自己的瀏覽器中，本站不收集、不上傳任何個人資料。
- 如版權所有者認為本站內容不妥，請聯絡我們，我們會立即處理或移除。
""".replace("{ST}", SITE_TITLE)

NOJEKYLL = ""


def load(path, default=None):
    if not os.path.exists(path):
        return default
    # 用 utf-8-sig 讀取：本專案部分 JSON 帶 UTF-8 BOM，
    # 純 utf-8 會拋 "Unexpected UTF-8 BOM"，而 build.py 端已自行剝離 BOM。
    with io.open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def chem_readme_stats():
    """從資料檔實時統計，避免課題增減後 README 過期。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subj = load(os.path.join(base, "data", "chem", "subject.json"), {}) or {}
    topics = subj.get("topics") or []
    n_pts = n_mc = n_tf = 0
    titles = []
    for tid in topics:
        t = load(os.path.join(base, "data", "chem", tid + ".json"), None)
        if t:
            titles.append("%s %s" % (tid.upper(), t.get("title", "")))
            n_pts += sum(len(s.get("points", [])) for s in t.get("sections", []))
        q = load(os.path.join(base, "quiz", "chem", tid + ".json"), None) or {}
        for x in q.get("questions", []):
            if x.get("type") == "mc":
                n_mc += 1
            elif x.get("type") == "tf":
                n_tf += 1
    links = load(os.path.join(base, "data", "chem", "links.json"), []) or []
    return dict(NP=len(topics), NT=len(topics), NPTS=n_pts, NQ=n_mc + n_tf,
                NMC=n_mc, NTF=n_tf, NL=len(links), TOPLIST="、".join(titles))


def phys_readme_stats():
    """物理區統計（同樣實時從資料檔算，避免 README 與內容脫節）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subj = load(os.path.join(base, "data", "phys", "subject.json"), {}) or {}
    topics = subj.get("topics") or []
    n_pts = n_q = 0
    titles = []
    for tid in topics:
        t = load(os.path.join(base, "data", "phys", tid + ".json"), None)
        if t:
            titles.append(t.get("title", tid))
            n_pts += sum(len(s.get("points", [])) for s in t.get("sections", []))
        q = load(os.path.join(base, "quiz", "phys", tid + ".json"), None) or {}
        n_q += len(q.get("questions", []) or [])
    links = load(os.path.join(base, "data", "phys", "links.json"), []) or []
    return dict(PNPTS=n_pts, PNQ=n_q, PNL=len(links),
                PNT=len(topics), PTOPLIST="、".join(titles))


def nuclear_readme_stats():
    """核物理區統計（nuclear1~3 三個課題）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    nuc = ["nuclear1", "nuclear2", "nuclear3"]
    n_pts = n_mc = n_tf = 0
    for tid in nuc:
        t = load(os.path.join(base, "data", "phys", tid + ".json"), None)
        if t:
            n_pts += sum(len(s.get("points", [])) for s in t.get("sections", []))
        q = load(os.path.join(base, "quiz", "phys", tid + ".json"), None) or {}
        for x in q.get("questions", []):
            if x.get("type") == "mc":
                n_mc += 1
            elif x.get("type") == "tf":
                n_tf += 1
    links = load(os.path.join(base, "data", "phys", "links.json"), []) or []
    n_nl = len([l for l in links
                if str(l.get("from", "")).startswith("nuclear")
                or str(l.get("to", "")).startswith("nuclear")])
    # 注意：前綴 NUC，避免與 chem_readme_stats 的 NPTS/NQ/NMC/NTF/NL 撞名
    return dict(NUCPTS=n_pts, NUCQ=n_mc + n_tf, NUCMC=n_mc,
                NUCTF=n_tf, NUCL=n_nl)


def atomic_readme_stats():
    """原子世界區統計（atomic1~3 三個課題）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ato = ["atomic1", "atomic2", "atomic3"]
    n_pts = n_mc = n_tf = 0
    for tid in ato:
        t = load(os.path.join(base, "data", "phys", tid + ".json"), None)
        if t:
            n_pts += sum(len(s.get("points", [])) for s in t.get("sections", []))
        q = load(os.path.join(base, "quiz", "phys", tid + ".json"), None) or {}
        for x in q.get("questions", []):
            if x.get("type") == "mc":
                n_mc += 1
            elif x.get("type") == "tf":
                n_tf += 1
    links = load(os.path.join(base, "data", "phys", "links.json"), []) or []
    n_al = len([l for l in links
                if str(l.get("from", "")).startswith("atomic")
                or str(l.get("to", "")).startswith("atomic")])
    # 注意：前綴 ATO，避免與 chem_readme_stats 的 NPTS/NQ/NMC/NTF/NL 撞名
    return dict(ATOPTS=n_pts, ATOQ=n_mc + n_tf, ATOMC=n_mc,
                ATOTF=n_tf, ATOL=n_al)

NOTFOUND = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{ST}</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:linear-gradient(160deg,#0f766e,#134e4a);color:#fff;
 font-family:"PingFang TC","Microsoft JhengHei",system-ui,sans-serif;padding:20px;text-align:center}
.c{max-width:420px;width:100%}
h1{font-size:23px;margin:0 0 10px}
p{opacity:.85;font-size:14.5px;line-height:1.8}
a.btn{display:inline-block;background:#fff;color:#0f766e;text-decoration:none;font-weight:700;
 font-size:17px;padding:14px 28px;border-radius:13px;margin-top:20px;min-height:44px;line-height:1.2;box-sizing:border-box}
</style></head>
<body><div class="c">
<h1>🧪 {ST}</h1>
<p>你打開的這個頁面不存在。<br>回到首頁請點下面的按鈕。</p>
<a class="btn" id="home" href="./">回到首頁 →</a>
</div>
<script>
// 這個 404 頁面會被 GitHub Pages 用在任何不存在的路徑下，網址可能是
//   /倉庫名/打錯的頁面        或   /倉庫名/深/一層/打錯
// 所以不能用 "./"（它會相對「打錯的那一層」解析，還是 404），
// 也不能用 "/"（那是使用者主頁，不是筆記）。
// 專案網站的網址固定是 /倉庫名/...，取第一段就是倉庫根；使用者主頁只有一段，根就是 "/"。
(function () {
  var path = location.pathname;
  var seg = path.split("/").filter(Boolean);
  var base;
  if (seg.length >= 2) {
    base = "/" + seg[0] + "/";        // /倉庫名/任何東西
  } else if (seg.length === 1 && path.charAt(path.length - 1) === "/") {
    base = "/" + seg[0] + "/";        // /倉庫名/ 本身
  } else {
    base = "/";                       // 使用者主頁，或主頁下的 404
  }
  document.getElementById("home").setAttribute("href", base);
})();
</script>
</body></html>
""".replace("{ST}", SITE_TITLE)


def rmtree_soft(path):
    """刪掉舊的發布目錄。裡面可能殘留 headless Chrome 的臨時 profile（檔案被鎖住），
    這種情況下逐項刪、刪不掉的先跳過，不要讓整個發布流程失敗。"""
    if not os.path.isdir(path):
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for n in files:
            try:
                os.unlink(os.path.join(root, n))
            except OSError:
                pass
        for n in dirs:
            try:
                os.rmdir(os.path.join(root, n))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        print("  note: 舊發布目錄有檔案被占用，殘留部分已略過")


def copy_pwa():
    """複製 PWA 資源到發布目錄，並把 SW 版號換成當前站點版號。

    這些檔案是「加到主畫面」與「離線可用」的必要條件，也讓 iOS 給予
    durable storage（否則 7 天沒開就清空學習進度）。
    缺檔不致命：網站本體仍可正常使用，只是少了安裝與離線能力。
    """
    copied = []
    # PWA 核心檔案 + 圖示，全部平鋪在網站根目錄。
    # 刻意不放 icons/ 子資料夾：用 GitHub 網頁上傳時，拖曳資料夾很容易只傳到檔案、
    # 整個資料夾沒上去；而 <link rel="apple-touch-icon"> 一旦指向 404，iOS 不會回退到
    # 根目錄圖示，會直接用 theme-color 底色 + 標題首字生成佔位圖示。
    # 平鋪在根目錄後，上傳時「全選檔案一起拖」就不可能漏。
    flat = ["manifest.json", "service-worker.js", "favicon.ico",
            "apple-touch-icon.png", "apple-touch-icon-167.png", "apple-touch-icon-152.png",
            "favicon-32.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"]
    for name in flat:
        src = os.path.join(SITE, name)
        if not os.path.exists(src):
            print("  note: 缺少 %s（略過；網站本體不受影響）" % name)
            continue
        dst = os.path.join(OUT, name)
        if name == "service-worker.js":
            with io.open(src, encoding="utf-8") as f:
                js = f.read()
            js = js.replace("__SW_VERSION__", SITE_VER)
            with io.open(dst, "w", encoding="utf-8") as f:
                f.write(js)
        else:
            shutil.copy2(src, dst)
        copied.append(name)
    return copied


def copy_note_images():
    """把 index.html 引用到的筆記原圖複製到 gh-pages/img/（路線三：圖片外置）。

    圖片走同域相對路徑 img/<file>.webp：
      · HTML 單檔從 16 MB 降到 ~2 MB
      · Service Worker 同源緩存天然覆蓋，離線體驗與內嵌一致
      · GitHub Pages 1GB 上限對 15 MB 級部署量有 70 倍餘量

    與「圖示平鋪」鐵律不衝突：圖示是 <link> 指向、404 時 iOS 不回退必須放根目錄；
    筆記圖是自家 HTML 的相對引用，放 img/ 子目錄沒問題——但上傳時**整個 img/ 資料夾
    必須一起傳**（強烈建議 git push 而非網頁拖拽）。
    """
    with io.open(os.path.join(OUT, "index.html"), encoding="utf-8") as f:
        html = f.read()
    refs = sorted(set(re.findall(r"img/([A-Za-z0-9_]+\.webp)", html)))
    # 自製圖解放在 img/gen/ 子目錄（SVG 為主，早期幾張是 PNG），必須一起複製，否則線上 404
    refs_gen = sorted(set(re.findall(r"img/(gen/[A-Za-z0-9_\-]+\.(?:svg|png))", html)))
    # 真題配圖放在 img/pp/<年份>/f<NN>.webp，引用來自 payload JSON（不是 markdown），
    # 舊版正則抓不到 → 線上 404。這裡一併收進來。
    # ⚠️ 年份段必須同時容納「四位數年份」與「PP／SP」兩個短代碼 —— 
    #    只寫 [0-9]{4} 會漏掉 PP（練習卷）與 SP（樣本試卷）的全部配圖（39 張），
    #    這正是 V0.20.0～V0.24.0 期間線上 PP／SP 題目配圖全 404 的原因。
    refs_pp = sorted(set(re.findall(r"img/(pp/(?:[0-9]{4}|PP|SP)/[A-Za-z0-9_]+\.webp)", html)))
    all_refs = refs + refs_gen + refs_pp
    if not all_refs:
        print("  note: index.html 未引用任何 img/*.webp（圖片外置未啟用？）")
        return 0
    dst_dir = os.path.join(OUT, "img")
    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)
    copied, miss = 0, []
    for name in all_refs:
        rel = name.replace("/", os.sep)
        src = os.path.join(SITE, "img", rel)
        dst = os.path.join(dst_dir, rel)
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            copied += 1
        else:
            miss.append(name)
    if miss:
        print("  warning: %d 個引用圖片在 site/img/ 找不到: %s"
              % (len(miss), ", ".join(miss[:5])))
    total = 0
    for dp, _dn, fn in os.walk(dst_dir):
        for n in fn:
            total += os.path.getsize(os.path.join(dp, n))
    print("  筆記原圖：外置 %d 張（自製圖解 %d 張、真題配圖 %d 張）→ img/（%.2f MB）"
          % (copied, len(refs_gen), len(refs_pp), total / 1024.0 / 1024.0))
    return copied




def copy_extra_files():
    """把 extras/<sid>/ 下的補充檔案（html/xlsx/pdf 等）複製到 gh-pages/files/。

    這些檔案由 extras.js 的 viewFiles() 透過相對路徑 files/<name> 存取。
    """
    src_dir = os.path.join(os.path.dirname(SITE), "extras", "bio")
    if not os.path.isdir(src_dir):
        print("  note: extras/bio/ 不存在，略過補充檔案複製")
        return 0
    dst_dir = os.path.join(OUT, "files")
    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)
    copied = 0
    for n in sorted(os.listdir(src_dir)):
        if not n.endswith((".html", ".xlsx", ".pdf", ".zip")):
            continue
        ap = os.path.join(src_dir, n)
        if not os.path.isfile(ap):
            continue
        shutil.copy2(ap, os.path.join(dst_dir, n))
        copied += 1
        print("  複製補充檔案：files/%s" % n)
    print("  補充檔案：files/ %d 個" % copied)
    return copied

def main():
    # 可用 NO_WIPE=1 跳過清空（原地覆蓋，適合沙箱不允許批量刪除時）
    if not os.environ.get("NO_WIPE"):
        rmtree_soft(OUT)
    if not os.path.isdir(OUT):
        os.makedirs(OUT)

    # 主站 = 穩定檔名的單檔網站（舊檔名的轉址頁只有幾百 bytes，會自然被排除）
    src = stable_html()
    if not os.path.exists(src):
        cands = []
        for n in os.listdir(SITE):
            if (n.endswith(".html") and "verify" not in n and "shot" not in n
                    and n != "index.html"):
                p = os.path.join(SITE, n)
                cands.append((os.path.getsize(p), p))
        cands.sort(reverse=True)
        if not cands:
            raise SystemExit("找不到網站 HTML")
        src = cands[0][1]

    shutil.copy2(src, os.path.join(OUT, "index.html"))
    _stats = chem_readme_stats()
    _stats.update(phys_readme_stats())
    _stats.update(nuclear_readme_stats())
    _stats.update(atomic_readme_stats())
    with io.open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
        f.write(README.format(**_stats))
    with io.open(os.path.join(OUT, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write(NOJEKYLL)
    with io.open(os.path.join(OUT, "404.html"), "w", encoding="utf-8") as f:
        f.write(NOTFOUND)
    pwa = copy_pwa()
    n_img = copy_note_images()
    n_files = copy_extra_files()

    print("站名：%s" % SITE_TITLE)
    print("來源：%s" % os.path.basename(src))
    print("發布目錄已準備好：%s" % OUT)
    for n in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, n)
        if os.path.isfile(p):
            print("  %-18s %8.1f KB" % (n, os.path.getsize(p) / 1024.0))
    print("  PWA 資源：%d 個（%s）" % (len(pwa), "、".join(pwa[:3]) + ("…" if len(pwa) > 3 else "")))
    print("  筆記原圖：img/ %d 張" % n_img)

    total = 0
    for root, _dirs, files in os.walk(OUT):
        for n in files:
            total += os.path.getsize(os.path.join(root, n))
    print("\n合計 %.1f KB" % (total / 1024.0))


if __name__ == "__main__":
    main()
