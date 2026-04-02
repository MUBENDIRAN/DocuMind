FROM python:3.11-slim

# Install system dependencies (only what you actually need)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 
EXPOSE 10000

# Run app
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "10000"]