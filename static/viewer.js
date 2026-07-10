/**
 * Gridfinity Creator - 3D Preview Viewer
 * Uses Three.js to display STL models with camera controls
 */

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
    console.log(`Initializing viewer for ${containerId}`);
    this.init();
  }

  init() {
    try {
      // Scene setup
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0xffffff);

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

      // Lighting
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
      this.scene.add(ambientLight);

      const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
      directionalLight.position.set(100, 100, 100);
      this.scene.add(directionalLight);

      // Grid
      this.addGrid();

      // Camera controls
      this.setupControls();

      // Handle window resize
      window.addEventListener('resize', () => this.onWindowResize());

      // Start render loop
      this.animate();
      
      console.log(`Viewer initialized successfully for ${this.container.id}`);
    } catch (e) {
      console.error('Error initializing viewer:', e);
    }
  }

  addGrid() {
    const size = 300;
    const divisions = 10;
    const gridHelper = new THREE.GridHelper(size, divisions, 0x5588dd, 0x8bb0e8);
    gridHelper.position.y = 0;
    this.scene.add(gridHelper);
  }

  setupControls() {
    // Simple orbit controls using mouse events
    this.isDragging = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.rotation = { x: 0, y: 0 };

    this.renderer.domElement.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    this.renderer.domElement.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        const deltaX = e.clientX - this.previousMousePosition.x;
        const deltaY = e.clientY - this.previousMousePosition.y;

        this.rotation.y += deltaX * 0.01;
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
      const direction = this.camera.position.clone().normalize();
      const distance = this.camera.position.length();
      const newDistance = distance + (e.deltaY > 0 ? zoomSpeed * 10 : -zoomSpeed * 10);

      if (newDistance > 50 && newDistance < 500) {
        this.camera.position.copy(direction.multiplyScalar(newDistance));
      }
    }, { passive: false });
  }

  updateCameraPosition() {
    const distance = 200;
    this.camera.position.x = distance * Math.sin(this.rotation.y) * Math.cos(this.rotation.x);
    this.camera.position.y = distance * Math.sin(this.rotation.x);
    this.camera.position.z = distance * Math.cos(this.rotation.y) * Math.cos(this.rotation.x);
    this.camera.lookAt(0, 0, 0);
  }

  loadSTL(arrayBuffer) {
    // Remove existing model
    if (this.model) {
      this.scene.remove(this.model);
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
      this.scene.add(this.model);

      this.fitCameraToModel();
      console.log('STL model loaded successfully');
    } catch (error) {
      console.error('Error parsing STL preview:', error);
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

    this.camera.position.z = cameraZ;
    this.camera.lookAt(center);
    this.scene.position.copy(center).multiplyScalar(-1);
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
    requestAnimationFrame(() => this.animate());
    this.renderer.render(this.scene, this.camera);
  }
}

// Global viewers indexed by form ID
const viewers = {};

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
 * Generate and display preview for a form
 */
async function generatePreview(formId) {
  const viewer = viewers[formId];
  if (!viewer) {
    console.warn(`Viewer not initialized for ${formId}`);
    return;
  }

  const formElement = document.getElementById(formId + '_form');
  if (!formElement) {
    console.warn(`Form ${formId}_form not found`);
    return;
  }

  const formData = new FormData(formElement);
  formData.append('preview', 'true');
  formData.append(formId, 'Generate');

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
