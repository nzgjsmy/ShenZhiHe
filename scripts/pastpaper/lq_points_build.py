# -*- coding: utf-8 -*-
"""為卷二每道大題的**計分子題**產生「得分點關鍵詞」—— 供前端離線自評使用。

為什麼需要這個
--------------
站點是**純離線單檔案**，沒有後端，不可能真的叫一個 LLM 來改卷。
所以「以資深老師視角主觀判斷」只能這樣近似：

  把每道小題的官方得分點濃縮成幾個**關鍵概念詞**，學生作答時檢查
  這些概念有沒有被提到 —— 命中幾個得分點，就給幾成的回饋。
  不要求用字與參考答案相同，**同義詞、子串、近義寫法都算命中**。

關鍵詞從哪裡來
--------------
從 `lq_guides/<年份>.txt` 的每個「（N 分）」得分點抽取：
  1. 優先取 `**加粗**` 的內容（我們撰寫題解時已把關鍵概念加粗）
  2. 去掉虛詞、括號補充、與「（1 分）」標記
  3. 切成 2–6 字的概念詞，取前幾個作為匹配候選
  4. 套用 `SYN` 同義詞表擴充（生物科常見一詞多寫）

用法
----
    python scripts/pastpaper/lq_points_build.py            # 只看報告
    python scripts/pastpaper/lq_points_build.py --write    # 寫入 _lq.json
"""
import argparse
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LQ = os.path.join(ROOT, "data", "bio", "_lq.json")
GU = os.path.join(ROOT, "scripts", "pastpaper", "lq_guides")

# 標題行：**（i）...（3 分）** / **（ii）(1) ...（2 分）**
TITLE = re.compile(r"^\*\*（(.+?)）(.*?)（(?:(\d+) 分|分值待核對)）\*\*", re.M)
# 得分點行：- xxx（1 分）
POINT = re.compile(r"^\s*[-*]\s+(.+?)（\s*\d+\s*分\s*）", re.M)
BOLD = re.compile(r"\*\*(.+?)\*\*")
MD = re.compile(r"[`*_]|\$.*?\$")

# 虛詞／連接詞：切詞時當分隔符，且本身不當關鍵詞
STOP = set("的了是在與和及或就都也很而因此因為所以為何為何會能可把被從到於其這那"
           "些個們之內中上下前後時當若如則者所很更最又有沒不")
STOP |= set("，。、：；！？（）()《》「」『』“”‘’…—-~ \t")

