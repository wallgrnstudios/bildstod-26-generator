# Produktion mot 3 000 utbildningsrelevanta bilder

## Orsak till utebliven tillväxt

Driftunderlaget 2026-10-26 kl. 15:32 svensk tid rapporterade 816 aktiverade bildinstruktioner och 816 kandidater, utan väntande grundmotiv. Genereringskörning 40326466217 planerade noll bilder på alla åtta arbetare. Granskningsgodkännanden fyller inte automatiskt på med nya motiv. Schemat var aktiverat men hade en tom förberedd kö; dessutom var schemagränsen tre motiv per arbetare.

Den lokala källan låg efter den publika motorn: den saknade tolv redan genererade klädmotiv samt senare rättningar för instruktioner, blockerade motiv och hantering av köfel. Dessa ändringar har hämtats in utan att skriva över privata granskningsdata.

## Genomförd påfyllning

- Tio återstående klädmotiv prioriterades. De är genererade och tekniskt filverifierade; se `WEATHER_GARMENTS.md`.
- Alla 134 poster med öppna betydelsefrågor har fått en individuellt avgränsad komplettering i `catalog/school/brief-completions-2026-10-26.json`: 89 konkreta motiv, 44 konventionsförslag och en återanvändning.
- 214 ytterligare unika konkreta motiv har lagts till från 215 skrivna instruktioner. En redan befintlig pennvässare uteslöts utan att återaktivera dess blockerade version. Underlag: `catalog/school/expansion-2026-10-26.json`.
- Den nya grundkön omfattar 303 motiv, utöver klädkörningen. Prioritet: kläder, kompletterade konkreta grundbegrepp, övrigt skolmaterial och vardagsmotiv.
- Schemat fortsätter var tredje timme med högst 100 kandidater per arbetare och befintlig tidsgräns på två timmars bildarbete. Ingen betald beräkning eller lokal modellkörning har lagts till.
- Driftstatus kan nu hantera en saknad bildmängd över 200 och räknar bort redaktionellt blockerade begrepp från den aktiva kön.

[Den nya produktionskörningen 40361089781](https://github.com/wallgrnstudios/bildstod-26-generator/actions/runs/40361089781) startades efter godkänd validering. Den genererar kandidater till granskning, utan automatisk publicering i det godkända biblioteket.

## Faktiska antal efter påfyllning

Ordlistan innehåller 2 232 begrepp/fraser. 1 125 har bildinstruktioner markerade för generering; 156 är fortfarande redaktionellt blockerade, vilket ger 969 tillåtna bildmotiv. 681 poster har konventionsförslag, 401 sammansättningar och 25 återanvänder andra symboler. Dessa är inte 3 000 färdiga eller godkända bilder. Alla antal kan räknas ur katalogfilerna; `summary.json` har produktionsmålet 3 000.

För att nå målet behövs ytterligare 2 031 tillåtna, unika motiv utöver dessa 969 samt produktion och granskning. Sammansättningar, etikettvarianter och obearbetade tvetydiga ord räknas inte som nya färdiga bilder. Konventionsförslagen har bildinstruktioner men är inte automatiskt aktiverade eller pedagogiskt godkända.

## Verifiering

Katalogvalidering och riktade tester har körts. GitHub-validering 40360898551 passerade samtliga 37 tester. Samtliga 1 125 aktiverade instruktioner ryms inom den pinnade tokenizerns 220-tokenstak. Återkörning av de två kompletteringsskripten tillför inga dubbletter. De tolv redan genererade klädkontrakten har identiska fingeravtryck efter ändringen. Bildfiler och privata granskningsbeslut har inte massgodkänts.

Senaste kontroll: alla åtta arbetare befann sig i genereringssteget. 0 av de 303 nya skolmotiven fanns då redan i resultatmanifesten. GitHub-validering 40361292236 passerade efter den sista driftjusteringen. Driftstatus 40361097291 lyckades och redovisade inga felkvittens eller varningar.
