frappe.query_reports["QS Tagesliste"] = {
	filters: [
		{ fieldname: "von", label: __("Von"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "bis", label: __("Bis"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "arten",
			label: __("Arten"),
			fieldtype: "MultiSelectList",
			get_data: () => ["FEFO", "Einwaage", "Prüfung", "Sperre"].map((a) => ({ value: a, description: "" })),
		},
	],
	onload(report) {
		report.page.add_inner_button(__("Tag als durchgesehen bestätigen"), () => {
			const von = report.get_filter_value("von");
			const bis = report.get_filter_value("bis") || von;
			if (von !== bis) {
				frappe.msgprint(__("Bitte genau einen Tag wählen (Von = Bis)."));
				return;
			}
			frappe.prompt(
				[{ fieldname: "bemerkung", label: __("Bemerkung (optional)"), fieldtype: "Small Text" }],
				(v) =>
					frappe
						.call("keks_trace.qs_tagesliste.durchsehen", { datum: von, bemerkung: v.bemerkung })
						.then((r) => {
							frappe.show_alert({ message: __("Durchgesehen: {0} Einträge", [r.message.eintraege]), indicator: "green" });
							report.refresh();
						}),
				__("Durchsicht {0} bestätigen", [frappe.datetime.str_to_user(von)]),
				__("Bestätigen")
			);
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "art" && data) {
			const farbe = { FEFO: "var(--orange-600)", Einwaage: "var(--orange-600)", Prüfung: "var(--red-600)", Sperre: "var(--red-600)" }[data.art];
			return `<span style="color:${farbe};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
