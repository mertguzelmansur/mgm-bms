package com.mgm.bms;

import java.math.BigInteger;
import java.nio.charset.Charset;
import java.security.MessageDigest;
import java.util.Arrays;

/**
 * MGM BMS lisans doğrulama – masaüstü lisans.py ile birebir aynı biçim.
 * Anahtar: "MGM1-" + base32(yük || Ed25519 imza), imza = Ed25519("MGMBMS-LIC" || yük).
 * Uygulamada yalnızca açık anahtar vardır (yeni anahtar üretilemez).
 * Bu sınıf Android'e bağımlı değildir (JVM'de de test edilebilir).
 */
public final class License {
    static final String PUBLIC_KEY_HEX = "1fc74cf8d65e33d596138f11eed649d83f36350ccde6746b9e2926c8382bbca4";
    static final byte[] DOMAIN = "MGMBMS-LIC".getBytes(Charset.forName("US-ASCII"));

    // kısa anahtar doğrulama anahtarı: depoda YOK, LicenseKey.java içinde (araclar/gizli_dosyalari_olustur.py üretir)
    static final String SK_A = LicenseKey.A, SK_B = LicenseKey.B;
    static final byte[] SHORT_DOMAIN = "MGMBMS-SHORT".getBytes(Charset.forName("US-ASCII"));

    public static final class Info {
        public String name;
        public boolean factory;
        public int issuedDay, expiresDay;     // 2024-01-01'den itibaren gün (0 = süresiz)
    }

    /* ------------------------------------------------------------ cihaz kimliği */
    public static byte[] deviceBytes(String androidId) {
        try {
            byte[] h = MessageDigest.getInstance("SHA-256").digest(("MGM-BMS|android|" + androidId).getBytes(Charset.forName("UTF-8")));
            return Arrays.copyOf(h, 10);
        } catch (Exception e) { throw new RuntimeException(e); }
    }

    public static String formatDevice(byte[] d) {
        String s = b32(d);
        return "MGM-" + s.substring(0, 4) + "-" + s.substring(4, 8) + "-" + s.substring(8, 12) + "-" + s.substring(12, 16);
    }

    /* ------------------------------------------------------------ anahtar doğrulama */
    /** geçerliyse Info döndürür, değilse Türkçe mesajlı IllegalArgumentException fırlatır */
    public static Info check(String key, byte[] device, int todayDay) {
        String sh = cleanShort(key);
        if (sh.length() == 8) return checkKey8(sh, device, todayDay);
        if (sh.length() == 20 && !sh.startsWith("MGM1")) return checkShort(sh, device, todayDay);
        StringBuilder sb = new StringBuilder();
        for (char c : key.toUpperCase().toCharArray()) if (Character.isLetterOrDigit(c) && c < 128) sb.append(c);
        String s = sb.toString();
        if (!s.startsWith("MGM1")) throw new IllegalArgumentException("Anahtar tanınmadı – XXXX-XXXX biçiminde olmalı");
        byte[] raw;
        try { raw = unb32(s.substring(4)); } catch (Exception e) { throw new IllegalArgumentException("Anahtar eksik ya da hatalı kopyalanmış"); }
        if (raw.length < 16 + 64) throw new IllegalArgumentException("Anahtar eksik ya da hatalı kopyalanmış");
        byte[] payload = Arrays.copyOf(raw, raw.length - 64), sig = Arrays.copyOfRange(raw, raw.length - 64, raw.length);
        int n = payload[15] & 0xFF;
        if (payload[0] != 1 || payload.length != 16 + n) throw new IllegalArgumentException("Anahtar biçimi tanınmadı");
        byte[] msg = new byte[DOMAIN.length + payload.length];
        System.arraycopy(DOMAIN, 0, msg, 0, DOMAIN.length);
        System.arraycopy(payload, 0, msg, DOMAIN.length, payload.length);
        if (!verify(hex(PUBLIC_KEY_HEX), msg, sig)) throw new IllegalArgumentException("Geçersiz lisans anahtarı");
        if (!Arrays.equals(Arrays.copyOfRange(payload, 1, 11), device))
            throw new IllegalArgumentException("Bu anahtar başka bir cihaz için üretilmiş");
        Info i = new Info();
        i.issuedDay = (payload[11] & 0xFF) | (payload[12] & 0xFF) << 8;
        i.expiresDay = (payload[13] & 0xFF) | (payload[14] & 0xFF) << 8;
        i.name = new String(payload, 16, n, Charset.forName("UTF-8"));
        if (i.expiresDay != 0 && todayDay > i.expiresDay)
            throw new IllegalArgumentException("Lisans süresi " + dayToText(i.expiresDay) + " tarihinde doldu");
        return i;
    }

