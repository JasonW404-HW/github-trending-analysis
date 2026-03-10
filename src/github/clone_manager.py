"""本地仓库克隆与同步管理。"""

import subprocess
from pathlib import Path
from typing import Optional

from src.config import REPO_LOCAL_CLONE_DIR
from src.util.print_util import logger


class CloneManager:
    """管理远程仓库的本地镜像。"""

    def __init__(self, clone_dir: str = REPO_LOCAL_CLONE_DIR):
        self.clone_root = Path(clone_dir)
        self.clone_root.mkdir(parents=True, exist_ok=True)

    def get_repo_path(self, repo_name: str) -> Path:
        safe_name = repo_name.replace("/", "__")
        return self.clone_root / safe_name

    def ensure_latest(self, repo_name: str, repo_url: Optional[str] = None) -> Path:
        repo_path = self.get_repo_path(repo_name)
        url = (repo_url or f"https://github.com/{repo_name}.git").strip()

        if not repo_path.exists():
            self._run(["git", "clone", "--depth", "1", url, str(repo_path)])
            return repo_path

        self._run(["git", "-C", str(repo_path), "fetch", "origin", "--depth", "1"])
        self._run(["git", "-C", str(repo_path), "reset", "--hard", "origin/HEAD"])
        return repo_path

    def get_head_commit_sha(self, repo_name: str) -> str:
        repo_path = self.get_repo_path(repo_name)
        if not repo_path.exists():
            return ""
        result = self._run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
        )
        return (result.stdout or "").strip()

    def _run(self, command: list[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=capture_output,
            )
        except subprocess.CalledProcessError as error:
            logger.warning(f"   ⚠️ git 命令失败: {' '.join(command)} -> {error}")
            raise
