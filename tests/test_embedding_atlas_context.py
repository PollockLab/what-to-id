"""Exercise actual fragment codec, target restoration and result verification with Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
SOURCE = Path(__file__).parents[1] / "src/what_to_id"
SHA = "a" * 64
TAXONOMY_SHA = "b" * 64


def evaluate(expression):
    script = (
        f"const context=require({json.dumps(str(SOURCE / 'embedding_atlas_context.js'))});"
        f"const scope=require({json.dumps(str(SOURCE / 'embedding_atlas_logic.js'))});"
        f"console.log(JSON.stringify({expression}));"
    )
    result = subprocess.run([NODE, "-e", script], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def context_value(**updates):
    return (
        dict(
            v=1,
            group="Plantae",
            poolSha=SHA,
            taxonomySha=None,
            q="",
            taxonRoots=[],
            taxonExclude=False,
            brushIds=[11, 13],
            onlyBrushed=True,
            geoBounds=None,
            resultIds=[11, 13],
            fromLabel="BioCLIP",
        )
        | updates
    )


def payload_value():
    return dict(
        group="Plantae",
        records=[
            dict(id=13, name="Plant", lon=-123, lat=49),
            dict(id=12, name="Plant", lon=-123, lat=49),
            dict(id=11, name="Plant", lon=-100, lat=49),
        ],
    )


def restore(value, payload=None, pool_sha=SHA):
    return evaluate(
        f"context.restore({json.dumps(value)}, {json.dumps(payload or payload_value())}, "
        f"{{pool_sha256:{json.dumps(pool_sha)}}}, scope)"
    )


def test_context_round_trip_and_brush_restores_by_id_without_reordering_source():
    value = context_value()
    assert evaluate(f"context.decode(context.encode({json.dumps(value)}))") == value
    assert restore(value) == dict(
        presetIndex=-1,
        brushedIndices=[2, 0],
        missingBrush=0,
        ok=True,
        missing=0,
        unexpected=0,
        missingTarget=0,
    )
    href = evaluate(
        'scope.modelHref("other/embeddings.html", "https://example.test/embeddings.html", '
        f'"Plantae", 11, context.encode({json.dumps(value)}))'
    )
    assert "?" not in href and "&ctx=" in href


@pytest.mark.parametrize(
    "updates",
    [
        dict(v=2),
        dict(poolSha="unknown"),
        dict(taxonomySha="unknown"),
        dict(resultIds=[1, 1]),
        dict(resultIds=[0]),
        dict(resultIds=[-1]),
        dict(resultIds=[9007199254740992]),
        dict(resultIds=list(range(1, 1002))),
        dict(brushIds=["11"]),
        dict(brushIds=list(range(1, 1001)), resultIds=[1001]),
        dict(taxonRoots=[0]),
        dict(taxonExclude=True),
        dict(onlyBrushed="true"),
        dict(q="a" * 1001),
        dict(geoBounds=[0, -91, 1, 2]),
        dict(geoBounds=[0, 2, 1, 1]),
        dict(geoBounds=[0, 0, 1]),
    ],
)
def test_context_rejects_unsafe_ids_malformed_fields_and_unbounded_state(updates):
    value = context_value(**updates)
    assert evaluate(
        f"(()=>{{try{{context.encode({json.dumps(value)});return false;}}catch{{return true;}}}})()"
    )


@pytest.mark.parametrize("text", ["{", "null", "a" * 100001])
def test_malformed_or_oversized_fragment_is_rejected(text):
    assert evaluate(
        f"(()=>{{try{{context.decode({json.dumps(text)});return false;}}catch{{return true;}}}})()"
    )


def test_missing_target_and_unexpected_results_fail_verification_instead_of_filtering():
    value = context_value(brushIds=[], onlyBrushed=False, resultIds=[11, 99])
    result = restore(value)
    assert result == dict(
        presetIndex=-1,
        brushedIndices=[],
        missingBrush=0,
        ok=False,
        missing=1,
        unexpected=2,
        missingTarget=1,
    )
    empty = restore(context_value(brushIds=[], onlyBrushed=False, q="absent", resultIds=[]))
    assert empty["ok"] is True
    assert restore(context_value(brushIds=[], onlyBrushed=False, resultIds=[]))["ok"] is False


def test_taxon_restoration_uses_actual_roots_and_exclusion_not_preset_position():
    payload = payload_value()
    payload["taxonomy"] = dict(
        cache_sha256=TAXONOMY_SHA,
        presets=[
            dict(label="Outside", approximate=True, exclude=True, taxon_ids=[50]),
            dict(label="Inside", approximate=True, exclude=False, taxon_ids=[50]),
        ],
    )
    for record, ancestry, complete in zip(
        payload["records"], [[13, 1], [12, 50], [11, 999]], [True, False, False], strict=True
    ):
        record.update(
            taxon_id=record["id"], ancestor_taxon_ids=ancestry, taxonomy_complete=complete
        )
    value = context_value(
        taxonomySha=TAXONOMY_SHA,
        taxonRoots=[50],
        taxonExclude=True,
        brushIds=[],
        onlyBrushed=False,
        resultIds=[13],
    )
    assert restore(value, payload)["ok"] is True
    assert restore(value, payload)["presetIndex"] == 0
    assert restore(value | dict(taxonExclude=False, resultIds=[12]), payload)["presetIndex"] == 1
    for change in [dict(taxonomySha=SHA), dict(taxonRoots=[99]), dict(poolSha=TAXONOMY_SHA)]:
        assert evaluate(
            f"(()=>{{try{{context.restore({json.dumps(value | change)}, {json.dumps(payload)}, "
            f"{{pool_sha256:{json.dumps(SHA)}}}, scope);return false;}}catch{{return true;}}}})()"
        )


def test_retained_geo_is_a_criterion_and_result_ids_only_verify_it():
    value = context_value(
        brushIds=[], onlyBrushed=False, geoBounds=[-130, 45, -110, 60], resultIds=[12, 13]
    )
    assert restore(value)["ok"] is True
    mismatch = restore(value | dict(resultIds=[11]))
    assert mismatch["missing"] == 1 and mismatch["unexpected"] == 2


def test_missing_brush_id_blocks_even_when_unfiltered_result_ids_still_match():
    result = restore(context_value(brushIds=[99], onlyBrushed=False, resultIds=[11, 12, 13]))
    assert result["ok"] is False
    assert result["missingBrush"] == 1
    assert result["missing"] == result["unexpected"] == 0
