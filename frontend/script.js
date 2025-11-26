const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const previews = document.getElementById('previews');
const convertBtn = document.getElementById('convert-btn');
const scaleSelect = document.getElementById('scale');
const fpsInput = document.getElementById('fps-input');
const progContainer = document.getElementById('progress-container');
const progBar = document.getElementById('progress-bar');
const progText = document.getElementById('progress-text');
const downloads = document.getElementById('downloads');
const POLL_MAX_RETRIES = 5;
const POLL_BASE_DELAY_MS = 1000;

let fileData = []; // Store { file, startTime, endTime, duration, elements: {startInput, endInput, startSlider, endSlider, timeDisplay} }
let objectUrls = []; // Keep track of object URLs to revoke later

// Drag & drop handlers
['dragenter','dragover'].forEach(evt => {
  dropZone.addEventListener(evt, e => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
});
['dragleave','drop'].forEach(evt => {
  dropZone.addEventListener(evt, e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
  });
});
dropZone.addEventListener('drop', e => {
  handleFiles(e.dataTransfer.files);
});
dropZone.addEventListener('click', (e) => {
  if (e.target !== fileInput) {
    fileInput.click();
  }
});
fileInput.addEventListener('change', () => {
  handleFiles(fileInput.files);
});

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.round((seconds - Math.floor(seconds)) * 100);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(ms).padStart(2, '0')}`;
}

function handleFiles(files) {
  // Revoke previous object URLs and clear data
  objectUrls.forEach(url => URL.revokeObjectURL(url));
  objectUrls = [];
  fileData = [];
  previews.innerHTML = '';

  Array.from(files).forEach((file, index) => {
    if (file.type.startsWith('video/')) {
      const url = URL.createObjectURL(file);
      objectUrls.push(url); // Store the URL

      const container = document.createElement('div');
      container.classList.add('video-editor-container'); // New class for styling

      const video = document.createElement('video');
      video.src = url;
      video.controls = true;
      video.classList.add('video-preview'); // Reuse existing style if applicable
      video.muted = true; // Mute by default to allow autoplay if needed, and prevent loudness

      const fileName = document.createElement('p');
      fileName.classList.add('video-filename');

      // --- Editor Controls ---
      const editorControls = document.createElement('div');
      editorControls.classList.add('editor-controls');

      const timeDisplay = document.createElement('div');
      timeDisplay.classList.add('time-display');
      timeDisplay.textContent = 'Start: 00:00.00 | End: Loading... | Selected: Loading... | Total: Loading...';

      // -- Start Control Row --
      const startRow = document.createElement('div');
      startRow.classList.add('control-row');
      const startLabel = document.createElement('label');
      startLabel.textContent = 'Start:';
      const startSlider = document.createElement('input');
      startSlider.type = 'range'; startSlider.min = 0; startSlider.max = 1; startSlider.step = 0.01; startSlider.value = 0; startSlider.disabled = true;
      startSlider.classList.add('time-slider', 'start-slider');
      const startInput = document.createElement('input');
      startInput.type = 'number'; startInput.min = 0; startInput.step = 0.01; startInput.value = 0; startInput.disabled = true;
      startInput.classList.add('time-input', 'start-input');
      startRow.appendChild(startLabel);
      startRow.appendChild(startSlider);
      startRow.appendChild(startInput);
      // -- End Start Control Row --

      // -- End Control Row --
      const endRow = document.createElement('div');
      endRow.classList.add('control-row');
      const endLabel = document.createElement('label');
      endLabel.textContent = 'End:';
      const endSlider = document.createElement('input');
      endSlider.type = 'range'; endSlider.min = 0; endSlider.max = 1; endSlider.step = 0.01; endSlider.value = 1; endSlider.disabled = true;
      endSlider.classList.add('time-slider', 'end-slider');
      const endInput = document.createElement('input');
      endInput.type = 'number'; endInput.min = 0; endInput.step = 0.01; endInput.value = 1; endInput.disabled = true;
      endInput.classList.add('time-input', 'end-input');
      endRow.appendChild(endLabel);
      endRow.appendChild(endSlider);
      endRow.appendChild(endInput);
      // -- End End Control Row --


      editorControls.appendChild(timeDisplay);
      editorControls.appendChild(startRow); // Add the row div
      editorControls.appendChild(endRow);   // Add the row div
      // --- End Editor Controls ---

      container.appendChild(video);
      container.appendChild(fileName);
      container.appendChild(editorControls);
      previews.appendChild(container);

      const currentFileData = {
        file: file,
        startTime: 0,
        endTime: 0,
        duration: 0,
        originalWidth: 0,
        originalHeight: 0,
        elements: { startInput, endInput, startSlider, endSlider, timeDisplay, video }
      };
      fileData.push(currentFileData);

      // Event Listeners Setup
      video.addEventListener('loadedmetadata', () => {
        const duration = video.duration;
        const width = video.videoWidth;
        const height = video.videoHeight;

        currentFileData.duration = duration;
        currentFileData.endTime = duration;
        currentFileData.originalWidth = width;
        currentFileData.originalHeight = height;

        fileName.textContent = `${file.name} (${width}x${height})`;

        // Update controls
        startSlider.max = duration; startSlider.disabled = false; startSlider.value = 0;
        endSlider.max = duration; endSlider.disabled = false; endSlider.value = duration;
        startInput.max = duration; startInput.disabled = false; startInput.value = 0;
        endInput.max = duration; endInput.disabled = false; endInput.value = duration;

        updateTimeDisplay(currentFileData);
      });

      startSlider.addEventListener('input', () => handleTimeChange(currentFileData, 'startSlider'));
      endSlider.addEventListener('input', () => handleTimeChange(currentFileData, 'endSlider'));
      startInput.addEventListener('input', () => handleTimeChange(currentFileData, 'startInput'));
      endInput.addEventListener('input', () => handleTimeChange(currentFileData, 'endInput'));

      // Optional: Seek video on slider interaction
       startSlider.addEventListener('input', () => { if (!video.paused) video.pause(); video.currentTime = parseFloat(startSlider.value); });
       endSlider.addEventListener('input', () => { if (!video.paused) video.pause(); video.currentTime = parseFloat(endSlider.value); });


    } else {
      // Handle non-video files if necessary (e.g., show an icon or skip)
      console.warn(`Skipping non-video file: ${file.name}`);
      const unsupportedPreview = document.createElement('div');
      unsupportedPreview.textContent = `Unsupported file: ${file.name}`;
      unsupportedPreview.classList.add('unsupported-preview');
      previews.appendChild(unsupportedPreview);
    }
  });
}

function handleTimeChange(data, source) {
  const { startInput, endInput, startSlider, endSlider, video } = data.elements;
  let start = parseFloat(startSlider.value);
  let end = parseFloat(endSlider.value);
  const duration = data.duration;

  // Read value from the source that triggered the event
  if (source === 'startSlider') start = parseFloat(startSlider.value);
  if (source === 'endSlider') end = parseFloat(endSlider.value);
  if (source === 'startInput') start = parseFloat(startInput.value);
  if (source === 'endInput') end = parseFloat(endInput.value);

  // Basic validation & adjustment
  if (isNaN(start) || start < 0) start = 0;
  if (isNaN(end) || end < 0) end = 0; // Allow end to be 0 temporarily during input
  if (start > duration) start = duration;
  if (end > duration) end = duration;

  // Prevent start time from exceeding end time (and vice-versa)
  if ((source === 'startSlider' || source === 'startInput') && start >= end) {
    start = end - 0.01; // Adjust start slightly less than end
    if (start < 0) start = 0;
  }
  if ((source === 'endSlider' || source === 'endInput') && end <= start) {
    end = start + 0.01; // Adjust end slightly more than start
    if (end > duration) end = duration;
     // If adjusting end pushed it over duration, check if we can pull start back
     if (end > duration && start > 0) {
         start = duration - 0.01;
         if(start < 0) start = 0;
         end = duration;
     }
  }

   // Final clamping
   start = Math.max(0, Math.min(start, duration));
   end = Math.max(0, Math.min(end, duration));
   if (end < start) { // Final check
       if(source.startsWith('start')) end = start;
       else start = end;
   }


  // Update data object
  data.startTime = start;
  data.endTime = end;

  // Update corresponding controls (prevent infinite loops)
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
    const durationStr = formatTime(data.duration);
    const selectionDuration = formatTime(Math.max(0, data.endTime - data.startTime));
    timeDisplay.textContent = `Start: ${startStr} | End: ${endStr} | Selected: ${selectionDuration} | Total: ${durationStr}`;
}


convertBtn.addEventListener('click', async () => {
  if (!fileData.length) return alert('Please add video files first.');

  // Revoke object URLs before starting upload if desired
  // objectUrls.forEach(url => URL.revokeObjectURL(url));
  // objectUrls = [];
  // previews.innerHTML = ''; // Clear previews if desired

  const form = new FormData();
  const startTimes = [];
  const endTimes = [];

  fileData.forEach(data => {
    form.append('files', data.file);
    startTimes.push(data.startTime.toFixed(3));
    endTimes.push(data.endTime.toFixed(3));
  });

  // Get FPS value (with validation/defaulting)
  let fps = parseInt(fpsInput.value, 10);
  if (isNaN(fps) || fps < 1 || fps > 20) {
      console.warn(`Invalid FPS value (${fpsInput.value}), defaulting to 10.`);
      fps = 10; // Default to 10 if invalid
      fpsInput.value = 10; // Correct the input field as well
  }

  form.append('scale', scaleSelect.value);
  form.append('fps', fps); // Append FPS value
  // Send times as separate lists
  startTimes.forEach(t => form.append('start_times', t));
  endTimes.forEach(t => form.append('end_times', t));


  progContainer.classList.remove('hidden');
  downloads.innerHTML = ''; // Clear previous downloads

  try {
    // --- Fetch and poll logic (mostly unchanged, ensure pollProgress handles errors) ---
    const res = await fetch('/convert', { method: 'POST', body: form });
    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
    const { job_id } = await res.json();
    pollProgress(job_id, 0);
    // --- End fetch and poll logic ---
  } catch (error) {
      console.error('Error starting conversion:', error);
      progText.textContent = `Error starting conversion: ${error.message}`;
      progContainer.classList.remove('hidden'); // Ensure progress area is visible for error
      progBar.value = 0;
  }
});

async function pollProgress(job_id, attempt = 0) {
  try {
    const res = await fetch(`/progress?job_id=${job_id}`);
    if (!res.ok) {
        // Handle potential errors during polling (e.g., job not found, server error)
        if (res.status === 404) {
          progText.textContent = `Job ${job_id} not found. It might have expired or failed.`;
          progBar.value = 0;
          console.error(`Polling error: Job ${job_id} not found.`);
          // Stop polling if job not found
          return;
        }
        throw new Error(`HTTP error! status: ${res.status}`);
    }
    const data = await res.json();

    // Defensive checks for data structure
    if (!data || typeof data !== 'object') {
      throw new Error('Invalid progress data received');
    }

    const {
      current_file_index = 0,
      total_files = 1,
      current_file_percent = 0,
      current_file_est_seconds = null,
      status = 'unknown',
      downloads: dls = []
    } = data; // Provide defaults

    progBar.value = current_file_percent;
    const etaString = current_file_est_seconds !== null && current_file_est_seconds >= 0 ? `${current_file_est_seconds}s` : '--';
    progText.textContent = `${status} — File ${current_file_index}/${total_files} — ${current_file_percent}% (est. ${etaString})`;

    const isDone = status === 'done' || status === 'failed' || status.startsWith('completed') || status.startsWith('error');
    const isSuccess = status === 'done' || status.startsWith('completed');

    if (!isDone) {
      setTimeout(() => pollProgress(job_id, attempt + 1), 1000);
    } else {
        // Final status is set above
        if (isSuccess && downloads.children.length === 0 && dls && dls.length > 0) {
            dls.forEach(d => {
                if (d && d.url) { // Check if download info is valid
                  const a = document.createElement('a');
                  a.href = d.url;
                  // Use the actual gif filename for the link text, removing '.gif' extension
                  const filename = d.url.split('/').pop();
                  const linkTextName = filename.endsWith('.gif') ? filename.slice(0, -4) : filename;
                  a.textContent = `Download ${linkTextName}.gif`;
                  a.download = filename; // Set download attribute for better UX
                  downloads.appendChild(a);
                  downloads.appendChild(document.createElement('br'));
                } else {
                  console.warn('Received invalid download data:', d);
                }
            });
        } else if (!isSuccess) {
           // Display error status clearly if polling finishes with an error
           progText.textContent = `Error during conversion: ${status}`;
           console.error(`Conversion failed for job ${job_id}: ${status}`);
        }
    }
  } catch (error) {
    console.error('Error polling progress:', error);
    progText.textContent = `Error fetching progress: ${error.message}`;
    if (attempt < POLL_MAX_RETRIES) {
      const delay = POLL_BASE_DELAY_MS * (attempt + 1);
      setTimeout(() => pollProgress(job_id, attempt + 1), delay);
    }
  }
} 