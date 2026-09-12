# 设计文档

MoKai Mono / 墨楷等宽 —— 一款 1:2 严格等宽的中英混排编程字体。

---

## 1. 字体构成

### 1.1 来源

| 部分 | 来源 | 许可证 |
|---|---|---|
| 拉丁 / 希腊 / 西里尔 | [Iosevka Slab](https://github.com/be5invis/Iosevka) | OFL 1.1 |
| 中文（Light / Regular） | [霞鹜文楷 GB](https://github.com/lxgw/LxgwWenKaiGB) | OFL 1.1 + 保留字体名 |
| 中文（Bold） | [霞鹜臻楷 GB](https://github.com/lxgw/LxgwZhenKai) | OFL 1.1 + 保留字体名 |

选用 **GB（G 源字形）** 版本而非普通版，是为了让整个字族符合大陆字形规范，
字体名中的 `CN` 标记即指此。

### 1.2 字重映射

中文侧做了**整体上移一格**的偏移：

| 我们的字重 | 中文 | 拉丁 |
|---|---|---|
| Light | 文楷 GB Regular | Iosevka Slab Light |
| Regular | 文楷 GB Medium | Iosevka Slab Regular |
| **Bold** | **臻楷 GB Regular** | Iosevka Slab Bold |

**偏移的理由**：文楷本身笔画偏细。若按名义字重一一对应（Light↔Light、Regular↔Regular），
中文会明显比拉丁轻，混排时中文"发虚"。上移一格后中西文观感才匹配。
臻楷比文楷更粗，正好充当 Bold。**文楷 Light 字重不使用。**

### 1.3 字宽

两者都是 1000 units/em：

- 文楷 / 臻楷的汉字宽度 = **1000**（占 2 格）
- Iosevka Slab 的拉丁宽度 = **500**（占 1 格）

即 **1:2 严格等宽**，终端里中英混排不会错位。
宽度只能取 Iosevka 的 Normal(500) 档 —— Extended 是 600，会破坏比例。

---

## 2. 变体矩阵与命名

### 2.1 四个维度

| 维度 | 取值 |
|---|---|
| 间距 / 连字 | `Slab` / `NL` / `Term` / `TermNL` |
| hinting | 有 / 无 |
| Nerd Fonts | 有 / 无 |
| 字重 | Light / Regular / Bold |

**共 4 × 2 × 2 × 3 = 48 个字体**（24 个普通版 + 24 个 NF 版）。

间距与连字是两个独立轴，完整 2×2：

| 变体 | 终端优化 | 连字 | 骨架来源 |
|---|---|---|---|
| `MoKaiMono` | ✗ | ✓ | `IosevkaSlab` |
| `MoKaiMonoNL` | ✗ | ✗ | `IosevkaSlab` 人工剔除 `calt` |
| `MoKaiMonoTerm` | ✓ | ✓ | `IosevkaTermSlab` |
| `MoKaiMonoTermNL` | ✓ | ✗ | `IosevkaFixedSlab` |

> Iosevka 官方只发布了三种间距产物，「标准间距 + 无连字」不存在，
> 由本项目在裁剪骨架时剔除 `calt` 特性合成。

### 2.2 命名规则

修饰符拼接顺序：**间距 → NF → CN → unhinted**，无 `unhinted` 标记即带 hinting。
（此约定参照 [Maple Mono](https://github.com/subframe7536/maple-font)。）

```
文件:  MoKaiMono{,-Term,-NL,-TermNL}{-NF}-CN{-unhinted}-{Weight}.ttf
家族:  MoKai Mono{ Term| NL| TermNL}{ NF} CN{ Unhinted}
打包:  MoKaiMono{...}.zip + 同名 .sha256
```

字体内部采用 **WWS 约定**：
`nameID 16` = 家族名，`nameID 17` = 字重；
非 RIBBI 字重的 `nameID 1` = 「家族名 + 字重」、`nameID 2` = `Regular`；
Bold 的 `nameID 1` = 家族名、`nameID 2` = `Bold`。

### 2.3 字符集

**只收录与臻楷重叠的码位**（臻楷是文楷的严格子集），共 **22,365 个**。
这样三个字重的字符集完全一致，任何字在任何字重下都不会变成豆腐块。

代价是放弃文楷独有的 9,674 个码位（CJK 扩展A 6,431 + 扩展B+ 2,348）。
开关：`config.RESTRICT_TO_COMMON_COVERAGE`。

---

## 3. 技术方案

### 3.1 骨架注入，而非对称合并

以 Iosevka 为骨架，只把 CJK 字形**追加**进去，Iosevka 的
GSUB / GPOS / GDEF / hinting 表在二进制层面完全不被触碰。

不采用 `fontTools.merge` 对称合并的原因：Iosevka 的 GSUB 包含
99 个 `cv01-cv99` + 19 个 `ss01-ss20` + 数十个内部特性 + `calt` 连字，
对称合并极易破坏连字，且内存与耗时不可控。

### 3.2 字形数硬上限

`maxp.numGlyphs` 是 **uint16，上限 65,535**。
Iosevka 全量 46,736 + 中文 32,020 = 68,803，超出 3,268。

实测各方案的可达字形数：

| 方案 | 骨架字形 | 合计 | 结论 |
|---|---|---|---|
| 保留全部特性 | 46,736 | 68,803 | 超 3,268 |
| 仅去掉 `ss*` | 46,736 | 68,803 | 超（`ss*` 复用 `cv*` 字形，单独去掉不省） |
| **仅去掉 `cv*`** | **22,173** | **44,240** | 采用，留出余量 |
| 去掉 `cv*` + `ss*` | 15,461 | 37,528 | 可行但没必要 |

**采用方案：去掉 `cv01-cv99`（99 个字符变体）**，保留 `ss01-ss20`、`calt`/`dlig`
连字、`frac`/`numr`/`dnom`/`zero`/`lnum`/`onum`/`locl` 及 Iosevka 的内部特性。
代价是失去逐字符设计变体（终端用不到，编辑器里可手动开启）。

### 3.3 码位归属

只有落在 `ranges.CJK_TAKE` 区间内的码位从中文源取，其余保留骨架字形。
这条单一规则同时保证了：

- 制表符 / 方块元素 / 盲文 / 箭头保持 Iosevka 的宽度（中文源里这些是 1000，会毁掉终端对齐）
- 拉丁 / 希腊 / 西里尔来自 Iosevka（中文源里是比例宽度，会污染等宽性）
- CJK 汉字 / 假名 / 全角形式 / CJK 标点来自中文源

### 3.4 标点处理（参照 Sarasa Gothic）

参照 [Sarasa Gothic](https://github.com/be5invis/Sarasa-Gothic) 的
`make/punct/sanitize-symbols.mjs`：

**弯引号**（`‘’“”`，U+2018/19/1C/1D）
Sarasa 的 `isWestern()` 只把 `< 0x2000` 判为西文，所以引号**从 CJK 字体取字形**，
再由 sanitize 步骤统一宽度。中文排版用全角，因此：

- 宽度统一到 **1000**
- **左引号**（`‘` `“`）额外右移 `em - 原宽度`，让字形贴住后一个字
- **右引号**（`’` `”`）不平移，保持靠左

这正是 Sarasa `quoteLeft` / `quoteRight` 的差异。

**宽度吸附**
Sarasa 的 `toMono` 是**向上取整到 em/2 的倍数**并**居中轮廓**。
本项目采用同样规则；另有显式覆盖表（`config.WIDTH_OVERRIDES`），
用于 U+31B4–31B7 / U+31BB 这几个注音符号 —— Sarasa 对它们也用 `half` 而非 `toMono`。

**制表符**
Iosevka 的制表符本身已可无缝拼接（墨迹触及格子边界），校验中逐字符断言。

### 3.5 竖排度量

中文源有 `vhea`/`vmtx`，Iosevka 没有。参照 Sarasa 的 `initVhea`：
为**全部字形**补竖排度量，vertical origin = 0.88em、bottom = −0.12em，
即竖排前进量恰为 1em。

---

## 4. 不变量

每次构建都对产物断言以下条件，任一不通过即判定失败：

| 检查 | 内容 |
|---|---|
| 字形数上限 | ≤ 65,535 |
| 等宽不变量 | 所有 cmap 字形宽度 ∈ {0, 500, 1000} |
| CJK 覆盖率 | 应取码位全部存在 |
| 终端关键码位 | 制表符/方块/盲文/Powerline 宽度正确（随间距变化） |
| 制表符拼接 | 11 个制表符的墨迹触及应连接的格子边界 |
| CJK 关键码位 | 含 `U+3000` 全角空格（源字体里是空白字形，最易漏） |
| 连字特性 | `calt`/`ccmp` 存在（无连字变体则断言不存在） |
| **连字整形** | harfbuzz 实测，13 个序列全部触发 |
| 拉丁等宽 | 拉丁字母宽度为 500 |
| 中文标点 | `、。，：` 保持双宽 |
| 弯引号 | 为中文全角（1000） |
| 竖排度量 | 含 `vhea`/`vmtx` |
| OFL §3 | 字体名未使用保留字体名 |
| OFL §2 | 版权声明保留上游署名 |
| DSIG | 已删除（修改后签名失效） |
| Nerd Fonts | 图标码位存在且为单格（仅 NF 版） |

---

## 5. 构建流水线

```
src/config.py      全部可调参数；上游版本可用 MOKAI_*_TAG 环境变量覆盖
src/ranges.py      码位归属规则
src/merge.py       骨架裁剪 + 注入合并 + 标点清洗 + 竖排度量 + 命名
src/verify.py      不变量校验
src/patch.py       Nerd Fonts 补丁 + 宽度还原（支持并行）
src/package.py     收拢 + 打包 zip + sha256
src/textrender.py  HarfBuzz 整形 + FreeType 光栅化（展示图用）
src/specimen.py    展示图生成（代码连字、中文排版、制表符、字重瀑布）
src/woff2.py       原生 woff2_compress 转换 + woff2_decompress round-trip 校验
src/build.py       编排
```

```bash
python src/build.py fetch       # 下载上游产物
python src/build.py licenses    # 抓取上游许可证
python src/build.py merge       # 裁剪 + 合并
python src/build.py patch       # Nerd Fonts 补丁
python src/build.py package     # TTF / WOFF2 + zip + sha256
python src/build.py specimen    # HarfBuzz 真实排版展示图
python src/build.py all         # 全流程

--spacing slab|slab-nl|term|term-nl     # 限定间距
--only Light|Regular|Bold     # 限定字重
```

---

## 6. CI/CD

| 工作流 | 触发 | 职责 |
|---|---|---|
| `watch-upstream.yml` | 每日 cron + 手动 | 轮询三个上游的 `releases/latest`，与 `config/upstream.lock.json` 比对，有变化则回写锁文件并触发构建 |
| `build.yml` | 手动 / 被调用 / push | 构建 → 打包 → 发布 Release |

三个上游都没有为下游提供 webhook，所以只能轮询 Releases API
（认证后限额 5000 次/小时，匿名仅 60 次/小时，必须带 token）。
`releases/latest` 天然跳过 `-rc` / `-beta` 等预发布版。

---

## 7. 关键实现细节

### 7.1 Nerd Fonts 补丁会摧毁 CJK 宽度

`font-patcher --mono` 隐含 `--single-width-glyphs`，它会把**字体里所有字形**
都压成单格宽 —— 包括汉字。实测补丁后 4 万个字形的 advance 全变成 500，
汉字 1000 的宽度被摧毁，1:2 设计彻底失效。

好消息是实测确认了两点，使后处理方案成立：

1. 它**只改 advance width，完全不动轮廓**（U+4E00 的墨迹补丁前后逐点相同）
2. **原有字形名全部保留**

因此按字形名把补丁前字形的度量还原回去即可，只保留新增图标字形的单格宽度。

### 7.2 并行补丁的竞态

不能用「共享输出目录 + 目录 diff」识别 patcher 产物：多线程并行时会互相串文件，
导致变体与源文件配错。**必须给每个变体独立的输出目录。**

### 7.3 连字的实现方式

Iosevka 把连字实现为**「左半 + 右半」两个字形的配对**（`.join-r` + `.join-l`），
每个 500 宽、合计 1000 —— 正好跨 2 格，与 1:2 设计天然契合。

因此整形 `=>` 得到的仍是 **2 个字形**，只是从 `equal`+`greater`
变成了 `.join-r` + `.join-l`。**不能用「字形数是否减少」判断连字是否触发**，
必须比对「整串整形结果」与「逐字符整形结果」。

### 7.4 展示图必须走真实排版引擎

Pillow 的 `draw.text` 在 RAQM（harfbuzz）引擎不可用时会**静默退回 BASIC 引擎**，
而 BASIC 引擎不应用 OpenType 特性 —— 连字完全不生效，展示图会失真。

本项目改用 `textrender.py`：直接调 harfbuzz 整形、按 glyph id 交给 freetype
光栅化，渲染结果与真实排版一致。

### 7.5 行高要用 typo 度量

制表符的竖向范围恰好等于字体的 typo 度量（ascent..descent）。
展示图若用拍脑袋的行高倍数，连续的线会被画断，误判成字体缺陷。

---

## 8. 已知限制

- **不含斜体**。中文没有斜体设计，交由编辑器做机械倾斜。
- **不含可变字体**。中文是静态轮廓，无法与 Iosevka 的可变版本组合。
- 为控制在 65,535 字形上限内，去掉了 Iosevka 的 `cv01-cv99` 字符变体特性。
- 字符集限制在与臻楷重叠的 22,365 个码位，不含 CJK 扩展A/B+ 的大部分。
- Nerd Fonts 补丁是构建瓶颈：单变体约 136–330 秒，24 个 NF 变体全量耗时显著，
  CI 上建议提高并行度或分片。
- font-patcher 的输出随 FontForge 版本变化，生产环境必须锁定版本
  （CI 使用固定 digest 的官方 `nerdfonts/patcher` 镜像；FontPatcher.zip 也校验 SHA-256）。
- WOFF2 使用原生 `woff2_compress`，随后用 `woff2_decompress` round-trip 并核对字形数。

---

## 9. 许可证

采用 SIL Open Font License 1.1。这是**修改版本（Modified Version）**。

上游声明的保留字体名为 `霞鹜 / 霞鶩 / 落霞孤鹜 / 落霞孤鶩 / LXGW`，
本衍生字体的名称中不含这些字样（校验中有自动断言）。
完整许可证见 `LICENSES/`。
