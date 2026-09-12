"""骨架注入式合并。

以 Iosevka Slab 为骨架，只把 CJK 字形「注入」进去。
Iosevka 的 GSUB / GPOS / GDEF / hinting 表在二进制层面完全不被触碰 ——
这是保证连字特性（calt）完好、以及保证拉丁侧渲染质量的关键。

不采用 fontTools.merge.Merger 的对称合并：Iosevka 的 GSUB 包含
99 个 cv01-cv99 + 19 个 ss01-ss20 + 数十个内部特性 + calt 连字，
对称合并极易破坏连字且内存/耗时不可控。
"""
from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._g_l_y_f import Glyph

import config
import ranges

# ---------------------------------------------------------------------------
# OS/2 ulUnicodeRange 位映射（OS/2 规范，bits 0-127 分布于 4 个 32 位字段）
# ---------------------------------------------------------------------------
UNICODE_RANGE_BITS = [
    (0, 0x0000, 0x007F), (1, 0x0080, 0x00FF), (2, 0x0100, 0x017F), (3, 0x0180, 0x024F),
    (4, 0x0250, 0x02AF), (5, 0x02B0, 0x02FF), (6, 0x0300, 0x036F), (7, 0x0370, 0x03FF),
    (9, 0x0400, 0x04FF), (10, 0x0530, 0x058F), (11, 0x0590, 0x05FF), (13, 0x0600, 0x06FF),
    (29, 0x1E00, 0x1EFF), (30, 0x1F00, 0x1FFF), (31, 0x2000, 0x206F), (32, 0x2070, 0x209F),
    (33, 0x20A0, 0x20CF), (34, 0x20D0, 0x20FF), (35, 0x2100, 0x214F), (36, 0x2150, 0x218F),
    (37, 0x2190, 0x21FF), (38, 0x2200, 0x22FF), (39, 0x2300, 0x23FF), (40, 0x2400, 0x243F),
    (42, 0x2460, 0x24FF), (43, 0x2500, 0x257F), (44, 0x2580, 0x259F), (45, 0x25A0, 0x25FF),
    (46, 0x2600, 0x26FF), (47, 0x2700, 0x27BF), (48, 0x3000, 0x303F), (49, 0x3040, 0x309F),
    (50, 0x30A0, 0x30FF), (51, 0x3100, 0x312F), (52, 0x3130, 0x318F), (54, 0x3200, 0x32FF),
    (55, 0x3300, 0x33FF), (56, 0xAC00, 0xD7AF), (57, 0x10000, 0x10FFFF), (59, 0x4E00, 0x9FFF),
    (60, 0xE000, 0xF8FF), (61, 0x31C0, 0x31EF), (62, 0xFB00, 0xFB4F), (65, 0xFE30, 0xFE4F),
    (66, 0xFE50, 0xFE6F), (68, 0xFF00, 0xFFEF), (69, 0xFFF0, 0xFFFF), (82, 0x2800, 0x28FF),
    (90, 0xF0000, 0xFFFFD),
]

CODEPAGE_BITS = [
    (0, 0x0000, 0x00FF),        # Latin 1 (CP1252)
    (17, 0x4E00, 0x9FFF),       # Chinese Traditional (Big5)
    (18, 0x4E00, 0x9FFF),       # Chinese Simplified (GB2312)
    (19, 0x3040, 0x30FF),       # Japanese (ShiftJIS)
    (20, 0xAC00, 0xD7AF),       # Korean Wansung
    (21, 0x4E00, 0x9FFF),       # Chinese Traditional (CNS)
    (22, 0x4E00, 0x9FFF),       # Chinese Simplified (GBK)
]

MANAGED_NAME_IDS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22}


