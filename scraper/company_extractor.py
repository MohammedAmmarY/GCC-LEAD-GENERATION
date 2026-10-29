"""
Turns messy, human-pasted text into a clean list of company names.

Why this file exists:
Real input is messy - blank lines, numbering like "1. Honeywell",
inconsistent capitalization, duplicate entries. This module handles all
of that in one place so the rest of the pipeline can assume it's getting
clean data.

This is deliberately built as its own module (not mixed into app.py or
the pipeline) so that later, extracting names from a webpage's HTML
instead of pasted text only requires changing this one file.
"""

import re


def clean_company_name(raw_name: str) -> str:
    """
    Clean up a single raw line of text into a company name.

    Examples of what this handles:
        "1. Honeywell"      -> "Honeywell"
        "  Caterpillar  "   -> "Caterpillar"
        "- Emerson"         -> "Emerson"
        "Rockwell Automation, Inc." -> "Rockwell Automation, Inc."
    """
    name = raw_name.strip()

    # Remove a leading list marker like "1.", "2)", "-", "*", "•"
    # The regex means: start of string, digits+period/parenthesis OR a
    # bullet character, then any spaces.
    name = re.sub(r"^\s*(\d+[\.\)]|[-*•])\s*", "", name)

    # Collapse multiple internal spaces into one (e.g. "GE   Vernova").
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def normalize_for_deduplication(name: str) -> str:
    """
    Produce a "normalized" version of a name used only for detecting
    duplicates - not for display. Lowercased, punctuation removed, so
    "GE Vernova" and "GE Vernova." are recognized as the same company.
    """
    normalized = name.lower()
    normalized = re.sub(r"[^\w\s]", "", normalized)  # strip punctuation
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def extract_companies_from_text(raw_text: str) -> list[str]:
    """
    Take a block of raw text (e.g. pasted from an email or webpage, one
    company per line) and return a clean, deduplicated list of company
    names, in the order they first appeared.

    Empty lines and lines that become empty after cleaning are skipped.
    """
    lines = raw_text.splitlines()

    cleaned_names: list[str] = []
    seen_normalized: set[str] = set()

    for line in lines:
        cleaned = clean_company_name(line)

        if not cleaned:
            continue  # skip blank lines

        normalized = normalize_for_deduplication(cleaned)

        if normalized in seen_normalized:
            continue  # skip duplicates we've already added

        seen_normalized.add(normalized)
        cleaned_names.append(cleaned)

    return cleaned_names