    /* ------------------------------------------------------------ kısa anahtar / fabrika kodu (lisans.py ile aynı) */
    static String cleanShort(String key) {
        StringBuilder b = new StringBuilder();
        for (char c : key.toUpperCase(java.util.Locale.US).toCharArray()) {
            if (c >= 128 || !Character.isLetterOrDigit(c)) continue;
            b.append(c == '0' ? 'O' : c == '1' ? 'I' : c == '8' ? 'B' : c == '9' ? 'G' : c);
        }
        return b.toString();
    }

    static byte[] shortMac(byte[] hk, int kind, int exp, byte[] dev) throws Exception {
        javax.crypto.Mac m = javax.crypto.Mac.getInstance("HmacSHA256");
        m.init(new javax.crypto.spec.SecretKeySpec(hk, "HmacSHA256"));
        m.update(SHORT_DOMAIN);
        m.update(new byte[]{(byte) kind, (byte) exp, (byte) (exp >> 8)});
        if (kind == 1) m.update(dev);
        return Arrays.copyOf(m.doFinal(), 9);
    }

    /* ------------------------------------------------------------ 8 karakter "XXXX-XXXX" (lisans.py check_key8) */
    static byte[] hk() {
        byte[] a = hex(SK_A), b = hex(SK_B), k = new byte[32];
        for (int i = 0; i < 32; i++) k[i] = (byte) (a[i] ^ b[i]);
        return k;
    }

    static byte[] mac8(byte[] hk, int kind, int month, byte[] dev) throws Exception {
        javax.crypto.Mac m = javax.crypto.Mac.getInstance("HmacSHA256");
        m.init(new javax.crypto.spec.SecretKeySpec(hk, "HmacSHA256"));
        m.update("MGMBMS-K8".getBytes(Charset.forName("US-ASCII")));
        m.update(new byte[]{(byte) kind, (byte) month});
        if (kind == 1) m.update(dev);
        return Arrays.copyOf(m.doFinal(), 4);
    }

    /** ayın (1 = Ocak 2024) son günü, 2024-01-01'den gün olarak */
    static int monthEndDay(int month) {
        java.util.Calendar c = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        c.clear();
        c.set(2024, 0, 1);
        c.add(java.util.Calendar.MONTH, month);           // sonraki ayın 1'i
        c.add(java.util.Calendar.DAY_OF_MONTH, -1);
        java.util.Calendar e = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        e.clear();
        e.set(2024, 0, 1);
        return (int) ((c.getTimeInMillis() - e.getTimeInMillis()) / 86400000L);
    }

    static Info checkKey8(String s, byte[] device, int todayDay) {
        byte[] raw;
        try { raw = unb32(s); } catch (Exception e) { throw new IllegalArgumentException("Anahtarda geçersiz karakter var"); }
        if (raw.length != 5) throw new IllegalArgumentException("Geçersiz lisans anahtarı");
        byte[] mac = Arrays.copyOf(raw, 4);
        int kind = 0, month;
        try {
            month = (raw[4] ^ MessageDigest.getInstance("SHA-256").digest(mac)[0]) & 0xFF;
            byte[] k = hk();
            if (MessageDigest.isEqual(mac, mac8(k, 1, month, device))) kind = 1;
            else if (MessageDigest.isEqual(mac, mac8(k, 2, month, device))) kind = 2;
        } catch (Exception e) { throw new IllegalArgumentException("Geçersiz lisans anahtarı"); }
        if (kind == 0) throw new IllegalArgumentException("Geçersiz anahtar ya da başka bir cihaz için üretilmiş");
        int exp = month == 0 ? 0 : monthEndDay(month);
        if (exp != 0 && todayDay > exp) throw new IllegalArgumentException("Lisans süresi " + dayToText(exp) + " tarihinde doldu");
        Info i = new Info();
        i.factory = kind == 2;
        i.name = i.factory ? "Fabrika lisansı" : "Cihaz lisansı";
        i.expiresDay = exp;
        return i;
    }

