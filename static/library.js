/**
 * Gridfinity Creator - Configuration Library Manager
 * Stores and manages user configurations in browser localStorage
 */

class GridfinityLibrary {
  constructor() {
    this.STORAGE_KEY = 'gridfinitycreator_library';
    this.VERSION = '1.0';
    this.init();
  }

  init() {
    // Initialize library in localStorage if it doesn't exist
    if (!localStorage.getItem(this.STORAGE_KEY)) {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify({
        version: this.VERSION,
        configs: []
      }));
    }
  }

  /**
   * Save current form configuration to library
   * @param {string} formId - The form ID (e.g., 'classicbin')
   * @param {string} name - User-provided name for this config
   * @returns {object} The saved configuration
   */
  saveConfig(formId, name) {
    const formElement = document.getElementById(formId + '_form');
    if (!formElement) {
      throw new Error(`Form with ID ${formId}_form not found`);
    }

    const config = {
      id: Date.now() + '_' + Math.random().toString(36).substr(2, 9),
      name: name,
      formId: formId,
      data: this.captureFormData(formElement),
      createdAt: new Date().toISOString(),
      notes: ''
    };

    const library = JSON.parse(localStorage.getItem(this.STORAGE_KEY));
    library.configs.push(config);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(library));

    return config;
  }

  /**
   * Load a configuration into a form
   * @param {string} configId - The config ID to load
   * @param {string} formId - The form ID to load into
   */
  loadConfig(configId, formId) {
    const library = JSON.parse(localStorage.getItem(this.STORAGE_KEY));
    const config = library.configs.find(c => c.id === configId);

    if (!config) {
      throw new Error(`Configuration ${configId} not found`);
    }

    const formElement = document.getElementById(formId + '_form');
    if (!formElement) {
      throw new Error(`Form with ID ${formId}_form not found`);
    }

    this.populateFormData(formElement, config.data);
    return config;
  }

  /**
   * Delete a configuration from library
   * @param {string} configId - The config ID to delete
   */
  deleteConfig(configId) {
    const library = JSON.parse(localStorage.getItem(this.STORAGE_KEY));
    library.configs = library.configs.filter(c => c.id !== configId);
    localStorage.setItem(this.STORAGE_KEY, JSON.stringify(library));
  }

  /**
   * Get all configurations or filter by formId
   * @param {string} formId - Optional: filter by form type
   * @returns {array} Array of configurations
   */
  getAllConfigs(formId = null) {
    const library = JSON.parse(localStorage.getItem(this.STORAGE_KEY));
    if (!formId) {
      return library.configs;
    }
    return library.configs.filter(c => c.formId === formId);
  }

  /**
   * Get a single configuration
   * @param {string} configId - The config ID
   * @returns {object} The configuration
   */
  getConfig(configId) {
    const library = JSON.parse(localStorage.getItem(this.STORAGE_KEY));
    return library.configs.find(c => c.id === configId);
  }

  /**
   * Export library as JSON string
   * @returns {string} JSON string of entire library
   */
  exportLibrary() {
    return localStorage.getItem(this.STORAGE_KEY);
  }

  /**
   * Import library from JSON string (overwrites existing)
   * @param {string} jsonString - JSON string to import
   */
  importLibrary(jsonString) {
    try {
      const imported = JSON.parse(jsonString);
      if (!imported.version || !Array.isArray(imported.configs)) {
        throw new Error('Invalid library format');
      }
      localStorage.setItem(this.STORAGE_KEY, jsonString);
      return true;
    } catch (e) {
      throw new Error('Failed to import library: ' + e.message);
    }
  }

  /**
   * Export library as a shareable encoded string
   * @returns {string} URL-safe encoded library
   */
  exportAsString() {
    const json = this.exportLibrary();
    return btoa(json);
  }

  /**
   * Import library from encoded string
   * @param {string} encodedString - Encoded library string
   */
  importFromString(encodedString) {
    try {
      const json = atob(encodedString);
      this.importLibrary(json);
      return true;
    } catch (e) {
      throw new Error('Failed to decode library: ' + e.message);
    }
  }

  /**
   * Clear entire library (use with caution)
   */
  clearLibrary() {
    if (confirm('Are you sure you want to delete all saved configurations? This cannot be undone.')) {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify({
        version: this.VERSION,
        configs: []
      }));
      return true;
    }
    return false;
  }

  /**
   * Capture all form field values
   * @private
   */
  captureFormData(formElement) {
    const data = {};
    const formData = new FormData(formElement);

    for (let [key, value] of formData.entries()) {
      if (key !== 'csrf_token') {
        // Handle checkboxes - they might appear multiple times or not at all
        if (data[key] !== undefined) {
          if (!Array.isArray(data[key])) {
            data[key] = [data[key]];
          }
          data[key].push(value);
        } else {
          data[key] = value;
        }
      }
    }

    // Also capture checkbox states directly from form inputs
    const checkboxes = formElement.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
      data[checkbox.name] = checkbox.checked;
    });

    return data;
  }

  /**
   * Populate form fields with saved data
   * @private
   */
  populateFormData(formElement, data) {
    for (let [key, value] of Object.entries(data)) {
      const field = formElement.elements[key];
      if (!field) continue;

      if (field.type === 'checkbox') {
        field.checked = value === true || value === 'true' || value === 'on';
      } else if (field.type === 'radio') {
        const radioButton = formElement.querySelector(`input[name="${key}"][value="${value}"]`);
        if (radioButton) {
          radioButton.checked = true;
        }
      } else if (field.tagName === 'SELECT') {
        field.value = value;
      } else {
        field.value = value;
      }
    }
  }

  /**
   * Get storage size in bytes
   * @returns {number} Size of library in bytes
   */
  getStorageSize() {
    const data = localStorage.getItem(this.STORAGE_KEY);
    return data ? new Blob([data]).size : 0;
  }

  /**
   * Get storage usage percentage (approximate)
   * @returns {number} Usage percentage (0-100)
   */
  getStorageUsagePercent() {
    // localStorage is typically 5-10MB per domain
    const sizeInMB = this.getStorageSize() / (1024 * 1024);
    const estimatedTotal = 5; // Conservative estimate
    return Math.min(100, Math.round((sizeInMB / estimatedTotal) * 100));
  }
}

