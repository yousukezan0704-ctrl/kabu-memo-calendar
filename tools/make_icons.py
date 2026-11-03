"""アイコン(PNG)を作る。外部ライブラリ不要。python tools/make_icons.py"""
import os, struct, zlib

def png(path, n):
    rows = []
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            fx, fy = x / n, y / n
            c = (26, 86, 219)                       # 青い背景
            if 0.18 < fx < 0.82 and 0.24 < fy < 0.80:
                c = (255, 255, 255)                 # 白いカレンダー本体
                if fy < 0.38:
                    c = (200, 38, 45)               # 上の赤い帯
                elif int(fx * 100) % 20 in (4, 5, 6, 7, 8) and 0.5 < fy < 0.7 and False:
                    pass
                elif 0.5 < fy < 0.62 and (int((fx - 0.18) / 0.64 * 4)) % 2 == 0 and 0.24 < fx:
                    c = (26, 86, 219)
            row += bytes(c)
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(t, d):
        b = struct.pack(">I", len(d)) + t + d
        return b + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(data)

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "icons")
for n in (180, 192, 512):
    png(os.path.join(root, "icon-%d.png" % n), n)
print("ok")
