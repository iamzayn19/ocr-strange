from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re
from typing import Mapping


Schema = Mapping[str, str]


@dataclass(frozen=True)
class RepairResult:
    data: dict[str, str | None]
    confidence: dict[str, float]
    review_reasons: list[str]
    cleaned_text: str
    corrections: list[str] = field(default_factory=list)


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "invoice_number": ("invoice no", "invoice number", "invoice #", "inv no", "inv #", "invoice"),
    "date": ("date", "invoice date", "issued", "issue date"),
    "total": ("total", "amount due", "balance due", "grand total"),
    "email": ("email", "e-mail", "mail"),
    "phone": ("phone", "tel", "telephone", "mobile"),
}

GLOBAL_REPLACEMENTS = (
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u2013", "-"),
    ("\u2014", "-"),
    ("|", "I"),
    ("`", "'"),
)


def clean_text(text: str) -> str:
    cleaned = text
    for old, new in GLOBAL_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.splitlines())
    return cleaned.strip()


def repair_text(text: str, schema: Schema | None = None) -> RepairResult:
    cleaned = clean_text(text)
    corrections: list[str] = []
    repaired = _repair_common_words(cleaned, corrections)
    schema = schema or {}

    data: dict[str, str | None] = {}
    confidence: dict[str, float] = {}
    review_reasons: list[str] = []

    for field_name, field_type in schema.items():
        raw = _extract_field(repaired, field_name)
        normalized, score, reasons = _normalize_field(raw, field_type, field_name)
        data[field_name] = normalized
        confidence[field_name] = score
        review_reasons.extend(reasons)

    return RepairResult(
        data=data,
        confidence=confidence,
        review_reasons=_unique(review_reasons + _review_reasons_from_corrections(corrections)),
        cleaned_text=repaired,
        corrections=_unique(corrections),
    )


def _repair_common_words(text: str, corrections: list[str]) -> str:
    replacements = {
        r"\blNV0lCE\b": "INVOICE",
        r"\blNV0ICE\b": "INVOICE",
        r"\blNVOICE\b": "INVOICE",
        r"\bN0\b": "NO",
        r"\blssue\b": "Issue",
        r"\bDAT E\b": "Date",
        r"\bTotaI\b": "Total",
        r"\bSubtotaI\b": "Subtotal",
        r"\bArnount\b": "Amount",
        r"\bPayrnent\b": "Payment",
        r"\bEmaii\b": "Email",
        r"\bcorn\b": "com",
    }
    repaired = text
    for pattern, replacement in replacements.items():
        updated = re.sub(pattern, replacement, repaired, flags=re.IGNORECASE)
        if updated != repaired:
            corrections.append(f"corrected likely OCR word confusion: {pattern} -> {replacement}")
        repaired = updated
    return repaired


def _extract_field(text: str, field_name: str) -> str | None:
    labels = FIELD_ALIASES.get(field_name, ())
    labels = labels + (_humanize(field_name), field_name.replace("_", " "))
    for label in labels:
        pattern = re.compile(
            rf"(?im)^\s*{re.escape(label)}\s*(?:[:#-]|\b)\s*(?P<value>.+?)\s*$"
        )
        match = pattern.search(text)
        if match:
            return match.group("value").strip()

    if field_name == "email":
        match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        return match.group(0) if match else None
    if field_name == "phone":
        match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
        return match.group(0) if match else None
    return None


def _normalize_field(value: str | None, field_type: str, field_name: str) -> tuple[str | None, float, list[str]]:
    if not value:
        return None, 0.0, [f"{field_name} was not found"]

    field_type = field_type.lower()
    if field_type == "money":
        return _normalize_money(value, field_name)
    if field_type == "date":
        return _normalize_date(value, field_name)
    if field_type == "email":
        return _normalize_email(value, field_name)
    if field_type == "phone":
        return _normalize_phone(value, field_name)
    if field_type == "number":
        return _normalize_number(value, field_name)
    return _normalize_string(value)


