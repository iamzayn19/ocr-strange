from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import repair_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean and validate messy OCR text.")
    parser.add_argument("file", type=Path, help="Text file containing OCR output")
    parser.add_argument(
        "--schema",
        default="",
        help="Comma-separated schema, e.g. invoice_number:string,date:date,total:money",
    )
    args = parser.parse_args()

    schema = _parse_schema(args.schema)
    result = repair_text(args.file.read_text(encoding="utf-8"), schema=schema)
    print(json.dumps({
        "data": result.data,
        "confidence": result.confidence,
        "review_reasons": result.review_reasons,
        "corrections": result.corrections,
        "cleaned_text": result.cleaned_text,
    }, indent=2, sort_keys=True))


def _parse_schema(value: str) -> dict[str, str]:
    if not value:
        return {}
    schema = {}
    for item in value.split(","):
        name, _, field_type = item.partition(":")
        if not name or not field_type:
            raise SystemExit(f"Invalid schema item: {item!r}")
        schema[name.strip()] = field_type.strip()
    return schema


if __name__ == "__main__":
    main()

