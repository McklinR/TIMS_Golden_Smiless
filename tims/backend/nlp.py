"""Structured WhatsApp tracking parsing helpers."""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

STATUS_KEYWORDS = {
    "OFFLOADED": ["offloaded", "off loading", "offloading", "delivered", "received at destination", "unloaded"],
    "BORDER QUEUE": ["border queue", "queue at border", "border", "customs", "clearing", "beitbridge", "chirundu"],
    "DELAYED": ["delayed", "delay", "held up", "traffic", "waiting", "stuck", "breakdown", "broken down", "puncture"],
    "EN ROUTE": ["en route", "on route", "on the road", "moving", "travelling", "left", "departed", "heading"],
}

KNOWN_LOCATIONS = [
    "Lalapanzi",
    "Mapanzure",
    "NETA",
    "Mberegwa",
    "Shurugwi",
    "Zvishavane",
    "Costco",
    "Grindrod",
    "Vayela",
    "Beitbridge",
    "Chirundu",
    "Masvingo",
    "Harare",
    "Bulawayo",
    "Musina",
    "Polokwane",
    "Gweru",
    "Mutare",
    "Rutenga",
    "Chiredzi",
    "Louis Trichardt",
]

_location_pattern = re.compile(
    r"\b(" + "|".join(re.escape(loc) for loc in sorted(KNOWN_LOCATIONS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_registration_patterns = [
    re.compile(r"\b([A-Z]{2,3}\s?\d{3,4}[A-Z]?)\b", re.IGNORECASE),
    re.compile(r"\b([A-Z]{1,3}-\d{3,4}[A-Z]?)\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class TrackingExtraction:
    horse_registration: str
    current_location: str
    trip_status: str
    parsed_notes: str


def normalize_registration(value: str) -> str:
    return re.sub(r"[\s\-]", "", value or "").upper()


def extract_horse_registration(text: str) -> str:
    if not text:
        return ""

    for pattern in _registration_patterns:
        match = pattern.search(text.upper())
        if match:
            return normalize_registration(match.group(1))

    fallback = re.search(r"\b([A-Z0-9]{4,12})\b", text.upper())
    return fallback.group(1) if fallback else ""


def extract_current_location(text: str) -> str:
    if not text:
        return "UNKNOWN"

    match = _location_pattern.search(text)
    if match:
        return match.group(1)

    preposition_match = re.search(r"\b(?:at|in|near|via|around|towards|to)\s+([A-Z][A-Za-z ]{2,40})", text)
    if preposition_match:
        return preposition_match.group(1).strip()

    return "UNKNOWN"


def extract_trip_status(text: str) -> str:
    lowered = (text or "").lower()
    for status, keywords in STATUS_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return status
    return "EN ROUTE"


def clean_parsed_notes(text: str) -> str:
    cleaned = re.sub(r"\+?\d[\d\s\-]{7,}\d", "[REDACTED_PHONE]", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_tracking_note(note: str) -> Tuple[Optional[str], Optional[str]]:
    """Backward-compatible parser for existing tracking log routes."""
    if not note:
        return None, None
    return extract_trip_status(note), extract_current_location(note)


def parse_whatsapp_tracking_text(raw_whatsapp_text: str) -> TrackingExtraction:
    horse_registration = extract_horse_registration(raw_whatsapp_text)
    current_location = extract_current_location(raw_whatsapp_text)
    trip_status = extract_trip_status(raw_whatsapp_text)
    parsed_notes = clean_parsed_notes(raw_whatsapp_text)
    return TrackingExtraction(
        horse_registration=horse_registration,
        current_location=current_location,
        trip_status=trip_status,
        parsed_notes=parsed_notes,
    )
