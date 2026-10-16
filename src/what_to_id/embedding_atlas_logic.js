/* Public-coordinate filtering, shared by the atlas and its Node regression tests. */
const AtlasScope = (() => {
  function inBounds(record, bounds) {
    if (!bounds || bounds.length !== 4 || !bounds.every(Number.isFinite)) return false;
    const [west, south, east, north] = bounds;
    if (!Number.isFinite(record.lon) || !Number.isFinite(record.lat) || south > north) return false;
    if (record.lat < south || record.lat > north) return false;
    let width = east - west;
    if (width >= 360) return true;
    if (width < 0) width = ((width % 360) + 360) % 360;
    const delta = (((record.lon - west) % 360) + 360) % 360;
    return delta <= width + 1e-9;
  }
  function matches(records, {term = '', bounds = null, onlyInView = false,
                             order = 'sample', hasReference = false, onlyBrushed = false,
                             brushedIndices = [], taxonRoots = null, taxonExclude = false} = {}) {
    const query = term.trim().toLocaleLowerCase();
    const brush = new Set(brushedIndices);
    const result = records.map((r, i) => ({r, i})).filter(({r, i}) =>
      (!onlyBrushed || brush.has(i)) &&
      (!onlyInView || inBounds(r, bounds)) &&
      (taxonRoots === null || taxonMembership(r, taxonRoots, taxonExclude) === true) &&
      `${r.name} ${r.id}`.toLocaleLowerCase().includes(query));
    if (order === 'reference' && hasReference) {
      result.sort((a, b) => b.r.reference_distance - a.r.reference_distance || a.r.id - b.r.id);
    }
    return result;
  }
  function taxonMembership(record, roots, exclude = false) {
    const validId = id => Number.isSafeInteger(id) && id > 0;
    if (typeof exclude !== 'boolean' || !Array.isArray(roots) || !roots.length || !roots.every(validId) ||
        !validId(record?.taxon_id) || typeof record.taxonomy_complete !== 'boolean' ||
        !Array.isArray(record.ancestor_taxon_ids) || !record.ancestor_taxon_ids.every(validId) ||
        !record.ancestor_taxon_ids.includes(record.taxon_id) ||
        new Set(record.ancestor_taxon_ids).size !== record.ancestor_taxon_ids.length) return null;
    if (roots.some(root => record.ancestor_taxon_ids.includes(root))) return !exclude;
    return record.taxonomy_complete ? exclude : null;
  }
  function taxonPresets(payload) {
    if (!Array.isArray(payload?.taxonomy?.presets)) return [];
    return payload.taxonomy.presets.filter(preset => typeof preset?.label === 'string' &&
      preset.label.length > 0 && typeof preset.approximate === 'boolean' &&
      (preset.exclude === undefined || typeof preset.exclude === 'boolean') &&
      Array.isArray(preset.taxon_ids) && preset.taxon_ids.length > 0 &&
      preset.taxon_ids.every(id => Number.isSafeInteger(id) && id > 0));
  }
  function taxonCounts(records, roots, exclude = false) {
    const result = {verified: 0, excluded: 0, unknown: 0};
    records.forEach(record => {
      const state = taxonMembership(record, roots, exclude);
      result[state === true ? 'verified' : state === false ? 'excluded' : 'unknown']++;
    });
    return result;
  }
  function brushIndices(points, rectangle) {
    if (!rectangle || rectangle.length !== 4 || !rectangle.every(Number.isFinite)) return [];
    const [x0, y0, x1, y1] = rectangle;
    const left = Math.min(x0, x1), right = Math.max(x0, x1);
    const top = Math.min(y0, y1), bottom = Math.max(y0, y1);
    return points.flatMap(([x, y], i) => Number.isFinite(x) && Number.isFinite(y) &&
      x >= left && x <= right && y >= top && y <= bottom ? [i] : []);
  }
  function toggleIndex(indices, index) {
    const result = new Set(indices);
    if (result.has(index)) result.delete(index); else result.add(index);
    return [...result].sort((a, b) => a - b);
  }
  function modelHref(relative, base, group, id, context = null) {
    const target = new URL(relative, base);
    const state = new URLSearchParams();
    state.set('group', group);
    if (id !== null && id !== undefined) state.set('id', String(id));
    if (context !== null) state.set('ctx', context);
    target.hash = state.toString();
    return target.href;
  }
  function mapHref(target, base, group, id) {
    const url = new URL(target, base);
    const state = new URLSearchParams({groups: group});
    if (id !== null && id !== undefined) state.set('record', String(id));
    url.hash = state.toString();
    return url.href;
  }
  function resolveSelection(records, requested) {
    const id = Number(requested);
    const valid = requested !== null && requested !== '' && Number.isSafeInteger(id) && id > 0;
    if (!valid) return {index: 0, missingRequestedId: null};
    const index = records.findIndex(record => record.id === id);
    return {index: index < 0 ? 0 : index, missingRequestedId: index < 0 ? id : null};
  }
  function compareNeighborhoods(left, right, queryId) {
    const a = left.records.find(r => r.id === queryId);
    const b = right.records.find(r => r.id === queryId);
    if (!a || !b) return {status: 'missing_query'};
    const leftIds = new Set(left.records.map(r => r.id));
    const rightIds = new Set(right.records.map(r => r.id));
    if (left.group !== right.group || leftIds.size !== left.records.length ||
        rightIds.size !== right.records.length || leftIds.size !== rightIds.size ||
        [...leftIds].some(id => !rightIds.has(id))) return {status: 'pool_mismatch'};
    if (leftIds.size < 2) return {status: 'insufficient_pool'};
    if (left.backbone === right.backbone) return {status: 'same_encoder'};
    function neighbors(payload, record) {
      if (!Array.isArray(record.neighbors)) return null;
      const k = Math.min(12, payload.records.length - 1);
      if (record.neighbors.length < k) return null;
      const result = [];
      for (const entry of record.neighbors.slice(0, k)) {
        const index = Array.isArray(entry) ? entry[0] : null;
        if (!Number.isInteger(index) || !payload.records[index]) return null;
        const id = payload.records[index].id;
        if (id === queryId || result.includes(id)) return null;
        result.push(id);
      }
      return result.length ? result : null;
    }
    const first = neighbors(left, a), second = neighbors(right, b);
    if (!first || !second) return {status: 'invalid_neighbors'};
    const other = new Set(second);
    return {status: 'comparable', leftCount: first.length, rightCount: second.length,
      sharedIds: first.filter(id => other.has(id)), cohortCount: leftIds.size,
      exhaustive: leftIds.size <= 13};
  }
  function hasRepresentationColors(payload) {
    return Boolean(payload.representation_colors) &&
      Number.isFinite(payload.representation_colors.variance_retained) &&
      payload.representation_colors.variance_retained >= 0 &&
      payload.representation_colors.variance_retained <= 1 + 1e-12 &&
      payload.records.every(r => Array.isArray(r.rgb) && r.rgb.length === 3 &&
        r.rgb.every(channel => Number.isInteger(channel) && channel >= 0 && channel <= 255));
  }
  function representationColor(rgb) {
    return Array.isArray(rgb) && rgb.length === 3 &&
      rgb.every(channel => Number.isInteger(channel) && channel >= 0 && channel <= 255)
      ? `rgb(${rgb.join(',')})` : '#808080';
  }
  function hasPcaAlternative(payload) {
    return typeof payload.projection === 'string' && payload.projection.toUpperCase() !== 'PCA' &&
      payload.records.length > 0 && payload.records.every(record =>
        Array.isArray(record.pca_xy) && record.pca_xy.length === 2 && record.pca_xy.every(Number.isFinite));
  }
  function projectionCoordinates(payload, layout = 'primary') {
    const pca = layout === 'pca' && hasPcaAlternative(payload);
    return payload.records.map(record => pca ? record.pca_xy : record.xy);
  }
  function projectionSummary(payload, index, layout = 'primary') {
    const pca = layout === 'pca' && hasPcaAlternative(payload);
    const method = pca ? 'PCA' : typeof payload.projection === 'string' ? payload.projection : '2D';
    let summary = `${method} layout. Distances are approximate; compare the ranked photos.`;
    if (method === 't-SNE') {
      summary = 'Local t-SNE layout. Distant points and gaps do not quantify full-space similarity. Compare the ranked photos.';
    }
    if (method.toUpperCase() === 'PCA' && Number.isFinite(payload.variance_retained)) {
      summary = `PCA retains ${(100 * payload.variance_retained).toFixed(1)}% of variation. Compare the ranked photos.`;
    }
    if (!pca && method === 'PCA' && payload.projection_metadata?.requested_method === 't-SNE') {
      summary = `PCA fallback for this sample. ${summary}`;
    }
    const record = payload.records[index], quality = pca ? payload.pca_projection_quality : payload.projection_quality;
    const count = pca ? record?.pca_projection_match_count : record?.projection_match_count;
    if (quality && record && Number.isInteger(quality.k) && quality.k > 0 &&
        Number.isInteger(count) && count >= 0 && count <= quality.k) {
      summary += ` The ${quality.k} nearest points on this layout contain ${count} of this photo’s ${quality.k} full-space matches.`;
    }
    return summary;
  }
  function markerHits(candidates, point, radius = 12) {
    const hits = new Map();
    for (const candidate of candidates) {
      if (![candidate.x, candidate.y, point.x, point.y].every(Number.isFinite)) continue;
      const distance = (candidate.x - point.x) ** 2 + (candidate.y - point.y) ** 2;
      if (distance > radius * radius) continue;
      const previous = hits.get(candidate.id);
      if (!previous || distance < previous.distance ||
          (distance === previous.distance && candidate.index < previous.index)) {
        hits.set(candidate.id, {...candidate, distance});
      }
    }
    return [...hits.values()].sort((a, b) =>
      a.distance - b.distance || a.id - b.id || a.index - b.index).map(hit => hit.index);
  }
  function nearestMarker(candidates, point, radius = 12) {
    return markerHits(candidates, point, radius)[0] ?? null;
  }
  function nearestLongitude(longitude, reference) {
    return longitude + 360 * Math.round((reference - longitude) / 360);
  }
  function requestGate() {
    let generation = 0;
    return {begin: () => ++generation, cancel: () => {generation++;},
      current: token => token === generation};
  }
  return {inBounds, matches, taxonMembership, taxonPresets, taxonCounts,
    brushIndices, toggleIndex, modelHref, resolveSelection, mapHref,
    compareNeighborhoods, requestGate, representationColor, hasRepresentationColors, hasPcaAlternative, projectionCoordinates, projectionSummary, markerHits, nearestMarker, nearestLongitude};
})();
if (typeof module !== 'undefined') module.exports = AtlasScope;
