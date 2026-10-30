package com.mgm.bms;

import android.Manifest;
import android.app.Activity;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanRecord;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelUuid;
import android.provider.MediaStore;
import android.view.View;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.Charset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * MGM BMS – Android kabuğu.
 * Arayüz (assets/www/index.html) masaüstü sürümüyle aynıdır; bu sınıf yalnızca WebView'i barındırır ve
 * JavaScript'e "AndroidNative" adıyla yerel Bluetooth LE + dosya kaydetme köprüsü sunar.
 * Yerelden JS'e olaylar: window.__nativeEvent(tür, json)
 */
public class MainActivity extends Activity {
    static final UUID SERVICE = UUID.fromString("0000ffe0-0000-1000-8000-00805f9b34fb");
    static final UUID CHAR = UUID.fromString("0000ffe1-0000-1000-8000-00805f9b34fb");
    static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");
    static final int REQ_PERM = 11, REQ_BT = 12, REQ_FILE = 13;

    WebView web;
    final Handler ui = new Handler(Looper.getMainLooper());
    BluetoothAdapter adapter;
    BluetoothLeScanner scanner;
    BluetoothGatt gatt;
    BluetoothGattCharacteristic chr;
    String gattAddr;
    boolean scanning;
    ValueCallback<Uri[]> fileCb;
    HistoryStore hist;
    byte[] devBytes;
    volatile boolean licOk;
    String licJson = "{}";
    volatile boolean oldProto;
    String devName = "";

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        BluetoothManager bm = (BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE);
        adapter = bm != null ? bm.getAdapter() : null;
        hist = HistoryStore.get(this);
        String aid = null;
        try { aid = android.provider.Settings.Secure.getString(getContentResolver(), android.provider.Settings.Secure.ANDROID_ID); } catch (Exception e) { /* */ }
        devBytes = License.deviceBytes(aid == null ? "yok" : aid);
        loadLicense(getSharedPreferences("mgm", MODE_PRIVATE).getString("lisans", null));

        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(5, 8, 13));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setTextZoom(100);
        if (Build.VERSION.SDK_INT >= 21) s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        WebView.setWebContentsDebuggingEnabled(true);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.addJavascriptInterface(new Bridge(), "AndroidNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) {
                if (url.startsWith("file:")) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); } catch (Exception e) { /* */ }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (fileCb != null) fileCb.onReceiveValue(null);
                fileCb = cb;
                Intent i = new Intent(Intent.ACTION_GET_CONTENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("*/*");
                try { startActivityForResult(Intent.createChooser(i, "Dosya seç"), REQ_FILE); }
                catch (Exception e) { fileCb = null; return false; }
                return true;
            }
            @Override
            public boolean onConsoleMessage(ConsoleMessage m) { return super.onConsoleMessage(m); }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/www/index.html");
    }

    @Override
    public void onBackPressed() {
        web.evaluateJavascript("(window.__androidBack&&window.__androidBack())||false", new ValueCallback<String>() {
            public void onReceiveValue(String v) { if (!"true".equals(v)) moveTaskToBack(true); }
        });
    }

    @Override
    protected void onDestroy() {
        stopScanInt();
        closeGatt();
        super.onDestroy();
    }

    /* ------------------------------------------------------------ lisans */
    /** anahtarı doğrular; geçerliyse true. licJson arayüze gidecek durumu tutar */
    synchronized boolean loadLicense(String key) {
        String did = License.formatDevice(devBytes);
        if (key == null || key.trim().length() == 0) {
            licOk = false;
            licJson = "{\"ok\":false,\"device_id\":" + q(did) + "}";
            return false;
        }
        try {
            License.Info i = License.check(key, devBytes, License.today());
            licOk = true;
            licJson = "{\"ok\":true,\"device_id\":" + q(did) + ",\"name\":" + q(i.name) + ",\"factory\":" + i.factory + ",\"issued\":" + (i.issuedDay == 0 ? "null" : q(License.dayToIso(i.issuedDay)))
                    + ",\"expires\":" + (i.expiresDay == 0 ? "null" : q(License.dayToIso(i.expiresDay))) + "}";
            return true;
        } catch (IllegalArgumentException e) {
            licOk = false;
            licJson = "{\"ok\":false,\"device_id\":" + q(did) + ",\"error\":" + q(e.getMessage()) + "}";
            return false;
        }
    }

    /* ------------------------------------------------------------ JS'e olay */
    void send(final String type, final String json) {
        ui.post(new Runnable() { public void run() {
            if (web != null) web.evaluateJavascript("window.__nativeEvent&&window.__nativeEvent(" + q(type) + "," + json + ")", null);
        }});
    }

    static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c < 0x20 || c == 0x2028 || c == 0x2029) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        return b.append('"').toString();
    }

    static String hex(byte[] d) {
        char[] H = "0123456789abcdef".toCharArray();
        char[] o = new char[d.length * 2];
        for (int i = 0; i < d.length; i++) { o[2 * i] = H[(d[i] >> 4) & 15]; o[2 * i + 1] = H[d[i] & 15]; }
        return new String(o);
    }

    static byte[] unhex(String s) {
        byte[] o = new byte[s.length() / 2];
        for (int i = 0; i < o.length; i++) o[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
        return o;
    }

    /* ------------------------------------------------------------ izinler */
    String[] requestPerms() {
        String[] p = neededPerms();
        if (Build.VERSION.SDK_INT < 33) return p;
        String[] o = new String[p.length + 1];
        System.arraycopy(p, 0, o, 0, p.length);
        o[p.length] = "android.permission.POST_NOTIFICATIONS";
        return o;
    }

    String[] neededPerms() {
        if (Build.VERSION.SDK_INT >= 31)
            return new String[]{Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT};
        if (Build.VERSION.SDK_INT >= 23)
            return new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION};
        return new String[0];
    }

    boolean hasPerms() {
        if (Build.VERSION.SDK_INT < 23) return true;
        for (String p : neededPerms()) if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) return false;
        return true;
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] res) {
        if (code == REQ_PERM) send("perm", hasPerms() ? "true" : "false");
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == REQ_BT) {
            send("btEnable", adapter != null && adapter.isEnabled() ? "true" : "false");
        } else if (code == REQ_FILE) {
            Uri[] r = null;
            if (result == RESULT_OK && data != null && data.getData() != null) r = new Uri[]{data.getData()};
            if (fileCb != null) fileCb.onReceiveValue(r);
            fileCb = null;
        }
    }

    /* ------------------------------------------------------------ tarama */
    final ScanCallback scanCb = new ScanCallback() {
        @Override
        public void onScanResult(int type, ScanResult r) { report(r); }
        @Override
        public void onBatchScanResults(List<ScanResult> rs) { for (ScanResult r : rs) report(r); }
        @Override
        public void onScanFailed(int err) { send("scanError", q("Tarama başlatılamadı (kod " + err + ")")); }

        void report(ScanResult r) {
            BluetoothDevice d = r.getDevice();
            String name = null;
            StringBuilder uu = new StringBuilder("[");
            ScanRecord rec = r.getScanRecord();
            if (rec != null) {
                name = rec.getDeviceName();
                List<ParcelUuid> l = rec.getServiceUuids();
                if (l != null) for (int i = 0; i < l.size(); i++) {
                    if (i > 0) uu.append(',');
                    uu.append(q(l.get(i).getUuid().toString()));
                }
            }
            uu.append(']');
            if (name == null) {
                try { name = d.getName(); } catch (SecurityException e) { /* */ }
            }
            send("scan", "{\"id\":" + q(d.getAddress()) + ",\"name\":" + q(name == null ? "" : name)
                    + ",\"rssi\":" + r.getRssi() + ",\"uuids\":" + uu + "}");
        }
    };

    void stopScanInt() {
        if (scanning && scanner != null) {
            try { scanner.stopScan(scanCb); } catch (Exception e) { /* */ }
        }
        scanning = false;
    }

    /* ------------------------------------------------------------ GATT */
    void closeGatt() {
        if (BmsService.running || gatt != null) BmsService.stop(this);
        BluetoothGatt g = gatt;
        gatt = null; chr = null; gattAddr = null;
        if (g != null) {
            try { g.disconnect(); } catch (Exception e) { /* */ }
            try { g.close(); } catch (Exception e) { /* */ }
        }
    }

    final BluetoothGattCallback gattCb = new BluetoothGattCallback() {
        @Override
        public void onConnectionStateChange(BluetoothGatt g, int status, int state) {
            if (g != gatt) { try { g.close(); } catch (Exception e) { /* */ } return; }
            if (state == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS) {
                try {
                    if (!g.requestMtu(247)) g.discoverServices();
                } catch (SecurityException e) { fail("İzin yok: " + e.getMessage()); }
            } else {
                boolean wasReady = chr != null;
                closeGatt();
                if (wasReady) send("disconnected", "null");
                else send("connectError", q("Bağlantı kurulamadı (GATT " + status + ")"));
            }
        }

        @Override
        public void onMtuChanged(BluetoothGatt g, int mtu, int status) {
            try { g.discoverServices(); } catch (SecurityException e) { fail("İzin yok"); }
        }

        @Override
        public void onServicesDiscovered(BluetoothGatt g, int status) {
            BluetoothGattService s = g.getService(SERVICE);
            BluetoothGattCharacteristic c = s != null ? s.getCharacteristic(CHAR) : null;
            if (c == null) { fail("Bu cihazda JK BMS servisi (FFE0/FFE1) bulunamadı"); return; }
            chr = null;
            pending = c;
            try {
                g.setCharacteristicNotification(c, true);
                BluetoothGattDescriptor d = c.getDescriptor(CCCD);
                if (d != null) {
                    byte[] en = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE;
                    if (Build.VERSION.SDK_INT >= 33) g.writeDescriptor(d, en);
                    else { d.setValue(en); g.writeDescriptor(d); }
                } else ready(g, c);
            } catch (SecurityException e) { fail("İzin yok"); }
        }

        BluetoothGattCharacteristic pending;

        @Override
        public void onDescriptorWrite(BluetoothGatt g, BluetoothGattDescriptor d, int status) {
            if (pending != null && chr == null) ready(g, pending);
        }

        void ready(BluetoothGatt g, BluetoothGattCharacteristic c) {
            chr = c;
            try { g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH); } catch (Exception e) { /* */ }
            oldProto = false;
            try { String n = g.getDevice().getName(); if (n != null) devName = n; } catch (SecurityException e) { /* */ }
            BmsService.start(MainActivity.this, devName);
            send("connected", q(g.getDevice().getAddress()));
        }

        void fail(String msg) {
            closeGatt();
            send("connectError", q(msg));
        }

        @Override
        public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c, byte[] v) {
            if (v == null || v.length == 0) return;
            hist.feed(v, !oldProto);
            send("data", q(hex(v)));
        }

        @SuppressWarnings("deprecation")
        @Override
        public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c) {
            byte[] v = c.getValue();
            if (v == null || v.length == 0) return;
            hist.feed(v, !oldProto);
            send("data", q(hex(v)));
        }

        @Override
        public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic c, int status) {
            send("written", status == BluetoothGatt.GATT_SUCCESS ? "true" : "false");
        }
    };

    /* ------------------------------------------------------------ JS köprüsü */
    class Bridge {
        @JavascriptInterface
        public boolean available() { return adapter != null; }

        @JavascriptInterface
        public boolean isEnabled() { return adapter != null && adapter.isEnabled(); }

        @JavascriptInterface
        public boolean hasPermissions() { return hasPerms(); }

        @JavascriptInterface
        public void requestPermissions() {
            ui.post(new Runnable() { public void run() {
                if (hasPerms() || Build.VERSION.SDK_INT < 23) send("perm", "true");
                else MainActivity.this.requestPermissions(requestPerms(), REQ_PERM);
            }});
        }

        @JavascriptInterface
        public void requestEnable() {
            ui.post(new Runnable() { public void run() {
                try { startActivityForResult(new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE), REQ_BT); }
                catch (Exception e) { send("btEnable", "false"); }
            }});
        }

        @JavascriptInterface
        public String licenseInfo() { return licJson; }

        @JavascriptInterface
        public String activate(String key) {
            String prev = licJson;
            if (loadLicense(key)) {
                getSharedPreferences("mgm", MODE_PRIVATE).edit().putString("lisans", key.trim()).apply();
                return licJson;
            }
            String res = licJson;
            // önceki geçerli lisans varsa onu koru
            String old = getSharedPreferences("mgm", MODE_PRIVATE).getString("lisans", null);
            if (old != null) loadLicense(old); else licJson = prev;
            return res;
        }

        @JavascriptInterface
        public String startScan() {
            if (!licOk) return "Lisans gerekli – önce uygulamayı etkinleştirin";
            if (adapter == null || !adapter.isEnabled()) return "Bluetooth kapalı";
            if (!hasPerms()) return "Bluetooth izni verilmedi";
            try {
                scanner = adapter.getBluetoothLeScanner();
                if (scanner == null) return "Tarayıcı kullanılamıyor";
                stopScanInt();
                ScanSettings st = new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build();
                scanner.startScan(null, st, scanCb);
                scanning = true;
                return "";
            } catch (SecurityException e) {
                return "İzin hatası: " + e.getMessage();
            } catch (Exception e) {
                return "Tarama hatası: " + e.getMessage();
            }
        }

        @JavascriptInterface
        public void stopScan() { stopScanInt(); }

        @JavascriptInterface
        public String connect(String addr) {
            if (!licOk) return "Lisans gerekli – önce uygulamayı etkinleştirin";
            if (adapter == null || !adapter.isEnabled()) return "Bluetooth kapalı";
            stopScanInt();
            try {
                closeGatt();
                BluetoothDevice d = adapter.getRemoteDevice(addr);
                gattAddr = addr;
                if (Build.VERSION.SDK_INT >= 23)
                    gatt = d.connectGatt(MainActivity.this, false, gattCb, BluetoothDevice.TRANSPORT_LE);
                else gatt = d.connectGatt(MainActivity.this, false, gattCb);
                return gatt == null ? "Bağlantı başlatılamadı" : "";
            } catch (SecurityException e) {
                return "İzin hatası: " + e.getMessage();
            } catch (Exception e) {
                return "Bağlantı hatası: " + e.getMessage();
            }
        }

        @JavascriptInterface
        public void disconnect() { closeGatt(); }

        @SuppressWarnings("deprecation")
        @JavascriptInterface
        public String write(String hexData, boolean withResponse) {
            BluetoothGatt g = gatt;
            BluetoothGattCharacteristic c = chr;
            if (g == null || c == null) return "Bağlı değil";
            byte[] v = unhex(hexData);
            int type = withResponse ? BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT : BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE;
            try {
                if (Build.VERSION.SDK_INT >= 33) {
                    int r = g.writeCharacteristic(c, v, type);
                    return r == 0 ? "" : "Yazma reddedildi (" + r + ")";
                }
                c.setWriteType(type);
                c.setValue(v);
                return g.writeCharacteristic(c) ? "" : "Yazma reddedildi";
            } catch (SecurityException e) {
                return "İzin hatası";
            }
        }

        @JavascriptInterface
        public void keepScreenOn(final boolean on) {
            ui.post(new Runnable() { public void run() {
                if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            }});
        }

        @JavascriptInterface
        public void toast(final String msg) {
            ui.post(new Runnable() { public void run() { Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show(); }});
        }

        /** Dosyayı İndirilenler/MGM BMS klasörüne kaydeder, sonra paylaşma menüsünü açar. Dönüş: yol ya da "HATA:..." */
        @JavascriptInterface
        public String saveFile(final String name, final String text, final String mime, final boolean share) {
            byte[] data = text.getBytes(Charset.forName("UTF-8"));
            Uri uri = null;
            String where;
            try {
                if (Build.VERSION.SDK_INT >= 29) {
                    ContentResolver cr = getContentResolver();
                    ContentValues cv = new ContentValues();
                    cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                    cv.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                    cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/MGM BMS");
                    uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                    if (uri == null) throw new Exception("MediaStore kaydı oluşturulamadı");
                    OutputStream os = cr.openOutputStream(uri);
                    os.write(data);
                    os.close();
                    where = "İndirilenler/MGM BMS/" + name;
                } else {
                    File dir = getExternalFilesDir(null);
                    if (dir == null) dir = getFilesDir();
                    File f = new File(dir, name);
                    FileOutputStream os = new FileOutputStream(f);
                    os.write(data);
                    os.close();
                    where = f.getAbsolutePath();
                }
            } catch (Exception e) {
                return "HATA:" + e.getMessage();
            }
            final Uri u = uri;
            final String w = where;
            ui.post(new Runnable() { public void run() {
                Toast.makeText(MainActivity.this, "Kaydedildi: " + w, Toast.LENGTH_LONG).show();
                if (!share) return;
                try {
                    Intent i = new Intent(Intent.ACTION_SEND);
                    if (u != null) {
                        i.setType(mime);
                        i.putExtra(Intent.EXTRA_STREAM, u);
                        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    } else {
                        i.setType("text/plain");
                        i.putExtra(Intent.EXTRA_TEXT, text.length() > 90000 ? text.substring(0, 90000) : text);
                    }
                    i.putExtra(Intent.EXTRA_SUBJECT, name);
                    startActivity(Intent.createChooser(i, "Paylaş: " + name));
                } catch (Exception e) { /* paylaşım yoksa sadece kaydedildi */ }
            }});
            return where;
        }

        /* ---------------- 24 saat kaydı */
        @JavascriptInterface
        public String histInfo() { return hist.infoJson(); }

        @JavascriptInterface
        public String histRows() { return hist.chartJson(); }

        @JavascriptInterface
        public boolean histEnable(boolean on) { return hist.setEnabled(on); }

        @JavascriptInterface
        public boolean histClear() { hist.clear(); return true; }

        /** eski (24S) protokol: çözümlemeyi JS yapar, satırı buraya yollar */
        @JavascriptInterface
        public void histAdd(String rowWithoutTime) { if (oldProto) hist.addFromJs(rowWithoutTime); }

        @JavascriptInterface
        public void setOldProtocol(boolean old) { oldProto = old; }

        @JavascriptInterface
        public void setDeviceName(String n) {
            if (n == null || n.length() == 0) return;
            devName = n; BmsService.deviceName = n;
        }

        /** CSV'yi arka planda İndirilenler/MGM BMS'e yazar; sonuç "histExport" olayıyla gelir */
        @JavascriptInterface
        public void histExport(final String name) {
            new Thread(new Runnable() { public void run() {
                String res;
                try {
                    if (hist.count() == 0) throw new Exception("Kayıtta henüz veri yok");
                    Uri uri = null; String where; OutputStream os; int n;
                    if (Build.VERSION.SDK_INT >= 29) {
                        ContentResolver cr = getContentResolver();
                        ContentValues cv = new ContentValues();
                        cv.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                        cv.put(MediaStore.MediaColumns.MIME_TYPE, "text/csv");
                        cv.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/MGM BMS");
                        uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
                        if (uri == null) throw new Exception("MediaStore kaydı oluşturulamadı");
                        os = cr.openOutputStream(uri);
                        where = "İndirilenler/MGM BMS/" + name;
                    } else {
                        File dir = getExternalFilesDir(null);
                        if (dir == null) dir = getFilesDir();
                        File f = new File(dir, name);
                        os = new FileOutputStream(f);
                        where = f.getAbsolutePath();
                    }
                    n = hist.exportCsv(os);
                    os.close();
                    res = "{\"ok\":true,\"count\":" + n + ",\"file\":" + q(where) + "}";
                    final Uri u = uri;
                    if (u != null) ui.post(new Runnable() { public void run() {
                        try {
                            Intent i = new Intent(Intent.ACTION_SEND).setType("text/csv").putExtra(Intent.EXTRA_STREAM, u)
                                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION).putExtra(Intent.EXTRA_SUBJECT, name);
                            startActivity(Intent.createChooser(i, "Paylaş: " + name));
                        } catch (Exception e) { /* */ }
                    }});
                } catch (Exception e) {
                    res = "{\"ok\":false,\"error\":" + q(String.valueOf(e.getMessage())) + "}";
                }
                send("histExport", res);
            }}).start();
        }

        @JavascriptInterface
        public String version() {
            try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionName; }
            catch (Exception e) { return "?"; }
        }
    }
}
