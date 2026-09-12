"""不变量校验。

这些断言是「这是一款严格等宽字体」的可执行定义。
任何一条不通过，产物都不应发布。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from fontTools.ttLib import TTFont

import config
import ranges


class Check:
    def __init__(self):
        self.results: list[tuple[bool, str, str]] = []

    def ok(self, name: str, detail: str = ""):
        self.results.append((True, name, detail))

    def fail(self, name: str, detail: str = ""):
        self.results.append((False, name, detail))

    def expect(self, cond: bool, name: str, detail: str = ""):
        (self.ok if cond else self.fail)(name, detail)

    @property
    def passed(self) -> bool:
        return all(r[0] for r in self.results)

    def report(self, title: str) -> bool:
        print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")
        for good, name, detail in self.results:
            mark = "PASS" if good else "FAIL"
            print(f"  [{mark}] {name}" + (f"  —  {detail}" if detail else ""))
        n_fail = sum(1 for r in self.results if not r[0])
        print("-" * 74)
        print(f"  {len(self.results) - n_fail}/{len(self.results)} 通过"
              + ("" if not n_fail else f"，{n_fail} 项失败"))
        return self.passed


def _ligature_probe(font_path: Path, samples: list[str]):
    """用 harfbuzz 实测连字是否触发。返回 [(序列, 是否触发连字)]，缺依赖时返回 None。"""
    try:
        import uharfbuzz as hb
    except ImportError:
        return None

    tt = TTFont(str(font_path), lazy=True)
    order = tt.getGlyphOrder()
    blob = hb.Blob.from_file_path(str(font_path))
    face = hb.Face(blob)
    font = hb.Font(face)

    def shape(text: str) -> list[str]:
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        return [order[i.codepoint] for i in buf.glyph_infos]

    out = []
    for t in samples:
        naive: list[str] = []
        for ch in t:
            naive += shape(ch)
        out.append((t, shape(t) != naive))
    tt.close()
    return out


def verify(font_path: Path, *, cjk_references: list[Path] | None = None,
           expected_codepoints: set[int] | None = None,
           nf: bool = False, spacing: str = "slab",
           title: str | None = None) -> bool:
    c = Check()
    font = TTFont(str(font_path), lazy=True)
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    n_glyphs = font["maxp"].numGlyphs

    # --- 1. 字形数上限 ---
    c.expect(n_glyphs <= 65535, "字形数不超过 65535（maxp 是 uint16）",
             f"{n_glyphs}")

    # --- 2. 等宽不变量 ---
    widths = Counter(hmtx[g][0] for g in cmap.values())
    bad = {w: n for w, n in widths.items() if w not in config.ALLOWED_WIDTHS}
    c.expect(not bad, "等宽不变量：所有 cmap 字形宽度 ∈ {0, 500, 1000}",
             f"越界宽度 {bad}" if bad else
             "、".join(f"{w}:{n}" for w, n in sorted(widths.items())))

    # --- 3. CJK 覆盖率 ---
    want: set[int] = set()
    if expected_codepoints is not None:
        want = set(expected_codepoints)
    elif cjk_references:
        for ref_path in cjk_references:
            ref = TTFont(str(ref_path), lazy=True)
            ref_cmap = ref.getBestCmap()
            want |= {cp for cp in ref_cmap if ranges.take_from_cjk(cp)}
            ref.close()
    if want:
        missing = sorted(want - set(cmap))
        extra = len({cp for cp in cmap if ranges.take_from_cjk(cp)} - want)
        c.expect(not missing, "CJK 覆盖率：应取的码位全部存在",
                 f"缺 {len(missing)} 个，例如 "
                 + ", ".join(f"U+{x:04X}" for x in missing[:6]) if missing
                 else f"{len(want)} 个码位全部存在"
                      + (f"（另有 {extra} 个超出范围，属预期）" if extra else ""))

    # --- 4. 终端关键码位宽度（随间距变化）---
    critical = dict(config.TERMINAL_CRITICAL_COMMON)
    critical.update(config.TERMINAL_CRITICAL_PER_SPACING.get(spacing, {}))
    term_bad = []
    for cp, want_w in critical.items():
        if cp not in cmap:
            term_bad.append(f"U+{cp:04X} 缺失")
        elif hmtx[cmap[cp]][0] != want_w:
            term_bad.append(f"U+{cp:04X}={hmtx[cmap[cp]][0]}(应{want_w})")
    c.expect(not term_bad, f"终端关键码位宽度正确（{spacing} 间距）",
             "; ".join(term_bad) if term_bad else f"{len(critical)} 个码位全部正确")

    # --- 4b. 制表符能否无缝拼接 ---
    # 终端里画表格依赖这些字形触及格子边界；差一点就会出现断线。
    from fontTools.pens.boundsPen import BoundsPen
    glyphset = font.getGlyphSet()
    hhea = font["hhea"]
    asc, desc = hhea.ascent, hhea.descent
    tol = 2
    seam_bad = []
    for cp, (left, right, top, bottom) in config.BOX_DRAWING_CONTACTS.items():
        gn = cmap.get(cp)
        if gn is None:
            seam_bad.append(f"U+{cp:04X} 缺失")
            continue
        bp = BoundsPen(glyphset)
        glyphset[gn].draw(bp)
        if not bp.bounds:
            seam_bad.append(f"U+{cp:04X} 空白")
            continue
        x0, y0, x1, y1 = bp.bounds
        adv = hmtx[gn][0]
        if left and x0 > tol:
            seam_bad.append(f"U+{cp:04X} 左边界差 {x0}")
        if right and x1 < adv - tol:
            seam_bad.append(f"U+{cp:04X} 右边界差 {adv - x1}")
        if top and y1 < asc - tol:
            seam_bad.append(f"U+{cp:04X} 上边界差 {asc - y1}")
        if bottom and y0 > desc + tol:
            seam_bad.append(f"U+{cp:04X} 下边界差 {y0 - desc}")
    c.expect(not seam_bad, "制表符可无缝拼接（字形触及格子边界）",
             "; ".join(seam_bad[:6]) if seam_bad
             else f"{len(config.BOX_DRAWING_CONTACTS)} 个制表符全部触边")

    # --- 5. CJK 关键码位宽度（U+3000 全角空格最易漏）---
    cjk_bad = []
    for cp, want_w in config.CJK_CRITICAL.items():
        if cp not in cmap:
            cjk_bad.append(f"U+{cp:04X} 缺失")
        elif hmtx[cmap[cp]][0] != want_w:
            cjk_bad.append(f"U+{cp:04X}={hmtx[cmap[cp]][0]}(应{want_w})")
    c.expect(not cjk_bad, "CJK 关键码位宽度正确（含 U+3000 全角空格）",
             "; ".join(cjk_bad) if cjk_bad else
             f"{len(config.CJK_CRITICAL)} 个码位全部正确")

    # --- 6. 连字特性（随间距/连字组合变化）---
    feats = set()
    if "GSUB" in font and font["GSUB"].table.FeatureList:
        feats = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    want_lig = config.spacing(spacing)["ligatures"]
    if want_lig:
        missing_feats = [f for f in config.REQUIRED_GSUB_FEATURES if f not in feats]
        c.expect(not missing_feats, "连字特性存在",
                 f"缺少 {missing_feats}" if missing_feats
                 else f"GSUB 共 {len(feats)} 个特性，calt 已就位")
    else:
        c.expect("calt" not in feats, "该变体不含 calt 连字特性（无连字组合）",
                 f"GSUB 共 {len(feats)} 个特性，calt 已移除")

    # --- 6b. 连字是否真的能整形出来（harfbuzz 实测）---
    # 注意：Iosevka 把连字实现为「左半 + 右半」两个字形（.join-r / .join-l），
    # 各 500 宽、合计 1000（跨 2 格）。所以**不能**用「字形数减少」判断，
    # 必须比对「整串整形结果」与「逐字符整形结果」是否不同。
    lig = _ligature_probe(font_path, config.LIGATURE_SAMPLES)
    if lig is None:
        c.fail("连字整形测试", "未安装 uharfbuzz，无法验证")
    elif want_lig:
        bad = [t for t, ok in lig if not ok]
        c.expect(not bad, "连字可正常整形（harfbuzz 实测）",
                 f"未触发连字: {bad}" if bad
                 else f"{len(lig)}/{len(lig)} 个序列全部触发连字")
    else:
        bad = [t for t, ok in lig if ok]
        c.expect(not bad, "该变体不含连字（harfbuzz 实测）",
                 f"意外触发连字: {bad}" if bad
                 else f"{len(lig)} 个序列均未触发连字")

    # --- 7. 拉丁侧确实来自 Iosevka ---
    latin_w = {hmtx[cmap[cp]][0] for cp in range(0x41, 0x5B) if cp in cmap}
    c.expect(latin_w == {500}, "拉丁字母宽度为 500（等宽）",
             f"实测 {sorted(latin_w)}")

    # --- 8. 中文标点保持双宽 ---
    punct = {cp: hmtx[cmap[cp]][0] for cp in (0x3001, 0x3002, 0xFF0C, 0xFF1A)
             if cp in cmap}
    c.expect(all(v == 1000 for v in punct.values()),
             "中文标点保持双宽（、。，：）",
             "、".join(f"U+{k:04X}={v}" for k, v in punct.items()))

    # --- 8b. 弯引号为中文全角 ---
    if config.FULLWIDTH_QUOTES:
        quotes = {cp: hmtx[cmap[cp]][0]
                  for cp in (0x2018, 0x2019, 0x201C, 0x201D) if cp in cmap}
        ok_q = len(quotes) == 4 and all(v == 1000 for v in quotes.values())
        c.expect(ok_q, "弯引号为中文全角（宽度 1000）",
                 "、".join(f"U+{k:04X}={v}" for k, v in sorted(quotes.items())))

    # --- 8c. 竖排度量 ---
    if config.BUILD_VERTICAL_METRICS:
        has = "vhea" in font and "vmtx" in font
        c.expect(has, "含竖排度量（vhea/vmtx）",
                 f"vhea {font['vhea'].ascent}/{font['vhea'].descent}，"
                 f"vmtx 覆盖 {len(font['vmtx'].metrics)} 个字形" if has
                 else "缺少 vhea/vmtx")

    # --- 9. OFL 保留字体名合规 ---
    # OFL §3 的限制只作用于「呈现给用户的主字体名」（nameID 1/4/6/16/17 等），
    # 而 §2 要求衍生字体必须保留上游版权声明 —— 所以版权字段（nameID 0）、
    # 描述（10）、许可（13）中出现上游名称是**必须的**，不算违规。
    NAME_IDS_PRESENTED = {1, 2, 3, 4, 5, 6, 16, 17, 18, 20, 21, 22}
    presented = " ".join(str(r) for r in font["name"].names
                         if r.nameID in NAME_IDS_PRESENTED)
    hits = [r for r in config.RESERVED_NAMES if r in presented]
    c.expect(not hits, "字体名未使用 OFL 保留字体名（§3）",
             f"命中 {hits}" if hits else "nameID 1/4/6/16/17 中未出现 LXGW / 霞鹜 / 落霞孤鹜")

    # --- 9b. 版权声明中保留上游署名（OFL §2 要求）---
    copyright_text = " ".join(str(r) for r in font["name"].names if r.nameID == 0)
    credited = all(k in copyright_text for k in ("LXGW ZhenKai", "Iosevka"))
    c.expect(credited, "版权声明保留了上游署名（OFL §2）",
             "已署名 LXGW ZhenKai 与 Iosevka" if credited else "缺少上游署名")

    # --- 10. 失效的数字签名已删除 ---
    c.expect("DSIG" not in font, "DSIG（数字签名）已删除")

    # --- 11. Nerd Fonts 图标（仅补丁后检查）---
    if nf:
        icons = {0xE0B0: "Powerline", 0xE0A0: "Powerline 分支",
                 0xE700: "Devicons", 0xF015: "FontAwesome"}
        miss = [f"U+{cp:04X}({n})" for cp, n in icons.items() if cp not in cmap]
        c.expect(not miss, "Nerd Fonts 图标码位存在",
                 f"缺 {miss}" if miss else f"{len(icons)} 个代表性图标就位")
        icon_bad = [f"U+{cp:04X}={hmtx[cmap[cp]][0]}" for cp in icons
                    if cp in cmap and hmtx[cmap[cp]][0] != 500]
        c.expect(not icon_bad, "Nerd Fonts 图标宽度为 500（单格）",
                 "; ".join(icon_bad) if icon_bad else "全部单格")

    font.close()
    return c.report(title or font_path.name)


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1])
    marker = p.stem.split("-")[0][len("MoKaiMono"):]
    spacing_key = {s["file_marker"]: s["key"] for s in config.SPACINGS}.get(marker, "slab")
    expected = None
    ref = config.coverage_reference_path()
    if ref.exists():
        expected = set()
        ref_font = TTFont(str(ref), lazy=True)
        expected = {cp for cp in ref_font.getBestCmap() if ranges.take_from_cjk(cp)}
        ref_font.close()
    verify(p, expected_codepoints=expected,
           spacing=spacing_key, nf="-NF-" in p.name or "-NF-" in p.stem)
