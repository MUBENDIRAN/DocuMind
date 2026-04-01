# AI-Powered Document Analysis API

## Description

An intelligent document processing API that extracts, analyses, and summarises content from PDFs, DOCX files, and images. It uses Tesseract OCR for text extraction and Google Gemini (via Google AI Studio free API) for AI-powered summarisation, named entity extraction, and sentiment analysis.

## Tech Stack

- **Framework:** FastAPI + Uvicorn
- **PDF Extraction:** PyMuPDF (fitz) — native text with OCR fallback
- **DOCX Extraction:** python-docx
- **OCR:** Tesseract via pytesseract + Pillow
- **AI Model:** Google Gemini 3.0 Flash (fallback: Gemini 2.5 Flash) via google-genai
- **Auth:** API key via x-api-key header
- **Frontend:** HTML/CSS/JS with drag-and-drop file upload

## Features

✅ Web UI with drag-and-drop upload  
✅ API endpoint for programmatic access  
✅ Gemini 3.0 Flash with automatic fallback to 2.5 Flash on rate limits  
✅ JSON response validation  
✅ Local testing without API key  

## AI Tools Used

This project was developed with assistance from:
- **GitHub Copilot** - AI-powered development assistant
  - Claude Opus 4.5 (for complex architecture and design decisions)
  - Claude Sonnet 4.5 (for implementation and optimization)


## Setup Instructions

### 1. Clone the repository
```bash
git clone <your-repo-url>
cd guvi-hack
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Tesseract OCR (system dependency)
```bash
# Ubuntu / Debian
sudo apt install tesseract-ocr

# macOS
brew install tesseract

# Windows — download installer from:
https://github.com/UB-Mannheim/tesseract/wiki
```

### 4. Set environment variables
```bash
cp .env.example .env
# Edit .env and set:
# - API_KEY=your_secret_key_for_api_access
# - GEMINI_API_KEY=your_gemini_api_key
# - ENVIRONMENT=development (for local) or production (for deploy)
```

### 5. Run the application
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open: http://localhost:8000

## How Authentication Works

### 🏠 Local Testing (ENVIRONMENT=development)
- **Web UI** (`/`): Works without API key ✅
- **Upload endpoint** (`/api/upload-test`): No API key needed ✅
- **API endpoint** (`/api/document-analyze`): Requires API key ✅

### 🚀 Production (ENVIRONMENT=production)
- **Web UI** (`/`): Requires API key in input field ✅
- **Upload endpoint** (`/api/upload-test`): Requires API key in header ✅
- **API endpoint** (`/api/document-analyze`): Requires API key in header ✅

## Deployment

### Environment Variables to Set:
```
API_KEY=your_secret_api_key_here
GEMINI_API_KEY=your_gemini_api_key_from_ai_studio
ENVIRONMENT=production
```

### Build Command:
```bash
pip install -r requirements.txt
```

### Start Command:
```bash
uvicorn src.main:app --host 0.0.0.0 --port $PORT
```

**Note:** Most platforms automatically set the `$PORT` environment variable.

## API Usage

### Endpoint 1: Web Upload (for testing)
```
POST /api/upload-test
```

**Headers:**
```
x-api-key: <your API_KEY> (required in production)
```

**Body:** multipart/form-data with `file` field

**Example cURL:**
```bash
curl -X POST https://your-app.example.com/api/upload-test \
  -H "x-api-key: your_api_key" \
  -F "file=@document.pdf"
```

### Endpoint 2: Base64 JSON 
```
POST /api/document-analyze
```

**Headers:**
```
Content-Type: application/json
x-api-key: <your API_KEY>
```

**Request Body:**
```json
{
  "fileName": "sample1.pdf",
  "fileType": "pdf",
  "fileBase64": "<base64 encoded file content>"
}
```

**Supported fileType values:** `pdf`, `docx`, `image`

**Example cURL:**
```bash
curl -X POST https://your-app.example.com/api/document-analyze \
  -H "Content-Type: application/json" \
  -H "x-api-key: your_api_key" \
  -d '{
    "fileName": "invoice.pdf",
    "fileType": "pdf",
    "fileBase64": "<base64string>"
  }'
```

### Success Response
```json
{
  "status": "success",
  "fileName": "sample1.pdf",
  "summary": "This document is an invoice issued by ABC Pvt Ltd to Ravi Kumar on 10 March 2026 for an amount of ₹10,000.",
  "entities": {
    "names": ["Ravi Kumar"],
    "dates": ["March 2026"],
    "organizations": ["ABC Pvt Ltd"],
    "amounts": ["₹10,000"]
  },
  "sentiment": "Neutral"
}
```

### Error Responses
| Status | Reason |
|--------|--------|
| 401 | Missing or invalid x-api-key |
| 400 | Unsupported fileType or bad base64 |
| 422 | No text could be extracted |
| 502 | Gemini AI analysis failed |

## Approach

### Text Extraction Strategy
- **PDF:** PyMuPDF extracts native text preserving reading order. If a page has no extractable text (scanned PDF), the page is rendered at 300 DPI and passed through Tesseract OCR.
- **DOCX:** python-docx reads paragraphs in order and also pulls text from embedded tables.
- **Image:** Tesseract with `--psm 6` (assume uniform block of text) for best layout preservation.

### AI Analysis Strategy
A single Gemini call handles all three tasks simultaneously to minimise latency and API quota usage. The system uses:
- **Primary Model:** Gemini 3.0 Flash (fast, efficient)
- **Fallback Model:** Gemini 2.5 Flash (activates on rate limits or errors)

The prompt strictly instructs the model to return only a JSON object with summary, entities (names, dates, organizations, amounts), and sentiment. Response validation ensures the JSON always matches the expected schema.


## 👨‍💻 Author

**Mubendiran K**  
Rajalakshmi Institute of Technology, Chennai  
Built as part of **GUVI Hackathon 2026** submission