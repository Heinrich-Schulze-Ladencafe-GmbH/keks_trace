"""Prüfungen nach Prüfplan (CP/CCP aus der HACCP) am Terminal.

Drei Auslöser:
- „Regelmäßig an der Station“ (z. B. Metalldetektor stündlich): das Terminal zeigt, wann sie fällig
  ist. Bei Abweichung werden alle Chargen gesperrt, die an der Station seit der letzten bestandenen
  Prüfung hergestellt wurden. Optional sperrt eine überfällige Prüfung das Buchen an der Station.
- „Beim Herstellen“ (z. B. Brix je Kochung): der Wert wird mit der Fertigung erfasst, bei
  Abweichung wird die neue Charge gesperrt.
- „Beim Wareneingang“ (z. B. Temperatur Kühlware): bei Abweichung wird die Annahme verweigert
  (nichts gebucht, aber protokolliert) oder die Charge gesperrt.

Jede Prüfung wird unveränderbar protokolliert (Pruefung).
"""

import json
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

REGEL = "Regelmäßig an der Station"
HERSTELLEN = "Beim Herstellen"
WARENEINGANG = "Beim Wareneingang"
UMSTELLUNG = "Bei Umstellung auf Bio"


class PruefFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, PruefFehler, title=_("Prüfung"))


# ---------------------------------------------------------------------------
# Welche Prüfungen gelten?
# ---------------------------------------------------------------------------


def _plaene(ausloeser):
	return [
		frappe.get_cached_doc("Pruefplan", n)
		for n in frappe.get_all("Pruefplan", filters={"aktiv": 1, "ausloeser": ausloeser}, pluck="name")
	]


def fuer_artikel(ausloeser: str, artikel: str) -> list:
	"""Prüfpläne, die beim Herstellen bzw. Wareneingang dieses Artikels abgefragt werden."""
	return [p for p in _plaene(ausloeser) if not p.artikel or artikel in {a.artikel for a in p.artikel}]


def fuer_umstellung(station: str, ziel: str) -> list:
	"""Prüfungen vor Bio-Herstellung, wenn an der Station zuletzt konventionell produziert wurde."""
	from keks_trace.kennzeichnung import umstellung_noetig

	if not station or not umstellung_noetig(station, ziel):
		return []
	return [p for p in _plaene(UMSTELLUNG) if not p.stationen or station in {x.station for x in p.stationen}]


def fuer_herstellen(ziel: str, station: str | None = None) -> list:
	return fuer_artikel(HERSTELLEN, ziel) + fuer_umstellung(station, ziel)


def fuer_station(station) -> list:
	s = frappe.get_cached_doc("Terminal Station", station)
	return [
		p
		for p in _plaene(REGEL)
		if (station in {x.station for x in p.stationen}) or (not p.stationen and s.f_herstellen)
	]


def _letzte_ok(plan, station):
	return frappe.db.get_value(
		"Pruefung",
		{"pruefplan": plan, "station": station, "ergebnis": "OK"},
		"zeitpunkt",
		order_by="zeitpunkt desc",
	)


def _zuletzt_abweichung(plan, station) -> bool:
	return (
		frappe.db.get_value(
			"Pruefung",
			{"pruefplan": plan, "station": station},
			"ergebnis",
			order_by="zeitpunkt desc, creation desc",
		)
		== "Abweichung"
	)


def faellig(station: str) -> list[dict]:
	"""Regelmäßige Prüfungen der Station mit Fälligkeit (für das Terminal)."""
	jetzt = now_datetime()
	ergebnis = []
	for p in fuer_station(station):
		letzte = _letzte_ok(p.name, station)
		faellig_ab = (get_datetime(letzte) + timedelta(minutes=p.intervall_minuten)) if letzte else None
		if _zuletzt_abweichung(p.name, station):
			faellig_ab = None  # nach einer Abweichung sofort wieder fällig, bis sie bestanden ist
		ergebnis.append(
			{
				**beschreibung(p),
				"letzte_ok": letzte.strftime("%H:%M") if letzte else None,
				"faellig_ab": faellig_ab.strftime("%H:%M") if faellig_ab else None,
				"faellig": faellig_ab is None or jetzt >= faellig_ab,
				"bald": bool(faellig_ab and jetzt < faellig_ab <= jetzt + timedelta(minutes=10)),
				"sperrt": bool(p.sperrt_wenn_faellig),
			}
		)
	reihenfolge = {"CCP": 0, "CP": 1, "GHP": 2}
	return sorted(ergebnis, key=lambda f: (not f["sperrt"], reihenfolge.get(f["lenkung"], 9), f["titel"]))


