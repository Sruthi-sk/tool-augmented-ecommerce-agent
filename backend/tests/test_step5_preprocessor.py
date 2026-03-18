"""Step 5a: Pre-processor tests — deterministic scope check, entity extraction, slot detection."""
import pytest
from agent.preprocessor import preprocess, PreprocessResult


# --- Scope check ---

def test_in_scope_part_query():
    """Part-related queries are in scope."""
    result = preprocess("I need a water filter for my refrigerator")
    assert result.is_in_scope is True


def test_in_scope_model_number():
    """Queries containing model numbers are in scope."""
    result = preprocess("Is this compatible with WDT780SAEM1?")
    assert result.is_in_scope is True


def test_in_scope_part_number():
    """Queries containing PS part numbers are in scope."""
    result = preprocess("How do I install PS11752778?")
    assert result.is_in_scope is True


def test_in_scope_dishwasher():
    """Dishwasher queries are in scope."""
    result = preprocess("My dishwasher is not draining")
    assert result.is_in_scope is True


def test_in_scope_symptom():
    """Symptom descriptions for supported appliances are in scope."""
    result = preprocess("The ice maker on my Whirlpool fridge is not working")
    assert result.is_in_scope is True


def test_out_of_scope_weather():
    """Weather queries are out of scope."""
    result = preprocess("What's the weather today?")
    assert result.is_in_scope is False


def test_out_of_scope_general():
    """General knowledge queries are out of scope."""
    result = preprocess("Who is the president of the United States?")
    assert result.is_in_scope is False


def test_out_of_scope_other_appliance():
    """Non-refrigerator/dishwasher appliance queries are out of scope."""
    result = preprocess("I need a new belt for my washing machine")
    assert result.is_in_scope is False


# --- Entity extraction ---

def test_extract_part_number():
    """Extracts PS-prefixed part numbers."""
    result = preprocess("Tell me about PS11752778")
    assert result.entities.get("part_number") == "PS11752778"


def test_extract_model_number():
    """Extracts appliance model numbers."""
    result = preprocess("Is this compatible with WDT780SAEM1?")
    assert result.entities.get("model_number") is not None
    assert "WDT780SAEM1" in result.entities["model_number"]


def test_extract_brand():
    """Extracts known brand names."""
    result = preprocess("My Whirlpool fridge is leaking")
    assert result.entities.get("brand") == "Whirlpool"


def test_extract_appliance_type_refrigerator():
    """Detects refrigerator from fridge/refrigerator keywords."""
    result = preprocess("My fridge ice maker is broken")
    assert result.entities.get("appliance_type") == "refrigerator"


def test_extract_appliance_type_dishwasher():
    """Detects dishwasher appliance type."""
    result = preprocess("Dishwasher won't drain")
    assert result.entities.get("appliance_type") == "dishwasher"


# --- Preprocess result structure ---

def test_preprocess_result_structure():
    """PreprocessResult has expected fields."""
    result = preprocess("Find me a water filter")
    assert isinstance(result, PreprocessResult)
    assert isinstance(result.is_in_scope, bool)
    assert isinstance(result.entities, dict)
    assert isinstance(result.missing_slots, list)
