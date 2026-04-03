# DocuMind - AI-Powered Document Analysis API

<div align="center">
  <img src="./static/DocuMind(logo).jpeg" alt="DocuMind Logo" width="120"/>
  <p><em>Intelligent document processing with AI-powered analysis</em></p>
</div>

## 📝 Description

An intelligent document processing API that extracts, analyzes, and summarizes content from PDFs, DOCX files, and images using Tesseract OCR and Google Gemini AI.

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | FastAPI + Uvicorn |
| **PDF Extraction** | PyMuPDF (fitz) with OCR fallback |
| **DOCX Extraction** | python-docx |
| **OCR** | Tesseract + pytesseract |
| **AI Model** | Google Gemini 2.5 Flash (fallback: 1.5 Flash) |
| **Multi-Key System** | Up to 4 API keys with auto-rotation |
| **Frontend** | HTML/CSS/JS with drag-and-drop |
| **Deployment** | Docker |

## 🏗️ Architecture

<div align="center">
  <img src="./DocuMind(architechture).jpeg" alt="Architecture Diagram" width="800"/>
</div>

## ✨ Features

- 📁 Supports PDF, DOCX, and Images
- 🤖 AI-powered summarization & entity extraction
- 🔄 Multi-API-key rotation (4x quota capacity)
- 🛡️ Intelligent fallback (never crashes)
- 🌐 Web UI + REST API
- 🐳 Docker ready

## 🚀 Setup Instructions

### Prerequisites
- Python 3.11+
- Tesseract OCR
- Docker (optional)

### Quick Start

**1. Clone repository**
```bash
git clone <your-repo-url>
cd guvi-hack
```

**2. Configure environment**
```bash
cp .env.example .env
nano .env  # Add your API keys
```

**`.env` file:**
```env
API_KEY=your_secret_key

# Add 1-4 Gemini API keys for rotation
GEMINI_API_KEY_1=your_first_key     # Required
GEMINI_API_KEY_2=your_second_key    # Optional
GEMINI_API_KEY_3=your_third_key     # Optional  
GEMINI_API_KEY_4=your_fourth_key    # Optional

ENVIRONMENT=development
```

Get keys: https://aistudio.google.com/apikey

**3A. Run with Docker (Recommended)**
```bash
docker build -t documind .
docker run -d -p 10000:10000 --env-file .env documind
```
Open: http://localhost:10000

**3B. Run locally**
```bash
# Install Tesseract
apt install tesseract-ocr    # Ubuntu
brew install tesseract        # macOS

# Install Python dependencies
pip install -r requirements.txt

# Run
uvicorn src.main:app --reload
```
Open: http://localhost:8000

## 📊 Data Extraction Strategy

### Text Extraction

| File Type | Method | Details |
|-----------|--------|---------|
| **PDF** | PyMuPDF | Extracts native text; for scanned pages, renders at 300 DPI → Tesseract OCR |
| **DOCX** | python-docx | Extracts paragraphs + tables in reading order |
| **Image** | Tesseract OCR | PSM 6 mode (uniform text block detection) |

### AI Analysis Pipeline

```
Document Upload
    ↓
Text Extraction (PDF/DOCX/Image)
    ↓
Gemini AI Analysis (12,000 char limit)
    ├── Summary (2-3 sentences, info-dense)
    ├── Entities (names, dates, organizations, amounts)
    └── Sentiment (Positive/Negative/Neutral)
    ↓
JSON Response
```

### Multi-Key Rotation System

**How it works:**
1. System tries API Key #1
2. If quota exhausted → switches to Key #2
3. If quota exhausted → switches to Key #3
4. If quota exhausted → switches to Key #4
5. If all exhausted → regex fallback 


### Error Handling

**Rate Limits (429):** Waits 7 seconds, retries automatically  
**Quota Exhausted:** Switches to next API key  
**All Keys Exhausted:** Pattern-based extraction 

## 📡 API Endpoints

### 1. Test Upload (multipart/form-data)
```bash
POST /api/upload-test
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/upload-test \
  -H "x-api-key: your_key" \
  -F "file=@document.pdf"
```

### 2. JSON API (base64)
```bash
POST /api/document-analyze
```

**Request:**
```json
{
  "fileName": "invoice.pdf",
  "fileType": "pdf",
  "fileBase64": "<base64_string>"
}
```

**Response:**
```json
{
  "status": "success",
  "fileName": "invoice.pdf",
  "summary": "Invoice from ABC Corp to John Smith for $10,000 dated March 2026.",
  "entities": {
    "names": ["John Smith"],
    "dates": ["March 2026"],
    "organizations": ["ABC Corp"],
    "amounts": ["$10,000"]
  },
  "sentiment": "Neutral"
}
```

## 🐳 Docker Architecture

**Base Image:** `python:3.11-slim`  
**System Dependencies:** Tesseract OCR  
**Exposed Port:** 10000  
**Application:** FastAPI + Uvicorn

## 🎥 Demo Video

https://youtu.be/tMJi5EOxsNE

## 👨‍💻 Author

**Mubendiran K**  
Rajalakshmi Institute of Technology, Chennai  
Built for **GUVI Hackathon 2026**

---

## 💡 AI Development Tools

- GitHub Copilot – code assistance
- ChatGPT – planning support
