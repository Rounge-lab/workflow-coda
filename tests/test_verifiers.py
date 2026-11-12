"""Tests for the artifact verifiers: the trio, the registry index,
and the core.tabular contract.

The verifier contracts, executable — driven through the registry's
index (the trio unconditionally, plugin verifiers gated by schema
version) and called directly on bytes: the returned records are
byte-pinned, the teachings fragment-pinned.  The imports of names
that do not exist yet are part of the contract — the suite's
collection error names the module the implementation owes.
"""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import pytest

from workflow_coda.artifact_store import JsonValue
from workflow_coda.components import (
    ComponentParameters,
    PlacementInfo,
    PluginMetadata,
    RenderedComponent,
    ReportComponent,
)
from workflow_coda.context import RenderContext
from workflow_coda.core.plugin import get_plugin
from workflow_coda.errors import PluginConflictError, VerificationError
from workflow_coda.plugins import ArtifactVerifier, ReportPlugin
from workflow_coda.registry import PluginRegistry


def _noop_render(
    context: RenderContext, info: PlacementInfo, parameters: ComponentParameters
) -> RenderedComponent:
    return RenderedComponent.skipped()


def _noop_verify(
    data: bytes, criteria: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    return {"format": "bio.newick", "status": "ok"}


def _plugin_claiming(
    plugin_id: str, fmt: str, versions: frozenset[str]
) -> ReportPlugin:
    """A minimal plugin whose only stake is one artifact format."""
    return ReportPlugin(
        metadata=PluginMetadata(
            id=plugin_id,
            name=f"{plugin_id} plugin",
            version="1.0",
            description="a test plugin",
            supported_schema_versions=versions,
        ),
        components=(
            ReportComponent(
                id=f"{plugin_id}.thing", title="Thing", render=_noop_render
            ),
        ),
        artifact_verifiers=(ArtifactVerifier(format=fmt, verify=_noop_verify),),
    )


def _formats(registry: PluginRegistry) -> tuple[str, ...]:
    return tuple(verifier.format for verifier in registry.verifiers)


def _verifier(registry: PluginRegistry, fmt: str) -> ArtifactVerifier:
    for verifier in registry.verifiers:
        if verifier.format == fmt:
            return verifier
    pytest.fail(f"no verifier for {fmt!r}")


# ---------------------------------------------------------------------------
# The index: trio, plugin claims, gating, conflicts
# ---------------------------------------------------------------------------


def test_the_trio_is_unconditional() -> None:
    # The agnostic formats are the framework's own: an empty registry
    # — no plugins at all — still verifies json, txt, and bytes.
    assert _formats(PluginRegistry(())) == ("json", "txt", "bytes")


def test_core_plugin_offers_the_tabular_verifier() -> None:
    # core.tabular rides the core plugin like its components do, and
    # the index answers in order: the framework's trio first, then
    # plugin claims in discovery order — the census shape.
    registry = PluginRegistry((get_plugin(),))
    assert _formats(registry) == ("json", "txt", "bytes", "core.tabular")


def test_plugin_verifiers_gate_by_schema_version() -> None:
    # The same gate as components: a verifier arrives with its
    # plugin's version support, and the version being written
    # decides — while the trio, the framework's own, survives any
    # version.  A plugin may still declare the old version; it
    # simply never gates in.
    old = _plugin_claiming("oldguard", "bio.legacy", frozenset({"0.2.0"}))
    new = _plugin_claiming("newguard", "bio.newick", frozenset({"0.3.0"}))
    registry = PluginRegistry((old, new))
    assert _formats(registry) == (
        "json",
        "txt",
        "bytes",
        "bio.legacy",
        "bio.newick",
    )
    supporting = registry.verifiers_supporting("0.3.0")
    assert tuple(verifier.format for verifier in supporting) == (
        "json",
        "txt",
        "bytes",
        "bio.newick",
    )


def test_cross_plugin_format_claims_teach() -> None:
    # Two plugins claiming one format is the registry's component-id
    # law in a second namespace: the conflict teaches at assembly,
    # counted and named.
    alpha = _plugin_claiming("alpha", "bio.newick", frozenset({"0.3.0"}))
    beta = _plugin_claiming("beta", "bio.newick", frozenset({"0.3.0"}))
    with pytest.raises(PluginConflictError, match="same format: 'bio.newick' x2"):
        PluginRegistry((alpha, beta))


def test_the_trio_is_reserved() -> None:
    # json, txt, and bytes are the framework's own formats; a plugin
    # claiming one is taught the reservation at assembly.
    hijacker = _plugin_claiming("hijacker", "json", frozenset({"0.3.0"}))
    with pytest.raises(PluginConflictError, match="reserved"):
        PluginRegistry((hijacker,))


def test_the_trio_covers_the_manifests_format_enum() -> None:
    # Design pin: the framework's verifier trio is exactly the
    # manifest's ArtifactFormat enum — the agnostic formats are the
    # framework's to verify, everything namespaced is a plugin's.
    # verify's format index is its own deliberate dispatch surface;
    # the store's no-dispatch law lives in its own suite, untouched.
    from workflow_coda.manifest import ArtifactFormat

    assert _formats(PluginRegistry(())) == tuple(fmt.value for fmt in ArtifactFormat)


# ---------------------------------------------------------------------------
# The verifier model's contract
# ---------------------------------------------------------------------------


def test_the_verifier_model_is_frozen() -> None:
    # Value semantics: a declared verifier is immutable, like every
    # contract model in the framework.
    verifier = ArtifactVerifier(format="json", verify=_noop_verify)
    with pytest.raises(FrozenInstanceError):
        verifier.format = "txt"  # type: ignore[misc]


def test_a_verifier_requires_a_callable() -> None:
    # The ReportComponent precedent: the declaration validates its
    # own shape at construction — the recipe, not the meal.
    with pytest.raises(ValueError, match="callable"):
        ArtifactVerifier(
            format="bio.newick",
            verify="not a callable",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# The agnostic trio's contracts, on bytes
# ---------------------------------------------------------------------------


def _trio(fmt: str) -> ArtifactVerifier:
    """One of the framework's own verifiers, straight from the index."""
    return _verifier(PluginRegistry(()), fmt)


def test_json_passes_basic_check_and_records() -> None:
    record = _trio("json").verify(b'{"depth": 12.4, "rate": 98.2}', {})
    assert record == {"format": "json", "status": "ok"}


def test_json_teaches_on_bad_bytes() -> None:
    with pytest.raises(VerificationError, match="not valid UTF-8"):
        _trio("json").verify(b"\xff\xfe", {})
    with pytest.raises(VerificationError, match="does not parse as JSON"):
        _trio("json").verify(b"{nope", {})


def test_json_keys_criterion_accepts_both_transport_shapes() -> None:
    # Spec mode arrives YAML-typed, flags mode as one string — the
    # verifier's grammar takes both, and the record shows what was
    # checked either way.
    data = b'{"depth": 12.4, "rate": 98.2}'
    expected = {
        "format": "json",
        "status": "ok",
        "keys_checked": ["depth", "rate"],
    }
    assert _trio("json").verify(data, {"keys": "depth,rate"}) == expected
    assert _trio("json").verify(data, {"keys": ["depth", "rate"]}) == expected


def test_json_keys_criterion_teaches_the_missing_key() -> None:
    with pytest.raises(VerificationError, match="names 'missing'"):
        _trio("json").verify(b'{"depth": 12.4}', {"keys": ["depth", "missing"]})


def test_json_keys_on_a_non_object_payload_teaches() -> None:
    with pytest.raises(VerificationError, match="top-level object"):
        _trio("json").verify(b"[1, 2]", {"keys": ["depth"]})


def test_json_keys_shape_teaches() -> None:
    with pytest.raises(VerificationError, match="at least one"):
        _trio("json").verify(b'{"depth": 12.4}', {"keys": []})
    with pytest.raises(VerificationError, match="twice"):
        _trio("json").verify(b'{"depth": 12.4}', {"keys": ["depth", "depth"]})


def test_json_unknown_criterion_teaches_with_a_suggestion() -> None:
    # reject_unknown_parameters' law at the verifier boundary.
    with pytest.raises(VerificationError, match="did you mean 'keys'"):
        _trio("json").verify(b'{"depth": 12.4}', {"keyz": ["depth"]})


def test_txt_passes_and_takes_no_criteria() -> None:
    # txt claims UTF-8 text and nothing more — there is no content
    # promise to declare, so criteria are refused, not guessed.
    record = _trio("txt").verify(b"field notes\n", {})
    assert record == {"format": "txt", "status": "ok"}
    with pytest.raises(VerificationError, match="takes no criteria"):
        _trio("txt").verify(b"notes", {"keys": ["a"]})


def test_txt_teaches_on_invalid_utf8() -> None:
    with pytest.raises(VerificationError, match="not valid UTF-8"):
        _trio("txt").verify(b"\xff\xfe", {})


def test_bytes_verifies_any_bytes_and_takes_no_criteria() -> None:
    # bytes claims nothing beyond existence — and existence is the
    # CLI's own check — so the basic check is the record alone.
    record = _trio("bytes").verify(b"\xff\xfe\x00raw", {})
    assert record == {"format": "bytes", "status": "ok"}
    with pytest.raises(VerificationError, match="takes no criteria"):
        _trio("bytes").verify(b"x", {"min_rows": 1})


# ---------------------------------------------------------------------------
# core.tabular: the component's default reading, plus the promises
# ---------------------------------------------------------------------------


def _tabular() -> ArtifactVerifier:
    """The core plugin's tabular verifier, off the shipped roster."""
    return _verifier(PluginRegistry((get_plugin(),)), "core.tabular")


def _samples() -> bytes:
    """The bundle's samples artifact: headered, four data rows, real
    tabs as explicit escapes so the fixture's bytes are unambiguous."""
    return (
        b"sample_id\tdepth\tstatus\n"
        b"S1\t9\tpassed\n"
        b"S2\t100\tfailed\n"
        b"S3\t10\tpassed\n"
        b"S4\t\tpending\n"
    )


def test_tabular_basic_check_records_the_default_reading() -> None:
    # The coherence rule, executable: the verifier's default reading
    # is the component's — header under tab, shape laws, four data
    # rows — and the record states exactly that reading.
    assert _tabular().verify(_samples(), {}) == {
        "format": "core.tabular",
        "status": "ok",
        "sep": "\t",
        "header": True,
        "rows": 4,
    }


def test_tabular_empty_file_teaches() -> None:
    with pytest.raises(VerificationError, match="contains no header row"):
        _tabular().verify(b"", {})


def test_tabular_blank_header_cell_beyond_the_first_teaches() -> None:
    with pytest.raises(
        VerificationError, match="empty header column name at position 3"
    ):
        _tabular().verify(b"a\tb\t\n1\t2\t3\n", {})


def test_tabular_duplicate_header_teaches() -> None:
    with pytest.raises(VerificationError, match="duplicate header column 'depth'"):
        _tabular().verify(b"depth\tdepth\n1\t2\n", {})


def test_tabular_ragged_row_teaches() -> None:
    with pytest.raises(VerificationError, match="has 2 fields, expected 3"):
        _tabular().verify(b"a\tb\tc\n1\t2\n", {})


def test_tabular_mixed_delimiters_name_the_suspect_sep() -> None:
    # The one mixed-delimiter case the parser can see — table.py's
    # documented boundary — carried into verification.
    with pytest.raises(VerificationError, match="actual delimiter"):
        _tabular().verify(b"a\tb\tc\n1,2,3\n", {})


def test_tabular_sep_criterion_adjusts_the_reading() -> None:
    comma = b"sample_id,depth\nS1,9\n"
    assert _tabular().verify(comma, {"sep": ","}) == {
        "format": "core.tabular",
        "status": "ok",
        "sep": ",",
        "header": True,
        "rows": 1,
    }
    with pytest.raises(VerificationError, match="single character"):
        _tabular().verify(comma, {"sep": ",,"})


def test_tabular_columns_criterion_is_a_presence_check() -> None:
    # A set, never an order: order and selection are presentation —
    # core.table's business, not the pipeline's promise.
    record = _tabular().verify(_samples(), {"columns": "sample_id,depth"})
    assert record["columns_checked"] == ["sample_id", "depth"]
    with pytest.raises(VerificationError, match="the criteria names 'missing'"):
        _tabular().verify(_samples(), {"columns": "sample_id,missing"})


def test_tabular_columns_shape_teaches() -> None:
    with pytest.raises(VerificationError, match="at least one"):
        _tabular().verify(_samples(), {"columns": []})
    with pytest.raises(VerificationError, match="twice"):
        _tabular().verify(_samples(), {"columns": ["depth", "depth"]})


def test_tabular_min_rows_counts_data_rows() -> None:
    # The header is not a data row — min_rows four against four
    # samples passes; five teaches with the actual count.
    assert _tabular().verify(_samples(), {"min_rows": 4})["min_rows"] == 4
    with pytest.raises(VerificationError, match="requires at least 5"):
        _tabular().verify(_samples(), {"min_rows": 5})


def test_tabular_flag_transport_shapes_parse() -> None:
    # Flags criteria arrive as strings; the verifier's grammar
    # parses them — booleans, integers, comma lists — and teaches
    # on what it cannot parse.
    assert _tabular().verify(b"S1\t9\n", {"header": "false"})["header"] is False
    assert _tabular().verify(_samples(), {"min_rows": "4"})["min_rows"] == 4
    with pytest.raises(VerificationError, match="boolean"):
        _tabular().verify(b"S1\t9\n", {"header": "nope"})
    with pytest.raises(VerificationError, match="integer"):
        _tabular().verify(_samples(), {"min_rows": "four"})


def test_tabular_headerless_reading_records_rows() -> None:
    assert _tabular().verify(b"S1\t9\nS2\t100\n", {"header": False}) == {
        "format": "core.tabular",
        "status": "ok",
        "sep": "\t",
        "header": False,
        "rows": 2,
    }


def test_tabular_headerless_refuses_columns() -> None:
    # The component's own teaching, carried: columns select by
    # header name, and a headerless table has none.
    with pytest.raises(VerificationError, match="header: false"):
        _tabular().verify(b"S1\t9\n", {"header": False, "columns": ["a"]})


def test_tabular_headerless_empty_teaches() -> None:
    with pytest.raises(VerificationError, match="column count is unknown"):
        _tabular().verify(b"", {"header": False})


def test_tabular_index_column_convention_is_legal() -> None:
    # A blank first header cell is the producer's in-band index
    # declaration — legal, and 'columns' addresses the named
    # columns after it, exactly as core.table does.
    indexed = b"\tdepth\nS1\t9\nS2\t100\n"
    assert _tabular().verify(indexed, {})["rows"] == 2
    assert _tabular().verify(indexed, {"columns": ["depth"]})["status"] == "ok"


def test_tabular_unknown_criterion_teaches_with_a_suggestion() -> None:
    with pytest.raises(VerificationError, match="did you mean 'min_rows'"):
        _tabular().verify(_samples(), {"min_row": 5})
