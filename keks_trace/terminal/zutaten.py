"""Prüfen einer gescannten Zutat: Sperre, Verfall, Rework-Regel, FEFO."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import kennzeichnung
from keks_trace import palette as paletten
from keks_trace.install import REWORK_ZIELE
from keks_trace.terminal.basis import EPS, _fehler, _station, _vorraete
from keks_trace.terminal.bestand import _lager_chargen, _pruefe_charge, _quellen
from keks_trace.terminal.einwaage import rezept
from keks_trace.terminal.scan import aufloesen
from keks_trace.utils import artikel_stufe, einstellung

FEFO_STUFEN = ("Rohstoff", "Packmittel")


def _fefo_aeltere(artikel: str, charge: str | None, verwendet=()) -> list[dict]:
	"""FEFO: Chargen desselben Rohstoffs/Packmittels mit früherem MHD, die noch im Lager liegen.

	Nicht gezählt: gesperrte und abgelaufene Chargen, Silo/Vorrat/Linie (dort teilt das System selbst zu),
	und Chargen, die in derselben Buchung ohnehin verbraucht werden.
	"""
	if not charge or artikel_stufe(artikel) not in FEFO_STUFEN:
		return []
	eigen = frappe.db.get_value("Batch", charge, "expiry_date")
	if not eigen:
		return []
	heute, eigen = getdate(nowdate()), getdate(eigen)
	aeltere = []
	for c in _lager_chargen(artikel):
		if c["charge"] == charge or c["charge"] in verwendet:
			continue
		mhd = frappe.db.get_value("Batch", c["charge"], "expiry_date")
		if mhd and heute <= getdate(mhd) < eigen:
			aeltere.append(
				{"charge": c["charge"], "mhd": formatdate(mhd), "menge": c["menge"], "iso": str(mhd)}
			)
	aeltere.sort(key=lambda a: a["iso"])
	return [{k: v for k, v in a.items() if k != "iso"} for a in aeltere[:3]]


def _fefo_modus() -> str:
	return einstellung("fefo_rohstoffe") or "Grund Pflicht"


def _fefo_text(z: dict, aeltere: list[dict]) -> str:
	a = aeltere[0]
	return _("{0}: Charge {1} genommen, älter ist {2} (MHD {3}, {4} im Lager).").format(
		z["name"], z["charge"], a["charge"], a["mhd"], paletten._n(a["menge"], z["einheit"])
	)


def _pruefe_fefo(eingaenge: list[dict], grund: str | None) -> str | None:
	"""Abweichung von FEFO nur mit Grund. Gibt den Text fürs Protokoll zurück (None = keine Abweichung)."""
	modus = _fefo_modus()
	if modus == "Aus":
		return None
	verwendet = {z["charge"] for z in eingaenge if z.get("charge")}
	texte = []
	for z in eingaenge:
		if z.get("typ") == "silo":
			continue
		aeltere = _fefo_aeltere(z["artikel"], z.get("charge"), verwendet)
		if aeltere:
			texte.append(_fefo_text(z, aeltere))
	if not texte:
		return None
	grund = (grund or "").strip()
	if modus == "Nur Hinweis" and not grund:
		frappe.msgprint("<br>".join(texte), title=_("FEFO-Hinweis"), indicator="orange", alert=True)
		return _("Ohne Grund (Einstellung: nur Hinweis)") + "\n" + "\n".join(texte)
	if not grund:
		_fehler(
			_("Älteres MHD liegt im Lager. Bitte die ältere Charge nehmen oder einen Grund angeben.")
			+ "<br>"
			+ "<br>".join(texte)
		)
	return _("Grund: {0}").format(grund) + "\n" + "\n".join(texte)


def _pruefe_rework_fuer(rework, ziel):
	from keks_trace.rework import _pruefe_allergene

	if artikel_stufe(ziel) not in REWORK_ZIELE:
		_fehler(_("Rework darf nur in Grundteig oder veredelten Teig."))
	regel = frappe.db.get_value(
		"Rework Regel", {"rework_artikel": rework, "ziel_artikel": ziel, "aktiv": 1}, "max_anteil_prozent"
	)
	if regel is None:
		_fehler(_("Rework {0} ist für {1} nicht zugelassen (keine Rework-Regel).").format(rework, ziel))
	_pruefe_allergene(rework, ziel)
	return flt(regel)


def _zeile(code, menge, ziel=None, erlaubt=None):
	"""Löst einen Scan auf und prüft ihn als Zutat. Gibt die Buchungszeile zurück."""
	menge = flt(menge)
	if menge <= EPS:
		_fehler(_("Bitte eine Menge größer 0 eingeben."))
	r = aufloesen(code)
	if r["typ"] == "palette":
		_fehler(_("{0} ist eine Palette. Bitte das Los oder die Kiste scannen.").format(r["code"]))
	artikel = r.get("artikel")
	if not artikel:
		_fehler(_("Behälter {0} ist leer.").format(r["code"]))

	stufe = artikel_stufe(artikel)
	ist_rework = stufe == "Rework"
	max_anteil = None
	if erlaubt is not None and artikel not in erlaubt:
		if ist_rework and ziel:
			max_anteil = _pruefe_rework_fuer(artikel, ziel)
		else:
			_fehler(
				_("{0} ({1}) gehört nicht zum Rezept.").format(
					frappe.bold(frappe.get_cached_value("Item", artikel, "item_name")), artikel
				)
			)

	if r["typ"] == "silo":
		from keks_trace.silo import bestand

		frei, offen = bestand(r["lager"], now_datetime()), menge
		for c in frei:
			if offen <= EPS:
				break
			_pruefe_charge(c["charge"], artikel)
			if ziel:
				kennzeichnung.pruefe_zutat(ziel, c["charge"], artikel, r["silo"])
			offen -= c["menge"]
		if offen > EPS:
			rest = max(flt(menge - offen, 3), 0)
			if rest <= EPS and r["silo"] in _vorraete().values():
				_fehler(_("{0} ist leer. Erst einen Karton anbrechen.").format(r["silo"]))
			_fehler(
				_("Im {0} sind rechnerisch nur {1}.").format(
					r["silo"], paletten._n(rest, frappe.get_cached_value("Item", artikel, "stock_uom"))
				)
			)
	else:
		_pruefe_charge(r["charge"], artikel)
		if ziel:
			kennzeichnung.pruefe_zutat(ziel, r["charge"], artikel)
		if r["typ"] == "behaelter" and menge > flt(r["inhalt"]) * 1.005 + EPS:
			_fehler(_("Behälter {0} enthält nur {1} kg.").format(r["behaelter"], r["inhalt"]))
		if r["typ"] == "charge" and menge > flt(r["inhalt"]) + EPS:
			_fehler(_("Von Charge {0} sind nur {1} kg am Lager.").format(r["charge"], r["inhalt"]))
		if not r.get("lager"):
			_fehler(_("Charge {0} hat keinen Bestand.").format(r["charge"]))

	return {
		"code": r["code"],
		"typ": r["typ"],
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"charge": r.get("charge") if r["typ"] != "silo" else None,
		"lager": r["lager"],
		"behaelter": r.get("behaelter"),
		"silo": r.get("silo"),
		"menge": flt(menge, 3),
		"einheit": frappe.get_cached_value("Item", artikel, "stock_uom"),
		"rework": ist_rework,
		"max_anteil": max_anteil,
		# Hinweis am Terminal: ältere Chargen (die Oberfläche blendet die schon gescannten aus)
		"fefo": _fefo_aeltere(artikel, r.get("charge"))
		if r["typ"] != "silo" and _fefo_modus() != "Aus"
		else [],
		"fefo_pflicht": _fefo_modus() == "Grund Pflicht",
	}


@frappe.whitelist()
def auswahl(station: str, artikel: str) -> list[dict]:
	"""Zum Selbst-Auswählen ohne Scanner: Behälter und Chargen eines Artikels mit Menge und MHD."""
	_station(station)
	return _quellen(artikel)


@frappe.whitelist()
def vorschlag(
	station: str, ziel: str, menge: float, bevorzugt: str | None = None, kundenauftrag: str | None = None
) -> dict:
	"""Zutaten für die Sollmenge vorschlagen statt scannen: Vorrat am Tisch, Behälter (Silo/Tank) und
	sonst die älteste Ware zuerst, über mehrere Chargen bzw. Kisten verteilt. Jede Zeile ist geprüft."""
	s = _station(station)
	r = rezept(ziel, menge, s.name)
	erlaubt = {z["artikel"] for z in r["zutaten"]}
	zeilen, hinweise = [], []
	vorne = None
	if bevorzugt:  # z. B. die Kiste, die der Packer aus der Liste gewählt hat
		b = aufloesen(bevorzugt)
		vorne = (b.get("artikel"), {"code": b["code"], "menge": flt(b.get("inhalt") or 0)})
	for z in r["zutaten"]:
		quellen = (
			[{"code": z["silo"], "menge": z["menge"]}] if z["silo"] else _quellen(z["artikel"], kundenauftrag)
		)
		if vorne and vorne[0] == z["artikel"]:
			quellen = [vorne[1]] + [q for q in quellen if q["code"] != vorne[1]["code"]]
		offen = z["menge"]
		for q in quellen:
			if offen <= EPS:
				break
			m = min(offen, q["menge"])
			try:
				zeilen.append(_zeile(q["code"], m, ziel, erlaubt))
				offen -= m
			except frappe.ValidationError as e:
				hinweise.append(f"{z['name']}: {frappe.utils.strip_html(str(e))}")
				if z["silo"]:
					break
		if offen > EPS:
			hinweise.append(
				_("{0}: es fehlen {1}.").format(z["name"], paletten._n(flt(offen, 3), z["einheit"]))
			)
	frappe.local.message_log = []
	return {"zeilen": zeilen, "hinweise": hinweise}


@frappe.whitelist()
def pruefe_zeile(station: str, ziel: str, code: str, menge: float) -> dict:
	"""Sofortprüfung einer gescannten Zutat für ein Rezept (grün/rot am Terminal)."""
	_station(station)
	erlaubt = {z["artikel"] for z in rezept(ziel)["zutaten"]}
	return _zeile(code, menge, ziel, erlaubt)


@frappe.whitelist()
def fefo_pruefen(station: str, code: str) -> dict:
	"""Vor dem Zuführen: liegt vom gescannten Rohstoff/Packmittel eine Charge mit früherem MHD im Lager?

	Nur lesen. Gibt die älteren Chargen und ob ein Grund Pflicht ist (Einstellung) zurück.
	"""
	_station(station)
	modus = _fefo_modus()
	r = aufloesen(code)
	if modus == "Aus" or r["typ"] in ("silo", "palette") or not r.get("charge"):
		return {"aeltere": [], "pflicht": False}
	return {
		"aeltere": _fefo_aeltere(r["artikel"], r["charge"]),
		"pflicht": modus == "Grund Pflicht",
		"charge": r["charge"],
		"name": frappe.get_cached_value("Item", r["artikel"], "item_name"),
	}
