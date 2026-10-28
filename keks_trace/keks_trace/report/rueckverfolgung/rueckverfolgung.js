frappe.query_reports["Rueckverfolgung"] = {
	filters: [
		{
			fieldname: "charge",
			label: __("Charge"),
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
};
