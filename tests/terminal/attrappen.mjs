// Nachgebildete Antworten des Servers (keks_trace.terminal.*) für den Rauchtest.
//
// Die Daten müssen nicht fachlich stimmen. Sie sollen die Masken möglichst weit aufbauen, damit der
// Rauchtest viele Wege durch das JavaScript geht. Unbekannte Methoden liefern eine leere Liste.
// Codes mit „FEHLER“ lösen eine Meldung vom Server aus (Fehlerweg der Masken).

const FUNKTIONEN_ALLE = ["herstellen", "rework", "silo", "wareneingang", "paletten", "lieferung", "umlagern"];

// Stationstyp -> Antwort von start()
export const STATIONEN = {
	Backstube: { typ: "Backstube", funktionen: ["herstellen", "rework", "silo"], stufen: ["Grundteig", "Teig veredelt", "Backware"] },
	Kneter: { typ: "Kneter", funktionen: ["herstellen", "linie", "silo"], stufen: ["Teig veredelt"], linie: "Linie 1" },
	Former: { typ: "Former", funktionen: ["linie", "rework"], stufen: [], linie: "Linie 1" },
	Verpackung: { typ: "Verpackung", funktionen: ["herstellen", "paletten"], stufen: ["Fertigware"], nur_fertigware: true },
	"Verpackung Vorschlag": { typ: "Verpackung", funktionen: ["herstellen", "paletten"], stufen: ["Fertigware"], nur_fertigware: true, vorschlagen: true, linie: "Linie 1" },
	"Herzen Verpackung": { typ: "Herzen Verpackung", funktionen: ["herstellen", "paletten", "lieferung"], stufen: ["Fertigware"], nur_fertigware: true, vorschlagen: true },
	Lager: { typ: "Lager", funktionen: ["wareneingang", "silo", "paletten", "umlagern"], stufen: [], vorraete: true },
	Versand: { typ: "Versand", funktionen: ["lieferung", "paletten"], stufen: [] },
	Lagerverkauf: { typ: "Lagerverkauf", funktionen: ["umlagern"], stufen: [], umlager_ziel: "Lagerverkauf - KT" },
	Packstation: { typ: "Packstation", funktionen: ["packstation", "palette_fertig"], stufen: [], linie: "Linie 1" },
	"Verpackungs-PC": { typ: "Verpackungs-PC", funktionen: ["linie", "paletten"], stufen: [], linie: "Linie 1" },
	"Paletten-Terminal": { typ: "Paletten-Terminal", funktionen: ["paletten"], stufen: [] },
	Alles: { typ: "Individuell", funktionen: FUNKTIONEN_ALLE, stufen: ["Grundteig", "Fertigware"] },
};

export const SCANCODES = ["TB-0001", "340123450000000017", "FEHLER-1"];

const EINHEITEN = [
	{ einheit: "Palette", faktor: 168 },
	{ einheit: "Karton", faktor: 4 },
	{ einheit: "Kg", faktor: 1 },
];
const HINWEISE = [{ von: "Büro", text: "Mit Clip, neue Folie 2026" }];

const ZUTATEN = [
	{ artikel: "1001", name: "Weizenmehl 550", menge: 50, einheit: "Kg", stufe: "Rohstoff", lager: "Silo 1", silo: "Silo 1", toleranz: 0.5, gebinde: [] },
	{ artikel: "1002", name: "Zucker", menge: 20, einheit: "Kg", stufe: "Rohstoff", lager: "Lager - KT", toleranz: 0.2, gebinde: [{ einheit: "Sack", faktor: 25 }] },
	{ artikel: "1003", name: "Folie", menge: 2, einheit: "Nos", stufe: "Packmittel", lager: "Lager - KT", vorrat: "Vorrat Folie", gebinde: [] },
	{ artikel: "8001", name: "Rework Teig", menge: 0, einheit: "Kg", stufe: "Rework", rework: 1, gebinde: [] },
];

