"""Nerd Fonts 打补丁 —— 产出 NF 版字体。

使用官方 font-patcher（本机无 Docker，走本地 FontForge）。
⚠️ font-patcher 的输出随 FontForge 版本变化 —— 生产环境必须锁定 FontForge 版本
   或改用固定 tag 的 nerdfonts/patcher 镜像，否则构建不可复现。

单次补丁在 5.4 万字形的字体上约 136s，故用线程池并行（subprocess 会释放 GIL）。
"""
from __future__ import annotations

import shutil
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fontTools.ttLib import TTFont

import config
import merge
import verify

FILE_MARKER_TO_SPACING = {s["file_marker"]: s["key"] for s in config.SPACINGS}


def _patcher_path() -> Path:
    p = config.UPSTREAM / "fontpatcher" / "font-patcher"
    if not p.exists():
        raise SystemExit(
            f"找不到 font-patcher：{p}\n"
            "请下载 https://github.com/ryanoasis/nerd-fonts/releases/latest/download/"
            f"FontPatcher.zip 并解压到 {p.parent}"
        )
    return p


def fontforge_version() -> str:
    try:
        out = subprocess.run(["fontforge", "-version"], capture_output=True,
                             text=True, timeout=30).stdout
        for line in out.splitlines():
            if "Version:" in line:
                return line.split("Version:")[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def parse_variant(stem: str) -> tuple[str, str, bool]:
    """从文件名主干解析 (间距, 字重, 是否有 hinting)。

    例：'MoKaiMonoTermNL-CN-unhinted-Light' -> ('term-nl', 'Light', False)
    """
    parts = stem.split("-")
    weight = parts[-1]
    hinted = "unhinted" not in parts
    base = parts[0]                       # MoKaiMono / MoKaiMonoNL / MoKaiMonoTerm / MoKaiMonoTermNL
    marker = base[len("MoKaiMono"):]      # '' / 'NL' / 'Term' / 'TermNL'
    return FILE_MARKER_TO_SPACING[marker], weight, hinted


def _run_patcher(src: Path, tag: str) -> tuple[Path, float]:
    """在**每个变体独立的输出目录**里跑 patcher。

    ⚠️ 不能用共享目录 + 目录 diff 来识别产物：多线程并行时会互相串文件，
       导致变体与源文件配错（实测踩过：8 个变体因此配错，宽度还原失效）。
    """
    outdir = config.PATCHED / tag
    outdir.mkdir(parents=True, exist_ok=True)

    if config.PATCHER_MODE == "docker":
        # 官方镜像默认扫描 /in 中的全部字体；每个变体必须有独立输入目录，
        # 否则并行时会把同目录里的其它骨架一起打补丁并拿错输出。
        indir = outdir / "in"
        indir.mkdir(parents=True, exist_ok=True)
        input_font = indir / src.name
        shutil.copy2(src, input_font)
        cmd = ["docker", "run", "--rm",
               # 官方镜像内部也支持并行（PN）；外层线程池已经并行，
               # 这里固定单进程，避免 4×PN 嵌套并行压垮 CI runner。
               "-e", "PN=1",
               "-v", f"{indir.resolve()}:/in:ro",
               "-v", f"{outdir.resolve()}:/out",
               config.NERD_DOCKER_IMAGE,
               *config.NERD_PATCHER_ARGS]
    else:
        patcher = _patcher_path()
        cmd = ["fontforge", "-script", str(patcher.resolve()), str(src.resolve()),
               *config.NERD_PATCHER_ARGS, "-out", str(outdir.resolve())]

    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.time() - t0
    if proc.returncode != 0:
        for line in (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]:
            print(f"      {line}")
        raise RuntimeError(f"font-patcher 失败 (exit {proc.returncode}) on {src.name}")

    produced = sorted(outdir.glob("*.ttf"))
    if not produced:
        raise RuntimeError(f"font-patcher 没有产出文件: {src.name}")
    return produced[0], elapsed


def restore_widths(merged: Path, patched: Path, out: Path) -> Counter:
    """还原被 --mono 压平的原有字形宽度。

    ⚠️ 实测发现（本项目最关键的一处坑）：
       font-patcher 的 --mono 隐含 --single-width-glyphs，它会把**字体里所有字形**
       都压成单格宽 —— 包括汉字。实测补丁后 4 万个字形的 advance 全变成 500，
       汉字 1000 的宽度被摧毁，1:2 等宽设计彻底失效。

       但实测同时确认：它**只改 advance width，完全不动轮廓**
       （U+4E00 的墨迹补丁前后逐点相同），且**原有字形名全部保留**。

       因此按字形名把补丁前字形的度量还原回去，只保留新增图标字形的单格宽度。
    """
    src = TTFont(str(merged), lazy=True)
    src_metrics = dict(src["hmtx"].metrics)
    src.close()

    f = TTFont(str(patched), recalcTimestamp=False)
    hmtx = f["hmtx"]
    stats = Counter()
    for name, (adv, lsb) in src_metrics.items():
        if name not in hmtx.metrics:
            stats["missing_in_patched"] += 1
            continue
        if hmtx.metrics[name][0] != adv:
            hmtx.metrics[name] = (adv, lsb)
            stats["restored"] += 1
        else:
            stats["already_correct"] += 1

    f.save(str(out))
    f.close()
    return stats


def _finish(src: Path, spacing: str, weight: str, hinted: bool) -> tuple[Path, bool]:
    """补丁 → 还原宽度 → 恢复命名 → 校验。"""
    w = config.weight(weight)
    tag = src.stem
    nf_name = config.variant_filename(spacing, nf=True, hinted=hinted,
                                      weight_label=weight)
    raw, elapsed = _run_patcher(src, tag)
    final = config.OUT / nf_name
    stats = restore_widths(src, raw, final)
    f = TTFont(str(final), recalcTimestamp=False)
    merge.rename_font(f, config.variant_family(spacing, nf=True, hinted=hinted),
                      weight, w["weight"], config.variant_description(nf=True))
    f.save(str(final))
    f.close()
    # 清理中间产物；某些沙箱环境会拒绝删除，不能因此判定构建失败
    try:
        shutil.rmtree(config.PATCHED / tag, ignore_errors=True)
    except OSError:
        pass

    restrict = merge.coverage_reference()
    ok = verify.verify(final, expected_codepoints=restrict, nf=True,
                       spacing=spacing, title=f"{final.name}")
    print(f"  [{spacing}/{weight}/{'hinted' if hinted else 'unhinted'}] "
          f"{elapsed:.0f}s, 还原 {stats['restored']} 个字形宽度, "
          f"{'OK' if ok else 'FAIL'}")
    return final, ok


def run(only: str | None = None, spacing: str | None = None) -> int:
    print(f"FontForge 版本: {fontforge_version()}")
    print(f"font-patcher 参数: {' '.join(config.NERD_PATCHER_ARGS)}")
    print(f"并行度: {config.PATCH_JOBS}")
    print()

    sources = sorted(config.MERGED.glob("MoKaiMono*.ttf"))
    if only:
        sources = [p for p in sources if p.stem.endswith(f"-{only}")]
    if spacing:
        sources = [p for p in sources if parse_variant(p.stem)[0] == spacing]
    if not sources:
        print(f"{config.MERGED} 下没有可补丁的产物，先运行 python src/build.py merge")
        return 1

    print(f"待补丁 {len(sources)} 个变体")
    print()

    all_ok, results = True, []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=config.PATCH_JOBS) as ex:
        futures = {}
        for src in sources:
            sp, weight, hinted = parse_variant(src.stem)
            futures[ex.submit(_finish, src, sp, weight, hinted)] = src.name
        for fut in as_completed(futures):
            try:
                final, ok = fut.result()
                all_ok &= ok
                results.append((final, ok))
            except Exception as e:  # noqa: BLE001
                print(f"  [FAIL] {futures[fut]}: {e}")
                all_ok = False

    print()
    print("=" * 78)
    print(f"NF 补丁汇总（总耗时 {time.time() - t0:.0f}s）")
    print("=" * 78)
    for out, ok in sorted(results):
        print(f"  {'OK  ' if ok else 'FAIL'} {out.name:<42} "
              f"{out.stat().st_size / 1048576:>6.1f} MB")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
