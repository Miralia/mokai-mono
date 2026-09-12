"""基于 harfbuzz + freetype 的真实排版渲染。

为什么不用 Pillow 的 draw.text：
  Pillow 的 RAQM（harfbuzz）排版引擎在很多环境并不可用，会**静默退回 BASIC 引擎**，
  而 BASIC 引擎不应用 OpenType 特性 —— 连字、上下文替换（calt）全都不生效。
  实测本机就是这种情况：
      UserWarning: Raqm layout was requested, but Raqm is not available.
                   Falling back to basic layout.
  结果就是展示图里永远看不到连字。

  本模块直接用 harfbuzz 整形、按 glyph id 交给 freetype 光栅化，
  渲染结果与真实排版引擎一致。
"""
from __future__ import annotations

from pathlib import Path

import freetype
import uharfbuzz as hb
from PIL import Image

_SUBPIXEL = 64          # harfbuzz 用 26.6 定点数表示位置


class TextRenderer:
    """单个字体 + 单个字号的排版渲染器。"""

    def __init__(self, font_path: Path | str, size: int, index: int = 0):
        self.path = str(font_path)
        self.size = size
        self.face = freetype.Face(self.path, index)
        self.face.set_pixel_sizes(0, size)

        with open(self.path, "rb") as fh:
            data = fh.read()
        self._blob = hb.Blob(data)
        hb_face = hb.Face(self._blob)
        self._font = hb.Font(hb_face)
        self._font.scale = (size * _SUBPIXEL, size * _SUBPIXEL)

        self.upem = self.face.units_per_EM
        # freetype 的 ascender/descender 是 26.6 定点像素
        self.ascent = self.face.size.ascender / 64
        self.descent = -self.face.size.descender / 64
        self.line_height = self.ascent + self.descent

    # -- 整形 ---------------------------------------------------------------
    def shape(self, text: str):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self._font, buf)
        return buf.glyph_infos, buf.glyph_positions

    def width(self, text: str) -> float:
        _, positions = self.shape(text)
        return sum(p.x_advance for p in positions) / _SUBPIXEL

    # -- 绘制 ---------------------------------------------------------------
    def draw(self, img: Image.Image, x: float, baseline: float, text: str,
             color=(0, 0, 0)) -> float:
        """在 (x, baseline) 处绘制 text，返回前进宽度。"""
        infos, positions = self.shape(text)
        pen = float(x)
        for info, pos in zip(infos, positions):
            self.face.load_glyph(
                info.codepoint,
                freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
            g = self.face.glyph
            bm = g.bitmap
            if bm.width and bm.rows:
                left = int(round(pen + pos.x_offset / _SUBPIXEL)) + g.bitmap_left
                top = int(round(baseline - pos.y_offset / _SUBPIXEL)) - g.bitmap_top
                mask = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))
                img.paste(Image.new("RGB", (bm.width, bm.rows), color),
                          (left, top), mask)
            pen += pos.x_advance / _SUBPIXEL
        return pen - x

    def draw_line(self, img: Image.Image, x: float, top: float, text: str,
                  color=(0, 0, 0)) -> float:
        """在行框顶部 top 处绘制一行，基线按字体度量推算。返回前进宽度。"""
        return self.draw(img, x, top + self.ascent, text, color)


def measure(font_path: Path | str, size: int) -> tuple[float, float]:
    """返回 (ascent, descent)，单位像素。"""
    r = TextRenderer(font_path, size)
    return r.ascent, r.descent
