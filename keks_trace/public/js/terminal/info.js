// Terminal: Info-Scan, Akte, Herkunft.
/* global KtAkte */ // aus /assets/keks_trace/js/akte_ansicht.js (klassisches Skript)

import { api, app, esc, fokus, kg, meldung, ton, zustand } from "./basis.js";
import { textFeld } from "./tastatur.js";
import { aktionen, beiAllgemein, enter, etikettDrucken, etikettNachdrucken, gebindeDrucken, kopf } from "./rahmen.js";
import { kartonListeHtml, positionenHtml } from "./paletten.js";

// ------------------------------------------------------------------ Info
export function infoScan() {
	app.innerHTML = kopf("Info-Scan", true) + textFeld("scan", "Charge, Behälter, Silo oder Palette scannen") + `<div id="info"></div>`;
	aktionen(beiAllgemein);
	enter("scan", async (v, f) => {
		if (!v) return;
		f.value = "";
		try {
			const r = await api("info", { code: v });
			if (r.typ === "palette") {
				document.getElementById("info").innerHTML = `<div class="meldung gruen">${r.versandkarton ? "Versandkarton" : "Palette"} ${esc(r.nve)}</div>
					<div class="panel"><div class="zeile"><div class="fehlt">Art / Status</div><div class="rechts">${esc(r.art)} · ${esc(r.status)}</div></div>
					<div class="zeile"><div class="fehlt">Inhalt</div><div class="rechts">${esc(r.kartons || "leer")}</div></div>
					${r.auf_palette ? `<div class="zeile"><div class="fehlt">Steht auf Palette</div><div class="rechts">…${esc(r.auf_palette.slice(-6))}</div></div>` : ""}
					${r.lieferschein ? `<div class="zeile"><div class="fehlt">Lieferschein</div><div class="rechts">${esc(r.lieferschein)} · ${esc(r.kunde || "")}</div></div>` : ""}</div>` +
					`<p class="fehlt">Los antippen: Woraus besteht das?</p>` + positionenHtml(r, "herkunft-pos") + kartonListeHtml(r, null) +
					`<div class="reihe"><button class="knopf" data-a="etikett-palette">Etikett drucken</button><button class="knopf" data-a="akte">Akte</button></div>`;
				ton(true);
				aktionen((a, d) => {
					if (a === "etikett-palette") return etikettNachdrucken(r.nve);
					if (a === "akte") return akteZeigen(r.nve, infoScan);
					if (a === "herkunft-pos") return herkunftZeigen(r.positionen[+d.i].charge, infoScan);
					beiAllgemein(a);
				});
				return;
			}
			const zeilen = [];
			if (r.typ === "behaelter") zeilen.push(["Behälter", r.behaelter + " (" + r.behaelter_typ + ")"], ["Status", r.status]);
			if (r.typ === "behaelter" && r.gereinigt_am) zeilen.push(["Zuletzt gereinigt", r.gereinigt_am]);
			if (r.typ === "silo") zeilen.push(["Silo/Tank", r.silo]);
			if (r.artikelname) zeilen.push(["Artikel", r.artikelname]);
			if (r.charge) zeilen.push(["Charge", r.charge]);
			if (r.stufe) zeilen.push(["Stufe", r.stufe]);
			if (r.inhalt != null) zeilen.push(["Menge", kg(r.inhalt)]);
			if (r.backtag) zeilen.push(["Backtag", r.backtag]);
			if (r.mhd) zeilen.push(["Verwendbar bis / MHD", r.mhd + (r.abgelaufen ? " – ABGELAUFEN" : "")]);
			if (r.bestand) r.bestand.forEach((b) => zeilen.push(["Im Silo", b.charge + ": " + kg(b.menge)]));
			if (r.moeglich_enthalten && r.moeglich_enthalten.length) zeilen.push(["Möglicherweise enthalten", r.moeglich_enthalten.join(", ")]);
			const gesperrt = r.sperrstatus === "Gesperrt";
			// Leerer Behälter: zur Reinigung geben bzw. als gereinigt melden
			const reinigen = r.typ === "behaelter" && !r.charge && r.behaelter_typ !== "Gebinde" && r.status !== "Gesperrt";
			document.getElementById("info").innerHTML =
				(gesperrt ? `<div class="meldung rot">GESPERRT<small>${esc(r.sperrgrund || "")}</small></div>` : r.abgelaufen ? `<div class="meldung rot">ABGELAUFEN</div>`
					: r.status === "Reinigung" ? `<div class="meldung orange">${esc(v)} ist zur Reinigung<small>Erst nach der Meldung „gereinigt“ wieder befüllen.</small></div>` : `<div class="meldung gruen">${esc(v)}</div>`) +
				`<div class="panel">${zeilen.map(([k, w]) => `<div class="zeile"><div class="fehlt">${esc(k)}</div><div class="rechts">${esc(w)}</div></div>`).join("")}</div>` +
				(reinigen ? `<div class="reihe">${r.status === "Reinigung" ? `<button class="knopf gruen" data-a="gereinigt">Gereinigt – wieder frei</button>`
					: `<button class="knopf" data-a="zur-reinigung">Zur Reinigung</button><button class="knopf" data-a="gereinigt">Gereinigt melden</button>`}</div>` : "") +
				// Etikett nachdrucken (abgerissen, verschmutzt): Behälter und Gebinde
				(r.typ === "behaelter" ? `<div class="reihe"><button class="knopf" data-a="etikett-behaelter">Etikett drucken</button><button class="knopf" data-a="akte">Akte</button></div>` : "") +
				(r.charge ? `<div class="reihe"><button class="knopf" data-a="herkunft">Woraus besteht das?</button></div>` : "") +
				(r.fundstellen ? KtAkte.fundstellenHtml(r.fundstellen, true) : "");
			ton(!gesperrt && !r.abgelaufen);
			aktionen(async (a, d) => {
				if (a === "etikett-behaelter") return gebindeDrucken(r.behaelter, null);
				if (a === "akte") return akteZeigen(d.c || r.behaelter, infoScan);
				if (a === "herkunft") return herkunftZeigen(r.charge, infoScan);
				if (a === "fehlt") return fehltStart(r.fundstellen, +d.i, infoScan);
				if (a !== "gereinigt" && a !== "zur-reinigung") return beiAllgemein(a);
				try {
					const e = await api("behaelter_reinigung", { station: zustand.station, code: r.behaelter, gereinigt: a === "gereinigt" ? 1 : 0 });
					meldung("gruen", e.behaelter + ": " + (e.status === "Frei" ? "gereinigt, frei" : "zur Reinigung"));
					document.getElementById("info").innerHTML = "";
					fokus("scan");
				} catch (err) { meldung("rot", err.message); }
			});
		} catch (e) { meldung("rot", e.message); }
	});
	fokus("scan");
}
// ------------------------------------------------------------------ Akte, Herkunft, Etikett fehlt
// Darstellung in /assets/keks_trace/js/akte_ansicht.js (gemeinsam mit der Audit-Ansicht /akte)
async function akteZeigen(code, zurueck) {
	try {
		const a = await api("akte", { code });
		app.innerHTML = kopf("Akte", true) + `<div class="panel"><div class="gross">${esc(a.titel)}</div></div>` +
			((a.lose || []).length ? `<div class="reihe">${a.lose.map((l) => `<button class="knopf" data-a="herkunft" data-c="${esc(l.charge)}">Woraus besteht Los ${esc(l.los)}?<small>${esc(l.name || "")}</small></button>`).join("")}</div>` : "") +
			KtAkte.akteHtml(a);
		aktionen((x, d) => {
			if (x === "zurueck") return zurueck();
			if (x === "herkunft") return herkunftZeigen(d.c, () => akteZeigen(code, zurueck));
			beiAllgemein(x);
		});
	} catch (e) { meldung("rot", e.message); }
}
async function herkunftZeigen(code, zurueck) {
	app.innerHTML = kopf("Woraus besteht das?", true) + `<p>Lädt …</p>`;
	const zu = () => aktionen((x) => (x === "zurueck" ? zurueck() : beiAllgemein(x)));
	zu();
	try {
		const h = await api("herkunft", { code });
		app.innerHTML = kopf("Woraus besteht das?", true) + KtAkte.herkunftHtml(h);
		zu();
	} catch (e) { meldung("rot", e.message); }
}
// Palette ohne Etikett: aus „Wo ist dieses Los?“ nachdrucken. Damit keine NVE doppelt klebt, werden die
// anderen Paletten mit demselben Los gescannt (sie haben ihr Etikett noch). Das Protokoll hält fest, welche.
function fehltStart(f, i, zurueck) {
	const ziel = f.paletten[i];
	const andere = f.paletten.filter((_, j) => j !== i);
	const gesehen = new Set();
	const zeigen = () => {
		const offen = andere.length - gesehen.size;
		app.innerHTML = kopf("Etikett fehlt", true) +
			`<div class="panel"><div class="gross">Palette …${esc(ziel.nve.slice(-6))}</div><small>${esc([ziel.nve, ziel.dieses_los, ziel.gepackt, ziel.letzte].filter(Boolean).join(" · "))}</small></div>` +
			(andere.length
				? `<div class="meldung ${offen ? "orange" : "gruen"}">${offen ? `Damit keine NVE doppelt klebt: bitte die anderen Paletten mit Los ${esc(f.los)} scannen. Sie müssen ihr Etikett noch haben.<small>Noch ${offen} von ${andere.length}.</small>` : "Alle anderen Paletten haben ihr Etikett."}</div>` +
					textFeld("scan", "Andere Palette scannen") +
					`<div class="panel">${andere.map((x) => `<div class="zeile"><div>${gesehen.has(x.nve) ? "✔" : "○"} Palette …${esc(x.nve.slice(-6))}<br><small class="fehlt">${esc([x.status, x.dieses_los, x.letzte].filter(Boolean).join(" · "))}</small></div>
						<div class="rechts">${gesehen.has(x.nve) ? `<span class="ok">hat Etikett</span>` : "offen"}</div></div>`).join("")}</div>`
				: `<p>Keine anderen Paletten mit diesem Los im Lager.</p>`) +
			`<div class="reihe"><button class="knopf gruen" data-a="drucken"${offen ? " disabled" : ""}>Etikett nachdrucken</button>` +
			(offen ? `<button class="knopf" data-a="trotzdem">Andere nicht erreichbar – trotzdem drucken<small>wird im Protokoll vermerkt</small></button>` : "") + `</div>`;
		aktionen(async (a) => {
			if (a === "zurueck") return zurueck();
			if (a === "drucken" || a === "trotzdem") {
				await etikettDrucken(ziel.nve, "fehlt", [...gesehen].join(","));
				return zurueck();
			}
			beiAllgemein(a);
		});
		enter("scan", async (v, feldEl) => {
			if (!v) return;
			feldEl.value = "";
			try {
				const p = await api("palette_info", { code: v });
				if (p.nve === ziel.nve) { ton(false); return meldung("rot", "Diese Palette hat ein Etikett – dann ist sie nicht die gesuchte. Bitte nochmal prüfen."); }
				if (!andere.some((x) => x.nve === p.nve)) { ton(false); return meldung("orange", "Palette …" + p.nve.slice(-6) + " hat dieses Los nicht."); }
				gesehen.add(p.nve);
				ton(true);
				zeigen();
			} catch (e) { meldung("rot", e.message); }
		});
		fokus("scan");
	};
	zeigen();
}
