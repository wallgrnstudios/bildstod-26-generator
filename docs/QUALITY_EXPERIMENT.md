# Avgränsat kvalitetstest: 20 motiv

Testet använder 20 begrepp som tidigare avvisats, med nya konkreta bildinstruktioner. Baslinjen fryser den aktuella offentliga kandidaten med SHA-256 och oföränderlig källreferens. Den är inte nödvändigtvis samma bildversion som den historiska avvisningen gällde. Privata granskningsanteckningar exporteras aldrig till genereringsrepot.

Första jämförelsen använder samma pinnade FLUX-modell, samma bildinstruktioner och parade startvärden, med respektive utan stilreferens. Det testar referensens effekt, inte vilken modell som är bäst. Alternativ modell behöver en separat jämförelse och en beslutad kostnadsram. Alla bilder är kandidater; inget biblioteksgodkännande eller publicering sker.

## Förbered och kör

```sh
.venv/bin/python -m bildstod.quality_lab prepare --directory output/quality-test
.venv/bin/python -m bildstod.quality_lab plan --directory output/quality-test --profile text
```

`prepare` hämtar offentliga PNG-filer och kontrollerar deras SHA-256. Ett befintligt test skrivs aldrig över. Lokal inferens spärras. GitHub-workflowen **Compare 20 quality challenge images** fryser baslinjen en gång, kör en profil åt gången på standard ARM-runner och sparar separata resultatarkiv i 30 dagar. Den ändrar inga produktionsgrenar. Ladda ned resultatarkiven och öppna `review.html`. Kombinera profilerna i samma vy med `python -m bildstod.quality_lab merge --directory <text-arkiv> --source <referens-arkiv>`; olika testtillfällen eller bildversioner kan inte blandas.

## Granska och förbättra

Bedöm rätt betydelse, identifierande detaljer, frånvaro av extra betydelse, läsbarhet i 48 px, rena material och konsekvent stil. Sidan visar färg och gråskala. Välj beslut, skriv felorsak och vid omgenerering en konkret förbättrad instruktion på engelska. Klicka **Spara granskningsbeslut** och importera filen:

```sh
.venv/bin/python -m bildstod.quality_lab review --directory output/quality-test --decisions quality-decisions.json
.venv/bin/python -m bildstod.quality_lab plan --directory output/quality-test --profile text
```

Ett andra försök kräver beslutet `revise` samt en ny konkret bildinstruktion. Högst två försök per motiv och profil tillåts i det frysta testtillståndet. Godkända motiv hoppas över. Avbrutna eller misslyckade försök återkörs inte automatiskt. Efter två försök behöver ett fortsatt felaktigt motiv manuell bearbetning. `reject` skickar direkt till manuell bearbetning. Ett nytt test är en ny jämförelse, inte en fortsättning på en gammal försöksbudget.

Fortsättningskörning sker i samma workflow med `resume_run_id` från första körningen och `decisions_json` med exporterade offentliga beslut. Använd inte privata anteckningar i workflow-input. Källarkivet återställs före import och körning; tidigare försök behålls. Tomma fortsättningar laddar inte modellen.

`metrics.json` redovisar genererade kandidater, granskade försök, behållna motiv, tekniska fel och motiv för manuell bearbetning. `keep_for_pilot` är inte produktionsgodkännande. Bildfilens SHA kontrolleras både vid import och granskningsbeslut.

Driftstatusen skiljer nu senaste bildversion och nya aktuella versioner senaste dygnet från en lyckad CI-körning. Antalet är inte fullständig produktionshistorik: ersatta versioner kan saknas. Privata godkännanden läses inte och visas som okända. Tom grundkö och minst 24 timmar utan nya aktuella bildversioner ger uttryckliga meddelanden.
