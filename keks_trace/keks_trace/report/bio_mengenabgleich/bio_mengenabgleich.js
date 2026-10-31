frappe.query_reports["Bio Mengenabgleich"] = {
	filters: [
		{
			fieldname: "von",
			label: __("Von"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "bis",
			label: __("Bis"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
	],
};
