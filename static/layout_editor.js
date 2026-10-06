/**
 * Gridfinity Creator - compartment layout editor
 *
 * Interactive top-down view of a bin's compartment grid. Interior divider
 * walls are drawn as clickable segments: click one to remove it (merging the
 * two adjacent cells into one compartment), click again to restore it.
 *
 * The removed segments are stored as JSON in the form's hidden removedWalls
 * field ([["v",i,j], ...]), so they travel with previews, downloads, share
 * links and the config library exactly like any other setting.
 */

const LAYOUT_EDITOR_MAX_W = 300;
const LAYOUT_EDITOR_MAX_H = 200;

function layoutEditorState(form) {
  const cX = Math.max(1, parseInt(form.elements['compartmentsX']?.value, 10) || 1);
  const cY = Math.max(1, parseInt(form.elements['compartmentsY']?.value, 10) || 1);

  let removed = [];
  try {
    removed = JSON.parse(form.elements['removedWalls'].value || '[]');
  } catch (e) {
    removed = [];
  }

  // Keep only well-formed, in-range segments (grid may have shrunk)
  removed = removed.filter(seg =>
    Array.isArray(seg) && seg.length === 3 &&
    Number.isInteger(seg[1]) && Number.isInteger(seg[2]) &&
    (seg[0] === 'v'
      ? seg[1] >= 1 && seg[1] < cX && seg[2] >= 0 && seg[2] < cY
      : seg[0] === 'h' && seg[2] >= 1 && seg[2] < cY && seg[1] >= 0 && seg[1] < cX)
  );

  return { cX, cY, removed };
}

/**
 * What a screen reader announces for a wall. Columns count from the left and rows from the
 * front of the bin (row 1 is nearest the viewer in the 3D preview), both from 1.
 */
function layoutSegmentLabel(kind, i, j) {
  if (kind === 'v') {
    return `Divider wall between column ${i} and column ${i + 1}, row ${j + 1}`;
  }
  return `Divider wall between row ${j} and row ${j + 1}, column ${i + 1}`;
}

/**
 * Which wall an arrow key moves to, among `count` walls in drawing order, or null for any other
 * key. The walls form one tab stop; the arrows move within it (otherwise an 8 x 8 layout would be
 * over a hundred tab stops).
 */
function layoutNextIndex(current, count, key) {
  if (!count) return null;
  switch (key) {
    case 'ArrowRight':
    case 'ArrowDown':
      return Math.min(count - 1, current + 1);
    case 'ArrowLeft':
    case 'ArrowUp':
      return Math.max(0, current - 1);
    case 'Home':
      return 0;
    case 'End':
      return count - 1;
    default:
      return null;
  }
}

