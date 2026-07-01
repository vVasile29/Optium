"""Universal criteria ontology — MCDA-based framework for decision analysis.

Based on multi-criteria decision analysis (MCDA) theory (Keeney's Value-Focused
Thinking, Belton & Stewart's MCDA framework), these 6 universal value dimensions
cover the minimum criteria set applicable to virtually ANY decision.
"""

import re
from typing import List

UNIVERSAL_DIMENSIONS = [
    {
        "name": "Financial",
        "description": "Monetary costs, budget, price, and financial resources",
        "keywords": [
            "cost",
            "price",
            "budget",
            "money",
            "expensive",
            "cheap",
            "afford",
            "financial",
            "economic",
            "dollar",
            "fee",
            "expense",
        ],
        "metrics": [
            {
                "name": "Cost",
                "description": "Cost fit and affordability",
                "default_weight": 90,
            },
            {
                "name": "Value",
                "description": "Return on investment and bang for buck",
                "default_weight": 75,
            },
        ],
    },
    {
        "name": "Quality",
        "description": "Performance, effectiveness, durability, and excellence",
        "keywords": [
            "quality",
            "performance",
            "effective",
            "durable",
            "reliable",
            "excellent",
            "good",
            "better",
            "best",
            "superior",
            "efficient",
        ],
        "metrics": [
            {
                "name": "Quality",
                "description": "Overall quality and excellence",
                "default_weight": 85,
            },
            {
                "name": "Performance",
                "description": "How well it performs or delivers results",
                "default_weight": 80,
            },
        ],
    },
    {
        "name": "Time",
        "description": "Duration, speed, efficiency, and timeliness",
        "keywords": [
            "time",
            "speed",
            "fast",
            "slow",
            "duration",
            "quick",
            "efficient",
            "delay",
            "schedule",
            "hour",
            "minute",
            "deadline",
        ],
        "metrics": [
            {
                "name": "Time Required",
                "description": "Time fit, speed, and schedule compatibility",
                "default_weight": 70,
            },
            {
                "name": "Efficiency",
                "description": "Speed and productivity of the option",
                "default_weight": 65,
            },
        ],
    },
    {
        "name": "Risk",
        "description": "Safety, security, potential downsides, and reliability",
        "keywords": [
            "risk",
            "safe",
            "safety",
            "secure",
            "danger",
            "dangerous",
            "reliable",
            "reliability",
            "trust",
            "trustworthy",
            "guarantee",
            "warranty",
        ],
        "metrics": [
            {
                "name": "Risk",
                "description": "Low-risk fit and downside protection",
                "default_weight": 80,
            },
            {
                "name": "Safety",
                "description": "How safe and secure it is",
                "default_weight": 75,
            },
        ],
    },
    {
        "name": "Experience",
        "description": "Enjoyment, satisfaction, comfort, and personal fulfillment",
        "keywords": [
            "enjoy",
            "enjoyment",
            "fun",
            "happy",
            "satisfaction",
            "satisfy",
            "comfort",
            "comfortable",
            "fulfill",
            "fulfilling",
            "like",
            "love",
            "pleasure",
        ],
        "metrics": [
            {
                "name": "Enjoyment",
                "description": "How enjoyable and pleasant it is",
                "default_weight": 85,
            },
            {
                "name": "Satisfaction",
                "description": "Expected personal satisfaction",
                "default_weight": 80,
            },
        ],
    },
    {
        "name": "Convenience",
        "description": "Ease of use, accessibility, practicality, and maintenance",
        "keywords": [
            "convenient",
            "convenience",
            "easy",
            "accessible",
            "access",
            "practical",
            "simple",
            "maintenance",
            "effort",
            "hassle",
        ],
        "metrics": [
            {
                "name": "Convenience",
                "description": "Ease of use, access, and practicality",
                "default_weight": 70,
            },
            {
                "name": "Accessibility",
                "description": "How easy it is to obtain, reach, or maintain",
                "default_weight": 65,
            },
        ],
    },
]

# Flat list of all universal metrics for easy iteration
UNIVERSAL_METRICS = []
for dim in UNIVERSAL_DIMENSIONS:
    for m in dim["metrics"]:
        UNIVERSAL_METRICS.append(m)


def get_universal_criteria() -> tuple[str, list]:
    """Return the universal criteria set.

    Returns (dimension_name, metrics_list).
    Always returns the full universal set since all dimensions apply
    universally across any decision type.
    """
    return "General", UNIVERSAL_METRICS


def extract_alternatives(query: str) -> List[str]:
    """Extract alternatives from a decision query.

    Splits on " or ", " vs ", " versus ", " vs. " (case-insensitive),
    and cleans up each alternative.
    Returns empty list if no comparison markers are found.
    """
    match = re.search(
        r"(.+?)\s+(?:or|vs\.?|versus)\s+(.+)",
        query,
        re.IGNORECASE,
    )
    if not match:
        return []

    before = match.group(1).strip()
    after = match.group(2).strip()

    def clean(alt: str) -> str:
        alt = alt.strip().strip("?.,;:!")
        alt = re.sub(
            r"^(?:should\s+i|am\s+i|what\s+about|how\s+about|what\s+is|what\s+are|tell\s+me)\s+",
            "",
            alt,
            flags=re.IGNORECASE,
        )
        alt = re.sub(r"^(?:a|an|the)\s+", "", alt, flags=re.IGNORECASE)
        alt = alt.strip()
        if alt and alt[0].islower():
            alt = alt[0].upper() + alt[1:]
        return alt

    before_clean = before
    for prefix in [
        "should i",
        "am i",
        "do i",
        "would you",
        "should you",
        "i want to",
        "i need to",
        "i should",
        "i am",
    ]:
        before_clean = re.sub(
            r"^" + prefix, "", before_clean, flags=re.IGNORECASE
        ).strip()

    before_clean = re.sub(
        r"^(?:buy|get|choose|pick|select|take|go\s+for|opt\s+for|decide\s+between|compare|be|become|do|play|learn|use|try|have)\s+",
        "",
        before_clean,
        flags=re.IGNORECASE,
    ).strip()

    alt_parts = re.split(
        r"\s+(?:or|and|vs\.?|versus)\s+", before_clean, flags=re.IGNORECASE
    )
    alternatives = []
    for part in list(alt_parts) + [after]:
        cleaned = clean(part)
        if cleaned and len(cleaned) > 1:
            alternatives.append(cleaned)

    if len(alternatives) < 2:
        alts_combined = re.split(
            r"\s+(?:or|vs\.?|versus)\s+", query, flags=re.IGNORECASE
        )
        alternatives = [
            clean(a) for a in alts_combined if clean(a) and len(clean(a)) > 1
        ]

    return alternatives
