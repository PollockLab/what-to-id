// Every user-facing string the compare panel adds, in one place, so the EN/FR dictionary can take them over in one step.
// Functions take the numbers and names a sentence needs; the panel never builds a sentence of its own.
var IdentifyText={
  role:{label:'Label',suggested:'Suggested',lookalike:'Look-alike',runnerup:'Runner-up',similar:'Similar'},
  loading:'Loading reference photos…',
  noSpecies:'No species named to compare with.',
  noSimilar:'iNaturalist lists no similar species for it.',
  noPhoto:'No reference photo',
  taxonPage:'Taxon page',
  taxonPageOf:function(n){return 'Taxon page of '+n+' on iNaturalist';},
  photos:function(n){return n+(n===1?' photo':' photos');},
  refPhoto:function(role,n){return role+' '+n+', reference photo';},
  prevPhotos:'Earlier reference photos',
  nextPhotos:'More reference photos',
  refGroup:function(n){return 'Reference photos of '+n;},
  loadingObs:'Loading photos…',
  noObs:'No photo on iNaturalist now',
  obsPhoto:function(k,n){return 'Observation photo '+k+' of '+n;},
  thumb:function(k,n){return 'Photo '+k+' of '+n;},
  zoomIn:function(k,n){return 'Zoom in on photo '+k+' of '+n+' (z)';},
  zoomOut:function(k,n){return 'Zoom out of photo '+k+' of '+n+' (z)';},
  dateUnknown:'Date unknown',
  placeUnknown:'Place unknown',
  rangeIn:'Record in range',
  rangeOut:'Record outside range',
  rangeNone:'No range map',
  rangeLabel:function(n,inside){return 'Range of '+n+' in British Columbia: the record is '+(inside?'inside':'outside')+' it';},
  keys:'Up and down: species. Left and right: its photos, with Shift the record’s. Z: zoom. j and k: other records. Esc: close. The dot on each map is this record.'
};
