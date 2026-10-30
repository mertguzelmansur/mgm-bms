package com.mgm.bms;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.Charset;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Locale;

/**
 * Son 24 saatlik ölçüm kaydı (masaüstü gecmis.py ile aynı biçim).
 * Dosya: uygulama klasörü/gecmis_24s.jsonl – her satır:
 * [zaman_ms, V, A, W, fark_mV, SOC, MOS, T1, T2, kalan_Ah, [hücre_mV...]]
 * Bellekte yalnızca grafik için gereken ilk 9 alan tutulur; hücreler dosyada kalır.
 */
public class HistoryStore {
    static final long KEEP_MS = 24L * 3600 * 1000;
    static final long MIN_STEP_MS = 1000;
    static final long COMPACT_EVERY_MS = 30L * 60 * 1000;
    static final long FULL_RES_MS = 2L * 3600 * 1000;
    static final long OLD_STEP_MS = 5000;
    static final Charset UTF8 = Charset.forName("UTF-8");

    private static HistoryStore inst;

    static synchronized HistoryStore get(Context c) {
        if (inst == null) inst = new HistoryStore(c.getApplicationContext());
        return inst;
    }

    final File file;
    final SharedPreferences prefs;
    boolean enabled;
    final ArrayList<Long> times = new ArrayList<>();
    final ArrayList<String> chart = new ArrayList<>();
    long lastT, lastCompact;
    Writer out;
    /** son kaydedilen değerler (bildirim için) */
    double lastV, lastA;
    int lastSoc = -1;

    private HistoryStore(Context c) {
        file = new File(c.getFilesDir(), "gecmis_24s.jsonl");
        prefs = c.getSharedPreferences("mgm", Context.MODE_PRIVATE);
        enabled = prefs.getBoolean("kayit_24s", true);
        load();
    }

