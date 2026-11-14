// Canadian French for the Identify page: the one place its words are kept (read by identify_i18n.js).
// words: a line's English text (blanks inside it count as one) to its French. rules: [regex, replacement] for lines with numbers or
// names in them; every result gets a no-break space before % and in thousands (fix() in identify_i18n.js). In a regex source, # is a number.
var I18N_FR=(function(){
var MO={January:'janvier',February:'février',March:'mars',April:'avril',May:'mai',June:'juin',July:'juillet',August:'août',
  September:'septembre',October:'octobre',November:'novembre',December:'décembre',Jan:'janv.',Feb:'févr.',Mar:'mars',Apr:'avr.',
  Jun:'juin',Jul:'juill.',Aug:'août',Sep:'sept.',Oct:'oct.',Nov:'nov.',Dec:'déc.'};
function T(s){return typeof I18N==='undefined'?s:I18N.tr(s);}
function pl(n,a,b){return +String(n).replace(/\D/g,'')>1?b:a;}
// "15 October 2026" and "10 Aug 2026" in French: months by name, and 1er
function D(s){return s.replace(/\b(\d{1,2}) ([A-Z][a-z]+)\b/g,function(m,d,mo){return MO[mo]?(d==='1'?'1er':d)+' '+MO[mo]:m;}).replace(/\b([A-Z][a-z]+) (\d{4})\b/g,function(m,mo,y){return MO[mo]?MO[mo]+' '+y:m;});}
function R(src,to){return [new RegExp('^'+src.replace(/#/g,'(\\d[\\d ,.]*)')+'$'),to];}
function C(n){return n.replace('.',',');}
function G(n){return T(n);}  // a group or level name inside a longer line
var DL=" Photos downloaded on ",SC="Scored on ";
function when(s){
  var m=/^ Photos downloaded on (.+), scored on (.+)\.$/.exec(s);if(m)return ' Photos téléchargées le '+D(m[1])+', évaluées le '+D(m[2])+'.';
  m=/^ Photos downloaded on (.+)\.$/.exec(s);if(m)return ' Photos téléchargées le '+D(m[1])+'.';
  m=/^ Scored on (.+)\.$/.exec(s);return m?' Évaluées le '+D(m[1])+'.':s;
}
var CLICK="Cliquez pour choisir, de nouveau pour ",CLEAR="effacer.";
var words={
// the page
"Identify: What to ID next":"Identifier : quoi identifier ensuite","What to ID":"What to ID","Skip to content":"Passer au contenu",
"Close":"Fermer","Close (Esc)":"Fermer (Échap)","Loading…":"Chargement…","Settings":"Paramètres","Language":"Langue","Species names":"Noms des espèces",
"English":"English","Français":"Français","Latin":"Latin","Common":"Commun","Both":"Les deux","Methods":"Méthodes","Identify":"Identifier",
"Identify (Enter)":"Identifier (Entrée)","Identify on iNaturalist (Enter)":"Identifier sur iNaturalist (Entrée)","openbiodiversity.ca":"openbiodiversity.ca",
"(opens in a new tab)":"(s'ouvre dans un nouvel onglet)","· BC":"· C.-B.","About":"À propos","About this page":"À propos de cette page",
"About, notes and keys":"À propos, notes et raccourcis","Notes and keys":"Notes et raccourcis","Notes":"Notes",
// groups and bar
"Life forms":"Formes de vie","What, when, where, who":"Quoi, quand, où, qui","What":"Quoi","When":"Quand","Where":"Où","Who":"Qui",
"All groups":"Tous les groupes","Anywhere":"Partout","Anyone":"Tout le monde","Any time":"En tout temps","Your groups":"Vos groupes",
"Show all":"Tout afficher","Find a taxon":"Chercher un taxon","Latin or common name, e.g. Carex":"Nom latin ou commun, p. ex. Carex",
"Matching taxa":"Taxons correspondants","Taxon shortcuts":"Raccourcis de taxons","Taxon groups":"Groupes de taxons","Show only":"Afficher seulement",
"Browse the same selection full screen:":"Parcourir la même sélection en plein écran :","in photo space":"dans l'espace des photos",
"in the taxonomy":"dans la taxonomie","Location accuracy":"Précision de la localisation","Any location accuracy":"Toute précision de localisation",
"No accuracy reported for the location. Click to pick.":"Aucune précision signalée pour la localisation. Cliquez pour choisir.",
"Any":"Peu importe","Known":"Connue","Unknown only":"Inconnue seulement","Leave out":"Exclure","Clear the species filter":"Effacer le filtre d'espèce",
"Reload for this view":"Recharger pour cette vue","No records in view":"Aucune observation en vue","Loading your filters…":"Chargement de vos filtres…",
"Amphibians":"Amphibiens","Birds":"Oiseaux","Fish":"Poissons","Insects":"Insectes","Mammals":"Mammifères","Molluscs":"Mollusques","Plants":"Plantes",
"Reptiles":"Reptiles","Other animals":"Autres animaux","Spiders and allies":"Araignées et apparentés","Kelp and allies":"Varech et apparentés",
"Fungi and lichens":"Champignons et lichens","Slime moulds":"Myxomycètes","Unknown":"Inconnu","Bryophytes":"Bryophytes","Lichens":"Lichens",
"Hornworts, mosses and liverworts":"Anthocérotes, mousses et hépatiques","Fungi Including Lichens":"Champignons, lichens compris",
"The main lichen-forming fungi; approximate, as lichens are no single clade":"Les principaux champignons lichénisés; approximatif, car les lichens ne forment pas un seul clade",
"Invasive":"Envahissantes","Threatened":"Menacées","Introduced to BC":"Introduites en C.-B.","One ID from Research Grade":"À une identification de Qualité recherche",
"Species with a threatened status. Click to pick, again to leave out, again to clear.":"Espèces ayant un statut de menace. Cliquez pour choisir, de nouveau pour exclure, de nouveau pour effacer.",
"Species not native to BC. Click to pick, again to leave out, again to clear.":"Espèces non indigènes de la C.-B. Cliquez pour choisir, de nouveau pour exclure, de nouveau pour effacer.",
"Species where one more agreeing ID makes the record Research Grade, so agree only with an ID you would make yourself from the photos. Click to pick, again to leave out, again to clear.":"Espèces pour lesquelles une identification concordante de plus donne la Qualité recherche; n'approuvez donc qu'une identification que vous feriez vous-même d'après les photos. Cliquez pour choisir, de nouveau pour exclure, de nouveau pour effacer.",
"Records more than 50 km outside the iNaturalist range map of their label, so the ID or the location deserves a second look. Click to pick, again to leave out, again to clear.":"Observations à plus de 50 km de la carte de répartition iNaturalist de leur étiquette; l'identification ou la localisation mérite un second regard. Cliquez pour choisir, de nouveau pour exclure, de nouveau pour effacer.",
"The species, subspecies and varieties of the Conservation Challenge list":"Les espèces, sous-espèces et variétés de la liste du Défi de conservation",
"Pick several groups, or leave some out, in What":"Choisissez plusieurs groupes, ou excluez-en, sous Quoi",
"Open with these groups next time, in this browser":"Ouvrir avec ces groupes la prochaine fois, dans ce navigateur",
"Remember these groups":"Mémoriser ces groupes","Add another project for Identify only":"Ajouter un autre projet pour Identifier seulement",
"Project number or URL":"Numéro ou URL du projet","Add":"Ajouter","Sign out":"Se déconnecter","Login or number":"Identifiant ou numéro",
"iNat login":"Identifiant iNat","iNaturalist login or user number":"Identifiant iNaturalist ou numéro d'utilisateur","Your iNaturalist login":"Votre identifiant iNaturalist",
"Projects":"Projets","User":"Utilisateur","Adjust":"Ajuster","Group":"Groupe","Match":"Correspond","Only the user's genera":"Seulement les genres de l'utilisateur",
"Hide records the user identified":"Masquer les observations identifiées par l'utilisateur","Only records the user observed":"Seulement les observations de l'utilisateur",
"Keeps only the records inside the user's genera.":"Ne garde que les observations dans les genres de l'utilisateur.",
"Hides the records this user has already identified. Remembered for the next login.":"Masque les observations que cet utilisateur a déjà identifiées. Mémorisé pour la prochaine connexion.",
"Keeps only the records this user observed. Off while Hide records the user identified is ticked.":"Ne garde que les observations de cet utilisateur. Désactivé tant que « Masquer les observations identifiées par l'utilisateur » est coché.",
"Enter a user name first":"Saisissez d'abord un nom d'utilisateur","Reset to defaults":"Rétablir les valeurs par défaut",
"Automatic (80% of their IDs)":"Automatique (80 % de leurs identifications)",
// when
"Observed":"Observées","Uploaded":"Téléversées","Date to filter on":"Date de filtrage","Periods":"Périodes","Months of the year":"Mois de l'année",
"From":"Du","To":"Au","to":"au","Any month":"Tous les mois","Last 30 days":"30 derniers jours","Last 12 months":"12 derniers mois","This year":"Cette année",
"Records per year, every year, on a log scale. Click a year to zoom to it.":"Observations par année, toutes les années, à l'échelle logarithmique. Cliquez sur une année pour l'agrandir.",
"Expand map":"Agrandir la carte","Jan":"janv.","Feb":"févr.","Mar":"mars","Apr":"avr.","May":"mai","Jun":"juin","Jul":"juill.","Aug":"août","Sep":"sept.","Oct":"oct.","Nov":"nov.","Dec":"déc.",
"January":"janvier","February":"février","March":"mars","April":"avril","June":"juin","July":"juillet","August":"août","September":"septembre",
"October":"octobre","November":"novembre","December":"décembre",
// levels, tabs, sorting
"Level":"Niveau","Easy confirms":"Confirmations faciles","Might be wrong":"Peut-être erroné","Narrow it down":"À préciser","Batches":"Lots",
"vs":"contre","Likely mislabelled":"Probablement mal étiquetées","Odd shots":"Photos inhabituelles","Close calls":"Cas limites","Kind":"Genre","Kind:":"Genre :",
"These look just like their label. Confirm many in one go.":"Celles-ci ressemblent tout à fait à leur étiquette. Confirmez-en plusieurs d'un coup.",
"The photo is a hard shot, or another species matches it about as well or better. Check whether the label is right.":"La photo est difficile, ou une autre espèce lui correspond à peu près aussi bien, voire mieux. Vérifiez si l'étiquette est juste.",
"Labelled above species, and the photo points to one species of it. Take it to species.":"Étiquetée au-dessus de l'espèce, et la photo mène à une espèce de ce groupe. Poussez l'identification jusqu'à l'espèce.",
"Labelled at species, and the photo looks just like its label.":"Étiquetée à l'espèce, et la photo ressemble tout à fait à son étiquette.",
"Labelled above species, and the photo points to one species of it.":"Étiquetée au-dessus de l'espèce, et la photo mène à une espèce de ce groupe.",
"Records whose photo may not support the label: likely mislabels first, then odd shots, then close calls.":"Observations dont la photo ne confirme peut-être pas l'étiquette : d'abord les erreurs probables, puis les photos inhabituelles, puis les cas limites.",
"The photo matches another species clearly better than its label.":"La photo correspond nettement mieux à une autre espèce qu'à son étiquette.",
"Another species looks almost as likely as the label, or it may be something else.":"Une autre espèce paraît presque aussi probable que l'étiquette, ou il peut s'agir d'autre chose.",
"Hard photos, like hands, eggs and close-ups, that match no species well.":"Photos difficiles, comme des mains, des œufs et des gros plans, qui ne correspondent bien à aucune espèce.",
"Prioritize":"Prioriser","Range":"Aire","Then":"Puis","Shuffle":"Mélanger","newest":"plus récentes","oldest":"plus anciennes","random":"au hasard",
"Newest":"Plus récentes","Quick wins":"Gains rapides","Unusual":"Inhabituelles","Blitz the gap":"Combler la lacune","Survey gap":"Lacune d'inventaire",
"Label":"Étiquette","Combine":"Combiner","Best":"Meilleurs","Fewest IDs in a genus":"Moins d'identifications dans un genre","Fewest survey days":"Moins de jours d'inventaire",
"Biggest survey gaps first, then at-risk species, then best matches":"D'abord les plus grandes lacunes d'inventaire, puis les espèces à risque, puis les meilleures correspondances",
"Biggest survey gaps first, then at-risk species, then best matches (reading the where-to-blitz checklist…)":"D'abord les plus grandes lacunes d'inventaire, puis les espèces à risque, puis les meilleures correspondances (lecture de la liste des lieux à blitzer…)",
"Biggest survey gaps first, then best matches":"D'abord les plus grandes lacunes d'inventaire, puis les meilleures correspondances",
"Biggest survey gaps first, then best matches (reading the where-to-blitz checklist…)":"D'abord les plus grandes lacunes d'inventaire, puis les meilleures correspondances (lecture de la liste des lieux à blitzer…)",
"by how each photo matches its label.":"selon la correspondance de chaque photo avec son étiquette.","sorted for review":"triées pour révision",
"Records":"Observations","Records sorted for review":"Observations triées pour révision","How this works":"Comment ça fonctionne","How it works: Methods":"Comment ça fonctionne : Méthodes",
"Show":"Afficher","Show more":"Afficher plus","Skip":"Passer","Skip (s)":"Passer (s)","Copy":"Copier","Copied":"Copié","Copy failed":"Échec de la copie",
"Next batch":"Lot suivant","Previous batch":"Lot précédent","Next batch (N)":"Lot suivant (N)","Next card (j)":"Carte suivante (j)","Previous card (k)":"Carte précédente (k)",
"Start over":"Recommencer","Download my batches":"Télécharger mes lots","Study batches":"Lots d'étude",
"These batches come from a research study.":"Ces lots proviennent d'une étude de recherche.","You have seen every batch in this group.":"Vous avez vu tous les lots de ce groupe.",
"No records at this level here.":"Aucune observation à ce niveau ici.","None at this level here. Try":"Aucune à ce niveau ici. Essayez",
"Loading all the records for this selection…":"Chargement de toutes les observations de cette sélection…","Showing the top records, loading all of them…":"Affichage des meilleures observations, chargement de toutes en cours…",
"Reading the map data…":"Lecture des données cartographiques…","Loading photo":"Chargement de la photo","Loading photos…":"Chargement des photos…",
"Loading reference photos…":"Chargement des photos de référence…","No reference photo":"Aucune photo de référence","No photo on iNaturalist now":"Aucune photo sur iNaturalist pour l'instant",
"Date unknown":"Date inconnue","Place unknown":"Lieu inconnu","Your genus":"Votre genre","Unconfirmed":"Non confirmée","Record":"Observation",
"Identify this record on iNaturalist":"Identifier cette observation sur iNaturalist","All":"Toutes","All dates":"Toutes les dates","At risk":"À risque","Date and place…":"Date et lieu…","Most survey days":"Plus de jours d'inventaire","Next photo":"Photo suivante","Previous photo":"Photo précédente","Survey days":"Jours d'inventaire","Taxon page":"Page du taxon","Views":"Vues","Map":"Carte","or":"ou","cards":"cartes","Suggestion in range":"Suggestion dans l'aire","Suggestion not in range":"Suggestion hors de l'aire","Only far outside":"Seulement les très éloignées",
"A project added for Identify only goes into the Identify link but does not change the map or its counts.":"Un projet ajouté pour Identifier seulement va dans le lien Identifier, mais ne change ni la carte ni ses comptes.",
"A record takes the first level whose rule it meets, in this order:":"Une observation prend le premier niveau dont elle remplit la règle, dans cet ordre :",
"Runner-up":"Deuxième choix","Runner-up: no reference photo":"Deuxième choix : aucune photo de référence","Similar":"Semblable","Suggested":"Suggérée",
"Look-alike":"Espèce semblable","Looks more like":"Ressemble davantage à","Probably":"Probablement","Loading photo…":"Chargement de la photo…",
"Fits the label, not the look-alike":"Correspond à l'étiquette, pas à l'espèce semblable","Fits the look-alike, not the label":"Correspond à l'espèce semblable, pas à l'étiquette",
"Out of range":"Hors de l'aire","Outside usual range":"Hors de l'aire habituelle","Just outside range":"Juste hors de l'aire","In range":"Dans l'aire","Range map":"Carte de répartition",
"Outside both ranges: maybe neither":"Hors des deux aires : peut-être ni l'une ni l'autre","Outside both ranges: maybe neither.":"Hors des deux aires : peut-être ni l'une ni l'autre.",
"No range map: range unknown":"Aucune carte de répartition : aire inconnue","No range map for the suggestion":"Aucune carte de répartition pour la suggestion",
"Records far outside their range":"Observations loin de leur aire","Records in the suggested species' range":"Observations dans l'aire de l'espèce suggérée",
"Far outside: 50 km or more from the labelled species' known range in BC. Records with no range map count as in range.":"Loin à l'extérieur : à 50 km ou plus de l'aire connue de l'espèce étiquetée en C.-B. Les observations sans carte de répartition comptent comme dans l'aire.",
"In range: the record's grid cell is in the suggested species' known range in BC. Records with no range map for the suggestion count as not in range.":"Dans l'aire : la cellule de l'observation est dans l'aire connue de l'espèce suggérée en C.-B. Les observations sans carte de répartition pour la suggestion comptent comme hors de l'aire.",
"Species with no Research Grade record in this area yet. Your ID could be its first.":"Espèces sans observation de Qualité recherche dans cette zone pour l'instant. Votre identification pourrait être la première.",
"More →":"Plus →","Click or tap a card to compare.":"Cliquez ou touchez une carte pour comparer.",
"Keys: j next card, k previous, i or Enter Identify (copies the name, opens iNaturalist in one reused tab), c copy the name. Click a card or press Space for the compare panel: j, k, Enter, c, s (skip), u (undo), Esc":"Raccourcis : j carte suivante, k précédente, i ou Entrée Identifier (copie le nom, ouvre iNaturalist dans un onglet réutilisé), c copier le nom. Cliquez sur une carte ou appuyez sur Espace pour le panneau de comparaison : j, k, Entrée, c, s (passer), u (annuler), Échap",
"Click or tap a card to compare. On a keyboard, Enter opens iNat with the name copied (press i there to suggest an ID), j and k go to the next and previous card, s skips and u undoes.":"Cliquez ou touchez une carte pour comparer. Au clavier, Entrée ouvre iNat avec le nom copié (appuyez sur i pour proposer une identification), j et k passent à la carte suivante et précédente, s passe et u annule.",
"Up to 3 per species":"Jusqu'à 3 par espèce","Up to 3 per suggested species":"Jusqu'à 3 par espèce suggérée","Research Grade here":"Qualité recherche ici","Research Grade here:":"Qualité recherche ici :",
"Confused pairs":"Confusions","Conservation Challenge":"Défi de conservation","BC Biodiversity Program":"BC Biodiversity Program","none":"aucun","off":"désactivé","enough":"assez","in a level":"dans un niveau","Hide far outside":"Masquer les très éloignées",
// About
"Labelled at species. The margin is above 0, and the record is in the top 25% of its species by match score to the label. Only species with 4 or more scored records.":"Étiquetée à l'espèce. La marge est supérieure à 0, et l'observation est dans le quart supérieur de son espèce selon le score de correspondance avec l'étiquette. Seulement les espèces ayant 4 observations évaluées ou plus.",
"Labelled above species (a genus or a family, say), and the pool names one or more species inside the label. Every such record goes here, whatever its match scores.":"Étiquetée au-dessus de l'espèce (un genre ou une famille, par exemple), et le bassin nomme une ou plusieurs espèces de cette étiquette. Toute observation de ce type va ici, quels que soient ses scores de correspondance.",
"Three kinds of record, in this order: might be mislabelled (lowest margin first), odd shots, close calls. This order put the records iNaturalist identifiers later corrected nearer the top than mixing the three did. Odd shots: any rank, the photo's best match score to any species is in the lowest 2% of its group (birds, plants, fungi and so on). Close calls: labelled at species, one other species scores higher than the label by 0.02 or less and has 20 or more verifiable iNaturalist records in BC. Might be mislabelled: labelled at species, the margin is below −0.02 and the best other species has 20 or more verifiable iNaturalist records in BC. Close calls and might-be-mislabelled cards name that species and show a reference photo of it beside one of the label, from iNaturalist.":"Trois types d'observations, dans cet ordre : peut-être mal étiquetées (marge la plus faible d'abord), photos inhabituelles, cas limites. Cet ordre a placé plus haut les observations que des identificateurs d'iNaturalist ont corrigées par la suite que ne l'a fait un mélange des trois. Photos inhabituelles : à tout rang, le meilleur score de correspondance de la photo avec n'importe quelle espèce est parmi les 2 % les plus bas de son groupe (oiseaux, plantes, champignons, etc.). Cas limites : étiquetée à l'espèce, une autre espèce obtient un score supérieur à celui de l'étiquette d'au plus 0,02 et compte 20 observations vérifiables ou plus sur iNaturalist en C.-B. Peut-être mal étiquetées : étiquetée à l'espèce, la marge est inférieure à −0,02 et la meilleure autre espèce compte 20 observations vérifiables ou plus sur iNaturalist en C.-B. Les cartes des cas limites et des observations peut-être mal étiquetées nomment cette espèce et montrent une photo de référence de celle-ci à côté d'une photo de l'étiquette, tirées d'iNaturalist.",
"No level":"Aucun niveau","A level sorts records for review. It does not say that a label is right or wrong.":"Un niveau trie les observations pour révision. Il ne dit pas qu'une étiquette est juste ou erronée.",
"gives the model, every cut-off, and a test of the levels against later corrections.":"donne le modèle, chaque seuil, et un test des niveaux par rapport aux corrections ultérieures.",
"The User box is the map's: with an iNaturalist login it lists first the records in the user's genera, those holding about 80% of their identifications in BC (Adjust sets a number of IDs per genus instead), then a line, then the rest; the map dims the rest. Ticks narrow it, once a user name is entered: Only @login's genera, Hide records @login identified, or Only records @login observed. The login is kept on this device for a day. The login goes only to iNaturalist.":"La boîte Utilisateur est celle de la carte : avec un identifiant iNaturalist, elle liste d'abord les observations dans les genres de l'utilisateur, ceux qui détiennent environ 80 % de ses identifications en C.-B. (Ajuster fixe plutôt un nombre d'identifications par genre), puis une ligne, puis le reste; la carte atténue le reste. Des cases les restreignent, une fois un nom d'utilisateur saisi : Seulement les genres de @identifiant, Masquer les observations identifiées par @identifiant, ou Seulement les observations de @identifiant. L'identifiant est conservé sur cet appareil pendant un jour. L'identifiant n'est envoyé qu'à iNaturalist.",
"With a login, the records inside the user's genera come first and the rest are dimmed on the map: by default the genera holding about 80% of their identifications in BC, or under Adjust those with a set number of IDs. Nothing is hidden by this; the iNaturalist link still leaves out records they identified.":"Avec un identifiant, les observations dans les genres de l'utilisateur viennent en premier et le reste est atténué sur la carte : par défaut les genres détenant environ 80 % de ses identifications en C.-B., ou, sous Ajuster, ceux ayant un nombre fixe d'identifications. Rien n'est masqué par ce réglage; le lien iNaturalist exclut quand même les observations qu'il a identifiées.",
"Use it when you want to confirm many in one go.":"Utilisez-le pour en confirmer plusieurs d'un coup.","Group by suggested species":"Regrouper par espèce suggérée"
};
var rules=[
// the About text with its scoring dates, and the "no level" rule with the photo download
[/^Each record's first photo is compared with the names of the species in the pool by BioCLIP 2\.5 \(ViT-H\/14\), an image and text model trained on the tree of life\. A match score is the cosine between the photo's embedding and the embedding of the text "a photo of <species>"\. The margin is the match score of the label minus the best match score of any other species\.( .*)?$/,
  function(m,t){return "Chaque première photo d'observation est comparée aux noms des espèces du bassin par BioCLIP 2.5 (ViT-H/14), un modèle d'images et de texte entraîné sur l'arbre du vivant. Un score de correspondance est le cosinus entre le plongement de la photo et celui du texte « une photo de <espèce> ». La marge est le score de correspondance de l'étiquette moins le meilleur score de correspondance de toute autre espèce."+(t?when(t):'');}],
[/^All other records: the margin is above 0 but the record is outside the top 25% of its species, or its species has fewer than 4 records; the look-alike has fewer than 20 BC records; the pool names no species inside the label, or the label is a species that was not in the pool at scoring; the record was not in the (.+) photo download \(most were added after it\); or its label changed after scoring\.$/,
  function(m,d){return "Toutes les autres observations : la marge est supérieure à 0 mais l'observation est hors du quart supérieur de son espèce, ou son espèce compte moins de 4 observations; l'espèce semblable compte moins de 20 observations en C.-B.; le bassin ne nomme aucune espèce de l'étiquette, ou l'étiquette est une espèce absente du bassin lors de l'évaluation; l'observation ne figurait pas dans "+(d==='last'?'le dernier téléchargement de photos':'le téléchargement de photos du '+D(d))+" (la plupart y ont été ajoutées après); ou son étiquette a changé après l'évaluation.";}],
// counts
R('#\\+ of their IDs per genus','$1+ de leurs identifications par genre'),
R('(\\d{4}-\\d\\d-\\d\\d) to (\\d{4}-\\d\\d-\\d\\d)','$1 au $2'),
R('# cards',function(m,n){return n+' '+pl(n,'carte','cartes');}),
R('# records',function(m,n){return n+' '+pl(n,'observation','observations');}),
R('# cards \\(up to # per species\\)',function(m,n,k){return n+' '+pl(n,'carte','cartes')+" (jusqu'à "+k+' par espèce)';}),
R('all in # batches of #, in the order shown',function(m,n,k){return 'tous en '+n+' '+pl(n,'lot','lots')+' de '+k+", dans l'ordre affiché";}),
R('first # in # batches of #, in the order shown',function(m,a,n,k){return 'les '+a+' premiers en '+n+' '+pl(n,'lot','lots')+' de '+k+", dans l'ordre affiché";}),
R('# cards to ID \\(# records((?:, [^;]+)?); (up to|all) # per suggested species\\)',function(m,c,r,t,u,k){
  return c+' '+pl(c,'carte','cartes')+' à identifier ('+r+' '+pl(r,'observation','observations')+t.replace('Best ','meilleurs ').replace('in range',"dans l'aire")+'; '+(u==='all'?'toutes':"jusqu'à "+k)+' par espèce suggérée)';}),
R('# opened today',function(m,n){return n+' '+pl(n,'ouverte','ouvertes')+" aujourd'hui";}),
R('# records to identify','$1 observations à identifier'),
R('# of #, (.+?)(?: to (.+))?',function(m,a,b,n,t){return a+' sur '+b+', '+n+(t?' vers '+t:'');}),
R('# of # shown','$1 sur $2 affichées'),R('# of #','$1 sur $2'),
R('Batch # of #','Lot $1 sur $2'),R('Photo # of #','Photo $1 sur $2'),R('Observation photo # of #',"Photo de l'observation $1 sur $2"),R('Unknown, (.+)',function(m,n){return 'Inconnu, '+n;}),
R('Similar (.+), reference photo','Semblable $1, photo de référence'),R('· # per species of # records',function(m,n,r){return '· '+n+' par espèce sur '+r+' '+pl(r,'observation','observations');}),R('· # per species','· $1 par espèce'),
R('Show # cards',function(m,n){return 'Afficher '+n+' '+pl(n,'carte','cartes');}),
R('Show more \\(# left\\)','Afficher plus ($1 restantes)'),
R('Identify the first # on iNaturalist','Identifier les $1 premières sur iNaturalist'),
R('Identify these # on iNaturalist','Identifier ces $1 sur iNaturalist'),
R('(Easy confirms|Might be wrong|Narrow it down|Likely mislabelled|Odd shots|Close calls|All|Suggestion not in range|Suggestion in range|Hide far outside|Only far outside) ?(\\(?#\\)?)',function(m,a,n){return G(a)+' '+n;}),
R('\\+# more (.+)','+$1 autres $2'),
R('Show # more records of (.+)',function(m,n,x){return 'Afficher '+n+' '+pl(n,'autre observation','autres observations')+' de '+x;}),
R('Copy (.+)','Copier $1'),R('Photo of (.+)','Photo de $1'),R('Label (.+), reference photo','Étiquette $1, photo de référence'),
R('Look-alike (.+), reference photo','Espèce semblable $1, photo de référence'),R('Suggested (.+), reference photo','Suggérée $1, photo de référence'),
R('Runner-up (.+), reference photo','Deuxième choix $1, photo de référence'),
R('Taxon page of (.+) on iNaturalist','Page du taxon $1 sur iNaturalist'),R('Identify as (.+) on iNaturalist','Identifier comme $1 sur iNaturalist'),
R('ID as (.+)','Identifier comme $1'),R('Copied (.+), paste in iNat','$1 copié, collez dans iNat'),
R('Second best: (.+?)(?:\\. Margin ([\\d.]+) cosine; under 0\\.010 a close call, under 0\\.040 fair, else clear)?',function(m,n,g){return 'Deuxième meilleure : '+n+(g?'. Marge de '+C(g)+' de cosinus; sous 0,010 un cas limite, sous 0,040 correcte, sinon nette':'');}),R(', close call',', cas limite'),R(', fair margin',', marge correcte'),R(', clear margin',', marge nette'),
R('Best #%','Meilleurs $1 %'),R('Click to keep the Best #%','Cliquez pour garder les meilleurs $1 %'),
// group names with their counts
R('(.+?)(?: \\((\\w+)\\))?\\. Click to pick, again to clear\\.',function(m,n,l){return G(n)+(l?' ('+l+')':'')+'. '+CLICK+CLEAR;}),
R('(.+?)\\. Click to pick, again to leave out, again to clear\\.',function(m,n){return G(n)+'. '+CLICK+'exclure, de nouveau pour '+CLEAR;}),
R('Leave out (.+?)(?: \\((\\w+)\\))?, again to clear\\.',function(m,n,l){return 'Exclure '+G(n)+(l?' ('+l+')':'')+', de nouveau pour '+CLEAR;}),
R('Leave out (.+)',function(m,n){return 'Exclure '+G(n);}),R('Open the ranks under (.+)',function(m,n){return 'Ouvrir les rangs sous '+G(n);}),
R('(.+?)(?: \\((\\w+)\\))?: # of # records \\(([\\d.]+)%\\), # in view',function(m,n,l,a,b,p,v){return G(n)+(l?' ('+l+')':'')+' : '+a+' sur '+b+' observations ('+C(p)+' %), '+v+' en vue';}),
R('Largest groups in view: (.+)',function(m,l){return 'Plus grands groupes en vue : '+l.split(', ').map(function(x){return x.replace(/^(.+?) ([\d.]+%)$/,function(q,a,b){return G(a)+' '+C(b);});}).join(', ');}),
R('Move (.+), position # of #',function(m,n,a,b){return 'Déplacer '+G(n)+', position '+a+' sur '+b;}),
// dates and the histogram
R('One bar per (day|week|month|year), ([^.]+?) to ([^.]+?)\\.( Faint all-record bars show only with bars per month or year\\.)?( Drag to pick a period\\.)?',function(m,u,a,b,f,d){
  return 'Une barre par '+{day:'jour',week:'semaine',month:'mois',year:'année'}[u]+', du '+D(a)+' au '+D(b)+'.'+(f?" Les barres pâles de toutes les observations n'apparaissent qu'avec des barres par mois ou par année.":'')+(d?' Faites glisser pour choisir une période.':'');}),
R('Week of (.+)',function(m,d){return 'Semaine du '+D(d);}),
R('Could not load the photos: (.+)','Impossible de charger les photos : $1')
];
return {words:words,rules:rules};
})();
