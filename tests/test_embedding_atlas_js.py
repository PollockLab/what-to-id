"""Execute the atlas's actual public-coordinate filtering logic with Node."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
LOGIC = Path(__file__).parents[1] / "src/what_to_id/embedding_atlas_logic.js"


def evaluate(expression):
    script = (
        f"const scope=require({json.dumps(str(LOGIC))}); console.log(JSON.stringify({expression}));"
    )
    result = subprocess.run([NODE, "-e", script], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("lon", "lat", "bounds", "expected"),
    [
        (-123, 49, [-123, 49, -122, 50], True),
        (-122, 50, [-123, 49, -122, 50], True),
        (-124, 49, [-123, 49, -122, 50], False),
        (-122, 51, [-123, 49, -122, 50], False),
        (179, 0, [170, -10, -170, 10], True),
        (-179, 0, [170, -10, -170, 10], True),
        (0, 0, [170, -10, -170, 10], False),
        (-179, 0, [170, -10, 190, 10], True),
        (0, 0, [-400, -10, 400, 10], True),
        (-123, 49, None, False),
    ],
)
def test_public_coordinate_bounds_including_dateline(lon, lat, bounds, expected):
    assert (
        evaluate(f"scope.inBounds({json.dumps(dict(lon=lon, lat=lat))}, {json.dumps(bounds)})")
        is expected
    )


def test_filter_then_search_then_unfamiliar_order_preserves_record_indices():
    records = [
        dict(id=21, name="Bird beta", lon=-123, lat=49, reference_distance=0.3),
        dict(id=22, name="Bird alpha", lon=-122, lat=49, reference_distance=0.8),
        dict(id=23, name="Bird outside", lon=-100, lat=49, reference_distance=1.2),
        dict(id=24, name="Other taxon", lon=-122, lat=49, reference_distance=0.9),
    ]
    options = dict(
        bounds=[-124, 48, -121, 50],
        onlyInView=True,
        term="bird",
        order="reference",
        hasReference=True,
    )
    result = evaluate(f"scope.matches({json.dumps(records)}, {json.dumps(options)})")
    assert [r["r"]["id"] for r in result] == [22, 21]
    assert [r["i"] for r in result] == [1, 0]
    assert [r["id"] for r in records] == [21, 22, 23, 24]


def test_zero_viewport_matches_and_inactive_filter_recovery():
    records = [dict(id=1, name="Fish", lon=-123, lat=49)]
    options = dict(bounds=[10, 10, 11, 11], onlyInView=True)
    assert evaluate(f"scope.matches({json.dumps(records)}, {json.dumps(options)})") == []
    options["onlyInView"] = False
    assert len(evaluate(f"scope.matches({json.dumps(records)}, {json.dumps(options)})")) == 1


def test_group_changes_do_not_reuse_previous_groups_observations():
    birds = [dict(id=1, name="Bird", lon=-123, lat=49)]
    fish = [dict(id=2, name="Fish", lon=-123, lat=49)]
    options = dict(bounds=[-124, 48, -122, 50], onlyInView=True)
    assert evaluate(f"scope.matches({json.dumps(birds)}, {json.dumps(options)})")[0]["r"]["id"] == 1
    assert evaluate(f"scope.matches({json.dumps(fish)}, {json.dumps(options)})")[0]["r"]["id"] == 2


def test_no_map_bounds_cannot_offer_viewport_matches():
    assert evaluate('scope.matches([{id:1,name:"Bird",lon:0,lat:0}], {onlyInView:true})') == []


@pytest.mark.parametrize("rectangle", [[0, 0, 10, 10], [10, 10, 0, 0]])
def test_brush_geometric_boundaries_and_reverse_drag(rectangle):
    points = [[0, 0], [10, 10], [5, 5], [-0.01, 5], [5, 10.01]]
    assert evaluate(f"scope.brushIndices({json.dumps(points)}, {json.dumps(rectangle)})") == [
        0,
        1,
        2,
    ]


def test_empty_or_cleared_brush_has_no_geometric_members():
    assert evaluate("scope.brushIndices([[5,5]], null)") == []
    assert evaluate("scope.brushIndices([[5,5]], [0,0,1,1])") == []
    assert evaluate("scope.brushIndices([[5,5]], [0,0,NaN,10])") == []


def test_brush_intersects_viewport_search_and_reference_order_then_clear_recovers():
    records = [
        dict(id=1, name="Bird A", lon=-123, lat=49, reference_distance=0.2),
        dict(id=2, name="Bird B", lon=-123, lat=49, reference_distance=0.9),
        dict(id=3, name="Bird outside view", lon=-100, lat=49, reference_distance=1.1),
        dict(id=4, name="Different taxon", lon=-123, lat=49, reference_distance=0.8),
        dict(id=5, name="Bird outside brush", lon=-123, lat=49, reference_distance=1.5),
    ]
    options = dict(
        onlyBrushed=True,
        brushedIndices=[0, 1, 2, 3],
        onlyInView=True,
        bounds=[-124, 48, -122, 50],
        term="Bird",
        order="reference",
        hasReference=True,
    )
    result = evaluate(f"scope.matches({json.dumps(records)}, {json.dumps(options)})")
    assert [x["r"]["id"] for x in result] == [2, 1]
    options["brushedIndices"] = []
    assert evaluate(f"scope.matches({json.dumps(records)}, {json.dumps(options)})") == []
    options["onlyBrushed"] = False
    result = evaluate(f"scope.matches({json.dumps(records)}, {json.dumps(options)})")
    assert [x["r"]["id"] for x in result] == [5, 2, 1]


def test_keyboard_set_membership_matches_brush_scope_without_mutating_input():
    assert evaluate("scope.toggleIndex([0,2], 1)") == [0, 1, 2]
    assert evaluate("scope.toggleIndex([0,2], 2)") == [0]
    assert evaluate("scope.toggleIndex([0], 0)") == []
    assert evaluate(
        "(()=>{const initial=Object.freeze([0]);return scope.toggleIndex(initial,1);})()"
    ) == [0, 1]
    assert evaluate(
        'scope.matches([{id:1,name:"A"},{id:2,name:"B"}], '
        "{onlyBrushed:true, brushedIndices:scope.toggleIndex([],1)}).map(x=>x.r.id)"
    ) == [2]


def test_separate_model_navigation_preserves_group_and_selected_observation():
    assert (
        evaluate(
            'scope.modelHref("dinov3/embeddings.html", '
            '"https://example.org/atlas/embeddings.html?bbox=1,2,3,4#group=Aves&id=1", '
            '"Plantae", 123)'
        )
        == "https://example.org/atlas/dinov3/embeddings.html#group=Plantae&id=123"
    )
    assert (
        evaluate(
            'scope.modelHref("../embeddings.html", '
            '"https://example.org/atlas/dinov3/embeddings.html", "Aves", 456)'
        )
        == "https://example.org/atlas/embeddings.html#group=Aves&id=456"
    )


def test_unknown_cross_model_observation_is_explicitly_reported_not_lost():
    assert evaluate('scope.resolveSelection([{id:11},{id:12}], "99")') == {
        "index": 0,
        "missingRequestedId": 99,
    }
    assert evaluate('scope.resolveSelection([{id:11},{id:12}], "12")') == {
        "index": 1,
        "missingRequestedId": None,
    }
    assert evaluate("scope.resolveSelection([{id:11}], null)") == {
        "index": 0,
        "missingRequestedId": None,
    }


def test_atlas_returns_same_record_and_exact_group_to_sibling_map():
    assert (
        evaluate(
            'scope.mapHref("../map.html", '
            '"https://example.org/dinov3/embeddings.html", "Aves", 123)'
        )
        == "https://example.org/map.html#groups=Aves&record=123"
    )


def neighborhood_payloads(expression):
    setup = """(()=>{const ids=Array.from({length:26},(_,i)=>i+1);
function payload(backbone,order,neighbors){return {group:'Aves',backbone,
 records:order.map(id=>({id,name:'Photo '+id,neighbors:id===1?
 neighbors.map(n=>[order.indexOf(n),backbone==='a'?.1:999]):[]}))};}
const a=payload('a',ids,ids.slice(1,13));
const b=payload('b',[...ids].reverse(),[2,3,4,5,14,15,16,17,18,19,20,21]);
"""
    return evaluate(setup + expression + "})()")


def test_cross_encoder_overlap_uses_id_sets_not_indices_or_raw_scores():
    result = neighborhood_payloads("return scope.compareNeighborhoods(a,b,1);")
    assert result == {
        "status": "comparable",
        "leftCount": 12,
        "rightCount": 12,
        "sharedIds": [2, 3, 4, 5],
        "cohortCount": 26,
        "exhaustive": False,
    }


def test_cross_encoder_comparison_rejects_different_pools_or_groups():
    assert neighborhood_payloads(
        "b.records[0].id=99;return scope.compareNeighborhoods(a,b,1);"
    ) == {"status": "pool_mismatch"}
    assert neighborhood_payloads("b.group='Plantae';return scope.compareNeighborhoods(a,b,1);") == {
        "status": "pool_mismatch"
    }


def test_cross_encoder_missing_query_and_invalid_neighbors_are_explicit():
    assert neighborhood_payloads("return scope.compareNeighborhoods(a,b,99);") == {
        "status": "missing_query",
    }
    assert neighborhood_payloads(
        "a.records[0].neighbors=[[999,.1]];return scope.compareNeighborhoods(a,b,1);"
    ) == {"status": "invalid_neighbors"}


def test_cross_encoder_empty_overlap_is_valid_agreement_result():
    assert (
        neighborhood_payloads("""b.records.find(r=>r.id===1).neighbors=
      Array.from({length:12},(_,i)=>[b.records.findIndex(r=>r.id===i+14),999]);
      return scope.compareNeighborhoods(a,b,1);""")["sharedIds"]
        == []
    )


def test_comparison_gate_rejects_late_selection_and_group_requests():
    result = evaluate("""(()=>{const gate=scope.requestGate(),old=gate.begin(),next=gate.begin();
      const before=[gate.current(old),gate.current(next)];gate.cancel();
      return {before,after:gate.current(next),fresh:gate.current(gate.begin())};})()""")
    assert result == {"before": [False, True], "after": False, "fresh": True}


def test_cross_encoder_requires_full_intended_top_k_list():
    assert neighborhood_payloads(
        "a.records[0].neighbors=a.records[0].neighbors.slice(0,11);"
        "return scope.compareNeighborhoods(a,b,1);"
    ) == {"status": "invalid_neighbors"}
    assert neighborhood_payloads(
        "a.records[0].neighbors[1]=a.records[0].neighbors[0];"
        "return scope.compareNeighborhoods(a,b,1);"
    ) == {"status": "invalid_neighbors"}
    assert neighborhood_payloads(
        "a.records[0].neighbors[0]=[0,0];return scope.compareNeighborhoods(a,b,1);"
    ) == {"status": "invalid_neighbors"}


def test_cross_encoder_small_pool_overlap_is_marked_trivial():
    result = evaluate("""scope.compareNeighborhoods(
      {group:'Aves',backbone:'a',records:[{id:1,neighbors:[[1,.1]]},{id:2}]},
      {group:'Aves',backbone:'b',records:[{id:2},{id:1,neighbors:[[0,999]]}]},1)""")
    assert result["sharedIds"] == [2]
    assert result["exhaustive"] is True
    assert result["leftCount"] == result["rightCount"] == 1
    assert evaluate("""scope.compareNeighborhoods(
      {group:'Aves',backbone:'a',records:[{id:1,neighbors:[]}]},
      {group:'Aves',backbone:'b',records:[{id:1,neighbors:[]}]},1)""") == {
        "status": "insufficient_pool",
    }


def test_representation_rgb_is_same_render_value_and_old_payload_disables_mode():
    assert evaluate("scope.representationColor([0,128,255])") == "rgb(0,128,255)"
    assert evaluate("scope.representationColor([0,Infinity,255])") == "#808080"
    assert evaluate("scope.representationColor([0,256,255])") == "#808080"
    assert evaluate("scope.hasRepresentationColors({records:[{id:1}]})") is False
    assert (
        evaluate(
            "scope.hasRepresentationColors({representation_colors:{variance_retained:.2},records:[{rgb:[0,128,255]}]})"
        )
        is True
    )
    assert evaluate('scope.matches([{id:1,name:"Bird"}],{term:"Bird"}).length') == 1


def test_bounded_marker_hit_prefers_nearest_center_not_render_order():
    assert (
        evaluate("""scope.nearestMarker([
      {index:1,id:101,x:10,y:10},{index:2,id:102,x:4,y:3}],{x:0,y:0})""")
        == 2
    )
    assert (
        evaluate("""scope.nearestMarker([
      {index:1,id:101,x:13,y:0}],{x:0,y:0})""")
        is None
    )
    assert evaluate("scope.nearestMarker([],{x:0,y:0})") is None


def test_marker_hit_radius_boundary_and_stable_id_ties():
    assert (
        evaluate("""scope.nearestMarker([
      {index:1,id:101,x:12,y:0}],{x:0,y:0})""")
        == 1
    )
    assert (
        evaluate("""scope.nearestMarker([
      {index:1,id:102,x:3,y:4},{index:2,id:101,x:-3,y:-4}],{x:0,y:0})""")
        == 2
    )
    assert (
        evaluate("""scope.nearestMarker([
      {index:2,id:101,x:-3,y:-4},{index:1,id:102,x:3,y:4}],{x:0,y:0})""")
        == 2
    )


def test_marker_projection_handles_wrapped_world_copy():
    assert evaluate("scope.nearestLongitude(-123,237)") == 237
    assert evaluate("scope.nearestLongitude(179,-181)") == -181
    assert evaluate("scope.nearestLongitude(-123,-124)") == -123


def test_marker_hits_expose_all_overlap_ids_and_deduplicate_world_copies():
    candidates = [dict(index=i, id=100 + i, x=5, y=5) for i in range(98)]
    candidates += [dict(index=0, id=100, x=5, y=5), dict(index=98, id=198, x=30, y=30)]
    assert evaluate(f"scope.markerHits({json.dumps(candidates)}, {{x:5,y:5}})") == list(range(98))
    candidates.reverse()
    assert evaluate(f"scope.markerHits({json.dumps(candidates)}, {{x:5,y:5}})") == list(range(98))


def test_marker_hits_preserve_nearest_order_boundary_and_empty_states():
    assert evaluate("scope.markerHits([], {x:0,y:0})") == []
    assert evaluate("scope.markerHits([{index:1,id:1,x:NaN,y:0}], {x:0,y:0})") == []
    assert evaluate("scope.markerHits([{index:1,id:1,x:0,y:0}], {x:NaN,y:0})") == []
    assert evaluate("""scope.markerHits([
        {index:2,id:2,x:12,y:0},{index:3,id:3,x:0,y:0},
        {index:2,id:2,x:1,y:0},{index:4,id:4,x:12.01,y:0}],{x:0,y:0})""") == [3, 2]


def test_projection_description_distinguishes_method_and_optional_local_fidelity():
    text = evaluate("""scope.projectionSummary({projection:'t-SNE',variance_retained:.12,
      projection_quality:{k:12,mean_neighbor_recall:.4},
      records:[{projection_match_count:4}]},0)""")
    assert "t-SNE layout" in text and "PCA" not in text
    assert "12 nearest points on this layout contain 4" in text
    assert "12 full-space matches" in text
    text = evaluate(
        "scope.projectionSummary({projection:'PCA',variance_retained:.12,records:[{}]},0)"
    )
    assert "PCA retains 12.0%" in text
    assert "nearest points" not in text


def test_layout_alternate_requires_complete_finite_coordinates_and_non_pca_primary():
    payload = dict(
        projection="t-SNE",
        records=[dict(xy=[1, 2], pca_xy=[3, 4]), dict(xy=[5, 6], pca_xy=[7, 8])],
    )
    assert evaluate(f"scope.hasPcaAlternative({json.dumps(payload)})") is True
    assert evaluate(f"scope.projectionCoordinates({json.dumps(payload)},'pca')") == [[3, 4], [7, 8]]
    assert evaluate(f"scope.projectionCoordinates({json.dumps(payload)})") == [[1, 2], [5, 6]]
    payload["records"][1].pop("pca_xy")
    assert evaluate(f"scope.hasPcaAlternative({json.dumps(payload)})") is False
    assert evaluate(f"scope.projectionCoordinates({json.dumps(payload)},'pca')") == [[1, 2], [5, 6]]
    assert (
        evaluate("scope.hasPcaAlternative({projection:'t-SNE',records:[{pca_xy:[0,NaN]}]})")
        is False
    )
    assert evaluate("scope.hasPcaAlternative({projection:'PCA',records:[{pca_xy:[0,1]}]})") is False
    assert evaluate("scope.hasPcaAlternative({projection:'t-SNE',records:[]})") is False


def test_layout_summary_switches_method_and_matching_diagnostic_without_changing_payload():
    payload = dict(
        projection="t-SNE",
        variance_retained=0.12,
        projection_quality=dict(k=12, mean_neighbor_recall=0.8),
        pca_projection_quality=dict(k=12, mean_neighbor_recall=0.2),
        records=[
            dict(xy=[0, 1], pca_xy=[2, 3], projection_match_count=10, pca_projection_match_count=3)
        ],
    )
    primary = evaluate(f"scope.projectionSummary({json.dumps(payload)},0)")
    alternate = evaluate(f"scope.projectionSummary({json.dumps(payload)},0,'pca')")
    assert "Local t-SNE layout" in primary and "contain 10" in primary
    assert "PCA retains 12.0%" in alternate and "contain 3" in alternate
    assert payload["records"][0]["xy"] == [0, 1]
    payload["projection"] = "PCA"
    payload["projection_metadata"] = dict(
        requested_method="t-SNE", fallback_reason="constant vectors"
    )
    fallback = evaluate(f"scope.projectionSummary({json.dumps(payload)},0)")
    assert "PCA fallback for this sample" in fallback
    assert "Local t-SNE layout" not in fallback


def test_taxonomy_scopes_distinguish_verified_partial_unknown_and_name_lookalikes():
    records = [
        dict(
            id=1,
            name="Atrichum undulatum",
            taxon_id=11,
            ancestor_taxon_ids=[11, 311249, 1],
            taxonomy_complete=True,
        ),
        dict(id=2, name="Mosses", taxon_id=20, ancestor_taxon_ids=[20, 1], taxonomy_complete=True),
        dict(
            id=3,
            name="Different recorded name",
            taxon_id=12,
            ancestor_taxon_ids=[12, 311249, 999],
            taxonomy_complete=False,
        ),
        dict(id=4, name="Mosses", taxon_id=99, ancestor_taxon_ids=[99], taxonomy_complete=False),
        dict(id=5, name="Plants", taxon_id=1, ancestor_taxon_ids=[1], taxonomy_complete=True),
    ]
    encoded = json.dumps(records)
    assert evaluate(f"{encoded}.map(r=>scope.taxonMembership(r,[311249]))") == [
        True,
        False,
        True,
        None,
        False,
    ]
    assert evaluate(f"scope.taxonCounts({encoded},[311249])") == dict(
        verified=2, excluded=2, unknown=1
    )
    selected = evaluate(f"scope.matches({encoded},{{taxonRoots:[311249]}})")
    assert [r["r"]["id"] for r in selected] == [1, 3]
    assert [r["i"] for r in selected] == [0, 2]
    assert evaluate(f"scope.matches({encoded},{{taxonRoots:[311249],term:'Mosses'}})") == []
    assert evaluate(f"scope.matches({encoded},{{term:'Mosses'}}).map(x=>x.r.id)") == [2, 4]
    assert evaluate(
        f"scope.matches({encoded},{{taxonRoots:[311249],term:'Atrichum'}}).map(x=>x.r.id)"
    ) == [1]


def test_taxonomy_scope_intersects_search_map_brush_and_existing_order():
    records = [
        dict(
            id=i,
            name="Species",
            lon=lon,
            lat=49,
            reference_distance=distance,
            taxon_id=i,
            ancestor_taxon_ids=[i, 311249, 1],
            taxonomy_complete=True,
        )
        for i, lon, distance in [(11, -123, 0.2), (12, -123, 0.9), (13, -100, 1), (14, -123, 2)]
    ]
    options = dict(
        taxonRoots=[311249],
        term="Species",
        bounds=[-124, 48, -122, 50],
        onlyInView=True,
        onlyBrushed=True,
        brushedIndices=[0, 1, 2],
        order="reference",
        hasReference=True,
    )
    selected = evaluate(f"scope.matches({json.dumps(records)},{json.dumps(options)})")
    assert [r["r"]["id"] for r in selected] == [12, 11]
    options["taxonRoots"] = [56327]
    assert evaluate(f"scope.matches({json.dumps(records)},{json.dumps(options)})") == []
    options["taxonRoots"] = None
    assert len(evaluate(f"scope.matches({json.dumps(records)},{json.dumps(options)})")) == 2


@pytest.mark.parametrize(
    "record",
    [
        {},
        dict(taxon_id=None, ancestor_taxon_ids=[], taxonomy_complete=False),
        dict(taxon_id=1, ancestor_taxon_ids=[1, "311249"], taxonomy_complete=True),
        dict(taxon_id=1, ancestor_taxon_ids=[311249], taxonomy_complete=True),
        dict(taxon_id=1, ancestor_taxon_ids=[1, 311249, 1], taxonomy_complete=True),
        dict(taxon_id=1, ancestor_taxon_ids=[1, 311249], taxonomy_complete="true"),
    ],
)
def test_corrupt_or_missing_ancestry_is_unknown_not_a_verified_scope(record):
    assert evaluate(f"scope.taxonMembership({json.dumps(record)},[311249])") is None


def test_taxon_presets_require_explicit_build_metadata_and_valid_root_ids():
    assert evaluate("scope.taxonPresets({records:[{name:'Mosses'}]})") == []
    valid = dict(label="Bryophytes", taxon_ids=[311249], approximate=False)
    invalid = [
        dict(label="Guessed", taxon_ids=["311249"], approximate=False),
        dict(label="Empty", taxon_ids=[], approximate=False),
    ]
    assert evaluate(
        f"scope.taxonPresets({json.dumps(dict(taxonomy=dict(presets=[valid, *invalid])))})"
    ) == [valid]
