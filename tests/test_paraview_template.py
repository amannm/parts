from __future__ import annotations

from pathlib import Path

from simstack.io.paraview import write_paraview_template


def test_write_paraview_template_prefers_xdmf(tmp_path: Path) -> None:
    fields_bp = tmp_path / "fields.bp"
    fields_xdmf = tmp_path / "fields.xdmf"
    mesh_xdmf = tmp_path / "mesh.xdmf"
    tag_map = tmp_path / "tag_map.json"
    provenance = tmp_path / "provenance.json"
    for path in (fields_bp, fields_xdmf, mesh_xdmf, tag_map, provenance):
        path.write_text("placeholder")

    output_paths = {
        "vtx": {"fields": str(fields_bp)},
        "xdmf": {"fields": str(fields_xdmf)},
    }

    bundle = write_paraview_template(
        tmp_path,
        output_paths,
        mesh_path=str(mesh_xdmf),
        tag_map_path=str(tag_map),
        provenance_path=str(provenance),
    )

    assert bundle is not None
    state = Path(bundle["state"])
    macro = Path(bundle["macro"])
    assert state.exists()
    assert macro.exists()

    state_text = state.read_text()
    assert 'Fields format="xdmf"' in state_text
    assert str(fields_xdmf) in state_text
    assert str(mesh_xdmf) in state_text
    assert str(provenance) in state_text

    macro_text = macro.read_text()
    assert str(fields_xdmf) in macro_text
    assert str(mesh_xdmf) in macro_text


def test_write_paraview_template_returns_none_without_fields(tmp_path: Path) -> None:
    bundle = write_paraview_template(tmp_path, {"vtx": {}, "xdmf": {}})
    assert bundle is None
