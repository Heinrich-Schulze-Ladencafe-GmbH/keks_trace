// Terminal: Lieferung (Verladung) und Paketversand DHL.

import { api, app, ein, esc, fokus, kg, meldung, rund, stk, zahl, zerlegen, zustand } from "./basis.js";
import { textFeld, zahlFeld } from "./tastatur.js";
import { aktionen, anzahlAbfragen, beiAllgemein, enter, ergebnis, etikettDrucken, kopf, suchListe, zahlText } from "./rahmen.js";
import { hinweisHtml } from "./linie.js";
import { grossZahlen, gruppe, maske, zeileKV } from "./herstellen.js";
import { hatInhalt, kartonListeHtml, positionenHtml, statusMarke } from "./paletten.js";

// ------------------------------------------------------------------ Paketversand DHL (Herzenboden)
export async function dhlStart() {
	app.innerHTML = kopf("Lieferung (DHL)", true) + `<p><b>Offene Aufträge</b> – Zeile antippen</p><div id="dhl">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const liste = (await api("auftraege", { station: zustand.station })).map((z) => ({ ...z, offen: Math.max(rund(z.menge - z.geliefert), 0) })).filter((z) => z.offen > 0);
		suchListe("dhl", [["Auftrag", "auftrag"], ["Kunde", "kundenname"], ["Artikel", "name"], ["Bestellt", (z) => zahlText(z.menge), 1],
			["Geliefert", (z) => zahlText(z.geliefert), 1], ["Offen", (z) => zahlText(z.offen), 1], ["Termin", "termin"]],
			liste, (z) => dhlErfassen(z), "Suchen: Kunde, Auftrag, Artikel …");
	} catch (e) { meldung("rot", e.message); }
}
async function dhlErfassen(z) {
	app.innerHTML = kopf("DHL: " + z.kundenname, true) +
		`<div class="panel"><b>${esc(z.name)}</b> · Auftrag ${esc(z.auftrag)} · offen ${esc(zahlText(z.offen))} Stk<div id="dhl-info" class="fehlt" style="font-size:16px"></div></div>` +
		`<div class="reihe" style="margin-top:0"><div>${zahlFeld("stk", "Stück im Paket bzw. in allen Paketen", z.offen)}</div><div>${zahlFeld("pakete", "Anzahl Pakete", 1)}</div></div>
		<div id="gewichte"></div>` + textFeld("sendung", "Sendungsnummer (optional, vom DHL-Label scannen – geht auch später)") +
		`<div class="reihe"><button class="knopf" data-a="zurueck-dhl">← Aufträge</button><button class="knopf gruen" data-a="buchen">Lieferschein buchen</button></div>
		<div class="reihe"><button class="knopf blau" data-a="kartons">Pakete als Versandkarton mit NVE<small>je Paket eigene NVE und Etikett, Sendungsnummer je Karton</small></button></div>`;
	let erwartet = null;
	const neu = async () => {
		const stk = zahl(document.getElementById("stk").value), n = Math.max(1, Math.min(20, Math.round(zahl(document.getElementById("pakete").value) || 1)));
		try {
			const v = await api("paket_vorschlag", { station: zustand.station, artikel: z.artikel, stueck: stk, pakete: n });
			erwartet = v.erwartet_kg;
			document.getElementById("dhl-info").textContent = `Verpackt im Lager: ${zahlText(v.verfuegbar)} Stk` + (erwartet ? ` · erwartet etwa ${zahlText(erwartet)} kg gesamt` : " · Stückgewicht am Artikel fehlt");
		} catch (e) { /* nur Info */ }
		// von Hand eingetragene Gewichte bleiben, sonst Vorschlag aus dem Stückgewicht
		const alt = [...document.querySelectorAll("#gewichte input")].map((f) => (f.dataset.hand ? f.value : ""));
		document.getElementById("gewichte").innerHTML = Array.from({ length: n }, (_, i) =>
			zahlFeld("gw" + i, `Paket ${i + 1}: Gewicht von der Paketwaage (kg)`, alt[i] || (erwartet ? rund(erwartet / n, 2) : ""))).join("");
		document.querySelectorAll("#gewichte input").forEach((f, i) => { if (alt[i]) f.dataset.hand = "1"; f.addEventListener("input", () => { f.dataset.hand = "1"; }); });
	};
	document.getElementById("stk").addEventListener("change", neu);
	document.getElementById("pakete").addEventListener("change", neu);
	enter("pakete", neu);
	await neu();
	aktionen(async (a) => {
		if (a === "zurueck-dhl") return dhlStart();
		if (a === "kartons") return dhlKartons(z, []);
		if (a !== "buchen") return beiAllgemein(a);
		const gewichte = [...document.querySelectorAll("#gewichte input")].map((f) => zahl(f.value));
		try {
			const e = await api("paket_lieferung", { station: zustand.station, kundenauftrag: z.auftrag, artikel: z.artikel,
				stueck: zahl(document.getElementById("stk").value), gewichte, sendungsnummer: document.getElementById("sendung").value.trim() || null });
			ergebnis("Lieferung " + e.kunde, ["Lieferschein: " + e.lieferschein, "Pakete: " + e.pakete + ", gewogen " + zahlText(e.gewicht_kg) + " kg",
				"Lose: " + e.lose.join(", "), e.adresse ? "Adresse: " + e.adresse.replace(/\n/g, ", ") : "Adresse fehlt im Kundenstamm"], e.hinweise,
				`<button class="knopf" data-a="sendung">Sendungsnummer scannen</button><button class="knopf" data-a="weiter">Nächste Lieferung</button>`)((b) => {
				if (b === "sendung") return sendungScannen(e.lieferschein);
				if (b === "weiter") return dhlStart();
				beiAllgemein(b);
			});
		} catch (err) { meldung("rot", err.message); }
	});
}
// DHL mit NVE: jedes Paket ist ein Versandkarton (eigene NVE, Etikett), danach ein Lieferschein für alle
function dhlKartons(z, liste) {
	const gepackt = liste.reduce((n, k) => n + (k.stueck || 0), 0);
	const rest = Math.max(rund(z.offen - gepackt), 0);
	app.innerHTML = kopf("DHL mit NVE: " + z.kundenname, true) +
		`<div class="panel"><b>${esc(z.name)}</b> · Auftrag ${esc(z.auftrag)} · offen ${esc(zahlText(z.offen))} Stk${gepackt ? ` · gepackt ${esc(zahlText(gepackt))} Stk` : ""}</div>` +
		`<div class="reihe" style="margin-top:0"><div>${zahlFeld("stk", "Stück in diesem Paket", rest || "")}</div><div>${zahlFeld("gw", "Gewicht von der Paketwaage (kg)")}</div></div>
		<div class="reihe"><button class="knopf blau" data-a="packen">Paket packen<small>neuer Versandkarton, Etikett wird gedruckt</small></button></div>` +
		textFeld("scan", "oder einen fertigen Versandkarton scannen") +
		(liste.length ? `<div class="panel">${liste.map((k, i) => `<div class="zeile"><div>Versandkarton …${esc(k.nve.slice(-6))}<br><small class="fehlt">${esc(k.kartons || "")}</small></div>
			<div class="rechts">${k.gewicht_kg ? esc(zahlText(k.gewicht_kg)) + " kg" : ""} <button class="x" data-a="weg" data-i="${i}">✕</button></div></div>`).join("")}</div>` +
			textFeld("sendung", "Sendungsnummer (optional, vom DHL-Label scannen – geht auch später, je Paket)") : "") +
		`<div class="reihe"><button class="knopf" data-a="zurueck-dhl">← Zurück</button>${liste.length ? `<button class="knopf gruen" data-a="buchen">Lieferschein buchen (${liste.length} Pakete)</button>` : ""}</div>`;
	aktionen(async (a, d) => {
		if (a === "zurueck-dhl" || a === "zurueck") return dhlErfassen(z);
		if (a === "weg") { liste.splice(+d.i, 1); return dhlKartons(z, liste); }
		if (a === "packen") {
			try {
				const stueck = zahl(document.getElementById("stk").value);
				const k = await api("paket_karton", { station: zustand.station, kundenauftrag: z.auftrag, artikel: z.artikel, stueck, gewicht: zahl(document.getElementById("gw").value) || null });
				etikettDrucken(k.nve);
				liste.push({ ...k, stueck });
				dhlKartons(z, liste);
				return meldung("gruen", "Paket gepackt: Versandkarton …" + k.nve.slice(-6), "Etikett wird gedruckt.");
			} catch (e) { return meldung("rot", e.message); }
		}
		if (a === "buchen") {
			try {
				const e = await api("paket_lieferung", { station: zustand.station, kundenauftrag: z.auftrag, kartons: liste.map((k) => k.nve),
					sendungsnummer: (document.getElementById("sendung") || {}).value || null });
				ergebnis("Lieferung " + e.kunde, ["Lieferschein: " + e.lieferschein, "Pakete: " + e.pakete + (e.gewicht_kg ? ", gewogen " + zahlText(e.gewicht_kg) + " kg" : ""),
					"Versandkartons: " + e.versandkartons.map((n) => "…" + n.slice(-6)).join(", "), "Lose: " + e.lose.join(", "),
					e.adresse ? "Adresse: " + e.adresse.replace(/\n/g, ", ") : "Adresse fehlt im Kundenstamm"], e.hinweise,
					`<button class="knopf" data-a="sendung">Sendungsnummern scannen</button><button class="knopf" data-a="weiter">Nächste Lieferung</button>`)((b) => {
					if (b === "sendung") return sendungScannen(e.lieferschein);
					if (b === "weiter") return dhlStart();
					beiAllgemein(b);
				});
			} catch (err) { meldung("rot", err.message); }
			return;
		}
		beiAllgemein(a);
	});
	enter("scan", async (v) => {
		if (!v) return;
		try {
			const i = await api("info", { code: v });
			if (i.typ !== "palette" || !i.versandkarton) throw new Error("Bitte einen Versandkarton scannen.");
			if (liste.some((k) => k.nve === i.nve)) throw new Error("Dieser Versandkarton ist schon dabei.");
			liste.push(i);
			dhlKartons(z, liste);
		} catch (e) { meldung("rot", e.message); }
	});
	fokus("stk");
}
function sendungScannen(lieferschein, liste) {
	app.innerHTML = kopf("Sendungsnummer " + lieferschein, true) + textFeld("scan", "DHL-Label scannen (je Paket einmal)") +
		(liste && liste.length ? `<div class="panel">${liste.map((x) => `<div class="zeile"><div>${esc(x)}</div></div>`).join("")}</div>` : "") +
		`<div class="reihe"><button class="knopf gruen" data-a="fertig">Fertig</button></div>`;
	aktionen((a) => (a === "fertig" ? dhlStart() : beiAllgemein(a)));
	enter("scan", async (v) => {
		if (!v) return;
		try { const r = await api("sendungsnummer", { station: zustand.station, lieferschein, nummer: v }); sendungScannen(lieferschein, r.sendungsnummern); meldung("gruen", "Sendungsnummer gespeichert"); }
		catch (e) { meldung("rot", e.message); }
	});
	fokus("scan");
}
// ------------------------------------------------------------------ Lieferung
let lieferung;
export async function lieferungStart() {
	app.innerHTML = kopf("Lieferung", true) + `<p>An welchen Kunden? Zeile antippen</p><div id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const liste = await api("kunden");
		suchListe("liste", [["Kunde", "customer_name"], ["Nr.", "name"]], liste, (k) => {
			lieferung = { kunde: k.name, titel: k.customer_name, zeilen: [], auftrag: null, positionen: [] };
			lieferAuftragWaehlen();
		}, "Suchen: Kundenname …");
	} catch (e) { meldung("rot", e.message); }
}
async function lieferAuftragWaehlen() {
	let liste = [];
	try { liste = await api("auftraege", { station: zustand.station, kunde: lieferung.kunde }); } catch (e) { /* ohne */ }
	const auftraege = {};
	liste.forEach((z) => { (auftraege[z.auftrag] = auftraege[z.auftrag] || []).push(z); });
	const namen = Object.keys(auftraege);
	if (!namen.length) return lieferungZeigen();
	app.innerHTML = kopf("Lieferung an " + lieferung.titel, true) + `<p>Zu welchem Kundenauftrag?</p><div class="raster">
		${namen.map((n) => `<button class="knopf blau" data-a="auftrag" data-n="${esc(n)}">${esc(n)}<small>${auftraege[n].map((z) =>
			esc(z.name) + ": " + esc(z.offen_liefern_text) + " offen").join("<br>")}${auftraege[n][0].termin ? "<br>Termin " + esc(auftraege[n][0].termin) : ""}</small></button>`).join("")}
		<button class="knopf" data-a="ohne">Ohne Auftrag</button></div>`;
	aktionen((a, d) => {
		if (a === "auftrag") { lieferung.auftrag = d.n; lieferung.positionen = auftraege[d.n]; return lieferungZeigen(); }
		if (a === "ohne") return lieferungZeigen();
		if (a === "zurueck") return lieferungStart();
		beiAllgemein(a);
	});
}
function lieferungZeilePlus(anfrage, positionen) {
	lieferung.zeilen.push({ anfrage, positionen });
	lieferungZeigen();
	const n = positionen.reduce((s, x) => s + x.anzahl, 0);
	meldung("gruen", "OK: " + (anfrage.ganz ? "ganze Palette " + anfrage.palette.slice(-6) : positionen[0].name) + " · " + stk(n, positionen[0].einheit));
}
// Verladung nach Kundenauftrag wie bei FOBIS: links alle Positionen mit Bestellt / Erledigt / ToDo und die
// gewählte groß samt Registrierungen, rechts Herkunft (scannen), Ziel (Kunde, Auftrag) und Buchen
function verladungMaske(gescanntJe, liste, hinweise) {
	const pos = lieferung.positionen.map((z) => {
		const f = z.faktor || 1;
		const jetzt = (gescanntJe[z.artikel] || 0) / f;
		const erledigt = rund((z.geliefert || 0) + jetzt);
		const todo = Math.max(rund(z.menge - erledigt), 0);
		return { z, jetzt, erledigt, todo, status: todo <= 1e-6 ? "Fertig" : erledigt > 0 ? "Aktiv" : "Neu" };
	});
	if (lieferung.sel == null || !pos[lieferung.sel]) lieferung.sel = Math.max(0, pos.findIndex((p) => p.status !== "Fertig"));
	const mitHinweis = pos.some((p) => p.z.hinweis);
	const zeilen = pos.map((p, i) => `<tr data-a="sel" data-i="${i}" class="${i === lieferung.sel ? "gewaehlt" : p.status === "Fertig" ? "fertig" : ""}">
		<td>${i + 1}</td><td>${esc(p.z.name)}<small style="display:block;color:var(--muted)">${esc(p.z.artikel)} · in ${esc(ein(p.z.einheit))}</small></td>
		<td class="z">${esc(zerlegen(p.z.einheiten, p.z.menge * (p.z.faktor || 1)))}</td>
		<td class="z">${p.erledigt ? esc(zerlegen(p.z.einheiten, p.erledigt * (p.z.faktor || 1))) : "–"}</td>
		<td class="z todo">${p.todo ? esc(zerlegen(p.z.einheiten, p.todo * (p.z.faktor || 1))) : "–"}</td>
		<td>${p.status === "Fertig" ? "✔ " : ""}${p.status}</td>${mitHinweis ? `<td>${esc(p.z.hinweis || "")}</td>` : ""}</tr>`).join("");
	const g = pos[lieferung.sel];
	const reg = g ? lieferung.zeilen.map((zl, i) => ({ zl, i })).filter((x) => x.zl.positionen.some((y) => y.artikel === g.z.artikel)) : [];
	const detail = g ? `<div class="m-detail"><div class="titel"><div><b>${esc(g.z.artikel)}</b> ${esc(g.z.name)}<small>${esc(ein(g.z.einheit))}${g.z.termin ? " · Termin " + esc(g.z.termin) : ""}</small></div>
			<div class="fehlt" style="font-size:16px;text-align:right">jetzt gescannt<br><b>${esc(zerlegen(g.z.einheiten, gescanntJe[g.z.artikel] || 0))}</b></div></div>
			${g.z.hinweis ? hinweisHtml([{ von: "Kundenauftrag", text: g.z.hinweis }]) : ""}
			${grossZahlen(g.z.menge, g.erledigt, g.todo, g.z.einheit, [g.z.menge, g.erledigt, g.todo].map((n) => zerlegen(g.z.einheiten, n * (g.z.faktor || 1))))}
			${reg.length ? `<div style="margin-top:8px">${reg.map((x) => x.zl.positionen.filter((y) => y.artikel === g.z.artikel).map((y, j) => `<div class="zeile"><div>Los ${esc(y.charge)}${y.palette ? " · " + (y.versandkarton ? "Versandkarton" : "Palette") + " …" + esc(y.palette.slice(-6)) : " · lose"}</div>
				<div class="rechts">${esc(stk(y.anzahl, y.einheit))}${j === 0 ? ` <button class="x" data-a="weg" data-i="${x.i}">✕</button>` : ""}</div></div>`).join("")).join("")}</div>` : ""}</div>` : "";
	const offen = pos.filter((p) => p.status !== "Fertig").length;
	const links = `<div class="einwaage"><table class="tab"><thead><tr><th>Pos</th><th>Artikel</th><th class="z">Bestellt</th><th class="z">Erledigt</th><th class="z">ToDo</th><th>Status</th>${mitHinweis ? "<th>Hinweis</th>" : ""}</tr></thead>
		<tbody>${zeilen}</tbody></table></div>` + detail +
		(lieferung.zeilen.length ? `<div class="reihe"><button class="knopf gruen" data-a="buchen">Lieferschein buchen<small>${lieferung.zeilen.length} Registrierung(en)${offen ? " · " + offen + " Position(en) noch offen" : ""}</small></button></div>` : "") +
		(lieferung.zeilen.length ? `<div class="panel"><div class="fehlt" style="font-size:16px">Alle Registrierungen</div>${liste}</div>` : "");
	const rechts = gruppe("Herkunft", textFeld("scan", "Palette, Versandkarton oder Los scannen") +
			`<p class="fehlt" style="font-size:16px;margin:6px 0 0">Ganze Palette oder Versandkarton: NVE scannen. Lose Kartons: Los scannen, dann die Anzahl.</p>`) +
		gruppe("Ziel", zeileKV("Kunde", lieferung.titel) + zeileKV("Kundenauftrag", lieferung.auftrag) + zeileKV("Positionen", pos.length + " · offen " + offen)) +
		(hinweise.length ? hinweisHtml(hinweise.map((h) => ({ von: "Kundenauftrag", text: h }))) : "");
	return maske(links, rechts);
}
function lieferungZeigen() {
	const liste = lieferung.zeilen.map((z, i) => z.positionen.map((x, j) => `<div class="zeile"><div>${esc(x.name)}<br><span class="fehlt" style="font-size:16px">Los ${esc(x.charge)}${x.palette ? " · Palette …" + esc(x.palette.slice(-6)) : " · lose"}</span></div>
		<div class="rechts">${esc(stk(x.anzahl, x.einheit))} ${j === 0 ? `<button class="x" data-a="weg" data-i="${i}">✕</button>` : ""}</div></div>`).join("")).join("");
	const gescanntJe = {};
	lieferung.zeilen.forEach((z) => z.positionen.forEach((x) => { gescanntJe[x.artikel] = (gescanntJe[x.artikel] || 0) + x.menge; }));
	const hinweise = [...new Set(lieferung.positionen.map((z) => z.hinweis).filter(Boolean))];
	const auftragHtml = (lieferung.auftrag ? hinweisHtml(hinweise.map((h) => ({ von: "Kundenauftrag " + lieferung.auftrag, text: h }))) : "") + (lieferung.auftrag ? `<div class="panel"><div class="fehlt" style="font-size:16px">Kundenauftrag ${esc(lieferung.auftrag)}</div>${lieferung.positionen.map((z) => {
		const offen = (z.menge - z.geliefert) * (z.faktor || 1);
		const jetzt = gescanntJe[z.artikel] || 0;
		const fertig = jetzt >= offen - 1e-6;
		return `<div class="zeile"><div class="${fertig ? "ok" : ""}">${fertig ? "✔" : "○"} ${esc(z.name)}</div><div class="rechts ${fertig ? "ok" : "fehlt"}">${esc(zerlegen(z.einheiten, jetzt))}<br><small>von ${esc(zerlegen(z.einheiten, offen))}</small></div></div>`;
	}).join("")}</div>` : "");
	if (lieferung.auftrag) app.innerHTML = kopf("Verladung " + lieferung.auftrag + ": " + lieferung.titel, true) + verladungMaske(gescanntJe, liste, hinweise);
	else app.innerHTML = kopf("Lieferung an " + lieferung.titel, true) + auftragHtml +
		textFeld("scan", "Palette, Versandkarton oder Los scannen") +
		(lieferung.zeilen.length ? `<div class="panel">${liste}</div><div class="reihe"><button class="knopf gruen" data-a="buchen">Lieferschein buchen</button></div>` : "");
	aktionen(async (a, d) => {
		if (a === "sel") { lieferung.sel = +d.i; return lieferungZeigen(); }
		if (a === "weg") { lieferung.zeilen.splice(+d.i, 1); return lieferungZeigen(); }
		if (a !== "buchen") return beiAllgemein(a);
		const knopf = app.querySelector('[data-a="buchen"]');
		if (knopf) { knopf.disabled = true; knopf.textContent = "Bucht …"; }
		try {
			const e = await api("lieferung", { station: zustand.station, kunde: lieferung.kunde, kundenauftrag: lieferung.auftrag, zeilen: lieferung.zeilen.map((z) => z.anfrage) });
			ergebnis("Lieferung", ["Lieferschein: " + e.lieferschein, "Kunde: " + e.kunde, e.kundenauftrag ? "Kundenauftrag: " + e.kundenauftrag : "", e.positionen + " Position(en), " + kg(e.menge),
				e.paletten.length ? "Paletten: " + e.paletten.join(", ") : ""].filter(Boolean), e.hinweise)(beiAllgemein);
		} catch (err) {
			if (knopf) { knopf.disabled = false; knopf.textContent = "Lieferschein buchen"; }
			meldung("rot", err.message);
		}
	});
	enter("scan", async (v) => {
		if (!v) return;
		try {
			const i = await api("info", { code: v });
			if (i.typ === "palette") return lieferPalette(i);
			if (i.typ !== "charge") throw new Error("Bitte eine Palette oder ein Los scannen.");
			const einheiten = await api("einheiten", { artikel: i.artikel });
			anzahlAbfragen("Lose Kartons: Los " + i.charge, esc(i.artikelname) + (i.mhd ? " · MHD " + esc(i.mhd) : ""), einheiten, null, async (n, e) => {
				const anfrage = { code: i.charge, anzahl: n, einheit: e };
				try { lieferungZeilePlus(anfrage, await api("pruefe_lieferzeile", { station: zustand.station, ...anfrage })); }
				catch (err) { lieferungZeigen(); meldung("rot", err.message); }
			}, lieferungZeigen);
		} catch (e) { meldung("rot", e.message); }
	});
	fokus("scan");
}
function lieferPalette(p) {
	const aktiv = p.status === "Offen" || p.status === "Geschlossen";
	app.innerHTML = kopf("Palette …" + p.nve.slice(-6), true) +
		`<div class="panel"><div class="nve">${esc(p.nve)} ${statusMarke(p.status)}<br><small>${esc(p.kartons || "")} · ${esc(kg(p.menge || 0))}</small></div></div>` +
		(aktiv && hatInhalt(p) ? `<div class="reihe"><button class="knopf gruen" data-a="ganz">${p.versandkarton ? "Ganzen Versandkarton liefern" : "Ganze Palette liefern"}${(p.versandkartons || []).length ? `<small>mit ${p.versandkartons.length} Versandkartons</small>` : ""}</button></div>
			${p.positionen.length ? `<p class="fehlt">Oder Position antippen, um nur einzelne Kartons zu nehmen (${p.versandkarton ? "Karton" : "Palette"} wird angebrochen).</p>` : ""}` : "") +
		positionenHtml(p, aktiv ? "pos" : null) + kartonListeHtml(p, null) +
		((p.versandkartons || []).length ? `<p class="fehlt">Einen einzelnen Versandkarton liefern: seine NVE scannen.</p>` : "");
	aktionen(async (a, d) => {
		if (a === "zurueck") return lieferungZeigen();
		if (a === "ganz") {
			const anfrage = { palette: p.nve, ganz: 1 };
			try { return lieferungZeilePlus(anfrage, await api("pruefe_lieferzeile", { station: zustand.station, ...anfrage })); }
			catch (e) { return meldung("rot", e.message); }
		}
		if (a === "pos") {
			const pos = p.positionen[+d.i];
			return anzahlAbfragen("Von Palette …" + p.nve.slice(-6), `${esc(pos.name)} · Los ${esc(pos.charge)}<br><span class="fehlt">Auf der Palette: ${esc(stk(pos.anzahl, pos.einheit))}</span>`,
				[{ einheit: pos.einheit, faktor: 1 }], { einheit: pos.einheit }, async (n) => {
					const anfrage = { palette: p.nve, charge: pos.charge, anzahl: n, einheit: pos.einheit };
					try { lieferungZeilePlus(anfrage, await api("pruefe_lieferzeile", { station: zustand.station, ...anfrage })); }
					catch (e) { lieferungZeigen(); meldung("rot", e.message); }
				}, () => lieferPalette(p));
		}
		beiAllgemein(a);
	});
}
