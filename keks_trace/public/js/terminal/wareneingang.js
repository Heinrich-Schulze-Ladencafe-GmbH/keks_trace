// Terminal: Wareneingang mit Scan des Lieferanten-Etiketts.

import { api, app, ein, esc, fokus, meldung, mg, rund, ton, zahl, zustand } from "./basis.js";
import { datumDe, datumFeld, datumWert, einheitSetzen, textFeld, zahlFeld } from "./tastatur.js";
import { aktionen, beiAllgemein, enter, ergebnis, gebindeDrucken, kopf, suchListe } from "./rahmen.js";
import { kennzeichenMarken, pruefFelder, pruefWerte } from "./station.js";

// ------------------------------------------------------------------ Wareneingang
let artikelListe = [];
export async function wareneingangStart() {
	// Zuerst das Etikett des Lieferanten scannen; ohne Code den Artikel antippen
	let vorschlag = null;
	app.innerHTML = kopf("Wareneingang", true) +
		textFeld("etikett", "Etikett des Lieferanten scannen – oder Artikel unten antippen") +
		`<div id="etikett-info"></div><p>Welcher Artikel? Zeile antippen</p><div id="liste">Lädt …</div>`;
	aktionen(beiAllgemein);
	try {
		artikelListe = await api("wareneingang_artikel");
		suchListe("liste", [["Artikel", "artikel"], ["Bezeichnung", "name"], ["Einheit", (r) => ein(r.stock_uom)],
			["Hinweis", (r) => [r.silo ? "Silo" : "", r.kt_freigabe_pflicht ? "Freigabe QS" : "", r.bio ? "BIO" : ""].filter(Boolean).join(", ")]],
			artikelListe, (r) => wareneingangErfassen(r, vorschlag), "Suchen: Artikelnummer oder Bezeichnung …");
	} catch (e) { meldung("rot", e.message); }
	enter("etikett", async (code, f) => {
		if (!code) return;
		try {
			const r = await api("wareneingang_scan", { code });
			const info = document.getElementById("etikett-info");
			if (r.artikel) {
				const art = artikelListe.find((a) => a.artikel === r.artikel);
				if (!art) return meldung("rot", "Artikel " + r.artikel + " ist hier nicht für den Wareneingang freigegeben.");
				return wareneingangErfassen(art, r);
			}
			vorschlag = r.gs1 || r.gtin ? { ...r, artikel: null } : { charge: r.charge };
			f.value = "";
			info.innerHTML = r.unbekannt
				? `<div class="meldung orange">Code ${esc(r.gtin)} ist keinem Artikel zugeordnet. Bitte den Artikel unten antippen.<small>Im Büro am Artikel unter „Barcodes“ eintragen (mit Einheit, z. B. Karton). Danach erkennt das Terminal ihn selbst.</small></div>`
				: `<div class="meldung orange">Kein Artikel-Code, als Charge übernommen: ${esc(r.charge)}. Bitte den Artikel unten antippen.</div>`;
		} catch (e) { meldung("rot", e.message); }
	});
	fokus("etikett");
}
// Lieferanten-Etikett ins Formular übernehmen (nur Vorschlag – der Mensch prüft vor dem Buchen)
function etikettUebernehmen(v, einheit) {
	if (!v) return "";
	const set = (id, wert) => {
		const f = document.getElementById(id);
		if (f && wert != null && wert !== "") { f.value = wert; f.dispatchEvent(new Event("input", { bubbles: true })); }
	};
	set("scan", v.charge);
	if (v.mhd) { const [y, m, d] = v.mhd.split("-"); set("mhd", `${d}.${m}.${y}`); }
	if (v.menge_je_gebinde) set("menge", String(rund(v.menge_je_gebinde, 3)).replace(".", ","));
	const teile = [v.charge ? "Charge " + v.charge : "", v.mhd ? "MHD " + datumDe(v.mhd) : "",
		v.menge_je_gebinde ? "je Gebinde " + String(rund(v.menge_je_gebinde, 3)).replace(".", ",") + (einheit ? " " + ein(einheit) : "") : ""].filter(Boolean);
	return (teile.length ? `<div class="panel">Vom Etikett gelesen: <b>${esc(teile.join(" · "))}</b><br><span class="fehlt" style="font-size:16px">Noch nicht gebucht. Bitte mit dem Etikett vergleichen.</span></div>` : "") +
		(v.unvollstaendig ? `<div class="meldung orange">Etikett nur teilweise gelesen. Bitte alle Felder prüfen.</div>` : "") +
		(v.charge_bekannt ? `<div class="meldung orange">Diese Charge ist schon gebucht. Gleiche Lieferung zweimal?</div>` : "");
}
function wareneingangErfassen(art, vorschlag) {
	const ARTEN = ["Sack", "Fass", "IBC", "Eimer", "Karton", "Kanister", "BigBag", "Sonstiges"];
	let gebindeart = vorschlag && ARTEN.includes(vorschlag.gebindeart) ? vorschlag.gebindeart : "Sack";
	// Eigenes Etikett nur, wenn das Etikett des Lieferanten die Charge nicht im Strichcode trägt
	let etiketten = !(vorschlag && vorschlag.gs1 && vorschlag.charge && vorschlag.artikel === art.artikel);
	const lief = art.lieferanten || [];
	app.innerHTML = kopf(art.name, true) +
		(art.bio ? `<div class="panel">${kennzeichenMarken(["Bio"])} <span class="fehlt" style="font-size:16px">Nur Lieferanten mit gültigem Öko-Zertifikat.</span></div>` : "") +
		(art.bio && !lief.length ? `<div class="meldung rot">Kein Lieferant mit gültigem Öko-Zertifikat hinterlegt. Annahme als Bio nicht möglich.<small>Zertifikat beim Lieferanten im Büro eintragen.</small></div>` : "") +
		(lief.length ? `<label>Lieferant${art.bio ? "" : " (optional)"}</label><select id="lieferant" class="feld">${art.bio ? "" : `<option value="">–</option>`}${lief.map((l) => `<option value="${esc(l.lieferant)}">${esc(l.name)}${l.bio_ok ? " · Bio-zertifiziert" : ""}</option>`).join("")}</select>` : "") +
		((art.bestellungen || []).length ? `<label for="bestellung">Bestellung</label><select id="bestellung" class="feld"></select>
			<small class="feld-hinweis">Offene Bestellungen mit diesem Artikel. Mit Bestellung steht sie in der Rückverfolgung.</small>` : "") +
		`<div id="etikett-info"></div>` +
		textFeld("scan", "Charge des Lieferanten (Etikett scannen oder Charge eingeben)") +
		`${art.has_expiry_date ? datumFeld("mhd", "MHD", { pflicht: true, abHeute: true }) : ""}
		${art.silo ? `<label>Wohin?</label><select id="ziel" class="feld"><option value="${esc(art.silo)}">ins ${esc(art.silo)}</option><option value="">als Gebinde ins Lager</option></select>` : ""}
		<div id="gebinde-box" style="${art.silo ? "display:none" : ""}">
			<label>Gebindeart</label><div class="einheiten">${ARTEN.map((a) => `<button type="button" data-a="einheit" data-e="${a}" class="${a === gebindeart ? "an" : ""}">${a}</button>`).join("")}</div>
			${zahlFeld("anzahl", "Wie viele Gebinde?", 1)}
			<label>Eigenes Etikett je Gebinde?</label><div class="einheiten">
				<button type="button" data-a="etikett" data-e="ja" class="${etiketten ? "an" : ""}">Ja, drucken</button>
				<button type="button" data-a="etikett" data-e="nein" class="${etiketten ? "" : "an"}">Nein, Lieferanten-Etikett hat die Charge</button></div>
		</div>` +
		zahlFeld("menge", `<span id="menge-text">${art.silo ? "Menge" : "Menge je Gebinde"}</span> (${esc(ein(art.stock_uom))})`) +
		pruefFelder(art.pruefungen, "pw") +
		`<div class="reihe"><button class="knopf gruen" data-a="buchen">Buchen</button></div>`;
	// Bestellung: Auswahl passend zum Lieferanten; Bestellung wählen setzt den Lieferanten
	const bestFeld = document.getElementById("bestellung");
	const liefFeld = document.getElementById("lieferant");
	const bestFuellen = () => {
		if (!bestFeld) return;
		const l = liefFeld ? liefFeld.value : "";
		const alt = bestFeld.value;
		const liste = art.bestellungen.filter((b) => !l || b.lieferant === l);
		bestFeld.innerHTML = `<option value="">– ohne Bestellung –</option>` + liste.map((b) => `<option value="${esc(b.bestellung)}">${esc(b.bestellung)} · ${esc(b.lieferantname || b.lieferant)} · offen ${esc(mg(b.offen, art.stock_uom))}${b.termin ? " · Termin " + esc(b.termin) : ""}</option>`).join("");
		bestFeld.value = liste.some((b) => b.bestellung === alt) ? alt : liste.length === 1 ? liste[0].bestellung : "";
	};
	if (bestFeld) {
		bestFuellen();
		bestFeld.addEventListener("change", () => {
			const b = art.bestellungen.find((x) => x.bestellung === bestFeld.value);
			if (b && liefFeld && [...liefFeld.options].some((o) => o.value === b.lieferant)) liefFeld.value = b.lieferant;
		});
		if (liefFeld) liefFeld.addEventListener("change", bestFuellen);
	}
	const zielFeld = document.getElementById("ziel");
	if (zielFeld) zielFeld.addEventListener("change", () => {
		const silo = !!zielFeld.value;
		document.getElementById("gebinde-box").style.display = silo ? "none" : "";
		document.getElementById("menge-text").textContent = silo ? "Menge" : "Menge je Gebinde";
	});
	const info = document.getElementById("etikett-info");
	info.innerHTML = etikettUebernehmen(vorschlag, art.stock_uom);
	// Lieferanten-Charge mit Charge im Strichcode: nur dann kann die Backstube das Lieferanten-Etikett scannen
	let chargeImCode = !etiketten;
	const etikettSetzen = (ja) => {
		etiketten = ja;
		app.querySelectorAll('[data-a="etikett"]').forEach((b) => b.classList.toggle("an", (b.dataset.e === "ja") === ja));
		if (!ja && !chargeImCode) meldung("orange", "Ohne eigenes Etikett muss die Backstube die Charge eintippen – das Lieferanten-Etikett hat sie nicht im Strichcode.");
	};
	enter("scan", async (code) => {
		if (!code) return;
		try {
			const r = await api("wareneingang_scan", { code });
			if (r.artikel && r.artikel !== art.artikel) return meldung("rot", "Das Etikett gehört zu " + r.artikel + ", nicht zu " + art.artikel + ".");
			if (r.gs1 || r.gtin) {
				if (!r.charge) return meldung("orange", "Auf diesem Etikett steht keine Charge im Strichcode. Bitte die Charge abtippen.");
				document.getElementById("scan").value = "";
				info.innerHTML = etikettUebernehmen(r, art.stock_uom);
				chargeImCode = !!(r.gs1 && r.artikel === art.artikel);
				if (chargeImCode) etikettSetzen(false);
			}
		} catch (e) { return meldung("rot", e.message); }
		const m = document.getElementById("mhd");
		if (m && !m.value) m.focus(); else fokus("menge");
	});
	aktionen(async (a, d) => {
		if (a === "einheit") { gebindeart = d.e; return einheitSetzen(gebindeart); }
		if (a === "etikett") return etikettSetzen(d.e === "ja");
		if (a !== "buchen") return beiAllgemein(a);
		const knopf = app.querySelector('[data-a="buchen"]');
		if (knopf) { knopf.disabled = true; knopf.textContent = "Bucht …"; }
		try {
			const ziel = document.getElementById("ziel");
			const mhdIso = datumWert("mhd", "MHD");
			const silo = ziel ? ziel.value || null : null;
			const e = await api("wareneingang", {
				station: zustand.station,
				artikel: art.artikel,
				lieferantencharge: document.getElementById("scan").value.trim(),
				lieferant: document.getElementById("lieferant") ? document.getElementById("lieferant").value || null : null,
				menge: zahl(document.getElementById("menge").value),
				mhd: mhdIso,
				silo,
				gebinde: silo ? 0 : Math.max(1, Math.round(zahl(document.getElementById("anzahl").value))),
				gebindeart: silo ? null : gebindeart,
				etiketten: etiketten ? 1 : 0,
				pruefwerte: pruefWerte(art.pruefungen, "pw"),
				bestellung: bestFeld ? bestFeld.value || null : null,
			});
			if (e.abgelehnt) {
				app.innerHTML = kopf(e.name, true) + `<div class="meldung rot">Annahme verweigert<small>${e.gruende.map(esc).join("<br>")}</small></div>` +
					e.korrektur.map((k) => `<div class="meldung orange">${esc(k)}</div>`).join("") +
					`<p class="fehlt">Nichts gebucht. Die Prüfung ist protokolliert.</p><div class="reihe"><button class="knopf blau" data-a="zurueck">Fertig</button></div>`;
				ton(false);
				return aktionen(beiAllgemein);
			}
			const druck = (grund) => gebindeDrucken(e.gebinde, grund);
			if (e.gebinde && e.gebinde.length) druck("ablauf");
			ergebnis(e.name, ["Charge: " + e.charge, "Menge: " + mg(e.menge, art.stock_uom), "Ort: " + e.lager,
				e.bestellung ? "Bestellung: " + e.bestellung : "",
				e.gebinde && e.gebinde.length ? "Gebinde: " + e.gebinde.join(", ") : "", e.mhd ? "MHD: " + e.mhd : ""].filter(Boolean),
				(e.gesperrt ? ["Gesperrt bis zur Freigabe durch die QS (" + (e.sperrgrund || "") + ")"] : []).concat(e.hinweise || []),
				e.gebinde && e.gebinde.length ? `<button class="knopf" data-a="etiketten">Gebinde-Etiketten drucken</button>` : "")((a2) => (a2 === "etiketten" ? druck(null) : beiAllgemein(a2)));
		} catch (err) {
			if (knopf) { knopf.disabled = false; knopf.textContent = "Buchen"; }
			meldung("rot", err.message);
		}
	});
	enter("anzahl", () => fokus("menge"));
	enter("menge", () => {});
	const mhdFeld = document.getElementById("mhd");
	fokus(!(vorschlag && vorschlag.charge) ? "scan" : mhdFeld && !mhdFeld.value ? "mhd" : art.silo ? "menge" : "anzahl");
}
