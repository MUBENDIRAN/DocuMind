"""
DocuMind - AI-Powered Document Analysis API

A FastAPI application that extracts text from PDFs, DOCX, and images,
then analyzes them using Google Gemini for summarization, entity extraction,
and sentiment analysis.
"""

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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel


# ============================================================================
# CONFIGURATION
# ============================================================================

load_dotenv()

# Environment variables
API_KEY: str = os.getenv("API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

# Validate required environment variables
if not API_KEY:
    raise RuntimeError("API_KEY is not found. Please set it in .env file")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not found. Please set it in .env file")

# Initialize Google Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Model configuration with fallback
PRIMARY_MODEL = "gemini-3.0-flash"
FALLBACK_MODEL = "gemini-2.5-flash"

# Initialize FastAPI application
app = FastAPI(
    title="DocuMind API",
    description="AI-Powered Document Analysis API"
)

# Mount static files for web UI
app.mount("/static", StaticFiles(directory="static", html=True), name="static")


# ============================================================================
# DATA MODELS
# ============================================================================


class DocumentRequest(BaseModel):
    """Request model for document analysis endpoint."""
    fileName: str
    fileType: str  # pdf | docx | image
    fileBase64: str


# File extension to type mapping
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


# ============================================================================
# AUTHENTICATION
# ============================================================================

def verify_api_key(x_api_key: str = Header(default=None)) -> None:
    """Verify API key from request header."""
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail={
                "status": "error",
                "message": "Unauthorized: Invalid or missing API key.",
            },
        )


def is_local_request(request: Request) -> bool:
    """Check if the request originates from localhost."""
    client_host = request.client.host if request.client else ""
    return client_host in ("127.0.0.1", "localhost", "::1")


# ============================================================================
# TEXT EXTRACTION
# ============================================================================

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF using PyMuPDF.
    Falls back to Tesseract OCR for scanned pages.
    
    Args:
        file_bytes: PDF file content as bytes
        
    Returns:
        Extracted text as string
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    all_text: list[str] = []

    for page in doc:
        page_text = page.get_text("text").strip()

        if page_text:
            all_text.append(page_text)
        else:
            # Scanned page - render and apply OCR
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            ocr_text = pytesseract.image_to_string(img, config="--psm 6").strip()
            if ocr_text:
                all_text.append(ocr_text)

    doc.close()
    return "\n\n".join(all_text)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract text from DOCX files using python-docx.
    Preserves reading order and includes table content.
    
    Args:
        file_bytes: DOCX file content as bytes
        
    Returns:
        Extracted text as string
    """
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    # Extract text from tables
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(
                cell.text.strip() for cell in row.cells if cell.text.strip()
            )
            if row_text:
                paragraphs.append(row_text)

    return "\n".join(paragraphs)


def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Extract text from images using Tesseract OCR.
    
    Args:
        file_bytes: Image file content as bytes
        
    Returns:
        Extracted text as string
    """
    img = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(img, config="--psm 6").strip()


# ============================================================================
# AI ANALYSIS WITH GOOGLE GEMINI
# ============================================================================

