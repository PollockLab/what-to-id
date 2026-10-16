/* Bounded, versioned filter transfer. Result IDs verify criteria, never filter them. */
const AtlasContext = (() => {
  const MAX_IDS = 1000, MAX_TEXT = 100000;
  const validId = id => Number.isSafeInteger(id) && id > 0;
  const sha = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  function ids(value) {
    return Array.isArray(value) && value.length <= MAX_IDS && value.every(validId) &&
      new Set(value).size === value.length;
  }
  function validate(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || value.v !== 1 ||
        typeof value.group !== 'string' || !value.group.length || value.group.length > 80 ||
        !sha(value.poolSha) || !(value.taxonomySha === null || sha(value.taxonomySha)) ||
        typeof value.q !== 'string' || value.q.length > 1000 ||
        typeof value.fromLabel !== 'string' || value.fromLabel.length > 100 ||
        !ids(value.taxonRoots) || !ids(value.brushIds) || !ids(value.resultIds) ||
        typeof value.taxonExclude !== 'boolean' || typeof value.onlyBrushed !== 'boolean' ||
        (!value.taxonRoots.length && value.taxonExclude) ||
        new Set([...value.brushIds, ...value.resultIds]).size > MAX_IDS) throw Error('Invalid transferred filter context.');
    if (value.geoBounds !== null) {
      const b = value.geoBounds;
      if (!Array.isArray(b) || b.length !== 4 || !b.every(Number.isFinite) ||
          Math.abs(b[0]) > 1e6 || Math.abs(b[2]) > 1e6 || Math.abs(b[2] - b[0]) > 3600 ||
          b[1] < -90 || b[3] > 90 || b[1] > b[3]) throw Error('Invalid transferred map bounds.');
    }
    return value;
  }
  function decode(text) {
    if (typeof text !== 'string' || text.length > MAX_TEXT) throw Error('Transferred filter context is too large.');
    try {return validate(JSON.parse(text));}
    catch (error) {throw Error(error instanceof SyntaxError ? 'Malformed transferred filter context.' : error.message);}
  }
  function encode(value) {
    const text = JSON.stringify(validate(value));
    if (text.length > MAX_TEXT) throw Error('Transferred filter context is too large.');
    return text;
  }
  function sameIds(left, right) {
    const other = new Set(right);
    return left.length === other.size && left.every(id => other.has(id));
  }
  function verify(expected, records, matchedIds) {
    const available = new Set(records.map(record => record.id)), actual = new Set(matchedIds);
    const wanted = new Set(expected);
    const missingTarget = expected.filter(id => !available.has(id)).length;
    const missing = expected.filter(id => !actual.has(id)).length;
    const unexpected = matchedIds.filter(id => !wanted.has(id)).length;
    return {ok: missing === 0 && unexpected === 0, missing, unexpected, missingTarget};
  }
  function restore(value, payload, metadata, scope) {
    const context = validate(value);
    if (payload.records.length > MAX_IDS || payload.group !== context.group ||
        metadata.pool_sha256 !== context.poolSha) throw Error('The transferred source pool does not match this view.');
    let presetIndex = -1, taxonId = null;
    if (context.taxonRoots.length) {
      if (!context.taxonomySha || payload.taxonomy?.cache_sha256 !== context.taxonomySha)
        throw Error('The transferred taxonomy does not match this view.');
      presetIndex = scope.taxonPresets(payload).findIndex(preset =>
        sameIds(context.taxonRoots, preset.taxon_ids) && (preset.exclude === true) === context.taxonExclude);
      if (presetIndex < 0) {
        if (!context.taxonExclude && context.taxonRoots.length === 1 &&
            scope.taxonCatalog(payload).some(taxon => taxon.id === context.taxonRoots[0]))
          taxonId = context.taxonRoots[0];
        else throw Error('The transferred ancestry scope is unavailable in this view.');
      }
    }
    const index = new Map(payload.records.map((record, i) => [record.id, i]));
    if (index.size !== payload.records.length || !payload.records.every(record => validId(record.id)))
      throw Error('This view has invalid observation IDs.');
    const missingBrush = context.brushIds.filter(id => !index.has(id)).length;
    const brushedIndices = context.brushIds.filter(id => index.has(id)).map(id => index.get(id));
    const options = {term: context.q, taxonRoots: context.taxonRoots.length ? context.taxonRoots : null,
      taxonExclude: context.taxonExclude, brushedIndices, onlyBrushed: context.onlyBrushed,
      bounds: context.geoBounds, onlyInView: context.geoBounds !== null};
    const matchedIds = scope.matches(payload.records, options).map(({r}) => r.id);
    const verification = verify(context.resultIds, payload.records, matchedIds);
    return {presetIndex, ...(taxonId === null ? {} : {taxonId}), brushedIndices, missingBrush, ...verification,
      ok: verification.ok && missingBrush === 0};
  }
  return {MAX_IDS, MAX_TEXT, decode, encode, restore, verify};
})();
if (typeof module !== 'undefined') module.exports = AtlasContext;
