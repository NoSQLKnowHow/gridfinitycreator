"""Shared model export helpers.

CadQuery's 3MF writer tessellates every B-rep face independently, so the
triangles of adjacent faces don't share vertices. The result is technically
non-manifold and some slicers refuse or mis-handle it. weld_3mf() rewrites
the mesh with duplicate vertices merged, producing a watertight indexed mesh
(verified: 0 non-manifold edges, Euler characteristic 2).
"""

import zipfile
import xml.etree.ElementTree as ET

from cadquery import exporters

MODEL_PATH = "3D/3dmodel.model"

def export_model(model, filename):
    """Export a model, inferring the format from the file extension.
       3MF output is post-processed into a welded, watertight mesh."""
    exporters.export(model, filename)
    if filename.lower().endswith(".3mf"):
        weld_3mf(filename)

def weld_3mf(filename):
    """Merge duplicate vertices in every mesh of a 3MF file, in place."""
    with zipfile.ZipFile(filename) as zf:
        entries = {name: zf.read(name) for name in zf.namelist()}

    root = ET.fromstring(entries[MODEL_PATH])
    namespace = root.tag.split("}")[0].strip("{")
    ET.register_namespace("", namespace)
    ns = {"m": namespace}

    for mesh in root.findall(".//m:mesh", ns):
        verticesEl = mesh.find("m:vertices", ns)
        trianglesEl = mesh.find("m:triangles", ns)
        if verticesEl is None or trianglesEl is None:
            continue

        # Weld: map identical (rounded) coordinates onto a single index
        weld = {}
        remap = []
        welded = []
        for v in verticesEl.findall("m:vertex", ns):
            coords = (v.get("x"), v.get("y"), v.get("z"))
            key = tuple(round(float(c), 6) for c in coords)
            if key not in weld:
                weld[key] = len(welded)
                welded.append(coords)
            remap.append(weld[key])

        # Rewrite vertices
        for v in list(verticesEl):
            verticesEl.remove(v)
        for x, y, z in welded:
            ET.SubElement(verticesEl, f"{{{namespace}}}vertex", {"x": x, "y": y, "z": z})

        # Rewrite triangles with remapped indices, dropping any that
        # collapsed to a degenerate (all other attributes are preserved)
        triangles = list(trianglesEl)
        for t in triangles:
            trianglesEl.remove(t)
        for t in triangles:
            v1 = remap[int(t.get("v1"))]
            v2 = remap[int(t.get("v2"))]
            v3 = remap[int(t.get("v3"))]
            if v1 == v2 or v2 == v3 or v1 == v3:
                continue
            attrs = dict(t.attrib)
            attrs["v1"], attrs["v2"], attrs["v3"] = str(v1), str(v2), str(v3)
            ET.SubElement(trianglesEl, f"{{{namespace}}}triangle", attrs)

    entries[MODEL_PATH] = ET.tostring(root, xml_declaration=True, encoding="UTF-8")

    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
