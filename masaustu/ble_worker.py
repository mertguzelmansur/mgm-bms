# -*- coding: utf-8 -*-
"""BLE bağlantı katmanı – bleak ile JK BMS'e bağlanır, olayları kuyruğa yazar."""
import asyncio
import threading
import time

import jk_protocol as jk

try:
    from bleak import BleakClient, BleakScanner
    HAVE_BLEAK = True
except ImportError:
    HAVE_BLEAK = False


class BleWorker:
    """Ayrı bir thread içinde asyncio döngüsü çalıştırır; GUI ile kuyrukla konuşur."""

    def __init__(self, events: "queue.Queue"):
        self.ev = events
        self.loop = asyncio.new_event_loop()
        self.client = None
        self.asm = jk.FrameAssembler()
        self.old_protocol = False
        self.last_cell_frame = 0.0
        self._keepalive_task = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    # ---------------------------------------------------------------- tarama
    async def scan(self, seconds=6.0):
        self.ev.put(("status", "Taranıyor..."))
        try:
            found = await BleakScanner.discover(timeout=seconds, return_adv=True)
        except Exception as e:
            self.ev.put(("error", f"Tarama hatası: {e}"))
            return
        devs = []
        for addr, (d, adv) in found.items():
            uuids = [u.lower() for u in (adv.service_uuids or [])]
            name = d.name or adv.local_name or ""
            is_jk = jk.SERVICE_UUID in uuids or name.upper().startswith(("JK", "SQ"))
            devs.append((is_jk, adv.rssi or -999, name or "(isimsiz)", addr))
        devs.sort(key=lambda x: (not x[0], -x[1]))
        self.ev.put(("scan", devs))
        n = sum(1 for d in devs if d[0])
        self.ev.put(("status", f"{n} JK BMS bulundu" + (f" ({len(devs) - n} diğer cihaz gizlendi)" if len(devs) > n else "")))

    # ---------------------------------------------------------------- bağlantı
    async def connect(self, address):
        await self.disconnect()
        self.ev.put(("status", f"Bağlanıyor: {address}"))
        self.asm = jk.FrameAssembler()
        self.old_protocol = False
        try:
            self.client = BleakClient(address, disconnected_callback=self._on_disc, timeout=20.0)
            await self.client.connect()
            await self.client.start_notify(jk.CHAR_UUID, self._on_notify)
        except Exception as e:
            self.client = None
            self.ev.put(("error", f"Bağlantı hatası: {e}"))
            self.ev.put(("connected", False))
            return
        self.ev.put(("connected", True))
        self.ev.put(("status", "Bağlandı – veriler isteniyor"))
        await asyncio.sleep(0.3)
        await self.write(jk.build_command(jk.CMD_DEVICE_INFO))
        await asyncio.sleep(0.5)
        await self.write(jk.build_command(jk.CMD_SETTINGS_AND_DATA))
        self.last_cell_frame = time.time()
        self._keepalive_task = asyncio.ensure_future(self._keepalive())

    async def _keepalive(self):
        # BMS 0x96'dan sonra sürekli 0x02 yollar; susarsa isteği yinele
        while self.client and self.client.is_connected:
            await asyncio.sleep(2)
            if time.time() - self.last_cell_frame > 6:
                await self.write(jk.build_command(jk.CMD_SETTINGS_AND_DATA))
                self.last_cell_frame = time.time()

    def _on_disc(self, _client):
        self.ev.put(("connected", False))
        self.ev.put(("status", "Bağlantı kesildi"))

    async def disconnect(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None

    async def rename(self, name: str):
        await self.write(jk.build_rename(name))
        await asyncio.sleep(1.0)
        await self.write(jk.build_command(jk.CMD_DEVICE_INFO))   # yeni adı geri oku

    async def write(self, data: bytes):
        if not (self.client and self.client.is_connected):
            return
        self.ev.put(("raw", "TX", data))
        try:
            # Android uygulaması WRITE_TYPE_NO_RESPONSE kullanıyor
            await self.client.write_gatt_char(jk.CHAR_UUID, data, response=False)
        except Exception:
            try:
                await self.client.write_gatt_char(jk.CHAR_UUID, data, response=True)
            except Exception as e:
                self.ev.put(("error", f"Yazma hatası: {e}"))

    def _on_notify(self, _char, data: bytearray):
        for frame in self.asm.feed(bytes(data)):
            self.handle_frame(frame)

    def handle_frame(self, frame: bytes):
        self.ev.put(("raw", "RX", frame))
        t = frame[4]
        if t == 0x03:
            info = jk.parse_device_info(frame)
            self.old_protocol = jk.is_old_protocol(info)
            if self.old_protocol:
                info = jk.parse_device_info(jk.old_to_new(frame))
                info["protocol"] = "eski (24S)"
            self.ev.put(("info", info))
            return
        if t == 0x06:                       # arıza kaydı paketi (0xA7 isteğine yanıt)
            self.ev.put(("logframe", frame))
            return
        if self.old_protocol:
            frame = jk.old_to_new(frame)
        if t == 0x01:
            self.ev.put(("settings", jk.parse_settings(frame)))
        elif t == 0x02:
            self.last_cell_frame = time.time()
            self.ev.put(("cells", jk.parse_cell_info(frame)))

