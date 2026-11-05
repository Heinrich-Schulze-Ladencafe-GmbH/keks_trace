// Terminal: Linie mit Produktionsauftrag, Packstation, Verpackungs-PC, Palette fertig, Retour ins Lager.

import { api, app, ein, esc, fokus, kg, meldung, mg, rund, stk, ton, zahl, zustand } from "./basis.js";
import { einheitSetzen, einheitWahl, textFeld, zahlFeld } from "./tastatur.js";
import { aktionen, beiAllgemein, enter, ergebnis, etikettDrucken, etikettNachdrucken, kartonDrucken, kopf, tabelle, zahlText } from "./rahmen.js";
import { FEFO_GRUENDE, registrierungenLaden, schnellStart } from "./herstellen.js";

// ------------------------------------------------------------------ Linie: Produktionsaufträge
export async function auftragWaehlen(titel, weiter) {
	app.innerHTML = kopf(titel, true) + `<p>Für welchen Produktionsauftrag? Zeile antippen</p><div id="pa-liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		const liste = await api("linie_auftraege", { station: zustand.station });
		const el = document.getElementById("pa-liste");
		if (!liste.length) { el.innerHTML = `<p class="fehlt">Kein freigegebener Auftrag für heute. Die Produktionsleitung gibt den Tagesplan frei.</p>`; return; }
		el.innerHTML = tabelle([["Auftrag", "name"], ["Artikel", "artikel"], ["Bezeichnung", "artikelname"], ["Kunde", "kundenname"], ["Tag", "datum_text"],
			["Bestellt", "menge_text", 1], ["Gebucht", "gebucht_text", 1], ["Anlage", "verpackungsanlage"], ["Status", (a) => (a.aktuell ? "▶ " : "") + a.status],
			...(liste.some((a) => a.hinweis) ? [["Hinweis", (a) => a.hinweis || ""]] : [])], liste, "pa");
		aktionen(async (a, d) => {
			if (a !== "pa") return beiAllgemein(a);
			try { await api("linie_waehlen", { station: zustand.station, auftrag: liste[+d.i].name }); weiter(); } catch (e) { meldung("rot", e.message); }
		});
	} catch (e) { meldung("rot", e.message); }
}
export function hinweisHtml(liste) {
	return (liste || []).filter((h) => h && h.text).map((h) => `<div class="hinweis-buero"><small>Hinweis ${esc(h.von || "")}</small>${esc(h.text)}</div>`).join("");
}
export function auftragKopf(i) {
	return hinweisHtml(i.hinweise) + tabelle([["Auftrag", "auftrag"], ["Bezeichnung", "name"], ["Kunde", (x) => x.kunde || ""], ["Anlage", (x) => x.verpackungsanlage || ""],
		["Bestellt", "menge_text", 1], ["Gebucht", "gebucht_text", 1]], [i]) + `<div style="text-align:right;margin-top:-8px"><button class="link" data-a="pa-wechseln">Auftrag wechseln</button></div>`;
}
// An die Linie: Kübel einkippen (Former), Gebinde nachfüllen
export async function linieStart() {
	let i;
	try { i = await api("linie_info", { station: zustand.station }); } catch (e) { return meldung("rot", e.message); }
	if (!i || !i.auftrag || i.status !== "Läuft") return auftragWaehlen("An die Linie", linieStart);
	const zutaten = i.zutaten.filter((z) => z.stufe !== "Packmittel").map((z) => `<div class="zeile"><div>${esc(z.name)}</div>
		<div class="rechts ${z.auf_linie > 0 ? "ok" : "fehlt"}">${esc(mg(z.auf_linie, z.einheit))} auf der Linie${z.reicht_fuer != null ? " · reicht für " + esc(mg(z.reicht_fuer, i.lagereinheit)) : ""}</div></div>`).join("");
	const kuebel = i.kuebel.length ? `<div class="panel"><div class="fehlt" style="font-size:16px">Nächste Kübel (ältester zuerst)</div>
		<div class="gross">${i.kuebel.map((k) => esc(k.code)).join(" · ")}</div>
		<div class="fehlt" style="font-size:16px">${i.kuebel.map((k) => esc(k.code + ": " + k.name + (k.datum ? " vom " + k.datum : "") + ", " + kg(k.menge))).join("<br>")}</div></div>` : "";
	app.innerHTML = kopf("An die Linie", true) + auftragKopf(i) + kuebel + `<div class="panel">${zutaten}</div>` +
		textFeld("scan", "Kübel, Gebinde oder Tank scannen") +
		zahlFeld("menge", "Menge (leer = ganzer Kübel)") +
		`<div class="reihe"><button class="knopf" data-a="retour">Retour ins Lager<small>Unbenutztes von der Linie zurück, z. B. halber Sack</small></button></div>`;
	aktionen((a) => {
		if (a === "pa-wechseln") return auftragWaehlen("An die Linie", linieStart);
		if (a === "retour") return retourStart(linieStart);
		beiAllgemein(a);
	});
	const zufuehren = async (code, menge, fefoGrund) => {
		try {
			const r = await api("linie_zufuehren", { station: zustand.station, code, menge, fefo_grund: fefoGrund || null });
			await linieStart();
			meldung("gruen", "Zugeführt: " + r.name + " " + mg(r.menge, r.einheit), (r.behaelter ? r.behaelter + " · " : "") + "Charge " + r.chargen.join(", "));
			ton(true);
			(r.hinweise || []).forEach((h) => app.querySelector("#meldung").insertAdjacentHTML("beforeend", `<div class="meldung orange">${esc(h)}</div>`));
		} catch (e) { meldung("rot", e.message); const f = document.getElementById("scan"); if (f) f.value = ""; }
	};
	enter("scan", async (code) => {
		if (!code) return;
		const menge = zahl(document.getElementById("menge").value) || null;
		// FEFO: ältere Charge im Lager? Dann Grund wählen (Pflicht laut Einstellung), sonst direkt zuführen
		let f = { aeltere: [] };
		try { f = await api("fefo_pruefen", { station: zustand.station, code }); } catch (e) { /* Fehler meldet das Zuführen */ }
		if (!f.aeltere.length) return zufuehren(code, menge, null);
		app.insertAdjacentHTML("beforeend", `<div class="panel" id="fefo-frage"><div class="meldung orange">Älteres MHD liegt im Lager<small>${esc(f.name + ": gescannt " + f.charge + ", älter " +
			f.aeltere.map((a) => a.charge + " (MHD " + a.mhd + ", " + mg(a.menge, "Kg") + ")").join(", "))}</small></div>
			<label>Besser die ältere Charge holen. Sonst Grund${f.pflicht ? "" : " (freiwillig)"}:</label>
			<div class="einheiten">${FEFO_GRUENDE.map((g) => `<button type="button" data-g="${esc(g)}">${esc(g)}</button>`).join("")}</div>
			<div class="reihe"><button class="knopf" data-g="">Abbrechen</button>${f.pflicht ? "" : `<button class="knopf" data-g="-">Ohne Grund zuführen</button>`}</div></div>`);
		const frage = document.getElementById("fefo-frage");
		frage.scrollIntoView({ block: "nearest" });
		frage.addEventListener("click", (ev) => {
			const b = ev.target.closest("[data-g]");
			if (!b) return;
			frage.remove();
			if (b.dataset.g === "") { document.getElementById("scan").value = ""; return fokus("scan"); }
			zufuehren(code, menge, b.dataset.g === "-" ? null : b.dataset.g);
		});
	});
	fokus("scan");
}
// Packstation: nur anzeigen, Kartonlabel drucken
export async function packstationStart() {
	let d;
	try { d = await api("packstation", { station: zustand.station }); } catch (e) { return meldung("rot", e.message); }
	if (!d || !d.auftrag) return auftragWaehlen("Packstation", packstationStart);
	app.innerHTML = kopf("Packstation", true) + auftragKopf(d) + `
		<div class="panel"><div class="zeile"><div>Verpackungsanlage</div><div class="rechts gross">${esc(d.verpackungsanlage || "–")}</div></div>
		<div class="zeile"><div>Beutel je Karton</div><div class="rechts gross">${esc(d.beutel_je_karton || "–")}</div></div>
		<div class="zeile"><div>Los</div><div class="rechts gross">${esc(d.los_vorschau || "–")}</div></div>
		<div class="zeile"><div>MHD</div><div class="rechts gross">${esc(d.mhd_vorschau || "–")}</div></div>
		<div class="zeile"><div>Noch offen</div><div class="rechts">${esc(d.offen_text)}</div></div></div>` +
		zahlFeld("anzahl", "Wie viele Kartonlabel?", 20) +
		`<div class="reihe"><button class="knopf gruen" data-a="label">Kartonlabel drucken</button><button class="knopf" data-a="neu">Aktualisieren</button></div>`;
	aktionen((a) => {
		if (a === "pa-wechseln") return auftragWaehlen("Packstation", packstationStart);
		if (a === "neu") return packstationStart();
		if (a === "label") return kartonDrucken(Math.max(1, Math.round(zahl(document.getElementById("anzahl").value))));
		beiAllgemein(a);
	});
}
// ------------------------------------------------------------------ Verpackungs-PC an der Linie
// Zeigt den Verpackungsauftrag (Spezifikation, Anlage, Beutel je Karton, Los, MHD) und bucht, was wirklich
// verpackt wurde: Karton auf eine Palette (jede Palette hat eine NVE) und lose Ware in Kisten. Beliebig oft.
export async function vpcStart(hinweis) {
	let d;
	try { d = await api("packstation", { station: zustand.station }); } catch (e) { return meldung("rot", e.message); }
	if (!d || !d.auftrag || d.status !== "Läuft") return auftragWaehlen("Verpacken", vpcStart);
	const spez = d.spezifikation ? (/^https?:/.test(d.spezifikation)
		? `<a href="${esc(d.spezifikation)}" target="_blank" rel="noopener">Spezifikation öffnen</a>` : esc(d.spezifikation)) : "–";
	app.innerHTML = kopf("Verpacken: " + d.name, true) + auftragKopf(d) + `
		<div class="position"><div class="titel"><b>Verpackungsauftrag</b><span>${d.kunde ? esc(d.kunde) : "Lager"}</span></div>
			<div class="wert">Los<div>${esc(d.los_vorschau || "–")}</div></div>
			<div class="wert">MHD<div style="font-size:34px">${esc(d.mhd_vorschau || "–")}</div></div>
			<div class="wert">Anlage<div style="font-size:30px">${esc(d.verpackungsanlage || "–")}</div></div>
			<div class="wert">Beutel je Karton<div>${esc(d.beutel_je_karton || "–")}</div></div>
			<div class="wert">Karton je Palette<div>${esc(d.karton_je_palette || "–")}</div></div>
			<div class="wert">Spezifikation<div style="font-size:20px">${spez}</div></div></div>
		${linienlagerPanel(d)}
		<div class="reihe"><button class="knopf gruen" data-a="karton">Karton auf Palette buchen<small>gebucht bisher ${esc(d.gebucht_text)} von ${esc(d.menge_text)}</small></button>
			${d.lose_artikel ? `<button class="knopf blau" data-a="lose">Lose Ware buchen<small>${esc(d.lose_name)} im ${esc(ein(d.lose_einheit))} ins Lager oder Linienlager</small></button>` : ""}</div>
		<div class="reihe"><button class="knopf" data-a="label">Kartonetiketten drucken</button><button class="knopf" data-a="beenden">Auftrag beenden</button></div>
		<div class="reiter"><button class="an" type="button">Registrierungen</button></div><div class="panel" style="margin-top:0" id="registrierungen">Lädt …</div>`;
	if (hinweis) meldung("gruen", hinweis);
	registrierungenLaden({ produktionsauftrag: d.auftrag });
	aktionen(async (a) => {
		if (a === "pa-wechseln") return auftragWaehlen("Verpacken", vpcStart);
		if (a === "karton") return paletteFertigStart(vpcStart);
		if (a === "lose") return loseBuchen(d);
		if (a === "linienlager-verpacken") return schnellStart(true);
		if (a === "label") return kartonDrucken(d.karton_je_palette || 20);
		if (a === "beenden") { const i = await api("linie_info", { station: zustand.station }); return auftragBeenden(i); }
		beiAllgemein(a);
	});
}
// Was im Linienlager auf die Verpackung wartet (Wannen werden nicht gebucht)
function linienlagerPanel(d) {
	if (!d.linienlager) return "";
	const l = d.im_linienlager || [];
	if (!l.length) return `<div class="panel"><b>Linienlager</b> <span class="fehlt">leer · Wannen sind nicht gebucht, bitte heute noch leer fahren</span></div>`;
	return `<div class="panel"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><b>Linienlager: wartet auf die Verpackung</b>
		<button class="knopf blau" style="min-height:0;padding:10px 18px" data-a="linienlager-verpacken">Jetzt verpacken</button></div>
		${l.map((z) => `<div class="zeile"><div>${esc(z.name)} · ${esc(z.charge)}</div><div class="rechts ${z.alt ? "fehlt" : ""}">${esc(z.menge_text)} · seit ${esc(z.seit)}</div></div>`).join("")}</div>`;
}
// Lose Ware vom laufenden Auftrag: Kartons (kg je Karton fest) ins Lager auf Palette (F5) oder ins Linienlager (F6)
async function loseBuchen(d) {
	let ziel = "lager";
	const je = d.lose_je_einheit && d.lose_einheit !== "Kg" ? ` (${zahlText(d.lose_je_einheit)} kg je ${esc(ein(d.lose_einheit))})` : "";
	app.innerHTML = kopf("Lose Ware: " + d.lose_name, true) + auftragKopf(d) +
		`<div class="einheiten" id="ziele"><button type="button" class="an" data-a="ziel" data-z="lager">Ins Lager<small> parallel abgenommen</small></button>` +
		(d.linienlager ? `<button type="button" data-a="ziel" data-z="linienlager">Ins Linienlager<small> Verpackung kommt nicht nach</small></button>` : "") + `</div>` +
		zahlFeld("anzahl", `Wie viele ${esc(ein(d.lose_einheit || "Kg"))}?${je}`) +
		`<div id="pal-feld">${textFeld("scan", "Palette scannen (leer = neue Palette)")}</div>` +
		`<div class="reihe"><button class="knopf" data-a="zurueck-vpc">← Zurück</button><button class="knopf gruen" data-a="buchen">Buchen</button></div>`;
	aktionen(async (a, x) => {
		if (a === "zurueck-vpc") return vpcStart();
		if (a === "ziel") {
			ziel = x.z;
			app.querySelectorAll("#ziele button").forEach((b) => b.classList.toggle("an", b.dataset.z === ziel));
			document.getElementById("pal-feld").hidden = ziel !== "lager";
			return fokus("anzahl");
		}
		if (a !== "buchen") return beiAllgemein(a);
		const knopf = app.querySelector('[data-a="buchen"]');
		knopf.disabled = true; knopf.textContent = "Bucht …";
		try {
			let palette = null;
			if (ziel === "lager") {
				palette = document.getElementById("scan").value.trim();
				if (!palette) palette = (await api("palette_neu", { station: zustand.station, typ: "Lagerpalette" })).nve;
			}
			const e = await api("linie_lose", { station: zustand.station, anzahl: zahl(document.getElementById("anzahl").value), einheit: d.lose_einheit, ziel, palette });
			if (e.palette) etikettDrucken(e.palette);
			ergebnis(e.name, ["Charge: " + e.charge, "Menge: " + stk(e.anzahl, ein(e.einheit)) + (e.einheit !== "Kg" ? " (" + kg(e.menge) + ")" : ""),
				e.ziel === "linienlager" ? "Ins Linienlager, wird später verpackt" : "Ins Lager" + (e.palette ? " auf Palette " + e.palette : ""),
				e.mhd ? "Verwendbar bis: " + e.mhd : "", e.gesperrt ? "Gesperrt bis zur Freigabe durch die QS" : "",
				"Verbraucht: " + e.verbraucht.map((v) => v.name + " " + v.charge).join(", ")].filter(Boolean),
				e.hinweise, `<button class="knopf gruen" data-a="weiter">Zurück zum Auftrag</button>`)((b) => (b === "weiter" ? vpcStart() : beiAllgemein(b)));
		} catch (err) { knopf.disabled = false; knopf.textContent = "Buchen"; meldung("rot", err.message); }
	});
	const buchen = () => app.querySelector('[data-a="buchen"]').click();
	enter("anzahl", () => (ziel === "lager" ? fokus("scan") : buchen()));
	enter("scan", buchen);
	fokus("anzahl");
}
// Palette fertig: Kartons zählen, buchen
export async function paletteFertigStart(zurueckZu) {
	const zurueck = typeof zurueckZu === "function" ? zurueckZu : null;
	let i;
	try { i = await api("linie_info", { station: zustand.station }); } catch (e) { return meldung("rot", e.message); }
	if (!i || !i.auftrag || i.status !== "Läuft") return auftragWaehlen("Palette fertig", zurueck || paletteFertigStart);
	const einheiten = (i.einheiten || []).filter((e) => e.einheit !== "Palette" && e.einheit !== "Lage");
	let einheit = (einheiten.find((e) => e.einheit === "Karton") || einheiten[0] || { einheit: "Kg" }).einheit;
	app.innerHTML = kopf(zurueck ? "Karton auf Palette" : "Palette fertig", true) + auftragKopf(i) + einheitWahl(einheiten, einheit, i.lagereinheit) +
		zahlFeld("anzahl", `Wie viele <span id="einheit-text">${esc(einheit)}</span> auf der Palette?`) +
		textFeld("scan", "Palette scannen (leer = neue Palette)") +
		`<div class="reihe"><button class="knopf gruen" data-a="buchen">Buchen</button><button class="knopf" data-a="beenden">Auftrag beenden</button></div>`;
	aktionen(async (a, d) => {
		if (a === "pa-wechseln") return auftragWaehlen("Palette fertig", zurueck || paletteFertigStart);
		if (a === "zurueck" && zurueck) return zurueck();
		if (a === "einheit") { einheit = d.e; einheitSetzen(einheit); document.getElementById("einheit-text").textContent = einheit; return fokus("anzahl"); }
		if (a === "beenden") return auftragBeenden(i);
		if (a !== "buchen") return beiAllgemein(a);
		const knopf = app.querySelector('[data-a="buchen"]');
		knopf.disabled = true; knopf.textContent = "Bucht …";
		try {
			let palette = document.getElementById("scan").value.trim();
			if (!palette) palette = (await api("palette_neu", { station: zustand.station, typ: "Lagerpalette" })).nve;
			const e = await api("linie_palette", { station: zustand.station, anzahl: zahl(document.getElementById("anzahl").value), einheit, palette });
			etikettDrucken(e.palette);
			ergebnis(e.name, [
				"Los: " + e.los, "Menge: " + stk(e.anzahl, ein(e.einheit)) + (e.einheit !== i.lagereinheit ? " (" + mg(e.menge, i.lagereinheit) + ")" : ""), "Palette: " + e.palette,
				e.mhd ? "MHD: " + e.mhd : "", e.kennzeichen ? "Kennzeichen: " + e.kennzeichen : "",
				"Auftrag gesamt: " + e.gebucht_text, "Verbraucht: " + e.verbraucht.map((v) => v.name + " " + v.charge).join(", "),
			].filter(Boolean), e.hinweise, `<button class="knopf" data-a="etikett">Palettenlabel nochmal</button><button class="knopf" data-a="weiter">Nächste Palette</button>`)((a2) => {
				if (a2 === "etikett") return etikettNachdrucken(e.palette);
				if (a2 === "weiter") return zurueck ? zurueck() : paletteFertigStart();
				beiAllgemein(a2);
			});
		} catch (err) { knopf.disabled = false; knopf.textContent = "Buchen"; meldung("rot", err.message); }
	});
	fokus("anzahl");
}
function auftragBeenden(i) {
	const rest = i.zutaten.filter((z) => z.auf_linie > 0);
	app.innerHTML = kopf("Auftrag beenden", true) + auftragKopf(i) +
		(rest.length ? `<div class="panel"><div class="fehlt" style="font-size:16px">Rest auf der Linie wird als Linienrest ausgebucht (Bruch, Biogas). Wannen vorher leer verpacken!</div>${rest.map((z) => `<div class="zeile"><div>${esc(z.name)}</div><div class="rechts">${esc(mg(z.auf_linie, z.einheit))}</div></div>`).join("")}</div>` : `<p>Nichts mehr auf der Linie.</p>`) +
		(rest.length ? `<div class="reihe"><button class="knopf blau" data-a="retour">Erst Unbenutztes zurück ins Lager<small>Retour: Säcke, Gebinde, Packmittel</small></button></div>` : "") +
		`<div class="reihe"><button class="knopf" data-a="zurueck-pf">← Zurück</button><button class="knopf gruen" data-a="ja">Auftrag beenden</button></div>`;
	aktionen(async (a) => {
		if (a === "zurueck-pf") return paletteFertigStart();
		if (a === "retour") return retourStart(async () => auftragBeenden(await api("linie_info", { station: zustand.station })));
		if (a !== "ja") return beiAllgemein(a);
		try {
			const r = await api("linie_beenden", { station: zustand.station, auftrag: i.auftrag });
			ergebnis(i.name, ["Auftrag " + r.auftrag + " beendet", ...r.rest.map((z) => "Linienrest: " + z.name + " " + z.charge + " " + rund(z.menge))], [])(beiAllgemein);
		} catch (e) { meldung("rot", e.message); }
	});
}
// ------------------------------------------------------------------ Retour von der Linie
// Was an die Linie gegeben, aber nicht verbraucht wurde, geht zurück in das Lager, aus dem es kam. Sonst würde
// es beim Auftragsende als Linienrest ausgebucht und Bestand und Mengenbilanz stimmten nicht.
async function retourStart(zurueck, hinweis) {
	app.innerHTML = kopf("Retour ins Lager", true) + `<div id="retour">Lädt …</div>`;
	aktionen((a) => (a === "zurueck" ? zurueck() : beiAllgemein(a)));
	if (hinweis) meldung("gruen", hinweis);
	let liste;
	try { liste = await api("linie_retour_liste", { station: zustand.station }); } catch (e) { return meldung("rot", e.message); }
	const el = document.getElementById("retour");
	if (!liste.length) { el.innerHTML = `<p class="fehlt">Auf der Linie liegen keine Rohstoffe oder Packmittel dieses Auftrags.</p>`; return; }
	el.innerHTML = `<p>Was geht zurück? Zeile antippen</p>` + tabelle([["Artikel", "name"], ["Charge", "charge"], ["Auf der Linie", (z) => mg(z.menge, z.einheit), 1],
		["Zurück nach", (z) => z.silo ? "– (aus dem Silo)" : z.ziel_name || "–"]], liste, "zeile");
	aktionen((a, d) => {
		if (a === "zurueck") return zurueck();
		if (a !== "zeile") return beiAllgemein(a);
		const z = liste[+d.i];
		if (z.silo || !z.ziel) return meldung("orange", z.name + " kam aus dem Silo und kann nicht zurück.");
		retourMenge(z, zurueck);
	});
}
function retourMenge(z, zurueck) {
	app.innerHTML = kopf("Retour: " + z.name, true) +
		`<div class="panel"><div class="zeile"><div>Charge</div><div class="rechts">${esc(z.charge)}</div></div>
		<div class="zeile"><div>Auf der Linie</div><div class="rechts">${esc(mg(z.menge, z.einheit))}</div></div>
		<div class="zeile"><div>Zurück nach</div><div class="rechts">${esc(z.ziel_name)}</div></div></div>` +
		zahlFeld("menge", `Wie viel geht zurück (${esc(ein(z.einheit))})?`, z.menge) +
		`<div class="reihe"><button class="knopf" data-a="zur-liste">← Liste</button><button class="knopf gruen" data-a="buchen">Zurück ins Lager buchen</button></div>`;
	const buchen = async () => {
		try {
			const r = await api("linie_rueckgabe", { station: zustand.station, charge: z.charge, menge: zahl(document.getElementById("menge").value) });
			ton(true);
			retourStart(zurueck, "Zurück ins Lager: " + r.name + " " + mg(r.menge, r.einheit) + " nach " + r.ziel);
		} catch (e) { meldung("rot", e.message); }
	};
	aktionen((a) => {
		if (a === "zur-liste" || a === "zurueck") return retourStart(zurueck);
		if (a === "buchen") return buchen();
		beiAllgemein(a);
	});
	enter("menge", buchen);
	fokus("menge");
}
