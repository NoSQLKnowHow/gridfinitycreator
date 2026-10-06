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

function layoutEditorRender(formId) {
  const container = document.getElementById(`layout-editor-${formId}`);
  const form = document.getElementById(formId + '_form');
  if (!container || !form || !form.elements['removedWalls']) return;

  const { cX, cY, removed } = layoutEditorState(form);
  const removedKeys = new Set(removed.map(s => s.join(',')));

  // Write the pruned list back so stale segments don't linger in the field
  form.elements['removedWalls'].value = removed.length ? JSON.stringify(removed) : '';

  const cell = Math.min(LAYOUT_EDITOR_MAX_W / cX, LAYOUT_EDITOR_MAX_H / cY, 56);
  const w = cX * cell;
  const h = cY * cell;
  const pad = 6;

  const svg = [];
  svg.push(`<svg viewBox="0 0 ${w + 2 * pad} ${h + 2 * pad}" width="${w + 2 * pad}" height="${h + 2 * pad}" role="img">`);

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
      `class="gfg-layout-hit" data-seg="${key}">${title}</rect>`
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

  container.querySelectorAll('.gfg-layout-hit').forEach(hit => {
    hit.addEventListener('click', () => {
      const [kind, i, j] = hit.dataset.seg.split(',');
      layoutEditorToggle(formId, [kind, parseInt(i, 10), parseInt(j, 10)]);
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

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', layoutEditorInitAll);
} else {
  layoutEditorInitAll();
}
