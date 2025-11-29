/**
 * vid2gif WebUI - Modern Frontend
 * Video to GIF conversion with trimming support
 */

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const previews = document.getElementById('previews');
const conversionPanel = document.getElementById('conversion-panel');
const convertBtn = document.getElementById('convert-btn');
const scaleSelect = document.getElementById('scale');
const fpsInput = document.getElementById('fps-input');
const progressContainer = document.getElementById('progress-container');
const progressBar = document.getElementById('progress-bar');
const progressStatus = document.getElementById('progress-status');
const progressPercent = document.getElementById('progress-percent');
const progressDetails = document.getElementById('progress-details');
const downloadsContainer = document.getElementById('downloads-container');
const downloadsList = document.getElementById('downloads-list');
const toast = document.getElementById('toast');

// Constants
const POLL_MAX_RETRIES = 5;
const POLL_BASE_DELAY_MS = 1000;

// State
let fileData = [];
let objectUrls = [];
let isConverting = false;

// ============================================
// Toast Notifications
// ============================================

function showToast(message, type = 'info', duration = 3000) {
  toast.textContent = message;
  toast.className = `toast ${type} visible`;
  
  setTimeout(() => {
    toast.classList.remove('visible');
  }, duration);
}

// ============================================
// Utility Functions
// ============================================

