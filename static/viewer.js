/**
 * Gridfinity Creator - 3D Preview Viewer
 * Uses Three.js to display STL models with camera controls
 */

// Colors the 3D viewer uses per theme - kept in sync with the CSS custom
// properties in static/theme.css, but Three.js needs actual hex values.
const GFG_VIEWER_THEME_COLORS = {
  light: { background: 0xf2f4fb, gridMain: 0x4f46e5, gridSub: 0xd4daf0, edge: 0x0b3d91 },
  dark: { background: 0x1a2136, gridMain: 0x818cf8, gridSub: 0x353f61, edge: 0x0a1024 },
};

function gfgViewerTheme() {
  return document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
}

// Wait for Three.js to load
function waitForThree(callback, attempts = 0) {
  if (typeof THREE !== 'undefined') {
    callback();
  } else if (attempts < 50) {
    setTimeout(() => waitForThree(callback, attempts + 1), 100);
  } else {
    console.error('Three.js failed to load');
  }
}

class GridfinityViewer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      console.error(`Container ${containerId} not found`);
      return;
    }
    
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.model = null;
    this.gridHelper = null;
    this.orbitTarget = new THREE.Vector3(0, 0, 0);
    this.orbitDistance = 200;
    console.log(`Initializing viewer for ${containerId}`);
    this.init();

    document.addEventListener('gfg-theme-change', () => this.applyTheme());
  }

  init() {
    try {
      // Scene setup
      this.scene = new THREE.Scene();

      // Camera setup
      let width = this.container.clientWidth || this.container.offsetWidth;
      let height = this.container.clientHeight || this.container.offsetHeight;
      if (width === 0 || height === 0) {
        width = Math.max(1, this.container.offsetWidth || 600);
        height = Math.max(1, this.container.offsetHeight || 400);
      }
      console.log(`Viewer size: ${width}x${height}`);
      
      this.camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
      this.camera.position.set(150, 150, 150);

      // Renderer setup
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      this.renderer.setSize(width, height);
      this.renderer.setPixelRatio(window.devicePixelRatio);
      this.container.appendChild(this.renderer.domElement);

      // Lighting. Keep the ambient term low - a high ambient washes out the
      // shading differences that make recesses readable - and light from
      // several directions so the model stays legible at any orbit angle.
      this.scene.add(new THREE.AmbientLight(0xffffff, 0.42));

      const keyLight = new THREE.DirectionalLight(0xffffff, 0.6);
      keyLight.position.set(120, 200, 120);
      this.scene.add(keyLight);

      const fillLight = new THREE.DirectionalLight(0xffffff, 0.32);
      fillLight.position.set(-150, 90, -110);
      this.scene.add(fillLight);

      const rimLight = new THREE.DirectionalLight(0xffffff, 0.22);
      rimLight.position.set(0, -130, 70);
      this.scene.add(rimLight);

      // Background and grid, matching the current light/dark theme
      this.applyTheme();

      // Camera controls
      this.setupControls();

      // Handle window resize
      window.addEventListener('resize', () => this.onWindowResize());

      // Start render loop
      this.running = true;
      this.animate();
      
      console.log(`Viewer initialized successfully for ${this.container.id}`);
    } catch (e) {
      console.error('Error initializing viewer:', e);
    }
  }

  applyTheme() {
    if (!this.scene) return;

    const colors = GFG_VIEWER_THEME_COLORS[gfgViewerTheme()];
    this.scene.background = new THREE.Color(colors.background);

    // GridHelper bakes both line colors into its vertex colors at construction
    // time, so the only way to re-theme it is to rebuild it.
    if (this.gridHelper) {
      this.scene.remove(this.gridHelper);
      this.gridHelper.geometry.dispose();
      this.gridHelper.material.dispose();
    }

    this.gridHelper = new THREE.GridHelper(300, 10, colors.gridMain, colors.gridSub);
    this.gridHelper.position.y = 0;
    this.scene.add(this.gridHelper);

    if (this.edgeLines) {
      this.edgeLines.material.color.setHex(colors.edge);
    }
  }

  setupControls() {
    // Simple orbit controls using mouse events
    this.isDragging = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.rotation = { x: Math.PI / 6, y: Math.PI / 4 };

    this.renderer.domElement.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    this.renderer.domElement.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        const deltaX = e.clientX - this.previousMousePosition.x;
        const deltaY = e.clientY - this.previousMousePosition.y;

        // Invert horizontal rotation so moving mouse right rotates view right
        this.rotation.y -= deltaX * 0.01;
        this.rotation.x += deltaY * 0.01;

        // Limit pitch
        this.rotation.x = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, this.rotation.x));

        this.updateCameraPosition();
        this.previousMousePosition = { x: e.clientX, y: e.clientY };
      }
    });

    this.renderer.domElement.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    this.renderer.domElement.addEventListener('mouseleave', () => {
      this.isDragging = false;
    });

    // Zoom with mouse wheel
    this.renderer.domElement.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomSpeed = 0.1;
      const newDistance = this.orbitDistance + (e.deltaY > 0 ? zoomSpeed * 10 : -zoomSpeed * 10);

      if (newDistance > 50 && newDistance < 500) {
        this.orbitDistance = newDistance;
        this.updateCameraPosition();
      }
    }, { passive: false });
  }

  updateCameraPosition() {
    const distance = this.orbitDistance;
    this.camera.position.x = this.orbitTarget.x + distance * Math.sin(this.rotation.y) * Math.cos(this.rotation.x);
    this.camera.position.y = this.orbitTarget.y + distance * Math.sin(this.rotation.x);
    this.camera.position.z = this.orbitTarget.z + distance * Math.cos(this.rotation.y) * Math.cos(this.rotation.x);
    this.camera.lookAt(this.orbitTarget);
  }

  loadSTL(arrayBuffer) {
    // Remove existing model, releasing its GPU buffers (previews regenerate on
    // every settings change, so leaking these adds up quickly)
    if (this.model) {
      this.scene.remove(this.model);
      this.model.geometry.dispose();
      this.model.material.dispose();
      if (this.edgeLines) {
        this.edgeLines.geometry.dispose();
        this.edgeLines.material.dispose();
        this.edgeLines = null;
      }
    }

    if (!arrayBuffer || arrayBuffer.byteLength < 84) {
      console.error('STL preview too small or invalid:', arrayBuffer && arrayBuffer.byteLength);
      return;
    }

    try {
      const geometry = this.parseSTL(arrayBuffer);
      geometry.computeVertexNormals();
      geometry.center();

      const material = new THREE.MeshPhongMaterial({ color: 0x2196f3, shininess: 100 });
      this.model = new THREE.Mesh(geometry, material);

      // Outline the model's sharp feature edges. A flat-bottomed recess (square
      // or hexagonal hole, weight pocket, ...) has the same surface normal as
      // the face it was cut into, so lighting alone renders it nearly invisible.
      // Drawing the feature edges makes every cut read clearly at any angle.
      this.edgeLines = new THREE.LineSegments(
        new THREE.EdgesGeometry(geometry, 25),
        new THREE.LineBasicMaterial({ color: GFG_VIEWER_THEME_COLORS[gfgViewerTheme()].edge })
      );
      this.model.add(this.edgeLines);

      this.scene.add(this.model);

      this.alignModelFlat();
      this.fitCameraToModel();
      console.log('STL model loaded successfully');
    } catch (error) {
      console.error('Error parsing STL preview:', error);
    }
  }

  alignModelFlat() {
    if (!this.model) {
      return;
    }

    // Layout model onto the ground plane.
    // Rotate so the original vertical axis lies flat and keep the model above the grid.
    // Reset transforms so bounding box is computed from a clean state
    this.model.rotation.set(0, 0, 0);
    this.model.position.set(0, 0, 0);
    this.model.updateMatrixWorld(true);

    // Rotate so the model lies flat (rotate X -90deg)
    this.model.rotation.x = -Math.PI / 2;
    this.model.updateMatrixWorld(true);

    // Recompute bounds after rotation and raise the mesh so it sits on Y=0.
    const box = new THREE.Box3().setFromObject(this.model);
    const minY = box.min.y;
    if (Number.isFinite(minY)) {
      this.model.position.y -= minY;
    }
  }

  parseSTL(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    const isASCII = this.isASCIISTL(arrayBuffer);

    if (isASCII) {
      return this.parseASCIISTL(new TextDecoder().decode(arrayBuffer));
    } else {
      return this.parseBinarySTL(view);
    }
  }

  isASCIISTL(arrayBuffer) {
    const header = new TextDecoder().decode(new Uint8Array(arrayBuffer, 0, Math.min(5, arrayBuffer.byteLength)));
    if (header.toLowerCase() !== 'solid') {
      return false;
    }

    const textSample = new TextDecoder('utf-8', { fatal: false }).decode(new Uint8Array(arrayBuffer, 0, Math.min(2048, arrayBuffer.byteLength)));
    return /facet\s+normal/i.test(textSample) && /vertex\s+/i.test(textSample);
  }

  parseBinarySTL(view) {
    const byteLength = view.byteLength;
    if (byteLength < 84) {
      throw new Error(`Binary STL too short for header: ${byteLength}`);
    }

    const faces = view.getUint32(80, true);
    if (!Number.isFinite(faces) || faces < 0 || faces > 2000000) {
      throw new Error(`Binary STL face count invalid: ${faces}`);
    }

    const expectedLength = 84 + faces * 50;
    if (expectedLength > 200 * 1024 * 1024) {
      throw new Error(`Binary STL expected size too large: ${expectedLength} bytes for ${faces} faces`);
    }
    if (byteLength < expectedLength) {
      throw new Error(`Binary STL size mismatch: ${byteLength} bytes but expected ${expectedLength} for ${faces} faces`);
    }

    const geometry = new THREE.BufferGeometry();
    const vertices = [];
    const normals = [];

    let offset = 84;
    for (let i = 0; i < faces; i++) {
      const nx = view.getFloat32(offset, true);
      offset += 4;
      const ny = view.getFloat32(offset, true);
      offset += 4;
      const nz = view.getFloat32(offset, true);
      offset += 4;

      for (let j = 0; j < 3; j++) {
        vertices.push(view.getFloat32(offset, true));
        offset += 4;
        vertices.push(view.getFloat32(offset, true));
        offset += 4;
        vertices.push(view.getFloat32(offset, true));
        offset += 4;

        normals.push(nx, ny, nz);
      }

      offset += 2; // attribute byte count
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertices), 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(normals), 3));

    return geometry;
  }

  parseASCIISTL(text) {
    const geometry = new THREE.BufferGeometry();
    const vertices = [];
    const normals = [];

    const vertexPattern = /vertex\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/g;
    const normalPattern = /facet\s+normal\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/g;

    let normalMatch;
    let currentNormal = [0, 0, 1];

    while ((normalMatch = normalPattern.exec(text)) !== null) {
      currentNormal = [parseFloat(normalMatch[1]), parseFloat(normalMatch[3]), parseFloat(normalMatch[5])];

      const normalStart = text.lastIndexOf('facet', normalMatch.index) + normalMatch[0].length;
      const normalEnd = text.indexOf('endfacet', normalStart);
      const facetText = text.substring(normalStart, normalEnd);

      let vertexMatch;
      const vertexPattern2 = /vertex\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)\s+([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/g;
      while ((vertexMatch = vertexPattern2.exec(facetText)) !== null) {
        vertices.push(parseFloat(vertexMatch[1]), parseFloat(vertexMatch[3]), parseFloat(vertexMatch[5]));
        normals.push(currentNormal[0], currentNormal[1], currentNormal[2]);
      }
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertices), 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(normals), 3));

    return geometry;
  }

  fitCameraToModel() {
    if (!this.model) return;

    const box = new THREE.Box3().setFromObject(this.model);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = this.camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));

    cameraZ *= 1.5;

    // Keep the scene (and grid) fixed in world space - the model already rests on Y=0
    // via alignModelFlat(). Orbit around the model's actual center/distance instead of a
    // separate, disconnected set of values, so dragging never "snaps" the view.
    this.orbitTarget.copy(center);
    this.orbitDistance = cameraZ;
    this.updateCameraPosition();
  }

  onWindowResize() {
    let width = this.container.clientWidth || this.container.offsetWidth;
    let height = this.container.clientHeight || this.container.offsetHeight;
    if (width === 0 || height === 0) {
      return;
    }

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  animate() {
    // The render loop is the viewer's real cost - bail out entirely when
    // paused/disposed rather than scheduling another frame
    if (!this.running) return;
    requestAnimationFrame(() => this.animate());
    this.renderer.render(this.scene, this.camera);
  }

  pause() {
    this.running = false;
  }

  resume() {
    if (this.running || !this.renderer) return;
    this.running = true;
    this.animate();
  }

  /** Release the WebGL context and all GPU resources */
  dispose() {
    this.running = false;

    if (this.model) {
      this.model.geometry.dispose();
      this.model.material.dispose();
      this.scene.remove(this.model);
      this.model = null;
    }
    if (this.edgeLines) {
      this.edgeLines.geometry.dispose();
      this.edgeLines.material.dispose();
      this.edgeLines = null;
    }
    if (this.gridHelper) {
      this.gridHelper.geometry.dispose();
      this.gridHelper.material.dispose();
      this.gridHelper = null;
    }
    if (this.renderer) {
      this.renderer.dispose();
      const canvas = this.renderer.domElement;
      if (canvas && canvas.parentNode) {
        canvas.parentNode.removeChild(canvas);
      }
      this.renderer = null;
    }
    this.scene = null;
  }
}