const LINIE_INFO = {
	auftrag: "PA-0001", name: "Honig Moppen", status: "Läuft", kunde: "Kunde A", verpackungsanlage: "Anlage 2",
	menge_text: "500 Karton", gebucht_text: "120 Karton", lagereinheit: "Karton", einheiten: EINHEITEN, hinweise: HINWEISE,
	zutaten: [
		{ artikel: "5812", name: "Grundteig Honig", stufe: "Teig veredelt", auf_linie: 40, einheit: "Kg", reicht_fuer: 10 },
		{ artikel: "1002", name: "Zucker", stufe: "Rohstoff", auf_linie: 5, einheit: "Kg" },
		{ artikel: "1003", name: "Folie", stufe: "Packmittel", auf_linie: 0, einheit: "Nos" },
	],
	kuebel: [{ code: "TB-0001", name: "Grundteig Honig", datum: "04.11.26", menge: 120 }],
};

const PACKSTATION = {
	...LINIE_INFO, beutel_je_karton: 12, karton_je_palette: 42, los_vorschau: "6447", mhd_vorschau: "30.06.29",
	offen_text: "380 Karton", spezifikation: "https://example.org/spez.pdf", linienlager: "Linienlager - KT",
	im_linienlager: [{ name: "Moppen lose", charge: "C-1", menge_text: "8 Karton", seit: "08:10", alt: false }],
	lose_artikel: "17670", lose_name: "Moppen lose", lose_einheit: "Karton", lose_je_einheit: 4,
};

const PALETTE = {
	nve: "340123450000000017", art: "Lagerpalette", typ: "Lagerpalette", status: "Offen", lager: "Lager - KT",
	kunde: null, versandkarton: false, etikett_veraltet: true, voll_text: "35 von 42 Karton",
	positionen: [
		{ name: "Honig Moppen", charge: "17846-2026-6447", los: "6447", mhd: "30.06.29", anzahl: 35, einheit: "Karton", menge: 140, gesperrt: false },
		{ name: "Lebkuchen", charge: "17847-2026-6447", los: "6447", anzahl: 2, einheit: "Karton", menge: 8, gesperrt: true },
	],
	versandkartons: [{ nve: "340123450000000024", inhalt: "Honig Moppen 2 Karton", menge: 8 }],
};

const AUFLOESEN = {
	typ: "Behälter", code: "TB-0001", artikel: "5812", artikelname: "Grundteig Honig", name: "Grundteig Honig",
	charge: "C-5812-1", menge: 120, einheit: "Kg", stufe: "Grundteig", inhalt: "Grundteig Honig 120 kg",
};

