"""将 TTF 转为 WOFF2，并为 webfont 产物做 round-trip 校验。

优先使用原生 woff2_compress：大型 CJK 字体用 fontTools 的纯 Python/Brotli
路径内存开销很高，容易被系统杀掉。CI 通过 apt 安装 woff2。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont

import config


def _tool() -> str:
    candidate = os.environ.get("WOFF2_COMPRESS") or shutil.which("woff2_compress")
    if not candidate:
        raise RuntimeError(
            "找不到 woff2_compress。macOS: brew install woff2；"
            "Ubuntu CI: apt-get install woff2。"
        )
    return candidate


def _decompress_tool() -> str:
    candidate = os.environ.get("WOFF2_DECOMPRESS") or shutil.which("woff2_decompress")
    if not candidate:
        raise RuntimeError(
            "找不到 woff2_decompress，无法完成 WOFF2 round-trip 校验。"
            "macOS: brew install woff2；Ubuntu CI: apt-get install woff2。"
        )
    return candidate


def _roundtrip_check(src: Path, woff2_path: Path) -> None:
    """原生解压后至少解析 maxp，并核对字形数。"""
    with tempfile.TemporaryDirectory(prefix="mokai-woff2-") as td:
        copied = Path(td) / woff2_path.name
        shutil.copy2(woff2_path, copied)
        proc = subprocess.run([_decompress_tool(), str(copied)],
                              capture_output=True, text=True)
        ttf = copied.with_suffix(".ttf")
        if proc.returncode != 0 or not ttf.exists():
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"WOFF2 解压校验失败: {woff2_path.name}\n{detail[-500:]}")
        original = TTFont(str(src), lazy=True)
        restored = TTFont(str(ttf), lazy=True)
        a = original["maxp"].numGlyphs
        b = restored["maxp"].numGlyphs
        original.close()
        restored.close()
        if a != b:
            raise RuntimeError(f"WOFF2 round-trip 字形数不一致: {src.name}: {a} != {b}")


def convert_one(src: Path, dest_dir: Path) -> Path:
    """把一个 TTF 转成同名 WOFF2，并做 native round-trip 校验。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.with_suffix(".woff2").name
    if not (dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime):
        # woff2_compress 固定把输出写在输入文件旁边；在临时目录运行，
        # 既不污染 TTF 目录，也不需要删除旧的中间文件。
        with tempfile.TemporaryDirectory(prefix="mokai-woff2-input-") as td:
            temp_src = Path(td) / src.name
            shutil.copy2(src, temp_src)
            generated = temp_src.with_suffix(".woff2")
            proc = subprocess.run([_tool(), str(temp_src)], capture_output=True, text=True)
            if proc.returncode != 0 or not generated.exists():
                detail = (proc.stderr or proc.stdout or "").strip()
                raise RuntimeError(f"WOFF2 转换失败: {src.name}\n{detail[-500:]}")
            shutil.copy2(generated, dest)
    _roundtrip_check(src, dest)
    return dest


def convert_all(ttf_dir: Path | None = None,
                woff2_dir: Path | None = None) -> list[Path]:
    ttf_dir = ttf_dir or (config.OUT / "ttf")
    woff2_dir = woff2_dir or (config.OUT / "woff2")
    sources = sorted(ttf_dir.glob("*.ttf"))
    if not sources:
        raise RuntimeError(f"没有找到 TTF: {ttf_dir}")
    result = []
    for src in sources:
        out = convert_one(src, woff2_dir)
        result.append(out)
        print(f"  {src.name:<48} → {out.stat().st_size / 1048576:>6.1f} MB")
    print(f"WOFF2 共 {len(result)} 个: {woff2_dir}")
    return result
