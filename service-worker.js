/* 神智核 Service Worker
 *
 * 目的有两个，第二个比第一个重要得多：
 *   1. 离线可用——地铁、飞机、断网都能打开复习。
 *   2. **让 iOS Safari 不清空学习进度**。iOS 的 ITP 会清掉「7 天没交互过」的网站的全部
 *      script-writable storage（localStorage / IndexedDB / Cache API）。用户把本站
 *      「加到主畫面」安装成 PWA 后，会进入 durable storage context，不再受这个 7 天限制。
 *      而 iOS 判断能否安装成 PWA 的前提之一，就是这里注册了有效的 Service Worker。
 *      所以这个文件是「进度不丢」的技术前提，不只是离线缓存。
 *
 * 路径策略：全部用相对路径（./）。本站可能部署在
 *   https://用戶名.github.io/倉庫名/   这种子路径下，
 *   写死 "/index.html" 会指向用户主页面而不是笔记首页。
 *
 * 缓存策略：
 *   导航请求（打开页面）→ 网络优先，但最多等 3.5 秒；超时或失败即回退缓存。
 *                        这样在线时总能拿到最新版，断网时又不会干等。
 *   其他同源 GET        → 缓存优先 + 后台更新（stale-while-revalidate）。
 *
 * V0.9.20 由 prep_ghpages.py 在部署时替换成站点版号。改版即换缓存名，
 * 避免用户长期停留在旧缓存上，同时 activate 时清掉旧版缓存防止无限增长。
 */
var SW_VERSION = 'V0.9.20';
var CACHE = 'shenzhine-' + SW_VERSION;
var NET_TIMEOUT = 3500;
/* data/*.json 是几百 KB 的分区資料（heavy-phys.json 等），
   弱网首次访问可能超过 3.5s——给独立的长超时（15s）。
   导航仍是 3.5s（首屏要快）；data 用 15s，超时才回退缓存。 */
var DATA_TIMEOUT = 15000;

/* 预缓存清单。用相对路径，scope 根就是站点根。
   图例全部在根目录（不放子资料夹），理由见 manifest.json 的说明：
   网页上传时拖曳资料夹很容易整包漏掉，而图标 404 会让 iOS 生成占位图标。
   只列 index.html 一份首页：'./' 与 './index.html' 是同一份 4.7MB 内容，
   两个都预缓存会把存储翻倍，没有必要。 */
var CORE = [
  './index.html',
  './manifest.json',
  './apple-touch-icon.png',
  './icon-192.png',
  './icon-512.png',
  './icon-maskable-512.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      /* 逐个加，任何一个失败（例如某个图标在部署包里缺失）都不该让整个 SW 安装失败，
         其余功能仍要能用。 */
      return Promise.all(CORE.map(function (url) {
        return cache.add(new Request(url, { cache: 'reload' })).catch(function () {
          return null;
        });
      }));
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        /* 清掉旧版号缓存，避免用户攒了几十个版本把存储撑爆 */
        if (k.indexOf('shenzhine-') === 0 && k !== CACHE) {
          return caches.delete(k);
        }
        return null;
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

/* 网络优先 + 超时保护：在线拿最新，断网快速回退，不干等浏览器默认超时。 */
function netFirstWithTimeout(req, timeoutMs) {
  return new Promise(function (resolve, reject) {
    var settled = false;
    var timer = setTimeout(function () {
      if (!settled) {
        settled = true;
        reject(new Error('timeout'));
      }
    }, timeoutMs || NET_TIMEOUT);
    fetch(req).then(function (res) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(res);
    }).catch(function (err) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(err);
    });
  });
}

self.addEventListener('fetch', function (e) {
  var req = e.request;

  /* 只处理同源 GET。POST、跨域请求一律放行，不干预。 */
  if (req.method !== 'GET') return;

  var url;
  try {
    url = new URL(req.url);
  } catch {
    /* req.url 不是合法 URL（極少見），放行不干預 */
    return;
  }
  if (url.origin !== self.location.origin) return;

  /* 导航请求——网络优先（带超时），失败回退缓存首页 */
  if (req.mode === 'navigate') {
    e.respondWith(
      netFirstWithTimeout(req).then(function (res) {
        /* 只缓存正常响应，别把 404 页面缓存下来当成首页 */
        if (res && res.status === 200) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put('./index.html', copy); });
        }
        return res;
      }).catch(function () {
        return caches.match('./index.html').then(function (hit) {
          return hit || caches.match('./') || Response.error();
        });
      })
    );
    return;
  }

  /* 其他同源资源：按「内容型 vs 静态资源型」分策略（V0.9.5 修）
     ─────────────────────────────────────────────────────────────
     為什麼要分：
       · data/*.json 是**筆記正文與圖片引用**——改版後必須立刻看到新內容。
         原本走 cache-first，導致「HTML 已是新版、知識點卻還是舊圖」，
         用戶反覆刷新也看不到更新（要等第二次訪問才生效）。
       · 圖片／圖示是**靜態資源**——內容不變時走 cache-first 最省流量，
         且離線時能直接命中緩存。
     策略：
       data/*.json → 網絡優先（超時／失敗才回退緩存）＝ 永遠看到最新筆記
       其餘資源    → 緩存優先 + 後台靜默更新（stale-while-revalidate）
  */
  var path = url.pathname;
  var isData = /\/data\/[^/]+\.json$/.test(path) || /(^|\/)data\/heavy-/.test(path);

  if (isData) {
    e.respondWith(
      netFirstWithTimeout(req, DATA_TIMEOUT).then(function (res) {
        if (res && res.status === 200) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () {
        /* 離線時回退緩存（沒有緩存過就報錯，讓上層顯示載入失敗） */
        return caches.match(req).then(function (hit) {
          return hit || Response.error();
        });
      })
    );
    return;
  }

  /* 靜態資源（圖片／圖示／字體等）：緩存優先，命中後後台靜默更新 */
  e.respondWith(
    caches.match(req).then(function (hit) {
      var fetching = fetch(req).then(function (res) {
        if (res && res.status === 200 && res.type === 'basic') {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); });
        }
        return res;
      }).catch(function () {
        return hit || Response.error();
      });
      return hit || fetching;
    })
  );
});

/* 页面可发消息让新 SW 立刻接管（配合「有新版本，点此刷新」） */
self.addEventListener('message', function (e) {
  if (e.data === 'skipWaiting') self.skipWaiting();
});
