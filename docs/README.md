# Mastopy

Mit mastopy lassen sich Toots von Mastodon Instanzen in einer 
MongoDB Datenbank speichern. Hierbei kann man auswählen, welche Attribute
gespeichert werden und nach Eigenschaften filtern.

## Requirements
Vor dem Starten des Programms müssen die in der Datei `docs/requirements.txt` angegebenen Module installiert werden.

## MongoDB Verbindung herstellen
Vor der Ausführung muss die Datei `config/dbconfig.json` für die Verbindung mit der MongoDB Datenbank mit den erforderlichen Daten befüllt werden. 

## Mastodon Instanzen hinzufügen
Damit Toots von Instanzen gefetched werden können, müssen erst die Instanzen
gespeichert werden. Dafür gibt es in `main.py` die Methode `masto_db.fetch_instances()`, welche die API [instances.social](instances.social) nutzt. Die Methode ist asynchron und muss dementsprechend mit der Funktion `asyncio.run()` ausgeführt werden.

Für die Suche der Instanzen sind in der Datei `config/instance_filter.json`
Filter bereitgestellt. Falls ein Filter nicht genutzt werden soll, muss der Wert
`null` sein.

| Name | Typ | Beschreibung | <div style="width:69px">Beispiel</div>|
| ----------- | ----------- | ----------- | ----------- |
| amount_of_instances | int | Anzahl der Instanzen, die gefetched werden.<br><br>Größenbereich: `0-9999` <br>Default: `20` <br>Setze auf `0`, um alle instanzen zu fetchen.<br><br>Manche Filter wirken erst nach dem Fetch, sodass weniger Instanzen als angegeben gespeichert werden können.| 30
| min_users | int | Minimale Anzahl an registrierten Nutzen auf der Instanz. | 100
| min_active_users | int | Minimale Anzahl an aktiven Nutzen pro Woche auf der Instanz. <br><br> [-Dieser Filter schließt alle Instanzen unter der Mastodon Version 2.1.2 aus!-]| 30
| amount_statuses | int | Minimale Anzahl an geposteten Toots auf der Instanz. | 1000
| languages | list[str] | Instanz muss eine der Sprachen als genutzte Sprache angegeben haben. Sprachen müssen nach `ISO 639-1` angegeben werden.| ["de", "en"]
| include_closed | bool | Instanzen, die derzeit keine Registrierungen erlauben, sind enthalten. | false
| min_obs_score | int | Instanzen mit einem Mozilla Observatory Score unter dem gegebenen Wert werden nicht gefetched. Siehe [Link](observatory.mozilla.org).| 90

## Toots von gespeicherten Instanzen fetchen.
Die Methode `masto_db.fetch_posts()` beginnt ein Loop und fetched Toots speichert sie in der Datenbank. Um den Loop zu stoppen und das Programm zu beenden, drücke `Strg-C`.

### Attribute auswählen
Für das Fetchen kann man zum einen auswählen, welche Attribute des Toots gespeichert werden können. Dazu müssen die Felder der Datei `config/toot_attributes.json` gesetzt werden.
Die Werte sind entweder `true` oder `false`.
Die post_ID wird immer gespeichert.
| Name  | Typ | Beschreibung 
| ----------- | ----------- | -----------
date | str | Datum nach `ISO 8601 Datetime`, an dem der Toot gepostet wurde.
content | str | Inhalt des Toots im HTML-Format.
html_parsed_content | str | Inhalt des Toots wird HTML geparsed.[-Keine separates Attribut, impliziert `content`!-]
url | str | Der Link zum Toot.
uid | str | ID des Accounts, der den Toot gepostet hat.
sensitive | bool | Gibt an, ob der Toot als "sensitive" markiert wurde.
favourites_count | int | Anzahl der Favorisierungen des Toots.
tags | list[str] | Liste der Tags, die in dem Toot genutzt werden.
media | list[str] | Liste von Links zu den Medien-Dateien des Toots. 

### Toots filtern
Toots werden über die Datei `config/toot_filter.json` gefiltert. Falls ein Filter nicht genutzt werden soll, muss der Wert `null` sein.

| Name | Typ | Beschreibung | <div style="width:69px">Beispiel</div>|
| ----------- | ----------- | ----------- | ----------- 
has_media | bool | Toots beinhalten Medien (Bilder, Videos etc.). |  true
has_image | bool | Toots beinhalten Bilder. [-Impliziert \`has_media\`!-] | false
has_video | bool | Toots beinhalten Videos. [-Impliziert \`has_media\`!-] |  true
substring | str | Text des Toots muss gegebenen Substring enthalten. |  "der"

### Fetch-Loop und Ratelimit
`masto_db.fetch_posts()` startet ein Fetch-Loop über alle Instanzen, die in der Datenbank gespeichert sind. Ratelimits gibt es pro Instanz und erlaubt in der Regel 300 API-Calls, wonach
man 5 Minuten warten muss, um das Ratelimit zu resetten.

Der Loop fetcht Toots, solange keine Fehler auftreten und das Ratelimit nicht erreicht wird.
Falls ein Fehler bei einem Fetch auftritt, wird die Instanz aus dem Loop geworfen und wird bis zum Neustart des Programms nicht weiter betrachtet. Beim Erschöpfen des Ratelimits wird gewartet, 
bis wieder neue Fetchs möglich sind.

## Statistik
Beim Fetchen werden die Antwortszeiten jedes Fetchs für jede Instanz mitgespeichert.
Die Methode `stats.print_average()` gibt in der Konsole aus, was die durchschnittliche Antwortzeit eines Fetches der gespeicherten Instanzen ist.

## Datenbankstruktur
Die Datenbankstruktur sieht wie folgt aus:
```
    Mastodon:
        instanceData: [{
            _id: mastodon.social,
            languages: ["de", "en"],
            caughtUp: false,
            fetchTime: 727.1337
        }],

        instance1: [toot_document],
        instance2: [toot_document],
        instance3: [toot_document],
    ...
```
`instanceData` ist hierbei eine Collection, welche für die Ausführung der Methoden benötigt wird.
