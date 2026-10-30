import frappe
from frappe import _
from frappe.utils import flt

from keks_trace.bilanz import mengenbilanz


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.charge:
		return _spalten(), [], None
	b = mengenbilanz(filters.charge)
	daten = [
		{
			"zeitpunkt": x["zeitpunkt"],
			"kategorie": x["kategorie"],
			"beleg_typ": x["beleg_typ"],
			"beleg": x["beleg"],
			"lager": x["lager"],
			"menge": x["menge"],
		}
		for x in b["bewegungen"]
	]
	return _spalten(), daten, _nachricht(b)


def _spalten():
	return [
		{"fieldname": "zeitpunkt", "label": _("Zeitpunkt"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "kategorie", "label": _("Kategorie"), "fieldtype": "Data", "width": 190},
		{
			"fieldname": "beleg_typ",
			"label": _("Belegart"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 120,
		},
		{
			"fieldname": "beleg",
			"label": _("Beleg"),
			"fieldtype": "Dynamic Link",
			"options": "beleg_typ",
			"width": 180,
		},
		{
			"fieldname": "lager",
			"label": _("Lager"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 160,
		},
		{"fieldname": "menge", "label": _("Menge"), "fieldtype": "Float", "width": 100},
	]


def _nachricht(b):
	e = b["einheit"] or ""
	zeilen = [
		(_("Zugang"), b["zugang"]),
		(_("Abgang"), b["abgang"]),
		(_("Inventurkorrektur"), b["inventur"]),
		(_("Bestand"), b["bestand"]),
		(_("Differenz Lager"), b["differenz_lager"]),
		(_("Verbraucht laut Lager"), b["verbraucht_lager"]),
		(_("Verbraucht laut Genealogie"), b["verbraucht_genealogie"]),
		(_("Differenz Genealogie"), b["differenz_genealogie"]),
	]
	if b["ausbeute_prozent"] is not None:
		zeilen.append((_("Ausbeute (Ausbringung / Einsatz)"), f"{b['ausbeute_prozent']} %"))
	tabelle = "".join(
		f"<tr><td>{k}</td><td style='text-align:right'>{v if isinstance(v, str) else flt(v, 3)} {'' if isinstance(v, str) else e}</td></tr>"
		for k, v in zeilen
	)
	status = (
		_("Mengenbilanz geht auf") if b["ok"] else _("Abweichung: {0}").format("; ".join(b["abweichungen"]))
	)
	farbe = "green" if b["ok"] else "red"
	return (
		f"<p><b style='color:{farbe}'>{status}</b></p>"
		f"<table class='table table-bordered' style='max-width:520px'>{tabelle}</table>"
	)