// Global viewers indexed by form ID
const viewers = {};

/**
 * 3D preview enable/disable.
 *
 * The preview is OFF by default: each viewer holds a WebGL context and runs a
 * requestAnimationFrame loop, which is a real cost on lower-powered machines.
 * Nothing is created until the user opts in - either with the toggle in the
 * preview card header, or simply by hovering the preview area, which loads
 * that one viewer on demand.
 */
const GFG_PREVIEW_STORAGE_KEY = 'gfg-3d-preview';

function isPreviewEnabled() {
  try {
    return localStorage.getItem(GFG_PREVIEW_STORAGE_KEY) === 'on';
  } catch (e) {
    return false;
  }
}

/**
 * Record that the preview is now on and sync every tab's toggle. Called for
 * any activation route - the toggle, a click, or a hover - so the switch always
 * reflects the actual state of the viewer.
 */
function markPreviewEnabled() {
  try {
    localStorage.setItem(GFG_PREVIEW_STORAGE_KEY, 'on');
  } catch (e) {
    // Storage may be unavailable; the preference just won't persist
  }
  document.querySelectorAll('.preview-toggle-input').forEach(cb => { cb.checked = true; });
}

function setPreviewEnabled(enabled) {
  if (enabled) {
    markPreviewEnabled();
    const active = document.querySelector('.tab-pane.active .viewer-container');
    if (active) {
      activateViewer(active.id.replace('viewer-', ''));
    }
    return;
  }

  try {
    localStorage.setItem(GFG_PREVIEW_STORAGE_KEY, 'off');
  } catch (e) {
    // Storage may be unavailable; the preference just won't persist
  }
  document.querySelectorAll('.preview-toggle-input').forEach(cb => { cb.checked = false; });
  Object.keys(viewers).forEach(teardownViewer);
}

