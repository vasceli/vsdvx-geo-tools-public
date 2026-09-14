from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import sys
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.parsers.maps_parser import parse_yandex_maps_url
from backend.parsers.requisites_parser import parse_requisites_file
from backend.services.calculator import calculate_services, load_tariffs
from backend.services.contract_builder import build_docx, build_preview_html, contract_filename, normalize_payload, validate_payload
from backend.services.pdf_builder import build_pdf

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
FRONTEND = ROOT / "frontend"

app = FastAPI(title="Contract Generator", version="0.1.0")
cors_origins = [
    origin.strip()
    for origin in os.getenv("CONTRACTS_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=bool(cors_origins),
    allow_methods=["*"],
    allow_headers=["Content-Type"],
)
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


class CalculateRequest(BaseModel):
    months: int
    total_price: int
    reputation_total: int | None = None
    include_reputation: bool = True


class MapRequest(BaseModel):
    url: str


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/plans")
def plans() -> dict[str, Any]:
    return load_tariffs()["plans"]


@app.post("/api/calculate")
def calculate(req: CalculateRequest) -> dict[str, Any]:
    try:
        return calculate_services(req.months, req.total_price, req.reputation_total, req.include_reputation)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/parse-requisites")
async def parse_requisites(file: UploadFile = File(...)) -> dict[str, Any]:
    try:
        content = await file.read()
        return parse_requisites_file(file.filename or "upload", content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось распарсить реквизиты: {exc}") from exc


@app.post("/api/parse-map")
def parse_map(req: MapRequest) -> dict[str, Any]:
    return parse_yandex_maps_url(req.url)


@app.post("/api/preview", response_class=HTMLResponse)
async def preview(data: dict[str, Any]) -> HTMLResponse:
    try:
        return HTMLResponse(build_preview_html(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/validate")
def validate(data: dict[str, Any]) -> dict[str, Any]:
    try:
        normalized = normalize_payload(data)
        return {"ok": True, "warnings": validate_payload(normalized), "normalized": normalized}
    except Exception as exc:
        return {"ok": False, "warnings": [str(exc)], "normalized": data}


@app.post("/api/generate-docx")
def generate_docx(data: dict[str, Any]) -> StreamingResponse:
    try:
        normalized = normalize_payload(data)
        content = build_docx(normalized)
        filename = contract_filename(normalized, "docx")
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8\'\'{quote(filename)}"}
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/generate-pdf")
def generate_pdf(data: dict[str, Any]) -> StreamingResponse:
    try:
        normalized = normalize_payload(data)
        # LibreOffice gives the closest visual match to DOCX when it is installed.
        # On a clean computer the built-in ReportLab renderer is used instead.
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        pdf_content: bytes
        if soffice:
            docx_content = build_docx(normalized)
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                docx_path = tmp / "contract.docx"
                docx_path.write_bytes(docx_content)
                subprocess.run(
                    [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmp), str(docx_path)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=90,
                )
                pdf_path = tmp / "contract.pdf"
                if not pdf_path.exists() or pdf_path.stat().st_size == 0:
                    raise RuntimeError("LibreOffice не создал PDF")
                pdf_content = pdf_path.read_bytes()
        else:
            pdf_content = build_pdf(normalized)
        filename = contract_filename(normalized, "pdf")
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8\'\'{quote(filename)}"}
        return StreamingResponse(BytesIO(pdf_content), media_type="application/pdf", headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