def _apply_os2_bits(os2, cmap) -> None:
    cps = set(cmap)
    ur = [os2.ulUnicodeRange1, os2.ulUnicodeRange2, os2.ulUnicodeRange3, os2.ulUnicodeRange4]
    for bit, lo, hi in UNICODE_RANGE_BITS:
        if any(lo <= c <= hi for c in cps):
            ur[bit // 32] |= 1 << (bit % 32)
    (os2.ulUnicodeRange1, os2.ulUnicodeRange2,
     os2.ulUnicodeRange3, os2.ulUnicodeRange4) = ur

    cr = [os2.ulCodePageRange1, os2.ulCodePageRange2]
    for bit, lo, hi in CODEPAGE_BITS:
        if any(lo <= c <= hi for c in cps):
            cr[bit // 32] |= 1 << (bit % 32)
    os2.ulCodePageRange1, os2.ulCodePageRange2 = cr


def _shift_contours(glyph, dx: float) -> None:
    """水平平移简单字形的控制点（复合字形不处理）。"""
    if glyph.numberOfContours <= 0 or not hasattr(glyph, "coordinates"):
        return
    coords = glyph.coordinates
    for i in range(len(coords)):
        x, y = coords[i]
        coords[i] = (x + dx, y)


def _fit_width(glyph, cur_w: int, target_w: int) -> None:
    """把字形改到目标宽度，并**居中**轮廓。

    参照 Sarasa Gothic 的 CenterTo：改宽度时同步平移轮廓，
    否则字形会贴左、在等宽格子里看着偏。
    """
    if target_w != cur_w:
        _shift_contours(glyph, (target_w - cur_w) / 2)


def _snap_width(adv: int, em: int = 1000) -> int:
    """宽度吸附 —— 参照 Sarasa Gothic 的 toMono：
    向上取整到最近的 em/2 倍数，上限为 em。
    """
    if adv <= 0:
        return 0
    half = em // 2
    return min(em, -(-adv // half) * half)


def _sanitize_quotes(sk_glyf, sk_hmtx, merged_cmap, *, full_width: bool = True
                     ) -> Counter:
    """弯引号统一成全角，并让左引号右移贴住后一个字。

    参照 Sarasa Gothic（make/punct/sanitize-symbols.mjs）的 quoteLeft / quoteRight：
        Gothic 变体：宽度 → em；左引号额外平移 (em - 原宽度)
        其余变体：  宽度 → em/2
    中文排版用全角引号，所以默认走 Gothic 那条分支。
    """
    stats = Counter()
    em = 1000
    for cp, kind in ranges.CJK_QUOTES.items():
        gname = merged_cmap.get(cp)
        if gname is None:
            stats["quote_missing"] += 1
            continue
        glyph = sk_glyf[gname]
        glyph.expand(sk_glyf)
        adv = sk_hmtx.metrics[gname][0]
        target = em if full_width else em // 2
        if full_width:
            # 左引号右移，贴住后一个字；右引号**不平移**（保持靠左）。
            # 这正是 Sarasa 的 quoteLeft / quoteRight 的差异：
            #   quoteLeft  → shiftContours(em - 原宽度) 后 setAdvanceWidth(em)
            #   quoteRight → 只 setAdvanceWidth(em)，不动轮廓
            if kind == "left":
                _shift_contours(glyph, em - adv)
        else:
            _fit_width(glyph, adv, target)
        glyph.recalcBounds(sk_glyf)
        sk_hmtx.metrics[gname] = (target, glyph.xMin)
        stats[f"quote_{kind}"] += 1
    return stats


def _init_vertical_metrics(font, order: list[str], em: int = 1000) -> Counter:
    """为全部字形补一套竖排度量。

    参照 Sarasa Gothic 的 initVhea：CJK 源字体有 vhea/vmtx，Iosevka 没有，
    合并后若不管，竖排中文会退化。统一取 vertical origin = 0.88em、
    bottom = -0.12em，即竖排前进量恰为 1em。
    """
    from fontTools.ttLib import newTable

    stats = Counter()
    glyf = font["glyf"]
    top = round(em * 0.88)
    bottom = round(em * -0.12)

    vmtx = newTable("vmtx")
    vmtx.metrics = {}
    min_tsb = 0
    max_extent = 0
    for gname in order:
        glyph = glyf[gname]
        glyph.expand(glyf)
        y_max = getattr(glyph, "yMax", 0) if glyph.numberOfContours else 0
        tsb = top - y_max
        vmtx.metrics[gname] = (em, tsb)
        min_tsb = min(min_tsb, tsb)
        max_extent = max(max_extent, y_max - bottom)
    font["vmtx"] = vmtx

    vhea = newTable("vhea")
    vhea.tableVersion = 0x00011000
    vhea.ascent = top
    vhea.descent = bottom
    vhea.lineGap = 0
    vhea.advanceHeightMax = em
    vhea.minTopSideBearing = min_tsb
    vhea.minBottomSideBearing = 0
    vhea.yMaxExtent = max_extent
    vhea.caretSlopeRise = 0
    vhea.caretSlopeRun = 1
    vhea.caretOffset = 0
    vhea.reserved1 = vhea.reserved2 = vhea.reserved3 = vhea.reserved4 = 0
    vhea.metricDataFormat = 0
    vhea.numberOfVMetrics = len(order)
    font["vhea"] = vhea
    stats["vmtx_glyphs"] = len(order)
    return stats


def rename_font(font, family: str, style: str, weight_class: int = 400,
                description: str | None = None) -> None:
    """按 WWS 约定重写 name 表（支持四字重家族）。

    family = 排版家族名（例如 "MoKai Mono CN" 或 "MoKai Mono Term NF CN"）
    style  = Light / Regular / Bold

    nameID 1/2 的分组规则（系统靠这两个字段给字体分组）：
        Light   → nameID1 "MoKai Mono Light"    nameID2 "Regular"
        Regular → nameID1 "MoKai Mono"          nameID2 "Regular"
        Bold    → nameID1 "MoKai Mono"          nameID2 "Bold"

    注意 OFL §3：派生字体不得使用保留字体名（LXGW / 霞鹜 / 落霞孤鹜）。
    verify.py 会对此做断言。
    """
    is_bold = style == "Bold"
    legacy_family = family if style in ("Regular", "Bold") else f"{family} {style}"
    legacy_sub = "Bold" if is_bold else "Regular"
    full = family if style == "Regular" else f"{family} {style}"
    ps = f"{family.replace(' ', '')}-{style}"

    values = {
        0: config.COPYRIGHT,
        1: legacy_family,
        2: legacy_sub,
        3: f"{config.VERSION};{config.VENDOR};{ps}",
        4: full,
        5: f"Version {config.VERSION}",
        6: ps,
        8: config.VENDOR,
        9: "Iosevka by Renzhi Li (Belleve Invis); "
           "LXGW WenKai and LXGW ZhenKai by LXGW",
        10: description or config.DESCRIPTION,
        11: "https://github.com/",
        12: "https://github.com/",
        13: "This Font Software is licensed under the SIL Open Font License, "
            "Version 1.1. This font is a Modified Version and is not endorsed by "
            "the original authors.",
        14: "https://openfontlicense.org",
        16: family,
        17: style,
    }

    name = font["name"]
    name.names = [r for r in name.names if r.nameID not in MANAGED_NAME_IDS]
    for nid, val in values.items():
        name.setName(val, nid, 3, 1, 0x409)   # Windows, Unicode BMP, en-US
        name.setName(val, nid, 1, 0, 0)       # Macintosh, Roman, en

    # OS/2 与 head 的字重标记
    os2 = font["OS/2"]
    os2.usWeightClass = weight_class
    sel = (os2.fsSelection & ~0x61) | 0x80    # 清 REGULAR/BOLD，保留其它，置 USE_TYPO_METRICS
    if is_bold:
        sel |= 0x20
    elif style == "Regular":
        sel |= 0x40
    os2.fsSelection = sel
    font["head"].macStyle = 1 if is_bold else 0


def prune_skeleton(src: Path, dst: Path, *, drop_ligatures: bool = False,
                   verbose: bool = True) -> Counter:
    """按字形预算裁剪骨架字体。

    ⚠️ TrueType 的 maxp.numGlyphs 是 uint16，**硬上限 65,535 个字形**。

       裁剪策略：去掉 cv01-cv99（99 个「字符变体」）特性及其独占字形。
       实测 cv* 独占约 24,563 个字形，去掉后骨架从 46,736 降到 22,173，
       与文楷的 32,020 个 CJK 字形相加 = 54,193，留出 11,342 个余量。

       保留：ss01-ss20（19 个风格集）、calt / dlig（连字）、
             frac / numr / dnom / zero / lnum / onum / locl，以及 Iosevka 的内部特性。
       代价：失去逐字符的设计变体（cv*）。终端基本用不到，编辑器里可手动开启。
    """
    from fontTools import subset

    stats = Counter()
    t0 = time.time()

    font = TTFont(str(src), lazy=False, recalcTimestamp=False)
    cmap = font.getBestCmap()
    feats = sorted({r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord})
    keep = [t for t in feats if not t.startswith("cv")]
    stats["features_dropped"] = len(feats) - len(keep)
    if drop_ligatures:
        # 「标准间距 + 无连字」这个组合 Iosevka 官方没有发布，由这里合成：
        # 剔除 calt 特性，其独占的连字字形会被 subsetter 一并回收。
        keep = [t for t in keep if t != "calt"]
        stats["calt_dropped"] = 1

    opts = subset.Options()
    opts.layout_features = keep
    opts.notdef_outline = True
    opts.hinting = True            # 保留 hinting，拉丁侧在 Windows 下更锐利
    opts.glyph_names = True        # 保留字形名（post 2.0 + font-patcher 依赖）
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    opts.drop_tables = []
    opts.recalc_bounds = False
    opts.recalc_timestamp = False

    s = subset.Subsetter(options=opts)
    s.populate(unicodes=set(cmap.keys()))
    s.subset(font)

    order = font.getGlyphOrder()
    font["maxp"].numGlyphs = len(order)
    dst.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(dst))
    font.close()

    stats["skeleton_glyphs"] = len(order)
    stats["elapsed_s"] = round(time.time() - t0, 1)
    if verbose:
        extra = "，并剔除 calt 连字特性" if drop_ligatures else ""
        print(f"  裁剪骨架 → {dst.name}: 保留 {len(keep)} 个特性、"
              f"丢弃 {stats['features_dropped']} 个 cv* 特性{extra}，"
              f"字形 {stats['skeleton_glyphs']}，{stats['elapsed_s']}s")
    return stats


def coverage_reference() -> set[int] | None:
    """允许注入的码位集合。

    RESTRICT_TO_COMMON_COVERAGE = True 时返回**与臻楷重叠**的码位集合，
    使三个字重的字符集完全一致 —— 任何字在任何字重下都不会变豆腐块。
    代价是放弃文楷独有的 9,674 个码位（扩展A 6,431 + 扩展B+ 2,348）。
    """
    if not config.RESTRICT_TO_COMMON_COVERAGE:
        return None
    ref = TTFont(str(config.coverage_reference_path()), lazy=True)
    cmap = ref.getBestCmap()
    allowed = {cp for cp in cmap if ranges.take_from_cjk(cp)}
    ref.close()
    return allowed


def merge(skeleton_path: Path, cjk_paths: list[Path], out_path: Path, *,
          family: str, style: str, weight_class: int = 400,
          description: str | None = None,
          restrict_to: set[int] | None = None,
          verbose: bool = True) -> Counter:
    """把 CJK 字形注入骨架字体并落盘。

    cjk_paths 是**按优先级排序**的 CJK 源列表：逐个码位取第一个含它的源。
    用于 Bold 字重「臻楷为主 + 文楷补缺字」的混合策略。
    """
    t0 = time.time()
    stats = Counter()

    def log(msg):
        if verbose:
            print(msg, flush=True)

    log(f"  载入骨架 : {skeleton_path.name}")
    sk = TTFont(str(skeleton_path), recalcTimestamp=False)

    srcs = []
    for p in cjk_paths:
        f = TTFont(str(p), lazy=False, recalcTimestamp=False)
        srcs.append({
            "path": p, "font": f, "cmap": f.getBestCmap(),
            "glyf": f["glyf"], "hmtx": f["hmtx"], "glyphset": f.getGlyphSet(),
        })
        log(f"  载入 CJK 源[{len(srcs)-1}]: {p.name}")

    if "DSIG" in sk:                      # 修改后签名失效
        del sk["DSIG"]
        stats["dsig_dropped"] = 1

    sk_glyf = sk["glyf"]
    sk_order = list(sk.getGlyphOrder())
    sk_names = set(sk_order)
    sk_cmap = sk.getBestCmap()
    sk_hmtx = sk["hmtx"]

    # 目标码位 = 所有源在 CJK_TAKE 区间内的并集，再与 restrict_to 求交集
    targets: set[int] = set()
    for s in srcs:
        targets |= {cp for cp in s["cmap"] if ranges.take_from_cjk(cp)}
    if restrict_to is not None:
        before = len(targets)
        targets &= restrict_to
        stats["excluded_by_coverage_rule"] = before - len(targets)
    targets = sorted(targets)
    stats["target_codepoints"] = len(targets)

    name_of: dict[tuple[int, str], str] = {}
    added: list[str] = []
    taken: dict[int, str] = {}
    per_source = Counter()
    normalized: list[tuple[int, int, int]] = []

    for cp in targets:
        si = None
        for i, s in enumerate(srcs):
            if cp in s["cmap"]:
                si = i
                break
        if si is None:
            stats["codepoints_unavailable"] += 1
            continue

        s = srcs[si]
        src_name = s["cmap"][cp]
        key = (si, src_name)
        new_name = name_of.get(key)

        if new_name is None:
            new_name = src_name
            if new_name in sk_names:
                new_name = f"cjk{si}." + src_name
            while new_name in sk_names:
                new_name = "_" + new_name
            name_of[key] = new_name
            sk_names.add(new_name)

            g = s["glyf"][src_name]
            g.expand(s["glyf"])
            ng = Glyph()
            ng.numberOfContours = g.numberOfContours
            ng.program = ttProgram.Program()

            if g.isComposite():
                pen = TTGlyphPen(s["glyphset"])
                s["glyphset"][src_name].draw(pen)
                ng = pen.glyph()
                ng.program = ttProgram.Program()
                stats["composite_flattened"] += 1
            elif g.numberOfContours == 0 or not hasattr(g, "coordinates"):
                stats["empty_glyph"] += 1
            else:
                ng.coordinates = g.coordinates
                ng.flags = g.flags
                ng.endPtsOfContours = g.endPtsOfContours
                if getattr(g, "program", None):
                    ng.program = g.program
                stats["simple_glyph"] += 1

            adv, _lsb = s["hmtx"][src_name]
            # 宽度吸附：源字体里存在比例宽度（如文楷的 U+31B4-31B7 注音符号
            # 是 600），必须归一化到 {0,500,1000} 才不破坏等宽不变量。
            # 弯引号例外：保留源宽度，稍后由 _sanitize_quotes 按中文全角规则处理。
            # 规则参照 Sarasa Gothic 的 toMono（向上取整到 em/2 倍数）+ 显式覆盖表。
            if (config.NORMALIZE_INJECTED_WIDTHS
                    and cp not in ranges.CJK_QUOTES
                    and adv not in config.ALLOWED_WIDTHS):
                target = config.WIDTH_OVERRIDES.get(cp, _snap_width(adv))
                _fit_width(ng, adv, target)
                normalized.append((cp, adv, target))
                stats["width_normalized"] += 1
                adv = target
            if ng.numberOfContours > 0:
                ng.recalcBounds(sk_glyf)
            sk_glyf[new_name] = ng
            sk_hmtx.metrics[new_name] = (adv,
                                         ng.xMin if ng.numberOfContours > 0 else 0)
            added.append(new_name)
            per_source[s["path"].name] += 1

        taken[cp] = new_name

    order = sk_order + added
    sk_glyf.glyphOrder = order
    sk.setGlyphOrder(order)
    sk["maxp"].numGlyphs = len(order)
    stats["glyphs_added"] = len(added)
    for k, v in per_source.items():
        stats[f"from_{k}"] = v

    # --- cmap 重建 ---
    merged_cmap = dict(sk_cmap)
    merged_cmap.update(taken)
    bmp = {c: g for c, g in merged_cmap.items() if c <= 0xFFFF}
    byte = {c: g for c, g in merged_cmap.items() if c <= 0xFF}

    new_tables = []
    have12 = any(t.format == 12 for t in sk["cmap"].tables)
    for t in sk["cmap"].tables:
        if t.isUnicode():
            if t.format == 12:
                t.cmap = dict(merged_cmap)
            elif t.format == 0:
                t.cmap = dict(byte)
            else:
                t.cmap = dict(bmp)
        new_tables.append(t)
    if not have12 and any(c > 0xFFFF for c in merged_cmap):
        t = CmapSubtable.newSubtable(12)
        t.platformID, t.platEncID, t.language = 3, 10, 0
        t.cmap = dict(merged_cmap)
        new_tables.append(t)
        stats["cmap12_added"] = 1
    sk["cmap"].tables = new_tables
    stats["cmap_size"] = len(merged_cmap)

    # --- OS/2 ---
    os2 = sk["OS/2"]
    _apply_os2_bits(os2, merged_cmap)
    os2.xAvgCharWidth = 500
    os2.usFirstCharIndex = min(0x20, min(merged_cmap))
    os2.usLastCharIndex = min(0xFFFF, max(merged_cmap))
    os2.usDefaultChar = 0x20
    os2.usBreakChar = 0x20
    sk["head"].fontRevision = config.FONT_REVISION

    # --- 标点清洗：弯引号统一到中文全角（参照 Sarasa Gothic）---
    if config.FULLWIDTH_QUOTES:
        stats.update(_sanitize_quotes(sk_glyf, sk_hmtx, merged_cmap,
                                      full_width=True))

    # --- 竖排度量：为全部字形补 vhea/vmtx（参照 Sarasa 的 initVhea）---
    if config.BUILD_VERTICAL_METRICS:
        stats.update(_init_vertical_metrics(sk, order))

    rename_font(sk, family, style, weight_class, description)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sk.save(str(out_path))
    sk.close()
    for s in srcs:
        s["font"].close()

    stats["total_glyphs"] = len(order)
    stats["elapsed_s"] = round(time.time() - t0, 1)
    log(f"  → {out_path.name}  ({out_path.stat().st_size / 1048576:.1f} MB, "
        f"{stats['elapsed_s']}s, 共 {stats['total_glyphs']} 字形)")
    if normalized:
        log(f"    宽度吸附 {len(normalized)} 个字形，例如 "
            + ", ".join(f"U+{cp:04X}:{a}→{b}" for cp, a, b in normalized[:4]))
    if stats.get("excluded_by_coverage_rule"):
        log(f"    按「与臻楷重叠」规则排除 {stats['excluded_by_coverage_rule']} 个码位")
    return stats
