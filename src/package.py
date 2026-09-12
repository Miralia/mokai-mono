"""打包：收拢 TTF / WOFF2、生成 zip 包与校验和。

发布结构参照 Maple Mono：

    out/
    ├── ttf/                         48 个 TTF + 单文件 sha256
    ├── woff2/                       48 个 WOFF2 + 单文件 sha256
    ├── MoKaiMono-CN.zip             每个变体族一个 TTF 包
    ├── MoKaiMono-CN-Woff2.zip       每个变体族一个 WOFF2 包
    └── *.sha256
"""
from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

import config
import woff2


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksum(path: Path) -> Path:
    digest = _sha256_file(path)
    out = path.with_suffix(path.suffix + ".sha256")
    out.write_text(f"{digest}  {path.name}\n")
    return out


def _variant_stems() -> list[str]:
    out = []
    for s in config.SPACINGS:
        for nf in (False, True):
            for hinted in (True, False):
                out.append(config.variant_stem(s["key"], nf=nf, hinted=hinted))
    return out


def _copy_plain_ttf(ttf_dir: Path, only: str | None) -> int:
    count = 0
    for src in sorted(config.MERGED.glob("MoKaiMono*.ttf")):
        if only and not src.stem.endswith(f"-{only}"):
            continue
        shutil.copy2(src, ttf_dir / src.name)
        count += 1
    return count


def _move_nf_ttf(ttf_dir: Path, only: str | None) -> int:
    count = 0
    for src in sorted(config.OUT.glob("MoKaiMono*-NF-*.ttf")):
        if only and not src.stem.endswith(f"-{only}"):
            continue
        dest = ttf_dir / src.name
        if src.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
        count += 1
    return count


def _zip_group(directory: Path, stem: str, suffix: str,
               license_dir: Path, readme: Path, only: str | None) -> Path | None:
    members = sorted(directory.glob(f"{stem}-*.{suffix}"))
    if only:
        members = [m for m in members if m.stem.endswith(f"-{only}")]
    if not members:
        return None

    name = f"{stem}{'-Woff2' if suffix == 'woff2' else ''}.zip"
    zpath = config.OUT / name
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for member in members:
            z.write(member, member.name)
        for license_file in sorted(license_dir.glob("*")):
            z.write(license_file, f"LICENSES/{license_file.name}")
        if readme.exists():
            z.write(readme, "README.md")
    _write_checksum(zpath)
    return zpath


def _clear_generated_files(directory: Path, suffix: str) -> None:
    """清理本次流水线管理的旧文件，避免旧矩阵混入新 zip。"""
    directory.mkdir(parents=True, exist_ok=True)
    for pattern in (f"MoKaiMono*.{suffix}", f"MoKaiMono*.{suffix}.sha256"):
        for path in directory.glob(pattern):
            path.unlink()


def run(only: str | None = None) -> int:
    ttf_dir = config.OUT / "ttf"
    _clear_generated_files(ttf_dir, "ttf")
    _clear_generated_files(config.OUT / "woff2", "woff2")

    plain = _copy_plain_ttf(ttf_dir, only)
    nf = _move_nf_ttf(ttf_dir, only)
    print(f"普通版收拢: {plain} 个")
    print(f"NF 版收拢: {nf} 个")

    for p in sorted(ttf_dir.glob("*.ttf")):
        _write_checksum(p)
    print(f"TTF 单文件校验和: {len(list(ttf_dir.glob('*.ttf.sha256')))} 个")

    print("生成 WOFF2 ...")
    woff2_dir = config.OUT / "woff2"
    woff2.convert_all(ttf_dir, woff2_dir)
    for p in sorted(woff2_dir.glob("*.woff2")):
        _write_checksum(p)
    print(f"WOFF2 单文件校验和: {len(list(woff2_dir.glob('*.woff2.sha256')))} 个")

    license_dir = config.ROOT / "LICENSES"
    readme = config.ROOT / "README.md"
    for stem in _variant_stems():
        for name in (f"{stem}.zip", f"{stem}.zip.sha256",
                     f"{stem}-Woff2.zip", f"{stem}-Woff2.zip.sha256"):
            path = config.OUT / name
            if path.exists():
                path.unlink()
    made_ttf, made_woff2 = [], []
    for stem in _variant_stems():
        p = _zip_group(ttf_dir, stem, "ttf", license_dir, readme, only)
        if p:
            made_ttf.append(p)
        p = _zip_group(woff2_dir, stem, "woff2", license_dir, readme, only)
        if p:
            made_woff2.append(p)

    print()
    print("=" * 78)
    print(f"产物目录: {config.OUT}")
    print(f"TTF 包 {len(made_ttf)} 个，WOFF2 包 {len(made_woff2)} 个")
    print("=" * 78)
    for p in sorted(made_ttf + made_woff2):
        print(f"  {p.name:<46} {p.stat().st_size / 1048576:>7.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
