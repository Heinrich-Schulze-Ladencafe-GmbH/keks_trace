// Terminal: Eingabefelder, Datumsfelder, Bildschirmtastatur und Scanner-Erkennung.

import { app, ein, esc, meldung, rund } from "./basis.js";

// ------------------------------------------------------------------ Bildschirmtastatur und Scanner
// Eine Tastatur unten am Bildschirm schreibt in das angetippte Feld: Ziffern bei Mengen/Datum,
// Buchstaben bei Text. Felder haben inputmode="none" (keine kleine Systemtastatur).
// Scanner tippen sehr schnell und schließen mit Enter: ein Scan landet immer im Scanfeld
// (data-scan), auch wenn gerade ein Mengenfeld aktiv ist; dessen Inhalt bleibt erhalten.
function feld(id, label, wert, art, scan) {
	return `<label for="${id}">${label}</label><input id="${id}" class="feld" data-art="${art}" ${scan ? "data-scan" : ""}
		inputmode="none" autocomplete="off" autocapitalize="off" spellcheck="false" value="${esc(wert == null ? "" : wert)}">`;
}
export function zahlFeld(id, label, wert) {
	return feld(id, label, wert == null || wert === "" ? "" : String(wert).replace(".", ","), "zahl");
}
export function textFeld(id, label, wert) { return feld(id, label, wert, "text", true); }
// Datumsfeld mit Zwangsformat TT.MM.JJ: nur Ziffern, die Punkte setzt das Terminal; darunter steht das erkannte
// Datum mit Wochentag oder der Fehler. opt: pflicht (leer nicht erlaubt), abHeute (nicht in der Vergangenheit),
// wert (ISO-Datum zum Vorbelegen). Beim Buchen den Wert mit datumWert(id, name) holen – der prüft noch einmal.
const DATUM_MAX_JAHRE = 10;
export function datumFeld(id, label, opt) {
	const o = opt || {};
	return `<label for="${id}">${label}</label><input id="${id}" class="feld" data-art="datum" data-pflicht="${o.pflicht ? 1 : ""}" data-ab-heute="${o.abHeute ? 1 : ""}"
		inputmode="none" autocomplete="off" maxlength="10" placeholder="TT.MM.JJ" value="${esc(o.wert ? datumMaske(o.wert.split("-").reverse().join("").replace(/^(\d{4})\d{2}(\d{2})$/, "$1$2")) : "")}">
		<small class="feld-hinweis" id="${id}-hinweis">Tag, Monat, Jahr als Ziffern, z. B. 300628 für den 30.06.2028</small>`;
}
function datumMaske(text) {
	const z = String(text || "").replace(/\D/g, "").slice(0, 8);
	return z.slice(0, 2) + (z.length > 2 ? "." + z.slice(2, 4) : "") + (z.length > 4 ? "." + z.slice(4) : "");
}
const WOCHENTAGE = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
// {iso, fehler, text}: fehler = warum nicht gültig; leer und nicht Pflicht = {iso: null}
function datumPruefen(f) {
	const z = f.value.replace(/\D/g, "");
	if (!z) return f.dataset.pflicht ? { fehler: "Bitte das Datum eingeben." } : { iso: null };
	if (z.length !== 6 && z.length !== 8) return { fehler: "Unvollständig: Tag, Monat und Jahr eingeben (TTMMJJ)." };
	const iso = datumIso(z);
	if (!iso) return { fehler: datumMaske(z) + " gibt es nicht." };
	const dt = new Date(iso + "T12:00:00");
	const heute = new Date(); heute.setHours(0, 0, 0, 0);
	const grenze = new Date(heute); grenze.setFullYear(grenze.getFullYear() + DATUM_MAX_JAHRE);
	if (f.dataset.abHeute && dt < heute) return { fehler: datumMaske(z) + " liegt in der Vergangenheit." };
	if (dt > grenze) return { fehler: datumMaske(z) + " liegt über " + DATUM_MAX_JAHRE + " Jahre in der Zukunft. Jahr prüfen." };
	return { iso, text: WOCHENTAGE[dt.getDay()] + ", " + datumDe(iso) };
}
export function datumAnzeigen(f) {
	const h = document.getElementById(f.id + "-hinweis");
	const z = f.value.replace(/\D/g, "");
	const r = datumPruefen(f);
	const fertig = z.length === 6 || z.length === 8;
	f.classList.toggle("falsch", fertig && !!r.fehler);
	if (!h) return r;
	h.className = "feld-hinweis" + (r.text ? " ok" : fertig && r.fehler ? " falsch" : "");
	h.textContent = r.text ? "= " + r.text : fertig && r.fehler ? r.fehler : "Tag, Monat, Jahr als Ziffern, z. B. 300628 für den 30.06.2028";
	return r;
}
// Beim Buchen: ISO-Datum oder Fehler (wird als Meldung gezeigt, Feld bekommt den Fokus)
export function datumWert(id, name) {
	const f = document.getElementById(id);
	if (!f) return null;
	const r = datumAnzeigen(f);
	if (r.fehler) { f.classList.add("falsch"); f.focus(); throw new Error((name ? name + ": " : "") + r.fehler); }
	return r.iso;
}
// Jede Eingabe (Bildschirmtastatur, Tastatur, Scanner, Vorbelegung) wird sofort auf TT.MM.JJ gebracht
document.addEventListener("input", (e) => {
	const f = e.target;
	if (!f || !f.dataset || f.dataset.art !== "datum") return;
	const neu = datumMaske(f.value);
	if (neu !== f.value) { f.value = neu; f.setSelectionRange(neu.length, neu.length); }
	datumAnzeigen(f);
}, true);
function datumIso(t) {
	const z = String(t || "").replace(/\D/g, "");
	let d, m, y;
	if (/^\d{1,2}\.\d{1,2}\.\d{2,4}$/.test(String(t).trim())) [d, m, y] = String(t).trim().split(".");
	else if (z.length === 6) [d, m, y] = [z.slice(0, 2), z.slice(2, 4), z.slice(4)];
	else if (z.length === 8) [d, m, y] = [z.slice(0, 2), z.slice(2, 4), z.slice(4)];
	else return null;
	y = String(y).length === 2 ? "20" + y : String(y);
	const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
	const dt = new Date(iso + "T12:00:00");
	return isNaN(dt) || dt.getDate() !== +d ? null : iso;
}
const tasten = document.createElement("div");
tasten.id = "tasten";
document.body.appendChild(tasten);
let tastenArt = null;
const BELEGUNG = {
	zahl: ["7", "8", "9", "⌫", "4", "5", "6", "C", "1", "2", "3", "OK", "ZU", "0", ","],
	datum: ["7", "8", "9", "⌫", "4", "5", "6", "C", "1", "2", "3", "OK", "ZU", "0", "."],
	text: ["1234567890", "QWERTZUIOP", "ASDFGHJKL-", "YXCVBNM./"],
};
// Buchstaben nur nach Antippen (Scanfelder bekommen den Cursor automatisch, da stört die Tastatur);
// Ziffern erscheinen auch automatisch, wenn eine Menge gefragt ist.
let angetippt = null;
// Ausblenden erst, wenn der Finger los ist und der Klick durch: sonst wird der Inhalt breiter und der
// angetippte Knopf (z. B. „Buchen“) rutscht unter dem Finger weg, der Klick geht ins Leere.
let gedrueckt = false, losgelassen = 0, tastenTimer = null;
document.addEventListener("pointerdown", (e) => { angetippt = e.target.closest("input[data-art]"); gedrueckt = true; }, true);
document.addEventListener("pointerup", () => { gedrueckt = false; losgelassen = performance.now(); }, true);
document.addEventListener("pointercancel", () => { gedrueckt = false; losgelassen = performance.now(); }, true);
// Breiter Bildschirm (Surface, Terminal): Ziffernblock FEST rechts wie bei FOBIS – kein Ein- und Ausblenden,
// der Inhalt springt nicht. Ohne aktives Feld gehen die Ziffern ins Scanfeld (Suchen über Nummern).
// Auch Scan- und Textfelder bekommen erst die Ziffern; „ABC“ schaltet auf Buchstaben, „123“ zurück.
// Schmaler Bildschirm (Handy): wie bisher, Tastatur nur bei Bedarf.
const fest = () => window.innerWidth >= 1000;
let abc = false;
function aktivesFeld() {
	const f = document.activeElement;
	return f && f.dataset && f.dataset.art && app.contains(f) ? f : null;
}
function zielFeld() {
	const sichtbar = (x) => x.offsetParent && !x.disabled && !x.readOnly;
	return [...app.querySelectorAll("input[data-scan]")].find(sichtbar) || [...app.querySelectorAll("input[data-art]")].find(sichtbar) || null;
}
function belegen(art) {
	if (art === tastenArt) return;
	tastenArt = art;
	if (art === "text") {
		tasten.className = "text";
		tasten.innerHTML = BELEGUNG.text.map((r) => r.split("").map((z) => `<button type="button" data-z="${z}">${z}</button>`).join("")).join("") +
			`<button type="button" data-z="⌫" class="breit weg">⌫</button><button type="button" data-z="C" class="breit weg">C</button>` +
			(fest() ? `<button type="button" data-z="123" class="breit weg">123</button>` : `<button type="button" data-z="ZU" class="breit">▾</button>`) +
			`<button type="button" data-z="OK" class="ok" style="grid-column: span 4">OK</button>`;
	} else {
		// art: zahl, datum oder zahltext (Ziffern für ein Scan-/Textfeld)
		const belegung = BELEGUNG[art === "zahltext" ? "zahl" : art].map((z) => (z === "," && art === "zahltext" ? "-" : z));
		tasten.className = "zahl";
		tasten.innerHTML = belegung.map((z) => {
			if (z === "ZU" && fest()) return `<button type="button" data-z="ABC" class="weg">ABC</button>`;
			return `<button type="button" data-z="${z}" class="${z === "OK" ? "ok" : z === "⌫" || z === "C" ? "weg" : ""}">${z === "ZU" ? "▾" : z}</button>`;
		}).join("");
	}
}
function tastenZeigen() {
	const f = document.activeElement;
	let art = f && f.dataset ? f.dataset.art : null;
	clearTimeout(tastenTimer);
	if (fest()) {
		// immer sichtbar; Buchstaben nur auf Wunsch
		const feldArt = aktivesFeld() ? art : null;
		if (feldArt !== "text") abc = false;
		// Scanfelder (Nummern) starten mit Ziffern, reine Freitextfelder (Grund, Bemerkung) mit Buchstaben
		const freitext = feldArt === "text" && !f.hasAttribute("data-scan") && !f.hasAttribute("data-nummern");
		belegen(feldArt === "text" ? (abc || freitext ? "text" : "zahltext") : feldArt || "zahltext");
		tasten.style.display = "grid";
		tasten.classList.toggle("leer", !aktivesFeld() && !zielFeld());
		if (tastenArt === "text") { app.classList.remove("blockrechts"); app.style.paddingBottom = tasten.offsetHeight + 40 + "px"; }
		else { app.classList.add("blockrechts"); app.style.paddingBottom = ""; }
		if (aktivesFeld()) setTimeout(() => f.scrollIntoView({ block: "nearest", behavior: "smooth" }), 20);
		return;
	}
	if (art === "text" && angetippt !== f) art = null;
	if (!art && tasten.style.display === "grid" && (gedrueckt || performance.now() - losgelassen < 400)) {
		tastenTimer = setTimeout(tastenZeigen, 150);
		return;
	}
	if (!art) { tasten.style.display = "none"; app.style.paddingBottom = ""; app.classList.remove("blockrechts"); tastenArt = null; return; }
	belegen(art);
	tasten.style.display = "grid";
	app.classList.remove("blockrechts"); app.style.paddingBottom = tasten.offsetHeight + 40 + "px";
	setTimeout(() => f.scrollIntoView({ block: "nearest", behavior: "smooth" }), 20);
}
document.addEventListener("focusin", tastenZeigen);
document.addEventListener("focusout", () => setTimeout(tastenZeigen, 60));
window.addEventListener("resize", () => { tastenArt = null; tastenZeigen(); });
// neuer Bildschirm (app.innerHTML): Zustand des festen Blocks neu bestimmen (Scanfeld da oder nicht)
new MutationObserver(() => { if (fest()) tastenZeigen(); }).observe(app, { childList: true });
tasten.addEventListener("pointerdown", (e) => e.preventDefault());
tasten.addEventListener("click", (e) => {
	const b = e.target.closest("[data-z]");
	if (!b) return;
	let f = aktivesFeld();
	if (!f && fest()) { f = zielFeld(); if (f) f.focus(); }
	if (!f) return;
	const z = b.dataset.z;
	if (z === "ABC") { abc = true; tastenArt = null; return tastenZeigen(); }
	if (z === "123") { abc = false; tastenArt = null; belegen("zahltext"); app.classList.add("blockrechts"); app.style.paddingBottom = ""; return; }
	if (z === "OK") { abc = false; return weiter(f); }
	if (z === "ZU") return f.blur();
	const markiert = f.value && f.selectionStart === 0 && f.selectionEnd === f.value.length;
	if (markiert && z !== "⌫" && z !== "C") f.value = ""; // markierter Vorschlag wird überschrieben
	if (z === "⌫") f.value = markiert ? "" : f.value.slice(0, -1);
	else if (z === "C") f.value = "";
	else if ((z === "," || z === ".") && f.dataset.art === "zahl" && f.value.includes(",")) return;
	else f.value += z === "." && f.dataset.art === "zahl" ? "," : z;
	f.setSelectionRange(f.value.length, f.value.length);
	f.dispatchEvent(new Event("input", { bubbles: true }));
});
// OK/Enter: Formular-Logik des Bildschirms auslösen; ändert die nichts am Fokus, ins nächste Feld
function weiter(f) {
	f.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
	setTimeout(() => {
		if (document.activeElement !== f || !document.body.contains(f)) return;
		const felder = [...app.querySelectorAll("input[data-art], select")].filter((x) => x.offsetParent);
		const n = felder[felder.indexOf(f) + 1];
		if (n) n.focus();
		else f.blur(); // letztes Feld: Tastatur weg, Buchen-Knopf frei
	}, 80);
}
// Scanner erkennen: viele Zeichen in kurzem Abstand, dann Enter
const scanPuffer = { text: "", zeit: 0, feld: null, vorher: "" };
document.addEventListener("keydown", (e) => {
	const f = document.activeElement;
	const jetzt = performance.now();
	if (e.key === "Enter") {
		const istScan = scanPuffer.text.length >= 4 && scanPuffer.feld === f && jetzt - scanPuffer.zeit < 80;
		const code = scanPuffer.text;
		scanPuffer.text = "";
		if (!istScan || !f || !f.dataset) return;
		const ziel = f.dataset.scan !== undefined ? null
			: [...app.querySelectorAll("[data-scan]")].find((x) => x.offsetParent && !x.value) || app.querySelector("[data-scan]");
		if (f.dataset.scan !== undefined) return; // Scan im Scanfeld: normal weiter
		e.preventDefault();
		e.stopImmediatePropagation();
		f.value = scanPuffer.vorher; // Mengenfeld behält seinen Inhalt
		if (!ziel) return meldung("rot", "Gescannt: " + code + ". Hier bitte erst die Eingabe abschließen.");
		ziel.value = code;
		ziel.focus();
		ziel.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
		return;
	}
	if (e.key.length !== 1) return;
	if (jetzt - scanPuffer.zeit > 50 || scanPuffer.feld !== f) {
		scanPuffer.text = "";
		scanPuffer.feld = f;
		scanPuffer.vorher = f && "value" in f ? f.value : "";
	}
	scanPuffer.text += e.key;
	scanPuffer.zeit = jetzt;
}, true);
export function einheitWahl(einheiten, aktiv, basis) {
	if (!einheiten || einheiten.length < 2) return "";
	return `<div class="einheiten">${einheiten.map((e) =>
		`<button type="button" data-a="einheit" data-e="${esc(e.einheit)}" class="${e.einheit === aktiv ? "an" : ""}">${esc(ein(e.einheit))}${e.faktor !== 1 ? ` <small>(${esc(String(rund(e.faktor)).replace(".", ","))} ${esc(ein(basis))})</small>` : ""}</button>`).join("")}</div>`;
}
export function einheitSetzen(einheit) {
	app.querySelectorAll('[data-a="einheit"]').forEach((b) => b.classList.toggle("an", b.dataset.e === einheit));
}
export function faktorVon(einheiten, einheit) {
	const e = (einheiten || []).find((x) => x.einheit === einheit);
	return e ? e.faktor : 1;
}
export function datumDe(iso) { const [y, m, d] = String(iso).split("-"); return `${d}.${m}.${y}`; }
