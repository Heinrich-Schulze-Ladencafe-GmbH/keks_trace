import frappe
from frappe import _
from frappe.utils import flt, formatdate

from keks_trace.trace import rueckverfolgung


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.charge:
		return _spalten(), [], None

	ergebnis = rueckverfolgung(filters.charge, filters.richtung or "Vorwärts")
	daten = [
		{
			"generation": z["generation"],
			"charge": z["charge"],
			"artikel": z.get("artikel"),
			"stufe": z.get("stufe"),
			"anteil": flt(z["anteil"]) * 100,
			"herstelldatum": z.get("herstelldatum"),
			"ursprungsdatum": z.get("ursprungsdatum"),
			"verfall": z.get("verfall"),
			"bestand": z.get("bestand"),
			"lieferant": z.get("lieferant"),
		}
		for z in ergebnis["chargen"]
	]
	return _spalten(), daten, _nachricht(ergebnis)


def _spalten():
	return [
		{"fieldname": "generation", "label": _("Stufe in Kette"), "fieldtype": "Int", "width": 90},
		{"fieldname": "charge", "label": _("Charge"), "fieldtype": "Link", "options": "Batch", "width": 170},
		{"fieldname": "artikel", "label": _("Artikel"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "stufe", "label": _("Chargenstufe"), "fieldtype": "Data", "width": 120},
		{"fieldname": "anteil", "label": _("Anteil %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "herstelldatum", "label": _("Herstelldatum"), "fieldtype": "Date", "width": 110},
		{"fieldname": "ursprungsdatum", "label": _("Ursprung"), "fieldtype": "Date", "width": 110},
		{"fieldname": "verfall", "label": _("Verfall/MHD"), "fieldtype": "Date", "width": 110},
		{"fieldname": "bestand", "label": _("Bestand"), "fieldtype": "Float", "width": 90},
		{
			"fieldname": "lieferant",
			"label": _("Lieferant"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 140,
		},
	]


def _nachricht(ergebnis):
	if ergebnis["richtung"] == "Rückwärts":
		return None
	kunden = ergebnis.get("kunden") or []
	paletten = _paletten(ergebnis.get("paletten") or []) + _lagerverkauf(ergebnis.get("lagerverkauf") or [])
	if not kunden:
		return "<p>" + _("Keine Lieferungen an Kunden gefunden.") + "</p>" + paletten
	zeilen = "".join(
		f"<tr><td>{frappe.utils.escape_html(k.kundenname or k.kunde)}</td><td>{k.lieferschein}</td>"
		f"<td>{formatdate(k.lieferdatum)}</td><td>{k.charge}</td><td>{flt(k.menge, 2)}</td></tr>"
		for k in kunden
	)
	return (
		"<h5>" + _("Betroffene Lieferungen") + "</h5>"
		"<table class='table table-bordered'><thead><tr>"
		f"<th>{_('Kunde')}</th><th>{_('Lieferschein')}</th><th>{_('Datum')}</th>"
		f"<th>{_('Charge')}</th><th>{_('Menge')}</th></tr></thead><tbody>{zeilen}</tbody></table>"
	) + paletten


def _lagerverkauf(zeilen):
	if not zeilen:
		return ""
	z = "".join(
		f"<tr><td>{r.charge}</td><td>{r.lagerort}</td><td>{flt(r.verkauft, 3)}</td><td>{flt(r.bestand, 3)}</td></tr>"
		for r in zeilen
	)
	return (
		"<h5>" + _("Lagerverkauf (Endverbraucher)") + "</h5>"
		"<table class='table table-bordered'><thead><tr>"
		f"<th>{_('Los')}</th><th>{_('Lagerort')}</th><th>{_('Verkauft (kg)')}</th><th>{_('Noch vorrätig (kg)')}</th>"
		f"</tr></thead><tbody>{z}</tbody></table>"
	)


def _paletten(paletten):
	if not paletten:
		return ""
	zeilen = "".join(
		f"<tr><td>{p.palette}</td><td>{p.charge}</td><td>{p.status}</td>"
		f"<td>{flt(p.anzahl_jetzt, 3):g} {p.einheit}</td><td>{p.lieferschein or ''}</td>"
		f"<td>{frappe.utils.escape_html(p.kunde or '')}</td></tr>"
		for p in paletten
	)
	return (
		"<h5>" + _("Paletten (NVE)") + "</h5>"
		"<table class='table table-bordered'><thead><tr>"
		f"<th>{_('NVE')}</th><th>{_('Los')}</th><th>{_('Status')}</th><th>{_('Noch drauf')}</th>"
		f"<th>{_('Lieferschein')}</th><th>{_('Kunde')}</th></tr></thead><tbody>{zeilen}</tbody></table>"
	)
