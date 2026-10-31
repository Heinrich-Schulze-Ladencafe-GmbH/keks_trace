frappe.query_reports["Rueckverfolgung"] = {
	filters: [
		{
			fieldname: "charge",
			label: __("Charge / Los"),
			fieldtype: "Link",
			options: "Batch",
			reqd: 1,
		},
		{
			fieldname: "richtung",
			label: __("Richtung"),
			fieldtype: "Select",
			options: "Vorwärts\nRückwärts",
			default: "Vorwärts",
			reqd: 1,
		},
	],

	onload(report) {
		const charge = () => report.get_filter_value("charge");

		report.page.add_inner_button(__("Rückverfolgungstest protokollieren"), () => {
			if (!charge()) return frappe.msgprint(__("Bitte zuerst eine Charge wählen."));
			frappe.prompt(
				{ fieldname: "anlass", fieldtype: "Select", label: __("Anlass"), reqd: 1,
				  options: "Jährlicher Test\nÄnderung am System\nReklamation\nRückruf\nAudit", default: "Jährlicher Test" },
				async (v) => {
					const doc = await frappe.db.insert({ doctype: "Rueckverfolgungstest", charge: charge(), anlass: v.anlass });
					frappe.set_route("Form", "Rueckverfolgungstest", doc.name);
				},
				__("Rückverfolgungstest (IFS 4.18)"),
				__("Test starten")
			);
		});

		report.page.add_inner_button(__("Rückruf: alles vorwärts sperren"), () => {
			if (!charge()) return frappe.msgprint(__("Bitte zuerst eine Charge wählen."));
			frappe.prompt(
				{ fieldname: "grund", fieldtype: "Small Text", label: __("Grund"), reqd: 1 },
				(v) => {
					frappe.confirm(
						__("Charge {0} und alle Chargen, in die sie eingeflossen ist, werden gesperrt. Fortfahren?", [charge()]),
						() => frappe.call({
							method: "keks_trace.sperre.rueckruf_sperre",
							args: { charge: charge(), grund: v.grund },
							freeze: true,
							callback: (r) => {
								const e = r.message || {};
								const kunden = [...new Set((e.kunden || []).map((k) => `${k.kundenname || k.kunde} (${k.lieferschein})`))];
								const paletten = (e.paletten || []).map((p) => p.palette);
								const laden = (e.lagerverkauf || []).map((z) => `${z.charge}: ${Math.round(z.bestand * 1000) / 1000} kg`);
								frappe.msgprint({
									title: __("Rückruf {0}", [e.vorgang]),
									indicator: "red",
									message: `<p>${__("Gesperrt")}: ${(e.chargen || []).length} ${__("Chargen")}</p>` +
										`<p><b>${__("Betroffene Kunden")}:</b><br>${kunden.join("<br>") || "-"}</p>` +
										`<p><b>${__("Paletten noch im Lager")}:</b><br>${paletten.join("<br>") || "-"}</p>` +
										`<p><b>${__("Noch im Lagerverkauf (aus dem Regal nehmen)")}:</b><br>${laden.join("<br>") || "-"}</p>`,
								});
								report.refresh();
							},
						})
					);
				},
				__("Rückruf"),
				__("Sperren")
			);
		});
	},
};
