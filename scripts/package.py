"""赛事提交打包脚本：产出交付压缩包 + SHA256 清单 + 内容清单。

用法（仓库根目录下）：
    python scripts/package.py                # 打包到 dist/（含版本号）
    python scripts/package.py --dry-run      # 只列出将打包的内容，不产出

产物：
    dist/os2026_chess_friend_v<版本>.zip    # 交付包（不含 .git/.env/data/临时目录）
    dist/os2026_chess_friend_v<版本>.SHA256SUMS   # 校验和清单
    dist/os2026_chess_friend_v<版本>.manifest.txt # 内容清单（文件+字节数）

版本号：从 git 自动取（最近提交数 + 短哈希），如 v1.0.0+b7.8ca2f47。
"""
from __future__ import annotations

import hashlib
import os
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

# 打包内容：目录/文件（相对仓库根）；黑名单用于排除目录内的杂物
INCLUDE: list[str] = [
    "backend",
    "frontend",
    "scripts",
    "vendor",
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
EXCLUDE_DIR_NAMES = {".git", ".pytest_cache", "__pycache__", ".tmp_pytest_ws", "node_modules", "dist"}
EXCLUDE_FILE_NAMES = {".env", "*.pyc", "*.db", "*.db-wal", "*.db-shm", "*.log"}
ALWAYS_SKIP_REL = {".env"}


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


def collect() -> list[Path]:
    files: list[Path] = []
    for rel in INCLUDE:
        p = ROOT / rel
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not _skip(f):
                    files.append(f)
    return files


def _skip(f: Path) -> bool:
    parts = f.relative_to(ROOT).parts
    if parts[0] in ALWAYS_SKIP_REL:
        return True
    for part in parts:
        if part in EXCLUDE_DIR_NAMES:
            return True
        if part in EXCLUDE_FILE_NAMES:
            return True
    if f.suffix in (".pyc", ".log"):
        return True
    if f.name in (".env",):
        return True
    return False


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
    files = collect()
    if not files:
        print("没有可打包内容，检查 INCLUDE 配置")
        sys.exit(1)

    manifest: list[tuple[str, int, str]] = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        manifest.append((rel, f.stat().st_size, sha256_of(f)))

    total = sum(s for _, s, _ in manifest)
    print(f"== 打包清单（{len(manifest)} 文件，{total / 1024 / 1024:.1f} MB）版本 {ver} ==")
    for rel, size, _ in sorted(manifest):
        print(f"  {size:>9,}  {rel}")
    if dry:
        print("\n（--dry-run：未产出压缩包）")
        return

    zip_path = dist / f"os2026_chess_friend_{ver}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, _, _ in sorted(manifest):
            z.write(ROOT / rel, arcname=f"os2026_chess_friend/{rel}")

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
