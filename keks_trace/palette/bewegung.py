"""Paletten: anlegen, beladen, umpacken, schließen, öffnen, Korrektur (unveränderbare Bewegungen)."""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from keks_trace.palette.basis import AKTIV, EPS, _fehler
from keks_trace.palette.bestand import (
	_offen,
	_status_pruefen,
	_summe_text,
	etikett_aktuell,
	info,
	inhalt,
	kartons,
	lose,
)
from keks_trace.palette.einheit import faktor
from keks_trace.palette.nve import nve_neu, standard_kreis
from keks_trace.utils import versandfaehig


def _bewegung(
	palette, richtung, art, charge, anzahl, einheit, station=None, beleg_typ=None, beleg=None, gegen=None
):
	artikel = frappe.db.get_value("Batch", charge, "item")
	frappe.get_doc(
		{
			"doctype": "Paletten Bewegung",
			"palette": palette,
			"richtung": richtung,
			"art": art,
			"charge": charge,
			"artikel": artikel,
			"anzahl": flt(anzahl, 6),
			"einheit": einheit,
			"menge": flt(flt(anzahl) * faktor(artikel, einheit), 6),
			"gegen_palette": gegen,
			"station": station,
			"beleg_typ": beleg_typ,
			"beleg": beleg,
			"zeitpunkt": now_datetime(),
			"nutzer": frappe.session.user,
		}
	).insert(ignore_permissions=True)
	if richtung == "Abgang":
		_etikett_hinweis(palette)


def _etikett_hinweis(palette):
	"""Kartons von einer etikettierten Palette genommen: Etikett stimmt nicht mehr (statt Zahl von Hand korrigieren)."""
	gemeldet = frappe.flags.setdefault("kt_etikett_hinweis", set())
	if palette in gemeldet:
		return
	pos = inhalt(palette)
	if pos and etikett_aktuell(palette, pos) is False:
		gemeldet.add(palette)
		frappe.msgprint(
			_("Palette {0}: Inhalt geändert ({1}). Etikett neu drucken.").format(palette, _summe_text(pos)),
			title=_("Etikett"),
			indicator="orange",
			alert=True,
		)


def anlegen(
	typ: str = "Lagerpalette", station: str | None = None, kunde: str | None = None, kreis: str | None = None
) -> str:
	kreis = kreis or standard_kreis()
	nve, test = nve_neu(kreis)
	frappe.get_doc(
		{
			"doctype": "Palette",
			"nve": nve,
			"typ": typ,
			"status": "Offen",
			"station": station,
			"kunde": kunde,
			"test_nve": 1 if test else 0,
			"nve_kreis": kreis,
		}
	).insert(ignore_permissions=True)
	return nve


def beladen(
	palette, charge, anzahl, einheit, station=None, art="Beladen", beleg_typ=None, beleg=None
) -> dict:
	"""Lose Kartons eines Loses auf eine Palette."""
	artikel = frappe.db.get_value("Batch", charge, "item")
	if not artikel:
		_fehler(_("Charge {0} gibt es nicht.").format(charge))
	if not versandfaehig(artikel):
		_fehler(_("Auf Paletten kommen nur Fertigware und lose Ware im Karton, nicht {0}.").format(artikel))
	anzahl = flt(anzahl)
	if anzahl <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	_offen(palette)
	menge = anzahl * faktor(artikel, einheit)
	frei = lose(charge)
	if menge > frei + 1e-4:
		_fehler(
			_("Von Los {0} sind nur noch {1} {2} lose (nicht auf einer Palette).").format(
				charge, _anzahl_text(artikel, frei, einheit), einheit
			)
		)
	_bewegung(palette, "Zugang", art, charge, anzahl, einheit, station, beleg_typ, beleg)
	i = info(palette)
	_hinweis_fuellung(i)
	return i


def _hinweis_fuellung(i):
	f = i.get("fuellung")
	if not f:
		return
	if f["ueber"]:
		frappe.msgprint(
			_("Palette {0} ist überladen ({1} %). Bitte Kartons auf eine neue Palette.").format(
				i["nve"], round(f["anteil"] * 100)
			),
			indicator="orange",
			alert=True,
		)
	elif f["voll"]:
		frappe.msgprint(
			_("Palette {0} ist voll. Schließen, Etikett anbringen, neue Palette beginnen.").format(i["nve"]),
			indicator="green",
			alert=True,
		)


def _anzahl_text(artikel, menge, einheit):
	return f"{flt(menge / faktor(artikel, einheit), 3):g}"


def _position(palette, charge, einheit):
	for x in inhalt(palette):
		if x["charge"] == charge and x["einheit"] == einheit:
			return x
	return None


def umpacken(von, nach, charge, anzahl, einheit, station=None) -> dict:
	"""Kartons von einer Palette auf eine andere (Anbrechen, Kommissionieren)."""
	if von == nach:
		_fehler(_("Quelle und Ziel sind dieselbe Palette."))
	anzahl = flt(anzahl)
	pos = _position(von, charge, einheit)
	if not pos or anzahl > pos["anzahl"] + EPS:
		_fehler(
			_("Auf Palette {0} sind von Los {1} nur {2} {3}.").format(
				von, charge, flt(pos["anzahl"], 3) if pos else 0, einheit
			)
		)
	if anzahl <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	if frappe.db.get_value("Palette", von, "status") not in AKTIV:
		_fehler(_("Palette {0} ist nicht mehr im Lager.").format(von))
	_offen(nach)
	_bewegung(von, "Abgang", "Umpacken", charge, anzahl, einheit, station, gegen=nach)
	_bewegung(nach, "Zugang", "Umpacken", charge, anzahl, einheit, station, gegen=von)
	_status_pruefen(von)
	i = info(nach)
	_hinweis_fuellung(i)
	return i


def schliessen(palette) -> dict:
	if frappe.db.get_value("Palette", palette, "status") == "Offen":
		frappe.db.set_value(
			"Palette", palette, "status", "Geschlossen" if inhalt(palette) or kartons(palette) else "Leer"
		)
	return info(palette)


def oeffnen(palette) -> dict:
	if frappe.db.get_value("Palette", palette, "status") in ("Geschlossen", "Leer"):
		frappe.db.set_value("Palette", palette, "status", "Offen")
	return info(palette)


@frappe.whitelist()
def korrektur(palette: str, charge: str, anzahl: float, einheit: str, richtung: str, grund: str) -> dict:
	"""Inhalt einer Palette nach Zählung korrigieren (nur Lagerleitung/QS)."""
	if not set(frappe.get_roles()) & {"Stock Manager", "Quality Manager", "System Manager"}:
		frappe.throw(_("Nur Lagerleitung oder QS darf Paletten korrigieren."), frappe.PermissionError)
	if not grund:
		_fehler(_("Bitte einen Grund angeben."))
	if richtung == "Zugang":
		beladen(palette, charge, anzahl, einheit, art="Korrektur")
	else:
		pos = _position(palette, charge, einheit)
		if not pos or flt(anzahl) > pos["anzahl"] + EPS:
			_fehler(_("So viel ist nicht auf der Palette."))
		_bewegung(palette, "Abgang", "Korrektur", charge, anzahl, einheit)
		_status_pruefen(palette)
	frappe.get_doc("Palette", palette).add_comment("Comment", _("Korrektur: {0}").format(grund))
	return info(palette)
