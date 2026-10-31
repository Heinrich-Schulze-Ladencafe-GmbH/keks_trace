frappe.query_reports["Produktionsplan"] = {
	filters: [
		{ fieldname: "linie", label: __("Linie"), fieldtype: "Link", options: "Linie", reqd: 1 },
		{ fieldname: "von", label: __("Von"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "bis", label: __("Bis"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 30) },
	],
	onload(report) {
		const linie = () => report.get_filter_value("linie");
		report.page.add_inner_button(__("Planung vorschlagen"), () => {
			if (!linie()) return frappe.msgprint(__("Bitte erst eine Linie wählen."));
			frappe.call("keks_trace.planung.vorschlag", { linie: linie() }).then((r) => {
				const m = r.message;
				frappe.msgprint(__("{0} Produktionsaufträge geplant.", [m.angelegt]) +
					(m.ohne_leistung.length ? "<br>" + __("Ohne Leistung je Abschnitt (nicht geplant): {0}", [m.ohne_leistung.join(", ")]) : "") +
					(m.ohne_linie.length ? "<br>" + __("Ohne Linie am Artikel (nicht geplant): {0}", [m.ohne_linie.join(", ")]) : ""));
				report.refresh();
			});
		});
		report.page.add_inner_button(__("Tag freigeben"), () => {
			if (!linie()) return frappe.msgprint(__("Bitte erst eine Linie wählen."));
			frappe.prompt({ fieldname: "datum", label: __("Produktionstag"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() }, (v) => {
				frappe.call("keks_trace.planung.tag_freigeben", { linie: linie(), datum: v.datum }).then((r) => {
					frappe.show_alert({ message: __("{0} Aufträge freigegeben", [r.message.freigegeben]), indicator: "green" });
					report.refresh();
				});
			}, __("Tagesplan freigeben"), __("Freigeben"));
		});
		report.page.add_inner_button(__("Nicht freigegebene verwerfen"), () => {
			if (!linie()) return;
			frappe.confirm(__("Alle noch nicht freigegebenen Aufträge ab heute löschen?"), () => {
				frappe.call("keks_trace.planung.plan_verwerfen", { linie: linie() }).then((r) => {
					frappe.show_alert({ message: __("{0} gelöscht", [r.message.geloescht]) });
					report.refresh();
				});
			});
		});
	},
};
