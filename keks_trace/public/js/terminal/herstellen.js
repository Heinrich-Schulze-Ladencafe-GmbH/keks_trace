// Terminal: Herstellen und Verpacken, schnell buchen, Einwaage (Ansatz) mit Rezept und FEFO.

import { api, app, ein, esc, fokus, meldung, mg, rund, stk, zahl, zustand } from "./basis.js";
import { datumAnzeigen, datumFeld, datumWert, einheitSetzen, einheitWahl, faktorVon, textFeld, zahlFeld } from "./tastatur.js";
import { aktionen, anzahlAbfragen, beiAllgemein, enter, ergebnis, etikettDrucken, etikettNachdrucken, kopf, positionBox, suchListe, tabelle, zahlText } from "./rahmen.js";
import { kennzeichenMarken, pruefFelder, pruefWerte } from "./station.js";
import { auftragKopf, auftragWaehlen, hinweisHtml, linieStart } from "./linie.js";
import { paletteLaden } from "./paletten.js";

// ------------------------------------------------------------------ Herstellen / Verpacken
let ansatz;
let auftragsListe = [];
// ------------------------------------------------------------------ Schnell buchen (ohne Scannen)
// Herzenboden: offene Kundenaufträge antippen → Anzahl → Buchen. Manuelles Verpacken: was im Lager zum
// Verpacken liegt antippen → Anzahl Karton → Buchen. Verbraucht wird automatisch (älteste zuerst);
// fehlt etwas, kommt die Zutatenliste zum Selbst-Auswählen.
export async function herstellenStart() {
	if (zustand.vorschlagen) return schnellStart();
	return herstellenListe();
}
export async function schnellStart(nurLose) {
	const fw = zustand.nur_fertigware;
	const nachAuftrag = !!zustand.linie && !nurLose;
	app.innerHTML = kopf(fw ? "Verpacken" : "Herstellen", true) +
		`<p><b>${nachAuftrag ? "Offene Aufträge" : "Liegt zum Verpacken im Lager"}</b> – Zeile antippen</p><div id="aufg">Lädt …</div>
		<div class="reihe"><button class="knopf" data-a="klassisch">Ohne Auftrag${fw ? "" : " (z. B. Zuckerguss anmischen)"}</button></div>`;
	aktionen((a) => (a === "klassisch" ? herstellenListe() : beiAllgemein(a)));
	zustand.zurueckZu = () => schnellStart(nurLose);
	try {
		if (nachAuftrag) {
			const liste = await api("aufgaben", { station: zustand.station });
			suchListe("aufg", [["Auftrag", "auftrag"], ["Kunde", "kunde"], ["Artikel", "name"],
				["Bestellt", (a) => zahlText(a.bestellt), 1], ["Erledigt", (a) => zahlText(a.erledigt), 1], ["ToDo", (a) => zahlText(a.todo), 1],
				["Vorrat", (a) => !a.vorstufe ? "" : (a.vorrat_eigen ? zahlText(a.vorrat_eigen) + " für Auftrag" + (a.vorrat_frei ? " + " + zahlText(a.vorrat_frei) + " frei" : "") : zahlText(a.verfuegbar)) + " " + a.vorstufe, 1], ["Termin", "termin"],
				...(liste.some((a) => a.hinweis) ? [["Hinweis", (a) => a.hinweis || ""]] : [])],
				liste, (a) => schnellAnzahl(a), "Suchen: Kunde, Auftrag, Artikel …");
		} else {
			const liste = await api("zum_verpacken", { station: zustand.station });
			suchListe("aufg", [["Wo", (q) => q.linienlager ? "Linienlager" : "Lager"], ["Ware", "name"], ["Kiste / Charge", (q) => q.behaelter ? "Kiste " + q.behaelter : q.charge],
				["Backtag", "backtag"], ["MHD", (q) => q.mhd || ""], ["Menge", (q) => q.menge_text || mg(q.menge, q.einheit), 1]],
				liste, (q) => zielWaehlen(q), "Suchen: Ware, Kiste, Charge …");
		}
	} catch (e) { meldung("rot", e.message); }
}
async function schnellAnzahl(a) {
	let einheiten = [{ einheit: a.einheit, faktor: 1 }];
	if (zustand.nur_fertigware) { try { const e = await api("einheiten", { artikel: a.artikel }); if (e && e.length) einheiten = e; } catch (x) { /* Lagereinheit */ } }
	const vorschlag = a.verfuegbar != null ? Math.min(a.todo, a.verfuegbar) : a.todo;
	anzahlAbfragen(a.name + " für " + a.kunde,
		`Auftrag ${esc(a.auftrag)} · noch ${esc(zahlText(a.todo))} ${esc(ein(a.einheit))}${a.vorstufe ? ` · im Lager ${esc(zahlText(a.verfuegbar))} ${esc(a.vorstufe)}` : ""}`,
		einheiten, { anzahl: vorschlag > 0 ? vorschlag : null, einheit: einheiten.find((e) => e.einheit === a.einheit) ? a.einheit : einheiten[0].einheit },
		(n, e) => schnellBuchen(a.artikel, n * faktorVon(einheiten, e), { anzahl: n, einheit: e, auftrag: a }), () => zustand.zurueckZu());
}
// Was wird aus der losen Ware? Erst offene Kundenaufträge, die sie brauchen, dann jeder mögliche Artikel
async function zielWaehlen(q) {
	app.innerHTML = kopf(q.name + ": verpacken für", true) +
		`<p><b>Kundenaufträge</b> – Zeile antippen</p><div id="ziel-auftraege">Lädt …</div>
		<p style="margin-top:22px"><b>Ohne Auftrag (ins Lager)</b> – Artikel antippen</p><div id="ziel-artikel"></div>`;
	aktionen((a) => (a === "zurueck" ? zustand.zurueckZu() : beiAllgemein(a)));
	try {
		const z = await api("verpacken_ziele", { station: zustand.station, lose: q.lose });
		if (z.auftraege.length) suchListe("ziel-auftraege", [["Auftrag", "auftrag"], ["Kunde", "kunde"], ["Artikel", "name"],
			["Offen", "offen_text", 1], ["Termin", "termin"]], z.auftraege, (au) => verpackenAnzahl(q, au, au), "Suchen: Kunde, Auftrag, Artikel …");
		else document.getElementById("ziel-auftraege").innerHTML = `<span class="fehlt">Kein offener Kundenauftrag braucht diese Ware.</span>`;
		suchListe("ziel-artikel", [["Artikel", "artikel"], ["Bezeichnung", "name"]], z.artikel, (ziel) => verpackenAnzahl(q, ziel), "Suchen: Artikel, Gebinde …");
	} catch (e) { meldung("rot", e.message); }
}
async function verpackenAnzahl(q, ziel, au) {
	let einheiten = [];
	try { einheiten = await api("einheiten", { artikel: ziel.artikel }); } catch (x) { /* unten */ }
	if (!einheiten || !einheiten.length) einheiten = [{ einheit: "Kg", faktor: 1 }];
	anzahlAbfragen(ziel.name + (au ? " für " + au.kunde : ""), `aus ${esc(q.name)} · ${esc(q.behaelter ? "Kiste " + q.behaelter : q.charge)} · ${esc(q.menge_text || mg(q.menge, q.einheit))} im ${q.linienlager ? "Linienlager" : "Lager"}${au ? ` · Auftrag ${esc(au.auftrag)}, offen ${esc(au.offen_text)}` : ""}`,
		einheiten, null, (n, e) => paletteFrage(ziel.name, (palette) => schnellBuchen(ziel.artikel, n * faktorVon(einheiten, e), { anzahl: n, einheit: e, bevorzugt: q.code, palette, auftrag: au })),
		() => zustand.zurueckZu());
}
// Kartons auf eine Palette (jede Palette hat eine NVE): scannen, neue Palette oder lose ins Lager
function paletteFrage(titel, weiter) {
	app.innerHTML = kopf(titel + ": wohin?", true) + textFeld("scan", "Palette scannen") +
		`<div class="reihe"><button class="knopf gruen" data-a="neu">Neue Palette<small>NVE-Etikett wird gedruckt</small></button>
		<button class="knopf" data-a="ohne">Ohne Palette<small>Kartons lose ins Lager</small></button></div>`;
	aktionen(async (a) => {
		if (a === "ohne") return weiter(null);
		if (a === "neu") {
			try { return weiter((await api("palette_neu", { station: zustand.station, typ: "Lagerpalette" })).nve); } catch (e) { return meldung("rot", e.message); }
		}
		beiAllgemein(a);
	});
	enter("scan", (v) => v && weiter(v));
	fokus("scan");
}
async function schnellBuchen(ziel, menge, o) {
	const au = o.auftrag;
	try {
		const v = await api("vorschlag", { station: zustand.station, ziel, menge, bevorzugt: o.bevorzugt || null, kundenauftrag: au ? au.auftrag : null });
		if (v.hinweise.length) {
			// Etwas fehlt oder passt nicht: Zutatenliste zum Selbst-Auswählen
			ansatz = { rezept: await api("rezept", { artikel: ziel, menge, station: zustand.station }), zeilen: v.zeilen, offen: null, einheit: o.einheit,
				auftrag: au ? { auftrag: au.auftrag, artikel: au.artikel, name: au.name, kundenname: au.kunde, menge: au.bestellt, verpackt: au.erledigt, offen_verpacken: au.todo, einheit: au.einheit } : null };
			ansatzZeigen();
			return meldung("orange", "Bitte prüfen", v.hinweise.join(" · "));
		}
		const e = await api("herstellen", {
			station: zustand.station, ziel, zeilen: v.zeilen.map((z) => ({ code: z.code, menge: z.menge })),
			ausbringung: menge, anzahl: o.anzahl, einheit: o.einheit, kundenauftrag: au ? au.auftrag : null, ziel_behaelter: o.palette || null,
		});
		if (o.palette) etikettDrucken(o.palette);
		ergebnis(e.name, [
			e.los ? "Los: " + e.los : "Charge: " + e.charge,
			"Menge: " + (e.anzahl ? stk(e.anzahl, ein(e.einheit)) : mg(e.menge, e.einheit)),
			e.mhd ? "MHD: " + e.mhd : "",
			au ? "Kundenauftrag: " + au.auftrag + " · " + au.kunde : "",
			"Verbraucht: " + v.zeilen.map((z) => z.name + " " + mg(z.menge, z.einheit) + " (" + (z.silo || z.behaelter || z.charge) + ")").join(", "),
		].filter(Boolean), e.hinweise, `<button class="knopf gruen" data-a="weiter">Nächste Buchung</button>`)((a) => (a === "weiter" ? zustand.zurueckZu() : beiAllgemein(a)));
	} catch (err) { meldung("rot", err.message); }
}
async function herstellenListe() {
	const verpackung = zustand.nur_fertigware;
	if ((zustand.funktionen || []).includes("linie")) {
		// Kneter an der Linie: erst den laufenden Produktionsauftrag wählen
		let i;
		try { i = await api("linie_info", { station: zustand.station }); } catch (e) { return meldung("rot", e.message); }
		if (!i || !i.auftrag || i.status !== "Läuft") return auftragWaehlen("Kneten", herstellenStart);
		// Ohne veredelten Teig (z. B. Herzen-Rohlinge aus Grundteig): Kübel direkt auf die Linie
		if (!i.zutaten.some((z) => z.stufe === "Teig veredelt")) return linieStart();
		zustand.linienAuftrag = i;
	} else zustand.linienAuftrag = null;
	const la = zustand.linienAuftrag;
	app.innerHTML = kopf(la ? "Kneten" : verpackung ? "Verpacken" : "Herstellen", true) + (la ? auftragKopf(la) +
		`<div class="reihe" style="margin-top:0"><button class="knopf" data-a="direkt-linie">Kübel oder Rework direkt auf die Linie<small>ohne Kneten scannen</small></button></div>` : "") +
		(verpackung ? `<p><b>Kundenaufträge</b> – Zeile antippen</p><div id="auftraege">Lädt …</div><p style="margin-top:22px"><b>Ohne Auftrag</b></p>` : `<p>Was wird hergestellt?</p>`) +
		`<div id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const [liste, auftraege] = await Promise.all([
			api("rezepte", { station: zustand.station }),
			verpackung ? api("auftraege", { station: zustand.station }) : Promise.resolve([]),
		]);
		auftragsListe = auftraege.filter((z) => z.offen_verpacken > 0);
		if (verpackung) {
			document.getElementById("auftraege").innerHTML = auftragsListe.length
				? tabelle([["Auftrag", "auftrag"], ["Kunde", "kundenname"], ["Artikel", "artikel"], ["Bezeichnung", "name"],
					["Bestellt", (z) => zahlText(z.menge), 1], ["Erledigt", (z) => zahlText(z.verpackt), 1], ["ToDo", (z) => zahlText(z.offen_verpacken), 1],
					["Einh.", (z) => ein(z.einheit)], ["Termin", "termin"]], auftragsListe, "auftrag")
				: `<span class="fehlt">Keine offenen Kundenaufträge.</span>`;
		}
		// Kneter: nur der Teig, den der laufende Auftrag braucht
		const wahl = la ? liste.filter((r) => la.zutaten.some((z) => z.artikel === r.artikel)) : liste;
		suchListe("liste", [["Artikel", "artikel"], ["Bezeichnung", "name"], ["Stufe", "stufe"]], wahl, (r) => rezeptMenge(r.artikel), "Suchen: Artikelnummer oder Bezeichnung …");
		aktionen((a, d) => {
			if (a === "pa-wechseln") return auftragWaehlen("Kneten", herstellenStart);
			if (a === "direkt-linie") return linieStart();
			if (a === "rezept") return rezeptMenge(d.artikel);
			if (a === "auftrag") { const z = auftragsListe[+d.i]; return rezeptMenge(z.artikel, z); }
			beiAllgemein(a);
		});
	} catch (e) { meldung("rot", e.message); }
}
async function rezeptMenge(artikel, auftrag) {
	try {
		const r = await api("rezept", { artikel, station: zustand.station });
		const zaehlen = r.einheiten && r.einheiten.length > 1;
		let einheit = zaehlen ? r.einheiten[0].einheit : null;
		let vorschlag = zaehlen ? Math.round(r.sollmenge / r.einheiten[0].faktor) : r.sollmenge;
		if (auftrag && !zaehlen) vorschlag = rund(auftrag.offen_kg);
		if (auftrag && zaehlen) {
			if (r.einheiten.some((e) => e.einheit === auftrag.einheit)) einheit = auftrag.einheit;
			vorschlag = Math.ceil(auftrag.offen_kg / faktorVon(r.einheiten, einheit) - 1e-6);
		}
		app.innerHTML = kopf(r.name, true) +
			(auftrag ? positionBox(auftrag.artikel + "  " + auftrag.name, auftrag.auftrag + " · " + auftrag.kundenname, auftrag.menge, auftrag.verpackt, auftrag.offen_verpacken, auftrag.einheit) : "") +
			(zaehlen ? einheitWahl(r.einheiten, einheit, r.einheit) : "") +
			zahlFeld("soll", zaehlen ? `Soll – wie viele <span id="einheit-text">${esc(ein(einheit))}</span>?` : `Sollmenge (${esc(ein(r.einheit))}) – laut Rezept ${esc(mg(r.sollmenge, r.einheit))}`, vorschlag);
		const weiter = () => {
			const n = zahl(document.getElementById("soll").value);
			ansatzStarten(artikel, zaehlen ? n * faktorVon(r.einheiten, einheit) : n, einheit, auftrag);
		};
		aktionen((a, d) => {
			if (a === "einheit") { einheit = d.e; einheitSetzen(einheit); document.getElementById("einheit-text").textContent = einheit; return fokus("soll"); }
			beiAllgemein(a);
		});
		enter("soll", weiter);
		fokus("soll");
	} catch (e) { meldung("rot", e.message); }
}
async function ansatzStarten(artikel, soll, einheit, auftrag) {
	if (soll <= 0) return meldung("rot", "Bitte eine Sollmenge eingeben.");
	try {
		ansatz = { rezept: await api("rezept", { artikel, menge: soll, station: zustand.station }), zeilen: [], offen: null, einheit, auftrag };
		let fehlt = [];
		if (zustand.vorschlagen) {
			// Hier wird nicht gescannt: das Terminal füllt alles aus, älteste Ware zuerst
			const v = await api("vorschlag", { station: zustand.station, ziel: artikel, menge: soll });
			ansatz.zeilen = v.zeilen;
			fehlt = v.hinweise;
		} else {
			// Vorrat am Tisch (Folie, Etikett, Schleife ...): ohne Scan, Menge laut Rezept
			for (const z of ansatz.rezept.zutaten.filter((x) => x.vorrat)) {
				try { ansatz.zeilen.push(await api("pruefe_zeile", { station: zustand.station, ziel: artikel, code: z.vorrat, menge: z.menge })); }
				catch (e) { fehlt.push(z.vorrat + ": " + e.message); }
			}
		}
		ansatzZeigen();
		if (fehlt.length) meldung("orange", "Bitte prüfen", fehlt.join(" · "));
	} catch (e) { meldung("rot", e.message); }
}
function gescannt(artikelCode) {
	return ansatz.zeilen.filter((z) => z.artikel === artikelCode).reduce((s, z) => s + z.menge, 0);
}
// Bausteine der Arbeitsmaske (FOBIS-Aufbau)
export function maske(links, rechts) { return `<div class="maske"><div class="m-links">${links}</div><div class="m-rechts">${rechts}</div></div>`; }
export function gruppe(titel, inhalt) { return inhalt ? `<fieldset class="m-gruppe"><legend>${esc(titel)}</legend>${inhalt}</fieldset>` : ""; }
export function zeileKV(k, w) { return w == null || w === "" ? "" : `<div class="zeile"><div class="fehlt">${esc(k)}</div><div class="rechts">${esc(w)}</div></div>`; }
// unter: optional je Zahl ein kleiner Text darunter (z. B. „2 Paletten + 10 Karton“)
export function grossZahlen(bestellt, erledigt, todo, einheit, unter) {
	const u = unter || [];
	const z = (n, i) => `<b>${esc(zahlText(rund(n)))}</b><i>${esc(ein(einheit || ""))}</i>${u[i] ? `<small style="color:var(--muted)">${esc(u[i])}</small>` : ""}`;
	return `<div class="gross3"><div><small>Bestellt</small>${z(bestellt, 0)}</div><div><small>Erledigt</small>${z(erledigt, 1)}</div><div><small>ToDo</small>${z(Math.max(todo, 0), 2)}</div></div>`;
}
// Gebinde-Text zur Zutat: „Sack 25 kg“
function gebindeText(z) { return (z.gebinde || []).map((g) => ein(g.einheit) + " " + mg(g.faktor, z.einheit)).join(", "); }
function ansatzZeigen() {
	const r = ansatz.rezept;
	const stand = (z) => {
		const ist = gescannt(z.artikel);
		const ueber = r.rezept_pruefen && ist > 0 && Math.abs(ist - z.menge) > (z.toleranz || 0) + 1e-9;
		return { ist, todo: Math.max(rund(z.menge - ist), 0), ueber, fertig: ist >= z.menge * 0.98 && !ueber };
	};
	// gewählte Zutat: nach dem Scan die gescannte, sonst die erste offene
	if (ansatz.offen && ansatz.offen.artikel) ansatz.sel = ansatz.offen.artikel;
	if (!r.zutaten.some((z) => z.artikel === ansatz.sel)) ansatz.sel = (r.zutaten.find((z) => !stand(z).fertig) || r.zutaten[0] || {}).artikel;
	const sel = r.zutaten.find((z) => z.artikel === ansatz.sel);
	// Links oben: alle Zutaten wie bei FOBIS (Bestellt / Erledigt / ToDo, Lager)
	const zeilen = r.zutaten.map((z, i) => {
		const st = stand(z);
		return `<tr data-a="sel" data-artikel="${esc(z.artikel)}" class="${z.artikel === ansatz.sel ? "gewaehlt" : st.fertig ? "fertig" : st.ueber ? "ueber" : ""}">
			<td>${i + 1}</td><td>${st.ueber ? "⚠" : st.fertig ? "✔" : "○"} ${esc(z.name)}<small>${esc(z.artikel)}</small></td>
			<td>${esc(z.silo || z.vorrat || z.lager || "")}</td>
			<td class="z">${esc(mg(z.menge, z.einheit))}</td><td class="z">${st.ist ? esc(mg(st.ist, z.einheit)) : "–"}</td>
			<td class="z todo">${st.todo > 0 ? esc(mg(st.todo, z.einheit)) : "–"}</td></tr>`;
	}).join("") + ansatz.zeilen.filter((z) => z.rework).map((z) => `<tr class="fertig"><td></td><td>✔ Rework: ${esc(z.name)}</td><td>${esc(z.behaelter || "")}</td>
		<td class="z">–</td><td class="z">${esc(mg(z.menge, z.einheit))}</td><td class="z">–</td></tr>`).join("");
	// Links unten: die gewählte Zutat groß, mit ihren Registrierungen
	let detail = "";
	if (sel) {
		const st = stand(sel);
		const reg = ansatz.zeilen.map((z, i) => ({ z, i })).filter((x) => x.z.artikel === sel.artikel);
		detail = `<div class="m-detail"><div class="titel"><div><b>${esc(sel.artikel)}</b> ${esc(sel.name)}<small>${esc([sel.lager, gebindeText(sel)].filter(Boolean).join(" · "))}</small></div>
			<div class="fehlt" style="font-size:16px;text-align:right">${sel.toleranz ? "Toleranz ± " + esc(mg(sel.toleranz, sel.einheit)) : ""}${st.ueber ? `<br><b style="color:#b45309">${esc(prozentText(st.ist, sel.menge))}</b>` : ""}</div></div>
			${grossZahlen(sel.menge, st.ist, st.todo, sel.einheit)}
			${reg.length ? `<div style="margin-top:8px">${reg.map((x) => `<div class="zeile"><div>${esc(x.z.charge ? "Charge " + x.z.charge : "")}${x.z.behaelter ? " · " + esc(x.z.behaelter) : ""}${x.z.silo ? " · " + esc(x.z.silo) : ""}</div>
				<div class="rechts">${esc(mg(x.z.menge, x.z.einheit))} <button class="x" data-a="weg" data-i="${x.i}">✕</button></div></div>`).join("")}</div>` : ""}</div>`;
	}
	const au = ansatz.auftrag;
	const pa = zustand.linienAuftrag;
	const links = `<div class="einwaage"><table class="tab"><thead><tr><th>Pos</th><th>Zutat</th><th>Lager</th><th class="z">Bestellt</th><th class="z">Erledigt</th><th class="z">ToDo</th></tr></thead>
			<tbody>${zeilen}</tbody></table></div>` + detail +
		// Buchen links unter der Zutat: rechts unten steht fest der Ziffernblock
		(ansatz.zeilen.length && !ansatz.offen ? `<div class="reihe"><button class="knopf gruen" data-a="abschluss">Weiter zum Buchen<small>${ansatz.zeilen.length} Registrierung(en)</small></button></div>` : "") +
		(sollAnpassbar() ? `<div class="reihe"><button class="knopf" data-a="soll-anpassen">Soll an Grundteig anpassen: ${esc(mg(sollAnpassbar(), r.einheit))}</button></div>` : "") +
		(r.kuebel && r.kuebel.length ? `<div class="panel"><div class="fehlt" style="font-size:16px">Grundteig-Kübel (ältester zuerst)</div><div class="gross">${r.kuebel.map((k) => esc(k.code)).join(" · ")}</div>
			<div class="fehlt" style="font-size:16px">${r.kuebel.map((k) => esc(k.code + ": " + k.name + (k.datum ? " vom " + k.datum : "") + ", " + mg(k.menge, "Kg"))).join("<br>")}</div></div>` : "") +
		(au || pa ? `<div class="reiter"><button class="an" type="button">Registrierungen</button></div><div class="panel" style="margin-top:0" id="registrierungen">Lädt …</div>` : "");
	// Rechts: Herkunft (woher die gewählte Zutat kommt), Ziel, Eingabe
	const herkunft = ansatz.offen ? zeileKV("Gescannt", ansatz.offen.anzeige) + `<button class="link" data-a="abbrechen">Scan verwerfen</button>`
		: textFeld("scan", zustand.vorschlagen ? "Scannen (oder unten wählen)" : "Gebinde, Behälter oder Silo scannen" + (r.rework_moeglich ? " – auch Rework" : "")) +
			(sel ? (sel.vorrat ? zeileKV("Aus Vorrat", sel.vorrat)
				: sel.silo ? `<button class="knopf" data-a="silo-zutat" data-silo="${esc(sel.silo)}">${esc(sel.name)} aus ${esc(sel.silo)}</button>`
				: `<button class="knopf" data-a="auswahl" data-artikel="${esc(sel.artikel)}">${esc(sel.name)}: Charge wählen</button>`) : "");
	const ziel = zeileKV("Artikel", r.name) + zeileKV("Sollmenge", mg(r.sollmenge, r.einheit)) + (au ? zeileKV("Kundenauftrag", au.auftrag + (au.kundenname ? " · " + au.kundenname : "")) : "") +
		(r.kennzeichen && r.kennzeichen.length ? `<div class="zeile"><div class="fehlt">Kennzeichen</div><div class="rechts">${kennzeichenMarken(r.kennzeichen)}</div></div>` : "");
	const eingabe = ansatz.offen ? mengeEingabeHtml(ansatz.offen) : `<p class="fehlt" style="font-size:16px;margin:6px 0">Erst scannen, dann die Menge.</p>`;
	// Eingabe oben, damit der Ziffernblock sie nicht verdeckt; Ziel ist nur Information
	const rechts = gruppe("Herkunft", herkunft) + gruppe("Eingabe", eingabe) + gruppe("Ziel", ziel);
	app.innerHTML = kopf((au ? "Produktion " + au.auftrag + ": " : "") + r.name + " · " + mg(r.sollmenge, r.einheit), true) +
		(au && au.hinweis ? hinweisHtml([{ von: "Kundenauftrag " + au.auftrag, text: au.hinweis }]) : "") +
		(r.umstellung_bio ? `<div class="meldung orange">Umstellung auf Bio: hier wurde zuletzt konventionell produziert. Vor dem Buchen Reinigung bzw. Spülcharge bestätigen.</div>` : "") +
		maske(links, rechts);
	if (au || pa) registrierungenLaden(au ? { kundenauftrag: au.auftrag } : { produktionsauftrag: pa.auftrag });
	aktionen((a, d) => {
		if (a === "sel") { if (!ansatz.offen) ansatz.sel = d.artikel; return ansatzZeigen(); }
		if (a === "silo-zutat") return codeGescannt(d.silo);
		if (a === "auswahl") return auswahlZeigen(d.artikel);
		if (a === "weg") { ansatz.zeilen.splice(+d.i, 1); return ansatzZeigen(); }
		if (a === "abbrechen") { ansatz.offen = null; return ansatzZeigen(); }
		if (a === "einheit" && ansatz.offen) return gebindeWaehlen(d.e);
		if (a === "abschluss") return ansatzAbschluss();
		if (a === "soll-anpassen") return sollAnpassen(sollAnpassbar());
		beiAllgemein(a);
	});
	enter("scan", (v) => (ansatz.offen ? mengeEingegeben(v) : codeGescannt(v)));
	const scanFeld = document.getElementById("scan");
	if (ansatz.offen && scanFeld) { scanFeld.addEventListener("input", gebindeHinweis); gebindeHinweis(); }
	fokus("scan");
	if (ansatz.offen) setTimeout(() => document.getElementById("scan").select(), 40);
}
// Selbst auswählen (ohne Scanner): Kisten/Chargen eines Artikels antippen; ersetzt den Vorschlag
async function auswahlZeigen(artikel) {
	const z = ansatz.rezept.zutaten.find((x) => x.artikel === artikel);
	app.innerHTML = kopf(z.name + ": woher?", true) + `<p>Antippen, was genommen wird (älteste zuerst). Gebraucht: ${esc(mg(z.menge, z.einheit))}</p><div id="quellen">Lädt …</div>`;
	aktionen((a) => (a === "zurueck" ? ansatzZeigen() : beiAllgemein(a)));
	try {
		const liste = await api("auswahl", { station: zustand.station, artikel });
		const el = document.getElementById("quellen");
		if (!liste.length) { el.innerHTML = `<p class="fehlt">Nichts im Lager.</p>`; return; }
		el.innerHTML = tabelle([["Kiste / Charge", (q) => q.behaelter ? "Kiste " + q.behaelter : q.charge], ["Charge", "charge"], ["Menge", (q) => mg(q.menge, z.einheit), 1], ["MHD", (q) => q.mhd || ""]], liste, "quelle");
		aktionen(async (a, d) => {
			if (a === "zurueck") return ansatzZeigen();
			if (a !== "quelle") return beiAllgemein(a);
			const q = liste[+d.i];
			// erste Wahl ersetzt den Vorschlag, weitere Wahlen ergänzen (wenn eine Kiste nicht reicht)
			if (!ansatz.gewaehlt) ansatz.gewaehlt = {};
			if (!ansatz.gewaehlt[artikel]) { ansatz.zeilen = ansatz.zeilen.filter((x) => x.artikel !== artikel); ansatz.gewaehlt[artikel] = true; }
			const fehlt = rund(z.menge - gescannt(artikel));
			if (fehlt <= 0) return ansatzZeigen();
			try {
				ansatz.zeilen.push(await api("pruefe_zeile", { station: zustand.station, ziel: ansatz.rezept.artikel, code: q.code, menge: Math.min(fehlt, q.menge) }));
				ansatzZeigen();
			} catch (e) { meldung("rot", e.message); }
		});
	} catch (e) { meldung("rot", e.message); }
}
export async function registrierungenLaden(args) {
	try {
		const liste = await api("registrierungen", { station: zustand.station, ...args });
		const el = document.getElementById("registrierungen");
		if (!el) return;
		el.innerHTML = liste.length
			? tabelle([["Zeit", "wann"], ["Los", "los"], ["Menge", "menge_text", 1], ["MHD", "mhd"], ["Station", "station"]], liste)
			: `<span class="fehlt">Zu diesem Auftrag ist noch nichts gebucht.</span>`;
	} catch (e) { /* Anzeige ist nur Info */ }
}
// Menge zur gescannten Zutat: in kg oder in ganzen Gebinden (Sack, Kollo), wenn am Artikel eine Umrechnung steht
function mengeEingabeHtml(o) {
	const g = o.gebinde || [];
	const zaehl = g.find((x) => x.einheit === o.zaehl);
	return (g.length ? einheitWahl([{ einheit: o.einheit, faktor: 1 }, ...g], o.zaehl || o.einheit, o.einheit) : "") +
		zahlFeld("scan", zaehl ? `Wie viele ${esc(ein(zaehl.einheit))} (je ${esc(mg(zaehl.faktor, o.einheit))}) für ${esc(o.anzeige)}?`
			: `Menge (${esc(ein(o.einheit))}) für ${esc(o.anzeige)}`, o.vorschlag) +
		(zaehl ? `<small class="feld-hinweis" id="gebinde-hinweis"></small>` : "");
}
function gebindeFaktor(o) { const g = (o.gebinde || []).find((x) => x.einheit === o.zaehl); return g ? g.faktor : 1; }
function gebindeHinweis() {
	const o = ansatz.offen, h = document.getElementById("gebinde-hinweis"), f = document.getElementById("scan");
	if (!o || !h || !f) return;
	const n = zahl(f.value);
	h.className = "feld-hinweis" + (n > 0 ? " ok" : "");
	h.textContent = n > 0 ? "= " + mg(n * gebindeFaktor(o), o.einheit) + (o.todo ? " · ToDo " + mg(o.todo, o.einheit) : "") : "";
}
function gebindeWaehlen(einheit) {
	const o = ansatz.offen;
	o.zaehl = einheit === o.einheit ? null : einheit;
	const f = gebindeFaktor(o);
	o.vorschlag = o.todo > 0 ? (o.zaehl ? Math.max(1, Math.round(o.todo / f)) : rund(o.todo)) : "";
	ansatzZeigen();
}
async function codeGescannt(code) {
	if (!code) return;
	const r = ansatz.rezept;
	let info = {};
	try { info = await api("info", { code }); } catch (e) { ansatzZeigen(); return meldung("rot", e.message); }
	if (info.typ === "palette") { ansatzZeigen(); return meldung("rot", "Das ist eine Palette. Bitte Kiste, Behälter oder Gebinde scannen."); }
	const passende = r.zutaten.find((z) => z.artikel === info.artikel);
	let ziel = passende ? passende.menge - gescannt(passende.artikel) : null;
	if (ziel != null && info.inhalt != null && info.typ !== "silo") ziel = Math.min(ziel, info.inhalt);
	const anzeige = (info.artikelname || code) + (info.typ === "silo" ? "" : " · " + code);
	ansatz.offen = { code, anzeige, einheit: passende ? passende.einheit : null, vorschlag: ziel && ziel > 0 ? rund(ziel) : "",
		todo: ziel && ziel > 0 ? rund(ziel) : 0, gebinde: info.typ === "silo" || !passende ? [] : passende.gebinde || [],
		artikel: passende ? passende.artikel : null };
	// Geht der Rest in ganzen Gebinden auf (z. B. 50 kg = 2 Sack), gleich in Gebinden fragen
	const ganz = ansatz.offen.gebinde.slice().reverse().find((g) => ziel >= g.faktor && Math.abs(ziel / g.faktor - Math.round(ziel / g.faktor)) < 0.02);
	if (ganz) { ansatz.offen.zaehl = ganz.einheit; ansatz.offen.vorschlag = Math.round(ziel / ganz.faktor); }
	// Grundteig-Kübel kommt immer ganz in den Kneter: keine Mengenabfrage
	if (info.typ === "behaelter" && passende && passende.stufe === "Grundteig" && info.inhalt > 0) return mengeEingegeben(String(info.inhalt));
	ansatzZeigen();
}
async function mengeEingegeben(wert) {
	const menge = rund(zahl(wert) * gebindeFaktor(ansatz.offen), 6); // „2 Sack“ → 50 kg
	const code = ansatz.offen.code;
	if (menge <= 0) return meldung("rot", "Bitte eine Menge eingeben.");
	try {
		const z = await api("pruefe_zeile", { station: zustand.station, ziel: ansatz.rezept.artikel, code, menge });
		ansatz.zeilen.push(z);
		ansatz.offen = null;
		ansatzZeigen();
		const f = fefoOffen().find((x) => x.z === z);
		if (f) return meldung("orange", "Älteres MHD im Lager: " + f.aelter.map((a) => a.charge + " (MHD " + a.mhd + ")").join(", "),
			"Besser die ältere Charge nehmen. Sonst beim Buchen einen Grund wählen.");
		meldung("gruen", "OK: " + z.name + " " + mg(z.menge, z.einheit), z.charge ? "Charge " + z.charge : z.silo ? "aus " + z.silo + " (Charge wird nach FIFO zugeteilt)" : "");
	} catch (e) {
		ansatz.offen = null;
		ansatzZeigen();
		meldung("rot", e.message);
	}
}
// Rezepturtreue: Einwaage je Zutat gegen das Soll (Sollmenge, z. B. halbe Masse), Toleranz aus dem Rezept
function prozentText(ist, soll) { return soll ? (ist >= soll ? "+" : "") + Math.round((ist / soll - 1) * 100) + " %" : ""; }
const REZEPT_GRUENDE = ["Rezept angepasst (Anweisung)", "Korrektur nach Prüfung", "Rest aufgebraucht", "Sonstiges"];
function rezeptAbweichungen() {
	const r = ansatz.rezept;
	if (!r.rezept_pruefen) return [];
	return r.zutaten.map((z) => ({ z, ist: gescannt(z.artikel) })).filter((x) => Math.abs(x.ist - x.z.menge) > (x.z.toleranz || 0) + 1e-9);
}
// Neue Sollmenge, wenn ein Grundteig (ganzer Kübel) eingesetzt ist und vom Soll abweicht; sonst 0
function sollAnpassbar() {
	const r = ansatz.rezept;
	if (!r.rezept_pruefen) return 0;
	const gt = r.zutaten.find((z) => z.stufe === "Grundteig" && z.menge > 0);
	if (!gt) return 0;
	const ist = gescannt(gt.artikel);
	if (ist <= 0 || Math.abs(ist - gt.menge) <= (gt.toleranz || 0) + 1e-9) return 0;
	return rund(r.sollmenge * ist / gt.menge, 3);
}
async function sollAnpassen(soll) {
	try {
		ansatz.rezept = await api("rezept", { artikel: ansatz.rezept.artikel, menge: soll, station: zustand.station });
		ansatzZeigen();
		meldung("gruen", "Soll angepasst: " + mg(soll, ansatz.rezept.einheit), "Die übrigen Zutaten richten sich jetzt nach dem eingesetzten Grundteig.");
	} catch (e) { meldung("rot", e.message); }
}
function rezeptPanel() {
	const abw = rezeptAbweichungen();
	if (!abw.length) return "";
	const r = ansatz.rezept;
	return `<div class="meldung orange">Einwaage außerhalb der Toleranz<small>${abw.map((x) => esc(x.z.name + ": " + mg(x.ist, x.z.einheit) + " statt " + mg(x.z.menge, x.z.einheit) +
		(x.ist ? " (" + prozentText(x.ist, x.z.menge) + ")" : " (fehlt)"))).join("<br>")}</small></div>
		<label>Grund für die Abweichung${r.rezept_pflicht ? "" : " (freiwillig)"}</label><div class="einheiten">${REZEPT_GRUENDE.map((g) =>
			`<button type="button" data-a="rezept-grund" data-e="${esc(g)}" class="${ansatz.rezeptGrund === g ? "an" : ""}">${esc(g)}</button>`).join("")}</div>`;
}
// FEFO: Zeilen mit älterer Charge im Lager (in diesem Ansatz schon gescannte zählen nicht)
export const FEFO_GRUENDE = ["Ältere Charge nicht erreichbar", "Ältere Charge angebrochen oder beschädigt", "Anweisung QS", "Sonstiges"];
function fefoOffen() {
	const verwendet = new Set(ansatz.zeilen.map((z) => z.charge).filter(Boolean));
	return ansatz.zeilen.map((z) => ({ z, aelter: (z.fefo || []).filter((a) => !verwendet.has(a.charge)) })).filter((x) => x.aelter.length);
}
function fefoPanel() {
	const offen = fefoOffen();
	if (!offen.length) return "";
	return `<div class="meldung orange">Älteres MHD liegt im Lager<small>${offen.map((x) => esc(x.z.name + ": genommen " + x.z.charge + ", älter " +
		x.aelter.map((a) => a.charge + " (MHD " + a.mhd + ")").join(", "))).join("<br>")}</small></div>
		<label>Grund für die Abweichung${offen.some((x) => x.z.fefo_pflicht) ? "" : " (freiwillig)"}</label><div class="einheiten">${FEFO_GRUENDE.map((g) =>
			`<button type="button" data-a="fefo-grund" data-e="${esc(g)}" class="${ansatz.fefoGrund === g ? "an" : ""}">${esc(g)}</button>`).join("")}</div>`;
}
function ansatzAbschluss() {
	const r = ansatz.rezept;
	const packmittel = new Set(r.zutaten.filter((z) => z.stufe === "Packmittel").map((z) => z.artikel));
	const summe = ansatz.zeilen.filter((z) => (!z.einheit || z.einheit === (r.einheit || "Kg")) && !packmittel.has(z.artikel)).reduce((s, z) => s + z.menge, 0);
	const zaehlen = r.einheiten && r.einheiten.length > 1;
	let einheit = ansatz.einheit || (zaehlen ? r.einheiten[0].einheit : null);
	const kgVorschlag = rund(summe * r.ausbeute);
	const vorschlag = zaehlen ? Math.floor(kgVorschlag / faktorVon(r.einheiten, einheit) + 1e-6) : kgVorschlag;
	const fertigware = r.stufe === "Fertigware";
	app.innerHTML = kopf(r.name, true) + `
		<div class="panel"><div class="zeile"><div>${r.einheit === "Kg" ? "Eingewogen" : "Eingesetzt"}</div><div class="rechts">${esc(mg(summe, r.einheit))}</div></div></div>
		${zaehlen ? einheitWahl(r.einheiten, einheit, r.einheit) : ""}
		<div id="vorschau"></div>
		${zahlFeld("aus", zaehlen ? `Ausbringung – wie viele <span id="einheit-text">${esc(einheit)}</span>?` : "Ausbringung (" + ein(r.einheit) + ")" + (r.ausbeute < 0.999 || r.ausbeute > 1.001 ? " – Vorschlag laut Rezept" : ""), vorschlag)}
		${r.ausgabe_silo ? `<p class="fehlt">Geht in ${esc(r.ausgabe_silo)}.</p>`
			: fertigware ? textFeld("scan", "Palette scannen (optional)") + `<div class="reihe"><button class="knopf" data-a="neue-palette">+ Neue Palette (Etikett drucken)</button></div>`
			: textFeld("scan", "Zielbehälter / Kiste scannen (optional)")}
		<div id="rezept-abw">${rezeptPanel()}</div>
		<div id="fefo">${fefoPanel()}</div>
		${pruefFelder(r.pruefungen, "ph")}
		<div class="reihe"><button class="knopf" data-a="zurueck-ansatz">← Zutaten</button><button class="knopf gruen" data-a="buchen">Buchen</button></div>`;
	aktionen(async (a, d) => {
		if (a === "einheit") { einheit = d.e; einheitSetzen(einheit); document.getElementById("einheit-text").textContent = einheit; return fokus("aus"); }
		if (a === "zurueck-ansatz") return ansatzZeigen();
		if (a === "fefo-grund") { ansatz.fefoGrund = d.e; document.getElementById("fefo").innerHTML = fefoPanel(); return; }
		if (a === "rezept-grund") { ansatz.rezeptGrund = d.e; document.getElementById("rezept-abw").innerHTML = rezeptPanel(); return; }
		if (a === "buchen") return ansatzBuchen(zaehlen ? einheit : null);
		if (a === "neue-palette") {
			try {
				const p = await api("palette_neu", { station: zustand.station, typ: "Lagerpalette" });
				document.getElementById("scan").value = p.nve;
				etikettDrucken(p.nve);
				meldung("gruen", "Neue Palette " + p.nve, "Etikett wird gedruckt.");
			} catch (e) { meldung("rot", e.message); }
			return;
		}
		beiAllgemein(a);
	});
	enter("aus", () => fokus(document.getElementById("scan") ? "scan" : "aus"));
	enter("scan", () => {});
	const vorschauLaden = () => api("vorschau", { station: zustand.station, ziel: r.artikel, zeilen: ansatz.zeilen.map((z) => ({ code: z.code, menge: z.menge })),
			kundenauftrag: ansatz.auftrag ? ansatz.auftrag.auftrag : null, mhd: ansatz.mhd || null })
			.then((v) => {
				const el = document.getElementById("vorschau");
				if (!el || !v || !(v.los || v.mhd)) return;
				el.innerHTML = `<div class="panel"><div class="fehlt" style="font-size:16px">Am Beuteldrucker einstellen</div>
					<div class="gross">${v.los ? "Los " + esc(v.los) : ""}${v.mhd ? " · MHD " + esc(v.mhd) : ""}</div>
					${v.mhd_gekuerzt ? `<div class="fehlt" style="font-size:16px">Gekürzt für Kunde/Auftrag, möglich wäre ${esc(v.mhd_voll)}</div>` : ""}
					${datumFeld("mhd-wahl", "MHD kürzen auf", { pflicht: true, abHeute: true, wert: ansatz.mhd || v.mhd_iso || "" })}
					<div class="reihe"><button class="knopf" id="mhd-setzen">MHD kürzen</button>${ansatz.mhd ? `<button class="knopf" id="mhd-weg">Volles MHD</button>` : ""}</div>
					${v.kennzeichen && v.kennzeichen.length ? `<div>${kennzeichenMarken(v.kennzeichen)}${v.oeko_nr ? ` <b>${esc(v.oeko_nr)}</b>` : ""}</div>` : ""}
					${v.los_vorhanden ? `<div class="fehlt" style="font-size:16px">Los von heute läuft schon, diese Ware kommt dazu.</div>` : ""}</div>` +
					(v.mhd_sinkt ? `<div class="meldung orange">MHD sinkt von ${esc(v.mhd_bisher)} auf ${esc(v.mhd)}: Drucker umstellen, gedruckte Beutel prüfen.</div>` : "");
				datumAnzeigen(document.getElementById("mhd-wahl"));
				document.getElementById("mhd-setzen").onclick = () => {
					try { ansatz.mhd = datumWert("mhd-wahl", "MHD"); } catch (e) { return meldung("rot", e.message); }
					vorschauLaden();
				};
				const weg = document.getElementById("mhd-weg");
				if (weg) weg.onclick = () => { ansatz.mhd = null; vorschauLaden(); };
			}).catch(() => {});
	if (fertigware) vorschauLaden();
	fokus("aus");
	setTimeout(() => { const f = document.getElementById("aus"); if (f) f.select(); }, 40);
}
async function ansatzBuchen(einheit) {
	if (rezeptAbweichungen().length && ansatz.rezept.rezept_pflicht && !ansatz.rezeptGrund) return meldung("rot", "Einwaage außerhalb der Toleranz.", "Bitte einen Grund wählen oder zurück und korrigieren.");
	if (fefoOffen().some((x) => x.z.fefo_pflicht) && !ansatz.fefoGrund) return meldung("rot", "Älteres MHD liegt im Lager.", "Bitte einen Grund wählen oder zurück und die ältere Charge scannen.");
	const knopf = app.querySelector('[data-a="buchen"]');
	if (knopf) { knopf.disabled = true; knopf.textContent = "Bucht …"; }
	const ziel = document.getElementById("scan");
	const wert = zahl(document.getElementById("aus").value);
	try {
		const e = await api("herstellen", {
			station: zustand.station,
			ziel: ansatz.rezept.artikel,
			zeilen: ansatz.zeilen.map((z) => ({ code: z.code, menge: z.menge })),
			ausbringung: einheit ? null : wert,
			anzahl: einheit ? wert : null,
			einheit,
			ziel_behaelter: ziel ? ziel.value.trim() || null : null,
			kundenauftrag: ansatz.auftrag ? ansatz.auftrag.auftrag : null,
			pruefwerte: pruefWerte(ansatz.rezept.pruefungen, "ph"),
			mhd: ansatz.mhd || null,
			fefo_grund: fefoOffen().length ? ansatz.fefoGrund : null,
			sollmenge: ansatz.rezept.rezept_pruefen ? ansatz.rezept.sollmenge : null,
			rezept_grund: rezeptAbweichungen().length ? ansatz.rezeptGrund || null : null,
		});
		const zeilen = [
			e.los ? "Los: " + e.los + (e.los !== e.charge ? " (" + e.charge + ")" : "") : "Neue Charge: " + e.charge,
			e.anzahl ? "Menge: " + stk(e.anzahl, ein(e.einheit)) + " (" + mg(e.menge, ansatz.rezept.einheit) + ")" : "Menge: " + mg(e.menge, ansatz.rezept.einheit),
			e.behaelter ? "Behälter: " + e.behaelter : "",
			e.palette ? "Auf Palette: " + e.palette : "",
			e.kundenauftrag ? "Kundenauftrag: " + e.kundenauftrag : "",
			e.mhd ? "Verwendbar bis / MHD: " + e.mhd : "",
			e.kennzeichen ? "Kennzeichen: " + e.kennzeichen : "",
			e.gesperrt ? "Gesperrt bis zur Freigabe durch die QS" : "",
		].filter(Boolean);
		const extra = e.palette ? `<button class="knopf" data-a="etikett">Paletten-Etikett drucken</button><button class="knopf" data-a="palette">Palette anzeigen</button>` : "";
		ergebnis(e.name, zeilen, e.hinweise, extra)((a) => {
			if (a === "etikett") return etikettNachdrucken(e.palette);
			if (a === "palette") return paletteLaden(e.palette);
			beiAllgemein(a);
		});
	} catch (err) {
		if (knopf) { knopf.disabled = false; knopf.textContent = "Buchen"; }
		meldung("rot", err.message);
	}
}
