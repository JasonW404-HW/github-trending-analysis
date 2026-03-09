"""Website generation using shared HTML renderer."""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

from src.config import GITHUB_PAGES_URL, OUTPUT_DIR, PUSH_MIN_COMMERCIAL_LEVEL
from src.util.print_util import logger
from src.web import EmailReporter


class WebGenerator:
    """Generate website pages and report exports."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or OUTPUT_DIR)
        self.base_path = self._resolve_base_path()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "trending").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "exports").mkdir(parents=True, exist_ok=True)

    def generate_all(self, trends: Dict, date: str, db) -> List[str]:
        if self.base_path:
            logger.info(f"🌐 GitHub Pages Base Path: {self.base_path}")
        else:
            logger.info("🌐 GitHub Pages Base Path: /")

        files: List[str] = []

        opportunity_report = db.get_opportunity_report(
            date=date,
            min_level=PUSH_MIN_COMMERCIAL_LEVEL,
            limit=200,
        )
        export_files = self.generate_opportunity_exports(opportunity_report, date)
        files.extend(export_files.values())

        renderer = EmailReporter()
        shared_html = renderer.generate_email_html(
            trends=trends,
            date=date,
            report=opportunity_report,
            single_repo_mode=False,
        )

        index_path = self.output_dir / "index.html"
        index_path.write_text(shared_html, encoding="utf-8")
        files.append(str(index_path))

        latest_path = self.output_dir / "trending" / "latest.html"
        latest_path.write_text(shared_html, encoding="utf-8")
        files.append(str(latest_path))

        dated_path = self.output_dir / "trending" / f"{date}.html"
        dated_path.write_text(shared_html, encoding="utf-8")
        files.append(str(dated_path))

        logger.info(f"✅ 生成网站文件: {len(files)} 个")
        return files

    def generate_opportunity_exports(self, report: Dict, date: str) -> Dict[str, str]:
        export_dir = self.output_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        projects = report.get("projects", []) or []
        date_name = f"opportunity-report-{date}"

        json_path = export_dir / f"{date_name}.json"
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        csv_path = export_dir / f"{date_name}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as file_handle:
            writer = csv.writer(file_handle)
            writer.writerow(
                [
                    "rank",
                    "repo_name",
                    "stars",
                    "language",
                    "domain",
                    "domain_barrier_level",
                    "maturity_level",
                    "commercial_value_level",
                    "private_deploy_fit",
                    "summary",
                    "commercial_value_reason",
                    "infra_transformation_opportunities",
                    "implemented_features",
                    "current_issues",
                    "roadmap_signals",
                    "future_directions",
                    "tags",
                    "url",
                ]
            )
            for project in projects:
                writer.writerow(
                    [
                        project.get("rank", ""),
                        project.get("repo_name", ""),
                        project.get("stars", 0),
                        project.get("language", ""),
                        project.get("domain", ""),
                        project.get("domain_barrier_level", ""),
                        project.get("maturity_level", ""),
                        project.get("commercial_value_level", "none"),
                        project.get("private_deploy_fit", ""),
                        project.get("summary", ""),
                        project.get("commercial_value_reason", ""),
                        " | ".join(project.get("infra_transformation_opportunities", []) or []),
                        " | ".join(project.get("implemented_features", []) or []),
                        " | ".join(project.get("current_issues", []) or []),
                        " | ".join(project.get("roadmap_signals", []) or []),
                        " | ".join(project.get("future_directions", []) or []),
                        " | ".join(project.get("tags", []) or []),
                        project.get("url", ""),
                    ]
                )

        latest_json = export_dir / "opportunity-report-latest.json"
        latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

        latest_csv = export_dir / "opportunity-report-latest.csv"
        latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")

        return {
            "json": str(json_path),
            "csv": str(csv_path),
            "json_latest": str(latest_json),
            "csv_latest": str(latest_csv),
        }

    def _resolve_base_path(self) -> str:
        from_env = self._normalize_base_path(GITHUB_PAGES_URL)
        if from_env:
            return from_env

        github_repository = os.getenv("GITHUB_REPOSITORY", "")
        if "/" not in github_repository:
            return ""

        owner, repo = github_repository.split("/", 1)
        if repo.lower() == f"{owner.lower()}.github.io":
            return ""

        return f"/{repo}"

    @staticmethod
    def _normalize_base_path(pages_url: str) -> str:
        if not pages_url:
            return ""

        parsed = urlparse(pages_url)
        path = (parsed.path or "").strip()
        if not path:
            return ""

        normalized = "/" + path.strip("/")
        if normalized == "/":
            return ""
        return normalized