/**
 * Placeholder state: 'idle' (invitation to load), 'loading' (spinner - the
 * model takes a few seconds to build, so this is what tells the user their
 * hover/click registered) or 'hidden' (model is on screen).
 */
function setPlaceholderState(formId, state) {
  const placeholder = document.getElementById(`viewer-placeholder-${formId}`);
  if (!placeholder) return;
  placeholder.style.display = state === 'hidden' ? 'none' : '';
  placeholder.classList.toggle('loading', state === 'loading');
}

function setPlaceholderVisible(formId, visible) {
  setPlaceholderState(formId, visible ? 'idle' : 'hidden');
}

/** Create (if needed) and render the viewer for one form */
function activateViewer(formId) {
  const container = document.getElementById(`viewer-${formId}`);
  if (!container) return null;

  if (!viewers[formId]) {
    // Keep the placeholder up, showing a spinner, until the model actually
    // arrives - hiding it right away leaves a blank panel that reads as
    // "nothing happened" while the geometry is still being generated.
    setPlaceholderState(formId, 'loading');
    const viewer = new GridfinityViewer(`viewer-${formId}`);
    if (!viewer.renderer) {
      // WebGL unavailable or init failed - put the invitation back
      setPlaceholderState(formId, 'idle');
      return null;
    }
    viewers[formId] = viewer;
  }

  // However the preview got loaded - toggle, click or hover - it is on now,
  // so keep the stored setting and every tab's switch in step with reality
  markPreviewEnabled();

  viewers[formId].resume();
  viewers[formId].onWindowResize();
  generatePreview(formId);
  return viewers[formId];
}

