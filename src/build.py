"""构建流水线编排。

用法：
    python src/build.py fetch              # 下载并校验上游产物
    python src/build.py licenses           # 抓取上游许可证
    python src/build.py merge              # 裁剪骨架 + 注入合并
    python src/build.py patch              # 打 Nerd Fonts 补丁（产出 NF 版）
    python src/build.py package            # 收拢普通版 + 打包 zip + sha256
    python src/build.py specimen           # 渲染对比样张
    python src/build.py all                # 全流程

    --only Regular      限定字重
    --spacing slab      限定间距（slab / slab-nl / term / term-nl）
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import config
import merge
import verify


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  已存在: {dest.name} ({dest.stat().st_size / 1048576:.1f} MB)")
        return
    print(f"  下载 {dest.name} ...")
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=900) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print(f"    完成 ({len(data) / 1048576:.1f} MB, {time.time() - t0:.0f}s)")


# ---------------------------------------------------------------------------
def cmd_fetch(args):
    config.UPSTREAM.mkdir(parents=True, exist_ok=True)
    print("── Iosevka 骨架（4 组合 × 2 hinting；共 6 个上游包）")
    for (skey, hinted), (zip_name, dir_name) in sorted(config.IOSEVKA_PACKAGES.items()):
        url = config.IOSEVKA["base_url"] + zip_name
        zip_path = config.UPSTREAM / zip_name
        _download(url, zip_path)
        target = config.UPSTREAM / dir_name
        if not target.exists() or len(list(target.glob("*.ttf"))) < 50:
            target.mkdir(parents=True, exist_ok=True)
            shutil.unpack_archive(str(zip_path), str(target))
        print(f"    {dir_name}/: {len(list(target.glob('*.ttf')))} TTF")

    print("── CJK 源")
    for name, base in sorted(config.CJK_UPSTREAMS.items()):
        dest = config.UPSTREAM / name
        _download(base + name, dest)
    return 0


def cmd_licenses(args):
    lic_dir = config.ROOT / "LICENSES"
    if not lic_dir.exists():
        lic_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "OFL-LXGWZhenKai.txt":
            "https://raw.githubusercontent.com/lxgw/LxgwZhenKai/main/OFL.txt",
        "OFL-LXGWWenKai.txt":
            "https://raw.githubusercontent.com/lxgw/LxgwWenKai/main/OFL.txt",
        "OFL-Iosevka.md":
            "https://raw.githubusercontent.com/be5invis/Iosevka/main/LICENSE.md",
        "LICENSE-nerd-fonts.txt":
            "https://raw.githubusercontent.com/ryanoasis/nerd-fonts/master/LICENSE",
    }
    for name, url in sources.items():
        out = lic_dir / name
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
            out.write_bytes(data)
            print(f"  {name}: {len(data)} 字节")
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: 抓取失败 ({e})")
    return 0


# ---------------------------------------------------------------------------
def _prune_cached(spacing_key: str, iosevka_weight: str, hinted: bool) -> Path:
    """裁剪骨架并缓存。

    缓存名必须带上「是否剔除连字」的标记 —— slab 与 slab-nl 用的是同一个
    Iosevka 包，若共用缓存会导致其中一个变体拿到错误的骨架。
    """
    key = "hinted" if hinted else "unhinted"
    sp = config.spacing(spacing_key)
    stem = sp["iosevka_stem"]
    lig = "-noliga" if sp["drop_ligatures"] else ""
    dst = config.WORK / f"skeleton-{stem}-{iosevka_weight}-{key}{lig}.ttf"
    src = config.iosevka_path(spacing_key, iosevka_weight, hinted)
    if dst.exists() and dst.stat().st_mtime > src.stat().st_mtime:
        return dst
    merge.prune_skeleton(src, dst, drop_ligatures=sp["drop_ligatures"])
    return dst


def cmd_merge(args):
    spacings = config.SPACINGS
    if args.spacing:
        spacings = [config.spacing(args.spacing)]
    weights = config.WEIGHTS
    if args.only:
        weights = [config.weight(args.only)]

    missing = [p for w in weights for p in config.cjk_paths(w) if not p.exists()]
    if missing:
        print("缺少 CJK 源字体，先运行 python src/build.py fetch：")
        for p in missing:
            print(f"  {p}")
        return 1

    restrict = merge.coverage_reference()
    if restrict is not None:
        print(f"码位策略: 只保留与臻楷重叠的 {len(restrict)} 个码位"
              f"（三个字重字符集完全一致）")
    else:
        print("码位策略: 保留全部 CJK 覆盖（Bold 会比其余字重少 9,674 个字符）")
    print(f"矩阵: {len(spacings)} 间距 × {len(weights)} 字重 × 2 hinting "
          f"= {len(spacings) * len(weights) * 2} 个产物")
    print()

    all_ok, built = True, []
    for s in spacings:
        for w in weights:
            for hinted in (True, False):
                tag = "hinted" if hinted else "unhinted"
                print(f"── {s['key']} / {w['label']} / {tag} " + "─" * 38)
                pruned = _prune_cached(s["key"], w["iosevka_weight"], hinted)
                out = config.MERGED / config.variant_filename(
                    s["key"], nf=False, hinted=hinted, weight_label=w["label"])
                merge.merge(pruned, config.cjk_paths(w), out,
                            family=config.variant_family(s["key"], nf=False,
                                                         hinted=hinted),
                            style=w["label"], weight_class=w["weight"],
                            description=config.variant_description(nf=False),
                            restrict_to=restrict)
                ok = verify.verify(out, expected_codepoints=restrict,
                                   spacing=s["key"], title=f"{out.name}")
                all_ok &= ok
                built.append((f"{s['key']}/{w['label']}/{tag}", out, ok))
                print()

    print("=" * 78)
    print("合并汇总")
    print("=" * 78)
    for label, out, ok in built:
        print(f"  {'OK  ' if ok else 'FAIL'} {label:<26} {out.name:<40} "
              f"{out.stat().st_size / 1048576:>6.1f} MB")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
def cmd_patch(args):
    import patch
    return patch.run(only=args.only, spacing=args.spacing)


def cmd_package(args):
    import package
    return package.run(only=args.only)


def cmd_specimen(args):
    import specimen
    return specimen.run(only=args.only, spacing=args.spacing)


def cmd_all(args):
    for fn in (cmd_fetch, cmd_licenses, cmd_merge, cmd_patch, cmd_package,
               cmd_specimen):
        rc = fn(args)
        if rc:
            return rc
    return 0


def main():
    ap = argparse.ArgumentParser(description="MoKai Mono 构建流水线")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("fetch", cmd_fetch), ("licenses", cmd_licenses),
                     ("merge", cmd_merge), ("patch", cmd_patch),
                     ("package", cmd_package), ("specimen", cmd_specimen),
                     ("all", cmd_all)]:
        p = sub.add_parser(name)
        p.add_argument("--only", help="字重：Light / Regular / Bold")
        p.add_argument("--spacing", help="间距：slab / slab-nl / term / term-nl")
        p.set_defaults(func=fn)
    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
