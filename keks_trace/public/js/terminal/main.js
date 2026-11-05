// Terminal: Einstieg. Lädt alle Teile in der alten Reihenfolge und startet die Oberfläche.

import { api, laden, speichern, zustand } from "./basis.js";
import { startseite, stationWaehlen } from "./station.js";
import { umlagerZielVergessen } from "./lager.js";

// ------------------------------------------------------------------ Start
// Direktlink /terminal?station=Lager (Drehbuch der Demo, Lesezeichen am Gerät): Station merken, Adresse aufräumen
const stationAusLink = new URLSearchParams(location.search).get("station");
if (stationAusLink) { speichern("kt_station", stationAusLink); history.replaceState(null, "", location.pathname); }
export async function init() {
	const station = laden("kt_station");
	if (!station) return stationWaehlen();
	try {
		const s = await api("start", { station });
		zustand.station = s.station;
		zustand.typ = s.typ;
		zustand.funktionen = s.funktionen;
		zustand.stufen = s.stufen;
		zustand.nur_fertigware = s.nur_fertigware;
		zustand.umlager_ziel = s.umlager_ziel;
		zustand.vorschlagen = s.vorschlagen;
		zustand.drucker = s.drucker || {};
		zustand.linie = s.linie;
		umlagerZielVergessen();
		zustand.vorraete = s.vorraete;
		startseite();
	} catch (e) {
		speichern("kt_station", "");
		stationWaehlen();
	}
}
init();
