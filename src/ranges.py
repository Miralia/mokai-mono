"""码位归属规则。

骨架 = Iosevka Slab / Term Slab / Fixed Slab 的对应官方变体。**只有**落在 CJK_TAKE 区间内的码位才从 CJK 源字体取字形，
其余一律保留骨架原有字形。这条单一规则同时保证了：

  * 制表符 / 方块元素 / 盲文 / 箭头等终端关键字形保持 500（骨架版本）
    —— 臻楷里这些是 1000，直接取会毁掉终端表格对齐
  * 拉丁 / 希腊 / 西里尔 / 通用标点来自 Iosevka，保持 500 等宽
    —— 臻楷里这些是比例宽度（600/350/575/…），会污染等宽性
  * 弯引号 ‘ ’ “ ”（U+2018/19/1C/1D）从 CJK 源取，合并阶段按中文排版规则
    统一为全角 1000，并按 Sarasa Gothic 的 quoteLeft / quoteRight 调整轮廓位置
  * CJK 汉字 / 假名 / 全角形式 / CJK 标点来自对应的文楷 GB 或臻楷 GB
"""

# (起始码位, 结束码位) —— 闭区间
CJK_TAKE = [
    (0x2E80, 0x2EFF),    # CJK 部首补充
    (0x2F00, 0x2FDF),    # 康熙部首
    (0x3000, 0x303F),    # CJK 符号和标点（含 U+3000 全角空格、U+3002 。）
    (0x3040, 0x309F),    # 平假名
    (0x30A0, 0x30FF),    # 片假名
    (0x3100, 0x312F),    # 注音符号
    (0x31A0, 0x31BF),    # 注音符号扩展
    (0x31F0, 0x31FF),    # 片假名语音扩展
    (0x3200, 0x32FF),    # 带圈 CJK 字母及月份
    (0x3300, 0x33FF),    # CJK 兼容
    (0x3400, 0x4DBF),    # CJK 扩展 A
    (0x4E00, 0x9FFF),    # CJK 统一表意文字
    (0xF900, 0xFAFF),    # CJK 兼容表意文字
    (0xFE10, 0xFE1F),    # 竖排形式
    (0xFE30, 0xFE4F),    # CJK 兼容形式
    (0xFF01, 0xFF60),    # 全角形式（含全角标点 ，：；！？）
    (0xFF61, 0xFFDC),    # 半角片假名 / 半角谚文
    (0xFFE0, 0xFFEE),    # 全角符号 + 半角形式（含 U+FFE8 半角竖线）
    (0x20000, 0x3FFFF),  # CJK 扩展 B 及以后
]

# 强制保留骨架字形的例外码位。
# PUA 冲突（臻楷的 U+EE01 vs Iosevka 的 U+EE00-EE0B）不需要例外，
# 因为 PUA 不在 CJK_TAKE 区间内，本来就全部保留骨架版本。
FORCE_SKELETON: set[int] = set()

# 弯引号。
#
# 参照 Sarasa Gothic（make/punct/sanitize-symbols.mjs）：
#   它的 isWestern() 只把 `< 0x2000` 判为西文，所以 “”‘’ 会**从 CJK 字体取字形**，
#   再由 sanitizeSymbols 统一调整宽度 —— Gothic 变体给全角（em），
#   其余变体给半角（em/2），且左引号额外右移 (em - 原宽度) 让字形贴住后一个字。
#
# 中文排版需要全角引号，因此这几个码位从 CJK 源取，宽度交由
# merge.py 的 _sanitize_quotes() 统一到 1000 并做同样的位移。
CJK_QUOTES = {
    0x2018: "left",    # ‘
    0x2019: "right",   # ’
    0x201C: "left",    # “
    0x201D: "right",   # ”
}


def take_from_cjk(cp: int) -> bool:
    """该码位是否应从 CJK 源字体取字形。"""
    if cp in FORCE_SKELETON:
        return False
    if cp in CJK_QUOTES:
        return True
    for lo, hi in CJK_TAKE:
        if lo <= cp <= hi:
            return True
    return False


def describe() -> str:
    return " ".join(f"U+{lo:04X}-U+{hi:04X}" for lo, hi in CJK_TAKE)
