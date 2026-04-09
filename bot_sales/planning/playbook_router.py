from __future__ import annotations

import re
from pathlib import Path

from .pipeline import PipelineStage


class PlaybookRouter:
    TAG_PATTERN = re.compile(r"^##\s+\[(?P<tag>[A-Z_]+)\](?:\s+.*)?$")

    def __init__(self, playbook_path: str | Path):
        self.playbook_path = Path(playbook_path)
        self.sections = self._load_sections()

    def _load_sections(self) -> dict[str, str]:
        if not self.playbook_path.exists():
            return {}

        current_tag: str | None = None
        chunks: dict[str, list[str]] = {}

        for line in self.playbook_path.read_text(encoding="utf-8").splitlines():
            match = self.TAG_PATTERN.match(line.strip())
            if match:
                current_tag = match.group("tag")
                chunks.setdefault(current_tag, [])
                continue
            if current_tag:
                chunks[current_tag].append(line.rstrip())

        return {tag: "\n".join(lines).strip() for tag, lines in chunks.items() if "".join(lines).strip()}

    def get_playbook_snippets(self, intent: str, stage: PipelineStage | str) -> list[str]:
        stage_value = PipelineStage(stage)
        requested = []
        specific = self._intent_to_tag(intent)
        if specific:
            requested.append(specific)

        requested.extend(self._stage_default_tags(stage_value))

        snippets: list[str] = []
        seen: set[str] = set()
        for tag in requested:
            if tag in seen:
                continue
            seen.add(tag)
            block = self.sections.get(tag)
            if not block:
                continue
            snippets.append(self._concise(block))
            if len(snippets) >= 2:
                break

        return snippets

    @staticmethod
    def _intent_to_tag(intent: str) -> str | None:
        mapping = {
            "OBJECTION_PRICE": "PRICE_OBJECTION",
            "OBJECTION_TRUST": "TRUST_OBJECTION",
            "OBJECTION_DEPOSIT": "DEPOSIT_OBJECTION",
            "OBJECTION_PAYMENT_INSTALLMENTS": "PAYMENT_METHODS",
            "OBJECTION_DELIVERY": "PAYMENT_METHODS",
            "OBJECTION_CURRENCY": "DOLLAR_DOWN_OBJECTION",
            "BUYING_SIGNAL": "CLOSING_PLAYS",
            "HIGH_INTENT_SIGNAL": "CLOSING_PLAYS",
        }
        return mapping.get(intent)

    @staticmethod
    def _stage_default_tags(stage: PipelineStage) -> list[str]:
        if stage in {PipelineStage.NEW, PipelineStage.QUALIFIED}:
            return ["VALUE_PROP"]
        if stage in {PipelineStage.QUOTED, PipelineStage.NEGOTIATING}:
            return ["VALUE_PROP", "CLOSING_PLAYS"]
        if stage == PipelineStage.NURTURE:
            return ["VALUE_PROP", "CLOSING_PLAYS"]
        return ["VALUE_PROP"]

    @staticmethod
    def _concise(text: str) -> str:
        non_empty = [line.strip() for line in text.splitlines() if line.strip()]
        bullet_lines = [line for line in non_empty if line.startswith("-") or line.startswith("•")]
        chosen = bullet_lines[:3] if bullet_lines else non_empty[:3]
        compact = " ".join(chosen)
        return compact[:220].strip()
