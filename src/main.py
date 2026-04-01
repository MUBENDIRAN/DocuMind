import base64
import io
import json
import os
import re

import fitz  # PyMuPDF
import pytesseract
from docx import Document
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()

API_KEY: str = os.getenv("API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # "production" or "development"

if not API_KEY:
    raise RuntimeError("API_KEY is not Found")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not Found")

# Initialize the new genai client
client = genai.Client(api_key=GEMINI_API_KEY)

# Model names for fallback (primary: gemini-3.0-flash, fallback: gemini-2.5-flash)
PRIMARY_MODEL = "gemini-3.0-flash"
FALLBACK_MODEL = "gemini-2.5-flash"

app = FastAPI(title="AI Document Analysis API", version="1.0.0")

# Mount static files for frontend
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------
class DocumentRequest(BaseModel):
    fileName: str
    fileType: str          # pdf | docx | image
    fileBase64: str

# ---------------------------------------------------------------------------
# Auth dependency (inline — keeps single-file structure)
# ---------------------------------------------------------------------------
def verify_api_key(x_api_key: str = Header(default=None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "message": "Unauthorized: Invalid or missing API key.",
            },
        )

# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """PyMuPDF native extraction; falls back to Tesseract OCR for scanned pages."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    all_text: list[str] = []

    for page in doc:
        page_text = page.get_text("text").strip()

        if page_text:
            all_text.append(page_text)
        else:
            # Scanned page — render and OCR
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text = pytesseract.image_to_string(img, config="--psm 6").strip()
            if ocr_text:
                all_text.append(ocr_text)

    doc.close()
    return "\n\n".join(all_text)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """python-docx paragraph extraction preserving reading order."""
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    # Also pull text from tables
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(
                cell.text.strip() for cell in row.cells if cell.text.strip()
            )
            if row_text:
                paragraphs.append(row_text)

    return "\n".join(paragraphs)


def extract_text_from_image(file_bytes: bytes) -> str:
    """Tesseract OCR on image bytes."""
    img = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(img, config="--psm 6").strip()


# ---------------------------------------------------------------------------
# Gemini analysis
# ---------------------------------------------------------------------------
ANALYSIS_PROMPT = """
You are a professional document analysis engine. Analyse the document text below and respond ONLY with a valid JSON object — no markdown, no backticks, no extra commentary.

The JSON must follow this exact schema:
{{
  "summary": "<concise 1-3 sentence summary of the document>",
  "entities": {{
    "names": ["<full person names found>"],
    "dates": ["<all dates found in any format>"],
    "organizations": ["<company, institution, or organisation names>"],
    "amounts": ["<monetary values with currency symbols>"]
  }},
  "sentiment": "<Positive | Negative | Neutral>"
}}

Rules:
- Extract ALL entities of each type present in the text.
- Do NOT return empty lists unless absolutely no entities exist in that category.
- Summary must accurately reflect the document's purpose and key facts.
- Do NOT include any text outside the JSON object.

Entity Extraction Rules:
- Names: Full person names, authors, signatories.
- Dates: Valid calendar dates only (see Date Rules below).
- Organizations: Extract only real organizations such as:
  - Companies (e.g., "ABC Pvt Ltd", "Google", "Microsoft")
  - Institutions (e.g., "Harvard University", "Red Cross", "World Bank")
  - Government bodies (e.g., "Ministry of Finance", "FBI", "Department of Education")
  
  Do NOT include:
  - Industries (e.g., "healthcare", "finance", "banking")
  - Sectors (e.g., "technology sector", "public sector")
  - Generic categories (e.g., "companies", "organizations", "financial institutions")
  
  Extract meaningful and distinct organizations. Avoid:
  - Duplicates
  - Overly generic terms like "organizations" or "industry"
  
  Prefer specific groups or entities actually mentioned in the document.

- Amounts: Monetary values with currency symbols (e.g., "₹10,000", "$500", "€1,200").

Sentiment Rules:
- If the document is factual (resume, CV, report, invoice, receipt, contract, form), return sentiment as "Neutral".
- Only return "Positive" or "Negative" for opinion-based content (reviews, feedback, letters with emotional tone).

Date Rules:
- Only extract valid calendar dates (e.g., "June 2020", "2017-03-15", "March 2017").
- Ignore vague terms like "Present", "Current", "Ongoing", "To Date".
- Return dates in a consistent format: "Month YYYY" or "YYYY-MM-DD".

Document text:
---
{text}
---
"""

def validate_gemini_response(data: dict) -> dict:
    """Validate and sanitize Gemini response to match expected schema."""
    # Ensure top-level keys exist with defaults
    validated = {
        "summary": "",
        "entities": {
            "names": [],
            "dates": [],
            "organizations": [],
            "amounts": [],
        },
        "sentiment": "Neutral",
    }
    
    # Extract summary
    if isinstance(data.get("summary"), str):
        validated["summary"] = data["summary"].strip()
    
    # Extract entities
    entities = data.get("entities", {})
    if isinstance(entities, dict):
        for key in ["names", "dates", "organizations", "amounts"]:
            if isinstance(entities.get(key), list):
                # Filter to only strings
                validated["entities"][key] = [
                    str(item).strip() for item in entities[key] 
                    if item and isinstance(item, (str, int, float))
                ]
    
    # Extract sentiment (must be one of the allowed values)
    sentiment = data.get("sentiment", "")
    if isinstance(sentiment, str) and sentiment.strip() in ("Positive", "Negative", "Neutral"):
        validated["sentiment"] = sentiment.strip()
    else:
        validated["sentiment"] = "Neutral"  # default fallback
    
    return validated


def analyse_with_gemini(text: str) -> dict:
    """Analyze text with Gemini. Falls back from gemini-3.0-flash to gemini-2.5-flash on errors."""
    prompt = ANALYSIS_PROMPT.format(text=text[:12000])  # stay within token limits
    
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error = None
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                ),
            )
            raw = response.text.strip()
            
            # Strip accidental markdown fences if model adds them
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            
            return validate_gemini_response(json.loads(raw))
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # If rate limited or resource exhausted, try fallback
            if "rate" in error_str or "resource" in error_str or "quota" in error_str or "429" in error_str:
                continue
            # For other errors, also try fallback
            continue
    
    # All models failed
    raise last_error


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------
@app.post("/api/document-analyze")
async def document_analyze(
    payload: DocumentRequest,
    x_api_key: str = Header(default=None),
):
    # Auth
    verify_api_key(x_api_key)

    # Validate fileType
    file_type = payload.fileType.lower().strip()
    supported = {"pdf", "docx", "image"}
    if file_type not in supported:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": f"Unsupported fileType '{payload.fileType}'. Use: pdf, docx, image.",
            },
        )

    # Decode base64
    try:
        file_bytes = base64.b64decode(payload.fileBase64)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"status": "error", "message": "Invalid base64 encoding in fileBase64."},
        )

    # Extract text
    try:
        if file_type == "pdf":
            text = extract_text_from_pdf(file_bytes)
        elif file_type == "docx":
            text = extract_text_from_docx(file_bytes)
        else:
            text = extract_text_from_image(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": f"Text extraction failed: {str(e)}"},
        )

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "No readable text could be extracted from the document."},
        )

    # Gemini analysis
    try:
        analysis = analyse_with_gemini(text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "AI returned malformed response. Please retry."},
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": f"AI analysis failed: {str(e)}"},
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "fileName": payload.fileName,
            "summary": analysis.get("summary", ""),
            "entities": {
                "names": analysis.get("entities", {}).get("names", []),
                "dates": analysis.get("entities", {}).get("dates", []),
                "organizations": analysis.get("entities", {}).get("organizations", []),
                "amounts": analysis.get("entities", {}).get("amounts", []),
            },
            "sentiment": analysis.get("sentiment", "Neutral"),
        },
    )