function formatTime(seconds) {
  if (!isFinite(seconds) || seconds < 0) seconds = 0;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.round((seconds - Math.floor(seconds)) * 100);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(2, '0')}`;
}

function formatDuration(seconds) {
  if (!isFinite(seconds) || seconds < 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ============================================
// Drag & Drop Handlers
// ============================================

['dragenter', 'dragover'].forEach(evt => {
  dropZone.addEventListener(evt, e => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach(evt => {
  dropZone.addEventListener(evt, e => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove('dragover');
  });
});

dropZone.addEventListener('drop', e => {
  const files = e.dataTransfer.files;
  if (files.length > 0) {
    handleFiles(files);
  }
});

// Click and keyboard support for drop zone
dropZone.addEventListener('click', e => {
  if (e.target !== fileInput) {
    fileInput.click();
  }
});

dropZone.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length > 0) {
    handleFiles(fileInput.files);
  }
});

// ============================================
// File Handling
// ============================================

function handleFiles(files) {
  // Revoke previous object URLs
  objectUrls.forEach(url => URL.revokeObjectURL(url));
  objectUrls = [];
  fileData = [];
  previews.innerHTML = '';
  
  // Hide downloads from previous conversion
  downloadsContainer.classList.remove('visible');
  downloadsList.innerHTML = '';
  progressContainer.classList.remove('visible');

  const videoFiles = Array.from(files).filter(file => file.type.startsWith('video/'));
  const unsupportedFiles = Array.from(files).filter(file => !file.type.startsWith('video/'));

  if (unsupportedFiles.length > 0) {
    showToast(`${unsupportedFiles.length} unsupported file(s) skipped`, 'error');
  }

  if (videoFiles.length === 0) {
    conversionPanel.classList.add('hidden');
    showToast('Please select video files', 'error');
    return;
  }

  videoFiles.forEach((file, index) => {
    createVideoEditor(file, index);
  });

  // Show conversion panel
  conversionPanel.classList.remove('hidden');
  
  showToast(`${videoFiles.length} video(s) loaded`, 'success');
}

function createVideoEditor(file, index) {
  const url = URL.createObjectURL(file);
  objectUrls.push(url);

  // Container
  const container = document.createElement('article');
  container.classList.add('video-editor-container');
  container.setAttribute('data-index', index);

  // Video wrapper with remove button
  const videoWrapper = document.createElement('div');
  videoWrapper.classList.add('video-wrapper');

  const video = document.createElement('video');
  video.src = url;
  video.controls = true;
  video.classList.add('video-preview');
  video.muted = true;
  video.playsInline = true;
  video.preload = 'metadata';

  const removeBtn = document.createElement('button');
  removeBtn.classList.add('remove-video-btn');
  removeBtn.setAttribute('aria-label', 'Remove video');
  removeBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
  removeBtn.addEventListener('click', () => removeVideo(index));

  videoWrapper.appendChild(video);
  videoWrapper.appendChild(removeBtn);

  // Video info
  const videoInfo = document.createElement('div');
  videoInfo.classList.add('video-info');
  
  const fileName = document.createElement('div');
  fileName.classList.add('video-filename');
  fileName.textContent = file.name;
  
  const videoMeta = document.createElement('div');
  videoMeta.classList.add('video-meta');
  videoMeta.textContent = `${formatFileSize(file.size)} • Loading...`;

  videoInfo.appendChild(fileName);
  videoInfo.appendChild(videoMeta);

  // Editor controls
  const editorControls = document.createElement('div');
  editorControls.classList.add('editor-controls');

  // Time display
  const timeDisplay = document.createElement('div');
  timeDisplay.classList.add('time-display');
  timeDisplay.innerHTML = `
    <span>Start: <span class="time-value">00:00.00</span></span>
    <span>End: <span class="time-value">--:--</span></span>
    <span>Duration: <span class="time-value">--:--</span></span>
  `;

  // Start control row
  const startRow = document.createElement('div');
  startRow.classList.add('control-row');
  
  const startLabel = document.createElement('label');
  startLabel.textContent = 'Start';
  startLabel.setAttribute('for', `start-slider-${index}`);
  
  const startSlider = document.createElement('input');
  startSlider.type = 'range';
  startSlider.id = `start-slider-${index}`;
  startSlider.min = 0;
  startSlider.max = 1;
  startSlider.step = 0.01;
  startSlider.value = 0;
  startSlider.disabled = true;
  startSlider.classList.add('time-slider');
  
  const startInput = document.createElement('input');
  startInput.type = 'number';
  startInput.min = 0;
  startInput.step = 0.01;
  startInput.value = '0.00';
  startInput.disabled = true;
  startInput.classList.add('time-input');
  startInput.setAttribute('aria-label', 'Start time in seconds');

  startRow.appendChild(startLabel);
  startRow.appendChild(startSlider);
  startRow.appendChild(startInput);

  // End control row
  const endRow = document.createElement('div');
  endRow.classList.add('control-row');
  
  const endLabel = document.createElement('label');
  endLabel.textContent = 'End';
  endLabel.setAttribute('for', `end-slider-${index}`);
  
  const endSlider = document.createElement('input');
  endSlider.type = 'range';
  endSlider.id = `end-slider-${index}`;
  endSlider.min = 0;
  endSlider.max = 1;
  endSlider.step = 0.01;
  endSlider.value = 1;
  endSlider.disabled = true;
  endSlider.classList.add('time-slider');
  
  const endInput = document.createElement('input');
  endInput.type = 'number';
  endInput.min = 0;
  endInput.step = 0.01;
  endInput.value = '0.00';
  endInput.disabled = true;
  endInput.classList.add('time-input');
  endInput.setAttribute('aria-label', 'End time in seconds');

  endRow.appendChild(endLabel);
  endRow.appendChild(endSlider);
  endRow.appendChild(endInput);

  editorControls.appendChild(timeDisplay);
  editorControls.appendChild(startRow);
  editorControls.appendChild(endRow);

  // Assemble container
  container.appendChild(videoWrapper);
  container.appendChild(videoInfo);
  container.appendChild(editorControls);
  previews.appendChild(container);

  // Store file data
  const currentFileData = {
    file,
    startTime: 0,
    endTime: 0,
    duration: 0,
    originalWidth: 0,
    originalHeight: 0,
    container,
    elements: { 
      startInput, endInput, startSlider, endSlider, 
      timeDisplay, video, videoMeta 
    }
  };
  fileData.push(currentFileData);

  // Event listeners
  video.addEventListener('loadedmetadata', () => {
    const duration = video.duration;
    const width = video.videoWidth;
    const height = video.videoHeight;

    currentFileData.duration = duration;
    currentFileData.endTime = duration;
    currentFileData.originalWidth = width;
    currentFileData.originalHeight = height;

    videoMeta.textContent = `${formatFileSize(file.size)} • ${width}x${height} • ${formatDuration(duration)}`;

    // Enable and configure controls
    startSlider.max = duration;
    startSlider.disabled = false;
    startSlider.value = 0;
    
    endSlider.max = duration;
    endSlider.disabled = false;
    endSlider.value = duration;
    
    startInput.max = duration;
    startInput.disabled = false;
    startInput.value = '0.00';
    
    endInput.max = duration;
    endInput.disabled = false;
    endInput.value = duration.toFixed(2);

    updateTimeDisplay(currentFileData);
  });

  video.addEventListener('error', () => {
    videoMeta.textContent = 'Error loading video';
    showToast(`Failed to load: ${file.name}`, 'error');
  });

  // Time control event listeners
  startSlider.addEventListener('input', () => {
    handleTimeChange(currentFileData, 'startSlider');
    video.currentTime = parseFloat(startSlider.value);
  });
  
  endSlider.addEventListener('input', () => {
    handleTimeChange(currentFileData, 'endSlider');
    video.currentTime = parseFloat(endSlider.value);
  });
  
  startInput.addEventListener('input', () => handleTimeChange(currentFileData, 'startInput'));
  endInput.addEventListener('input', () => handleTimeChange(currentFileData, 'endInput'));
  
  // Blur events for input validation
  startInput.addEventListener('blur', () => {
    startInput.value = currentFileData.startTime.toFixed(2);
  });
  
  endInput.addEventListener('blur', () => {
    endInput.value = currentFileData.endTime.toFixed(2);
  });
}

function removeVideo(index) {
  if (fileData[index]) {
    const data = fileData[index];
    if (data.container) {
      data.container.remove();
    }
    // Revoke the object URL
    const urlIndex = fileData.indexOf(data);
    if (urlIndex !== -1 && objectUrls[urlIndex]) {
      URL.revokeObjectURL(objectUrls[urlIndex]);
      objectUrls.splice(urlIndex, 1);
    }
    fileData.splice(index, 1);
    
    // Update indices
    fileData.forEach((fd, i) => {
      if (fd.container) {
        fd.container.setAttribute('data-index', i);
      }
    });

    if (fileData.length === 0) {
      conversionPanel.classList.add('hidden');
    }
    
    showToast('Video removed', 'info');
  }
}

// ============================================
// Time Control Handlers
// ============================================

function handleTimeChange(data, source) {
  const { startInput, endInput, startSlider, endSlider } = data.elements;
  let start = parseFloat(startSlider.value);
  let end = parseFloat(endSlider.value);
  const duration = data.duration;

  // Read value from the source
  if (source === 'startSlider') start = parseFloat(startSlider.value);
  if (source === 'endSlider') end = parseFloat(endSlider.value);
  if (source === 'startInput') start = parseFloat(startInput.value);
  if (source === 'endInput') end = parseFloat(endInput.value);

  // Validation
  if (isNaN(start) || start < 0) start = 0;
  if (isNaN(end) || end < 0) end = 0;
  if (start > duration) start = duration;
  if (end > duration) end = duration;

  // Prevent overlap
  const minGap = 0.1;
  if ((source === 'startSlider' || source === 'startInput') && start >= end - minGap) {
    start = Math.max(0, end - minGap);
  }
  if ((source === 'endSlider' || source === 'endInput') && end <= start + minGap) {
    end = Math.min(duration, start + minGap);
  }

  // Final clamping
  start = Math.max(0, Math.min(start, duration));
  end = Math.max(0, Math.min(end, duration));

  // Update data
  data.startTime = start;
  data.endTime = end;

  // Sync controls
  if (source !== 'startSlider') startSlider.value = start;
  if (source !== 'endSlider') endSlider.value = end;
  if (source !== 'startInput') startInput.value = start.toFixed(2);
  if (source !== 'endInput') endInput.value = end.toFixed(2);

  updateTimeDisplay(data);
}

function updateTimeDisplay(data) {
  const { timeDisplay } = data.elements;
  const startStr = formatTime(data.startTime);
  const endStr = formatTime(data.endTime);
  const selectionDuration = formatTime(Math.max(0, data.endTime - data.startTime));
  
  timeDisplay.innerHTML = `
    <span>Start: <span class="time-value">${startStr}</span></span>
    <span>End: <span class="time-value">${endStr}</span></span>
    <span>Duration: <span class="time-value">${selectionDuration}</span></span>
  `;
}

// ============================================
// Conversion
// ============================================

convertBtn.addEventListener('click', async () => {
  if (isConverting) return;
  
  if (!fileData.length) {
    showToast('Please add video files first', 'error');
    return;
  }

  // Validate all files have valid time ranges
  for (const data of fileData) {
    if (data.endTime <= data.startTime) {
      showToast('Invalid time range detected', 'error');
      return;
    }
  }

  isConverting = true;
  convertBtn.disabled = true;
  convertBtn.innerHTML = `
    <svg class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10" stroke-dasharray="60" stroke-dashoffset="20"/>
    </svg>
    Converting...
  `;

  const form = new FormData();
  const startTimes = [];
  const endTimes = [];

  fileData.forEach(data => {
    form.append('files', data.file);
    startTimes.push(data.startTime.toFixed(3));
    endTimes.push(data.endTime.toFixed(3));
  });

  // Validate and get FPS
  let fps = parseInt(fpsInput.value, 10);
  if (isNaN(fps) || fps < 1 || fps > 20) {
    fps = 10;
    fpsInput.value = 10;
  }

  form.append('scale', scaleSelect.value);
  form.append('fps', fps);
  startTimes.forEach(t => form.append('start_times', t));
  endTimes.forEach(t => form.append('end_times', t));

  // Show progress
  progressContainer.classList.add('visible');
  downloadsContainer.classList.remove('visible');
  downloadsList.innerHTML = '';
  updateProgress(0, 'Uploading...', '');

  try {
    const res = await fetch('/convert', { method: 'POST', body: form });
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || `Server error: ${res.status}`);
    }
    const { job_id } = await res.json();
    pollProgress(job_id, 0);
  } catch (error) {
    console.error('Error starting conversion:', error);
    showToast(`Conversion failed: ${error.message}`, 'error');
    updateProgress(0, 'Error', error.message);
    resetConvertButton();
  }
});

function updateProgress(percent, status, details) {
  progressBar.style.width = `${percent}%`;
  progressBar.setAttribute('aria-valuenow', percent);
  progressPercent.textContent = `${Math.round(percent)}%`;
  progressStatus.textContent = status;
  progressDetails.textContent = details;
}

function resetConvertButton() {
  isConverting = false;
  convertBtn.disabled = false;
  convertBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <polygon points="10 8 16 12 10 16 10 8"/>
    </svg>
    Create GIF
  `;
}