# 生物科常見「一詞多寫」—— 命中任何一個都算同一概念
SYN = {
    "水勢": ["水勢", "水潛勢", "滲透勢"],
    "滲透": ["滲透", "滲透作用", "osmosis"],
    "蒸騰": ["蒸騰", "蒸散", "蒸騰作用", "蒸散作用"],
    "光合作用": ["光合作用", "光合"],
    "呼吸作用": ["呼吸作用", "呼吸", "細胞呼吸"],
    "有氧呼吸": ["有氧呼吸", "需氧呼吸", "有氧"],
    "無氧呼吸": ["無氧呼吸", "厭氧呼吸", "缺氧呼吸", "發酵"],
    "主動運輸": ["主動運輸", "主動轉運"],
    "擴散": ["擴散", "被動運輸"],
    "酵": ["酵素", "酶"],
    "抗利尿激素": ["抗利尿激素", "ADH", "血管升壓素"],
    "胰島素": ["胰島素", "insulin"],
    "血糖": ["血糖", "葡萄糖濃度", "血中葡萄糖"],
    "等位基因": ["等位基因", "對偶基因"],
    "基因型": ["基因型", "遺傳型"],
    "表現型": ["表現型", "表型"],
    "減數分裂": ["減數分裂", "成熟分裂"],
    "基因突變": ["基因突變", "突變"],
    "限制酶": ["限制酶", "限制性內切酶", "限制酵素"],
    "凝膠電泳": ["凝膠電泳", "電泳"],
    "聚合酶鏈式反應": ["聚合酶鏈式反應", "PCR", "聚合酶鏈反應"],
    "質粒": ["質粒", "質體"],
    "轉基因": ["轉基因", "基因改造", "基改"],
    "幹細胞": ["幹細胞", "幹細胞"],
    "硝化作用": ["硝化作用", "硝化"],
    "反硝化": ["反硝化作用", "脫氮作用", "反硝化"],
    "分解作用": ["分解作用", "分解", "腐生"],
    "食物鏈": ["食物鏈", "食物網"],
    "生態系統": ["生態系統", "生態系"],
    "生物多樣性": ["生物多樣性", "多樣性"],
    "無菌": ["無菌", "無菌操作", "無菌技術"],
    "高壓蒸氣滅菌": ["高壓蒸氣滅菌", "高壓滅菌", "autoclave"],
    "巴斯德消毒": ["巴斯德消毒", "巴氏消毒", "巴士德消毒"],
    "噬菌體": ["噬菌體", "噬菌體", "phage"],
    "病毒": ["病毒", "virus"],
    "細菌": ["細菌", "菌"],
    "真菌": ["真菌", "黴菌", "菇"],
    "宿主": ["宿主", "寄主"],
    "互利共生": ["互利共生", "共生", "mutualism"],
    "攜帶者": ["攜帶者", "帶基因者", "帶因者", "雜合子"],
    "血紅蛋白": ["血紅蛋白", "血紅素"],
    "基因庫": ["基因庫", "gene pool"],
    "選擇性育種": ["選擇性育種", "選育", "人工選擇"],
    "克隆": ["克隆", "複製", "無性繁殖"],
    "等位基因頻率": ["等位基因頻率", "基因頻率"],
}


ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"]
MARK = re.compile(r"[（(]\s*([a-z]{1,3}|\d{1,2})\s*[)）]", re.I)

# ──「關係／方向」詞 ────────────────────────────────────────────────
# DSE 長題目絕大多數得分點要求的是**一條完整的陳述**（誰上升、誰下降、
# 兩者什麼關係），光寫出「尿液排泄量」「鈉濃度」這些名詞**並不得分**。
# 所以除了概念詞，還要把得分點裡的關係詞抽出來，學生作答時一併檢查。
UP = ("上升 升高 增加 增多 增大 變大 變高 加快 提高 較高 越高 愈高 越大 愈大 "
      "越多 愈多 越快 愈快 越強 愈強 越長 愈長 越高越 最大 最高 較多 較快 較大 "
      "正比 正相關 促進 活化 刺激 擴大 上升至 由低至高 由小至大 回升 旺盛 "
      "大於 高於 多於 快於").split()
DOWN = ("下降 降低 減少 減小 變小 變低 減慢 放緩 下降至 較低 越低 愈低 越小 愈小 "
        "越少 愈少 越慢 愈慢 越弱 愈弱 越短 愈短 最低愈 最小 最低 較少 較慢 較小 "
        "反比 負相關 抑制 受阻 減弱 萎縮 下跌 由高至低 由大至小 回落 "
        "小於 低於 少於 慢於").split()
ANY = ("隨着 隨著 隨 而變 而改 導致 引起 造成 因此 因而 故此 由於 令 使 讓 "
       "改變 變化 差異 相比 比較 相關 趨勢 模式 依次 關係 影響 取決於 "
       "正相關 負相關 相反 一致").split()

# 「越…越…」／「愈…愈…」= 兩個變量的**反向對比**（A 越高，B 越少）。
# 只有出現這種句式才判定為「反向關係」，作答時兩個方向都要寫到。
# 一般的因果鏈（滲透壓升高 → 釋放 ADH → 尿量減少）雖然 up/down 都出現，
# 但那是一條鏈，寫出任一段都算對 —— 這種放寬為 any。
YUE_UP = [w for w in UP if ("越" in w or "愈" in w)]
YUE_DOWN = [w for w in DOWN if ("越" in w or "愈" in w)]

