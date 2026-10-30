package com.mgm.bms;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

import java.util.Locale;

/**
 * BMS'e bağlıyken çalışan ön plan servisi: uygulama arka plandayken ya da ekran kapalıyken
 * Android'in işlemi durdurmasını engeller, böylece Bluetooth verisi ve 24 saat kaydı kesilmez.
 * Bildirimde canlı gerilim / akım / SOC gösterilir.
 */
public class BmsService extends Service {
    static final String CH = "mgm_bms_bg";
    static final int ID = 7;
    static String deviceName = "BMS";
    static boolean running;

    PowerManager.WakeLock wl;
    final Handler h = new Handler(Looper.getMainLooper());
    final Runnable tick = new Runnable() {
        public void run() {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            try { nm.notify(ID, build()); } catch (Exception e) { /* */ }
            h.postDelayed(this, 10000);
        }
    };

    static void start(Context c, String name) {
        if (name != null && name.length() > 0) deviceName = name;
        Intent i = new Intent(c, BmsService.class);
        try {
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Exception e) { /* arka plandan başlatma kısıtı vb. */ }
    }

    static void stop(Context c) {
        try { c.stopService(new Intent(c, BmsService.class)); } catch (Exception e) { /* */ }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CH, "Arka planda bağlantı", NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("BMS bağlıyken veri almaya ve 24 saat kaydına devam eder");
            ch.setShowBadge(false);
            ((NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE)).createNotificationChannel(ch);
        }
    }

    Notification build() {
        HistoryStore hs = HistoryStore.get(this);
        String text;
        if (hs.lastSoc >= 0)
            text = String.format(Locale.US, "%.2f V · %+.2f A · %%%d", hs.lastV, hs.lastA, hs.lastSoc)
                    + (hs.enabled ? " · kaydediliyor" : "");
        else text = hs.enabled ? "Bağlı · 24 saat kaydı açık" : "Bağlı";
        Intent open = new Intent(this, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, Build.VERSION.SDK_INT >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CH) : new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
                .setContentTitle("MGM BMS – " + deviceName)
                .setContentText(text)
                .setContentIntent(pi)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false);
        if (Build.VERSION.SDK_INT < 26) b.setPriority(Notification.PRIORITY_LOW);
        return b.build();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            if (Build.VERSION.SDK_INT >= 29)
                startForeground(ID, build(), ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
            else startForeground(ID, build());
        } catch (Exception e) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (wl == null) {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "mgmbms:ble");
            wl.setReferenceCounted(false);
            wl.acquire(26L * 3600 * 1000);
        }
        running = true;
        h.removeCallbacks(tick);
        h.postDelayed(tick, 3000);
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        h.removeCallbacks(tick);
        if (wl != null && wl.isHeld()) wl.release();
        wl = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent i) { return null; }
}
