// Terminal: Station wählen, Startseite mit Menü, Prüfungen (CP/CCP), Tagesübersicht.

import { api, app, esc, fokus, kopfLaden, meldung, speichern, status, ton, zustand } from "./basis.js";
import { textFeld, zahlFeld } from "./tastatur.js";
import { aktionen, beiAllgemein, kopf, suche } from "./rahmen.js";
import { linieStart, packstationStart, paletteFertigStart, vpcStart } from "./linie.js";
import { herstellenStart, schnellStart } from "./herstellen.js";
import { reworkStart } from "./rework.js";
import { wareneingangStart } from "./wareneingang.js";
import { einwickelnStart, palettenStart } from "./paletten.js";
import { dhlStart, lieferungStart } from "./lieferung.js";
import { anbrechenStart, siloLeer, umlagernStart } from "./lager.js";
import { infoScan } from "./info.js";
import { init } from "./main.js";

// Statusleiste: ⌂ zur Startseite, ← wie der Zurück-Knopf der Maske (hier, weil basis.js nichts importiert)
document.getElementById("status-start").addEventListener("click", () => zustand.station && startseite());
document.getElementById("status-zurueck").addEventListener("click", () => {
	const z = app.querySelector('[data-a="zurueck"], [data-a="zurueck-ansatz"]');
	if (z) z.click(); else if (zustand.station) startseite();
});
// ------------------------------------------------------------------ Station
export async function stationWaehlen() {
	status("", "Bereit.");
	app.innerHTML = `<div class="kopf"><h1>Keks Trace Terminal</h1></div><div id="meldung"></div>
		<p>An welcher Station steht dieses Terminal?</p><div class="raster" id="liste">Lädt …</div>`;
	try {
		const liste = await api("stationen");
		if (!liste.length) {
			document.getElementById("liste").innerHTML = "Es ist noch keine Station eingerichtet (Terminal Station in ERPNext anlegen).";
			suche("liste");
			return;
		}
		document.getElementById("liste").innerHTML = liste
			.map((s) => `<button class="knopf" data-a="station" data-name="${esc(s.name)}">${esc(s.name)}${s.typ !== s.name ? `<small>${esc(s.typ)}</small>` : ""}</button>`)
			.join("");
		aktionen((a, d) => { if (a === "station") { speichern("kt_station", d.name); init(); } });
	} catch (e) { meldung("rot", e.message); }
}
const UEBERSICHT = ["uebersicht", "Tagesübersicht", "Aufträge des Tages je Linie: Status, Fortschritt, Hinweise"];
// Knöpfe aus den Funktionen der Station (in ERPNext unter Terminal Station einstellbar)
function menue() {
	const f = zustand.funktionen || [];
	if (zustand.typ === "Verpackungs-PC") return [
		["vpc", "Linie verpacken", "Verpackungsauftrag der Backstraße: Karton auf Palette und lose Ware buchen"],
		["vpc_lose", "Lose Ware verpacken", "erst das Linienlager leer, sonst nach Bedarf aus dem Lager in Beutel / Karton"],
		["paletten", "Paletten", "Neue Palette, Etikett, umpacken"],
		["info", "Info-Scan", "Charge, Behälter oder Palette"],
		UEBERSICHT,
	];
	if (zustand.typ === "Paletten-Terminal") return [
		["einwickeln", "Palette einwickeln", "abschließen, NVE-Etikett, versandbereit ins Lager"],
		["paletten", "Paletten", "Neue Palette, Etikett, umpacken"],
		["info", "Info-Scan", "Charge, Behälter oder Palette"],
		UEBERSICHT,
	];
	const fw = zustand.nur_fertigware;
	const m = [];
	const kneter = f.includes("herstellen") && f.includes("linie");
	if (kneter) m.push(["herstellen", "Kneten", "Grundteig-Kübel und Zutaten → Teig direkt in den Former"]);
	else if (f.includes("herstellen")) m.push(["herstellen", fw ? "Verpacken" : "Herstellen", fw ? "Los mit MHD, nach Kundenauftrag, auf Palette" : (zustand.stufen || []).join(", ")]);
	if (f.includes("wareneingang")) m.push(["wareneingang", "Wareneingang", "Anlieferung buchen, ins Silo oder als Gebinde"]);
	if (f.includes("lieferung") && zustand.typ === "Herzen Verpackung") m.push(["dhl", "Lieferung (DHL)", "Pakete packen, wiegen, Lieferschein, Sendungsnummer"]);
	else if (f.includes("lieferung")) m.push(["lieferung", "Lieferung", "Paletten und Kartons an einen Kunden"]);
	if (f.includes("umlagern")) m.push(["umlagern", "Umlagern", zustand.umlager_ziel ? "in den Lagerverkauf oder zurück ins Lager" : "in ein anderes Lager oder in den Lagerverkauf"]);
	if (f.includes("paletten")) m.push(["paletten", "Paletten", "Neue Palette, Etikett, anbrechen, umpacken"]);
	if (f.includes("rework")) m.push(["rework", "Rework", "Behälter von der Linie wiegen: Sorte, kg, Etikett"]);
	if (zustand.vorraete) m.push(["anbrechen", "Karton anbrechen", "Neue Rolle / neuer Karton an den Tisch (Folie, Etikett, Schleife)"]);
	if (f.includes("silo")) m.push(["silo", zustand.vorraete ? "Leer melden" : "Silo leer melden", zustand.vorraete ? "Behälter oder Vorrat ist leer" : "Silo oder Tank ist leergefahren"]);
	if (f.includes("linie") && !kneter) m.push(["linie", "An die Linie", "Kübel einkippen, Füllung, Glasur, Schokolade nachfüllen"]);
	if (f.includes("packstation")) m.push(["packstation", "Packstation", "Auftrag, Anlage, Los, MHD, Kartonlabel"]);
	if (f.includes("palette_fertig")) m.push(["palette_fertig", "Palette fertig", "Kartons zählen, buchen, Palettenlabel"]);
	m.push(["info", "Info-Scan", "Charge, Behälter, Silo oder Palette"]);
	m.push(UEBERSICHT);
	return m;
}
// ------------------------------------------------------------------ Prüfungen (CP/CCP)
export function kennzeichenMarken(liste) {
	return (liste || []).map((k) => `<span class="marke ${k === "Bio" ? "gruen" : ""}">${esc(k === "Bio" ? "BIO" : k)}</span>`).join("");
}
export function pruefFelder(plaene, praefix) {
	return (plaene || []).map((p, i) => {
		const id = praefix + i;
		let html = `<div class="panel" style="margin:12px 0"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
			<b>${esc(p.frage)}</b><span class="marke ${p.lenkung === "CCP" ? "rot" : "orange"}">${esc(p.lenkung)}</span></div>
			<div class="fehlt" style="font-size:16px">Grenzwert: ${esc(p.grenzwert)}</div>`;
		if (p.art === "Messwert") html += zahlFeld(id, "Messwert" + (p.einheit ? " (" + esc(p.einheit) + ")" : ""));
		else if (p.art === "Ja/Nein") html += `<div class="einheiten" data-pw="${id}"><button type="button" data-pwv="1">✔ in Ordnung</button><button type="button" data-pwv="0">✖ nicht in Ordnung</button></div>`;
		else html += p.pruefkoerper.map((k, j) => `<div class="zeile"><div>${esc(k)}</div>
			<div class="einheiten" data-pw="${id}-${j}" style="margin:0;flex:0 0 440px"><button type="button" data-pwv="1">✔ erkannt</button><button type="button" data-pwv="0">✖ nicht erkannt</button></div></div>`).join("");
		return html + "</div>";
	}).join("");
}
app.addEventListener("click", (e) => {
	const b = e.target.closest("[data-pwv]");
	if (!b) return;
	const box = b.closest("[data-pw]");
	box.dataset.wert = b.dataset.pwv;
	box.querySelectorAll("button").forEach((x) => { x.classList.toggle("an", x === b); x.style.background = x === b && b.dataset.pwv === "0" ? "var(--rot)" : ""; });
});
export function pruefWerte(plaene, praefix) {
	const out = {};
	(plaene || []).forEach((p, i) => {
		const id = praefix + i;
		if (p.art === "Messwert") {
			const f = document.getElementById(id);
			if (f && f.value !== "") out[p.pruefplan] = { wert: f.value };
		} else if (p.art === "Ja/Nein") {
			const b = app.querySelector(`[data-pw="${id}"]`);
			if (b && b.dataset.wert !== undefined) out[p.pruefplan] = { ok: b.dataset.wert === "1" };
		} else {
			const k = {};
			let alle = true;
			p.pruefkoerper.forEach((name, j) => {
				const b = app.querySelector(`[data-pw="${id}-${j}"]`);
				if (b && b.dataset.wert !== undefined) k[name] = b.dataset.wert === "1"; else alle = false;
			});
			if (alle) out[p.pruefplan] = { koerper: k };
		}
	});
	return out;
}
async function pruefLeiste() {
	const el = document.getElementById("pruef-leiste");
	if (!el) return;
	let liste = [];
	try { liste = await api("pruefungen_faellig", { station: zustand.station }); } catch (e) { return; }
	if (!liste.length) { el.innerHTML = ""; return; }
	const faellig = liste.filter((p) => p.faellig);
	el.innerHTML = faellig.map((p) => {
		const i = liste.indexOf(p);
		return `<button class="knopf ${p.sperrt ? "rot" : ""}" data-pr="${i}" style="margin-bottom:12px;${p.sperrt ? "" : "background:var(--orange);color:#111"}">Prüfung fällig: ${esc(p.titel)}
			<small style="color:inherit">${esc(p.lenkung)}${p.letzte_ok ? " · zuletzt bestanden " + esc(p.letzte_ok) : " · heute noch nicht geprüft"}${p.sperrt ? " · Buchen gesperrt, bis bestanden" : ""}</small></button>`;
	}).join("") + `<div class="fehlt" style="font-size:16px;margin:0 0 14px">${liste.filter((p) => !p.faellig).map((p) =>
		`✔ ${esc(p.titel)}: nächste um ${esc(p.faellig_ab)}${p.bald ? " (bald)" : ""}`).join(" · ")}</div>`;
	el.querySelectorAll("[data-pr]").forEach((b) => b.addEventListener("click", () => pruefDialog(liste[+b.dataset.pr])));
}
function pruefDialog(p) {
	app.innerHTML = kopf(p.titel, true) + pruefFelder([p], "pd") +
		(p.korrektur ? `<p class="fehlt">Bei Abweichung: ${esc(p.korrektur)}</p>` : "") +
		textFeld("bem", "Bemerkung / Korrekturmaßnahme (bei Abweichung Pflicht)") +
		`<div class="reihe"><button class="knopf gruen" data-a="speichern">Prüfung speichern</button></div>`;
	aktionen(async (a) => {
		if (a !== "speichern") return beiAllgemein(a);
		try {
			const r = await api("pruefung_erfassen", {
				station: zustand.station, pruefplan: p.pruefplan,
				eingabe: pruefWerte([p], "pd")[p.pruefplan] || {},
				bemerkung: document.getElementById("bem").value.trim() || null,
			});
			app.innerHTML = kopf(p.titel, true) + (r.ok
				? `<div class="meldung gruen">Bestanden<small>Protokoll ${esc(r.pruefung)}</small></div>`
				: `<div class="meldung rot">Abweichung<small>${esc(r.folge || "")}${r.gesperrt.length ? "<br>Gesperrt: " + r.gesperrt.map(esc).join(", ") : ""}<br>Protokoll ${esc(r.pruefung)}</small></div>`) +
				`<div class="reihe"><button class="knopf blau" data-a="zurueck">Fertig</button></div>`;
			ton(r.ok);
			aktionen(beiAllgemein);
		} catch (e) { meldung("rot", e.message); }
	});
	fokus("pd0");
}
export function startseite() {
	kopfLaden();
	app.innerHTML = kopf(zustand.station) + `<div id="pruef-leiste"></div><div class="raster">${menue()
		.map(([a, t, u]) => `<button class="knopf ${a === "info" ? "" : "blau"}" data-a="${a}">${esc(t)}<small>${esc(u)}</small></button>`)
		.join("")}</div>`;
	aktionen((a) => {
		if (a === "herstellen") return herstellenStart();
		if (a === "rework") return reworkStart();
		if (a === "silo") return siloLeer();
		if (a === "anbrechen") return anbrechenStart();
		if (a === "vpc") return vpcStart();
		if (a === "dhl") return dhlStart();
		if (a === "vpc_lose") return schnellStart(true);
		if (a === "einwickeln") return einwickelnStart();
		if (a === "info") return infoScan();
		if (a === "uebersicht") return tagesuebersicht();
		if (a === "wareneingang") return wareneingangStart();
		if (a === "lieferung") return lieferungStart();
		if (a === "paletten") return palettenStart();
		if (a === "umlagern") return umlagernStart();
		if (a === "linie") return linieStart();
		if (a === "packstation") return packstationStart();
		if (a === "palette_fertig") return paletteFertigStart();
		beiAllgemein(a);
	});
	pruefLeiste();
}
// ------------------------------------------------------------------ Tagesübersicht
// Aufträge des Tages je Linie mit Status, Fortschritt und Hinweis – wie der Orderblock bei FOBIS
const PA_FARBE = { "Läuft": "gruen", Freigegeben: "orange", Geplant: "", Fertig: "", Abgebrochen: "rot" };
async function tagesuebersicht(datum) {
	app.innerHTML = kopf("Tagesübersicht", true) + `<div id="tag">Lädt …</div>`;
	aktionen(beiAllgemein);
	let t;
	try { t = await api("tagesuebersicht", { station: zustand.station, datum: datum || null }); } catch (e) { return meldung("rot", e.message); }
	const tagVerschieben = (n) => { const d = new Date(t.datum_iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };
	document.getElementById("tag").innerHTML =
		`<div class="reihe"><button class="knopf klein" data-a="tag" data-d="${tagVerschieben(-1)}">← Vortag</button>
			<div style="flex:2 1 260px;text-align:center"><div class="gross">${esc(t.datum)}${t.heute ? " · heute" : ""}</div>
			<div class="fehlt" style="font-size:16px">Offen ${t.offen} · Fertig ${t.fertig}</div></div>
			<button class="knopf klein" data-a="tag" data-d="${tagVerschieben(1)}">Folgetag →</button></div>` +
		(t.linien.length ? t.linien.map((l) => `<h2 style="margin:18px 0 0">${esc(l.linie)} <span class="fehlt" style="font-size:16px;font-weight:400">offen ${l.offen} · fertig ${l.fertig}</span></h2>
			<table class="tab"><thead><tr><th>Status</th><th>Auftrag</th><th>Artikel</th><th>Kunde</th><th class="z">Bestellt</th><th class="z">Gebucht</th></tr></thead><tbody>
			${l.auftraege.map((a) => `<tr><td><span class="marke ${PA_FARBE[a.status] || ""}" style="margin:0">${esc(a.status)}</span>${a.vortag ? `<small class="fehlt" style="display:block;font-size:14px">vom ${esc(a.datum)}</small>` : ""}</td>
				<td>${esc(a.auftrag)}</td><td>${esc(a.name)}${a.hinweis ? `<div class="hinweis-buero" style="font-size:17px;padding:6px 10px;margin:6px 0 0">${esc(a.hinweis)}</div>` : ""}</td>
				<td>${esc(a.kunde || "Lager")}</td><td class="z">${esc(a.menge_text)}</td>
				<td class="z">${esc(a.gebucht_text)}<div class="balken"><div style="width:${Math.round(a.anteil * 100)}%"></div></div></td></tr>`).join("")}
			</tbody></table>`).join("")
			: `<p class="fehlt">An diesem Tag sind keine Produktionsaufträge geplant.</p>`) +
		`<div class="reihe"><button class="knopf" data-a="tag" data-d="">Heute</button><button class="knopf" data-a="neu">Aktualisieren</button></div>`;
	aktionen((a, d) => {
		if (a === "tag") return tagesuebersicht(d.d || null);
		if (a === "neu") return tagesuebersicht(t.datum_iso);
		beiAllgemein(a);
	});
}
