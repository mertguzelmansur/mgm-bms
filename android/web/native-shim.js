/* MGM BMS – yerel Android kabuğu (Java WebView) için uyarlayıcı.
   window.AndroidNative (Java @JavascriptInterface) üzerine, bridge.js'nin beklediği Capacitor BleClient
   arayüzünü kurar. Böylece bridge.js değişmeden hem Capacitor hem yerel kabukta çalışır. */
(function () {
"use strict";
const N = window.AndroidNative;
if (!N) return;                                   // tarayıcıda: hiçbir şey yapma (demo modu çalışır)

const waiters = {};                               // tür -> [resolve,...]  (tek seferlik yanıtlar)
const once = (type, ms) => new Promise((res, rej) => {
  (waiters[type] = waiters[type] || []).push(res);
  if (ms) setTimeout(() => rej(new Error("Zaman aşımı")), ms);
});
let scanCb = null, notifyCb = null, discCb = null, connWait = null;
const hexToBytes = (h) => { const o = new Uint8Array(h.length >> 1); for (let i = 0; i < o.length; i++) o[i] = parseInt(h.substr(2 * i, 2), 16); return o; };
const bytesToHex = (dv) => { const b = new Uint8Array(dv.buffer, dv.byteOffset, dv.byteLength); let s = ""; for (const x of b) s += (x < 16 ? "0" : "") + x.toString(16); return s; };

window.__nativeEvent = function (type, data) {
  if (type === "scan") { scanCb && scanCb({device: {deviceId: data.id, name: data.name}, localName: data.name, rssi: data.rssi, uuids: data.uuids}); return; }
  if (type === "data") { notifyCb && notifyCb(new DataView(hexToBytes(data).buffer)); return; }
  if (type === "connected") { if (connWait) { connWait.res(); connWait = null; } return; }
  if (type === "connectError") { if (connWait) { connWait.rej(new Error(data)); connWait = null; } return; }
  if (type === "disconnected") { N.keepScreenOn(false); const f = discCb; discCb = null; notifyCb = null; f && f(); return; }
  if (type === "scanError") { console.warn(data); return; }
  const w = waiters[type]; if (w && w.length) w.shift()(data);
};

async function ensurePerms() {
  if (N.hasPermissions()) return;
  const p = once("perm"); N.requestPermissions();
  if (!(await p)) throw new Error("Bluetooth izni verilmedi – Ayarlar > Uygulamalar > MGM BMS > İzinler bölümünden 'Yakındaki cihazlar' iznini açın");
}
const chk = (err) => { if (err) throw new Error(err); };
async function writeRetry(hex, resp) {              // Android aynı anda tek GATT işlemi kabul eder: meşgulse kısa bekle, tekrar dene
  let err = "";
  for (let i = 0; i < 12; i++) { err = N.write(hex, resp); if (!err || err === "Bağlı değil") break; await new Promise(r => setTimeout(r, 40)); }
  chk(err);
}

const BleClient = {
  async initialize() { if (!N.available()) throw new Error("Bu cihazda Bluetooth yok"); await ensurePerms(); },
  async isEnabled() { return N.isEnabled(); },
  async requestEnable() { const p = once("btEnable"); N.requestEnable(); return p; },
  async requestLEScan(opts, cb) { scanCb = cb; chk(N.startScan()); },
  async stopLEScan() { scanCb = null; N.stopScan(); },
  async connect(id, onDisconnect, opts) {
    const t = (opts && opts.timeout) || 20000;
    const p = new Promise((res, rej) => { connWait = {res, rej}; });
    discCb = null;
    chk(N.connect(id));
    let timer;
    try {
      await Promise.race([p, new Promise((_, rej) => { timer = setTimeout(() => rej(new Error("Bağlantı zaman aşımı – BMS yakında ve açık mı?")), t); })]);
    } catch (e) { connWait = null; N.disconnect(); throw e; }
    finally { clearTimeout(timer); }
    discCb = onDisconnect;
  },
  async requestConnectionPriority() { /* yerel tarafta bağlantıda zaten yüksek */ },
  async startNotifications(id, svc, chr, cb) { notifyCb = cb; },
  async disconnect() { discCb = null; notifyCb = null; N.keepScreenOn(false); N.disconnect(); },
  async writeWithoutResponse(id, s, c, dv) { await writeRetry(bytesToHex(dv), false); },
  async write(id, s, c, dv) { await writeRetry(bytesToHex(dv), true); },
};

window.CAP = {
  Capacitor: {isNativePlatform: () => true, getPlatform: () => "android"},
  BleClient,
  license: {                                       // lisans (Java: License – Ed25519 doğrulama, ANDROID_ID)
    info: () => JSON.parse(N.licenseInfo()),
    activate(key) { const r = JSON.parse(N.activate(String(key))); if (!r.ok) throw new Error(r.error || "Geçersiz lisans anahtarı"); return r; },
  },
  history: {                                       // 24 saat kaydı (Java: HistoryStore + arka plan servisi)
    rows: () => JSON.parse(N.histRows()),
    info: () => JSON.parse(N.histInfo()),
    enable: (on) => N.histEnable(!!on),
    clear: () => N.histClear(),
    add: (row) => N.histAdd(row),
    setOld: (b) => N.setOldProtocol(!!b),
    setName: (n) => N.setDeviceName(n || ""),
    export(name) {
      const p = once("histExport"); N.histExport(name);
      return p.then(r => { if (!r.ok) throw new Error(r.error); return r; });
    },
  },
  saveFile(name, text, mime) {
    const r = N.saveFile(name, text, mime || "text/plain", true);
    if (r.startsWith("HATA:")) throw new Error("Dosya kaydedilemedi: " + r.slice(5));
    return r;
  },
};
window.MGM_NATIVE_VERSION = N.version();
})();
