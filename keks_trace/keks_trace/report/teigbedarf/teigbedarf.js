frappe.query_reports["Teigbedarf"] = {
	filters: [
		{ fieldname: "linie", label: __("Linie"), fieldtype: "Link", options: "Linie", reqd: 1 },
		{ fieldname: "tage", label: __("Tage voraus"), fieldtype: "Int", default: 10 },
	],
};
