const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const clearBtn = document.getElementById('clearBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const apiKeyInput = document.getElementById('apiKeyInput');
const loading = document.getElementById('loading');
const resultSection = document.getElementById('resultSection');
const errorSection = document.getElementById('errorSection');
const errorText = document.getElementById('errorText');

let selectedFile = null;

// Click to browse
uploadBox.addEventListener('click', () => fileInput.click());

// File selected
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

// Drag and drop
uploadBox.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadBox.classList.add('dragover');
});

uploadBox.addEventListener('dragleave', () => {
    uploadBox.classList.remove('dragover');
});

uploadBox.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadBox.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
    }
});

// Handle file selection
function handleFile(file) {
    const validExts = ['.pdf', '.docx', '.doc', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.webp'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    
    if (!validExts.includes(ext)) {
        showError('Unsupported file type. Please upload PDF, DOCX, or an image.');
        return;
    }
    
    selectedFile = file;
    fileName.textContent = file.name;
    fileInfo.hidden = false;
    analyzeBtn.disabled = false;
    hideError();
    hideResults();
}

// Clear file
clearBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearFile();
});

function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    fileInfo.hidden = true;
    analyzeBtn.disabled = true;
}

// Analyze button
analyzeBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    
    hideError();
    hideResults();
    loading.hidden = false;
    analyzeBtn.disabled = true;
    
    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        const headers = {};
        const apiKey = apiKeyInput.value.trim();
        if (apiKey) {
            headers['x-api-key'] = apiKey;
        }
        
        const response = await fetch('/api/upload-test', {
            method: 'POST',
            headers: headers,
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail?.message || data.message || 'Analysis failed');
        }
        
        displayResults(data);
    } catch (err) {
        showError(err.message || 'Something went wrong. Please try again.');
    } finally {
        loading.hidden = true;
        analyzeBtn.disabled = false;
    }
});

// Display results
function displayResults(data) {
    // Summary
    document.getElementById('summaryText').textContent = data.summary || 'No summary available.';
    
    // Sentiment
    const sentimentBadge = document.getElementById('sentimentBadge');
    const sentiment = data.sentiment || 'Neutral';
    sentimentBadge.textContent = sentiment;
    sentimentBadge.className = 'sentiment-badge ' + sentiment.toLowerCase();
    
    // Entities
    populateList('namesList', data.entities?.names);
    populateList('datesList', data.entities?.dates);
    populateList('orgsList', data.entities?.organizations);
    populateList('amountsList', data.entities?.amounts);
    
    resultSection.hidden = false;
}

function populateList(elementId, items) {
    const ul = document.getElementById(elementId);
    ul.innerHTML = '';
    
    if (!items || items.length === 0) {
        const li = document.createElement('li');
        li.className = 'empty';
        li.textContent = 'None found';
        ul.appendChild(li);
    } else {
        items.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item;
            ul.appendChild(li);
        });
    }
}

function hideResults() {
    resultSection.hidden = true;
}

function showError(message) {
    errorText.textContent = message;
    errorSection.hidden = false;
}

function hideError() {
    errorSection.hidden = true;
}
