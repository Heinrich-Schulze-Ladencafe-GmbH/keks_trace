frappe.query_reports["Reichweite Rohstoffe"] = {
	filters: [
		{
			fieldname: "stufe",
			label: __("Stufe"),
			fieldtype: "Select",
			options: "Rohstoff\nPackmittel\nRohstoff und Packmittel",
			default: "Rohstoff",
		},
		{ fieldname: "tage", label: __("Verbrauch der letzten Tage"), fieldtype: "Int", default: 60 },
		{ fieldname: "artikel", label: __("Artikel"), fieldtype: "Link", options: "Item" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "reicht_tage" && data && data.reicht_tage !== null && data.reicht_tage < 14) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
