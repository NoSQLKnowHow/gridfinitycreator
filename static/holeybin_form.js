/**
 * Gridfinity Creator - Holey bin: the number of holes and the size of the bin depend on each other.
 * Whichever the user changed last is what the other follows: change the number of holes and the bin
 * grows to fit them, change the bin size and as many holes as fit are laid out.
 *
 * (This used to be an inline script in the settings form; the Content-Security-Policy the server
 * sends allows scripts from this server only. The form names what a field does in data-change.)
 *
 * The numbers below are those of the standard grid: 42 mm pitch, 1.9 mm walls, 0.5 mm clearance.
 * They do not follow a custom grid, as they did not before.
 */
(function () {
  'use strict';

  let binSizeLeading = false;

  function recalculate(form) {
    const elements = form.elements;
    const keepoutDiameter = elements['keepoutDiameter'].value;

    if (binSizeLeading) {
      // The bin size was changed: recalculate the number of holes that fit
      const sizeUnitsX = elements['sizeUnitsX'].value;
      const sizeUnitsY = elements['sizeUnitsY'].value;

      elements['numHolesX'].value = Math.floor((sizeUnitsX * 42.0 - 2.0 * 1.9 - 0.5) / keepoutDiameter);
      elements['numHolesY'].value = Math.floor((sizeUnitsY * 42.0 - 2.0 * 1.9 - 0.5) / keepoutDiameter);
    } else {
      // The number of holes was changed: recalculate the bin size that is needed
      const numHolesX = elements['numHolesX'].value;
      const numHolesY = elements['numHolesY'].value;

      elements['sizeUnitsX'].value = Math.ceil((numHolesX * keepoutDiameter + 2.0 * 1.9 + 0.5) / 42.0);
      elements['sizeUnitsY'].value = Math.ceil((numHolesY * keepoutDiameter + 2.0 * 1.9 + 0.5) / 42.0);
    }
  }

  const CHANGE_ACTIONS = {
    'num-holes-changed': form => { binSizeLeading = false; recalculate(form); },
    'bin-size-changed': form => { binSizeLeading = true; recalculate(form); },
    'hole-size-changed': form => { binSizeLeading = false; recalculate(form); }
  };

  document.addEventListener('change', event => {
    const field = event.target;
    const action = field.dataset && CHANGE_ACTIONS[field.dataset.change];
    if (action && field.form) action(field.form);
  });
})();
