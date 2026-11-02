/* Akte, „Wo ist dieses Los?“ und „Woraus besteht das?“ als HTML – gemeinsam für das Terminal (/terminal)
 * und die Audit-Ansicht (/akte). Nur Darstellung: Daten kommen aus keks_trace.akte (über terminal.akte,
 * terminal.info, terminal.herkunft). Knöpfe tragen data-a / data-c / data-i; die Seite verdrahtet sie selbst. */
(function () {
	"use strict";
	const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
	const kurzNve = (nve) => "…" + String(nve || "").slice(-6);
	const zahl = (n) => String(Math.round(n * 1000) / 1000).replace(".", ",");

	const css = `
	.ak-panel { background: var(--panel, #fbeaa8); border: 1px solid var(--rand, #9db9dd); border-radius: 6px; padding: 4px 14px; margin: 10px 0; }
	.ak-zeile { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid rgba(0,0,0,.08); }
	.ak-zeile:last-child { border-bottom: none; }
	.ak-zeile .ak-k { color: var(--muted, #5a6573); flex: 0 0 auto; }
	.ak-zeile .ak-w { text-align: right; overflow-wrap: anywhere; }
	.ak-h2 { font-size: 20px; margin: 18px 0 6px; }
	.ak-hinweis { color: var(--muted, #5a6573); font-size: 15px; margin: 4px 0; }
	.ak-ereignis { display: grid; grid-template-columns: minmax(120px, 190px) 1fr; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(0,0,0,.08); }
	.ak-ereignis:last-child { border-bottom: none; }
	.ak-ereignis .ak-zeit { color: var(--muted, #5a6573); font-variant-numeric: tabular-nums; }
	.ak-ereignis small, .ak-baum small, .ak-roh small, .ak-karte small { display: block; color: var(--muted, #5a6573); font-size: 15px; }
	.ak-panel, .ak-karte, .ak-baum, .ak-ereignis > div { overflow-wrap: anywhere; min-width: 0; }
	.ak-karte { background: var(--panel2, #e9f1fb); border: 1px solid var(--rand, #9db9dd); border-radius: 6px; padding: 10px 14px; margin: 10px 0; }
	.ak-karte b { font-size: 20px; }
	.ak-knoepfe { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
	.ak-knoepfe button { flex: 1 1 180px; min-height: 52px; font-size: 18px; }
	.ak-marke { display: inline-block; font-size: 14px; padding: 1px 8px; border-radius: 10px; margin-left: 6px; vertical-align: middle; }
	.ak-ok { background: #d8f0da; color: #1f6b27; }
	.ak-rot { background: #fbd9d9; color: #9c1f1f; }
	.ak-grau { background: #e4e7eb; color: #4a5260; }
	.ak-orange { background: #fde6c2; color: #8a5300; }
	.ak-baum details { margin-left: 14px; border-left: 2px solid var(--rand, #9db9dd); padding-left: 10px; }
	.ak-baum > details { margin-left: 0; border-left: none; padding-left: 0; }
	.ak-baum summary { cursor: pointer; padding: 6px 0; list-style-position: outside; }
	.ak-knoten { padding: 6px 0 6px 14px; margin-left: 14px; border-left: 2px solid var(--rand, #9db9dd); }
	.ak-roh { padding: 8px 0; border-bottom: 1px solid rgba(0,0,0,.08); }
	.ak-roh:last-child { border-bottom: none; }
	.ak-moeglich { opacity: .75; font-style: italic; }
	@media (max-width: 600px) {
		.ak-baum details, .ak-knoten { margin-left: 4px; padding-left: 8px; }
		.ak-ereignis { grid-template-columns: 1fr; gap: 2px; }
		.ak-zeile { flex-wrap: wrap; }
		.ak-zeile .ak-w { text-align: left; }
	}
	`;
	if (!document.getElementById("ak-stil")) {
		const st = document.createElement("style");
		st.id = "ak-stil";
		st.textContent = css;
		document.head.appendChild(st);
	}

	function zeilen(liste) {
		return `<div class="ak-panel">${liste.filter((z) => z && z[1]).map(([k, w]) => `<div class="ak-zeile"><div class="ak-k">${esc(k)}</div><div class="ak-w">${esc(w)}</div></div>`).join("")}</div>`;
	}

	// Lebenslauf einer Palette oder eines Behälters, neueste zuerst
	function akteHtml(a) {
		const ev = (a.ereignisse || []).slice().reverse();
		return zeilen(a.zeilen || []) +
			`<h2 class="ak-h2">Lebenslauf <span class="ak-hinweis">(neueste zuerst)</span></h2>` +
			(ev.length ? `<div class="ak-panel">${ev.map((e) => `<div class="ak-ereignis"><div class="ak-zeit">${esc(e.zeit_text)}</div>
				<div>${esc(e.text)}${e.station || e.person ? `<small>${esc([e.station, e.person].filter(Boolean).join(" · "))}</small>` : ""}</div></div>`).join("")}</div>`
				: `<p class="ak-hinweis">Noch keine Einträge.</p>`);
	}

	// „Wo ist dieses Los?“ – mitNachdruck: Knopf „Etikett fehlt“ (nur am Terminal)
	function fundstellenHtml(f, mitNachdruck) {
		if (!f) return "";
		const p = f.paletten || [];
		const b = f.behaelter || [];
		let h = `<h2 class="ak-h2">Wo ist Los ${esc(f.los)}?</h2>`;
		if (!p.length && !b.length && !f.lose) return h + `<p class="ak-hinweis">Nicht im Lager: keine offene Palette, kein Behälter, keine lose Ware.</p>`;
		h += p.map((x, i) => `<div class="ak-karte">
			<div><b>Palette ${esc(kurzNve(x.nve))}</b> <span class="ak-marke ak-grau">${esc(x.status)}</span>${x.etikett_aktuell === false ? `<span class="ak-marke ak-orange">Etikett veraltet</span>` : ""}
				<small>${esc(x.nve)}${x.kunde ? " · " + esc(x.kunde) : ""}</small></div>
			${zeilen([["Dieses Los", x.dieses_los], ["Gesamt auf der Palette", x.inhalt],
				["Gepackt", x.gepackt ? [x.gepackt, x.stationen, x.personen].filter(Boolean).join(" · ") : null],
				["Zuletzt", x.letzte], ["Etikett", x.letzter_druck || "noch nie gedruckt"]])}
			<div class="ak-knoepfe"><button class="knopf klein" data-a="akte" data-c="${esc(x.nve)}">Akte</button>
				${mitNachdruck ? `<button class="knopf klein" data-a="fehlt" data-i="${i}">Etikett fehlt – nachdrucken</button>` : ""}</div></div>`).join("");
		if (f.mehr_paletten) h += `<p class="ak-hinweis">… und ${f.mehr_paletten} weitere Paletten.</p>`;
		h += b.map((x) => `<div class="ak-karte"><b>${esc(x.typ)} ${esc(x.code)}</b> <span class="ak-marke ak-grau">${esc(x.status)}</span>
			<small>${x.menge ? esc(zahl(x.menge)) + " kg" : ""}</small>
			<div class="ak-knoepfe"><button class="knopf klein" data-a="akte" data-c="${esc(x.code)}">Akte</button></div></div>`).join("");
		if (f.lose) h += `<div class="ak-karte"><b>Lose Ware</b> (nicht auf Palette)<small>${esc(f.lose)}</small></div>`;
		return h;
	}

	function marken(n) {
		let m = "";
		if (n.moeglich) m += `<span class="ak-marke ak-orange">möglicherweise enthalten</span>`;
		if (n.gesperrt) m += `<span class="ak-marke ak-rot">gesperrt</span>`;
		if (n.wiederholt) m += `<span class="ak-marke ak-grau">siehe oben</span>`;
		return m;
	}
	function wareneingang(w) {
		if (!w) return "kein Wareneingang gefunden";
		return ["Wareneingang " + (w.zeit || ""), w.lieferant ? "Lieferant " + w.lieferant : "", w.lieferschein ? "Lieferschein " + w.lieferschein : "",
			w.silo ? "direkt in " + w.silo : w.lager ? "nach " + w.lager : "", w.beleg].filter(Boolean).join(" · ");
	}
	function freigabe(f) {
		if (!f) return "";
		return (f.aktion === "Freigeben" ? "Freigegeben" : "Gesperrt") + " " + (f.zeit || "") + (f.person ? " von " + f.person : "");
	}
	function rohstoffHtml(r) {
		return `<div class="ak-roh${r.moeglich ? " ak-moeglich" : ""}"><b>${esc(r.name)}</b> · Charge ${esc(r.charge)}${marken(r)}
			<small>${esc(wareneingang(r.wareneingang))}</small>
			<small>${esc([r.mhd ? "MHD " + r.mhd : "", freigabe(r.freigabe), r.ueber_silo && !(r.wareneingang || {}).silo ? "über " + r.ueber_silo : ""].filter(Boolean).join(" · "))}</small></div>`;
	}
	function knotenKopf(n) {
		const was = [n.stufe, n.los ? "Los " + n.los : "Charge " + n.charge, n.menge ? zahl(n.menge) + " kg" : ""].filter(Boolean).join(" · ");
		return `<b>${esc(n.name)}</b> <span class="ak-hinweis">${esc(was)}</span>${marken(n)}`;
	}
	function knotenDetails(n) {
		const h = n.herstellung;
		const teile = [];
		if (h) teile.push(`<small>Hergestellt ${esc(h.zeit)}${h.station ? " · " + esc(h.station) : ""}${h.person ? " · " + esc(h.person) : ""} · ${esc(h.beleg)}</small>`);
		else if (n.hergestellt || n.backtag) teile.push(`<small>${esc(n.backtag ? "Backtag " + n.backtag : "Hergestellt " + n.hergestellt)}</small>`);
		if (n.mhd) teile.push(`<small>MHD / verwendbar bis ${esc(n.mhd)}</small>`);
		if (n.sperrgrund) teile.push(`<small>Sperrgrund: ${esc(n.sperrgrund)}</small>`);
		(n.pruefungen || []).forEach((p) => teile.push(`<small>Prüfung ${esc(p.was)} ${esc(p.zeit)}${p.wert ? " · " + esc(p.wert) : ""}
			<span class="ak-marke ${p.ergebnis === "OK" ? "ak-ok" : "ak-rot"}">${esc(p.ergebnis)}</span></small>`));
		if (n.abgeschnitten) teile.push(`<small>Weitere Stufen nicht angezeigt (sehr viele Chargen) – vollständig in ERPNext unter Rückverfolgung.</small>`);
		return teile.join("");
	}
	function knotenHtml(n, tiefe) {
		if (n.stufe === "Rohstoff" || n.stufe === "Packmittel") return `<div class="ak-knoten">${rohstoffHtml(n)}</div>`;
		if (!n.teile || !n.teile.length || n.wiederholt) return `<div class="ak-knoten">${knotenKopf(n)}${knotenDetails(n)}</div>`;
		return `<details${tiefe < 3 ? " open" : ""}><summary>${knotenKopf(n)}</summary>${knotenDetails(n)}${n.teile.map((t) => knotenHtml(t, tiefe + 1)).join("")}</details>`;
	}
	// „Woraus besteht das?“: erst alle Rohstoffe und Packmittel (für die Frage des Auditors), dann der Weg
	function herkunftHtml(h) {
		const r = h.rohstoffe || [];
		const sicher = r.filter((x) => !x.moeglich);
		const moeglich = r.filter((x) => x.moeglich);
		return `<h2 class="ak-h2">Woraus besteht ${esc(h.baum.los ? "Los " + h.baum.los : h.baum.name)}?</h2>
			<h2 class="ak-h2">Rohstoffe und Packmittel (${sicher.length})</h2>
			<div class="ak-panel">${sicher.map(rohstoffHtml).join("") || `<p class="ak-hinweis">Keine gefunden.</p>`}</div>
			${moeglich.length ? `<p class="ak-hinweis">Möglicherweise enthalten (Silo: alte und neue Charge vermischt):</p><div class="ak-panel">${moeglich.map(rohstoffHtml).join("")}</div>` : ""}
			<h2 class="ak-h2">Herstellungsweg</h2><div class="ak-baum">${knotenHtml(h.baum, 0)}</div>
			${h.abgeschnitten ? `<p class="ak-hinweis">Gekürzt: sehr viele Chargen. Vollständig in ERPNext unter Rückverfolgung (rückwärts).</p>` : ""}`;
	}

	window.KtAkte = { esc, akteHtml, fundstellenHtml, herkunftHtml };
})();
