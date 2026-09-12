# MoKai Mono 设计与实现

MoKai Mono / 墨楷等宽是一款面向中英混排代码的 **1:2 严格等宽字体**：
拉丁字符占 1 格（500 units），CJK 字符占 2 格（1000 units）。

## 1. 设计决策

### 字体来源

| 部分 | 来源 | 处理 |
|---|---|---|
| 拉丁 / 希腊 / 西里尔 | Iosevka Slab 系列 | 保留原始 GSUB / GPOS / GDEF / hinting |
| Light 中文 | WenKai GB Regular | 注入 CJK 码位 |
| Regular 中文 | WenKai GB Medium | 注入 CJK 码位 |
| Bold 中文 | ZhenKai GB Regular | 注入 CJK 码位 |

`GB` 表示大陆 G 源字形，文件名中的 `CN` 用来明确该来源。
文楷的 Light 不使用：文楷名义字重偏细，整体上移一档后中西文观感更平衡。

### 字符集策略

只保留与 ZhenKai GB 重叠的 CJK 码位，共 **22,365 个**。
臻楷是文楷的严格子集；使用交集可保证三个字重拥有完全一致的字符集，
避免同一字符在 Bold 或 Light 下突然变成豆腐块。

代价是舍弃文楷独有的 9,674 个码位，主要是 CJK 扩展 A 与扩展 B+。

### 间距 / 连字矩阵

间距和连字是两个独立维度，提供完整 2×2：

| 文件前缀 | 终端优化 | 连字 | 拉丁骨架 |
|---|---:|---:|---|
| `MoKaiMono` | 否 | 是 | IosevkaSlab |
| `MoKaiMonoNL` | 否 | 否 | IosevkaSlab，构建时剔除 `calt` |
| `MoKaiMonoTerm` | 是 | 是 | IosevkaTermSlab |
| `MoKaiMonoTermNL` | 是 | 否 | IosevkaFixedSlab |

每种组合再分 hinted / unhinted、普通版 / NF 版、Light / Regular / Bold：

**4 × 2 × 2 × 3 = 48 个字体**（24 个普通版 + 24 个 Nerd Fonts 版）。

### 命名

修饰符顺序参照 Maple Mono：

```
间距 → NF → CN → unhinted → 字重

MoKaiMono-CN-Regular.ttf
MoKaiMonoTerm-NF-CN-Bold.ttf
MoKaiMonoNL-CN-unhinted-Light.ttf
MoKaiMonoTermNL-NF-CN-unhinted-Regular.ttf
```

没有 `unhinted` 即带 hinting。`NF` 表示含 Nerd Fonts 图标。
`CN` 表示大陆 G 源字形。

字体内部使用 WWS 命名：`nameID 16` 是家族，`nameID 17` 是字重。
主字体名不使用上游的 Reserved Font Names。

## 2. 合并算法

### 2.1 骨架注入

不使用对称字体合并。以 Iosevka 为骨架，只追加 CJK 字形：

1. 从 Iosevka 官方 TTF 读取骨架。
2. 为了满足 TrueType `maxp.numGlyphs` 的 uint16 上限，剔除 `cv01-cv99`。
3. 保留 `ss*`、`calt` / `dlig`、数字样式、分数以及内部上下文特性。
4. 按码位范围从文楷 GB / 臻楷 GB 取 CJK 字形。
5. 重建 Unicode cmap，保留 format 12。
6. 删除修改后失效的 DSIG，更新 OS/2 与字体名称。
7. 补齐竖排 `vhea` / `vmtx`。

Iosevka 的布局表不被重新合并，因此连字查找表不会被 CJK 字形污染。

### 2.2 码位归属

CJK 源只负责以下类别：CJK 部首、汉字、假名、注音、CJK 标点、全角形式、
兼容表意文字和 CJK 扩展；制表符、方块元素、盲文、Powerline、拉丁、希腊、
西里尔和普通西文符号保留 Iosevka 版本。

这条边界非常重要：CJK 源中的制表符通常是双宽，直接拿来会破坏终端对齐。

### 2.3 Sarasa Gothic 风格的标点清洗

