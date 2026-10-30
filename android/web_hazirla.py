# -*- coding: utf-8 -*-
"""Android uygulamasının web varlıklarını build/assets/www içine hazırlar.
Arayüz masaüstüyle ortaktır: ../masaustu/ui/index.html"""
import os
H = os.path.dirname(os.path.abspath(__file__))
W, OUT = os.path.join(H, "web"), os.path.join(H, "build", "assets", "www")
os.makedirs(OUT, exist_ok=True)
rd = lambda p: open(p, encoding="utf8").read()
tpl, tables = rd(os.path.join(W, "jk_protocol.tpl.js")), rd(os.path.join(W, "jk_tables.json"))
assert "/*TABLES*/null" in tpl
open(os.path.join(OUT, "jk_protocol.js"), "w", encoding="utf8").write(tpl.replace("/*TABLES*/null", tables))
for f in ("bridge.js", "native-shim.js"):
    open(os.path.join(OUT, f), "w", encoding="utf8").write(rd(os.path.join(W, f)))
html = rd(os.path.join(H, "..", "masaustu", "ui", "index.html"))
tag = '<script>\n"use strict";'
assert html.count(tag) == 1, "ui/index.html beklenen biçimde değil"
html = html.replace(tag, '<script src="native-shim.js"></script>\n<script src="jk_protocol.js"></script>\n<script src="bridge.js"></script>\n' + tag)
open(os.path.join(OUT, "index.html"), "w", encoding="utf8").write(html)
print("web varlıkları hazır:", OUT)