    static Info checkShort(String s, byte[] device, int todayDay) {
        byte[] raw;
        try { raw = Arrays.copyOf(unb32(s), 12); } catch (Exception e) { throw new IllegalArgumentException("Anahtarda geçersiz karakter var"); }
        if (!b32(raw).equals(s)) throw new IllegalArgumentException("Geçersiz lisans anahtarı");
        byte[] mac = Arrays.copyOf(raw, 9), head = new byte[3];
        try {
            byte[] w = MessageDigest.getInstance("SHA-256").digest(mac);
            for (int i = 0; i < 3; i++) head[i] = (byte) (raw[9 + i] ^ w[i]);
        } catch (Exception e) { throw new RuntimeException(e); }
        int kind = head[0] & 0xFF, exp = (head[1] & 0xFF) | (head[2] & 0xFF) << 8;
        boolean ok = false;
        if (kind == 1 || kind == 2) {
            try {
                byte[] a = hex(SK_A), b = hex(SK_B), hk = new byte[32];
                for (int i = 0; i < 32; i++) hk[i] = (byte) (a[i] ^ b[i]);
                ok = MessageDigest.isEqual(mac, shortMac(hk, kind, exp, device));
            } catch (Exception e) { ok = false; }
        }
        if (!ok) throw new IllegalArgumentException(kind == 1 ? "Geçersiz anahtar ya da başka bir cihaz için üretilmiş" : "Geçersiz lisans anahtarı");
        if (exp != 0 && todayDay > exp) throw new IllegalArgumentException("Lisans süresi " + dayToText(exp) + " tarihinde doldu");
        Info i = new Info();
        i.factory = kind == 2;
        i.name = i.factory ? "Fabrika lisansı" : "Cihaz lisansı";
        i.issuedDay = 0;
        i.expiresDay = exp;
        return i;
    }

    /** 2024-01-01 + gün → "GG.AA.YYYY" */
    public static String dayToText(int day) {
        java.util.Calendar c = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        c.clear();
        c.set(2024, 0, 1);
        c.add(java.util.Calendar.DAY_OF_MONTH, day);
        return String.format(java.util.Locale.US, "%02d.%02d.%04d", c.get(java.util.Calendar.DAY_OF_MONTH), c.get(java.util.Calendar.MONTH) + 1, c.get(java.util.Calendar.YEAR));
    }

    public static String dayToIso(int day) {
        java.util.Calendar c = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        c.clear();
        c.set(2024, 0, 1);
        c.add(java.util.Calendar.DAY_OF_MONTH, day);
        return String.format(java.util.Locale.US, "%04d-%02d-%02d", c.get(java.util.Calendar.YEAR), c.get(java.util.Calendar.MONTH) + 1, c.get(java.util.Calendar.DAY_OF_MONTH));
    }

    /** yerel tarihe göre 2024-01-01'den bugüne gün */
    public static int today() {
        java.util.Calendar now = java.util.Calendar.getInstance();
        java.util.Calendar c = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        c.clear();
        c.set(now.get(java.util.Calendar.YEAR), now.get(java.util.Calendar.MONTH), now.get(java.util.Calendar.DAY_OF_MONTH));
        java.util.Calendar e = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        e.clear();
        e.set(2024, 0, 1);
        return (int) ((c.getTimeInMillis() - e.getTimeInMillis()) / 86400000L);
    }

    /* ------------------------------------------------------------ base32 / hex */
    static final String A32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

    static String b32(byte[] d) {
        StringBuilder o = new StringBuilder();
        int buf = 0, bits = 0;
        for (byte b : d) {
            buf = (buf << 8) | (b & 0xFF);
            bits += 8;
            while (bits >= 5) { o.append(A32.charAt((buf >> (bits - 5)) & 31)); bits -= 5; }
        }
        if (bits > 0) o.append(A32.charAt((buf << (5 - bits)) & 31));
        return o.toString();
    }

    static byte[] unb32(String s) {
        byte[] out = new byte[s.length() * 5 / 8];
        int buf = 0, bits = 0, k = 0;
        for (char c : s.toCharArray()) {
            int v = A32.indexOf(c);
            if (v < 0) throw new IllegalArgumentException("base32");
            buf = (buf << 5) | v;
            bits += 5;
            if (bits >= 8) { out[k++] = (byte) (buf >> (bits - 8)); bits -= 8; }
        }
        return Arrays.copyOf(out, k);
    }

    static byte[] hex(String h) {
        byte[] o = new byte[h.length() / 2];
        for (int i = 0; i < o.length; i++) o[i] = (byte) Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        return o;
    }

