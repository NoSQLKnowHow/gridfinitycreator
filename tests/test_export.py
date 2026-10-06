"""3MF export: welding duplicate vertices, and keeping it fast.

CadQuery writes every face's triangles with their own copies of the vertices. weld_3mf
merges them so the mesh is watertight. The first version of it parsed and rebuilt the
XML element by element: a minute and a gigabyte for a large bin. The fast path does
the same job on whole arrays; these tests pin down that it gives the same answer.
"""

import collections
import os
import xml.etree.ElementTree as ET
import zipfile

import pytest
import cadquery as cq

from generators.common import export

NAMESPACE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

# A cube as CadQuery writes it: every triangle owns its three vertices (36 for 8 corners)
CORNERS = [(x, y, z) for x in (0, 10) for y in (0, 10) for z in (0, 10)]
CUBE_TRIANGLES = [
    (0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
    (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5),
]


def cube_model_xml(triangle_attributes="", extra_degenerate=False, prefix=""):
    vertices, triangles = [], []
    for a, b, c in CUBE_TRIANGLES:
        base = len(vertices)
        vertices += [CORNERS[a], CORNERS[b], CORNERS[c]]
        triangles.append((base, base + 1, base + 2))
    if extra_degenerate:  # three copies of one corner: collapses to a point once welded
        base = len(vertices)
        vertices += [CORNERS[0]] * 3
        triangles.append((base, base + 1, base + 2))

    v = "".join(f'<{prefix}vertex x="{x}.0" y="{y}.0" z="{z}.0" />' for x, y, z in vertices)
    t = "".join(f'<{prefix}triangle v1="{a}" v2="{b}" v3="{c}"{triangle_attributes} />' for a, b, c in triangles)
    p = prefix
    return (f'<?xml version="1.0" encoding="utf-8"?><{p}model xmlns{":" + p[:-1] if p else ""}="{NAMESPACE}" unit="millimeter">'
            f'<{p}resources><{p}object id="1" type="model"><{p}mesh><{p}vertices>{v}</{p}vertices>'
            f'<{p}triangles>{t}</{p}triangles></{p}mesh></{p}object></{p}resources></{p}model>')


def write_3mf(path, model_xml):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(export.MODEL_PATH, model_xml)


def read_mesh(path):
    root = ET.fromstring(zipfile.ZipFile(path).read(export.MODEL_PATH))
    mesh = next(element for element in root.iter() if element.tag.endswith("}mesh") or element.tag == "mesh")
    children = {child.tag.split("}")[-1]: child for child in mesh}
    vertices = [(e.get("x"), e.get("y"), e.get("z")) for e in children["vertices"]]
    triangles = [dict(e.attrib) for e in children["triangles"]]
    return vertices, triangles


def edge_use(vertices, triangles):
    """How many triangles use each undirected edge, by vertex position"""
    uses = collections.Counter()
    for triangle in triangles:
        corners = [vertices[int(triangle[key])] for key in ("v1", "v2", "v3")]
        for first, second in ((0, 1), (1, 2), (2, 0)):
            uses[frozenset((corners[first], corners[second]))] += 1
    return uses


# ---------------------------------------------------------------- the fast path

def test_duplicate_vertices_are_merged_and_the_mesh_becomes_watertight(tmp_path):
    path = str(tmp_path / "cube.3mf")
    write_3mf(path, cube_model_xml())

    export.weld_3mf(path)
    vertices, triangles = read_mesh(path)

    assert len(vertices) == 8                       # 36 copies became the 8 corners
    assert len(triangles) == 12
    assert set(edge_use(vertices, triangles).values()) == {2}  # every edge shared by exactly two triangles


def test_vertices_keep_the_order_of_their_first_appearance(tmp_path):
    path = str(tmp_path / "cube.3mf")
    write_3mf(path, cube_model_xml())

    export.weld_3mf(path)
    vertices, triangles = read_mesh(path)

    # The first triangle was (corner 0, corner 2, corner 1), so those come out as 0, 1, 2
    assert [vertices[int(triangles[0][k])] for k in ("v1", "v2", "v3")] == [
        ("0.0", "0.0", "0.0"), ("0.0", "10.0", "0.0"), ("0.0", "0.0", "10.0")]
    assert (triangles[0]["v1"], triangles[0]["v2"], triangles[0]["v3"]) == ("0", "1", "2")


def test_triangles_that_collapse_are_dropped(tmp_path):
    path = str(tmp_path / "cube.3mf")
    write_3mf(path, cube_model_xml(extra_degenerate=True))

    export.weld_3mf(path)
    _, triangles = read_mesh(path)

    assert len(triangles) == 12


def test_the_fast_path_gives_the_same_result_as_the_general_implementation(tmp_path):
    xml = cube_model_xml(extra_degenerate=True)
    fast = tmp_path / "fast.3mf"
    write_3mf(str(fast), xml)
    export.weld_3mf(str(fast))

    slow = tmp_path / "slow.3mf"
    write_3mf(str(slow), export._weld_with_xml_parser(xml.encode()).decode())

    assert read_mesh(str(fast)) == read_mesh(str(slow))


@pytest.mark.parametrize("model", [
    cq.Workplane().box(10, 10, 10),
    cq.Workplane().box(20, 10, 5).edges("|Z").fillet(2).faces(">Z").workplane().hole(4),
])
def test_real_cadquery_output_is_welded_identically_by_both_implementations(tmp_path, model):
    raw = str(tmp_path / "raw.3mf")
    cq.exporters.export(model, raw)
    xml = zipfile.ZipFile(raw).read(export.MODEL_PATH)

    fast, slow = tmp_path / "fast.3mf", tmp_path / "slow.3mf"
    write_3mf(str(fast), xml.decode())
    export.weld_3mf(str(fast))
    write_3mf(str(slow), export._weld_with_xml_parser(xml).decode())

    raw_vertices, _ = read_mesh(raw)
    fast_vertices, fast_triangles = read_mesh(str(fast))
    assert read_mesh(str(fast)) == read_mesh(str(slow))
    assert len(fast_vertices) < len(raw_vertices)                       # welding actually merged vertices
    assert set(edge_use(fast_vertices, fast_triangles).values()) == {2}  # and the result is closed


def test_export_model_welds_3mf_but_leaves_other_formats_alone(tmp_path):
    box = cq.Workplane().box(10, 10, 10)

    export.export_model(box, str(tmp_path / "box.3mf"))
    export.export_model(box, str(tmp_path / "box.stl"))

    vertices, _ = read_mesh(str(tmp_path / "box.3mf"))
    assert len(vertices) == 8
    assert os.path.getsize(tmp_path / "box.stl") > 0


# ---------------------------------------------------------------- unfamiliar markup

def test_extra_triangle_attributes_use_the_general_path_and_are_preserved(tmp_path):
    path = str(tmp_path / "attributes.3mf")
    write_3mf(path, cube_model_xml(triangle_attributes=' p1="0"'))

    export.weld_3mf(path)
    vertices, triangles = read_mesh(path)

    assert len(vertices) == 8
    assert all(triangle["p1"] == "0" for triangle in triangles)


def test_a_namespace_prefix_uses_the_general_path(tmp_path):
    path = str(tmp_path / "prefixed.3mf")
    write_3mf(path, cube_model_xml(prefix="m:"))

    export.weld_3mf(path)
    vertices, triangles = read_mesh(path)

    assert len(vertices) == 8
    assert len(triangles) == 12
