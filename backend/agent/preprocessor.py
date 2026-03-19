"""Deterministic pre-processor: scope check, entity extraction, slot detection.

No LLM calls — all regex and keyword matching.
"""
import re
from dataclasses import dataclass, field

# Supported appliance keywords
_REFRIGERATOR_KEYWORDS = {
    "refrigerator", "fridge", "freezer", "ice maker", "icemaker",
    "water filter", "ice dispenser", "crisper", "defrost",
}
_DISHWASHER_KEYWORDS = {
    "dishwasher", "dish washer", "spray arm", "drain pump",
    "wash cycle", "rinse aid", "dish rack", "silverware basket",
}
_PART_KEYWORDS = {
    "part", "parts", "model", "replace", "replacement", "install", "installation",
    "fix", "repair", "broken", "not working", "compatible", "compatibility",
    "filter", "valve", "motor", "pump", "gasket", "thermostat", "relay",
    "board", "sensor", "hose", "tube", "drawer", "shelf", "handle",
    "door", "latch", "switch", "element", "fan", "compressor", "fuse",
}
_BRANDS = {
    "whirlpool", "ge", "samsung", "lg", "maytag", "kenmore",
    "frigidaire", "bosch", "kitchenaid", "amana", "electrolux",
}

# Part number pattern: PS followed by digits
_PART_NUMBER_RE = re.compile(r"\bPS\d{6,10}\b", re.IGNORECASE)

# Model number pattern: alphanumeric (at least one letter and one digit, 6+ chars)
# OR all-digit strings of 8+ chars (common for Kenmore models like 10650022211)
_MODEL_NUMBER_RE = re.compile(
    r"\b(?:[A-Z]{2,}[\w-]*\d[\w-]*|\d{8,})\b", re.IGNORECASE
)

# Filter out common false positives for model numbers
_MODEL_FALSE_POSITIVES = {
    "the", "and", "for", "not", "how", "can", "this",
    "what", "with", "from", "that", "have", "will", "are", "was",
}


@dataclass
class PreprocessResult:
    is_in_scope: bool
    entities: dict = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    refusal_message: str = ""


def preprocess(message: str) -> PreprocessResult:
    """Analyze a user message for scope, entities, and missing slots."""
    msg_lower = message.lower()
    entities: dict = {}

    # --- Entity extraction ---

    # Part number
    part_match = _PART_NUMBER_RE.search(message)
    if part_match:
        entities["part_number"] = part_match.group(0).upper()

    # Brand (word-boundary match to avoid substring false positives like "ge" in "leaking")
    for brand in sorted(_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{brand}\b", msg_lower):
            entities["brand"] = brand.title()
            break

    # Appliance type
    for kw in _REFRIGERATOR_KEYWORDS:
        if kw in msg_lower:
            entities["appliance_type"] = "refrigerator"
            break
    if "appliance_type" not in entities:
        for kw in _DISHWASHER_KEYWORDS:
            if kw in msg_lower:
                entities["appliance_type"] = "dishwasher"
                break

    # Model number (extract candidates, filter false positives)
    model_candidates = _MODEL_NUMBER_RE.findall(message)
    for candidate in model_candidates:
        if (
            candidate.lower() not in _MODEL_FALSE_POSITIVES
            and not _PART_NUMBER_RE.match(candidate)
            and len(candidate) >= 6
            and any(c.isdigit() for c in candidate)
            # All-digit model numbers (8+ chars, e.g. Kenmore) are valid;
            # mixed alphanumeric also valid.
            and (candidate.isdigit() or any(c.isalpha() for c in candidate))
        ):
            entities["model_number"] = candidate.upper()
            break

    # --- Scope check ---
    is_in_scope = False

    # In scope if we found a part number or model number
    if "part_number" in entities or "model_number" in entities:
        is_in_scope = True

    # In scope if message mentions supported appliances or part keywords
    if not is_in_scope:
        all_keywords = _REFRIGERATOR_KEYWORDS | _DISHWASHER_KEYWORDS | _PART_KEYWORDS
        if any(kw in msg_lower for kw in all_keywords):
            is_in_scope = True

    # In scope if a known brand is mentioned (likely about an appliance)
    if not is_in_scope and "brand" in entities:
        is_in_scope = True

    refusal = ""
    if not is_in_scope:
        refusal = (
            "I can only help with refrigerator and dishwasher parts from PartSelect. "
            "Could you ask me about finding parts, checking compatibility, "
            "installation help, or troubleshooting for these appliances?"
        )

    return PreprocessResult(
        is_in_scope=is_in_scope,
        entities=entities,
        missing_slots=[],
        refusal_message=refusal,
    )
