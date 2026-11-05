"""Stammdaten für die Oberfläche: Station, Kopfdaten, Etikettendruck, Vorräte, Silos."""

import frappe
from frappe.utils import cint, flt, formatdate, now_datetime

from keks_trace import etiketten, pruefung
from keks_trace import los as los_modul
from keks_trace import palette as paletten
from keks_trace.anfrage import einmalig
from keks_trace.terminal.basis import EPS, VORRAT, _silo_filter, _station
from keks_trace.terminal.bestand import _lager_chargen, _verkaufslager
from keks_trace.utils import VERSANDFAEHIG


@frappe.whitelist()
def stationen() -> list[dict]:
	return frappe.get_all(
		"Terminal Station", filters={"aktiv": 1}, fields=["name", "typ"], order_by="station_name"
	)


@frappe.whitelist()
def start(station: str) -> dict:
	s = _station(station)
	stufen = s.stufen_liste()
	return {
		"station": s.name,
		"typ": s.typ,
		"nutzer": frappe.session.user,
		"funktionen": s.funktionen(),
		"stufen": stufen,
		"nur_fertigware": stufen == ["Fertigware"],
		"vorschlagen": bool(s.zutaten_vorschlagen),
		"umlager_ziel": s.umlager_ziel,
		"vorraete": bool(s.f_silo and frappe.db.exists("Silo", {**_silo_filter(s), "typ": VORRAT})),
		"linie": s.linie,
		"pruefungen": pruefung.faellig(s.name),
		"drucker": etiketten.drucker_der_station(s.name),
	}


@frappe.whitelist()
@einmalig
def etikett_drucken(
	station: str,
	art: str,
	nve: str | None = None,
	codes: str | None = None,
	anzahl: int | None = None,
	grund: str | None = None,
	geprueft: str | None = None,
) -> dict:
	"""Etikett direkt auf den Netzwerkdrucker der Station (siehe etiketten.py). Einmalig: ein verlorenes
	Ergebnis und nochmal Tippen druckt nicht doppelt. Nachdruck ohne Anlass: Antwort `grund_noetig`."""
	_station(station)
	return etiketten.drucken(
		station, art, nve=nve, codes=codes, anzahl=anzahl, grund=grund, geprueft=geprueft
	)


@frappe.whitelist()
@einmalig
def etikett_vormerken(
	station: str,
	art: str,
	nve: str | None = None,
	codes: str | None = None,
	anzahl: int | None = None,
	grund: str | None = None,
	geprueft: str | None = None,
) -> dict:
	"""Browserdruck: vor dem Öffnen der Druckseite Grund prüfen und den Druck protokollieren."""
	_station(station)
	return etiketten.vormerken(
		station, art, nve=nve, codes=codes, anzahl=anzahl, grund=grund, geprueft=geprueft
	)


@frappe.whitelist()
def kopfdaten(station: str) -> dict:
	"""Für die Statusleiste: Serverzeit, KW, Los des Tages, Benutzer, laufender Auftrag, nächste Prüfung."""
	s = _station(station)
	jetzt = now_datetime()
	tage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
	daten = {
		"zeit": jetzt.isoformat(),
		"datum_text": f"{tage[jetzt.weekday()]} {jetzt.strftime('%d.%m.%Y')}",
		"kw": jetzt.isocalendar()[1],
		"los": los_modul.jwwt(jetzt.date()) if los_modul.format_() == "JWWT" else None,
		"benutzer": frappe.utils.get_fullname(frappe.session.user),
		"station": s.name,
		"auftrag": None,
		"pruefung": None,
	}
	if s.f_linie and s.aktueller_auftrag:
		pa = frappe.db.get_value(
			"Produktionsauftrag",
			s.aktueller_auftrag,
			["name", "artikel", "menge_kg", "gebucht_kg", "status"],
			as_dict=True,
		)
		if pa and pa.status == "Läuft":
			from keks_trace.linienbuchung import _menge_text

			daten["auftrag"] = (
				f"{pa.name} · {frappe.get_cached_value('Item', pa.artikel, 'item_name')} · "
				f"{_menge_text(pa.artikel, pa.gebucht_kg)} von {_menge_text(pa.artikel, pa.menge_kg)}"
			)
	try:
		liste = pruefung.faellig(s.name)
	except Exception:
		liste = []
	if liste:
		faellig = [p for p in liste if p["faellig"]]
		if faellig:
			daten["pruefung"] = {
				"text": f"{faellig[0]['titel']} fällig",
				"art": "rot" if faellig[0]["sperrt"] else "orange",
			}
		else:
			p = min(liste, key=lambda x: x["in_minuten"])
			daten["pruefung"] = {
				"text": f"{p['titel']} in {p['in_minuten']} min",
				"art": "orange" if p["bald"] else "",
			}
	return daten


