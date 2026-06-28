"""Question parser for free-text decision queries."""

import re

from services.ontology import UNIVERSAL_METRICS, suggest_criteria, extract_alternatives


def extract_subject(query: str) -> dict:
    """Extract single subject + optional goal from DIAGNOSE-style queries.

    Patterns (ordered most-specific first):
      - "How good is {subject} for {goal}"
      - "How does {subject} perform for {goal}"
      - "How good is {subject}"
      - "How does {subject} perform"
      - "Rate my {subject}"
      - "Evaluate {subject}"
      - "Review {subject}"
      - "What do you think about {subject}"

    Returns: {
        "subject": "Tesla Model 3",
        "goal": "commuting" or None,
        "parsed": True
    }
    or on no match: {
        "subject": "This option",
        "goal": None,
        "parsed": False
    }
    """
    query = query.strip()
    if not query:
        return {"subject": "This option", "goal": None, "parsed": False}

    # Strip trailing question mark
    clean = query.rstrip("?")

    patterns = [
        # Most specific first — with goal (article optional)
        (r"^how\s+good\s+is\s+(?:(?:a|an|the)\s+)?(.+?)\s+for\s+(.+)$", True),
        (r"^how\s+does\s+(?:(?:a|an|the)\s+)?(.+?)\s+perform\s+for\s+(.+)$", True),
        # Without goal (article optional)
        (r"^how\s+good\s+is\s+(?:(?:a|an|the)\s+)?(.+)$", False),
        (r"^how\s+does\s+(?:(?:a|an|the)\s+)?(.+?)\s+perform$", False),
        (r"^rate\s+my\s+(.+)$", False),
        (r"^evaluate\s+(.+)$", False),
        (r"^review\s*(.+)$", False),
        (r"^what\s+do\s+you\s+think\s+about\s+(?:(?:a|an|the)\s+)?(.+)$", False),
    ]

    for pattern, has_goal in patterns:
        match = re.match(pattern, clean, re.IGNORECASE)
        if match:
            subject = match.group(1).strip()
            goal = match.group(2).strip() if has_goal else None

            # Clean up leading articles from subject
            subject = re.sub(
                r"^(a|an|the)\s+", "", subject, flags=re.IGNORECASE
            ).strip()

            if not subject:
                return {"subject": "This option", "goal": goal, "parsed": False}

            return {"subject": subject, "goal": goal, "parsed": True}

    # No pattern matched
    return {"subject": "This option", "goal": None, "parsed": False}


def parse_question(query: str) -> dict:
    """Parse a free-text decision question.

    Returns: {
        "alternatives": ["House", "Apartment"],
        "criteria": [{"name": "Cost", ...}, ...],
        "category": "General",
        "parsed": True
    }
    """
    alternatives = extract_alternatives(query)
    category, criteria = suggest_criteria(query)

    if not alternatives:
        return {
            "parsed": False,
            "alternatives": ["Option A", "Option B"],
            "criteria": UNIVERSAL_METRICS,
            "category": "General",
        }

    return {
        "parsed": True,
        "alternatives": alternatives,
        "criteria": criteria,
        "category": category,
    }
