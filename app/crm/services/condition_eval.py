from __future__ import annotations

from datetime import datetime
from typing import Any


def _eval_rule(rule: dict[str, Any], ctx: dict[str, Any]) -> bool:
    field = rule.get("field")
    op = rule.get("op", "eq")
    value = rule.get("value")
    actual = ctx.get(field)

    if op == "eq":
        return actual == value
    if op == "neq":
        return actual != value
    if op == "gte":
        return actual is not None and actual >= value
    if op == "lte":
        return actual is not None and actual <= value
    if op == "gt":
        return actual is not None and actual > value
    if op == "lt":
        return actual is not None and actual < value
    if op == "in":
        return actual in (value or [])
    if op == "contains":
        return actual is not None and str(value).lower() in str(actual).lower()

    return False


def matches_conditions(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
    if not conditions:
        return True

    tags_required = set(conditions.get("tags", []))
    ctx_tags = set(context.get("tags", []))
    if tags_required and not tags_required.issubset(ctx_tags):
        return False

    if stage := conditions.get("stage"):
        if context.get("stage") != stage:
            return False

    if channels := conditions.get("channels"):
        if context.get("channel") not in channels:
            return False

    if product_models := conditions.get("product_models"):
        if context.get("product_model") not in product_models:
            return False

    if inactivity_minutes := conditions.get("inactivity_minutes"):
        if int(context.get("inactivity_minutes") or 0) < int(inactivity_minutes):
            return False

    if min_score := conditions.get("min_score"):
        if (context.get("score") or 0) < int(min_score):
            return False

    if max_score := conditions.get("max_score"):
        if (context.get("score") or 0) > int(max_score):
            return False

    if time_window := conditions.get("time_window"):
        now = datetime.utcnow().time()
        start = time_window.get("start", "00:00")
        end = time_window.get("end", "23:59")
        start_h, start_m = [int(x) for x in start.split(":", 1)]
        end_h, end_m = [int(x) for x in end.split(":", 1)]
        start_t = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end_t = now.replace(hour=end_h, minute=end_m, second=59, microsecond=0)
        if not (start_t <= now <= end_t):
            return False

    all_rules = conditions.get("all", [])
    if all_rules and not all(_eval_rule(rule, context) for rule in all_rules):
        return False

    any_rules = conditions.get("any", [])
    if any_rules and not any(_eval_rule(rule, context) for rule in any_rules):
        return False

    return True