# 切詞殘留常見的「斷頭斷尾」——以這些字開頭／結尾的多半不是完整概念
BAD_HEAD = "並他其之於從到使為被把讓給男女大小多少高低前後"
BAD_TAIL = "的了他其之於與和及就都很更最又有沒不"


def strip_md(s):
    return MD.sub("", s or "").strip()


def _has(text, ws):
    return any(w in text for w in ws)


def _first(text, ws):
    """詞在文本中首次出現的位置，沒出現回傳 -1。"""
    p = [text.find(w) for w in ws if w in text]
    return min(p) if p else -1


def relation_of(text):
    """判斷一個得分點**要不要寫出關係／方向**，要的話要哪一種。

    → {'m': 'inv'|'up'|'down'|'any'}

    - 'inv'  反向對比：得分點用了「越…越…」句式（A 越高，B 越少），
             作答時**兩個方向都要寫到**，只寫一邊不算。
    - 'up'   要寫出「上升／變大／增加」
    - 'down' 要寫出「下降／變小／減少」
    - 'any'  因果鏈型（如「滲透壓升高 → 釋放 ADH → 尿量減少」）：
             up/down 都出現在得分點裡，但那是一條鏈，寫出任一段都算對；
             或純因果／比較措辭（「導致」「隨…而改變」）。
    - None   純名詞型得分點（如「限制酶」「PCR」），不要求關係。

    ⚠️ 關鍵：得分點若指明了具體方向，作答只寫「有變化／有影響」這種
    中性詞**不算命中** —— DSE 要的是「變大還是變小」，不是「有變化」。
    所以 'up'/'down'/'inv'/'chain' 四種都要求作答裡出現**方向詞**，
    只有得分點本身也沒方向的 'any' 才接受純因果措辭。
    """
    t = text or ""
    if _has(t, YUE_UP) and _has(t, YUE_DOWN):
        return {"m": "inv"}
    pu, pd = _first(t, UP), _first(t, DOWN)
    if pu >= 0 and pd >= 0:
        return {"m": "chain"}        # 因果鏈：寫出任一段（但仍要有方向詞）
    if pu >= 0:
        return {"m": "up"}
    if pd >= 0:
        return {"m": "down"}
    if _has(t, ANY):
        return {"m": "any"}
    return None


def parse_mark(text):
    """'（ii）(1) xxx' → [(1,'ii'), (2,'1')]"""
    out = []
    for tok in MARK.findall(text or ""):
        t = tok.lower()
        if t in ROMAN:
            out.append((1, t))
        elif t.isdigit():
            out.append((2, t))
    return out


def ok_word(w):
    if len(w) < 2:
        return False
    if w[0] in BAD_HEAD and len(w) <= 3:
        return False
    if w[-1] in BAD_TAIL:
        return False
    # 全是虛詞的不收
    if all(c in STOP for c in w):
        return False
    return True


def keywords_of(text):
    """從一個得分點抽概念詞。

    第一位放「完整概念短句」（加粗原文，去符號）—— 提示時就顯示它，
    學生一看就知道方向；其後才是切出來的片段，用來提高命中率。
    """
    src = strip_md(text or "")
    bolds = [strip_md(b) for b in BOLD.findall(text or "")]
    words = []
    # 1) 完整概念短句
    for b in bolds:
        b = re.sub(r"[（(].*?[)）]", "", b).strip()
        if 2 <= len(b) <= 16:
            words.append(b)
    if not words:
        head = re.sub(r"[（(].*?[)）]", "", src).strip()
        if 2 <= len(head) <= 16:
            words.append(head)
    # 2) 切出來的概念片段
    body = " ".join(bolds) if bolds else src
    body = re.sub(r"[（(].*?[)）]", "", body)
    segs, cur = [], ""
    for ch in body:
        if ch in STOP or ch.isspace():
            if len(cur) >= 2:
                segs.append(cur)
            cur = ""
        else:
            cur += ch
    if len(cur) >= 2:
        segs.append(cur)
    for s in segs:
        if 2 <= len(s) <= 6 and ok_word(s):
            words.append(s)
        elif len(s) > 6:
            for piece in (s[:4], s[-4:]):
                if ok_word(piece):
                    words.append(piece)
    seen, out = set(), []
    for w in words:
        w = w.strip()
        if w and w not in seen and ok_word(w):
            seen.add(w)
            out.append(w)
    return out[:4]


