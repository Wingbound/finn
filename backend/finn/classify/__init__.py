from finn.models import Classification


def default_classification() -> Classification:
    """The fallback when neither the rules nor the LLM produced a usable classification."""
    return Classification(category="unclassified", by="default", confidence=0.0)
