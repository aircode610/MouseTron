// Configuration - Get API_URL from Electron API
const API_BASE_URL = window.electronAPI?.apiUrl || 'http://localhost:8080';
const POLL_INTERVAL = 2000; // Poll every 2 seconds


console.log(`Using API URL: ${API_BASE_URL}`);

// State
let pollInterval = null;
let lastStepsData = null;

// Status icons
const STATUS_ICONS = {
  pending: '⏳',
  in_progress: '⚙️',
  completed: '✅',
  failed: '❌'
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  console.log('Popup initialized');

  // Set up refresh button
  const refreshBtn = document.getElementById('refreshBtn');
  refreshBtn.addEventListener('click', () => {
    fetchSteps();
  });

  // Start polling
  startPolling();

  // Initial fetch
  fetchSteps();
});

// Start polling for updates
function startPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
  }

  pollInterval = setInterval(() => {
    fetchSteps();
  }, POLL_INTERVAL);

  console.log('Started polling every', POLL_INTERVAL, 'ms');
}

// Stop polling
function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  console.log('Stopped polling');
}

// Fetch steps from the server
async function fetchSteps() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/steps`);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const steps = await response.json();
    console.log('Fetched steps:', steps);

    // Update connection status
    updateConnectionStatus('connected');

    // Update UI
    updateStepsUI(steps);
    updateProgressBar(steps);
    updateLastUpdate();

    // Hide error section if visible
    hideError();

    // Store last data
    lastStepsData = steps;

  } catch (error) {
    console.error('Error fetching steps:', error);
    updateConnectionStatus('disconnected');
    showError(`Failed to connect to server: ${error.message}`);
  }
}

// Update connection status indicator
function updateConnectionStatus(status) {
  const statusElement = document.getElementById('connectionStatus');
  const dotElement = statusElement.querySelector('.dot');
  const textElement = statusElement.querySelector('.text');

  statusElement.className = 'status-indicator';

  if (status === 'connected') {
    statusElement.classList.add('connected');
    textElement.textContent = 'Connected';
  } else if (status === 'disconnected') {
    statusElement.classList.add('disconnected');
    textElement.textContent = 'Disconnected';
  } else if (status === 'idle') {
    statusElement.classList.add('idle');
    textElement.textContent = 'Idle';
  }
}

// Update the steps UI
function updateStepsUI(steps) {
  const stepsList = document.getElementById('stepsList');

  if (!steps || steps.length === 0) {
    // Show empty state
    stepsList.innerHTML = `
      <div class="empty-state">
        <p>No steps to display yet.</p>
        <p class="hint">The agent will start processing your request shortly...</p>
      </div>
    `;
    updateConnectionStatus('idle');
    return;
  }

  // Check if agent is running
  const hasActiveSteps = steps.some(s => s.status === 'in_progress');
  if (hasActiveSteps) {
    updateConnectionStatus('connected');
  } else {
    updateConnectionStatus('idle');
  }

  // Build steps HTML
  stepsList.innerHTML = steps.map((step, index) => {
    const icon = STATUS_ICONS[step.status] || '❓';
    const stepNumber = index + 1;

    return `
      <div class="step-item ${step.status}">
        <div class="step-header">
          <span class="step-icon">${icon}</span>
          <span class="step-text">
            <strong>Step ${stepNumber}:</strong> ${escapeHtml(step.step)}
          </span>
          <span class="step-status ${step.status}">${step.status.replace('_', ' ')}</span>
        </div>
      </div>
    `;
  }).join('');
}

// Update progress bar
function updateProgressBar(steps) {
  const progressBar = document.getElementById('progressBar');
  const progressText = document.getElementById('progressText');
  const progressPercent = document.getElementById('progressPercent');

  if (!steps || steps.length === 0) {
    progressBar.style.width = '0%';
    progressText.textContent = 'Waiting for agent...';
    progressPercent.textContent = '0%';
    return;
  }

  // Calculate progress
  const totalSteps = steps.length;
  const completedSteps = steps.filter(s => s.status === 'completed').length;
  const failedSteps = steps.filter(s => s.status === 'failed').length;
  const inProgressSteps = steps.filter(s => s.status === 'in_progress').length;

  const progress = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

  // Update progress bar
  progressBar.style.width = `${progress}%`;
  progressPercent.textContent = `${Math.round(progress)}%`;

  // Update progress text
  if (failedSteps > 0) {
    progressText.textContent = `${failedSteps} step(s) failed`;
    progressBar.style.background = 'linear-gradient(90deg, #ef4444 0%, #dc2626 100%)';
  } else if (inProgressSteps > 0) {
    progressText.textContent = `Processing step ${completedSteps + 1} of ${totalSteps}...`;
    progressBar.style.background = 'linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%)';
  } else if (completedSteps === totalSteps && totalSteps > 0) {
    progressText.textContent = `All ${totalSteps} steps completed!`;
    progressBar.style.background = 'linear-gradient(90deg, #10b981 0%, #059669 100%)';
  } else {
    progressText.textContent = `${completedSteps} of ${totalSteps} steps completed`;
    progressBar.style.background = 'linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%)';
  }
}

// Update last update time
function updateLastUpdate() {
  const lastUpdate = document.getElementById('lastUpdate');
  const now = new Date();
  const timeString = now.toLocaleTimeString();
  lastUpdate.textContent = timeString;
}

// Show error message
function showError(message) {
  const errorSection = document.getElementById('errorSection');
  const errorMessage = document.getElementById('errorMessage');

  errorMessage.textContent = message;
  errorSection.style.display = 'block';
}

// Hide error message
function hideError() {
  const errorSection = document.getElementById('errorSection');
  errorSection.style.display = 'none';
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, m => map[m]);
}

// Clean up on window close
window.addEventListener('beforeunload', () => {
  stopPolling();
});