// Terminal: Hilfen, Server-Aufrufe (api), Statusleiste mit Kopfdaten, Meldungen. Importiert nichts.

const API = "/api/method/keks_trace.terminal.";
export const app = document.getElementById("kt");
export const zustand = { station: null, typ: null };
// ------------------------------------------------------------------ Hilfen
export function esc(t) {
	return String(t == null ? "" : t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
export function zahl(t) {
	const n = parseFloat(String(t || "").replace(",", "."));
	return isNaN(n) ? 0 : n;
}
export function rund(n, s) { const f = Math.pow(10, s == null ? 3 : s); return Math.round(n * f) / f; }
export function kg(n) { return rund(n).toLocaleString("de-DE") + " kg"; }
export function stk(n, e) { return rund(n).toLocaleString("de-DE") + " " + (e || ""); }
export function ein(e) { return !e || e === "Kg" ? "kg" : e === "Nos" ? "Stk" : e; }
export function mg(n, e) { return !e || e === "Kg" ? kg(n) : stk(n, ein(e)); }
// Menge (Lagereinheit) in gemischten Einheiten: „3 Paletten + 5 Karton“ (wie palette.zerlegen)
export function zerlegen(einheiten, menge) {
	const stufen = (einheiten || []).filter((e) => e.einheit !== "Lage");
	if (!stufen.length) return kg(menge);
	const mz = { Palette: "Paletten", Lage: "Lagen" };
	const n = (x, e) => rund(x).toLocaleString("de-DE") + " " + (rund(x) !== 1 && mz[e] ? mz[e] : e);
	if (menge <= 1e-6) return "0 " + (stufen.find((e) => e.einheit !== "Palette") || stufen[0]).einheit;
	const teile = [];
	for (let i = 0; i < stufen.length; i++) {
		const e = stufen[i];
		const letzte = i === stufen.length - 1 || (stufen[i + 1].faktor === 1 && e.faktor !== 1);
		if (letzte) { const x = Math.round((menge / e.faktor) * 100) / 100; if (x >= 0.05) teile.push(n(x, e.einheit)); break; }
		const x = Math.floor(menge / e.faktor + 1e-6);
		if (x) { teile.push(n(x, e.einheit)); menge = rund(menge - x * e.faktor, 6); }
		if (menge <= 1e-6) break;
	}
	return teile.join(" + ") || "0 " + (stufen.find((e) => e.einheit !== "Palette") || stufen[0]).einheit;
}
function textAus(html) {
	const d = document.createElement("div");
	d.innerHTML = html;
	return d.textContent || d.innerText || "";
}
let audio;
export function ton(ok) {
	try {
		audio = audio || new (window.AudioContext || window.webkitAudioContext)();
		const o = audio.createOscillator(), g = audio.createGain();
		o.frequency.value = ok ? 880 : 220;
		o.connect(g); g.connect(audio.destination);
		g.gain.value = 0.15;
		o.start(); o.stop(audio.currentTime + (ok ? 0.12 : 0.5));
	} catch (e) { /* kein Ton */ }
	if (navigator.vibrate) navigator.vibrate(ok ? 60 : [200, 80, 200]);
}
export function speichern(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* privat */ } }
export function laden(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
const BUCHUNGEN = /^(herstellen|linie_|palette|pruefung_erfassen|umlagern|lieferung|paket_lieferung|anbrechen|wareneingang|rework_erfassen|rework_linie$|silo_leer|behaelter_)/;
// Anfrage-ID nur für Methoden, die der Server mit @einmalig schützt (Paket keks_trace/terminal); Test test_anfrage_liste
const MIT_ANFRAGE_ID = new Set(["anbrechen", "behaelter_reinigung", "etikett_drucken", "etikett_vormerken", "herstellen", "karton_abnehmen", "karton_auf_palette", "lieferung", "linie_beenden", "linie_lose", "linie_palette", "linie_rueckgabe", "linie_zufuehren", "paket_karton", "paket_lieferung", "palette_beladen", "palette_neu", "palette_umpacken", "palette_versandbereit", "pruefung_erfassen", "rework_erfassen", "rework_linie", "silo_leer", "umlagern", "wareneingang"]);
export async function api(methode, args) {
	let r;
	try {
		r = await apiRoh(methode, args);
	} catch (e) {
		if (e.name !== "TypeError") throw e; // fachlicher Fehler vom Server
		// Netzwerk weg (WLAN, Server): sichtbar machen
		kopfInfo.online = false;
		kopfZeigen();
		throw new Error("Keine Verbindung zum Server. Bitte auf dem Papierformular notieren und später nachbuchen.");
	}
	if (!kopfInfo.online) { kopfInfo.online = true; kopfZeigen(); }
	if (methode !== "kopfdaten" && BUCHUNGEN.test(methode)) setTimeout(kopfLaden, 400);
	return r;
}
// Doppelbuchung verhindern: eine Buchung behält ihre Anfrage-ID, bis sie geklappt hat. Geht die Antwort
// unterwegs verloren und es wird nochmal getippt, liefert der Server das erste Ergebnis (anfrage.py).
let anfrageId = null;
function neueId() { return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(36).slice(2); }
async function apiRoh(methode, args) {
	const buchung = MIT_ANFRAGE_ID.has(methode);
	if (buchung && !anfrageId) anfrageId = neueId();
	const r = await fetch(API + methode, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Accept: "application/json",
			"X-Frappe-CSRF-Token": app.dataset.csrf || (window.frappe && frappe.csrf_token) || "",
			...(buchung ? { "X-KT-Anfrage": anfrageId } : {}),
		},
		body: JSON.stringify(args || {}),
	});
	if (buchung && r.ok) anfrageId = null;
	let daten = {};
	try { daten = await r.json(); } catch (e) { /* leer */ }
	if (!r.ok || daten.exc_type || daten.exception) {
		let text = "";
		try {
			text = JSON.parse(daten._server_messages || "[]").map((m) => textAus(JSON.parse(m).message || m)).join(" ");
		} catch (e) { /* ignorieren */ }
		if (!text && daten.exception) text = String(daten.exception).split(":").slice(1).join(":").trim();
		if (daten.exc_type === "CSRFTokenError") {
			if (!laden("kt_neu")) { speichern("kt_neu", "1"); setTimeout(() => location.reload(), 1500); text = "Sitzung abgelaufen. Seite wird neu geladen …"; }
			else text = "Sitzung ungültig. Bitte neu anmelden.";
		}
		if (r.status === 403) text = text || "Nicht angemeldet oder keine Berechtigung.";
		throw new Error(text || "Fehler beim Buchen (" + r.status + ").");
	}
	speichern("kt_neu", "");
	return daten.message;
}
let meldungTimer;
let statusTimer;
export function status(art, text) {
	const s = document.getElementById("status");
	s.className = art || "";
	document.getElementById("status-text").textContent = text;
	clearTimeout(statusTimer);
	// Erfolg und Hinweise verschwinden von selbst; Fehler bleiben bis zum nächsten Bildschirm
	if (art && art !== "rot") statusTimer = setTimeout(() => status("", "Bereit."), 6000);
}
// Kopfdaten in der Statusleiste: Serverzeit (Uhr läuft lokal weiter), KW, Los, Verbindung, Auftrag, Prüfung
const kopfInfo = { versatz: 0, daten: null, online: true };
export async function kopfLaden() {
	if (!zustand.station) return;
	try {
		const vorher = Date.now();
		const d = await api("kopfdaten", { station: zustand.station });
		kopfInfo.versatz = new Date(d.zeit).getTime() - (vorher + Date.now()) / 2;
		kopfInfo.daten = d;
		kopfInfo.online = true;
	} catch (e) {
		kopfInfo.online = false;
	}
	kopfZeigen();
}
function kopfZeigen() {
	const el = document.getElementById("status-info");
	const d = kopfInfo.daten;
	if (!el || !d) return;
	const jetzt = new Date(Date.now() + kopfInfo.versatz);
	const uhr = jetzt.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
	const zweite = [d.auftrag, d.pruefung ? `<span class="pr ${esc(d.pruefung.art)}">${esc(d.pruefung.text)}</span>` : ""].filter(Boolean);
	el.innerHTML = `<div><span class="punkt ${kopfInfo.online ? "" : "weg"}"></span>${kopfInfo.online ? "" : '<span class="offline">keine Verbindung – Papierformular! </span>'}
		${esc(d.datum_text)} · <span class="uhr">${esc(uhr)}</span> · KW ${esc(d.kw)}${d.los ? " · Los " + esc(d.los) : ""}</div>
		<div class="zweit">${esc(d.station)} · ${esc(d.benutzer)}${zweite.length ? " · " + zweite.map((x) => (x.startsWith("<") ? x : esc(x))).join(" · ") : ""}</div>`;
}
setInterval(kopfZeigen, 1000 * 15);
setInterval(kopfLaden, 1000 * 60);
window.addEventListener("online", kopfLaden);
window.addEventListener("offline", () => { kopfInfo.online = false; kopfZeigen(); });
export function meldung(art, text, klein) {
	status(art, text + (klein ? " " + klein : ""));
	const el = document.getElementById("meldung");
	if (!el) return;
	el.innerHTML = `<div class="meldung ${art}">${esc(text)}${klein ? `<small>${esc(klein)}</small>` : ""}</div>`;
	ton(art !== "rot");
	clearTimeout(meldungTimer);
	if (art !== "rot") meldungTimer = setTimeout(() => { el.innerHTML = ""; }, 6000);
}
export function fokus(id) {
	setTimeout(() => { const f = document.getElementById(id || "scan"); if (f) f.focus(); }, 30);
}
document.addEventListener("click", (e) => {
	if (e.target.closest("input, select, textarea, button, .dialog, #tasten")) return;
	// Nur wenn gerade kein Feld aktiv ist: sonst würde ein Tipp, der wegen der aufgehenden Tastatur
	// danebengeht, den Cursor aus dem gerade angetippten Feld holen.
	const aktiv = document.activeElement;
	if (aktiv && aktiv !== document.body && aktiv.matches("input, select")) return;
	const f = document.getElementById("scan");
	if (f) f.focus();
});
