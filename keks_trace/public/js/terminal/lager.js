// Terminal: Umlagern, Karton anbrechen, Silo leer melden.

import { api, app, esc, fokus, kg, meldung, mg, rund, stk, zustand } from "./basis.js";
import { textFeld } from "./tastatur.js";
import { aktionen, anzahlAbfragen, beiAllgemein, enter, ergebnis, kopf, suche, tabelle } from "./rahmen.js";
import { positionenHtml, statusMarke } from "./paletten.js";

// ------------------------------------------------------------------ Umlagern
let umgelagert = [];
export let umlagerNach = null;
// Station neu gestartet: Ziel neu wählen (ES-Module dürfen fremde Variablen nicht direkt setzen)
export function umlagerZielVergessen() {
	umlagerNach = null;
}
let umlagerZiele = [];
export async function umlagernStart(hinweis) {
	if (!umlagerNach) return umlagerZielWaehlen();
	const nach = umlagerNach.name;
	const zurueck = !!umlagerNach.zurueck;
	const titel = (zurueck ? "Zurück ins " : "Umlagern nach ") + umlagerNach.titel;
	app.innerHTML = kopf(titel, true) +
		(umlagerZiele.length > 1 ? `<div class="reihe"><button class="knopf" data-a="ziel-wechseln">Anderes Ziel wählen</button></div>` : "") +
		textFeld("scan", "Palette oder Los scannen – oder Los-Nummer eintippen") +
		`<div class="reihe"><button class="knopf blau" data-a="liste">Ohne Scanner: aus der Liste wählen</button></div>` +
		(umgelagert.length ? `<div class="panel"><div class="fehlt" style="font-size:16px">Heute hier umgelagert</div>${umgelagert.map((x) =>
			`<div class="zeile"><div>${esc(x.name)}<br><span class="fehlt" style="font-size:16px">Los ${esc(x.charge)}</span></div><div class="rechts">${esc(stk(x.anzahl, x.einheit))}</div></div>`).join("")}</div>` : "");
	if (hinweis) meldung("gruen", hinweis);
	aktionen((a) => {
		if (a === "ziel-wechseln") { umlagerNach = null; return umlagerZielWaehlen(); }
		if (a === "liste") return umlagernListe();
		beiAllgemein(a);
	});
	const buchen = async (args) => {
		try {
			const e = await api("umlagern", { station: zustand.station, nach, ...args });
			umgelagert = e.positionen.concat(umgelagert).slice(0, 12);
			umlagernStart("Umgelagert: " + e.positionen.map((x) => stk(x.anzahl, x.einheit)).join(", ") + " nach " + e.nach);
		} catch (err) { umlagernStart(); meldung("rot", err.message); }
	};
	// Schritt für Schritt ohne Scanner: Fertigware im Lager antippen (Artikel suchen, Los, lose oder Palette)
	async function umlagernListe() {
		app.innerHTML = kopf(titel + ": was?", true) +
			`<p>1. Zeile antippen (oben suchen: Artikel, Los) · 2. Anzahl eingeben · 3. OK</p><div id="ware">Lädt …</div>`;
		aktionen((a) => (a === "zurueck" ? umlagernStart() : beiAllgemein(a)));
		try {
			const liste = await api("fertigware_im_lager", { station: zustand.station, aus_verkauf: zurueck ? 1 : 0 });
			const el = document.getElementById("ware");
			if (!liste.length) { el.innerHTML = `<p class="fehlt">Keine Fertigware im Lager.</p>`; return; }
			el.innerHTML = tabelle([["Artikel", "artikel"], ["Bezeichnung", "name"], ["Los", "los"], ["MHD", "mhd"], ["Wo", "wo"], ["Bestand", "menge_text", 1]], liste, "ware");
			const f = document.createElement("input");
			f.className = "feld"; f.placeholder = "Suchen: Artikel, Bezeichnung oder Los …"; f.dataset.art = "text"; f.setAttribute("inputmode", "none");
			el.insertBefore(f, el.firstChild);
			f.addEventListener("input", () => {
				const t = f.value.trim().toLowerCase();
				el.querySelectorAll("tbody tr").forEach((tr) => { tr.style.display = !t || tr.textContent.toLowerCase().includes(t) ? "" : "none"; });
			});
			aktionen(async (a, d) => {
				if (a === "zurueck") return umlagernStart();
				if (a !== "ware") return beiAllgemein(a);
				const w = liste[+d.i];
				if (w.palette) return verarbeiten(w.palette);
				const einheiten = await api("einheiten", { artikel: w.artikel });
				anzahlAbfragen("Los " + w.los + " (lose: " + w.menge_text + ")", esc(w.name), einheiten, null, (n, e) => buchen({ code: w.charge, anzahl: n, einheit: e }), umlagernListe);
			});
		} catch (e) { meldung("rot", e.message); }
	}
	const verarbeiten = async (v) => {
		if (!v) return;
		try {
			const i = await api("info", { code: v });
			if (i.typ === "palette") {
				const p = i;
				app.innerHTML = kopf("Palette …" + p.nve.slice(-6), true) +
					`<div class="panel"><div class="nve">${esc(p.nve)} ${statusMarke(p.status)}<br><small>${esc(p.kartons || "")}</small></div></div>` +
					`<div class="reihe"><button class="knopf gruen" data-a="ganz">Ganze Palette umlagern</button></div><p class="fehlt">Oder Position antippen für einzelne Kartons.</p>` +
					positionenHtml(p, "pos");
				aktionen((a, d) => {
					if (a === "zurueck") return umlagernStart();
					if (a === "ganz") return buchen({ palette: p.nve, ganz: 1 });
					if (a === "pos") {
						const pos = p.positionen[+d.i];
						return anzahlAbfragen("Von Palette …" + p.nve.slice(-6), `${esc(pos.name)} · Los ${esc(pos.charge)}`,
							[{ einheit: pos.einheit, faktor: 1 }], { einheit: pos.einheit }, (n) => buchen({ palette: p.nve, charge: pos.charge, anzahl: n, einheit: pos.einheit }), umlagernStart);
					}
					beiAllgemein(a);
				});
				return;
			}
			if (i.typ !== "charge") throw new Error("Bitte eine Palette oder ein Los scannen.");
			const einheiten = await api("einheiten", { artikel: i.artikel });
			anzahlAbfragen("Los " + i.charge, esc(i.artikelname), einheiten, null, (n, e) => buchen({ code: i.charge, anzahl: n, einheit: e }), umlagernStart);
		} catch (e) { meldung("rot", e.message); }
	};
	enter("scan", verarbeiten);
	fokus("scan");
}
async function umlagerZielWaehlen() {
	app.innerHTML = kopf("Umlagern wohin?", true) + `<div class="raster" id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const ziele = await api("umlager_ziele", { station: zustand.station });
		umlagerZiele = ziele;
		if (!ziele.length) throw new Error("Es ist noch kein Lagerort als Umlager-Ziel eingerichtet.");
		if (ziele.length === 1) { umlagerNach = ziele[0]; return umlagernStart(); }
		document.getElementById("liste").innerHTML = ziele.map((z, i) =>
			`<button class="knopf${z.lagerverkauf ? " gruen" : ""}" data-a="ziel" data-i="${i}">${z.zurueck ? "Zurück ins " : ""}${esc(z.titel)}${z.lagerverkauf ? "<br><small>Lagerverkauf</small>" : z.zurueck ? "<br><small>Rücknahme aus dem Lagerverkauf</small>" : ""}</button>`).join("");
		aktionen((a, d) => {
			if (a === "ziel") { umlagerNach = ziele[+d.i]; return umlagernStart(); }
			beiAllgemein(a);
		});
	} catch (e) { meldung("rot", e.message); }
}
// ------------------------------------------------------------------ Karton anbrechen (Vorrat am Tisch)
export async function anbrechenStart(hinweis) {
	app.innerHTML = kopf("Karton anbrechen", true) + textFeld("scan", "Etikett vom neuen Karton / der neuen Rolle scannen") +
		`<p class="fehlt">Ohne Scanner: beim Vorrat auf „Wählen“ tippen.</p><div id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	if (hinweis) meldung("gruen", hinweis);
	const buchen = async (code) => {
		try {
			const e = await api("anbrechen", { station: zustand.station, code });
			anbrechenStart("Angebrochen: " + e.name + ", Charge " + e.charge + " (" + rund(e.menge) + ") → " + e.vorrat);
		} catch (err) { meldung("rot", err.message); }
	};
	enter("scan", (v) => v && buchen(v));
	fokus("scan");
	try {
		const liste = await api("vorraete", { station: zustand.station });
		document.getElementById("liste").innerHTML = tabelle([["Vorrat", "vorrat"], ["Artikel", "name"],
			["Charge dran", (v) => v.chargen.length ? v.chargen[0].charge + (v.chargen.length > 1 ? ` (+${v.chargen.length - 1} weitere)` : "") : "– leer –"], ["Bestand", (v) => mg(v.bestand, v.einheit), 1], ["", () => "Wählen ›"]], liste, "waehlen");
		aktionen(async (a, d) => {
			if (a !== "waehlen") return beiAllgemein(a);
			const v = liste[+d.i];
			app.innerHTML = kopf("Anbrechen: " + v.name, true) + `<p>Welche Charge kommt an den Tisch? (ältestes MHD zuerst)</p><div id="chargen">Lädt …</div>`;
			aktionen((b) => (b === "zurueck" ? anbrechenStart() : beiAllgemein(b)));
			const ch = await api("lager_chargen", { station: zustand.station, artikel: v.artikel });
			document.getElementById("chargen").innerHTML = ch.length
				? tabelle([["Charge", "charge"], ["Im Lager", (c) => mg(c.menge, v.einheit), 1], ["MHD", (c) => c.mhd || ""]], ch, "charge")
				: `<p class="fehlt">Keine Charge im Lager. Erst Wareneingang buchen.</p>`;
			aktionen((b, e) => (b === "charge" ? buchen(ch[+e.i].charge) : b === "zurueck" ? anbrechenStart() : beiAllgemein(b)));
		});
	} catch (e) { meldung("rot", e.message); }
}
// ------------------------------------------------------------------ Silo leer
export async function siloLeer() {
	app.innerHTML = kopf("Silo leer melden", true) + `<p>Welches Silo oder welcher Tank ist leer?</p><div class="raster" id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const liste = await api("silos", { station: zustand.station });
		document.getElementById("liste").innerHTML = liste.map((s) => `<button class="knopf" data-a="silo" data-name="${esc(s.silo)}">${esc(s.silo)}<small>rechnerisch ${esc(mg(s.bestand, s.einheit))}</small></button>`).join("") || "Keine Silos angelegt.";
		suche("liste");
		aktionen((a, d) => (a === "silo" ? siloBestaetigen(d.name) : beiAllgemein(a)));
	} catch (e) { meldung("rot", e.message); }
}
function siloBestaetigen(silo) {
	const box = document.createElement("div");
	box.className = "dialog";
	box.innerHTML = `<div class="panel"><p class="gross" style="font-size:26px">${esc(silo)} ist wirklich leer?</p>
		<p class="fehlt">Ein rechnerischer Rest wird als Silo-Differenz ausgebucht.</p>
		<div class="reihe"><button class="knopf" id="nein">Nein</button><button class="knopf rot" id="ja">Ja, ist leer</button></div></div>`;
	document.body.appendChild(box);
	box.querySelector("#nein").onclick = () => box.remove();
	box.querySelector("#ja").onclick = async () => {
		box.remove();
		try {
			const e = await api("silo_leer", { station: zustand.station, silo });
			ergebnis("Silo leer", [silo + " ist leer gemeldet.", "Rechnerischer Rest ausgebucht: " + kg(e.rest)], e.hinweise)(beiAllgemein);
		} catch (err) { meldung("rot", err.message); }
	};
}
