frappe.query_reports["Mengenbilanz"] = {
	filters: [
		{
			fieldname: "charge",
			label: __("Charge"),
			fieldtype: "Link",
			options: "Batch",
			reqd: 1,
		},
	],
};
