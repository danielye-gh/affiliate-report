"""从 GitHub 下载最新代码并覆盖本地文件（自更新）。

发布到 GitHub 后，把 DEFAULT_REPO 改成实际仓库，如 "your-name/affiliate-report"。
也可在 .env 中设置 UPDATE_REPO / UPDATE_BRANCH 覆盖默认值。

更新时永远不会碰以下本地内容（见 PROTECTED_TOP_LEVEL）：
.env、.venv/、data/（含报表、原始数据、独家Code配置）、.git/
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from affiliate_report.config import PROJECT_ROOT

# TODO: 发布后填入实际 GitHub 仓库，格式 "用户名/仓库名"
DEFAULT_REPO = ""
DEFAULT_BRANCH = "main"

# 顶层路径命中即跳过，保护用户本地数据与凭证
PROTECTED_TOP_LEVEL = {
    ".env",
    ".venv",
    ".git",
    "data",
    "src.zip",
    ".DS_Store",
}

# 任意层级命中即跳过
SKIP_ANYWHERE = {"__pycache__", "__MACOSX", ".DS_Store"}

PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


class UpdateError(RuntimeError):
    pass


def _repo_from_git_remote() -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    # 支持 https://github.com/owner/repo(.git) 和 git@github.com:owner/repo(.git)
    for prefix in ("https://github.com/", "git@github.com:"):
        if url.startswith(prefix):
            repo = url[len(prefix):]
            return repo.removesuffix(".git").strip("/")
    return None


def resolve_repo() -> str:
    repo = os.getenv("UPDATE_REPO", "").strip() or DEFAULT_REPO or _repo_from_git_remote()
    if not repo:
        raise UpdateError(
            "未配置更新源。请在 .env 中设置 UPDATE_REPO=用户名/仓库名，"
            "或在 src/affiliate_report/updater.py 中填写 DEFAULT_REPO。"
        )
    return repo


def resolve_branch() -> str:
    return os.getenv("UPDATE_BRANCH", "").strip() or DEFAULT_BRANCH


def _download_zip(repo: str, branch: str, dest: Path, log) -> None:
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    log(f"下载 {url} ...\n")
    request = Request(url, headers={"User-Agent": "affiliate-report-updater"})
    try:
        with urlopen(request, timeout=120) as resp, open(dest, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                f"GitHub 上找不到 {repo} 的 {branch} 分支（HTTP 404）。"
                "请检查 UPDATE_REPO / UPDATE_BRANCH 配置，且仓库必须是 public。"
            ) from exc
        raise UpdateError(f"下载失败：HTTP {exc.code}") from exc
    except URLError as exc:
        raise UpdateError(f"网络错误，无法访问 GitHub：{exc.reason}") from exc


def _should_skip(rel: Path) -> bool:
    if rel.parts[0] in PROTECTED_TOP_LEVEL:
        return True
    if any(part in SKIP_ANYWHERE for part in rel.parts):
        return True
    if rel.suffix == ".pyc" or ".egg-info" in str(rel):
        return True
    return False


def _apply_update(extracted_root: Path, log) -> list[Path]:
    changed: list[Path] = []
    for src in sorted(extracted_root.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(extracted_root)
        if _should_skip(rel):
            continue
        dest = PROJECT_ROOT / rel
        if dest.is_file() and dest.read_bytes() == src.read_bytes():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        changed.append(rel)
        log(f"  更新 {rel}\n")
    return changed


def _reinstall_dependencies(log) -> None:
    log("\n依赖配置有变化，重新安装依赖 ...\n")
    base = [sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT), "-q"]
    result = subprocess.run(base + ["-i", PIP_MIRROR], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        log("镜像源安装失败，改用官方 PyPI 重试 ...\n")
        result = subprocess.run(base, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise UpdateError("依赖安装失败，请检查网络后重新运行 setup 脚本。")


def run_update(log=None) -> list[Path]:
    """下载最新代码并覆盖本地，返回更新过的文件列表。"""
    if log is None:
        log = lambda text: print(text, end="")  # noqa: E731

    repo = resolve_repo()
    branch = resolve_branch()
    log(f"更新源：github.com/{repo}（{branch} 分支）\n")

    with tempfile.TemporaryDirectory(prefix="affiliate-report-update-") as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "update.zip"
        _download_zip(repo, branch, zip_path, log)

        extract_dir = tmp_dir / "extracted"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        roots = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise UpdateError("下载的压缩包结构异常。")

        log("对比并覆盖本地文件（跳过 .env / data / .venv）...\n")
        changed = _apply_update(roots[0], log)

    if not changed:
        log("\n本地已是最新版本，无需更新。\n")
        return changed

    dep_files = {Path("pyproject.toml"), Path("requirements.txt")}
    if dep_files & set(changed):
        _reinstall_dependencies(log)

    log(f"\n更新完成，共更新 {len(changed)} 个文件。请重启程序生效。\n")
    return changed


def main() -> int:
    try:
        run_update()
    except UpdateError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