// Create global library instance
const gridfinityLib = new GridfinityLibrary();

/**
 * UI Helper Functions
 */

/**
 * Show save configuration modal
 * @param {string} formId - The form ID
 */
function showSaveModal(formId) {
  const modal = new bootstrap.Modal(document.getElementById('library-save-modal'));
  document.getElementById('save-form-id').value = formId;
  document.getElementById('save-config-name').value = '';
  document.getElementById('save-config-name').focus();
  modal.show();
}

/**
 * Show load configuration modal for a specific form
 * @param {string} formId - The form ID
 */
function showLoadModal(formId) {
  const configs = gridfinityLib.getAllConfigs(formId);
  
  if (configs.length === 0) {
    alert('No saved configurations for this component.');
    return;
  }

  const listHtml = configs.map(config => `
    <div class="list-group-item d-flex justify-content-between align-items-center">
      <div>
        <strong>${escapeHtml(config.name)}</strong>
        <small class="text-muted d-block">${new Date(config.createdAt).toLocaleString()}</small>
      </div>
      <div>
        <button class="btn btn-sm btn-primary me-2" onclick="libraryLoadAndClose('${escapeHtml(config.id)}', '${formId}')">Load</button>
        <button class="btn btn-sm btn-danger" onclick="libraryDelete('${escapeHtml(config.id)}')">Delete</button>
      </div>
    </div>
  `).join('');

  document.getElementById('library-list').innerHTML = `
    <div class="list-group">
      ${listHtml}
    </div>
  `;

  const modal = new bootstrap.Modal(document.getElementById('library-load-modal'));
  modal.show();
}

