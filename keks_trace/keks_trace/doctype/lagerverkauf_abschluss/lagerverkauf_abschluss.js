frappe.ui.form.on("Lagerverkauf Abschluss", {
	setup(frm) {
		frm.set_query("lagerort", () => ({ filters: { is_group: 0 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.datei && !frm.is_new()) {
			frm.add_custom_button(__("Datei einlesen"), () =>
				frappe.call({
					method: "keks_trace.keks_trace.doctype.lagerverkauf_abschluss.lagerverkauf_abschluss.einlesen",
					args: { name: frm.doc.name },
					freeze: true,
					callback: (r) => {
						frm.reload_doc();
						const e = r.message || {};
						frappe.show_alert({
							message: __("{0} Artikel eingelesen, {1} noch zuzuordnen", [e.positionen, e.unbekannt]),
							indicator: e.unbekannt ? "orange" : "green",
						});
					},
				})
			);
		}
	},
});
