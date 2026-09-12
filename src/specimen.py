"""生成展示效果图。

设计目标：像成熟字体项目那样，一图说清字体的定位与全部特性。
一张展示图自上而下分八段：标题 → 主视觉 → 字号瀑布 → 代码块 →
中文排版 → 制表符 → 连字 → 字符网格。

关键实现细节：
  * **全部文本走 harfbuzz 整形 + freetype 光栅化**（见 textrender.py）。
    不能用 Pillow 的 draw.text —— 它的 RAQM 引擎常常不可用、会静默退回
    BASIC 引擎，导致连字等 OpenType 特性完全不生效，展示图会失真。
  * 行高取自字体的 typo 度量（ascent..descent）—— 制表符的竖向范围恰好
    等于 typo 度量，行高不对会把连续的线画断。
  * 标签用系统 CJK 字体（PingFang），否则中文标签会变豆腐块。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

import config
import textrender as tr

# ---------------------------------------------------------------------------
# 设计常量
# ---------------------------------------------------------------------------
BG = "#FFFFFF"
INK = (17, 17, 17)
MUTED = (138, 138, 138)
ACCENT = (31, 111, 235)
RULE = "#E6E6E3"
GRID_LINE = "#EAF2FB"
CODE_BG = "#1E1E1E"
CODE_FG = (214, 214, 214)
CODE_KEY = (127, 179, 255)
CODE_CJK = (199, 229, 168)

PAD = 44
LABEL_W = 92
WIDTH = 1180

LABEL_FONTS = [
    ("/System/Library/Fonts/PingFang.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", 0),
    ("/System/Library/Fonts/Helvetica.ttc", 0),
]

CODE_SAMPLE = [
    [("const ", CODE_FG), ("add", CODE_KEY), (" = (", CODE_FG), ("a", CODE_KEY),
     (", ", CODE_FG), ("b", CODE_KEY), (") => ", CODE_FG), ("a + b", CODE_FG),
     (";  ", CODE_FG), ("// 求和", CODE_CJK)],
    [("if (", CODE_FG), ("x != y", CODE_FG), (" && ", CODE_FG), ("a <= b", CODE_FG),
     (") { ", CODE_FG), ("// 条件判断", CODE_CJK), (" }", CODE_FG)],
    [("let ", CODE_FG), ("中文变量", CODE_FG), (" = ", CODE_FG), ("'汉字'", CODE_FG),
     (";  ", CODE_FG), ("// 中文标识符", CODE_CJK)],
    [("┌────────┬────────┐", CODE_FG), ("   // 制表符无缝", CODE_CJK)],
]

PROSE = [
    "他说：「你好，世界。」——这是注释，不是代码。",
    "‘单引号’与“双引号”在中文排版中占满两格，位置正确。",
    "霞鹜文楷与霞鹜臻楷的字形，与 Latin 混排时基线对齐。",
]

LIGATURE_SAMPLE = [
    ("=  >", "分开写 —— 不连字"),
    ("=>", "紧邻 —— 连成箭头"),
    ("!=  <=  >=  |>  ->  ==>", "常见运算符连字"),
    ("汉字 != Latin 混排", "中文上下文同样生效"),
]

TABLE_SAMPLE = ["┌────────┬────────┐", "│ 中文列 │ Latin  │",
                "├────────┼────────┤", "│ 数据   │ 1234   │",
                "└────────┴────────┘"]

GRID_ROWS = [
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789  !\"#$%&'()*+,-./:;<=>?@",
    "天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏",
    "あいうえおかきくけこさしすせそたちつてと",
    "、。，：；！？「」『』（）【】——……“”‘’·",
]


def _label_path() -> tuple[str, int]:
    for path, idx in LABEL_FONTS:
        if Path(path).exists():
            return path, idx
    return LABEL_FONTS[-1]


class Canvas:
    """按段累积的画布：先算总高，再落笔。"""

    def __init__(self, width: int = WIDTH):
        self.width = width
        self.blocks: list[tuple[int, int, object]] = []
        self.y = PAD

    def add(self, height: float, draw_fn):
        h = int(round(height))
        self.blocks.append((self.y, h, draw_fn))
        self.y += h

    def render(self, out_path: Path) -> Path:
        img = Image.new("RGB", (int(self.width), int(self.y + PAD)), BG)
        d = ImageDraw.Draw(img)
        for y, h, fn in self.blocks:
            fn(img, d, y, h)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path)
        return out_path


def showcase(font_path: Path, out_path: Path, *, size: int = 30,
             meta: dict | None = None) -> Path:
    meta = meta or {}
    c = Canvas()
    body = tr.TextRenderer(font_path, size)
    lpath, lidx = _label_path()
    lab = tr.TextRenderer(lpath, 15, lidx)
    lab_s = tr.TextRenderer(lpath, 13, lidx)
    title_r = tr.TextRenderer(lpath, 33, lidx)
    sub_r = tr.TextRenderer(lpath, 16, lidx)
    left = PAD + LABEL_W
    lh = lambda r: r.line_height                                  # noqa: E731

    # ---- 1. 标题 ----
    def title(img, d, y, h):
        title_r.draw_line(img, PAD, y + 2, meta.get("title", font_path.stem), INK)
        sub_r.draw_line(img, PAD, y + 50, meta.get("subtitle", ""), MUTED)
        d.line([(PAD, y + h - 12), (WIDTH - PAD, y + h - 12)], fill=RULE, width=1)
    c.add(94, title)

    # ---- 2. 主视觉 ----
    hero = tr.TextRenderer(font_path, int(size * 1.3))
    def hero_block(img, d, y, h):
        hero.draw_line(img, PAD, y + 6, "汉字 Latin 混排 0123456789", INK)
        hero.draw_line(img, PAD, y + 6 + lh(hero) + 6,
                       "const 求和 = (a, b) => a + b;", INK)
    c.add(lh(hero) * 2 + 34, hero_block)

    # ---- 3. 字号瀑布 ----
    wf = [tr.TextRenderer(font_path, int(size * k)) for k in (0.6, 0.78, 1.0)]
    def waterfall(img, d, y, h):
        lab.draw_line(img, PAD, y + 6, "字号", MUTED)
        yy = y + 30
        for r in wf:
            r.draw_line(img, left, yy, "汉字与 Latin 混排对齐 0123456789", INK)
            yy += lh(r) + 8
    c.add(30 + sum(lh(r) + 8 for r in wf) + 14, waterfall)

    # ---- 4. 代码块 ----
    code = tr.TextRenderer(font_path, int(size * 0.84))
    def code_block(img, d, y, h):
        lab.draw_line(img, PAD, y + 6, "代码", MUTED)
        top = y + 30
        box_h = lh(code) * len(CODE_SAMPLE) + 32
        d.rounded_rectangle([(left, top), (WIDTH - PAD, top + box_h)],
                            radius=10, fill=CODE_BG)
        yy = top + 14
        for line in CODE_SAMPLE:
            x = float(left + 18)
            for text, color in line:
                x += code.draw(img, x, yy + code.ascent, text, color)
            yy += lh(code)
    c.add(30 + lh(code) * len(CODE_SAMPLE) + 32 + 20, code_block)

    # ---- 5. 中文排版 ----
    prose = tr.TextRenderer(font_path, int(size * 0.9))
    def prose_block(img, d, y, h):
        lab.draw_line(img, PAD, y + 6, "中文", MUTED)
        for i, line in enumerate(PROSE):
            prose.draw_line(img, left, y + 30 + i * lh(prose), line, INK)
    c.add(30 + lh(prose) * len(PROSE) + 16, prose_block)

    # ---- 6. 制表符 ----
    box = tr.TextRenderer(font_path, int(size * 0.84))
    def table_block(img, d, y, h):
        lab.draw_line(img, PAD, y + 6, "制表符", MUTED)
        for i, line in enumerate(TABLE_SAMPLE):
            box.draw_line(img, left, y + 30 + i * lh(box), line, INK)
    c.add(30 + lh(box) * len(TABLE_SAMPLE) + 16, table_block)

    # ---- 7. 连字 ----
    lig = tr.TextRenderer(font_path, int(size * 0.84))
    def lig_block(img, d, y, h):
        lab.draw_line(img, PAD, y + 6, "连字", MUTED)
        for i, (sample, note) in enumerate(LIGATURE_SAMPLE):
            yy = y + 30 + i * lh(lig)
            w = lig.draw_line(img, left, yy, sample, INK)
            lab_s.draw_line(img, left + max(w, 300) + 18, yy + 6, note, MUTED)
    c.add(30 + lh(lig) * len(LIGATURE_SAMPLE) + 16, lig_block)

    # ---- 8. 字符网格 ----
    grid = tr.TextRenderer(font_path, int(size * 0.66))
    def grid_block(img, d, y, h):
        lab.draw_line(img, PAD, y + 6, "字符", MUTED)
        for i, row in enumerate(GRID_ROWS):
            grid.draw_line(img, left, y + 30 + i * (lh(grid) + 2), row, INK)
    c.add(30 + (lh(grid) + 2) * len(GRID_ROWS) + 12, grid_block)

    # ---- 9. 页脚 ----
    def footer(img, d, y, h):
        d.line([(PAD, y + 4), (WIDTH - PAD, y + 4)], fill=RULE, width=1)
        lab_s.draw_line(img, PAD, y + 18, meta.get("footer", ""), MUTED)
    c.add(52, footer)

    return c.render(out_path)


def lineup(fonts: list[tuple[str, Path]], out_path: Path, *, size: int = 28) -> Path:
    """字重对比图：同一段样例按字重堆叠，叠加等宽栅格。"""
    c = Canvas()
    lpath, lidx = _label_path()
    head = tr.TextRenderer(lpath, 20, lidx)
    tag = tr.TextRenderer(lpath, 15, lidx)
    sample = [
        "汉字与 Latin 混排 0123456789",
        "const add = (a, b) => a + b;  // 求和",
        "他说：「你好，世界。」——注释",
    ]
    left = PAD + 128

    def header(img, d, y, h):
        head.draw_line(img, PAD, y + 2, "字重对比", INK)
        d.line([(PAD, y + h - 10), (WIDTH - PAD, y + h - 10)], fill=RULE, width=1)
    c.add(44, header)

    for label_txt, path in fonts:
        r = tr.TextRenderer(path, size)
        cell = r.width("A")
        lh = r.line_height

        def block(img, d, y, h, r=r, cell=cell, lh=lh, label_txt=label_txt):
            tag.draw_line(img, PAD, y + 8, label_txt, ACCENT)
            x, i = left, 0
            while x < WIDTH - PAD:
                if i % 2 == 0:
                    d.line([(x, y + 26), (x, y + 30 + lh * len(sample))],
                           fill=GRID_LINE, width=1)
                x += cell
                i += 1
            for li, line in enumerate(sample):
                r.draw_line(img, left, y + 30 + li * lh, line, INK)
        c.add(30 + lh * len(sample) + 24, block)

    return c.render(out_path)


def run(only: str | None = None, spacing: str | None = None) -> int:
    src_dir = config.MERGED
    if not src_dir.exists():
        print("没有可渲染的产物，先运行 python src/build.py merge")
        return 1
    want = spacing or "slab"
    marker = config.spacing(want)["file_marker"]
    found: dict[str, Path] = {}
    for p in sorted(src_dir.glob(f"MoKaiMono{marker}-*.ttf")):
        if "unhinted" in p.stem:
            continue
        found[p.stem.rsplit("-", 1)[-1]] = p
    if only:
        found = {k: v for k, v in found.items() if k == only}
    if not found:
        print(f"没找到 {want} 间距的产物")
        return 1

    ordered = [(w["label"], found[w["label"]])
               for w in config.WEIGHTS if w["label"] in found]
    for wlabel, path in ordered:
        out = showcase(path, config.SPECIMEN / f"showcase-{want}-{wlabel}.png", meta={
            "title": f"{config.variant_family(want, nf=False, hinted=True)}  {wlabel}",
            "subtitle": "1:2 严格等宽 · 中英混排 · 编程字体 · "
                        "拉丁 Iosevka Slab / 中文 霞鹜文楷 GB · 臻楷 GB",
            "footer": "MoKai Mono — SIL Open Font License 1.1 — "
                      "Modified Version of Iosevka + LXGW WenKai GB + LXGW ZhenKai GB",
        })
        print(f"  {out.name}")

    if len(ordered) > 1:
        out = lineup(ordered, config.SPECIMEN / f"lineup-{want}.png")
        print(f"  {out.name}（{len(ordered)} 个字重）")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
