"""
main.py
-------
FastAPI backend. Single endpoint: POST /api/analyze
Accepts an image, returns JSON analysis + downloadable Excel and DXF.
"""

import base64
import os
import traceback
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from pipeline import run_pipeline          # ← changed: was gemini_client
from exporters import to_excel, to_dxf

load_dotenv()

app = FastAPI(title="Structural Section Analyzer")

origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_FILE_SIZE_MB = 10


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    """
    Upload a structural section image.
    Returns JSON with corners, line segments, and base64-encoded Excel + DXF files.
    """
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime}. Use PNG, JPEG, or WebP.",
        )

    image_bytes = await file.read()

    if len(image_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_FILE_SIZE_MB}MB.")

    # Run multi-agent pipeline                ← changed: was analyze_structural_drawing()
    try:
        analysis = await run_pipeline(image_bytes, mime_type=mime)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        print(f"[ERROR] pipeline failed:\n{traceback.format_exc()}")
        message = str(e) or "no error message — see server logs"
        raise HTTPException(status_code=500, detail=f"Analysis failed: {type(e).__name__}: {message}")

    # Generate exports — unchanged, same JSON contract
    excel_bytes = to_excel(analysis)
    dxf_bytes = to_dxf(analysis)

    return JSONResponse({
        "analysis": analysis,
        "exports": {
            "excel_b64": base64.b64encode(excel_bytes).decode(),
            "dxf_b64": base64.b64encode(dxf_bytes).decode(),
        },
    })