# OCR Strange

OCR Strange cleans messy OCR output and turns it into validated JSON.

It does not call paid OCR APIs. It works on OCR text you already have from tools like Tesseract, PDF extraction, scanner software, or cloud OCR exports.

## Install

```bash
pip install ocr-strange
```

## Quick Start

```python
from ocr_strange import repair_text

result = repair_text(
    """
    INVOICE N0: INV-I042
    Date: 3O/O9/2O26
    TotaI: $I,29O.OO
    Email: billing@example.corn
    """,
    schema={
        "invoice_number": "string",
        "date": "date",
        "total": "money",
        "email": "email",
    },
)

print(result.data)
print(result.review_reasons)
```

## What It Does

- normalizes noisy OCR text
- repairs common OCR confusions
- extracts schema fields from labels and nearby text
- validates dates, money, email, phone, and generic strings
- produces field-level confidence
- explains why a field may need human review
- outputs JSON from the command line

## CLI

```bash
ocr-strange invoice.txt --schema invoice_number:string,date:date,total:money
```

## Python API

```python
from ocr_strange import clean_text, repair_text

cleaned = clean_text(raw_ocr_text)
result = repair_text(raw_ocr_text, schema={"total": "money"})

result.data
result.confidence
result.review_reasons
result.cleaned_text
```

## Supported Field Types

- `string`
- `date`
- `money`
- `email`
- `phone`
- `number`

## Why

OCR engines read text. Production apps need trustworthy fields.

OCR Strange is the post-processing layer: clean the text, extract what matters, validate it, and tell the app when a human should review the result.

