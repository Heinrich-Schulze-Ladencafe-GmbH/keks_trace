// Rauchtest für das Terminal (keks_trace/www/terminal.html) im Browser, ohne Frappe.
//
// Lädt die Seite mit nachgebildeten Server-Antworten (attrappen.mjs), klickt sich je Stationstyp
// automatisch durch alle Knöpfe und Zeilen (bis zu einer Tiefe) und scannt Beispielcodes. Jeder
// Bildschirm wird festgehalten: Inhalt, Statuszeile und die API-Aufrufe dahin.
//
//   node tests/terminal/rauchtest.mjs                 prüfen: keine JavaScript-Fehler
//   node tests/terminal/rauchtest.mjs --speichern d   zusätzlich alle Bildschirme nach d/ schreiben
//   node tests/terminal/rauchtest.mjs --vergleich d   Bildschirme mit d/ vergleichen (z. B. vor einem Umbau)
//   --station Lager                                   nur eine Station
//   KT_TIEFE=3 KT_MAX=250                             Klicktiefe und Bildschirme je Station
//
// Braucht Node 18+ und Playwright mit Chromium (npm i -D playwright && npx playwright install chromium).

import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { antwort, SCANCODES, STATIONEN } from "./attrappen.mjs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const HIER = path.dirname(fileURLToPath(import.meta.url));
const APP = path.resolve(HIER, "../../keks_trace");
const BASIS = "http://kt.test";
const TIEFE = Number(process.env.KT_TIEFE || 3);
const MAX_JE_STATION = Number(process.env.KT_MAX || 250);
const ZEIT = new Date("2026-11-05T09:30:00+01:00");

const args = process.argv.slice(2);
const wert = (n) => (args.includes(n) ? args[args.indexOf(n) + 1] : null);
const speichern = wert("--speichern");
const vergleich = wert("--vergleich");
const nur = wert("--station");

// Seite wie Frappe sie ausliefert, nur ohne base.html: Stil, Inhalt und Skript aus den Blöcken
function seite() {
	const t = fs.readFileSync(path.join(APP, "www/terminal.html"), "utf8");
	const block = (n) => {
		const m = t.match(new RegExp(`{% block ${n} %}([\\s\\S]*?){% endblock %}`));
		return m ? m[1] : "";
	};
	// Import-Map wie www/terminal.py, nur mit fester Version
	const url = "/assets/keks_trace/js/terminal/";
	const ordner = path.join(APP, "public/js/terminal");
	const module = fs.existsSync(ordner) ? fs.readdirSync(ordner).filter((f) => f.endsWith(".js")).sort() : [];
	const importmap = JSON.stringify({ imports: Object.fromEntries(module.map((f) => [url + f, `${url}${f}?v=test`])) });
	const jinja = (s) =>
		s.replace(/{% raw %}|{% endraw %}/g, "")
			.replace(/{{\s*kt_csrf\s*}}/g, "test-csrf")
			.replace(/{{\s*kt_version\s*}}/g, "test")
			.replace(/{{\s*kt_importmap\s*\|\s*safe\s*}}/g, importmap);
	return `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Terminal</title>${jinja(block("style"))}</head>
		<body>${jinja(block("content"))}${jinja(block("script"))}</body></html>`;
}

const TYPEN = { ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };

// Was angeklickt werden kann. Station wechseln und Zurück führen nur an bekannte Stellen.
const KLICKBAR = `#kt [data-a]:not([data-a="station-wechseln"]):not([data-a="zurueck"]):not([data-a="zurueck-ansatz"]),
	#kt [data-pr], #kt [data-g], #kt .einheiten button:not([data-g])`;