/**
 * Show library management modal
 */
function showLibraryModal() {
  const configs = gridfinityLib.getAllConfigs();
  
  let html = '';
  
  if (configs.length === 0) {
    html = '<p class="text-muted">No saved configurations yet. Save one from any component tab!</p>';
  } else {
    const grouped = configs.reduce((acc, config) => {
      if (!acc[config.formId]) acc[config.formId] = [];
      acc[config.formId].push(config);
      return acc;
    }, {});

    html = Object.entries(grouped).map(([formId, formConfigs]) => `
      <div class="mb-4">
        <h6>${formId}</h6>
        <div class="list-group">
          ${formConfigs.map(config => `
            <div class="list-group-item d-flex justify-content-between align-items-center">
              <div>
                <strong>${escapeHtml(config.name)}</strong>
                <small class="text-muted d-block">${new Date(config.createdAt).toLocaleString()}</small>
              </div>
              <button class="btn btn-sm btn-danger" onclick="libraryDelete('${escapeHtml(config.id)}')">Delete</button>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('');
  }

  document.getElementById('library-all-list').innerHTML = html;
  document.getElementById('library-storage-info').textContent = 
    `Storage: ${(gridfinityLib.getStorageSize() / 1024).toFixed(1)} KB (${gridfinityLib.getStorageUsagePercent()}% of quota)`;

  const modal = new bootstrap.Modal(document.getElementById('library-manage-modal'));
  modal.show();
}

/**
 * Save configuration from modal
 */
function librarySaveConfig() {
  const formId = document.getElementById('save-form-id').value;
  const name = document.getElementById('save-config-name').value.trim();

  if (!name) {
    alert('Please enter a name for this configuration.');
    return;
  }

  try {
    gridfinityLib.saveConfig(formId, name);
    alert(`Configuration "${name}" saved!`);
    bootstrap.Modal.getInstance(document.getElementById('library-save-modal')).hide();
  } catch (e) {
    alert('Error saving configuration: ' + e.message);
  }
}

/**
 * Load configuration and close modal
 */
function libraryLoadAndClose(configId, formId) {
  try {
    gridfinityLib.loadConfig(configId, formId);
    bootstrap.Modal.getInstance(document.getElementById('library-load-modal')).hide();
    
    // Switch to the form tab if not already visible
    const tab = document.querySelector(`[href="#${formId}"]`);
    if (tab) {
      const tabInstance = new bootstrap.Tab(tab);
      tabInstance.show();
    }
  } catch (e) {
    alert('Error loading configuration: ' + e.message);
  }
}

/**
 * Delete configuration
 */
function libraryDelete(configId) {
  if (confirm('Delete this configuration?')) {
    gridfinityLib.deleteConfig(configId);
    alert('Configuration deleted.');
    // Refresh any open modals
    if (document.getElementById('library-manage-modal').classList.contains('show')) {
      showLibraryModal();
    }
    if (document.getElementById('library-load-modal').classList.contains('show')) {
      showLoadModal(document.getElementById('save-form-id').value);
    }
  }
}

/**
 * Export library as JSON file
 */
function libraryExport() {
  const json = gridfinityLib.exportLibrary();
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `gridfinitycreator-library-${new Date().toISOString().split('T')[0]}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Import library from JSON file
 */
function libraryImport() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'application/json';
  input.onchange = function(e) {
    const file = e.target.files[0];
    const reader = new FileReader();
    reader.onload = function(event) {
      try {
        gridfinityLib.importLibrary(event.target.result);
        alert('Library imported successfully!');
        if (document.getElementById('library-manage-modal').classList.contains('show')) {
          showLibraryModal();
        }
      } catch (e) {
        alert('Error importing library: ' + e.message);
      }
    };
    reader.readAsText(file);
  };
  input.click();
}

/**
 * Utility to escape HTML
 */
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
