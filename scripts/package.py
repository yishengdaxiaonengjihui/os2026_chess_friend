"""赛事提交打包脚本：产出交付压缩包 + SHA256 清单 + 内容清单。

用法（仓库根目录下）：
    python scripts/package.py                # 打包到 dist/（含版本号）
    python scripts/package.py --dry-run      # 只列出将打包的内容，不产出

产物：
    dist/os2026_chess_friend_v<版本>.zip    # 交付包（不含 .git/.env/data/临时目录）
    dist/os2026_chess_friend_v<版本>.SHA256SUMS   # 校验和清单
    dist/os2026_chess_friend_v<版本>.manifest.txt # 内容清单（文件+字节数）

版本号：从 git 自动取（最近提交数 + 短哈希），如 v1.0.0+b7.8ca2f47。

附带文件（EXTRA_FILES，在仓库外、不进 git）：演示视频等大文件随交付包分发，
zip 内路径为 os2026_chess_friend/demo/demo.mp4；已压缩格式用 ZIP_STORED 不重复压缩。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 兼容 GBK 终端
    except Exception:  # noqa: BLE001
        pass

# 打包内容：目录/文件（相对仓库根）
INCLUDE: list[str] = [
    "backend",
    "frontend",
    "scripts",
    "docs",
    "README.md",
    "LICENSE",
    "requirements.txt",
    "requirements-memory.txt",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "docker-compose.yml",
]

# 附带文件：(源绝对路径, zip 内相对 arcname)；文件不存在时跳过并提示
EXTRA_FILES: list[tuple[str, str]] = [
    (r"D:\dsh\os2026\demo.mp4", "demo/demo.mp4"),  # 演示视频（5 分钟，原片）
]

EXCLUDE_DIR_NAMES = {".git", ".pytest_cache", "__pycache__", ".tmp_pytest_ws", "node_modules", "dist"}
EXCLUDE_FILE_NAMES = {".env", "*.pyc", "*.db", "*.db-wal", "*.db-shm", "*.log"}
ALWAYS_SKIP_REL = {".env"}
STORED_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}


def git_version() -> str:
    try:
        n = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
        h = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
        return f"v1.0.0+b{n}.{h}"
    except Exception:  # noqa: BLE001
        return "v1.0.0"


def _skip(f: Path) -> bool:
    parts = f.relative_to(ROOT).parts
    if parts[0] in ALWAYS_SKIP_REL:
        return True
    for part in parts:
        if part in EXCLUDE_DIR_NAMES or part in EXCLUDE_FILE_NAMES:
            return True
    if f.suffix in (".pyc", ".log"):
        return True
    return False


def collect_entries() -> list[tuple[Path, str]]:
    """返回 (源文件, zip 内 arcname) 列表。"""
    entries: list[tuple[Path, str]] = []
    for rel in INCLUDE:
        p = ROOT / rel
        if p.is_file():
            entries.append((p, rel))
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not _skip(f):
                    entries.append((f, f.relative_to(ROOT).as_posix()))
    for src, arc in EXTRA_FILES:
        sp = Path(src)
        if sp.is_file():
            entries.append((sp, arc))
        else:
            print(f"[warn] 附带文件不存在，跳过：{src}")
    return entries


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    dry = "--dry-run" in sys.argv
    ver = git_version()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    entries = collect_entries()
    if not entries:
        print("没有可打包内容，检查 INCLUDE / EXTRA_FILES 配置")
        sys.exit(1)

    manifest: list[tuple[str, int, str]] = []
    for f, arc in entries:
        manifest.append((arc, f.stat().st_size, sha256_of(f)))

    total = sum(s for _, s, _ in manifest)
    print(f"== 打包清单（{len(manifest)} 文件，{total / 1024 / 1024:.1f} MB）版本 {ver} ==")
    for rel, size, _ in sorted(manifest):
        print(f"  {size:>9,}  {rel}")
    if dry:
        print("\n（--dry-run：未产出压缩包）")
        return

    zip_path = dist / f"os2026_chess_friend_{ver}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, _, _ in sorted(manifest):
            src = next(f for f, a in entries if a == arc)
            method = zipfile.ZIP_STORED if Path(arc).suffix.lower() in STORED_SUFFIXES else zipfile.ZIP_DEFLATED
            z.write(src, arcname=f"os2026_chess_friend/{arc}", compress_type=method)

    sums_path = dist / f"os2026_chess_friend_{ver}.SHA256SUMS"
    sums_path.write_text("".join(f"{h}  os2026_chess_friend/{rel}\n" for rel, _, h in sorted(manifest)), encoding="utf-8")
    manifest_path = dist / f"os2026_chess_friend_{ver}.manifest.txt"
    manifest_path.write_text(
        "".join(f"{size:>10}  {rel}  {h}\n" for rel, size, h in sorted(manifest)), encoding="utf-8"
    )
    print(f"\n[OK] 交付包: {zip_path}（{zip_path.stat().st_size / 1024 / 1024:.1f} MB）")
    print(f"[OK] 校验和: {sums_path}")
    print(f"[OK] 清单:   {manifest_path}")


if __name__ == "__main__":
    main()
