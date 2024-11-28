# Anwendungsfälle

1. Anwendungsfall: <br>
Der Strom für die Produktion des Wasserstoffs beziehen wir aus unserer eigenen Windkraftwerk Anlage, welche neben unserer Produktionshalle steht. Dieser Strom fließt direkt in unsere Produktion hinein. Die Produktion wird somit gestartet und es wird bemessen, wie intensiv unsere Produktion läuft mit dem selbst bezogenen Strom. Sobald die Produktion erhöht werden muss, doch unsere Strom dafür nicht ausreicht, wird dem System zurück gemeldet, dass dies nicht möglich sei. <br>
Wenn zu wenig Strom produziert wird und die Intensivität der aktuellen Produktion nicht mehr gehalten werden kann, wird das dem System zurück gemeldet und folglichh muss die Produktion sich verringern. Sobald mehr Strom produziert wurde, steigt die Produktion wieder auf den Stand davor.

2. Anwendungsfall: <br>
Im besten Fall arbeitet die Wasserstoffzelle mit 100% Arbeitslast. Diese kann über die ganze Zeit gehalten werden. Sollte es dazu kommen, dass mehr Wasserstoff produziert werden soll, ist die Wasserstoffzelle auch auf beispielhaft 110% skalierbar. Hierbei muss man jedoch beachten, dass die Wasserstoffzelle überlastet ist. Diese Arbeitslast kann nicht ewig gehalten werden und muss überwacht werden. <br>
Das System meldet zurück, wenn die Wasserstoffzelle überhitzt ist und die Arbeitslast somit zu hoch ist. Das System wird neu skaliert und so angepasst, dass die Wasserstoffzelle abkühlen kann und dennoch weiter produziert.

# Use-Cases
| Abschnitt | Inhalt |
| ----------- | ----------- |
| Bezeichner | UC-01 |
| Name | Normalbetrieb |
| Autoren | Alex, Dany, Tommy |
| Priorität | Wichtigkeit für Systemerfolg "sehr hoch" |
| Kurzbeschreibung | Der Normalbetrieb für das ganze System |
| Auslösendes Ereignis | Produktion von Wasserstoff|
| Akteure | Windkraftanlagen, Abnahmegenerator, Wasserstoffzellen, Filteranlagen, Destillierungsanlagen |
| Vorbedingung | Wasser vorhanden, Energie vorhanden, Wasserstoffzellen einsatzfähig |
| Nachbedingung | Wasserstoff wurde produziert |
| Hauptszenario | 1. Wasser wird in die Filteranlage eingeleitet
||2. Filteranlage produziert gefiltertes Wasser
||3. Gefiltertes Wasser wird in die Destillierungsanlage eingeleitet
||4. Destillierungsanlage produziert destilliertes Wasser
||5. Destilliertes Wasser wird eingeleitet in die Wasserstoffzelle
||6. Wasserstoffzelle produziert Wasserstoff
||7. Wasserstoff wird in den Wasserstofftank geleitet
||8. Wasserstoff wird vom Wasserstofftank abgepumpt
| Alternativszenarien | 7a. Wasserstoff wird direkt abgepumpt in Transport |
<br>

| Abschnitt | Inhalt |
| ----------- | ----------- |
| Bezeichner | UC-02 |
| Name | zu wenig Strom |
| Autoren | Alex, Dany, Tommy |
| Priorität | Wichtigkeit für Systemerfolg "hoch" |
| Kurzbeschreibung | Produktion muss verringgert werden, aufgrund von zu wenig Strom |
| Auslösendes Ereignis | Windkraftanlage liefert zu wenig Strom|
| Akteure | Windkraftanlagen, Abnahmegenerator, Wasserstoffzellen, Filteranlagen, Destillierungsanlagen |
| Vorbedingung | Wasser vorhanden, zu wenig Energie vorhanden, Wasserstoffzellen einsatzfähig |
| Nachbedingung | Produktion wurde angepasst |
| Hauptszenario | 1. Wasserstoffzelle wird neu skaliert
||2. Filteranlage wird neu skaliert
||3. Destillierungsanlage wird neu skaliert
||4. Windkraftanlage wird neu skaliert

