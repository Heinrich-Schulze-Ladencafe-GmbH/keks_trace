// Terminal: Paletten und Versandkartons.

import { api, app, esc, fokus, kg, meldung, stk, zustand } from "./basis.js";
import { textFeld } from "./tastatur.js";
import { aktionen, anzahlAbfragen, beiAllgemein, enter, etikettDrucken, etikettNachdrucken, kopf, suchListe, zahlText } from "./rahmen.js";

// Paletten-Terminal: Palette eingewickelt → abschließen, NVE-Etikett, versandbereit
export async function einwickelnStart(hinweis) {
	app.innerHTML = kopf("Palette einwickeln", true) + textFeld("scan", "Palette scannen (NVE) – oder unten antippen") + `<div id="pal">Lädt …</div>`;
	if (hinweis) meldung("gruen", hinweis);
	aktionen(beiAllgemein);
	const fertig = async (nve) => {
		try {
			const p = await api("palette_versandbereit", { station: zustand.station, palette: nve });
			etikettDrucken(p.nve);
			einwickelnStart("Palette " + p.nve + " versandbereit, Etikett wird gedruckt.");
		} catch (e) { meldung("rot", e.message); }
	};
	enter("scan", (v) => v && fertig(v));
	fokus("scan");
	try {
		const liste = await api("offene_paletten", { station: zustand.station });
		suchListe("pal", [["NVE", (p) => "…" + p.nve.slice(-6)], ["Art", "typ"], ["Inhalt", "inhalt"], ["Lose", "lose"], ["Kunde", (p) => p.kunde || ""]],
			liste, (p) => fertig(p.nve), "Suchen: NVE, Los, Inhalt …");
	} catch (e) { meldung("rot", e.message); }
}
// ------------------------------------------------------------------ Paletten
export function palettenStart() {
	app.innerHTML = kopf("Paletten", true) + textFeld("scan", "Palette scannen (NVE)") + `
		<div class="raster" style="margin-top:16px">
			<button class="knopf blau" data-a="neu" data-typ="Lagerpalette">+ Neue Lagerpalette<small>für die Verpackung</small></button>
			<button class="knopf blau" data-a="neu" data-typ="Versandpalette">+ Neue Versandpalette<small>zum Kommissionieren</small></button>
			<button class="knopf blau" data-a="neu" data-typ="Versandkarton">+ Neuer Versandkarton<small>eigene NVE, auch auf eine Palette</small></button>
		</div>`;
	aktionen(async (a, d) => {
		if (a === "neu") {
			try {
				const p = await api("palette_neu", { station: zustand.station, typ: d.typ });
				etikettDrucken(p.nve);
				paletteZeigen(p, "Neue " + p.art + " angelegt, Etikett wird gedruckt.");
			} catch (e) { meldung("rot", e.message); }
			return;
		}
		beiAllgemein(a);
	});
	enter("scan", (v) => v && paletteLaden(v));
	fokus("scan");
}
export async function paletteLaden(code, hinweis) {
	try { paletteZeigen(await api("palette_info", { code }), hinweis); } catch (e) { meldung("rot", e.message); }
}
export function statusMarke(s) {
	const farbe = { Offen: "gruen", Geschlossen: "", Versendet: "orange", Leer: "" }[s] || "";
	return `<span class="marke ${farbe}">${esc(s)}</span>`;
}
// Versandkartons (eigene NVE) auf einer Palette; aktion = Knopf je Karton (z. B. abnehmen)
export function kartonListeHtml(p, aktion) {
	const k = p.versandkartons || [];
	if (!k.length) return "";
	return `<div class="panel"><div class="fehlt" style="font-size:16px">Versandkartons auf der Palette (${k.length})</div>${k.map((x, i) => `<div class="zeile">
		<div>Versandkarton …${esc(x.nve.slice(-6))}<br><small class="fehlt">${esc(x.nve)} · ${esc(x.inhalt)}</small></div>
		<div class="rechts">${esc(kg(x.menge))}${aktion ? ` <button class="knopf klein" data-a="${aktion}" data-i="${i}">abnehmen</button>` : ""}</div></div>`).join("")}</div>`;
}
export function hatInhalt(p) { return !!(p.positionen.length || (p.versandkartons || []).length); }
export function positionenHtml(p, aktion) {
	if (!p.positionen.length) return (p.versandkartons || []).length ? "" : `<p class="fehlt">${p.versandkarton ? "Versandkarton" : "Palette"} ist leer.</p>`;
	return p.positionen.map((x, i) => `<button class="pos" ${aktion ? `data-a="${aktion}" data-i="${i}"` : "disabled"}>
		<span>${esc(x.name)}<small>Los ${esc(x.los || x.charge)}${x.mhd ? " · MHD " + esc(x.mhd) : ""}${x.gesperrt ? " · GESPERRT" : ""}</small></span>
		<span class="rechts">${esc(stk(x.anzahl, x.einheit))}<small>${esc(kg(x.menge))}</small></span></button>`).join("");
}
function paletteZeigen(p, hinweis) {
	const aktiv = p.status === "Offen" || p.status === "Geschlossen" || p.status === "Leer";
	const vk = p.versandkarton;
	app.innerHTML = kopf(vk ? "Versandkarton" : "Palette", true) + `
		<div class="panel"><div class="nve">${esc(p.nve.slice(0, -6))}<span style="color:#6ea0ff">${esc(p.nve.slice(-6))}</span> ${statusMarke(p.status)}
			<br><small>${esc(p.art)}${p.kartons ? " · " + esc(p.kartons) : ""}${p.menge ? " · " + esc(kg(p.menge)) : ""}${p.lieferschein ? " · Lieferschein " + esc(p.lieferschein) : ""}</small></div>
			${p.fuellung ? `<div style="margin-top:10px"><div style="height:14px;background:var(--panel2);border-radius:7px;overflow:hidden"><div style="height:100%;width:${Math.min(100, Math.round(p.fuellung.anteil * 100))}%;background:${p.fuellung.ueber ? "var(--rot)" : p.fuellung.voll ? "var(--gruen)" : "var(--blau)"}"></div></div>
				<div class="fehlt" style="font-size:16px;margin-top:4px">${p.fuellung.ueber ? "ÜBERLADEN · " : p.fuellung.voll ? "VOLL · " : ""}${esc(p.fuellung.text || Math.round(p.fuellung.anteil * 100) + " % voll")}</div></div>` : ""}
			${p.test ? `<div class="meldung orange">Test-NVE: Etikett nicht an Kunden geben (GS1-Basisnummer fehlt in den Einstellungen).</div>` : ""}
			${vk && p.auf_palette ? `<div class="meldung">Steht auf Palette …${esc(p.auf_palette.slice(-6))}<small>${esc(p.auf_palette)}</small></div>` : ""}
			${p.gewicht_kg || p.sendungsnummer ? `<div class="fehlt" style="font-size:16px;margin-top:6px">Paket: ${esc([p.gewicht_kg ? zahlText(p.gewicht_kg) + " kg" : "", p.sendungsnummer || ""].filter(Boolean).join(" · "))}</div>` : ""}
			${p.etikett_aktuell === false && hatInhalt(p) ? (p.status === "Offen"
				? `<div class="meldung">Etikett zeigt noch nicht den ganzen Inhalt<small>Nach dem Beladen mit Inhalt drucken.</small></div>`
				: `<div class="meldung orange">Etikett passt nicht mehr zum Inhalt<small>Neu drucken und das alte überkleben, nicht von Hand korrigieren.</small></div>`) : ""}
		</div>
		${aktiv && p.positionen.length ? `<p class="fehlt">Position antippen, um Kartons auf eine andere Palette umzupacken.</p>` : ""}
		${positionenHtml(p, aktiv ? "pos" : null)}
		${kartonListeHtml(p, aktiv ? "karton-ab" : null)}
		<div class="reihe">
			${aktiv ? `<button class="knopf blau" data-a="laden">+ Lose Kartons laden<small>${vk ? "Los scannen" : "Los oder Versandkarton scannen"}</small></button>` : ""}
			${aktiv && vk && p.positionen.length ? (p.auf_palette
				? `<button class="knopf" data-a="vom-stapel">Von der Palette nehmen<small>bleibt im Lager</small></button>`
				: `<button class="knopf" data-a="auf-palette">Auf eine Palette stellen<small>Palette scannen</small></button>`) : ""}
			<button class="knopf ${p.etikett_aktuell === false && hatInhalt(p) ? "gruen" : ""}" data-a="etikett">${p.etikett_aktuell === false ? "Etikett neu drucken" : "Etikett drucken"}</button>
			${p.status === "Offen" ? `<button class="knopf" data-a="schliessen">${vk ? "Karton" : "Palette"} schließen</button>` : ""}
			${p.status === "Geschlossen" ? `<button class="knopf" data-a="oeffnen">Wieder öffnen</button>` : ""}
		</div>`;
	if (hinweis) meldung("gruen", hinweis);
	aktionen(async (a, d) => {
		try {
			if (a === "etikett") { if (await etikettNachdrucken(p.nve)) paletteLaden(p.nve); return; }
			if (a === "schliessen") return paletteZeigen(await api("palette_schliessen", { station: zustand.station, palette: p.nve }), "Palette geschlossen.");
			if (a === "oeffnen") return paletteZeigen(await api("palette_oeffnen", { station: zustand.station, palette: p.nve }), "Palette geöffnet.");
			if (a === "laden") return kartonsLaden(p);
			if (a === "pos") return umpacken(p, p.positionen[+d.i]);
			if (a === "karton-ab") return paletteZeigen(await api("karton_abnehmen", { station: zustand.station, karton: p.versandkartons[+d.i].nve }), "Versandkarton heruntergenommen.");
			if (a === "vom-stapel") { await api("karton_abnehmen", { station: zustand.station, karton: p.nve }); return paletteLaden(p.nve, "Von der Palette genommen."); }
			if (a === "auf-palette") return kartonAufPalette(p);
		} catch (e) { return meldung("rot", e.message); }
		if (a === "zurueck") return palettenStart();
		beiAllgemein(a);
	});
}
function kartonsLaden(p) {
	app.innerHTML = kopf("Auf Palette …" + p.nve.slice(-6), true) + textFeld("scan", "Los scannen (Etikett am Karton)");
	aktionen((a) => (a === "zurueck" ? paletteZeigen(p) : beiAllgemein(a)));
	enter("scan", async (v) => {
		if (!v) return;
		try {
			const i = await api("info", { code: v });
			if (i.typ === "palette" && i.versandkarton && !p.versandkarton) {
				return paletteZeigen(await api("karton_auf_palette", { station: zustand.station, karton: i.nve, palette: p.nve }), "Versandkarton …" + i.nve.slice(-6) + " aufgestellt.");
			}
			if (i.typ !== "charge") throw new Error("Bitte das Los scannen, nicht " + (i.typ === "palette" ? (p.versandkarton ? "eine Palette" : "eine Palette (nur Versandkartons kommen auf eine Palette)") : "einen Behälter") + ".");
			const einheiten = await api("einheiten", { artikel: i.artikel });
			anzahlAbfragen("Los " + i.charge, esc(i.artikelname) + (i.mhd ? " · MHD " + esc(i.mhd) : ""), einheiten, null, async (n, e) => {
				try {
					paletteZeigen(await api("palette_beladen", { station: zustand.station, palette: p.nve, code: i.charge, anzahl: n, einheit: e }), stk(n, e) + " geladen.");
				} catch (err) { meldung("rot", err.message); }
			}, () => paletteZeigen(p));
		} catch (e) { meldung("rot", e.message); }
	});
	fokus("scan");
}
// Versandkarton auf eine Palette stellen: Palette scannen oder neue anlegen
function kartonAufPalette(k) {
	app.innerHTML = kopf("Versandkarton …" + k.nve.slice(-6) + " aufstellen", true) + textFeld("scan", "Palette scannen (NVE)") +
		`<div class="reihe"><button class="knopf blau" data-a="neu">+ Neue Versandpalette<small>Etikett wird gedruckt</small></button></div>`;
	const los = async (palette) => {
		try { paletteZeigen(await api("karton_auf_palette", { station: zustand.station, karton: k.nve, palette }), "Versandkarton aufgestellt."); }
		catch (e) { meldung("rot", e.message); }
	};
	aktionen(async (a) => {
		if (a === "zurueck") return paletteZeigen(k);
		if (a === "neu") {
			try { const p = await api("palette_neu", { station: zustand.station, typ: "Versandpalette" }); etikettDrucken(p.nve); return los(p.nve); }
			catch (e) { return meldung("rot", e.message); }
		}
		beiAllgemein(a);
	});
	enter("scan", (v) => v && los(v));
	fokus("scan");
}
function umpacken(p, pos) {
	anzahlAbfragen("Umpacken", `${esc(pos.name)} · Los ${esc(pos.charge)}<br><span class="fehlt">Auf der Palette: ${esc(stk(pos.anzahl, pos.einheit))}</span>`,
		[{ einheit: pos.einheit, faktor: 1 }], { einheit: pos.einheit, anzahl: pos.anzahl }, (n) => {
			app.innerHTML = kopf("Umpacken: " + stk(n, pos.einheit), true) + textFeld("scan", "Zielpalette scannen") +
				`<div class="reihe"><button class="knopf blau" data-a="neu">+ Neue Versandpalette</button></div>`;
			const los = async (nach) => {
				try {
					const ziel = await api("palette_umpacken", { station: zustand.station, von: p.nve, nach, charge: pos.charge, anzahl: n, einheit: pos.einheit });
					paletteZeigen(ziel, stk(n, pos.einheit) + " umgepackt." + (ziel.hinweise && ziel.hinweise.length ? " " + ziel.hinweise.join(" ") : ""));
				} catch (e) { meldung("rot", e.message); }
			};
			aktionen(async (a) => {
				if (a === "neu") {
					try {
						const neu = await api("palette_neu", { station: zustand.station, typ: "Versandpalette" });
						etikettDrucken(neu.nve);
						return los(neu.nve);
					} catch (e) { return meldung("rot", e.message); }
				}
				if (a === "zurueck") return paletteZeigen(p);
				beiAllgemein(a);
			});
			enter("scan", (v) => v && los(v));
			fokus("scan");
		}, () => paletteZeigen(p));
}
