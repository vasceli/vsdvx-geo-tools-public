from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.services.contract_builder import build_docx, build_preview_html, normalize_payload, validate_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate contract DOCX/HTML from JSON payload")
    parser.add_argument("input_json", help="Path to JSON data")
    parser.add_argument("--docx", default="output/contract.docx", help="Output DOCX path")
    parser.add_argument("--html", default="output/preview.html", help="Output HTML preview path")
    args = parser.parse_args()

    data = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    normalized = normalize_payload(data)
    warnings = validate_payload(normalized)

    docx_path = Path(args.docx)
    html_path = Path(args.html)
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)

    docx_path.write_bytes(build_docx(normalized))
    html_path.write_text(build_preview_html(normalized), encoding="utf-8")

    print(f"DOCX: {docx_path}")
    print(f"HTML: {html_path}")
    if warnings:
        print("WARNINGS:")
        for warning in warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
