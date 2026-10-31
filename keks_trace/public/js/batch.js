// Charge: Sperren und Freigeben durch die QS (mit Grund, protokolliert in „Chargen Sperre“)
frappe.ui.form.on("Batch", {
	refresh(frm) {
		if (frm.is_new()) return;
		const qs = frappe.user.has_role("Quality Manager") || frappe.user.has_role("System Manager");
		if (frm.doc.kt_status === "Gesperrt") {
			frm.dashboard.set_headline_alert(__("Gesperrt: {0}", [frm.doc.kt_sperrgrund || ""]), "red");
			if (qs)
				frm.add_custom_button(__("Freigeben"), () =>
					frappe.prompt({ fieldname: "bemerkung", fieldtype: "Small Text", label: __("Bemerkung zur Freigabe"), reqd: 1 }, (v) =>
						frappe.call("keks_trace.sperre.freigeben", { charge: frm.doc.name, bemerkung: v.bemerkung }).then(() => frm.reload_doc()),
						__("Charge freigeben"), __("Freigeben"))
				);
		} else if (qs) {
			frm.add_custom_button(__("Sperren"), () =>
				frappe.prompt({ fieldname: "grund", fieldtype: "Small Text", label: __("Grund der Sperre"), reqd: 1 }, (v) =>
					frappe.call("keks_trace.sperre.sperren", { charge: frm.doc.name, grund: v.grund }).then(() => frm.reload_doc()),
					__("Charge sperren"), __("Sperren"))
			);
		}
		frm.add_custom_button(__("Rückverfolgung"), () =>
			frappe.set_route("query-report", "Rueckverfolgung", { charge: frm.doc.name })
		);
		frm.add_custom_button(__("Mengenbilanz"), () =>
			frappe.set_route("query-report", "Mengenbilanz", { charge: frm.doc.name })
		);
	},
});