/** Tear a viewer down, freeing its WebGL context */
function teardownViewer(formId) {
  const viewer = viewers[formId];
  if (!viewer) return;
  viewer.dispose();
  delete viewers[formId];
  setPlaceholderVisible(formId, true);
}

/** Pause every viewer except the given one (only one tab is ever visible) */
function pauseHiddenViewers(exceptFormId) {
  Object.keys(viewers).forEach(id => {
    if (id !== exceptFormId) viewers[id].pause();
  });
}

/**
 * Initialize a viewer for a specific form
 */
function initializeViewer(formId) {
  const containerId = `viewer-${formId}`;
  if (!document.getElementById(containerId)) {
    console.warn(`Container ${containerId} not found`);
    return;
  }
  
  if (!viewers[formId]) {
    console.log(`Creating new viewer for ${formId}`);
    viewers[formId] = new GridfinityViewer(containerId);
  }
  return viewers[formId];
}

/**
 * Fetch and render the real-world dimensions readout for a form
 */
async function updateDimensions(formId) {
  const panel = document.getElementById(`dimensions-${formId}`);
  const formElement = document.getElementById(formId + '_form');
  if (!panel || !formElement) return;

  const formData = new FormData(formElement);
  formData.append('dimensions', 'true');
  formData.append(formId, 'Generate');

  try {
    const response = await fetch('/', { method: 'POST', body: formData });
    if (!response.ok) return;

    const sections = await response.json();
    if (!Array.isArray(sections)) return;

    panel.innerHTML = sections.map(section => `
      <div class="gfg-dims-section">
        <div class="gfg-dims-title">${escapeHtml(section.title)}</div>
        ${section.rows.map(([label, value]) => `
          <div class="gfg-dims-row">
            <span class="gfg-dims-label">${escapeHtml(label)}</span>
            <span class="gfg-dims-value">${escapeHtml(value)}</span>
          </div>
        `).join('')}
      </div>
    `).join('');
  } catch (e) {
    console.warn('Dimensions update failed:', e);
  }
}