def expand(words):
    """用同義詞表擴充候選詞。"""
    out = []
    for w in words:
        out.append(w)
        for k, vs in SYN.items():
            if k in w or w in k:
                for v in vs:
                    if v not in out:
                        out.append(v)
    return out


def parse_guide(txt, qnum):
    """→ [(標記, [得分點關鍵詞組...])]"""
    body = txt.split("@@@ " + qnum)
    if len(body) < 2:
        return []
    sec = body[1].split("\n@@@")[0]
    out = []
    last = None
    for line in sec.split("\n"):
        m = TITLE.match(line)
        if m:
            # full 要保留原始整行 —— 標記的括號被 TITLE 正則吃掉了，
            # parse_mark 必須用整行才認得出（i）/（ii）(1) 這種層級
            last = {"mark": m.group(1), "full": line, "pts": [], "rels": []}
            out.append(last)
            continue
        mp = POINT.match(line)
        if mp and last is not None:
            ws = keywords_of(mp.group(1))
            if ws:
                last["pts"].append(expand(ws))
                last["rels"].append(relation_of(mp.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    lq = json.load(open(LQ, encoding="utf-8"))
    total_sub = got = 0

    for year in sorted(lq["years"]):
        path = os.path.join(GU, year + ".txt")
        if not os.path.exists(path):
            continue
        txt = io.open(path, encoding="utf-8").read()
        for q in lq["years"][year]:
            groups = parse_guide(txt, q["qnum"])
            if not groups:
                continue
            # 用「標記」對應子題（而不是純順序）—— 題解稿常略過引導句，
            # 純順序會整段錯位。標記對不上才退回順序。
            bykey = {}
            for i, s in enumerate(q.get("subqs") or []):
                no = (s.get("no") or "").lower()
                lv = s.get("level") or 1
                key = (1, no) if no in ROMAN else ((2, no) if no.isdigit()
                                                   else (lv, no))
                bykey.setdefault(key, i)
            used = set()
            for g in groups:
                pts = [p for p in g["pts"] if p]
                if not pts:
                    continue
                mk = parse_mark(g.get("full") or g["mark"])
                idx = bykey.get(mk[-1]) if mk else None
                if idx is None or idx in used:
                    idx = next((i for i, s in enumerate(q["subqs"] or [])
                                if i not in used
                                and s.get("marks") not in (None, "")), None)
                if idx is None:
                    continue
                used.add(idx)
                (q["subqs"][idx])["points"] = pts
                # 平行陣列：每個得分點對應的「關係／方向」要求
                # （None = 純名詞型得分點，不要求寫出關係）
                rels = g.get("rels") or []
                if any(r for r in rels):
                    (q["subqs"][idx])["pointRel"] = rels
                else:
                    (q["subqs"][idx]).pop("pointRel", None)
                got += 1
            total_sub += sum(1 for s in (q.get("subqs") or [])
                             if s.get("marks") not in (None, ""))
            q["hasPoints"] = True

    print("計分子題 %d 個，已產生關鍵詞 %d 個（覆蓋率 %.0f%%）"
          % (total_sub, got, 100.0 * got / max(1, total_sub)))

    if args.write:
        io.open(LQ, "w", encoding="utf-8", newline="\n").write(
            json.dumps(lq, ensure_ascii=False, indent=1) + "\n")
        print("已寫入 %s" % LQ)


if __name__ == "__main__":
    main()
