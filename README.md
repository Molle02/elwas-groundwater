# ELWAS Groundwater für Home Assistant

**Aktuelle Version: 1.0.2**

Diese Custom-Integration liest die veröffentlichten Wasserstände und
Flurabstände einer nordrhein-westfälischen ELWAS-Grundwassermessstelle ein.
Voreingestellt ist die LGD-Nummer **080200357** (`MEERERBUSCH Nr 88`). Andere
öffentliche Messstellen können über ihre neunstellige LGD-Nummer eingerichtet
werden.

> Die Messung beschreibt die ausgewählte Messstelle, nicht das eigene
> Grundstück. Sie ist eine Umweltinformation und keine Grundlage für Bau-,
> Versicherungs- oder Sicherheitsentscheidungen.

## Entitäten

| Entität | Bedeutung |
|---|---|
| Flurabstand | Vertikaler Abstand zwischen Geländeoberkante und Grundwasserspiegel; kleiner bedeutet höheres Grundwasser |
| Grundwasserstand | Höhenlage des Grundwasserspiegels in Metern über NHN2016 |
| Geländehöhe | Geländeoberkante der Messstelle in Metern über NHN2016 |
| Messdatum | Datum des neuesten veröffentlichten Messwerts |
| Datenalter | Alter des neuesten Messwerts in Tagen |
| 7-/30-Tage-Trend | Änderung des Flurabstands in cm/Woche aus einer linearen Regression |
| Trendrichtung | `steigend`, `stabil` oder `fallend` bezogen auf den Grundwasserspiegel |
| Saisonaler mittlerer Flurabstand | Mittel historischer Werte im Zeitfenster ±15 Kalendertage, ohne das aktuelle Jahr |
| Saisonale Abweichung | Aktueller Flurabstand minus saisonaler Mittelwert |
| Saisonales Perzentil | Anteil saisonaler Vergleichswerte, die höchstens so groß wie der aktuelle Flurabstand sind |
| Daten veraltet | Problemsensor; aktiv, wenn der jüngste Wert älter als sieben Tage ist |

Vorzeichen des Trends: Ein **negativer** Flurabstandstrend bedeutet steigendes
Grundwasser, ein **positiver** Trend fallendes Grundwasser. Eine positive
saisonale Abweichung bedeutet, dass das Grundwasser tiefer als saisonal üblich
liegt.

## Architektur

```text
Config Flow (LGD-Nummer)
          │
          ▼
ELWAS-Client ──► öffentliche Messstellenansicht
          │       Wasserstände und Flurabstände
          ▼
5.000+ historische Messwerte
          │
          ▼
Statistik: 7/30 Tage, saisonaler Vergleich, Langzeitmittel
          │
          ▼
DataUpdateCoordinator (alle 6 Stunden)
          │
          ├── Sensoren
          └── Warnung bei veralteten Daten
```

Der Client nutzt ausschließlich Python-Standardfunktionen und die in Home
Assistant vorhandene HTTP-Bibliothek. Zusätzliche Pakete sind nicht nötig.
ELWAS stellt für diesen Abruf keine stabile öffentliche Programmierschnittstelle
bereit; die Integration bildet deshalb den öffentlichen JSF-Webablauf nach.
Ändert das Land NRW diese Webseite, kann eine Anpassung nötig werden.

## Installation über HACS

[![Repository in HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Molle02&repository=elwas-groundwater&category=integration)

1. Auf den Button klicken und die eigene Home-Assistant-Instanz bestätigen.
   HACS fügt das Repository als benutzerdefiniertes Repository hinzu.
2. **Herunterladen** wählen und Home Assistant neu starten.
3. Die Integration einrichten:

[![Integration einrichten](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=elwas_groundwater)

## Manuelle Installation

1. Das Paket `elwas-groundwater-1.0.2.zip` entpacken.
2. Den darin enthaltenen Ordner `elwas_groundwater` vollständig nach
   `<config>/custom_components/` kopieren. Das Ergebnis muss so aussehen:

   ```text
   <config>/custom_components/elwas_groundwater/manifest.json
   ```

3. Home Assistant vollständig neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
5. Nach **ELWAS Grundwasser** suchen.
6. Die LGD-Nummer eingeben; für die gewählte Station ist `080200357`
   bereits voreingestellt.

Eine YAML-Konfiguration ist nicht vorgesehen. Für HACS kann der Inhalt als
eigenes GitHub-Repository mit `custom_components/elwas_groundwater` und einer
üblichen `hacs.json` veröffentlicht werden.

## Aktualisierung und Datenqualität

Home Assistant fragt ELWAS alle sechs Stunden ab. Das Veröffentlichungsdatum
der Quelldaten kann trotzdem zurückliegen; deshalb zeigen `Datenalter` und
`Daten veraltet` die tatsächliche Aktualität ausdrücklich an. Bereits geladene
Werte bleiben bei einem vorübergehenden ELWAS-Ausfall erhalten.

## Änderungen

### Version 1.0.2

- Neu veröffentlichte Updateversion mit der Jakarta-Faces-Korrektur.
- Ersetzt das versehentlich mit altem Quellstand veröffentlichte Release 1.0.1.

### Version 1.0.1

- Kompatibilität mit der ELWAS-Umstellung von Javax Faces auf Jakarta Faces.
- Automatische Erkennung des vom ELWAS-Server verwendeten JSF-Namensraums.
- Live geprüft mit der Messstelle `080200357` am 15. Oktober 2026.

### Version 1.0.0

- Erste Veröffentlichung.