/**
 * Generate and display preview for a form
 */
async function generatePreview(formId) {
  // Refresh the dimensions readout alongside the preview (cheap, not awaited)
  updateDimensions(formId);

  // With the preview off there is nothing to draw into - skip the STL request
  // entirely so neither the browser nor the server does the work. The
  // dimensions readout above still refreshes.
  const viewer = viewers[formId];
  if (!viewer) return;

  const formElement = document.getElementById(formId + '_form');
  if (!formElement) {
    console.warn(`Form ${formId}_form not found`);
    return;
  }

  const formData = new FormData(formElement);
  formData.append('preview', 'true');
  formData.append(formId, 'Generate');
  // Force preview generation to always produce STL regardless of exportFormat field
  try {
    formData.set('exportFormat', 'stl');
  } catch (e) {
    // ignore if set unsupported in some browsers
  }

  try {
    console.log(`Generating preview for ${formId}...`);
    const response = await fetch('/', {
      method: 'POST',
      body: formData
    });

    if (response.ok) {
      const blob = await response.blob();
      const arrayBuffer = await blob.arrayBuffer();
      const previewHeader = new TextDecoder('utf-8', { fatal: false }).decode(new Uint8Array(arrayBuffer, 0, Math.min(256, arrayBuffer.byteLength)));

      if (/<\/?html|<!doctype|<body|<title|error|exception/i.test(previewHeader)) {
        console.error('Preview response looks like HTML/error page:', previewHeader.slice(0, 256));
        return;
      }

      if (arrayBuffer.byteLength < 84 && !/solid/i.test(previewHeader)) {
        console.error('Preview response too small for STL:', arrayBuffer.byteLength, previewHeader.slice(0, 256));
        return;
      }

      console.log(`Received preview data: ${blob.size} bytes, type=${blob.type}`);
      viewer.loadSTL(arrayBuffer);
    } else {
      const errorText = await response.text();
      console.error('Preview generation failed:', response.status, response.statusText, errorText.slice(0, 500));
    }
  } catch (error) {
    console.error('Preview generation error:', error);
  } finally {
    // Reveal the model once it is actually on screen; if nothing loaded, put
    // the invitation back so the user can retry rather than face a blank panel
    setPlaceholderState(formId, viewer.model ? 'hidden' : 'idle');
  }
}

/**
 * Debounce preview generation to avoid too many requests
 */
function debouncePreview(formId, delay = 500) {
  if (window.previewTimeouts) {
    clearTimeout(window.previewTimeouts[formId]);
  } else {
    window.previewTimeouts = {};
  }

  window.previewTimeouts[formId] = setTimeout(() => {
    generatePreview(formId);
  }, delay);
}

// Wait for Three.js and then log ready
waitForThree(() => {
  console.log('Three.js loaded and ready');
});