<br>

| Abschnitt | Inhalt |
| ----------- | ----------- |
| Bezeichner | UC-03 |
| Name | Wasserstoffzelle fällt aus |
| Autoren | Alex, Dany, Tommy |
| Priorität | Wichtigkeit für Systemerfolg "hoch" |
| Kurzbeschreibung | Produktion muss angepasst werden, aufgrund von Ausfall von Wasserstoffzelle |
| Auslösendes Ereignis | Wasserstoff Produktion zu niedrig|
| Akteure | Windkraftanlagen, Abnahmegenerator, Wasserstoffzellen, Filteranlagen, Destillierungsanlagen |
| Vorbedingung | Wasser vorhanden, Energie vorhanden, Wasserstoffzellen teilweise einsatzfähig |
| Nachbedingung | Produktion wurde angepasst |
| Hauptszenario | 1. Wasserstoffzelle wird neu skaliert


<br>

| Abschnitt | Inhalt |
| ----------- | ----------- |
| Bezeichner | UC-04 |
| Name | Filteranlage fällt aus |
| Autoren | Alex, Dany, Tommy |
| Priorität | Wichtigkeit für Systemerfolg "hoch" |
| Kurzbeschreibung | Produktion muss angepasst werden, aufgrund von Ausfall von Fitleranlage |
| Auslösendes Ereignis | Produktion gefiltertes Wasser zu niedrig|
| Akteure | Windkraftanlagen, Abnahmegenerator, Wasserstoffzellen, Filteranlagen, Destillierungsanlagen |
| Vorbedingung | Wasser vorhanden, Energie vorhanden, Filteranlage teilweise einsatzfähig |
| Nachbedingung | Produktion wurde angepasst |
| Hauptszenario | 1. Filteranlage wird neu skaliert


<br>

| Abschnitt | Inhalt |
| ----------- | ----------- |
| Bezeichner | UC-05 |
| Name | Destillierungsanlage fällt aus |
| Autoren | Alex, Dany, Tommy |
| Priorität | Wichtigkeit für Systemerfolg "hoch" |
| Kurzbeschreibung | Produktion muss angepasst werden, aufgrund von Ausfall von Destillierungsanlage |
| Auslösendes Ereignis | Produktion destilliertes Wasser zu niedrig|
| Akteure | Windkraftanlagen, Abnahmegenerator, Wasserstoffzellen, Filteranlagen, Destillierungsanlagen |
| Vorbedingung | Wasser vorhanden, Energie vorhanden, Destillierungsanlagen teilweise einsatzfähig |
| Nachbedingung | Produktion wurde angepasst |
| Hauptszenario | 1. Destillierungsanlage wird neu skaliert

<br>

| Abschnitt | Inhalt |
| ----------- | ----------- |
| Bezeichner | UC-06 |
| Name | Windkraftanlage fällt aus |
| Autoren | Alex, Dany, Tommy |
| Priorität | Wichtigkeit für Systemerfolg "hoch" |
| Kurzbeschreibung | gesamte Produktion wird gestoppt |
| Auslösendes Ereignis | Windkraftanlage liefert keinen Strom|
| Akteure | Windkraftanlagen, Abnahmegenerator, Wasserstoffzellen, Filteranlagen, Destillierungsanlagen |
| Vorbedingung | System vollständig funktionsfähig, kein Strom mehr |
| Nachbedingung | Produktion wurde gestoppt |
| Hauptszenario | 1. Wasserstoffzelle wird gestoppt
||2. Filteranlage wird neu gestoppt
||3. Destillierungsanlage wird neu gestoppt
||4. Windkraftanlage wird neu gestoppt