@frappe.whitelist()
def pruefungen_faellig(station: str) -> list[dict]:
	return pruefung.faellig(_station(station).name)


@frappe.whitelist()
@einmalig
def pruefung_erfassen(station: str, pruefplan: str, eingabe, bemerkung: str | None = None) -> dict:
	s = _station(station)
	return pruefung.erfassen(s.name, pruefplan, eingabe, bemerkung)


@frappe.whitelist()
def fertigware_im_lager(station: str, aus_verkauf: int = 0) -> list[dict]:
	"""Fertigware mit Bestand im Lager (ohne Lagerverkauf), je Los lose und je Palette: zum Antippen.

	aus_verkauf=1: was im Lagerverkauf liegt (für die Rücknahme ins Lager).
	"""
	_station(station)
	verkauf = list(_verkaufslager()) or [""]
	bedingung = "sbe.warehouse in %(v)s" if cint(aus_verkauf) else "sbe.warehouse not in %(v)s"
	zeilen = frappe.db.sql(
		f"""
		select sbe.batch_no as charge, b.item as artikel, b.item_name as name, b.kt_los as los,
			b.expiry_date as mhd, sum(sbe.qty) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabBatch` b on b.name = sbe.batch_no
		where sbb.is_cancelled = 0 and sbb.docstatus = 1 and b.kt_chargen_stufe in %(stufen)s
			and ifnull(b.kt_status, '') != 'Gesperrt' and {bedingung} and sbe.warehouse not in %(linie)s
		group by sbe.batch_no, b.item, b.item_name, b.kt_los, b.expiry_date
		having sum(sbe.qty) > 0.0001
		order by b.item_name, b.expiry_date, b.creation
		limit 300
		""",
		{
			"v": tuple(verkauf),
			"stufen": VERSANDFAEHIG,
			"linie": tuple(frappe.get_all("Linie", pluck="lagerort")) or ("",),
		},
		as_dict=True,
	)
	auf_pal = {}
	for p in paletten.paletten_fuer([z.charge for z in zeilen]):
		if p.anzahl_jetzt > EPS and p.status in paletten.AKTIV:
			auf_pal.setdefault(p.charge, []).append(p)
	ergebnis = []
	for z in zeilen:
		basis = {"artikel": z.artikel, "name": z.name, "charge": z.charge, "los": z.los or z.charge,
		         "mhd": formatdate(z.mhd) if z.mhd else ""}  # fmt: skip
		lose = paletten.lose(z.charge)
		if lose > EPS:
			ergebnis.append({**basis, "wo": "lose", "menge_text": paletten.zerlegen(z.artikel, lose)})
		for p in auf_pal.get(z.charge, []):
			ergebnis.append(
				{**basis, "wo": "Palette …" + p.palette[-6:], "palette": p.palette,
				 "menge_text": paletten._n(p.anzahl_jetzt, p.einheit)}
			)  # fmt: skip
	return ergebnis


