frappe.query_reports["MHD Rohstoffe"] = {
	filters: [
		{
			fieldname: "stufe",
			label: __("Stufe"),
			fieldtype: "Select",
			options: "Rohstoff\nPackmittel\nRohstoff und Packmittel",
			default: "Rohstoff",
		},
		{ fieldname: "tage", label: __("MHD in den nächsten Tagen"), fieldtype: "Int", default: 60 },
		{ fieldname: "verbrauch_tage", label: __("Verbrauch der letzten Tage"), fieldtype: "Int", default: 60 },
		{ fieldname: "artikel", label: __("Artikel"), fieldtype: "Link", options: "Item" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const rot = (column.fieldname === "tage_bis_mhd" && data.tage_bis_mhd < 0) || (column.fieldname === "uebrig" && data.uebrig > 0);
		return rot ? `<span style="color: var(--red-600); font-weight: 600">${value}</span>` : value;
	},
};
