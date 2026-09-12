"""构建配置 —— 所有可调参数集中在此。

⚠️ OFL 1.1 保留字体名约束
   CJK 源（臻楷 / 文楷）都声明了保留字体名：
       霞鹜 / 霞鶩 / 落霞孤鹜 / 落霞孤鶩 / LXGW
   本项目产出的字体名中 **禁止出现上述任何字符串**。
   `src/verify.py` 会对此做自动断言。

决策记录（2026-09-12）
   拉丁骨架   → Iosevka **Slab** 四种组合各出一套
    CJK 源    → 文楷 GB（大陆 G 源字形）；Bold 用臻楷 GB
    码位范围   → 只保留与臻楷**重叠**的码位，保证三个字重字符集完全一致
    斜体       → 不处理，交由渲染端解决
    命名       → 参照 Maple Mono：修饰符按 间距 → NF → CN → unhinted 拼接
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
UPSTREAM = WORK / "upstream"
MERGED = WORK / "merged"
PATCHED = WORK / "patched"
SPECIMEN = WORK / "specimen"
OUT = ROOT / "out"

FAMILY_STEM = "MoKai Mono"
VERSION = "0.1.0"
VENDOR = "MoKai"
FONT_REVISION = 0.010
GLYPH_VARIANT = "CN"          # 大陆 G 源字形

RESERVED_NAMES = ["LXGW", "lxgw", "霞鹜", "霞鶩", "落霞孤鹜", "落霞孤鶩"]

COPYRIGHT = (
    "Copyright (c) 2026 The MoKai Mono Project. "
    "This font is a Modified Version that combines three fonts: "
    "LXGW WenKai GB and LXGW ZhenKai GB (Copyright (c) LXGW), licensed under the "
    "SIL Open Font License 1.1 with Reserved Font Names; and Iosevka "
    "(Copyright (c) 2015-2026 Renzhi Li, aka. Belleve Invis), "
    "licensed under the SIL Open Font License 1.1. "
    "This font is distributed under the SIL Open Font License 1.1."
)

DESCRIPTION = (
    "MoKai Mono is a 1:2 monospaced programming font for mixed CJK and Latin text. "
    "Latin, Greek and Cyrillic come from Iosevka Slab. CJK glyphs follow the "
    "mainland China (G-source) standard: the Light and Regular weights come "
    "from LXGW WenKai GB, and the Bold weight comes from the bolder LXGW ZhenKai GB. "
    "A Modified Version distributed under the SIL Open Font License 1.1."
)

DESCRIPTION_NF = DESCRIPTION + " Includes Nerd Fonts icon glyphs (Powerline, " \
    "Font Awesome, Material Design Icons, Octicons, Devicons and more)."

# ---------------------------------------------------------------------------
# 上游
#
# 版本号可用环境变量覆盖 —— CI 里由 watch-upstream 工作流传入新版本，
# 不需要改动源码。本地不设环境变量时用下面的默认值。
# ---------------------------------------------------------------------------
import os as _os

def _env_or(name: str, default: str) -> str:
    value = _os.environ.get(name, "").strip()
    return value or default


IOSEVKA_TAG = _env_or("MOKAI_IOSEVKA_TAG", "v34.8.1")
WENKAI_TAG = _env_or("MOKAI_WENKAI_TAG", "v1.522")
ZHENKAI_TAG = _env_or("MOKAI_ZHENKAI_TAG", "v0.825")

IOSEVKA = {
    "repo": "be5invis/Iosevka",
    "tag": IOSEVKA_TAG,
    "base_url": f"https://github.com/be5invis/Iosevka/releases/download/{IOSEVKA_TAG}/",
}

CJK_UPSTREAMS = {
    "LXGWWenKaiGB-Regular.ttf":
        f"https://github.com/lxgw/LxgwWenKaiGB/releases/download/{WENKAI_TAG}/",
    "LXGWWenKaiGB-Medium.ttf":
        f"https://github.com/lxgw/LxgwWenKaiGB/releases/download/{WENKAI_TAG}/",
    "LXGWZhenKaiGB-Regular.ttf":
        f"https://github.com/lxgw/LxgwZhenKai/releases/download/{ZHENKAI_TAG}/",
}

# ---------------------------------------------------------------------------
# 间距 × 连字（两个轴，完整 2×2）
#
#   变体       终端优化  连字   Iosevka 源        说明
#   MoKaiMono     ✗      ✓    IosevkaSlab      标准 Slab，破折号/箭头全宽
#   MoKaiMonoNL   ✗      ✗    IosevkaSlab      同上但人工剔除 calt
#   MoKaiMonoTerm ✓      ✓    IosevkaTermSlab  终端优化，半宽
#   MoKaiMonoTermNL ✓    ✗    IosevkaFixedSlab 官方无连字产物
#
# ⚠️ Iosevka 官方只发布了 3 种间距产物，「标准间距 + 无连字」不存在，
#    由本项目在裁剪骨架时人工剔除 calt 特性合成。
# ---------------------------------------------------------------------------
SPACINGS = [
    {
        "key": "slab", "file_marker": "", "family_marker": "",
        "term_optimized": False, "ligatures": True, "drop_ligatures": False,
        "iosevka_stem": "IosevkaSlab",
        "desc": "标准 Slab：破折号/箭头全宽，带连字",
    },
    {
        "key": "slab-nl", "file_marker": "NL", "family_marker": "NL",
        "term_optimized": False, "ligatures": False, "drop_ligatures": True,
        "iosevka_stem": "IosevkaSlab",
        "desc": "标准 Slab 但无连字（人工剔除 calt）",
    },
    {
        "key": "term", "file_marker": "Term", "family_marker": "Term",
        "term_optimized": True, "ligatures": True, "drop_ligatures": False,
        "iosevka_stem": "IosevkaTermSlab",
        "desc": "终端优化：破折号/箭头半宽，带连字",
    },
    {
        "key": "term-nl", "file_marker": "TermNL", "family_marker": "TermNL",
        "term_optimized": True, "ligatures": False, "drop_ligatures": False,
        "iosevka_stem": "IosevkaFixedSlab",
        "desc": "终端优化且无连字（官方 Fixed 产物）",
    },
]

_IO_VER = IOSEVKA_TAG.lstrip("v")
IOSEVKA_PACKAGES = {
    ("slab", True): (f"PkgTTF-IosevkaSlab-{_IO_VER}.zip", "iosevka"),
    ("slab", False): (f"PkgTTF-Unhinted-IosevkaSlab-{_IO_VER}.zip",
                      "iosevka_unhinted"),
    ("slab-nl", True): (f"PkgTTF-IosevkaSlab-{_IO_VER}.zip", "iosevka"),
    ("slab-nl", False): (f"PkgTTF-Unhinted-IosevkaSlab-{_IO_VER}.zip",
                         "iosevka_unhinted"),
    ("term", True): (f"PkgTTF-IosevkaTermSlab-{_IO_VER}.zip", "iosevka_term"),
    ("term", False): (f"PkgTTF-Unhinted-IosevkaTermSlab-{_IO_VER}.zip",
                      "unhinted-iosevkatermslab"),
    ("term-nl", True): (f"PkgTTF-IosevkaFixedSlab-{_IO_VER}.zip",
                        "iosevkafixedslab"),
    ("term-nl", False): (f"PkgTTF-Unhinted-IosevkaFixedSlab-{_IO_VER}.zip",
                         "unhinted-iosevkafixedslab"),
}

HINTINGS = ["hinted", "unhinted"]

# ---------------------------------------------------------------------------
# 字重（3 个字重）
#
# ⚠️ 字重做了**整体上移一格**的偏移修正：
#     我们的 Light   ← 文楷 GB Regular   + Iosevka Slab Light
#     我们的 Regular ← 文楷 GB Medium    + Iosevka Slab Regular
#     我们的 Bold    ← 臻楷 GB Regular   + Iosevka Slab Bold
#   原因：文楷本身笔画偏细，若按名义字重一一对应，中文会明显比拉丁轻。
#   上移一格后中西文观感才匹配。**不使用文楷 Light 字重。**
#
# `cjk` 是**按优先级排序**的 CJK 源列表：逐个码位取第一个含它的字体。
# Bold 的第二源只在关闭「与臻楷重叠」限制时才起作用（臻楷缺扩展A/B+）。
# ---------------------------------------------------------------------------
WEIGHTS = [
    {"label": "Light", "weight": 300, "iosevka_weight": "Light",
     "cjk": ["LXGWWenKaiGB-Regular.ttf"]},
    {"label": "Regular", "weight": 400, "iosevka_weight": "Regular",
     "cjk": ["LXGWWenKaiGB-Medium.ttf"]},
    {"label": "Bold", "weight": 700, "iosevka_weight": "Bold",
     "cjk": ["LXGWZhenKaiGB-Regular.ttf", "LXGWWenKaiGB-Medium.ttf"]},
]

# ---------------------------------------------------------------------------
# 码位范围策略
#
# True  = 只保留与臻楷（Bold 的源）重叠的码位。
#         三个字重字符集完全一致，任何字在任何字重下都不会变豆腐块。
#         代价：放弃文楷独有的 9,674 个码位（扩展A 6,431 + 扩展B+ 2,348）。
# False = 保留全部 CJK 覆盖，但 Bold 会比其余三个字重少 9,674 个字符。
# ---------------------------------------------------------------------------
RESTRICT_TO_COMMON_COVERAGE = True
COVERAGE_REFERENCE = "LXGWZhenKaiGB-Regular.ttf"

# ---------------------------------------------------------------------------
# 等宽不变量
# ---------------------------------------------------------------------------
ALLOWED_WIDTHS = {0, 500, 1000}

# 注入的 CJK 字形若宽度不在 ALLOWED_WIDTHS 内，按 Sarasa Gothic 的 toMono 规则
# 向上取整到最近的 em/2 倍数并居中轮廓。下表是**显式覆盖**，参照
# Sarasa 的 sanitizerTypesModular（这几个注音符号它也给 half 而不是 toMono）。
NORMALIZE_INJECTED_WIDTHS = True
WIDTH_OVERRIDES = {
    0x31B4: 500, 0x31B5: 500, 0x31B6: 500, 0x31B7: 500, 0x31BB: 500,  # 注音符号
}

# 弯引号是否用中文全角。参照 Sarasa Gothic：其 Gothic 变体给全角（em），
# 其余变体给半角（em/2）。中文排版需要全角，故默认开启。
FULLWIDTH_QUOTES = True

# 是否为全部字形补竖排度量（vhea/vmtx）。参照 Sarasa 的 initVhea。
BUILD_VERTICAL_METRICS = True

# 所有间距下都必须是 500 的终端关键码位
TERMINAL_CRITICAL_COMMON = {
    0x2500: 500, 0x2502: 500, 0x250C: 500,
    0x2588: 500, 0x2591: 500,
    0x2800: 500, 0x28FF: 500,
    0xE0B0: 500,
}

# 随间距而变的码位（Slab 间距下箭头/几何图形是全宽，这是 Iosevka 的设计）
TERMINAL_CRITICAL_PER_SPACING = {
    "slab": {0x2190: 1000, 0x25A0: 1000, 0x2014: 1000},
    "slab-nl": {0x2190: 1000, 0x25A0: 1000, 0x2014: 1000},
    "term": {0x2190: 500, 0x25A0: 500, 0x2014: 500},
    "term-nl": {0x2190: 500, 0x25A0: 500, 0x2014: 500},
}

CJK_CRITICAL = {0x3000: 1000, 0x4E00: 1000, 0x3002: 1000, 0xFF0C: 1000}

REQUIRED_GSUB_FEATURES = ["calt", "ccmp"]

# 连字样本：整形结果必须与「逐字符整形」不同。
# 注意 Iosevka 把连字实现为「左半 + 右半」两个字形（.join-r / .join-l），
# 各 500 宽、合计 1000（跨 2 格），所以不能用「字形数减少」判断。
LIGATURE_SAMPLES = ["=>", "->", "!=", "<=", ">=", "==", "|>", "<-", "-->", "=>>",
                    "::", "/*", "*/"]

BOX_DRAWING_CONTACTS = {
    0x2500: (1, 1, 0, 0), 0x2502: (0, 0, 1, 1),
    0x250C: (0, 1, 0, 1), 0x2510: (1, 0, 0, 1),
    0x2514: (0, 1, 1, 0), 0x2518: (1, 0, 1, 0),
    0x251C: (0, 1, 1, 1), 0x2524: (1, 0, 1, 1),
    0x252C: (1, 1, 0, 1), 0x2534: (1, 1, 1, 0),
    0x253C: (1, 1, 1, 1),
}

NERD_PATCHER_ARGS = ["--complete", "--mono", "--careful", "--has-no-italic"]

# ---------------------------------------------------------------------------
# Nerd Fonts 打补丁的执行方式
#
# "local"  = 直接调用 PATH 上的 fontforge（本机开发用）
# "docker" = 用官方镜像 nerdfonts/patcher（CI 用）
#
# ⚠️ font-patcher 的输出随 FontForge 版本变化，**必须锁定版本**才能可复现。
#    官方镜像内部自编译了已知可用的 FontForge，比 apt 装系统版可靠。
#    镜像 tag 必须固定，不能用 latest。
# ---------------------------------------------------------------------------
PATCHER_MODE = _os.environ.get("MOKAI_PATCHER_MODE", "local")
# Docker Hub tag 4.27.3，固定到 digest；该镜像对应 Nerd Fonts patcher 3.5.x 工具链。
NERD_DOCKER_IMAGE = (
    "nerdfonts/patcher@sha256:5afde49c2b29eb5628bcae0b5e814acc32d39335631228d6532455f9dbe02d3a"
)
NERD_PATCHER_RELEASE = "v3.5.1"
NERD_PATCHER_SHA256 = "42bcb32145499a35732274c7fc48deb434ad0d2e0e118f98527c1479c6fa251a"

# NF 打补丁的并行度（FontForge 单次 136–330s，串行 36 次太久）
PATCH_JOBS = 4


# ---------------------------------------------------------------------------
# 变体命名（修饰符顺序：间距 → NF → CN → unhinted）
# ---------------------------------------------------------------------------
def spacing(key: str) -> dict:
    for s in SPACINGS:
        if s["key"] == key:
            return s
    raise KeyError(key)


def weight(label: str) -> dict:
    for w in WEIGHTS:
        if w["label"] == label:
            return w
    raise KeyError(label)


def variant_family(spacing_key: str, *, nf: bool, hinted: bool) -> str:
    s = spacing(spacing_key)
    parts = [FAMILY_STEM]
    if s["family_marker"]:
        parts.append(s["family_marker"])
    if nf:
        parts.append("NF")
    parts.append(GLYPH_VARIANT)
    if not hinted:
        parts.append("Unhinted")
    return " ".join(parts)


def variant_stem(spacing_key: str, *, nf: bool, hinted: bool) -> str:
    s = spacing(spacing_key)
    parts = ["MoKaiMono" + s["file_marker"]]
    if nf:
        parts.append("NF")
    parts.append(GLYPH_VARIANT)
    if not hinted:
        parts.append("unhinted")
    return "-".join(parts)


def variant_filename(spacing_key: str, *, nf: bool, hinted: bool,
                     weight_label: str) -> str:
    return f"{variant_stem(spacing_key, nf=nf, hinted=hinted)}-{weight_label}.ttf"


def variant_description(nf: bool) -> str:
    return DESCRIPTION_NF if nf else DESCRIPTION


def iosevka_path(spacing_key: str, iosevka_weight: str, hinted: bool) -> Path:
    pkg = IOSEVKA_PACKAGES[(spacing_key, hinted)]
    stem = spacing(spacing_key)["iosevka_stem"]
    return UPSTREAM / pkg[1] / f"{stem}-{iosevka_weight}.ttf"


def cjk_paths(w: dict) -> list[Path]:
    return [UPSTREAM / f for f in w["cjk"]]


def coverage_reference_path() -> Path:
    return UPSTREAM / COVERAGE_REFERENCE


def all_variants() -> list[dict]:
    """完整变体矩阵：间距 × 字重 × hinting × NF。"""
    out = []
    for s in SPACINGS:
        for w in WEIGHTS:
            for hinted in (True, False):
                for nf in (False, True):
                    out.append({
                        "spacing": s["key"], "weight": w["label"],
                        "weight_class": w["weight"],
                        "iosevka_weight": w["iosevka_weight"],
                        "cjk": w["cjk"], "hinted": hinted, "nf": nf,
                        "family": variant_family(s["key"], nf=nf, hinted=hinted),
                        "filename": variant_filename(s["key"], nf=nf, hinted=hinted,
                                                     weight_label=w["label"]),
                    })
    return out