def _normalize_money(value: str, field_name: str) -> tuple[str | None, float, list[str]]:
    repaired = _digitish(value)
    repaired = repaired.replace("$", "").replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d{1,2})?", repaired)
    if not match:
        return None, 0.2, [f"{field_name} did not look like money"]
    amount = match.group(0)
    if "." not in amount:
        amount = f"{amount}.00"
    return f"{float(amount):.2f}", 0.88 if repaired != value else 0.96, []


def _normalize_number(value: str, field_name: str) -> tuple[str | None, float, list[str]]:
    repaired = _digitish(value)
    match = re.search(r"-?\d+(?:\.\d+)?", repaired)
    if not match:
        return None, 0.2, [f"{field_name} did not look like a number"]
    return match.group(0), 0.88 if repaired != value else 0.96, []


def _normalize_date(value: str, field_name: str) -> tuple[str | None, float, list[str]]:
    repaired = _digitish(value)
    match = re.search(r"(\d{1,4})[./-](\d{1,2})[./-](\d{2,4})", repaired)
    if not match:
        return None, 0.25, [f"{field_name} did not look like a date"]

    first, second, third = match.groups()
    year = int(third)
    if year < 100:
        year += 2000
    a = int(first)
    b = int(second)
    if len(first) == 4:
        year, month, day = int(first), b, int(third)
    elif a > 12:
        day, month = a, b
    else:
        month, day = a, b
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None, 0.3, [f"{field_name} had an invalid date value"]
    return parsed.isoformat(), 0.82 if repaired != value else 0.94, []


def _normalize_email(value: str, field_name: str) -> tuple[str | None, float, list[str]]:
    repaired = value.strip().replace(" ", "")
    repaired = re.sub(r"\.corn\b", ".com", repaired, flags=re.IGNORECASE)
    if "@" in repaired:
        local, domain = repaired.split("@", 1)
        domain = domain.replace("I", "l").replace("1", "l").replace("0", "o")
        repaired = f"{local}@{domain}"
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", repaired)
    if not match:
        return None, 0.2, [f"{field_name} did not look like an email"]
    email = match.group(0)
    return email, 0.86 if email != value.strip() else 0.96, []


def _normalize_phone(value: str, field_name: str) -> tuple[str | None, float, list[str]]:
    digits = re.sub(r"\D", "", _digitish(value))
    if len(digits) < 8:
        return None, 0.2, [f"{field_name} did not look like a phone number"]
    return digits, 0.9, []


def _normalize_string(value: str) -> tuple[str, float, list[str]]:
    repaired = value.strip()
    repaired = _repair_identifier(repaired)
    return repaired, 0.88 if repaired != value.strip() else 0.95, []


def _digitish(value: str) -> str:
    table = str.maketrans({
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
    })
    repaired = value.translate(table)
    repaired = re.sub(r"(?<=\d)S(?=[\d.])", "5", repaired)
    repaired = re.sub(r"(?<=[(\s])S(?=\d)", "5", repaired)
    repaired = re.sub(r"(?<=\d)B(?=[\d.])", "8", repaired)
    repaired = re.sub(r"(?<=[(\s])B(?=\d)", "8", repaired)
    return repaired


def _repair_identifier(value: str) -> str:
    repaired = value
    repaired = re.sub(r"\bl(?=[A-Z]{2})", "I", repaired)
    repaired = re.sub(r"(?<=\d)O(?=\d)", "0", repaired)
    repaired = re.sub(r"(?<=\d)I(?=\d)", "1", repaired)
    repaired = re.sub(r"(?<=[A-Z])-?I(?=\d)", "-1", repaired)
    return repaired


def _review_reasons_from_corrections(corrections: list[str]) -> list[str]:
    if not corrections:
        return []
    return ["common OCR confusions were corrected; review important fields if this document is high-risk"]


def _humanize(name: str) -> str:
    return name.replace("_", " ")


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
