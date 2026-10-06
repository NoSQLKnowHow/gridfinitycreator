/**
 * Gridfinity Creator - the page's own behaviour: the help dialog, the grid presets, and the
 * buttons and fields that used to carry onclick="..." and onchange="..." attributes.
 *
 * None of this is inline in the HTML. The Content-Security-Policy the server sends allows
 * scripts from this server only, so inline <script> blocks and event-handler attributes would
 * be refused. A button names what it does in data-action (and the generator it concerns in
 * data-form), and one listener on the document does the rest.
 */
(function () {
  'use strict';

  // What a click on [data-action] does
  const CLICK_ACTIONS = {
    'open-library': () => showLibraryModal(),
    'share-config': (button) => shareConfigLink(button.dataset.form, button),
    'save-config-dialog': (button) => showSaveModal(button.dataset.form),
    'load-config-dialog': (button) => showLoadModal(button.dataset.form),
    'save-config': () => librarySaveConfig(),
    'export-library': () => libraryExport(),
    'import-library': () => libraryImport()
  };

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    const action = button && CLICK_ACTIONS[button.dataset.action];
    if (action) action(button);
  });

  // Changes: a generator's form refreshes its preview, and the preview switch is remembered.
  // (A form names itself in data-preview-form.)
  document.addEventListener('change', event => {
    if (event.target.matches('.preview-toggle-input')) {
      setPreviewEnabled(event.target.checked);
    }
    const form = event.target.closest('form[data-preview-form]');
    if (form) debouncePreview(form.dataset.previewForm);
  });

  // The "?" buttons open the help dialog with the text of the (hidden) block they name
  document.body.addEventListener('click', event => {
    const helpButton = event.target.closest('.help-button');
    if (!helpButton) {
      return;
    }

    const sourceModalElement = document.getElementById('help-modal');
    const sourceModal = bootstrap.Modal.getOrCreateInstance(sourceModalElement);
    const helpSource = document.getElementById(helpButton.dataset.helpTarget);
    let helpText = helpSource ? helpSource.innerHTML : "";

    if (helpText === "") {
      helpText = "There is no extra information available for this field"
    }

    document.getElementById('help-modal-text').innerHTML = helpText

    // Bootstrap returns focus to the opener only for modals opened by data-bs-toggle;
    // this one is opened from here, so a keyboard user would otherwise be left at the top of the page
    sourceModalElement.addEventListener('hidden.bs.modal', () => helpButton.focus(), { once: true });
    sourceModal.show();
  }, false);

  window.addEventListener('load', () => {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
  });

  // Fill the grid fields from the chosen preset. The numbers live in gridspec.PRESETS and
  // arrive as data attributes; "Custom" carries none and leaves the fields alone.
  const presets = document.getElementById('grid-presets');
  if (presets) {
    presets.addEventListener('change', () => {
      const option = presets.querySelector('option:checked');
      if (!option || option.dataset.x === undefined) return;
      document.getElementById("gridSizeX").value = option.dataset.x;
      document.getElementById("gridSizeY").value = option.dataset.y;
      document.getElementById("gridSizeZ").value = option.dataset.z;
    });
  }
})();
