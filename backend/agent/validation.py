"""
Deterministic grounding/validation utilities.

This layer is intentionally non-LLM:
- It validates that the final assistant message is consistent with tool outputs.
- If validation fails, it deterministically rewrites a grounded response from `detail_data`.
"""

from __future__ import annotations

import re
from typing import Any, Optional


_PS_RE = re.compile(r"\bPS\d{6,10}\b", re.IGNORECASE)


def _normalize_ws(s: str) -> str:
    return " ".join((s or "").split())


def extract_ps_numbers(text: str) -> set[str]:
    return {m.group(0).upper() for m in _PS_RE.finditer(text or "")}


def text_contains_url(text: str, url: str) -> bool:
    if not url:
        return True
    return url in (text or "")


def compatibility_claims_match(text: str, expected_compatible: bool) -> bool:
    t = (text or "").lower()
    if expected_compatible:
        # Must indicate compatibility without an explicit negation.
        if "not compatible" in t or "incompatible" in t:
            return False
        return "compatible" in t or "yes" in t
    else:
        # Must indicate incompatibility/negative.
        if "compatible" in t and "not compatible" not in t and "incompatible" not in t:
            return False
        return "not compatible" in t or "incompatible" in t or "no" in t


def build_grounded_message(response_type: Optional[str], detail_data: Optional[dict]) -> str:
    detail_data = detail_data or {}
    if not response_type:
        return detail_data.get("error") or "I couldn't generate a grounded response."

    if "error" in detail_data and detail_data.get("error"):
        # Tool already provided a deterministic error.
        return str(detail_data.get("error"))

    if response_type == "compatibility":
        part_number = detail_data.get("part_number") or ""
        model_number = detail_data.get("model_number") or ""
        part_name = detail_data.get("part_name") or ""
        compatible = bool(detail_data.get("compatible"))
        source_url = detail_data.get("source_url") or ""

        if compatible:
            base = f"Yes — {part_number} is compatible with {model_number}."
        else:
            base = f"No — {part_number} is not compatible with {model_number}."
        if part_name:
            base += f" ({part_name})"
        if source_url:
            base += f" Source: {source_url}"
        return base

    if response_type == "product":
        part_number = detail_data.get("part_number") or ""
        name = detail_data.get("name") or detail_data.get("part_name") or ""
        price = detail_data.get("price") or ""
        in_stock = detail_data.get("in_stock")
        description = detail_data.get("description") or ""
        source_url = detail_data.get("source_url") or ""

        base = f"{name or part_number}."
        if price:
            base += f" Price: {price}."
        if in_stock is not None:
            base += "In stock." if bool(in_stock) else "Out of stock."
        if description:
            base += f" {description}"
        if source_url:
            base += f" Source: {source_url}"
        return _normalize_ws(base)

    if response_type == "installation":
        part_number = detail_data.get("part_number") or ""
        part_name = detail_data.get("part_name") or ""
        steps = detail_data.get("steps") or []
        source_url = detail_data.get("source_url") or ""

        shown = steps[:6]
        base = f"Installation steps for {part_name or part_number}:"
        if shown:
            base += " " + " ".join([f"Step {i+1}: {s}" for i, s in enumerate(shown)])
        if source_url:
            base += f" Source: {source_url}"
        return _normalize_ws(base)

    if response_type == "troubleshooting":
        symptom = detail_data.get("symptom") or ""
        matched_symptom = detail_data.get("matched_symptom") or ""
        causes = detail_data.get("causes") or []
        source_url = detail_data.get("source_url") or ""

        top_causes = []
        for c in causes[:4]:
            if isinstance(c, dict) and c.get("cause"):
                top_causes.append(c["cause"])
            elif isinstance(c, str):
                top_causes.append(c)
        base = f"Troubleshooting for {symptom or matched_symptom}:"
        if top_causes:
            base += " Likely causes: " + "; ".join(top_causes) + "."
        if source_url:
            base += f" Source: {source_url}"
        return _normalize_ws(base)

    if response_type == "search_results":
        parts = detail_data.get("parts") or []
        query = detail_data.get("query") or ""
        appliance_type = detail_data.get("appliance_type") or ""
        source_url = detail_data.get("source_url") or ""

        part_numbers = [p.get("part_number") for p in parts if isinstance(p, dict) and p.get("part_number")]
        shown = part_numbers[:5]
        base = f"Search results for '{query}' ({appliance_type}): found {len(parts)} parts."
        if shown:
            base += " Examples: " + ", ".join(shown) + "."
        if source_url:
            base += f" Source: {source_url}"
        return _normalize_ws(base)

    # Default safe fallback.
    return detail_data.get("error") or "I couldn't verify that request from indexed data."


def validate_and_maybe_ground(
    *,
    assistant_message: str,
    response_type: Optional[str],
    detail_data: Optional[dict],
) -> str:
    """
    Deterministically validate assistant content against tool outputs.

    If validation fails, return a grounded deterministic rewrite.
    """
    detail_data = detail_data or {}
    msg = assistant_message or ""

    # If there's no tool data, we can't ground.
    if not response_type or detail_data is None or detail_data == {}:
        return assistant_message

    grounded = build_grounded_message(response_type=response_type, detail_data=detail_data)

    # If tool output indicates an error, prefer grounded error message.
    if detail_data.get("error"):
        return grounded

    # Validate key tokens/citations based on response_type.
    try:
        if response_type == "compatibility":
            expected_compatible = bool(detail_data.get("compatible"))
            if not compatibility_claims_match(msg, expected_compatible):
                return grounded

            pn = (detail_data.get("part_number") or "").upper()
            mn = detail_data.get("model_number") or ""
            if pn and pn not in msg.upper():
                return grounded
            if mn and mn not in msg:
                return grounded

            url = detail_data.get("source_url") or ""
            if url and not text_contains_url(msg, url):
                return grounded

        elif response_type in {"product", "installation"}:
            pn = (detail_data.get("part_number") or "").upper()
            url = detail_data.get("source_url") or ""
            if pn and pn not in msg.upper():
                return grounded
            if url and not text_contains_url(msg, url):
                return grounded

        elif response_type == "troubleshooting":
            url = detail_data.get("source_url") or ""
            if url and not text_contains_url(msg, url):
                return grounded

            # Ensure symptom string or normalized symptom appears if present.
            symptom = detail_data.get("symptom") or ""
            matched = detail_data.get("matched_symptom") or ""
            if symptom and symptom.lower() not in msg.lower():
                if matched and matched.lower() not in msg.lower():
                    return grounded

        elif response_type == "search_results":
            url = detail_data.get("source_url") or ""
            if url and not text_contains_url(msg, url):
                return grounded
            # Check at least one part number is mentioned if parts exist.
            parts = detail_data.get("parts") or []
            expected_pn = [p.get("part_number").upper() for p in parts if isinstance(p, dict) and p.get("part_number")]
            if expected_pn:
                found = extract_ps_numbers(msg)
                if not (found & set(expected_pn)):
                    return grounded

    except Exception:
        # Fail closed: if validation errors, return grounded rewrite.
        return grounded

    return assistant_message