    /* ------------------------------------------------------------ Ed25519 doğrulama (RFC 8032) */
    static final BigInteger P = BigInteger.ONE.shiftLeft(255).subtract(BigInteger.valueOf(19));
    static final BigInteger L = BigInteger.ONE.shiftLeft(252).add(new BigInteger("27742317777372353535851937790883648493"));
    static final BigInteger D = BigInteger.valueOf(-121665).multiply(BigInteger.valueOf(121666).modInverse(P)).mod(P);
    static final BigInteger I = BigInteger.valueOf(2).modPow(P.subtract(BigInteger.ONE).shiftRight(2), P);
    static final BigInteger TWO = BigInteger.valueOf(2);
    static final BigInteger[] G;

    static {
        BigInteger gy = BigInteger.valueOf(4).multiply(BigInteger.valueOf(5).modInverse(P)).mod(P);
        BigInteger gx = recoverX(gy, 0);
        G = new BigInteger[]{gx, gy, BigInteger.ONE, gx.multiply(gy).mod(P)};
    }

    static BigInteger recoverX(BigInteger y, int sign) {
        if (y.compareTo(P) >= 0) return null;
        BigInteger y2 = y.multiply(y);
        BigInteger x2 = y2.subtract(BigInteger.ONE).multiply(D.multiply(y2).add(BigInteger.ONE).modInverse(P)).mod(P);
        if (x2.signum() == 0) return sign != 0 ? null : BigInteger.ZERO;
        BigInteger x = x2.modPow(P.add(BigInteger.valueOf(3)).shiftRight(3), P);
        if (x.multiply(x).subtract(x2).mod(P).signum() != 0) x = x.multiply(I).mod(P);
        if (x.multiply(x).subtract(x2).mod(P).signum() != 0) return null;
        if (x.testBit(0) != (sign == 1)) x = P.subtract(x);
        return x;
    }

    static BigInteger[] add(BigInteger[] p, BigInteger[] q) {
        BigInteger a = p[1].subtract(p[0]).multiply(q[1].subtract(q[0])).mod(P);
        BigInteger b = p[1].add(p[0]).multiply(q[1].add(q[0])).mod(P);
        BigInteger c = p[3].multiply(TWO).multiply(D).multiply(q[3]).mod(P);
        BigInteger d = p[2].multiply(TWO).multiply(q[2]).mod(P);
        BigInteger e = b.subtract(a), f = d.subtract(c), g = d.add(c), h = b.add(a);
        return new BigInteger[]{e.multiply(f).mod(P), g.multiply(h).mod(P), f.multiply(g).mod(P), e.multiply(h).mod(P)};
    }

    static BigInteger[] mul(BigInteger s, BigInteger[] p) {
        BigInteger[] q = {BigInteger.ZERO, BigInteger.ONE, BigInteger.ONE, BigInteger.ZERO};
        for (int i = s.bitLength() - 1; i >= 0; i--) {
            q = add(q, q);
            if (s.testBit(i)) q = add(q, p);
        }
        return q;
    }

    static boolean eq(BigInteger[] p, BigInteger[] q) {
        return p[0].multiply(q[2]).subtract(q[0].multiply(p[2])).mod(P).signum() == 0
                && p[1].multiply(q[2]).subtract(q[1].multiply(p[2])).mod(P).signum() == 0;
    }

    static BigInteger le(byte[] b, int off, int len) {
        byte[] r = new byte[len + 1];
        for (int i = 0; i < len; i++) r[len - i] = b[off + i];
        return new BigInteger(r);
    }

    static BigInteger[] decompress(byte[] s, int off) {
        BigInteger y = le(s, off, 32);
        int sign = y.testBit(255) ? 1 : 0;
        y = y.clearBit(255);
        BigInteger x = recoverX(y, sign);
        return x == null ? null : new BigInteger[]{x, y, BigInteger.ONE, x.multiply(y).mod(P)};
    }

    public static boolean verify(byte[] pub, byte[] msg, byte[] sig) {
        try {
            if (pub.length != 32 || sig.length != 64) return false;
            BigInteger[] a = decompress(pub, 0), r = decompress(sig, 0);
            if (a == null || r == null) return false;
            BigInteger s = le(sig, 32, 32);
            if (s.compareTo(L) >= 0) return false;
            MessageDigest md = MessageDigest.getInstance("SHA-512");
            md.update(sig, 0, 32);
            md.update(pub);
            md.update(msg);
            BigInteger k = le(md.digest(), 0, 64).mod(L);
            return eq(mul(s, G), add(r, mul(k, a)));
        } catch (Exception e) {
            return false;
        }
    }
}
