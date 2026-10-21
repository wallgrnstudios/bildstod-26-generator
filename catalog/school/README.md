# Skolkatalog: 2 000 ord och korta fraser

Detta är en **redaktionell startkatalog**, inte en uppmätt lista över Sveriges 2 000 vanligaste bildstödsord. Den är ett granskningsunderlag för förskola och grundskola. Innehållet behöver provas med användare och pedagoger. Etiketterna ska inte tolkas som att orden, betydelserna eller bilderna är pedagogiskt godkända.

## Urval

Egen svensk bruttolista om drygt 3 200 etiketter i skol- och vardagsdomäner. Dubbletter normaliseras och tas bort. De tidigare 94 begreppen behålls inklusive avstängda hjälp/paus. Grundläggande kommunikation, behov och skoldag prioriteras; en minimitäckning per kategori hindrar att allmänspråklig frekvens tränger undan skolämnen och specifika behov. Frekvensuppskattningar från wordfreq 3.1.1 används som sorteringsstöd inom prioriteringsnivåerna, inte som förskole-/grundskolefrekvens eller uppmätt frasfrekvens. Underlaget i wordfreq avser språkbruk fram till ungefär 2021. Ord som låter lika eller har flera betydelser kräver avgränsning inom angiven kategori, exempelvis pil (träd/riktning) och bock (idrott/djur).

SPSM:s vägledning om AKK och visuellt stöd har använts för principerna om kommunikation, tydliggörande, användarprövning och begränsade betydelsebärande detaljer. Den verifierar inte denna ordlistas urval eller rangordning:
- https://www.spsm.se/stod-och-rad/sprak-och-kommunikation/alternativ-och-kompletterande-kommunikation/
- https://spsm.se/studiepaket-npf/studiepaket-npf-forskola/tydliggorande-pedagogik-i-forskolan/moment-3--visuellt-stod-i-forskolan/
- https://github.com/rspeer/wordfreq

Ingen ARASAAC-bild, översättning eller katalogmetadata har importerats. Bildmodellen får våra egna avgränsade engelska bildinstruktioner och den befintliga stilreferensen.

## Filer och status

- `vocabulary-2000.json`: exakt 2 000 unika poster med beständigt ID, etikett, kategori, redaktionell prioritet, betydelsestatus och eventuell symbolkoppling.
- `vocabulary-2000.txt`: läsbar ordlista. Radnummer är redaktionell ordning, inte statistisk frekvensrankning.
- `summary.json`: antal och kategorifördelning.
- `editorial-vocabulary.txt`: bredare kandidatunderlag, inte den slutliga 2 000-listan.
- `ready-briefs.json`: egna individuella bildinstruktioner, avgörande detaljer och förväxlingsord för 409 tillkommande motiv.

`generation_ready` betyder att ett granskningsprov får genereras. `brief_required` kräver först en konkret bildinstruktion; `composition_required` kräver en uppdelning utan att meningen tillskrivs en enda bild; `convention_required` kräver vald symbolbetydelse. Det är automatiska beredningsstatusar, inte slutlig semantisk klassificering. En fras kan behöva en annan bedömning efter granskning.

Den aktiva genereringskatalogen är fortsatt `catalog/pilot/symbols.json`: **804 aktiverade bildinstruktioner** (501 tidigare och 303 nya från `concept-resolutions.json`). Alla resultat är `pending_review`, aldrig automatiskt godkända. Illustrationsstil, vit bakgrund och 512 px behålls.

## Genomarbetade poster: `concept-resolutions.json`

Alla 1 499 poster som saknade bildinstruktion har en avgränsad betydelse (`meaning_sv`) inom sin kategori och exakt en dokumenterad lösning:

| `resolution` | Status i ordlistan | Antal | Innebörd |
|---|---|---:|---|
| `standalone` | `generation_ready` | 303 | Självständigt motiv med `symbol_type` (`object` 120, `action` 113, `situation` 31, `body_part` 28, `person` 11), engelsk bildinstruktion, krav på synliga detaljer, förbjudna antydningar och förväxlingsord. |
| `reuse` | `reuses_symbol` | 24 | Samma motiv som en befintlig symbol (`reuse_symbol_id`), t.ex. *villa* → hus. Ingen nästan identisk bild skapas. |
| `composition` | `composition_defined` | 401 | Texten bevaras exakt och delas i `parts`; endast delar med matchande betydelse kopplas till symbol-ID. 160 har bara genereringsklara delar, 171 har minst en del som väntar på konvention, 70 har ännu ingen kopplad del. |
| `convention_proposal` | `convention_proposed` | 637 | Förslag på bildkonvention (`proposal_sv`, `proposal_visual_en`) och granskningsfråga. **Inte pedagogiskt validerade och aldrig aktiverade.** Inkluderar *hjälp* och *paus*. |
| `open_question` | `decision_required` | 134 | Betydelsen kan inte avgöras utan mänskligt beslut (`question_sv`, `options_sv`), t.ex. flertydiga ord. |

Beredningsverktyget lägger till en typberoende mall: föremål utesluter personer; handlingar visar själva rörelsen och bara de personer som behövs; personer visar roll enbart genom konkreta attribut; kroppsdelar visas vänligt, icke-medicinskt och utan nakenhet. Släktskap och roller som inte syns på utseendet (t.ex. *mormor*, *rektor*) är konventionsförslag. Fraser kan aldrig bli fristående motiv, och väntande konventionssymboler kan inte aktiveras som motiv.

Om en upprepad körning ändrar en post i `concept-resolutions.json` uppdateras ordlistan, men en redan aktiverad symbol i `symbols.json` skrivs aldrig om. Granskningskorrigeringar bevaras. Kör inte `build_school_vocabulary.py` utan att därefter köra `prepare_production_queue.py`, eftersom ombyggnaden återställer statusarna.

Bygg om med `python tools/build_school_vocabulary.py` från projektroten. Valfri redaktionell byggdependency: `wordfreq==3.1.1`; den behövs inte av bildgenerering eller validering i GitHub Actions. Tidigare ID:n återanvänds när posterna finns kvar. Byte av etikett eller nya urval kräver granskning av diffen och den publicerade kön.

Webbgranskningen visar den tidigare publicerade omgången med 92 bilder tills en ny Sites-version publiceras. Att lägga ord i denna katalog publicerar inte några nya bilder eller granskningsbeslut på webbplatsen.

`production-briefs.json` innehåller 300 individuellt skrivna motivbriefs i successivt beredda produktionsgrupper. `python tools/prepare_production_queue.py` aktiverar dem med befintliga ordliste-ID:n. Verktyget lämnar tidigare aktiva instruktioner, stilundantag och granskningar orörda; upprepad körning är idempotent. Fras- och konventionsposter aktiveras inte av detta verktyg.

Den senaste gruppen omfattar 200 konkreta motiv: djur, växter, mat, skolmaterial, teknik och vardagsföremål. Förväxlingsrisker och nödvändiga detaljer anges per motiv. Vanliga skolvardagsbegrepp prioriteras före kompletterande ämnesord. Alla tidigare bildinstruktioner och ID:n behålls oförändrade.