    /* ------------------------------------------------------------ dosya */
    private synchronized void load() {
        times.clear();
        chart.clear();
        long cut = System.currentTimeMillis() - KEEP_MS;
        if (file.exists()) {
            try {
                BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(file), UTF8));
                String line;
                while ((line = r.readLine()) != null) {
                    long t = timeOf(line);
                    String ch = chartPart(line);
                    if (t >= cut && ch != null) { times.add(t); chart.add(ch); }
                }
                r.close();
            } catch (Exception e) { /* bozuk dosya: okunabildiği kadar */ }
        }
        if (!times.isEmpty()) lastT = times.get(times.size() - 1);
        rewrite(cut);
    }

    static long timeOf(String line) {
        try {
            int c = line.indexOf(',');
            if (!line.startsWith("[") || c < 2) return -1;
            return Long.parseLong(line.substring(1, c));
        } catch (Exception e) { return -1; }
    }

    /** "[t,V,A,W,d,soc,mos,t1,t2,kalan,[..]]" → "[t,V,A,W,d,soc,mos,t1,t2]" */
    static String chartPart(String line) {
        int n = 0;
        for (int i = 0; i < line.length(); i++) {
            if (line.charAt(i) == ',' && ++n == 9) return line.substring(0, i) + "]";
        }
        return null;
    }

    /** eski satırları atarak dosyayı yeniden yazar */
    private synchronized void rewrite(long cut) {
        try {
            if (out != null) { out.close(); out = null; }
            File tmp = new File(file.getPath() + ".tmp");
            Writer w = new OutputStreamWriter(new FileOutputStream(tmp), UTF8);
            if (file.exists()) {
                BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(file), UTF8));
                String line;
                while ((line = r.readLine()) != null) {
                    long t = timeOf(line);
                    if (t >= cut && chartPart(line) != null) w.write(line + "\n");
                }
                r.close();
            }
            w.close();
            if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file); }
        } catch (Exception e) { /* */ }
        int i = 0;
        while (i < times.size() && times.get(i) < cut) i++;
        if (i > 0) { times.subList(0, i).clear(); chart.subList(0, i).clear(); }
        lastCompact = System.currentTimeMillis();
    }

    /* ------------------------------------------------------------ kayıt */
    static String num(double v, int dec) {
        if (dec == 0) return Long.toString(Math.round(v));
        String s = String.format(Locale.US, "%." + dec + "f", v);
        if (s.indexOf('.') >= 0) { s = s.replaceAll("0+$", ""); if (s.endsWith(".")) s += "0"; }
        return s;
    }

    static String tmp(Double v) { return v == null ? "null" : num(v, 1); }

    /** satır = tam JSON satırı; true: kaydedildi */
    synchronized boolean addLine(String line) {
        if (!enabled) return false;
        long now = System.currentTimeMillis();
        if (now - lastT < MIN_STEP_MS) return false;
        String ch = chartPart(line);
        long t = timeOf(line);
        if (ch == null || t <= 0) return false;
        lastT = now;
        times.add(t);
        chart.add(ch);
        try {
            if (out == null) out = new OutputStreamWriter(new FileOutputStream(file, true), UTF8);
            out.write(line + "\n");
            out.flush();
        } catch (Exception e) { /* */ }
        if (now - lastCompact > COMPACT_EVERY_MS) rewrite(now - KEEP_MS);
        return true;
    }

    /** JS'ten gelen satır (eski 24S protokolü için) – zaman damgasını burada koyarız */
    boolean addFromJs(String rowWithoutTime) {
        // rowWithoutTime: "V,A,W,fark,soc,mos,t1,t2,kalan,[hücreler]"
        return addLine("[" + System.currentTimeMillis() + "," + rowWithoutTime + "]");
    }

    /* ------------------------------------------------------------ çerçeve çözümleme (yeni protokol, tip 02) */
    final byte[] buf = new byte[4096];
    int bufLen;
    static final byte[] HDR = {0x55, (byte) 0xAA, (byte) 0xEB, (byte) 0x90};

    /** BLE bildirim parçalarını birleştirir; hücre çerçevesi çıkınca kaydeder */
    synchronized void feed(byte[] d, boolean record) {
        if (d.length >= 4 && d[0] == HDR[0] && d[1] == HDR[1] && d[2] == HDR[2] && d[3] == HDR[3]) bufLen = 0;
        if (bufLen + d.length > buf.length) bufLen = 0;
        System.arraycopy(d, 0, buf, bufLen, d.length);
        bufLen += d.length;
        while (true) {
            int i = find();
            if (i < 0) { if (bufLen > 3) { System.arraycopy(buf, bufLen - 3, buf, 0, 3); bufLen = 3; } break; }
            if (i > 0) { System.arraycopy(buf, i, buf, 0, bufLen - i); bufLen -= i; }
            if (bufLen < 300) break;
            int sum = 0;
            for (int k = 0; k < 299; k++) sum += buf[k] & 0xFF;
            boolean ok = (sum & 0xFF) == (buf[299] & 0xFF);
            if (ok && buf[4] == 2 && record) recordCells(buf);
            int drop = ok || buf[4] == 6 ? 300 : 4;
            System.arraycopy(buf, drop, buf, 0, bufLen - drop);
            bufLen -= drop;
        }
    }

    private int find() {
        outer:
        for (int i = 0; i + 4 <= bufLen; i++) {
            for (int k = 0; k < 4; k++) if (buf[i + k] != HDR[k]) continue outer;
            return i;
        }
        return -1;
    }

    static int u8(byte[] f, int o) { return f[6 + o] & 0xFF; }
    static int u16(byte[] f, int o) { return u8(f, o) | (u8(f, o + 1) << 8); }
    static int s16(byte[] f, int o) { return (short) u16(f, o); }
    static long u32(byte[] f, int o) { return (u16(f, o) | ((long) u16(f, o + 2) << 16)) & 0xFFFFFFFFL; }
    static int s32(byte[] f, int o) { return (int) u32(f, o); }
    static Double temp(byte[] f, int o) { int v = s16(f, o); return v <= -2000 || v >= 2000 ? null : v / 10.0; }

    private void recordCells(byte[] f) {
        long mask = u32(f, 64);
        StringBuilder cells = new StringBuilder("[");
        int n = 0;
        for (int i = 0; i < 32; i++) {
            boolean on = mask != 0 ? ((mask >> i) & 1) == 1 : u16(f, i * 2) != 0;
            if (!on) continue;
            if (n++ > 0) cells.append(',');
            cells.append(u16(f, i * 2));
        }
        cells.append(']');
        double v = u32(f, 144) / 1000.0, p = u32(f, 148) / 1000.0, a = s32(f, 152) / 1000.0;
        int soc = u8(f, 167);
        String line = "[" + System.currentTimeMillis() + "," + num(v, 3) + "," + num(a, 3) + "," + num(p, 1) + ","
                + u16(f, 70) + "," + soc + "," + tmp(temp(f, 138)) + "," + tmp(temp(f, 156)) + "," + tmp(temp(f, 158)) + ","
                + num(u32(f, 168) / 1000.0, 3) + "," + cells + "]";
        if (addLine(line)) { lastV = v; lastA = a; lastSoc = soc; }
    }

    /* ------------------------------------------------------------ arayüze */
    synchronized String infoJson() {
        long cut = System.currentTimeMillis() - KEEP_MS;
        int i = 0;
        while (i < times.size() && times.get(i) < cut) i++;
        if (i > 0) { times.subList(0, i).clear(); chart.subList(0, i).clear(); }
        int n = times.size();
        return "{\"count\":" + n + ",\"first\":" + (n > 0 ? times.get(0) : "null") + ",\"last\":" + (n > 0 ? times.get(n - 1) : "null")
                + ",\"bytes\":" + (file.exists() ? file.length() : 0) + ",\"enabled\":" + enabled + "}";
    }

    synchronized String chartJson() {
        long edge = System.currentTimeMillis() - FULL_RES_MS, cut = System.currentTimeMillis() - KEEP_MS, last = Long.MIN_VALUE / 2;
        StringBuilder b = new StringBuilder(chart.size() * 64 + 2).append('[');
        boolean first = true;
        for (int i = 0; i < times.size(); i++) {
            long t = times.get(i);
            if (t < cut) continue;
            if (t < edge && t - last < OLD_STEP_MS) continue;
            last = t;
            if (!first) b.append(',');
            b.append(chart.get(i));
            first = false;
        }
        return b.append(']').toString();
    }

    synchronized boolean setEnabled(boolean on) {
        enabled = on;
        prefs.edit().putBoolean("kayit_24s", on).apply();
        return enabled;
    }

    synchronized void clear() {
        times.clear();
        chart.clear();
        lastT = 0;
        try { if (out != null) { out.close(); out = null; } } catch (Exception e) { /* */ }
        file.delete();
        lastCompact = System.currentTimeMillis();
    }

    synchronized int count() { return times.size(); }

    /** tüm kaydı CSV olarak yazar; satır sayısını döndürür */
    int exportCsv(OutputStream os) throws Exception {
        synchronized (this) { try { if (out != null) out.flush(); } catch (Exception e) { /* */ } }
        long cut = System.currentTimeMillis() - KEEP_MS;
        ArrayList<String> lines = new ArrayList<>();
        int ncell = 0;
        synchronized (this) {
            if (file.exists()) {
                BufferedReader r = new BufferedReader(new InputStreamReader(new FileInputStream(file), UTF8));
                String line;
                while ((line = r.readLine()) != null) if (timeOf(line) >= cut && chartPart(line) != null) lines.add(line);
                r.close();
            }
        }
        Writer w = new OutputStreamWriter(os, UTF8);
        w.write("﻿");
        ArrayList<JSONArray> rows = new ArrayList<>();
        for (String l : lines) {
            try { JSONArray a = new JSONArray(l); rows.add(a); JSONArray c = a.optJSONArray(10); if (c != null) ncell = Math.max(ncell, c.length()); }
            catch (Exception e) { /* */ }
        }
        StringBuilder h = new StringBuilder("zaman;gerilim_V;akim_A;guc_W;fark_mV;SOC_%;MOS_C;T1_C;T2_C;kalan_Ah");
        for (int i = 1; i <= ncell; i++) h.append(";hucre").append(i).append("_V");
        w.write(h.append("\r\n").toString());
        SimpleDateFormat df = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);
        for (JSONArray a : rows) {
            StringBuilder s = new StringBuilder(df.format(new Date(a.getLong(0))));
            for (int k = 1; k < 10; k++) { s.append(';'); if (!a.isNull(k)) s.append(a.get(k).toString()); }
            JSONArray c = a.optJSONArray(10);
            if (c != null) for (int k = 0; k < c.length(); k++) s.append(';').append(String.format(Locale.US, "%.3f", c.getInt(k) / 1000.0));
            w.write(s.append("\r\n").toString());
        }
        w.flush();
        return rows.size();
    }
}