@frappe.whitelist()
def registrierungen(
	station: str, kundenauftrag: str | None = None, produktionsauftrag: str | None = None, anzahl: int = 30
) -> list[dict]:
	"""Was zu einem Auftrag schon gebucht wurde (wie „Registrierungen“ bei FOBIS), neueste zuerst."""
	_station(station)
	if not (kundenauftrag or produktionsauftrag):
		return []
	feld = "kt_kundenauftrag" if kundenauftrag else "kt_produktionsauftrag"
	zeilen = frappe.db.sql(
		f"""
		select se.name as buchung, se.posting_date as datum, se.posting_time as zeit, se.kt_station as station,
			sed.item_code as artikel, sed.batch_no as charge, sed.transfer_qty as menge, b.kt_los as los,
			b.expiry_date as mhd
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name and sed.is_finished_item = 1
		left join `tabBatch` b on b.name = sed.batch_no
		where se.docstatus = 1 and se.{feld} = %(auftrag)s and se.purpose = 'Manufacture'
			and b.kt_chargen_stufe in ('Fertigware', 'Ware lose')
		order by se.posting_date desc, se.posting_time desc
		limit %(n)s
		""",
		{"auftrag": kundenauftrag or produktionsauftrag, "n": cint(anzahl)},
		as_dict=True,
	)
	return [
		{
			"buchung": z.buchung,
			"wann": f"{formatdate(z.datum)} {str(z.zeit)[:5]}",
			"station": z.station,
			"los": z.los or z.charge,
			"charge": z.charge,
			"mhd": formatdate(z.mhd) if z.mhd else "",
			"menge_text": paletten.zerlegen(z.artikel, z.menge),
		}
		for z in zeilen
	]


@frappe.whitelist()
def vorraete(station: str) -> list[dict]:
	"""Offene Vorräte am Tisch mit der Charge, die gerade dran ist."""
	from keks_trace.silo import bestand

	s = _station(station)
	jetzt = now_datetime()
	ergebnis = []
	for v in frappe.get_all(
		"Silo",
		filters={**_silo_filter(s), "typ": VORRAT},
		fields=["name", "artikel", "warehouse"],
		order_by="name",
	):
		chargen = bestand(v.warehouse, jetzt)
		ergebnis.append(
			{
				"vorrat": v.name,
				"artikel": v.artikel,
				"name": frappe.get_cached_value("Item", v.artikel, "item_name"),
				"einheit": frappe.get_cached_value("Item", v.artikel, "stock_uom"),
				"chargen": [{"charge": c["charge"], "menge": flt(c["menge"], 3)} for c in chargen],
				"bestand": flt(sum(c["menge"] for c in chargen), 3),
			}
		)
	return ergebnis


@frappe.whitelist()
def lager_chargen(station: str, artikel: str) -> list[dict]:
	"""Chargen eines Artikels mit Bestand im Lager, ältestes MHD zuerst (zum Antippen ohne Scanner)."""
	_station(station)
	return _lager_chargen(artikel)


@frappe.whitelist()
def rework_artikel() -> list[dict]:
	return frappe.get_all(
		"Item",
		filters={"kt_chargen_stufe": "Rework", "disabled": 0},
		fields=["name as artikel", "item_name as name", "kt_allergengruppe as allergengruppe"],
		order_by="item_name",
	)


@frappe.whitelist()
def kunden() -> list[dict]:
	return frappe.get_all(
		"Customer",
		filters={"disabled": 0},
		fields=["name", "customer_name"],
		order_by="customer_name",
		limit=10000,
	)


@frappe.whitelist()
def silos(station: str | None = None) -> list[dict]:
	"""Silos, Tanks und Vorräte zum Leer melden; mit Station nur die, die sie sieht (ihre Linie)."""
	from keks_trace.silo import bestand

	jetzt = now_datetime()
	ergebnis = []
	filters = _silo_filter(_station(station)) if station else {"aktiv": 1}
	for s in frappe.get_all(
		"Silo", filters=filters, fields=["name", "typ", "artikel", "warehouse"], order_by="name"
	):
		ergebnis.append(
			{
				"silo": s.name,
				"typ": s.typ,
				"artikel": s.artikel,
				"einheit": frappe.get_cached_value("Item", s.artikel, "stock_uom"),
				"bestand": flt(sum(c["menge"] for c in bestand(s.warehouse, jetzt)), 3),
			}
		)
	return ergebnis


@frappe.whitelist()
def einheiten(artikel: str) -> list[dict]:
	return paletten.einheiten(artikel)
