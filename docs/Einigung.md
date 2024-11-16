# Komponenten
## Aktive Komponenten
1. v-Windkraftanlagen - Strom ist schon nutzbar
2. Abnahmegenerator (Wie viel Wasserstoff)
3. x-Wasserstoffzellen
4. y-Filteranlagen 
5. z-Destillierunganlagen (Wasser wird entsalzt)

## Passive Komponenten
1. Windkraftanlage - Summierer (wie viel Energie insgesamt)
2. x-Wasserstoffzellen - Summierer (wie viel Wasserstoff wird insgesamt produziert)
3. y-Filteranlagen - Summierer (wie viel gefiltertes Wasser wird insgesamt produziert)
4. z-Destillierungsanlagen - Summierer (wie viel destilliertes Wasser wird insgesamt produziert)

        -> eventuell 2. - 4. zentral?

5. benötigte Energie - Summierer
6. Tickgenerator
7. Wetterdaten-Generator
8. Wasserstofftank
9. Wassertank (optional)

# Schnittstellen
## Aktive Komponenten
1. v-Windkraftanlagen: <br>
benötigt: Wetterdaten, Energiebedarf <br>
liefert: Energie
2. Abnahmegenerator <br>
benötigt: - <br>
liefert: Abnahmemenge an Wasserstoff (pro Tag)
3. x-Wasserstoffzellen <br>
benötigt: destilliertes Wasser, Energie, Status der anderen Wasserstoffzellen, Abnahmemenge, bereits produzierte Abnahmemenge (pro Tag) <br>
liefert: Wasserstoff
4. y-Filteranlagen <br>
benötigt: Wasser, Energie, Status Destillierungsanlagen, benötigte Menge gefiltertes Wasser <br>
liefert: gefiltertes Wasser
5. z-Destillierunganlagen <br>
benötigt: gefiltertes Wasser, Energie, Status Fitleranlagen, benötigte Menge destilliertes Wasser<br>
liefert: destilliertes Wasser


## Passive Kompontenten
1. Windkraftanlage - Summierer <br>
benötigt: produzierte Energie der einzelnen v-Windkraftanlagen <br>
liefert: Summe Energie der v-Windkraftanlagen
2. x-Wasserstoffzellen - Summierer <br>
benötigt: produzierte Menge an Wasserstoff der einzelnen x-Wassestoffzellen <br>
liefert: Summe der produzierten Menge an Wasserstoff der x-Wasserstoffzellen
3. y-Filteranlagen - Summierer <br>
benötigt: produzierte Menge an gefiltertem Wasser der einzelnen y-Filteranlagen<br>
liefert: Summe der Menge an gefiltertem Wasser der y-Filteranlagen
4. z-Destillierungsanlagen - Summierer <br>
benötigt: produzierte Menge an destilliertem Wasser der einzelnen z-Destillierungsanlagen <br>
liefert: Summe der Menge an destilliertem Wasser der z-Destillierungsanlagen
5. benötigte Energie - Summierer<br>
benötigt: benötigte Energie aller Kompontenten<br>
liefert: Summe der benötigten Energie aller Komponenten
6. Tickgenerator<br>
benötigt: - <br>
liefert: Zeitintervalle
7. Wetterdaten-Generator<br>
benötigt: Zeitintervalle <br>
liefert: Wetterdaten
8. Wasserstofftank <br>
benötigt: Wasserstoff, Energie<br>
liefert: Wasserstoff
9. Wassertank <br>
benötigt: Wasser, Energie<br>
liefert: Wasser

# Key performance indicator (KPI)
### Produktivität (Menge an produziertem Wasserstoff) <br>
Verhältnis von tatsächlich produziertem Wasserstoff zu Abnahmemenge <br>
### Effektivität
Genau richtig, zu viel oder zu wenig produziert