def beschreibung(p) -> dict:
	return {
		"pruefplan": p.name,
		"titel": p.titel,
		"lenkung": p.lenkung,
		"art": p.art,
		"frage": p.frage or p.titel,
		"einheit": p.einheit,
		"min": p.grenze("min_wert"),
		"max": p.grenze("max_wert"),
		"grenzwert": grenzwert_text(p),
		"pruefkoerper": p.koerper(),
		"bei_abweichung": p.bei_abweichung,
		"korrektur": p.korrekturmassnahme,
	}


def _zahl(x):
	return f"{x:g}".replace(".", ",")


def grenzwert_text(p) -> str:
	if p.art == "Messwert":
		lo, hi, e = p.grenze("min_wert"), p.grenze("max_wert"), (p.einheit or "")
		if lo is not None and hi is not None:
			return f"{_zahl(lo)} bis {_zahl(hi)} {e}".strip()
		if hi is not None:
			return f"höchstens {_zahl(hi)} {e}".strip()
		return f"mindestens {_zahl(lo)} {e}".strip()
	if p.art == "Prüfkörper":
		return _("alle erkannt: {0}").format(", ".join(p.koerper()))
	return _("in Ordnung")


def sperrende_faelle(station: str) -> list[str]:
	"""Überfällige Prüfungen, die das Buchen sperren."""
	return [f["titel"] for f in faellig(station) if f["faellig"] and f["sperrt"]]


def pruefe_station_frei(station: str):
	offen = sperrende_faelle(station)
	if offen:
		_fehler(
			_("Erst die Prüfung durchführen: {0}. Bis dahin ist Buchen an dieser Station gesperrt.").format(
				", ".join(offen)
			)
		)


# ---------------------------------------------------------------------------
# Bewerten und protokollieren
# ---------------------------------------------------------------------------


def _werte(eingabe):
	if isinstance(eingabe, str):
		eingabe = json.loads(eingabe or "{}")
	return frappe._dict(eingabe or {})


def bewerten(p, eingabe) -> tuple[bool, dict]:
	"""Gibt (ok, Felder fürs Protokoll) zurück. eingabe: {"wert"} | {"ok"} | {"koerper": {name: bool}}."""
	e = _werte(eingabe)
	felder = {"grenzwert": grenzwert_text(p)}
	if p.art == "Messwert":
		if e.get("wert") in (None, ""):
			_fehler(_("Bitte den Messwert für „{0}“ eingeben.").format(p.titel))
		w = flt(str(e.wert).replace(",", "."))
		lo, hi = p.grenze("min_wert"), p.grenze("max_wert")
		ok = (lo is None or w >= lo - 1e-9) and (hi is None or w <= hi + 1e-9)
		felder.update({"wert": w, "einheit": p.einheit})
		return ok, felder
	if p.art == "Prüfkörper":
		koerper = e.get("koerper") or {}
		fehlend = [k for k in p.koerper() if k not in koerper]
		if fehlend:
			_fehler(
				_("Bitte für jeden Prüfkörper angeben, ob er erkannt wurde: {0}").format(", ".join(fehlend))
			)
		felder["details"] = "\n".join(
			f"{k}: {'erkannt' if koerper[k] else 'NICHT erkannt'}" for k in p.koerper()
		)
		return all(bool(koerper[k]) for k in p.koerper()), felder
	if e.get("ok") is None:
		_fehler(_("Bitte „in Ordnung“ oder „nicht in Ordnung“ für „{0}“ angeben.").format(p.titel))
	return bool(e.ok), felder


