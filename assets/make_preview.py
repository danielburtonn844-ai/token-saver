#!/usr/bin/env python3
"""生成 GitHub Social Preview 图（1280x640）。"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
BG = (13, 17, 23)
FG = (230, 237, 243)
MUTED = (139, 148, 158)
ACCENT = (63, 185, 80)
LINE = (48, 54, 61)

LATIN_B = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
LATIN = "/usr/share/fonts/dejavu/DejaVuSans.ttf"
CJK = "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc"

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

fb = lambda s: ImageFont.truetype(LATIN_B, s)
fr = lambda s: ImageFont.truetype(LATIN, s)
fc = lambda s: ImageFont.truetype(CJK, s, index=0)

M = 96
d.text((M, 70), "danielburtonn844-ai", font=fr(26), fill=MUTED)

d.text((M, 130), "token-saver", font=fb(96), fill=FG)

d.text((M, 258), "省 token 的作业规范与配套脚本", font=fc(40), fill=FG)

d.text((M, 316), "压缩工具输出 · 控制上下文 · 跨会话交接", font=fc(28), fill=MUTED)

d.line([(M, 392), (W - M, 392)], fill=LINE, width=2)

stats = [("99.3%", "日志压缩"), ("350 tk", "目录索引卡"), ("16", "项冒烟测试")]
x = M
for num, label in stats:
    d.text((x, 432), num, font=fb(52), fill=ACCENT)
    d.text((x, 502), label, font=fc(24), fill=MUTED)
    x += 330

d.text((M, 570), "github.com/danielburtonn844-ai/token-saver", font=fr(24), fill=MUTED)

img.save("/var/minis/workspace/token-saver/assets/social-preview.png", "PNG", optimize=True)
print("saved")
