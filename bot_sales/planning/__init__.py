"""Sales planning package with deterministic sales-operator logic."""

from .flow_manager import SalesFlowManager
from .intents import IntentClassifier, IntentResult, SalesIntent
from .pipeline import PipelineStage

__all__ = [
    "SalesFlowManager",
    "IntentClassifier",
    "IntentResult",
    "SalesIntent",
    "PipelineStage",
]
