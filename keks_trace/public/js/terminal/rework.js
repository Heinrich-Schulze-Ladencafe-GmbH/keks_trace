// Terminal: Rework und Bruch, an der Linie oder ohne Linie.

import { api, app, esc, fokus, kg, meldung, zahl, zustand } from "./basis.js";
import { textFeld, zahlFeld } from "./tastatur.js";
import { aktionen, beiAllgemein, enter, ergebnis, gebindeDrucken, kopf, suchListe } from "./rahmen.js";

// ------------------------------------------------------------------ Rework / Bruch
// Backstube: Rework-Behälter von der Linie wiegen und buchen (F18). Erst der Auftrag, dann die Sorte
// (nur passende: Regel und Allergene), Behälter, Gewicht von der Waage. Etikett für den Behälter.
export async function reworkStart() {
	app.innerHTML = kopf("Rework", true) + `<p><b>Von welchem Auftrag an der Linie?</b> – Zeile antippen</p><div id="liste">Lädt …</div>
		<div class="reihe"><button class="knopf" data-a="ohne-linie">Ohne Linie<small>Teigrest aus Kübel oder Charge</small></button></div>`;
	aktionen((a) => (a === "ohne-linie" ? reworkOhneLinie() : beiAllgemein(a)));
	try {
		const liste = await api("rework_linie_auftraege", { station: zustand.station });
		if (liste.length === 1) return reworkLinie(liste[0]);
		if (!liste.length) { document.getElementById("liste").innerHTML = `<span class="fehlt">Auf keiner Linie läuft gerade ein Auftrag.</span>`; return; }
		suchListe("liste", [["Linie", "linie"], ["Auftrag", "auftrag"], ["Artikel", "name"], ["Sorten", (x) => x.sorten.map((y) => y.punkt || y.name).join(", ")]],
			liste, (x) => reworkLinie(x), "Suchen …");
	} catch (e) { meldung("rot", e.message); }
}
async function reworkLinie(a) {
	if (!a.sorten.length) return meldung("rot", "Für " + a.name + " ist kein Rework zugelassen (keine Rework-Regel).");
	let sorte = a.sorten.length === 1 ? a.sorten[0].artikel : null, behaelter = null, frei = [];
	try { frei = await api("freie_rework_behaelter", { station: zustand.station }); } catch (e) { /* nur scannen */ }
	app.innerHTML = kopf("Rework: " + a.name, true) + `<div class="panel">${esc(a.linie)} · Auftrag ${esc(a.auftrag)}</div>
		<label>Sorte (Entnahmepunkt)</label><div class="einheiten" id="sorten">${a.sorten.map((x) =>
			`<button type="button" data-a="sorte" data-s="${esc(x.artikel)}" class="${x.artikel === sorte ? "an" : ""}">${esc(x.punkt || x.name)}<small> ${esc(x.name)}</small></button>`).join("")}</div>` +
		textFeld("scan", "Rework-Behälter scannen oder unten antippen") +
		(frei.length ? `<div class="einheiten" id="beh">${frei.slice(0, 24).map((b) => `<button type="button" data-a="beh" data-c="${esc(b.code)}">${esc(b.code)}</button>`).join("")}</div>` : "") +
		zahlFeld("kg", "Gewicht von der Waage (kg, ohne Behälter)") +
		`<div class="reihe"><button class="knopf" data-a="zurueck-rw">← Aufträge</button><button class="knopf gruen" data-a="buchen">Buchen und Etikett drucken</button></div>`;
	aktionen(async (x, d) => {
		if (x === "zurueck-rw") return reworkStart();
		if (x === "sorte") { sorte = d.s; app.querySelectorAll("#sorten button").forEach((b) => b.classList.toggle("an", b.dataset.s === sorte)); return; }
		if (x === "beh") { behaelter = d.c; document.getElementById("scan").value = d.c; app.querySelectorAll("#beh button").forEach((b) => b.classList.toggle("an", b.dataset.c === d.c)); return fokus("kg"); }
		if (x !== "buchen") return beiAllgemein(x);
		if (!sorte) return meldung("rot", "Bitte die Sorte wählen.");
		const knopf = app.querySelector('[data-a="buchen"]');
		knopf.disabled = true;
		try {
			const e = await api("rework_linie", { station: zustand.station, auftrag: a.auftrag, rework_artikel: sorte,
				kg: zahl(document.getElementById("kg").value), behaelter: document.getElementById("scan").value.trim() || behaelter });
			gebindeDrucken(e.behaelter);
			ergebnis(e.name, ["Behälter: " + e.behaelter, "Menge: " + kg(e.menge), e.punkt ? "Entnahmepunkt: " + e.punkt : "", "Charge: " + e.charge,
				e.mhd ? "Verwendbar bis: " + e.mhd : "", "Von Auftrag " + e.auftrag], [],
				`<button class="knopf" data-a="etikett">Etikett nochmal</button><button class="knopf gruen" data-a="weiter">Nächster Behälter</button>`)((b) => {
				if (b === "etikett") return gebindeDrucken(e.behaelter, null);
				if (b === "weiter") return reworkLinie(a);
				beiAllgemein(b);
			});
		} catch (err) { knopf.disabled = false; meldung("rot", err.message); }
	});
	enter("scan", (v) => { behaelter = v; fokus("kg"); });
	enter("kg", () => app.querySelector('[data-a="buchen"]').click());
	fokus(frei.length ? "kg" : "scan");
}
async function reworkOhneLinie() {
	app.innerHTML = kopf("Rework ohne Linie", true) + `<p>In welchen Rework-Behälter?</p><div id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const liste = await api("rework_artikel");
		suchListe("liste", [["Rework-Artikel", "name"], ["Artikel", "artikel"], ["Allergengruppe", "allergengruppe"]], liste, (r) => reworkErfassen(r.artikel, r.name));
	} catch (e) { meldung("rot", e.message); }
}
function reworkErfassen(artikel, name) {
	app.innerHTML = kopf(name, true) +
		textFeld("scan", "Herkunft scannen: Teigbehälter, Kiste oder Charge") +
		zahlFeld("menge", "Menge (kg)") +
		textFeld("ziel", "Rework-Behälter scannen (optional)") +
		`<div class="reihe"><button class="knopf gruen" data-a="buchen">Buchen</button></div>`;
	aktionen(async (a) => {
		if (a !== "buchen") return beiAllgemein(a);
		try {
			const e = await api("rework_erfassen", {
				station: zustand.station,
				quelle: document.getElementById("scan").value.trim(),
				menge: zahl(document.getElementById("menge").value),
				rework_artikel: artikel,
				ziel_behaelter: document.getElementById("ziel").value.trim() || null,
			});
			ergebnis(e.name, ["Neue Rework-Charge: " + e.charge, "Menge: " + kg(e.menge), e.behaelter ? "Behälter: " + e.behaelter : "", e.mhd ? "Verwendbar bis: " + e.mhd : ""].filter(Boolean), e.hinweise)(beiAllgemein);
		} catch (err) { meldung("rot", err.message); }
	});
	enter("scan", () => fokus("menge"));
	enter("menge", () => fokus("ziel"));
	fokus("scan");
}
