// Terminal: Bausteine der Masken (Kopf, Tabelle, Suchliste, Aktionen), Etikettendruck, Anzahl-Dialog.

import { api, app, ein, esc, fokus, meldung, rund, speichern, status, ton, zahl, zustand } from "./basis.js";
import { einheitSetzen, einheitWahl, zahlFeld } from "./tastatur.js";
import { startseite, stationWaehlen } from "./station.js";

// ------------------------------------------------------------------ Rahmen
export function kopf(titel, zurueck) {
	status("", "Bereit."); // neuer Bildschirm: alte Meldung weg (eine neue kommt ggf. direkt danach)
	return `<div class="kopf">
		<h1>${esc(titel)}</h1>
		<div style="text-align:right"><div class="klein">Station ${esc(zustand.station || "-")}</div>${zurueck ? `<button class="link" data-a="zurueck">← Zurück</button>` : `<button class="link" data-a="station-wechseln">Station wechseln</button>`}</div>
	</div><div id="meldung"></div>`;
}
// Tabelle wie bei FOBIS: spalten = [[Titel, Feld, rechtsbündig?]], Zeile antippen = aktion mit data-i
export function tabelle(spalten, zeilen, aktion) {
	return `<table class="tab"><thead><tr>${spalten.map(([t, , r]) => `<th class="${r ? "z" : ""}">${esc(t)}</th>`).join("")}</tr></thead><tbody>${zeilen.map((z, i) =>
		`<tr ${aktion ? `data-a="${aktion}" data-i="${i}"` : ""}>${spalten.map(([, f, r]) => `<td class="${r ? "z" : ""}">${esc(typeof f === "function" ? f(z) : z[f])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}
// Lange Listen wie bei FOBIS: Suchfeld + Tabelle, zeigt höchstens 50 Treffer (bei 2.000 Artikeln keine Knopfwüste).
// Eine Zeile antippen ruft wahl(zeile) auf. Gesucht wird in allen Spalten.
export function suchListe(elId, spalten, zeilen, wahl, platzhalter) {
	const el = document.getElementById(elId);
	if (!el) return;
	if (!zeilen.length) { el.innerHTML = `<p class="fehlt">Keine Einträge.</p>`; return; }
	const MAX = 50;
	const text = zeilen.map((z) => spalten.map(([, f]) => (typeof f === "function" ? f(z) : z[f]) || "").join(" ").toLowerCase());
	el.innerHTML = `<input class="feld" data-art="text" data-nummern inputmode="none" autocomplete="off" placeholder="${esc(platzhalter || "Suchen …")}">
		<div class="treffer"></div><p class="fehlt mehr" style="font-size:16px"></p>`;
	const f = el.querySelector("input"), box = el.querySelector(".treffer"), mehr = el.querySelector(".mehr");
	const zeigen = () => {
		const worte = f.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
		const idx = [];
		for (let i = 0; i < zeilen.length; i++) if (worte.every((w) => text[i].includes(w))) idx.push(i);
		const sicht = idx.slice(0, MAX).map((i) => ({ ...zeilen[i], _i: i }));
		box.innerHTML = tabelle(spalten, sicht, "wahl");
		box.querySelectorAll("tr[data-i]").forEach((tr) => { tr.dataset.i = sicht[+tr.dataset.i]._i; });
		mehr.textContent = idx.length > MAX ? `${idx.length} Treffer, die ersten ${MAX} angezeigt – Suche verfeinern.` : `${idx.length} von ${zeilen.length}`;
	};
	f.addEventListener("input", zeigen);
	box.addEventListener("click", (e) => { const tr = e.target.closest("tr[data-i]"); if (tr) wahl(zeilen[+tr.dataset.i]); });
	zeigen();
}
export function zahlText(n) { return n == null ? "" : rund(n, 3).toLocaleString("de-DE"); }
// Position wie bei FOBIS: Bestellt / Erledigt / ToDo groß
export function positionBox(titel, rechts, bestellt, erledigt, todo, einheit) {
	return `<div class="position"><div class="titel"><b>${esc(titel)}</b><span>${esc(rechts || "")}</span></div>
		<div class="wert">Bestellt<div>${esc(zahlText(bestellt))}</div></div>
		<div class="wert">Erledigt<div>${esc(zahlText(erledigt))}</div></div>
		<div class="wert">ToDo<div>${esc(zahlText(todo))}</div>${esc(einheit ? ein(einheit) : "")}</div></div>`;
}
export function aktionen(handler) {
	app.querySelectorAll("[data-a]").forEach((b) => b.addEventListener("click", () => handler(b.dataset.a, b.dataset)));
}
export function enter(id, fn) {
	const f = document.getElementById(id);
	if (f) f.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); fn(f.value.trim(), f); } });
}
export function beiAllgemein(a) {
	if (a === "zurueck") return startseite();
	if (a === "station-wechseln") { speichern("kt_station", ""); zustand.station = null; return stationWaehlen(); }
}
// Etiketten: auf den Netzwerkdrucker, der an der Terminal Station eingetragen ist (Abschnitt
// „Etikettendrucker“), sonst wie bisher über den Browser. Geht der Drucker nicht: Meldung und Browserdruck.
function browserDruck(url) { window.open(url, "_blank"); }
let druckTimer;
function druckHinweis(art, text, imBrowser) {
	let el = document.getElementById("druckhinweis");
	if (!el) { el = document.createElement("div"); el.id = "druckhinweis"; document.body.appendChild(el); }
	clearTimeout(druckTimer);
	el.innerHTML = art ? `<div class="meldung ${art}">${esc(text)}${imBrowser ? `<div class="reihe"><button class="knopf" data-d="browser">Im Browser drucken</button><button class="knopf" data-d="zu">Schließen</button></div>` : ""}</div>` : "";
	el.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => { el.innerHTML = ""; if (b.dataset.d === "browser") imBrowser(); }));
	if (art === "rot") ton(false);
	else if (art) druckTimer = setTimeout(() => { el.innerHTML = ""; }, art === "gruen" ? 5000 : 20000);
}
// Nachdruck ohne Anlass (gleicher Inhalt, nicht Teil einer Buchung): das System fragt nach dem Grund.
// Jeder Druck steht mit Grund im Protokoll „Etikettendruck“ (druckprotokoll.py).
function grundFragen(r) {
	return new Promise((fertig) => {
		const d = document.createElement("div");
		d.className = "dialog";
		d.innerHTML = `<div class="panel"><h2>Warum nochmal drucken?</h2>
			<p class="fehlt">Dieses Etikett wurde schon gedruckt. Der Nachdruck wird mit Grund protokolliert.</p>
			<div class="reihe">${r.gruende.map((g) => `<button class="knopf" data-g="${esc(g.wert)}">${esc(g.text)}</button>`).join("")}</div>
			<div class="reihe"><button class="knopf" data-g="">Abbrechen</button></div></div>`;
		d.querySelectorAll("[data-g]").forEach((b) => b.addEventListener("click", () => { d.remove(); fertig(b.dataset.g || null); }));
		document.body.appendChild(d);
	});
}
// grund: "ablauf" = Druck gehört zur Buchung; null = Nachdruck per Knopf (Server fragt ggf. nach dem Grund)
async function druckeEtikett(art, args, url, grund) {
	const drucker = (zustand.drucker || {})[art];
	const daten = Object.assign({ station: zustand.station, art }, args, grund ? { grund } : {});
	const nochmal = async (r) => {
		druckHinweis("", "");
		const g = await grundFragen(r);
		return g ? druckeEtikett(art, args, url, g) : false;
	};
	const imBrowser = async () => {
		try {
			const v = await api("etikett_vormerken", daten);
			if (v.grund_noetig) return nochmal(v);
			browserDruck(url);
		} catch (e) { druckHinweis("rot", e.message); }
		return false;
	};
	if (!drucker) return imBrowser();
	druckHinweis("orange", "Druckt auf " + drucker + " …");
	try {
		const r = await api("etikett_drucken", daten);
		if (r.grund_noetig) return nochmal(r);
		druckHinweis("gruen", (r.etiketten > 1 ? r.etiketten + " Etiketten" : "Etikett") + " an " + r.drucker + " geschickt.");
		return true;
	} catch (e) {
		druckHinweis("rot", e.message, imBrowser);
		return false;
	}
}
export function etikettDrucken(nve, grund = "ablauf", geprueft) {
	return druckeEtikett("palette", Object.assign({ nve }, geprueft !== undefined ? { geprueft } : {}), "/nve_etikett?nve=" + encodeURIComponent(nve) + "&druck=1", grund);
}
export function etikettNachdrucken(nve) { return etikettDrucken(nve, null); }
export function kartonDrucken(anzahl) {
	druckeEtikett("karton", { anzahl }, "/karton_etikett?druck=1&station=" + encodeURIComponent(zustand.station) + "&anzahl=" + anzahl);
}
export function gebindeDrucken(codes, grund = "ablauf") {
	const liste = [].concat(codes).join(",");
	return druckeEtikett("gebinde", { codes: liste }, "/gebinde_etikett?druck=1&codes=" + encodeURIComponent(liste), grund);
}
// ------------------------------------------------------------------ Suche in langen Listen
// Ab 8 Einträgen bekommt eine Knopfliste ein Suchfeld; filtert beim Tippen (Scanner geht weiter ins Scanfeld).
export function suche(listeId) {
	const liste = document.getElementById(listeId);
	if (!liste || liste.children.length < 8 || document.getElementById(listeId + "-suche")) return;
	const f = document.createElement("input");
	f.id = listeId + "-suche";
	f.className = "feld";
	f.placeholder = "Suchen …";
	f.style.marginBottom = "12px";
	liste.parentNode.insertBefore(f, liste);
	f.addEventListener("input", () => {
		const t = f.value.trim().toLowerCase();
		[...liste.children].forEach((k) => { k.style.display = !t || k.textContent.toLowerCase().includes(t) ? "" : "none"; });
	});
}
export function ergebnis(titel, zeilen, hinweise, extra) {
	app.innerHTML = kopf(titel, true) + `
		<div class="meldung gruen">Gebucht<small>${zeilen.map(esc).join("<br>")}</small></div>
		${(hinweise || []).map((h) => `<div class="meldung orange">${esc(h)}</div>`).join("")}
		<div class="reihe">${extra || ""}<button class="knopf blau" data-a="zurueck">Fertig</button></div>`;
	ton(true);
	return aktionen;
}
// ------------------------------------------------------------------ Anzahl-Dialog (Kartons/Beutel)
// Zeigt Anzahl mit Ziffernblock und Einheiten-Wahl. fertig(anzahl, einheit) beim OK.
export function anzahlAbfragen(titel, unterzeile, einheiten, start, fertig, zurueck) {
	let einheit = start && start.einheit ? start.einheit : einheiten[0].einheit;
	app.innerHTML = kopf(titel, true) + (unterzeile ? `<div class="panel">${unterzeile}</div>` : "") +
		einheitWahl(einheiten, einheit, (einheiten.find((e) => e.faktor === 1) || {}).einheit) +
		zahlFeld("anzahl", `Wie viele <span id="einheit-text">${esc(ein(einheit))}</span>?`, start && start.anzahl != null ? rund(start.anzahl) : "");
	aktionen((a, d) => {
		if (a === "einheit") { einheit = d.e; einheitSetzen(einheit); document.getElementById("einheit-text").textContent = ein(einheit); return fokus("anzahl"); }
		if (a === "zurueck" && zurueck) return zurueck();
		beiAllgemein(a);
	});
	enter("anzahl", (v) => {
		const n = zahl(v);
		if (n <= 0) return meldung("rot", "Bitte eine Anzahl eingeben.");
		fertig(n, einheit);
	});
	fokus("anzahl");
	setTimeout(() => { const f = document.getElementById("anzahl"); if (f) f.select(); }, 40);
}
