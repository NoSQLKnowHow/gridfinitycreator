"""Shared model export helpers.

CadQuery's 3MF writer tessellates every B-rep face independently, so the
triangles of adjacent faces don't share vertices. The result is technically
non-manifold and some slicers refuse or mis-handle it. weld_3mf() rewrites
the mesh with duplicate vertices merged, producing a watertight indexed mesh
(verified: 0 non-manifold edges, Euler characteristic 2).
"""

import re
import zipfile
import xml.etree.ElementTree as ET

import numpy as np
from cadquery import exporters

MODEL_PATH = "3D/3dmodel.model"

# Coordinates that agree to this many decimals are the same vertex
WELD_DECIMALS = 6

_MESH = re.compile(r"<mesh>(.*?)</mesh>", re.DOTALL)
_ANY_MESH = re.compile(r"<(?:[\w.-]+:)?mesh\b")  # a mesh element, with or without a namespace prefix
_VERTICES = re.compile(r"<vertices>(.*?)</vertices>", re.DOTALL)
_TRIANGLES = re.compile(r"<triangles>(.*?)</triangles>", re.DOTALL)
_VERTEX = re.compile(r'<vertex\s+x="([^"]*)"\s+y="([^"]*)"\s+z="([^"]*)"\s*/>')
_TRIANGLE = re.compile(r'<triangle\s+v1="(\d+)"\s+v2="(\d+)"\s+v3="(\d+)"\s*/>')

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

    model = entries[MODEL_PATH].decode("utf-8")
    try:
        model, handled = _MESH.subn(lambda mesh: "<mesh>" + _weld_mesh_fast(mesh.group(1)) + "</mesh>", model)

        # A mesh written some other way (a namespace prefix, say) is not matched at all, which
        # would leave it silently unwelded: insist the fast path handled every mesh there is
        if handled != len(_ANY_MESH.findall(model)):
            raise _UnexpectedMarkup()

        entries[MODEL_PATH] = model.encode("utf-8")
    except _UnexpectedMarkup:
        # Not the layout CadQuery writes (other attributes, a namespace prefix, ...):
        # use the slower, general XML-parser implementation instead
        entries[MODEL_PATH] = _weld_with_xml_parser(entries[MODEL_PATH])

    with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)

class _UnexpectedMarkup(Exception):
    """The mesh is not in the simple layout the fast path understands"""

def _weld_mesh_fast(mesh):
    """Weld one mesh given as the text between <mesh> and </mesh>.

       This is the same algorithm as _weld_with_xml_parser, done on whole arrays: parsing
       and rebuilding the XML one element at a time took a minute for a large bin and
       about a gigabyte of memory, the vectorised version takes a few seconds."""
    vertices_block, triangles_block = _VERTICES.search(mesh), _TRIANGLES.search(mesh)
    if vertices_block is None or triangles_block is None:
        raise _UnexpectedMarkup()

    vertex_text, triangle_text = vertices_block.group(1), triangles_block.group(1)
    vertices = _VERTEX.findall(vertex_text)
    triangles = _TRIANGLE.findall(triangle_text)

    # Everything the fast path does not recognise must go to the general path
    if len(vertices) != vertex_text.count("<vertex") or len(triangles) != triangle_text.count("<triangle"):
        raise _UnexpectedMarkup()
    if not vertices:
        return mesh

    # Map identical (rounded) coordinates onto the index of their first occurrence
    coordinates = np.round(np.array(vertices, dtype=np.float64), WELD_DECIMALS)
    _, first_occurrence, inverse = np.unique(coordinates, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)

    # np.unique orders vertices by value; number them in order of first appearance instead
    appearance_order = np.argsort(first_occurrence, kind="stable")
    new_number = np.empty(len(appearance_order), dtype=np.int64)
    new_number[appearance_order] = np.arange(len(appearance_order))
    remap = new_number[inverse]

    kept_vertices = [vertices[i] for i in first_occurrence[appearance_order]]  # original text, unchanged

    # Re-point the triangles at the merged vertices, dropping any that collapsed to a line or point
    indices = np.array(triangles, dtype=np.int64).reshape(-1, 3)
    indices = remap[indices]
    keep = (indices[:, 0] != indices[:, 1]) & (indices[:, 1] != indices[:, 2]) & (indices[:, 0] != indices[:, 2])

    new_vertices = "".join(f'<vertex x="{x}" y="{y}" z="{z}" />' for x, y, z in kept_vertices)
    new_triangles = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}" />' for a, b, c in indices[keep].tolist())

    mesh = mesh[:vertices_block.start(1)] + new_vertices + mesh[vertices_block.end(1):]
    triangles_block = _TRIANGLES.search(mesh)
    return mesh[:triangles_block.start(1)] + new_triangles + mesh[triangles_block.end(1):]

def _weld_with_xml_parser(model_xml):
    """General (and slow) implementation: handles any valid 3MF layout, including
       namespace prefixes and extra triangle attributes. Returns the new XML as bytes."""
    root = ET.fromstring(model_xml)
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
            key = tuple(round(float(c), WELD_DECIMALS) for c in coords)
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

    return ET.tostring(root, xml_declaration=True, encoding="UTF-8")