ANALYSIS_PROMPT = """
You are a document analysis engine. Respond ONLY with valid JSON — no markdown, backticks, or commentary.

Schema:
{{
  "summary": "<information-dense 2-3 sentence summary>",
  "entities": {{
    "names": ["<person names>"],
    "dates": ["<dates in Month YYYY or DD Month YYYY format>"],
    "organizations": ["<specific companies/institutions>"],
    "amounts": ["<monetary values with symbols>"]
  }},
  "sentiment": "<Positive | Negative | Neutral>"
}}

EXTRACTION RULES:

Summary Requirements (CRITICAL - generic summaries are considered INCORRECT):
- Include key actors (companies, institutions, people) if mentioned
- Include 2-3 specific details (technologies, applications, industries, metrics)
- Mention concrete use cases where applicable (e.g., "healthcare diagnostics", "supply chain optimization")
- Avoid generic phrases: "various industries", "many sectors", "significant growth" without detail
- Be concise but information-dense (3 - 4 sentences max)
- Prefer specific facts over broad statements
- QUALITY RULE: A weak/generic summary is incorrect even if factually true

Names: Extract full person names only (e.g., "John Smith", "Dr. Sarah Johnson"). Exclude job titles, pronouns.

Dates: Extract valid calendar dates (e.g., "June 2020", "15 March 2026"). Ignore vague terms ("Present", "Current", "Recent").

Organizations:
INCLUDE:
- Specific named entities: "Google Inc", "Harvard University", "FBI", "Reserve Bank of India"

DO NOT INCLUDE:
- Tech/tools: "Python", "Docker", "React", "TensorFlow", "ChatGPT"
- Broad/generic groups: "academic institutions", "government agencies", "healthcare professionals"
- Human roles/professions: "doctors", "engineers", "analysts"
- Vague terms: "industry", "sector", "market", "companies", "organizations"
- Low-value ambiguous groups

STRICT FILTER:
- Prefer specific named organizations over group terms
- If named organizations exist, avoid generic group entities
- Remove duplicates/overlaps (keep most specific)
- Resume/CV: Named companies/institutions ONLY
- Reports: Domain-specific groups allowed if meaningful
- When in doubt, EXCLUDE

Amounts: Extract monetary values with symbols (e.g., "₹10,000", "$500.50"). Ignore percentages.

Sentiment: 
- Factual docs (resume, report, invoice, contract, technical): "Neutral"
- Opinion-based (review, feedback, testimonial): "Positive" or "Negative"
- Default: "Neutral"

Defaults: Empty string for summary, empty arrays for entities, "Neutral" for sentiment if undetermined.

Document text:
---
{text}
---
"""

def validate_gemini_response(data: dict) -> dict:
    """
    Validate and sanitize Gemini API response.
    Ensures response matches expected schema with proper defaults.
    
    Args:
        data: Raw response dictionary from Gemini
        
    Returns:
        Validated and sanitized response dictionary
    """
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
    """
    Analyze document text using Google Gemini API.
    Implements automatic fallback from primary to secondary model on errors.
    
    Args:
        text: Document text to analyze (truncated to 12000 chars)
        
    Returns:
        Analysis results with summary, entities, and sentiment
        
    Raises:
        Exception: If all models fail to generate valid response
    """
    prompt = ANALYSIS_PROMPT.format(text=text[:12000])
    
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
            
            # Clean response: remove markdown code fences if present
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
            
            return validate_gemini_response(json.loads(raw))
            
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            
            # Check if error is rate limit related
            if any(keyword in error_str for keyword in ["rate", "resource", "quota", "429"]):
                continue  # Try fallback model
                
            # For other errors, also attempt fallback
            continue
    
    # All models failed - raise the last error
    raise last_error


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
def root():
    """Redirect root to web UI."""
    return RedirectResponse(url="/static/index.html")


@app.post("/api/document-analyze")
async def document_analyze(
    payload: DocumentRequest,
    x_api_key: str = Header(default=None),
):
    """
    Main API endpoint for document analysis.
    Accepts base64-encoded files and returns AI-powered analysis.
    
    Args:
        payload: DocumentRequest with fileName, fileType, and fileBase64
        x_api_key: API key for authentication (required)
        
    Returns:
        JSON response with summary, entities, and sentiment
        
    Raises:
        HTTPException: For authentication, validation, or processing errors
    """
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


@app.post("/api/upload-test")
async def upload_test(
    request: Request,
    file: UploadFile = File(...),
    x_api_key: str = Header(default=None),
):
    """
    Test endpoint for direct file upload.
    Accepts multipart/form-data files for easy testing.
    API key not required for localhost in development mode.
    
    Args:
        request: FastAPI request object
        file: Uploaded file
        x_api_key: API key (optional for localhost in dev mode)
        
    Returns:
        JSON response with analysis results
        
    Raises:
        HTTPException: For authentication, validation, or processing errors
    """
    # Check if running locally in development mode
    if ENVIRONMENT == "production" or not is_local_request(request):
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

    # Read file bytes
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