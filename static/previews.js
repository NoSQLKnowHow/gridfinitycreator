/**
 * Gridfinity Creator - set up the 3D preview areas of the generator tabs.
 *
 * (This used to be an inline script in index.html.j2; the Content-Security-Policy the server
 * sends allows scripts from this server only.)
 */
// Wire up the 3D preview areas. No viewer is created up front: the preview
// is off by default and only loads when the user opts in (toggle) or hovers
// over a preview area. The dimensions readout always refreshes either way.
function initializeAllViewers() {
  const enabled = isPreviewEnabled();
  document.querySelectorAll('.preview-toggle-input').forEach(cb => { cb.checked = enabled; });

  document.querySelectorAll('.viewer-container').forEach(container => {
    const formId = container.id.replace('viewer-', '');
    if (!formId) return;

    try {
      // Load this one preview on demand, even while the setting is off.
      // Clicking loads immediately; hovering loads after a brief pause so
      // that merely sweeping the mouse across the panel doesn't trigger it.
      const placeholder = document.getElementById(`viewer-placeholder-${formId}`);
      let hoverTimer = null;

      const loadNow = () => {
        if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null; }
        if (!viewers[formId]) activateViewer(formId);
      };

      container.addEventListener('mouseenter', () => {
        if (viewers[formId] || hoverTimer) return;
        hoverTimer = setTimeout(() => {
          hoverTimer = null;
          if (!viewers[formId]) activateViewer(formId);
        }, 500);
      });
      container.addEventListener('mouseleave', () => {
        if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null; }
      });

      if (placeholder) {
        placeholder.addEventListener('click', loadNow);
        placeholder.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            loadNow();
          }
        });
      }

      const tabButton = document.querySelector(`[data-bs-toggle="tab"][data-bs-target="#${formId}"]`);
      if (tabButton) {
        tabButton.addEventListener('shown.bs.tab', function() {
          // Only the visible tab needs to render
          pauseHiddenViewers(formId);

          if (isPreviewEnabled() || viewers[formId]) {
            activateViewer(formId);
          } else {
            updateDimensions(formId);
          }
        });
      }

      if (container.closest('.tab-pane.active')) {
        setTimeout(() => {
          if (isPreviewEnabled()) {
            activateViewer(formId);
          } else {
            updateDimensions(formId);
          }
        }, 100);
      }
    } catch (e) {
      console.error(`Failed to set up preview for ${formId}:`, e);
    }
  });
}

// Start initialization when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeAllViewers);
} else {
  initializeAllViewers();
}