def protokoll(
	p, ok, felder, station=None, charge=None, beleg=None, folge=None, gesperrt=None, bemerkung=None
):
	doc = frappe.get_doc(
		{
			"doctype": "Pruefung",
			"pruefplan": p.name,
			"lenkung": p.lenkung,
			"ergebnis": "OK" if ok else "Abweichung",
			"station": station,
			"zeitpunkt": now_datetime(),
			"nutzer": frappe.session.user,
			"charge": charge,
			"beleg": beleg,
			"folge": folge,
			"gesperrte_chargen": "\n".join(gesperrt or []) or None,
			"bemerkung": bemerkung,
			**felder,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _sperren(chargen, grund, vorgang):
	from keks_trace.sperre import _setze

	gesperrt = []
	for c in chargen:
		if frappe.db.get_value("Batch", c, "kt_status") != "Gesperrt":
			_setze(c, "Gesperrt", grund, vorgang)
			gesperrt.append(c)
	return gesperrt


def chargen_seit(station, seit) -> list[str]:
	"""Chargen, die an der Station seit dem Zeitpunkt hergestellt wurden (Ausgänge der Buchungen)."""
	bedingung = "and timestamp(se.posting_date, se.posting_time) >= %(seit)s" if seit else ""
	zeilen = frappe.db.sql(
		f"""
		select distinct ifnull(nullif(sed.batch_no, ''), sbe.batch_no) as charge
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name
		left join `tabSerial and Batch Entry` sbe on sbe.parent = sed.serial_and_batch_bundle
		where se.docstatus = 1 and se.kt_station = %(station)s
			and se.purpose in ('Manufacture', 'Repack') and ifnull(sed.t_warehouse, '') != ''
			{bedingung}
		""",
		# Buchungszeiten haben ganze Sekunden: auf die Sekunde abrunden, sonst fiele eine Buchung
		# in derselben Sekunde wie die letzte bestandene Prüfung heraus
		{"station": station, "seit": get_datetime(seit).replace(microsecond=0) if seit else None},
		as_dict=True,
	)
	return sorted({z.charge for z in zeilen if z.charge})


@frappe.whitelist()
def erfassen(station: str, pruefplan: str, eingabe, bemerkung: str | None = None) -> dict:
	"""Regelmäßige Prüfung an der Station erfassen."""
	p = frappe.get_cached_doc("Pruefplan", pruefplan)
	if p.ausloeser != REGEL:
		_fehler(_("{0} wird nicht regelmäßig an der Station erfasst.").format(p.titel))
	ok, felder = bewerten(p, eingabe)
	gesperrt, folge = [], None
	if not ok:
		if not (bemerkung or "").strip():
			_fehler(_("Abweichung: bitte die Korrekturmaßnahme bzw. Bemerkung eintragen."))
		if p.bei_abweichung == "Sperren":
			seit = _letzte_ok(p.name, station)
			vorgang = "PR-" + now_datetime().strftime("%Y%m%d-%H%M%S")
			gesperrt = _sperren(
				chargen_seit(station, seit),
				_("{0} ({1}) nicht bestanden an {2}").format(p.titel, p.lenkung, station),
				vorgang,
			)
			folge = _("{0} Charge(n) gesperrt (seit der letzten bestandenen Prüfung)").format(len(gesperrt))
		else:
			folge = _("dokumentiert")
	doc = protokoll(p, ok, felder, station=station, folge=folge, gesperrt=gesperrt, bemerkung=bemerkung)
	return {"pruefung": doc.name, "ok": ok, "gesperrt": gesperrt, "folge": folge}


def bei_buchung(ausloeser, artikel, eingaben, station=None):
	"""Prüfungen, die mit einer Buchung erfasst werden, bewerten (vor dem Buchen).

	Gibt Liste (plan, ok, felder) zurück. Fehlt eine Eingabe, kommt eine Fehlermeldung.
	"""
	eingaben = _werte(eingaben)
	plaene = (
		fuer_herstellen(artikel, station) if ausloeser == HERSTELLEN else fuer_artikel(ausloeser, artikel)
	)
	return [(p, *bewerten(p, eingaben.get(p.name))) for p in plaene]


def nach_buchung(ergebnisse, station, charge, beleg) -> list[str]:
	"""Protokollieren und bei Abweichung die neue Charge sperren. Gibt Hinweise zurück."""
	hinweise = []
	for p, ok, felder in ergebnisse:
		gesperrt, folge = [], None
		if not ok:
			if p.bei_abweichung in ("Sperren", "Annahme verweigern"):
				gesperrt = _sperren(
					[charge], _("{0}: Abweichung ({1})").format(p.titel, felder.get("grenzwert")), beleg
				)
				folge = _("Charge gesperrt")
			else:
				folge = _("dokumentiert")
			hinweise.append(
				_("Prüfung {0} nicht bestanden ({1}). {2}.").format(p.titel, felder.get("grenzwert"), folge)
			)
		protokoll(p, ok, felder, station=station, charge=charge, beleg=beleg, folge=folge, gesperrt=gesperrt)
	return hinweise


def verweigert(ergebnisse) -> list:
	"""Prüfungen mit Abweichung, bei denen die Annahme verweigert wird."""
	return [(p, ok, f) for p, ok, f in ergebnisse if not ok and p.bei_abweichung == "Annahme verweigern"]


def verweigern_herstellen(ergebnisse, station, text):
	"""Herstellen nicht buchen, weil eine Prüfung nicht bestanden ist (z. B. Linie nicht gereinigt).

	Die Prüfung wird trotzdem protokolliert (eigene Transaktion), dann kommt die Fehlermeldung.
	"""
	abgelehnt = verweigert(ergebnisse)
	if not abgelehnt:
		return
	for p, ok, felder in ergebnisse:
		protokoll(
			p, ok, felder, station=station, folge=_("nicht gebucht") if not ok else None, bemerkung=text
		)
	if not frappe.flags.in_test:
		frappe.db.commit()  # Nachweis bleibt, auch wenn die Buchung abgebrochen wird
	gruende = "; ".join(
		f"{p.titel}" + (f": {p.korrekturmassnahme}" if p.korrekturmassnahme else "")
		for p, _o, _f in abgelehnt
	)
	_fehler(_("Nicht gebucht, Prüfung nicht bestanden: {0}").format(gruende))