# ---------------------------------------------------------------------------
# Health check & Home page
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


# ---------------------------------------------------------------------------
# Test endpoint — direct file upload for testing
# For programmatic access, use /api/document-analyze with base64 JSON body
# ---------------------------------------------------------------------------
EXTENSION_TO_TYPE = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".webp": "image",
}


def is_local_request(request: Request) -> bool:
    """Check if request is from localhost."""
    client_host = request.client.host if request.client else ""
    return client_host in ("127.0.0.1", "localhost", "::1")


@app.post("/api/upload-test")
async def upload_test(
    request: Request,
    file: UploadFile = File(...),
    x_api_key: str = Header(default=None),
):
    # Check if running locally - if so, skip API key check
    if ENVIRONMENT != "production" and is_local_request(request):
        # Local testing - no API key needed
        pass
    else:
        # Production or remote access - verify API key
        verify_api_key(x_api_key)

    # Detect file type from extension
    filename = file.filename or ""
    ext = os.path.splitext(filename)[-1].lower()
    file_type = EXTENSION_TO_TYPE.get(ext)

    if not file_type:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": f"Unsupported file extension '{ext}'. Supported: pdf, docx, png, jpg, jpeg, tiff, bmp, webp.",
            },
        )

    # Read file bytes directly — no base64 needed
    file_bytes = await file.read()

    # Extract text
    try:
        if file_type == "pdf":
            text = extract_text_from_pdf(file_bytes)
        elif file_type == "docx":
            text = extract_text_from_docx(file_bytes)
        else:
            text = extract_text_from_image(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": f"Text extraction failed: {str(e)}"},
        )

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail={"status": "error", "message": "No readable text could be extracted from the document."},
        )

    # Gemini analysis
    try:
        analysis = analyse_with_gemini(text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": "AI returned malformed response. Please retry."},
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"status": "error", "message": f"AI analysis failed: {str(e)}"},
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "fileName": filename,
            "summary": analysis.get("summary", ""),
            "entities": {
                "names": analysis.get("entities", {}).get("names", []),
                "dates": analysis.get("entities", {}).get("dates", []),
                "organizations": analysis.get("entities", {}).get("organizations", []),
                "amounts": analysis.get("entities", {}).get("amounts", []),
            },
            "sentiment": analysis.get("sentiment", "Neutral"),
        },
    )