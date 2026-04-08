from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


MODEL_PROFILE_DEFAULTS = {
    "cheap": "gpt-4o-mini",
    "balanced": "",
    "rich": "gpt-4o",
}


DEFAULT_PRICING_MICROS_PER_1K = {
    "gpt-4o-mini": {"prompt": 150, "completion": 600},
    "gpt-4o": {"prompt": 2500, "completion": 10000},
    "gpt-4": {"prompt": 30000, "completion": 60000},
}


@dataclass(frozen=True)
class UsageCost:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_micros: int = 0


class TrainingCostEngine:
    """Cost helpers for training sandbox turns."""

    def __init__(self, default_model: str = "gpt-4o"):
        self.default_model = default_model

    def resolve_model(self, profile: str) -> str:
        profile = str(profile or "cheap").strip().lower()
        if profile == "balanced":
            return os.getenv("TRAINING_BALANCED_MODEL", "") or self.default_model
        if profile == "rich":
            return os.getenv("TRAINING_RICH_MODEL", "") or MODEL_PROFILE_DEFAULTS["rich"]
        return os.getenv("TRAINING_CHEAP_MODEL", "") or MODEL_PROFILE_DEFAULTS["cheap"]

    def pricing_for_model(self, model_name: str) -> Dict[str, int]:
        model_name = str(model_name or "").strip()
        env_key = model_name.upper().replace("-", "_").replace(".", "_")
        prompt = os.getenv(f"TRAINING_PRICE_{env_key}_PROMPT_MICROS_PER_1K")
        completion = os.getenv(f"TRAINING_PRICE_{env_key}_COMPLETION_MICROS_PER_1K")
        if prompt and completion:
            try:
                return {"prompt": int(prompt), "completion": int(completion)}
            except ValueError:
                pass
        return DEFAULT_PRICING_MICROS_PER_1K.get(model_name, {"prompt": 0, "completion": 0})

    def estimate(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> UsageCost:
        prompt_tokens = int(prompt_tokens or 0)
        completion_tokens = int(completion_tokens or 0)
        pricing = self.pricing_for_model(model_name)
        prompt_cost = int((prompt_tokens / 1000.0) * int(pricing.get("prompt", 0)))
        completion_cost = int((completion_tokens / 1000.0) * int(pricing.get("completion", 0)))
        return UsageCost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_micros=prompt_cost + completion_cost,
        )

    def daily_token_ceiling(self) -> int:
        return int(os.getenv("TRAINING_DAILY_TOKEN_CEILING", "0") or 0)

    def monthly_token_ceiling(self) -> int:
        return int(os.getenv("TRAINING_MONTHLY_TOKEN_CEILING", "0") or 0)