const ANTWORTEN = {
	stationen: () => Object.entries(STATIONEN).map(([name, s]) => ({ name, typ: s.typ })),
	start: (a) => {
		const s = STATIONEN[a.station];
		if (!s) return { __fehler: "Station ist nicht eingerichtet." };
		return { station: a.station, nutzer: "terminal@example.org", drucker: {}, umlager_ziel: null, vorraete: false, linie: null, nur_fertigware: false, vorschlagen: false, pruefungen: [], ...s };
	},
	kopfdaten: (a) => ({
		zeit: "2026-11-05T09:30:00", datum_text: "Do 05.11.26", kw: 45, los: "6454", station: a.station,
		benutzer: "terminal", auftrag: "PA-0001 Honig Moppen", pruefung: { art: "orange", text: "Metalldetektor fällig" },
	}),
	pruefungen_faellig: () => [
		{ pruefplan: "PP-1", titel: "Metalldetektor", frage: "Prüfkörper erkannt?", lenkung: "CCP", art: "Prüfkörper",
			pruefkoerper: ["Fe 2,0", "Edelstahl 3,0"], grenzwert: "alle erkannt", faellig: true, sperrt: true, letzte_ok: "07:00", korrektur: "Linie stoppen" },
		{ pruefplan: "PP-2", titel: "Temperatur", frage: "Kerntemperatur", lenkung: "CP", art: "Messwert", einheit: "°C",
			grenzwert: "> 95 °C", faellig: true, sperrt: false },
		{ pruefplan: "PP-3", titel: "Sichtprüfung", frage: "Folie sauber?", lenkung: "CP", art: "Ja/Nein", grenzwert: "ja",
			faellig: false, faellig_ab: "11:00", bald: true },
	],
	pruefung_erfassen: () => ({ ok: true, text: "Prüfung gespeichert." }),
	linie_info: () => LINIE_INFO,
	packstation: () => PACKSTATION,
	linie_auftraege: () => [
		{ name: "PA-0001", artikel: "17846", artikelname: "Honig Moppen", kundenname: "Kunde A", datum_text: "heute", menge_text: "500 Karton",
			gebucht_text: "120 Karton", verpackungsanlage: "Anlage 2", status: "Läuft", aktuell: true, hinweis: "Mit Clip" },
		{ name: "PA-0002", artikel: "17847", artikelname: "Lebkuchen", kundenname: "", datum_text: "heute", menge_text: "100 Karton",
			gebucht_text: "0 Karton", status: "Freigegeben" },
	],
	linie_waehlen: () => ({ ok: true }),
	linie_zufuehren: () => ({ name: "Grundteig Honig", menge: 120, einheit: "Kg", behaelter: "TB-0001", chargen: ["C-5812-1"], hinweise: ["Kübel ist jetzt leer"] }),
	fefo_pruefen: () => ({ name: "Zucker", charge: "C-2", pflicht: true, aeltere: [{ charge: "C-1", mhd: "01.01.27", menge: 5 }] }),
	linie_retour_liste: () => [
		{ name: "Zucker", charge: "C-2", menge: 12.5, einheit: "Kg", ziel: "Lager - KT", ziel_name: "Lager" },
		{ name: "Weizenmehl 550", charge: "C-3", menge: 3, einheit: "Kg", silo: "Silo 1" },
	],
	linie_rueckgabe: () => ({ name: "Zucker", menge: 12.5, einheit: "Kg", ziel: "Lager" }),
	linie_beenden: () => ({ auftrag: "PA-0001", rest: [{ name: "Zucker", charge: "C-2", menge: 1.2 }] }),
	linie_palette: () => ({ name: "Honig Moppen", los: "6447", anzahl: 42, einheit: "Karton", menge: 168, palette: "340123450000000017",
		mhd: "30.06.29", gebucht_text: "162 Karton", verbraucht: [{ name: "Folie", charge: "F-1" }], hinweise: [] }),
	linie_lose: () => ({ name: "Moppen lose", charge: "C-9", anzahl: 10, einheit: "Karton", menge: 40, ziel: "lager",
		palette: "340123450000000017", verbraucht: [{ name: "Backware", charge: "B-1" }], hinweise: [] }),
	tagesuebersicht: (a) => ({
		datum: "Do 05.11.26", datum_iso: a.datum || "2026-11-05", heute: !a.datum, offen: 2, fertig: 1,
		linien: [{ linie: "Linie 1", offen: 2, fertig: 1, auftraege: [
			{ status: "Läuft", auftrag: "PA-0001", name: "Honig Moppen", kunde: "Kunde A", menge_text: "500 Karton", gebucht_text: "120 Karton", anteil: 0.24, hinweis: "Mit Clip" },
			{ status: "Freigegeben", auftrag: "PA-0003", name: "Lebkuchen", vortag: true, datum: "04.11.26", menge_text: "100 Karton", gebucht_text: "0", anteil: 0 },
		] }],
	}),
	rezepte: () => [
		{ artikel: "5812", name: "Grundteig Honig", stufe: "Grundteig" },
		{ artikel: "5888", name: "Honig Moppen Teig", stufe: "Teig veredelt" },
	],
	rezept: (a) => ({
		artikel: a.artikel, name: "Grundteig Honig", einheit: "Kg", sollmenge: a.menge || 100, rezept_pruefen: true,
		einheiten: a.artikel === "17846" ? EINHEITEN.slice(1) : [], zutaten: ZUTATEN, kuebel: [{ code: "TB-0002", name: "Teigbehälter 2" }],
		rework_moeglich: [{ artikel: "8001", name: "Rework Teig", anteil: 10 }], kennzeichen: ["BIO"], umstellung_bio: false,
	}),
	auftraege: () => [
		{ auftrag: "SO-0001", kunde: "K-1", kundenname: "Kunde A", artikel: "17846", name: "Honig Moppen", menge: 100, geliefert: 20,
			verpackt: 30, offen_verpacken: 70, offen_kg: 280, einheit: "Karton", termin: "06.11.26", hinweis: "Mit Clip" },
	],
	aufgaben: () => [
		{ auftrag: "SO-0001", kunde: "Kunde A", artikel: "17846", name: "Honig Moppen", bestellt: 100, erledigt: 30, todo: 70,
			einheit: "Karton", termin: "06.11.26", vorstufe: "Moppen lose", verfuegbar: 50, vorrat_eigen: 20, vorrat_frei: 30 },
	],
	zum_verpacken: () => [
		{ lose: "17670", name: "Moppen lose", code: "KI-0001", behaelter: "KI-0001", charge: "C-9", backtag: "03.11.26", mhd: "01.02.27", menge: 40, einheit: "Karton", menge_text: "10 Karton", linienlager: true },
	],
	verpacken_ziele: () => ({
		auftraege: [{ auftrag: "SO-0001", kunde: "Kunde A", artikel: "17846", name: "Honig Moppen", offen_text: "70 Karton", termin: "06.11.26" }],
		artikel: [{ artikel: "17846", name: "Honig Moppen" }],
	}),
	einheiten: () => EINHEITEN.slice(1),
	vorschlag: (a) => ({
		zeilen: [{ code: "KI-0001", artikel: "17670", name: "Moppen lose", menge: a.menge || 10, einheit: "Kg", charge: "C-9", behaelter: "KI-0001" }],
		hinweise: a.kundenauftrag ? [] : ["Folie fehlt"],
	}),
	pruefe_zeile: (a) => (String(a.code).includes("FEHLER")
		? { __fehler: "Charge ist gesperrt." }
		: { code: a.code, artikel: "1002", name: "Zucker", menge: a.menge || 10, einheit: "Kg", charge: "C-2", lager: "Lager - KT", hinweise: [] }),
	auswahl: () => [{ code: "C-2", name: "Zucker", charge: "C-2", menge: 50, einheit: "Kg", mhd: "01.01.27", lager: "Lager - KT" }],
	registrierungen: () => [{ zeit: "08:12", text: "Zucker 25 kg", charge: "C-2", buchung: "STE-1" }],
	vorschau: () => ({ los: "6447", mhd: "30.06.29", hinweise: ["MHD sinkt durch ältere Ware"] }),
	herstellen: () => ({ name: "Grundteig Honig", charge: "C-5812-2", menge: 100, einheit: "Kg", los: "6447", mhd: "30.06.29", hinweise: [] }),
	rework_artikel: () => [{ artikel: "8001", name: "Rework Teig", entnahmepunkt: "nach dem Ofen" }],
	rework_linie_auftraege: () => [
		{ auftrag: "PA-0001", name: "Honig Moppen", linie: "Linie 1", status: "Läuft",
			sorten: [{ artikel: "8001", name: "Rework Teig", punkt: "nach dem Ofen" }, { artikel: "8002", name: "Rework Bruch", punkt: "am Ende" }] },
		{ auftrag: "PA-0002", name: "Lebkuchen", linie: "Linie 2", status: "Läuft", sorten: [] },
	],
	freie_rework_behaelter: () => [{ code: "RB-0001", name: "Rework-Behälter 1" }],
	rework_linie: () => ({ name: "Rework Teig", charge: "R-1", menge: 12, behaelter: "RB-0001", hinweise: [] }),
	rework_erfassen: () => ({ name: "Rework Teig", charge: "R-1", menge: 12, behaelter: "RB-0001", hinweise: [] }),
	wareneingang_artikel: () => [
		{ artikel: "1001", name: "Weizenmehl 550", stock_uom: "Kg", silo: "Silo 1", silos: [{ name: "Silo 1" }], bio: 1, lieferanten: [{ name: "Mühle", lieferant: "L-1" }],
			bestellungen: [{ name: "PO-1", lieferant: "L-1", offen: 1000, termin: "05.11.26" }], gebinde: [] },
		{ artikel: "1002", name: "Zucker", stock_uom: "Kg", kt_freigabe_pflicht: 1, gebinde: [{ einheit: "Sack", faktor: 25 }], lieferanten: [], bestellungen: [] },
	],
	wareneingang_scan: (a) => (a.code === "TB-0001"
		? { artikel: "1002", gs1: true, charge: "L-77", mhd: "2027-06-30", menge_je_gebinde: 25, gebindeart: "Sack" }
		: { charge: a.code, unbekannt: false }),
	wareneingang: () => ({ name: "Zucker", charge: "L-77", menge: 50, einheit: "Kg", codes: ["GB-1", "GB-2"], gesperrt: true, hinweise: [] }),
	silos: () => [{ name: "Silo 1", artikel: "1001", artikelname: "Weizenmehl 550", typ: "Silo", menge: 1200, chargen: ["C-3"] }],
	vorraete: () => [{ name: "Vorrat Folie", artikel: "1003", artikelname: "Folie", typ: "Vorrat am Tisch", menge: 3 }],
	silo_leer: () => ({ silo: "Silo 1", rest: 12.5, text: "Silo 1 leer gemeldet." }),
	anbrechen: () => ({ name: "Folie", charge: "F-1", vorrat: "Vorrat Folie", menge: 1 }),
	lager_chargen: () => [{ charge: "F-1", menge: 4, mhd: "01.01.28", lager: "Lager - KT" }],
	kunden: () => [{ name: "K-1", kunde: "Kunde A", kundenname: "Kunde A" }],
	pruefe_lieferzeile: (a) => (String(a.code).includes("FEHLER")
		? { __fehler: "Los ist gesperrt." }
		: { positionen: [{ charge: "17846-2026-6447", name: "Honig Moppen", anzahl: 10, einheit: "Karton", menge: 40, los: "6447", artikel: "17846" }], palette: null }),
	lieferung: () => ({ lieferschein: "LS-0001", name: "LS-0001", positionen: 1, hinweise: [] }),
	paket_vorschlag: () => ({ pakete: [{ stueck: 10, gewicht: 4.3 }], verfuegbar: 100 }),
	paket_lieferung: () => ({ lieferschein: "LS-0002", kartons: [], hinweise: [] }),
	sendungsnummer: () => ({ ok: true }),
	umlager_ziele: () => [{ name: "Lagerverkauf - KT", titel: "Lagerverkauf" }, { name: "Lager - KT", titel: "Lager" }],
	umlagern: () => ({ name: "STE-9", positionen: 1, hinweise: [] }),
	fertigware_im_lager: () => [{ charge: "17846-2026-6447", name: "Honig Moppen", los: "6447", anzahl: 10, einheit: "Karton", menge: 40, mhd: "30.06.29" }],
	palette_info: (a) => (String(a.code).includes("FEHLER") ? { __fehler: "Keine Palette." } : PALETTE),
	palette_neu: (a) => ({ ...PALETTE, nve: "340123450000000031", art: a.typ || "Lagerpalette", typ: a.typ || "Lagerpalette", positionen: [], versandkartons: [] }),
	palette_beladen: () => PALETTE,
	palette_umpacken: () => PALETTE,
	palette_schliessen: () => ({ ...PALETTE, status: "Geschlossen" }),
	palette_oeffnen: () => PALETTE,
	palette_versandbereit: () => ({ ...PALETTE, status: "Geschlossen" }),
	karton_auf_palette: () => PALETTE,
	karton_abnehmen: () => PALETTE,
	offene_paletten: () => [{ nve: "340123450000000017", typ: "Lagerpalette", inhalt: "Honig Moppen 35 Karton", lose: "6447", kunde: "" }],
	freie_kisten: () => [{ code: "KI-0002", name: "Kiste 2" }],
	info: (a) => (String(a.code).includes("FEHLER") ? { __fehler: "Code unbekannt." } : { ...AUFLOESEN, historie: [{ zeit: "04.11.26 08:00", text: "befüllt" }] }),
	akte: () => ({ titel: "Akte C-5812-1", abschnitte: [] }),
	herkunft: () => ({ titel: "Herkunft", zeilen: [] }),
	behaelter_reinigung: () => ({ code: "TB-0001", status: "Frei" }),
	etikett_drucken: () => ({ gedruckt: true, drucker: "Zebra 1" }),
	etikett_vormerken: () => ({ ok: true }),
};

export function antwort(methode, args, station) {
	const f = ANTWORTEN[methode];
	if (!f) return [];
	if (Object.values(args || {}).some((v) => typeof v === "string" && v.includes("FEHLER")) && methode !== "start") {
		return { __fehler: "Testfehler vom Server für " + methode + "." };
	}
	return f(args || {}, station);
}