async function oeffnen(browser, station, schritte) {
	const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
	const page = await ctx.newPage();
	const fehler = [];
	const aufrufe = [];
	page.on("pageerror", (e) => fehler.push("pageerror: " + e.message));
	page.on("console", (m) => {
		if (m.type() === "error" && !/Failed to load resource/.test(m.text())) fehler.push("console: " + m.text());
	});
	await page.clock.setFixedTime(ZEIT);
	await page.addInitScript((s) => {
		try {
			localStorage.setItem("kt_station", s);
		} catch (e) {
			/* egal */
		}
		window.open = () => null;
		window.print = () => {};
		navigator.vibrate = () => true;
		window.AudioContext = undefined;
		window.webkitAudioContext = undefined;
		window.crypto.randomUUID = () => "test-id";
	}, station);
	let offen = 0;
	await page.route(BASIS + "/**", async (route) => {
		const url = new URL(route.request().url());
		if (url.pathname === "/terminal") return route.fulfill({ contentType: "text/html", body: seite() });
		if (url.pathname.startsWith("/assets/keks_trace/")) {
			// Ohne Version käme nach einem Update die alte Datei aus dem Browser-Cache (Import-Map prüfen)
			if (url.pathname.includes("/js/terminal/") && !url.searchParams.get("v")) {
				fehler.push("ohne Version geladen: " + url.pathname);
			}
			const datei = path.join(APP, "public", url.pathname.slice("/assets/keks_trace/".length));
			if (!fs.existsSync(datei)) return route.fulfill({ status: 404, body: "" });
			return route.fulfill({
				contentType: TYPEN[path.extname(datei)] || "application/octet-stream",
				body: fs.readFileSync(datei),
			});
		}
		const m = url.pathname.match(/^\/api\/method\/keks_trace\.terminal\.(\w+)$/);
		if (!m) return route.fulfill({ status: 404, body: "" });
		offen++;
		let daten = {};
		try {
			daten = JSON.parse(route.request().postData() || "{}");
		} catch (e) {
			/* leer */
		}
		aufrufe.push(m[1] + " " + JSON.stringify(daten));
		const r = antwort(m[1], daten, station);
		offen--;
		if (r && r.__fehler) {
			return route.fulfill({
				status: 417,
				contentType: "application/json",
				body: JSON.stringify({
					exc_type: "TerminalFehler",
					_server_messages: JSON.stringify([JSON.stringify({ message: r.__fehler })]),
				}),
			});
		}
		return route.fulfill({ contentType: "application/json", body: JSON.stringify({ message: r }) });
	});
	await page.goto(BASIS + "/terminal");
	await ruhe(page, () => offen);
	for (const s of schritte) {
		if (s.klick != null) {
			const el = (await page.$$(KLICKBAR))[s.klick];
			if (!el) {
				fehler.push("Schritt nicht wiederholbar: " + JSON.stringify(s));
				break;
			}
			await el.evaluate((e) => e.click());
		} else if (s.scan != null) {
			await page.evaluate((code) => {
				const f = document.getElementById("scan");
				f.value = code;
				f.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
			}, s.scan);
		}
		await ruhe(page, () => offen);
	}
	const bild = await page.evaluate(() => ({
		inhalt: document.getElementById("kt").innerHTML.replace(/\s+/g, " "),
		status: document.getElementById("status-text").textContent,
		kopf: document.getElementById("status-info").innerHTML.replace(/\s+/g, " "),
	}));
	const klickbar = (await page.$$(KLICKBAR)).length;
	const scanfeld = !!(await page.$("#scan"));
	await ctx.close();
	return { bild, aufrufe, fehler, klickbar, scanfeld };
}

// Warten, bis keine Anfrage mehr läuft und das DOM zwei Takte lang ruhig ist
async function ruhe(page, offen) {
	let vorher = "";
	for (let i = 0; i < 40; i++) {
		await page.waitForTimeout(15);
		const jetzt = await page.evaluate(() => document.body.innerHTML);
		if (offen() === 0 && jetzt === vorher) return;
		vorher = jetzt;
	}
}

function schluessel(station, schritte) {
	const weg = schritte.map((s) => (s.klick != null ? "k" + s.klick : "s-" + s.scan)).join("_");
	return (station + "__" + (weg || "start")).replace(/[^\w.-]+/g, "-");
}

async function main() {
	const browser = await chromium.launch();
	const alleFehler = [];
	const unterschiede = [];
	let anzahl = 0;
	if (speichern) fs.mkdirSync(speichern, { recursive: true });
	for (const station of Object.keys(STATIONEN)) {
		if (nur && station !== nur) continue;
		const gesehen = new Set();
		const warteschlange = [[]];
		let n = 0;
		while (warteschlange.length && n < MAX_JE_STATION) {
			const schritte = warteschlange.shift();
			const r = await oeffnen(browser, station, schritte);
			n++;
			const key = schluessel(station, schritte);
			const text = JSON.stringify({ bild: r.bild, aufrufe: r.aufrufe }, null, 1);
			for (const f of r.fehler) alleFehler.push(`${key}: ${f}`);
			if (speichern) fs.writeFileSync(path.join(speichern, key + ".json"), text);
			if (vergleich) {
				const datei = path.join(vergleich, key + ".json");
				if (!fs.existsSync(datei)) unterschiede.push(key + ": fehlt im Vergleich");
				else if (fs.readFileSync(datei, "utf8") !== text) unterschiede.push(key + ": anders");
			}
			const id = r.bild.inhalt + "|" + r.bild.status;
			if (gesehen.has(id) || schritte.length >= TIEFE) continue;
			gesehen.add(id);
			for (let i = 0; i < r.klickbar; i++) warteschlange.push([...schritte, { klick: i }]);
			if (r.scanfeld) for (const c of SCANCODES) warteschlange.push([...schritte, { scan: c }]);
		}
		anzahl += n;
		const rest = warteschlange.length ? ` (Grenze erreicht, ${warteschlange.length} offen)` : "";
		console.log(`${station}: ${n} Bildschirme${rest}`);
	}
	await browser.close();
	console.log(`${anzahl} Bildschirme geprüft.`);
	if (alleFehler.length) console.log("\nJavaScript-Fehler:\n" + [...new Set(alleFehler)].join("\n"));
	if (vergleich) {
		console.log(unterschiede.length ? "\nUnterschiede:\n" + unterschiede.join("\n") : "Keine Unterschiede zum Vergleich.");
	}
	process.exit(alleFehler.length || unterschiede.length ? 1 : 0);
}

main().catch((e) => {
	console.error(e);
	process.exit(2);
});
