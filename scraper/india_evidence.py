"""
Finds India-related passages in crawled website pages using plain
keyword matching - no LLM involved.

Why this file exists:
The LLM's summary of India evidence is its own paraphrase, and you can't
easily check it. This module finds the actual sentences on the actual
pages that mention India or an Indian city, and remembers which page each
one came from. Those passages are FACTS (the site really says this); the
LLM's analysis built on top of them is interpretation.
"""

import re

MAX_SNIPPETS = 12
MAX_SNIPPET_CHARS = 300

INDIA_LOCATIONS = [
    "India", "Bengaluru", "Bangalore", "Hyderabad", "Pune", "Chennai",
    "Gurgaon", "Gurugram", "Noida", "Mumbai", "Navi Mumbai", "New Delhi",
    "Delhi", "Kolkata", "Ahmedabad", "Coimbatore", "Kochi", "Jaipur",
    "Chandigarh", "Indore", "Nagpur", "Vadodara", "Mysuru", "Mysore",
    "Thiruvananthapuram", "Trivandrum", "Visakhapatnam",
]

# Longest names first, so "New Delhi" is matched as a whole before "Delhi".
_location_alternatives = "|".join(
    re.escape(name) for name in sorted(INDIA_LOCATIONS, key=len, reverse=True)
)
LOCATION_PATTERN = re.compile(rf"\b(?:{_location_alternatives})\b", re.IGNORECASE)

# Wording that suggests a capability/engineering center rather than just
# a sales office, e.g. "engineering center", "global capability centre".
CENTER_PATTERN = re.compile(
    r"\b(?:global capability|capability|technology|engineering|development|"
    r"innovation|research|r&d|design|delivery|shared[- ]services?|competence|"
    r"excellence)\s+(?:cent(?:er|re)|hub)s?\b|\bGCCs?\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Country names, used to recognise "choose your country" menus, which
# list India next to dozens of other countries and prove nothing.
COUNTRY_WORDS = {
    "argentina", "australia", "austria", "belgium", "brazil", "canada",
    "chile", "china", "colombia", "czech", "denmark", "egypt", "finland",
    "france", "germany", "greece", "hungary", "indonesia", "ireland",
    "israel", "italy", "japan", "korea", "malaysia", "mexico",
    "netherlands", "norway", "peru", "philippines", "poland", "portugal",
    "romania", "singapore", "spain", "sweden", "switzerland", "taiwan",
    "thailand", "turkey", "ukraine", "united", "states", "kingdom",
    "emirates", "vietnam",
}


def _trim_around(sentence: str, match_start: int, limit: int) -> str:
    """Shorten a very long sentence to a window around the match."""
    sentence = sentence.strip()
    if len(sentence) <= limit:
        return sentence
    start = max(0, match_start - limit // 2)
    end = min(len(sentence), start + limit)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(sentence) else ""
    return f"{prefix}{sentence[start:end].strip()}{suffix}"


def _looks_like_country_menu(snippet: str) -> bool:
    """
    True for text like "Argentina Australia Austria Brazil Canada India
    Japan": mostly country names with no commas. A real sentence such as
    "Our offices are in Germany, France, Poland, Mexico and India" has
    commas, so it is kept.
    """
    words = re.findall(r"[a-z]+", snippet.lower())
    if not words:
        return False
    country_hits = sum(1 for word in words if word in COUNTRY_WORDS)
    return (
        country_hits >= 4
        and country_hits / len(words) >= 0.5
        and snippet.count(",") < 2
    )


def find_india_evidence(pages: list[dict], max_snippets: int = MAX_SNIPPETS) -> list[dict]:
    """
    Scan crawled pages (each {"url": ..., "text": ...}) for sentences that
    mention India or an Indian city. Returns up to max_snippets items:

        {"page": url, "text": the sentence, "locations": ["Pune"],
         "center_terms": ["engineering center"]}

    Passages that also use center-type wording come first.
    """
    evidence: list[dict] = []
    seen: set[str] = set()

    for page in pages:
        for sentence in SENTENCE_SPLIT.split(page["text"]):
            match = LOCATION_PATTERN.search(sentence)
            if not match:
                continue

            snippet = _trim_around(sentence, match.start(), MAX_SNIPPET_CHARS)
            if _looks_like_country_menu(snippet):
                continue

            key = snippet.lower()
            if key in seen:
                continue
            seen.add(key)

            evidence.append(
                {
                    "page": page["url"],
                    "text": snippet,
                    "locations": sorted({m.group(0).title() for m in LOCATION_PATTERN.finditer(snippet)}),
                    "center_terms": sorted({m.group(0).lower() for m in CENTER_PATTERN.finditer(snippet)}),
                }
            )

    evidence.sort(key=lambda item: 0 if item["center_terms"] else 1)  # stable sort
    return evidence[:max_snippets]


def format_evidence_for_prompt(evidence: list[dict]) -> str:
    """Turn the scan results into a text block placed before the page text for the LLM."""
    if not evidence:
        return "KEYWORD SCAN: no India-related passages were found on the crawled pages."

    lines = [
        "KEYWORD SCAN (found by a program, not by the AI) - "
        "India-related passages with their source pages:"
    ]
    for number, item in enumerate(evidence, start=1):
        lines.append(f"[{number}] ({item['page']}) {item['text']}")
    return "\n".join(lines)