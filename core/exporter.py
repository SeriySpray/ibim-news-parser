"""
IBIM News Parser — Export manager.

Exports articles to JSON, CSV, Markdown, and plain-text formats.
Designed for pipeline integration: the user exports data and processes
it externally rather than editing articles inside the application.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from core.models import NewsArticle

logger = logging.getLogger(__name__)


class Exporter:
    """Static export utilities for ``NewsArticle`` collections.

    Every method writes to the given *filepath* and returns ``True``
    on success or ``False`` on failure.  All text is encoded as UTF-8
    with ``ensure_ascii=False`` for proper Unicode support.
    """

    # ── JSON ──────────────────────────────────────────────────────────

    @staticmethod
    def export_to_json(articles: List[NewsArticle], filepath: Path) -> bool:
        """Export articles as a pretty-printed JSON array.

        Args:
            articles: Articles to export.
            filepath: Destination ``.json`` file.

        Returns:
            ``True`` on success, ``False`` on error.
        """
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            data = [article.to_dict() for article in articles]
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            logger.info("Exported %d articles to JSON → %s", len(articles), filepath)
            return True
        except Exception as exc:
            logger.error("JSON export failed: %s", exc)
            return False

    # ── CSV ───────────────────────────────────────────────────────────

    @staticmethod
    def export_to_csv(articles: List[NewsArticle], filepath: Path) -> bool:
        """Export articles as a CSV file with UTF-8-BOM encoding.

        The BOM ensures proper display when opened in Microsoft Excel.

        Args:
            articles: Articles to export.
            filepath: Destination ``.csv`` file.

        Returns:
            ``True`` on success, ``False`` on error.
        """
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            headers = [
                "id",
                "company_ticker",
                "company_name",
                "title",
                "content",
                "summary",
                "source",
                "source_url",
                "published_at",
                "fetched_at",
                "sentiment",
                "tags",
                "user_notes",
                "is_edited",
                "is_starred",
            ]

            with open(filepath, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                for article in articles:
                    row = article.to_dict()
                    # Flatten tags list back to a JSON string for the CSV cell
                    if isinstance(row.get("tags"), list):
                        row["tags"] = json.dumps(
                            row["tags"], ensure_ascii=False
                        )
                    writer.writerow(row)

            logger.info("Exported %d articles to CSV → %s", len(articles), filepath)
            return True
        except Exception as exc:
            logger.error("CSV export failed: %s", exc)
            return False

    # ── Markdown ──────────────────────────────────────────────────────

    @staticmethod
    def export_to_markdown(articles: List[NewsArticle], filepath: Path) -> bool:
        """Export articles as a readable Markdown document.

        Each article becomes a ``##`` section with metadata and content.

        Args:
            articles: Articles to export.
            filepath: Destination ``.md`` file.

        Returns:
            ``True`` on success, ``False`` on error.
        """
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            lines: List[str] = [
                f"# IBIM News Export",
                f"",
                f"*Exported on {datetime.now().strftime('%Y-%m-%d %H:%M')}*  ",
                f"*Total articles: {len(articles)}*",
                "",
                "---",
                "",
            ]

            for article in articles:
                pub_date = (
                    article.published_at.strftime("%Y-%m-%d %H:%M")
                    if article.published_at
                    else "N/A"
                )
                star = " ⭐" if article.is_starred else ""

                lines.append(f"## {article.title}{star}")
                lines.append("")
                lines.append(
                    f"**Ticker:** {article.company_ticker} | "
                    f"**Company:** {article.company_name}"
                )
                lines.append(
                    f"**Source:** {article.source} | "
                    f"**Published:** {pub_date}"
                )
                if article.sentiment:
                    lines.append(f"**Sentiment:** {article.sentiment}")
                if article.tags_list:
                    lines.append(
                        f"**Tags:** {', '.join(article.tags_list)}"
                    )
                if article.source_url:
                    lines.append(f"**URL:** {article.source_url}")
                lines.append("")

                if article.summary:
                    lines.append(f"> {article.summary}")
                    lines.append("")

                if article.content:
                    lines.append(article.content)
                    lines.append("")

                if article.user_notes:
                    lines.append(f"**Notes:** {article.user_notes}")
                    lines.append("")

                lines.append("---")
                lines.append("")

            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))

            logger.info(
                "Exported %d articles to Markdown → %s", len(articles), filepath
            )
            return True
        except Exception as exc:
            logger.error("Markdown export failed: %s", exc)
            return False

    # ── Plain text ────────────────────────────────────────────────────

    @staticmethod
    def export_to_txt(articles: List[NewsArticle], filepath: Path) -> bool:
        """Export articles as plain text — ideal for NLP pipelines.

        Each article's raw content is written sequentially, separated by
        a visual divider.  Minimal metadata is included.

        Args:
            articles: Articles to export.
            filepath: Destination ``.txt`` file.

        Returns:
            ``True`` on success, ``False`` on error.
        """
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            divider = "=" * 72

            parts: List[str] = []
            for article in articles:
                pub_date = (
                    article.published_at.strftime("%Y-%m-%d")
                    if article.published_at
                    else "N/A"
                )
                header = (
                    f"{article.title}\n"
                    f"{article.company_ticker} | {article.source} | {pub_date}"
                )
                body = article.content if article.content else article.summary
                parts.append(f"{header}\n\n{body}")

            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(f"\n{divider}\n\n".join(parts))
                if parts:
                    fh.write("\n")

            logger.info(
                "Exported %d articles to TXT → %s", len(articles), filepath
            )
            return True
        except Exception as exc:
            logger.error("TXT export failed: %s", exc)
            return False

    # ── Batch ─────────────────────────────────────────────────────────

    @staticmethod
    def export_batch(
        articles: List[NewsArticle],
        directory: Path,
        formats: List[str],
    ) -> Dict[str, Path]:
        """Export articles to multiple formats at once.

        Files are named ``{ticker}_{date_from}_{date_to}.{ext}`` where
        the ticker and date range are derived from the articles.

        Args:
            articles: Articles to export.
            directory: Target directory for the exported files.
            formats: List of format strings, each one of
                     ``"json"``, ``"csv"``, ``"markdown"``, ``"txt"``.

        Returns:
            A dict mapping each requested format to the written filepath,
            or to ``None`` if that format failed.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        # Derive a sensible base filename from the article collection
        tickers = sorted({a.company_ticker for a in articles if a.company_ticker})
        ticker_label = tickers[0] if len(tickers) == 1 else "MIXED"

        dates = [
            a.published_at
            for a in articles
            if a.published_at is not None
        ]
        if dates:
            date_from = min(dates).strftime("%Y%m%d")
            date_to = max(dates).strftime("%Y%m%d")
        else:
            today = datetime.now().strftime("%Y%m%d")
            date_from = today
            date_to = today

        basename = f"{ticker_label}_{date_from}_{date_to}"

        format_map = {
            "json": (".json", Exporter.export_to_json),
            "csv": (".csv", Exporter.export_to_csv),
            "markdown": (".md", Exporter.export_to_markdown),
            "txt": (".txt", Exporter.export_to_txt),
        }

        results: Dict[str, Path] = {}
        for fmt in formats:
            key = fmt.lower().strip()
            if key not in format_map:
                logger.warning("Unknown export format requested: %s", fmt)
                continue
            ext, export_fn = format_map[key]
            filepath = directory / f"{basename}{ext}"
            success = export_fn(articles, filepath)
            results[key] = filepath if success else None

        return results
