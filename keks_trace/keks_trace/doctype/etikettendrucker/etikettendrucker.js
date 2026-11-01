frappe.ui.form.on("Etikettendrucker", {
	refresh(frm) {
		const zeilen = (frm.doc.__onload && frm.doc.__onload.genutzt) || [];
		frm.fields_dict.genutzt.$wrapper.html(
			zeilen.length
				? `<table class="table table-bordered table-condensed"><thead><tr><th>${__("Terminal")}</th><th>${__("Etikett")}</th></tr></thead><tbody>` +
					zeilen.map((z) => `<tr><td><a href="/app/terminal-station/${encodeURIComponent(z.station)}">${frappe.utils.escape_html(z.station)}</a>` +
						(z.aktiv ? "" : ` <span class="text-muted">(${__("inaktiv")})</span>`) + `</td><td>${frappe.utils.escape_html(z.etikett)}</td></tr>`).join("") +
					`</tbody></table>`
				: `<p class="text-muted">${__("Noch an keinem Terminal eingetragen. Zuordnen an der Terminal Station, Abschnitt „Etikettendrucker“.")}</p>`
		);
		if (frm.is_new()) return;
		frm.add_custom_button(__("Testdruck"), () =>
			frappe.call({ method: "keks_trace.etiketten.testdruck", args: { drucker: frm.doc.name }, freeze: true })
				.then(() => frappe.show_alert({ message: __("Testetikett an {0} geschickt. Rahmen nachmessen: 90 x 50 mm.", [frm.doc.name]), indicator: "green" }))
		);
	},
});