function layoutEditorRender(formId) {
  const container = document.getElementById(`layout-editor-${formId}`);
  const form = document.getElementById(formId + '_form');
  if (!container || !form || !form.elements['removedWalls']) return;

  // Re-drawing replaces every element, so remember which wall had the keyboard focus
  const focusedSegment = container.contains(document.activeElement) ? document.activeElement.dataset.seg : null;

  const { cX, cY, removed } = layoutEditorState(form);
  const removedKeys = new Set(removed.map(s => s.join(',')));

  // Write the pruned list back so stale segments don't linger in the field
  form.elements['removedWalls'].value = removed.length ? JSON.stringify(removed) : '';

  const cell = Math.min(LAYOUT_EDITOR_MAX_W / cX, LAYOUT_EDITOR_MAX_H / cY, 56);
  const w = cX * cell;
  const h = cY * cell;
  const pad = 6;

  const svg = [];
  svg.push(`<svg viewBox="0 0 ${w + 2 * pad} ${h + 2 * pad}" width="${w + 2 * pad}" height="${h + 2 * pad}" ` +
    `role="group" aria-label="Compartment layout seen from above. Each divider wall can be removed to merge two compartments.">`);

  // Bin outline. Drawn to MATCH the 3D preview's orientation: model row 0 is
  // the front of the bin, which the preview shows nearest the viewer - so row
  // j=0 is at the BOTTOM of the editor and higher rows stack upward.
  svg.push(`<rect x="${pad}" y="${pad}" width="${w}" height="${h}" rx="8" class="gfg-layout-outline"/>`);

  // SVG y of the top edge of model row j (rows counted from the bottom)
  const rowTop = (j) => pad + (cY - 1 - j) * cell;

  const HIT = 14; // width of the invisible click target around each wall
  const seg = (kind, i, j, x1, y1, x2, y2) => {
    const key = `${kind},${i},${j}`;
    const isRemoved = removedKeys.has(key);
    const title = `<title>${isRemoved ? 'Click to restore this wall' : 'Click to remove this wall'}</title>`;
    // A wall is a checkbox: checked while it is there. Only one is a tab stop (see below)
    const semantics = `tabindex="-1" role="checkbox" aria-checked="${!isRemoved}" aria-label="${layoutSegmentLabel(kind, i, j)}"`;
    svg.push(
      `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" ` +
      `class="gfg-layout-wall${isRemoved ? ' removed' : ''}" data-seg="${key}"/>`
    );
    // A line has no area - overlay a transparent rect as the actual click target
    const rx = Math.min(x1, x2) - (x1 === x2 ? HIT / 2 : 0);
    const ry = Math.min(y1, y2) - (y1 === y2 ? HIT / 2 : 0);
    const rw = x1 === x2 ? HIT : Math.abs(x2 - x1);
    const rh = y1 === y2 ? HIT : Math.abs(y2 - y1);
    svg.push(
      `<rect x="${rx}" y="${ry}" width="${rw}" height="${rh}" ` +
      `class="gfg-layout-hit" data-seg="${key}" ${semantics}>${title}</rect>`
    );
  };

  // Vertical walls: between columns i-1 and i, one segment per row j
  for (let i = 1; i < cX; i++) {
    for (let j = 0; j < cY; j++) {
      const x = pad + i * cell;
      seg('v', i, j, x, rowTop(j) + 3, x, rowTop(j) + cell - 3);
    }
  }

  // Horizontal walls: between rows j-1 and j, one segment per column i.
  // The shared edge is the top of row j-1.
  for (let j = 1; j < cY; j++) {
    for (let i = 0; i < cX; i++) {
      const y = rowTop(j - 1);
      seg('h', i, j, pad + i * cell + 3, y, pad + (i + 1) * cell - 3, y);
    }
  }

  svg.push('</svg>');
  svg.push('<div class="gfg-layout-caption">front of bin</div>');
  container.innerHTML = svg.join('');

  const hits = [...container.querySelectorAll('.gfg-layout-hit')];

  // One tab stop for the whole editor: the wall that had the focus, else the first
  const stop = hits.find(hit => hit.dataset.seg === focusedSegment) || hits[0];
  if (stop) stop.setAttribute('tabindex', '0');
  if (focusedSegment && stop && stop.dataset.seg === focusedSegment) stop.focus();

  const toggle = hit => {
    const [kind, i, j] = hit.dataset.seg.split(',');
    layoutEditorToggle(formId, [kind, parseInt(i, 10), parseInt(j, 10)]);
  };

  hits.forEach((hit, index) => {
    hit.addEventListener('click', () => toggle(hit));
    hit.addEventListener('keydown', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        toggle(hit);
        return;
      }
      const next = layoutNextIndex(index, hits.length, event.key);
      if (next === null) return;
      event.preventDefault();
      hits.forEach(other => other.setAttribute('tabindex', '-1'));
      hits[next].setAttribute('tabindex', '0');
      hits[next].focus();
    });
    hit.addEventListener('mouseenter', () => {
      container.querySelector(`.gfg-layout-wall[data-seg="${hit.dataset.seg}"]`)?.classList.add('hover');
    });
    hit.addEventListener('mouseleave', () => {
      container.querySelector(`.gfg-layout-wall[data-seg="${hit.dataset.seg}"]`)?.classList.remove('hover');
    });
  });
}

function layoutEditorToggle(formId, segment) {
  const form = document.getElementById(formId + '_form');
  if (!form) return;

  const { removed } = layoutEditorState(form);
  const key = segment.join(',');
  const idx = removed.findIndex(s => s.join(',') === key);
  if (idx >= 0) {
    removed.splice(idx, 1);
  } else {
    removed.push(segment);
  }

  form.elements['removedWalls'].value = removed.length ? JSON.stringify(removed) : '';
  layoutEditorRender(formId);

  // Kick the normal change pipeline: debounced preview + dimensions refresh
  form.dispatchEvent(new Event('change', { bubbles: true }));
}

function layoutEditorInitAll() {
  document.querySelectorAll('[id^="layout-editor-"]').forEach(container => {
    const formId = container.id.replace('layout-editor-', '');
    const form = document.getElementById(formId + '_form');
    if (!form) return;

    layoutEditorRender(formId);

    // Re-render when anything in the form changes (compartment counts edited,
    // saved config loaded, shared link applied, ...)
    form.addEventListener('change', () => layoutEditorRender(formId));
  });

  // Shared links populate forms without firing change events - re-render
  // whichever editor's tab becomes visible
  document.addEventListener('shown.bs.tab', () => {
    document.querySelectorAll('[id^="layout-editor-"]').forEach(container => {
      layoutEditorRender(container.id.replace('layout-editor-', ''));
    });
  });
}

if (typeof module === 'object' && module.exports) {
  module.exports = { layoutSegmentLabel, layoutNextIndex }; // Node, for the tests
} else if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', layoutEditorInitAll);
} else {
  layoutEditorInitAll();
}