参照 [Sarasa Gothic](https://github.com/be5invis/Sarasa-Gothic) 的
`make/punct/sanitize-symbols.mjs`：

- 弯引号 `‘’“”` 从 CJK 源取字形，统一为全角 1000。
- 左引号右移至格子的右侧，右引号保持靠左。
- 非法比例宽度按 em/2 规则吸附；注音扩展中特定字符显式设为半宽。
- CJK 标点 `、。，：；！？` 保持双宽。
- 竖排度量使用 0.88em origin / -0.12em bottom，前进量为 1em。

## 3. 连字的正确验证

Iosevka 的编程连字不是简单地把两个字形变成一个字形。
例如 `=>` 通常整形成 `.join-r` + `.join-l` 两个半字宽字形，
总宽仍为 1000。因此不能用“输出字形数量减少”作为判断。

校验程序使用 HarfBuzz 对比：

```
整串整形("=>") != 逐字符整形("=") + 逐字符整形(">")
```

`=>`、`->`、`!=`、`<=`、`>=`、`==`、`|>`、`<-`、`-->`、`=>>`、`::`、`/*`、`*/`
均纳入校验。无连字组合则断言 `calt` 不存在且这些序列不触发替换。

## 4. Nerd Fonts 处理

官方 `font-patcher --mono` 会把所有原有字形的 advance 压成 500，
包括中文；这会摧毁 1:2 宽度。流水线因此分两步：

1. 使用官方 FontPatcher 增加图标。
2. 按原字形名恢复所有原有字形的 advance；新增 Nerd Fonts 图标保留 500。

每个变体使用独立的 patcher 输入 / 输出目录，避免并行构建发生输出串线。
CI 使用按 digest 固定的 `nerdfonts/patcher` 镜像，FontPatcher.zip 同时校验 SHA-256。

## 5. 展示图

展示图不使用 Pillow 的基础绘制排版。Pillow 的 RAQM 不可用时会静默退回 BASIC，
从而完全不应用 OpenType 连字。

`src/textrender.py` 直接使用 HarfBuzz 整形，再用 FreeType 按 glyph id 光栅化。
展示图包含真实使用案例：

- 中英混排代码：`const 求和 = (a, b) => a + b;`
- 运算符连字：`=>`、`!=`、`<=`、`>=`、`|>`、`->`
- 中文全角引号与中文标点
- 终端表格：`┌──┬──┐`、`│ 中文 │ Latin │`
- 字号瀑布、字重对比和字符覆盖网格

所有四种间距 / 连字组合都生成展示图，代表图位于 `docs/images/`。

## 6. 校验清单

每个普通版运行 15 项左右校验，每个 NF 版追加图标与图标宽度校验：

- 字形数 ≤ 65,535
- 所有 cmap 字形宽度属于 `{0, 500, 1000}`
- CJK 交集码位全部存在
- 间距对应的箭头、破折号、制表符宽度正确
- 制表符墨迹触及应连接的边界
- CJK 关键码位（含 U+3000）为双宽
- `calt` / `ccmp` 与 HarfBuzz 连字行为正确
- 拉丁字母为单格
- CJK 标点、弯引号为双宽
- `vhea` / `vmtx` 存在
- OFL Reserved Font Name 不出现在主字体名
- 上游版权声明存在，DSIG 已移除
- NF 图标存在且为单格

## 7. 构建命令

```bash
python src/build.py fetch
python src/build.py licenses
python src/build.py merge
python src/build.py patch
python src/build.py package       # TTF / WOFF2 / zip / sha256
python src/build.py specimen     # HarfBuzz 真实排版展示图
```

限定范围：

```bash
python src/build.py merge --spacing slab-nl --only Regular
python src/build.py specimen --spacing term
```

## 8. CI/CD

- `watch-upstream.yml` 每日读取三个上游仓库的正式版 Release，与 `config/upstream.lock.json`
  对比，有变化时更新锁文件并触发构建。
- `build.yml` 负责安装 `woff2`、下载固定版本上游、合并、NF 补丁、WOFF2、打包和 Release。
- 上游版本可通过 `MOKAI_IOSEVKA_TAG`、`MOKAI_WENKAI_TAG`、`MOKAI_ZHENKAI_TAG` 覆盖。

## 9. 许可

项目是 Modified Version，采用 SIL Open Font License 1.1。
完整许可证与上游版权声明位于 `LICENSE` 和 `LICENSES/`。
禁止单独出售字体文件；随软件分发时必须保留许可证和版权声明。