async function pollProgress(jobId, attempt = 0) {
  try {
    const res = await fetch(`/progress?job_id=${jobId}`);
    
    if (!res.ok) {
      if (res.status === 404) {
        updateProgress(0, 'Job not found', 'The conversion job may have expired');
        resetConvertButton();
        return;
      }
      throw new Error(`Server error: ${res.status}`);
    }
    
    const data = await res.json();
    
    if (!data || typeof data !== 'object') {
      throw new Error('Invalid response from server');
    }

    const {
      current_file_index = 0,
      total_files = 1,
      current_file_percent = 0,
      current_file_est_seconds = null,
      status = 'unknown',
      downloads: dls = []
    } = data;

    const etaStr = current_file_est_seconds !== null && current_file_est_seconds >= 0 
      ? `~${current_file_est_seconds}s remaining` 
      : '';
    
    const statusText = status.charAt(0).toUpperCase() + status.slice(1);
    const detailsText = total_files > 1 
      ? `File ${current_file_index}/${total_files} ${etaStr}`.trim()
      : etaStr;

    updateProgress(current_file_percent, statusText, detailsText);

    const isDone = status === 'done' || status === 'failed' || 
                   status.startsWith('completed') || status.startsWith('error');
    const isSuccess = status === 'done' || status.startsWith('completed');

    if (!isDone) {
      setTimeout(() => pollProgress(jobId, 0), 1000);
    } else {
      resetConvertButton();
      
      if (isSuccess && dls && dls.length > 0) {
        showDownloads(dls);
        showToast('Conversion complete!', 'success');
      } else if (!isSuccess) {
        showToast(`Conversion failed: ${status}`, 'error');
      }
    }
  } catch (error) {
    console.error('Error polling progress:', error);
    
    if (attempt < POLL_MAX_RETRIES) {
      const delay = POLL_BASE_DELAY_MS * (attempt + 1);
      updateProgress(0, 'Retrying...', `Connection issue, retrying in ${delay/1000}s`);
      setTimeout(() => pollProgress(jobId, attempt + 1), delay);
    } else {
      updateProgress(0, 'Connection lost', 'Please check your network and try again');
      resetConvertButton();
      showToast('Lost connection to server', 'error');
    }
  }
}

function showDownloads(downloads) {
  downloadsList.innerHTML = '';
  
  downloads.forEach(d => {
    if (!d || !d.url) return;
    
    const filename = d.url.split('/').pop();
    const displayName = filename.endsWith('.gif') ? filename.slice(0, -4) : filename;
    
    const link = document.createElement('a');
    link.href = d.url;
    link.download = filename;
    link.classList.add('download-item');
    link.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
      <span>${displayName}.gif</span>
    `;
    
    downloadsList.appendChild(link);
  });
  
  downloadsContainer.classList.add('visible');
}

// ============================================
// Spinner Animation (CSS)
// ============================================

const spinnerStyle = document.createElement('style');
spinnerStyle.textContent = `
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .spinner {
    animation: spin 1s linear infinite;
  }
`;
document.head.appendChild(spinnerStyle); 