"""
生成多尺寸 app.ico（金色均衡器波形，深色圆角底）
用于 EXE 文件图标、窗口图标与托盘图标。
"""

from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]

BG = (18, 22, 29, 255)        # 深蓝灰底
GOLD = (240, 192, 96, 255)    # 金色
GOLD_DIM = (150, 120, 64, 255)


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角背景
    m = max(1, size // 20)
    d.rounded_rectangle([m, m, size - m, size - m], radius=size // 5, fill=BG)

    # 均衡器波形条
    bars = [0.42, 0.78, 0.55, 1.0, 0.66, 0.48]
    n = len(bars)
    pad_x = size * 0.20
    pad_top = size * 0.22
    pad_bottom = size * 0.22
    inner_w = size - 2 * pad_x
    gap = inner_w / (n * 2.2)
    bw = (inner_w - gap * (n - 1)) / n
    base_y = size - pad_bottom

    for i, h in enumerate(bars):
        x0 = pad_x + i * (bw + gap)
        x1 = x0 + bw
        hgt = (base_y - pad_top) * h
        y0 = base_y - hgt
        r = max(1, bw * 0.45)
        fill = GOLD if i in (1, 3, 4) else GOLD_DIM
        d.rounded_rectangle([x0, y0, x1, base_y], radius=r, fill=fill)

    return img


def main():
    out = "app.ico"
    # 用一张高分辨率图，交给 Pillow 按 sizes 自动生成各尺寸
    img = make(256)
    img.save(out, sizes=[(s, s) for s in SIZES], format="ICO")
    print("已生成", out, SIZES)


if __name__ == "__main__":
    main()
