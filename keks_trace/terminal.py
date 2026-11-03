"""Schnittstelle für die Terminals (Backstube, Verpackung, Lager, Versand).

Jedes Terminal ist als seine Station angemeldet. Gescannt wird mit dem Handscanner als
Tastatureingabe: ein Code ist ein Behälter, ein Silo/Tank oder eine Charge.

Die Prüfungen am Terminal (pruefe_zeile) geben sofort grün oder rot. Beim Buchen laufen
zusätzlich alle Regeln aus keks_trace.pruefungen (Rework-Anteil, FIFO, Vollständigkeit, ...).
Die Daten vom Terminal werden beim Buchen serverseitig neu aufgelöst, nie blind übernommen.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import akte as akte_modul
from keks_trace import etiketten, gs1, kennzeichnung, pruefung
from keks_trace import los as los_modul
from keks_trace import palette as paletten
from keks_trace.anfrage import einmalig
from keks_trace.install import REWORK_ZIELE
from keks_trace.utils import VERSANDFAEHIG, allergene, artikel_stufe, einstellung, versandfaehig

EPS = 1e-6


class TerminalFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, TerminalFehler, title=_("Nicht möglich"))


def _silo_je_artikel():
	"""Artikel -> Silo (bei mehreren Silos für einen Artikel das zuletzt angelegte)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all(
			"Silo", filters={"aktiv": 1}, fields=["name", "artikel"], order_by="creation asc"
		)
	}


VORRAT = "Vorrat am Tisch"


def _vorraete():
	"""Artikel -> Vorrat am Tisch (offener Karton, Rolle, Behälter ohne Code)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all("Silo", filters={"aktiv": 1, "typ": VORRAT}, fields=["name", "artikel"])
	}


def _silo_filter(s) -> dict:
	"""Behälter, die eine Station sieht: die ihrer Linie; Stationen ohne Linie die ohne Linie."""
	return {"aktiv": 1, "linie": s.linie if s.linie else ["is", "not set"]}


def _station(station):
	if not station or not frappe.db.exists("Terminal Station", station):
		_fehler(_("Station {0} ist nicht eingerichtet.").format(station or "-"))
	return frappe.get_cached_doc("Terminal Station", station)


FUNKTIONSNAMEN = {
	"herstellen": "Herstellen",
	"rework": "Rework",
	"silo": "Silo leer melden",
	"wareneingang": "Wareneingang",
	"paletten": "Paletten",
	"lieferung": "Lieferung",
	"umlagern": "Umlagern",
	"linie": "An die Linie geben",
	"packstation": "Packstation",
	"palette_fertig": "Palette fertig",
}


def _darf(s, funktion):
	"""Serverseitig prüfen, dass die Station die Funktion hat (nicht nur Knöpfe ausblenden)."""
	if not s.get("f_" + funktion):
		_fehler(
			_("{0} ist an der Station {1} nicht freigeschaltet.").format(
				FUNKTIONSNAMEN.get(funktion, funktion), s.name
			)
		)


def _liste(wert):
	if isinstance(wert, str):
		return json.loads(wert or "[]")
	return wert or []


# ---------------------------------------------------------------------------
# Stammdaten für die Oberfläche
# ---------------------------------------------------------------------------


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
def rezepte(station: str) -> list[dict]:
	"""Herstellbare Artikel dieser Station (mit aktiver Standard-Stückliste)."""
	s = _station(station)
	stufen = s.stufen_liste()
	if not stufen:
		return []
	return frappe.db.sql(
		"""
		select i.name as artikel, i.item_name as name, i.kt_chargen_stufe as stufe, b.name as bom
		from `tabItem` i
		join `tabBOM` b on b.item = i.name and b.is_default = 1 and b.is_active = 1 and b.docstatus = 1
		where i.disabled = 0 and i.kt_chargen_stufe in %(stufen)s
			and ifnull(i.kt_linie, '') = %(linie)s
		order by field(i.kt_chargen_stufe, %(reihenfolge)s), i.item_name
		""",
		# Station einer Linie: nur Artikel dieser Linie; Station ohne Linie: nur Artikel ohne Linie
		{"stufen": tuple(stufen), "reihenfolge": ",".join(stufen), "linie": s.linie or ""},
		as_dict=True,
	)


@frappe.whitelist()
def rezept(artikel: str, menge: float | None = None, station: str | None = None) -> dict:
	"""Zutaten laut Standard-Stückliste, auf die Sollmenge umgerechnet."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		_fehler(_("Für {0} gibt es kein aktives Rezept (Stückliste).").format(artikel))
	b = frappe.get_cached_doc("BOM", bom)
	faktor = flt(menge or b.quantity) / flt(b.quantity or 1)
	silos = _silo_je_artikel()
	vorraete = _vorraete()
	gebinde = _gebinde_einheiten([z.item_code for z in b.items])
	zutaten = [
		{
			"artikel": z.item_code,
			"name": z.item_name,
			"menge": flt(z.qty * faktor, 3),
			"einheit": z.stock_uom or z.uom,
			"stufe": artikel_stufe(z.item_code),
			"silo": silos.get(z.item_code),
			"vorrat": silos.get(z.item_code) if z.item_code in vorraete else None,
			"toleranz": _toleranz(z, flt(z.qty * faktor, 3)),
			# Wo die Zutat liegt (wie „Kostenstelle“ bei FOBIS) und in welchen Gebinden sie gezählt werden kann
			"lager": silos.get(z.item_code) or _lagerort(z, b.company),
			"gebinde": gebinde.get(z.item_code, []),
		}
		for z in b.items
	]
	return {
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"stufe": artikel_stufe(artikel),
		"bom": bom,
		"sollmenge": flt(menge or b.quantity, 3),
		# Ausbeute nur über Zutaten in der Einheit des Produkts, ohne Packmittel (Herz in Stück:
		# 1 garniertes Herz + Folie + Etikett + Schleife = 1 Herz, nicht 4)
		"ausbeute": flt(b.quantity)
		/ (
			sum(
				flt(z.stock_qty or z.qty)
				for z in b.items
				if (z.stock_uom or z.uom) == b.uom and artikel_stufe(z.item_code) != "Packmittel"
			)
			or 1
		),
		"einheit": b.uom,
		"zutaten": zutaten,
		"rework_moeglich": artikel_stufe(artikel) in REWORK_ZIELE,
		# Einwaage gegen Soll prüfen (Grundteig, Teig, Halbfabrikat), siehe _pruefe_rezept
		"rezept_pruefen": artikel_stufe(artikel) in REZEPT_STUFEN and _rezept_modus() != "Aus",
		"rezept_pflicht": _rezept_modus() == "Grund Pflicht",
		"ausgabe_silo": silos.get(artikel),
		"einheiten": paletten.einheiten(artikel) if artikel_stufe(artikel) == "Fertigware" else [],
		"pruefungen": [pruefung.beschreibung(p) for p in pruefung.fuer_herstellen(artikel, station)],
		"kennzeichen": sorted(kennzeichnung.artikel_kennzeichen(artikel), key=kennzeichnung.ALLE.index),
		"kuebel": _kuebel_fuer(zutaten),
		"umstellung_bio": bool(station and kennzeichnung.umstellung_noetig(station, artikel)),
	}


REZEPT_STUFEN = ("Grundteig", "Teig veredelt", "Halbfabrikat")


def _mit_hinweis(zeilen: list[dict]) -> None:
	"""Hinweis des Büros am Kundenauftrag („mit Clip“ …) an jede Zeile hängen (Feld kt_hinweis_produktion)."""
	namen = {z["auftrag"] for z in zeilen if z.get("auftrag")}
	if not namen:
		return
	text = dict(
		frappe.get_all(
			"Sales Order",
			filters={"name": ["in", list(namen)]},
			fields=["name", "kt_hinweis_produktion"],
			as_list=True,
		)
	)
	for z in zeilen:
		z["hinweis"] = (text.get(z.get("auftrag")) or "").strip() or None


def _lagerort(bom_zeile, company: str | None) -> str | None:
	"""Lagerort einer Rezeptzeile: Quelllager der Stückliste, sonst Standardlager des Artikels (ohne Firmenkürzel)."""
	lager = bom_zeile.get("source_warehouse") or frappe.db.get_value(
		"Item Default", {"parent": bom_zeile.item_code, "company": company}, "default_warehouse"
	)
	return (frappe.get_cached_value("Warehouse", lager, "warehouse_name") or lager) if lager else None


def _gebinde_einheiten(artikel: list[str]) -> dict[str, list[dict]]:
	"""Gebinde mit festem Inhalt je Artikel aus der Maßeinheit-Umrechnung am Artikel, z. B. 1 Sack = 25 kg.
	Nur Einheiten größer als die Lagereinheit (Sack, Kollo, Karton); gezählt wird am Terminal in ganzen Gebinden."""
	if not artikel:
		return {}
	lagereinheit = dict(
		frappe.get_all("Item", filters={"name": ["in", artikel]}, fields=["name", "stock_uom"], as_list=True)
	)
	je = {}
	for u in frappe.get_all(
		"UOM Conversion Detail",
		filters={"parenttype": "Item", "parent": ["in", artikel], "conversion_factor": [">", 1]},
		fields=["parent", "uom", "conversion_factor"],
		order_by="conversion_factor asc",
	):
		if u.uom != lagereinheit.get(u.parent):
			je.setdefault(u.parent, []).append({"einheit": u.uom, "faktor": flt(u.conversion_factor, 6)})
	return je


def _rezept_modus() -> str:
	return einstellung("rezept_abweichung") or "Grund Pflicht"


def _toleranz(bom_zeile, soll: float) -> float:
	"""Erlaubte Abweichung in der Lagereinheit: % an der Rezeptzeile, sonst Standard; nie unter dem Minimum."""
	prozent = flt(bom_zeile.get("kt_toleranz_prozent")) or flt(einstellung("rezept_toleranz_prozent") or 5)
	return flt(max(abs(soll) * prozent / 100, flt(einstellung("rezept_toleranz_min") or 0.01)), 4)


def _pruefe_rezept(ziel: str, sollmenge, eingaenge: list[dict], grund: str | None) -> str | None:
	"""Einwaage gegen das Rezept, umgerechnet auf die Sollmenge (z. B. halbe Masse = halbe Sollmenge).

	Nur mit Sollmenge vom Terminal (Teigmacher), nur für REZEPT_STUFEN. Rework zählt nicht (eigene Regel).
	Gibt den Text fürs Protokoll zurück (None = alles in der Toleranz).
	"""
	modus = _rezept_modus()
	if not flt(sollmenge) or modus == "Aus" or artikel_stufe(ziel) not in REZEPT_STUFEN:
		return None
	r = rezept(ziel, flt(sollmenge))
	ist = {}
	for z in eingaenge:
		ist[z["artikel"]] = ist.get(z["artikel"], 0) + flt(z["menge"])
	texte = []
	for z in r["zutaten"]:
		menge = flt(ist.get(z["artikel"]), 3)
		if abs(menge - z["menge"]) <= z["toleranz"] + 1e-9:
			continue
		prozent = f"{(menge / z['menge'] - 1) * 100:+.0f} %" if z["menge"] else ""
		texte.append(
			_("{0}: {1} statt {2} ({3}, erlaubt ± {4})").format(
				z["name"],
				paletten._n(menge, z["einheit"]),
				paletten._n(z["menge"], z["einheit"]),
				prozent,
				paletten._n(z["toleranz"], z["einheit"]),
			)
		)
	if not texte:
		return None
	kopf = _("Sollmenge {0}").format(paletten._n(flt(sollmenge), r["einheit"]))
	grund = (grund or "").strip()
	if not grund:
		if modus == "Grund Pflicht":
			_fehler(
				_("Einwaage außerhalb der Toleranz. Bitte korrigieren oder einen Grund angeben.")
				+ "<br>"
				+ "<br>".join(texte)
			)
		frappe.msgprint("<br>".join(texte), title=_("Einwaage"), indicator="orange", alert=True)
		return _("Ohne Grund (Einstellung: nur Hinweis)") + "\n" + kopf + "\n" + "\n".join(texte)
	return _("Grund: {0}").format(grund) + "\n" + kopf + "\n" + "\n".join(texte)


def _kuebel_fuer(zutaten) -> list[dict]:
	"""Älteste belegte Kübel mit dem Grundteig des Rezepts (Vorschlag am Kneter bzw. bei der Veredelung)."""
	from keks_trace.linienbuchung import kuebel_vorschlag

	return kuebel_vorschlag([z["artikel"] for z in zutaten if z["stufe"] == "Grundteig"])


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


# ---------------------------------------------------------------------------
# Vorrat am Tisch: Karton/Rolle anbrechen (Folie, Etikett, Schleife, ...)
# ---------------------------------------------------------------------------


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


def _offene_auftraege(namen) -> set:
	"""Welche dieser Kundenaufträge noch offen sind (gebucht, nicht erledigt/geschlossen)."""
	namen = [n for n in set(namen or ()) if n]
	if not namen:
		return set()
	return set(
		frappe.get_all(
			"Sales Order",
			{"name": ["in", namen], "docstatus": 1, "status": ["not in", ["Completed", "Closed"]]},
			pluck="name",
		)
	)


def _reserviert(charge: str | None) -> str | None:
	"""Für welchen offenen Kundenauftrag eine Charge hergestellt wurde (sonst frei)."""
	if not charge:
		return None
	auftrag = frappe.db.get_value("Batch", charge, "kt_kundenauftrag")
	return auftrag if auftrag in _offene_auftraege([auftrag]) else None


def _lager_chargen(artikel: str, auftrag: str | None = None) -> list[dict]:
	"""Chargen eines Artikels mit Bestand im Lager (nicht im Vorrat/Silo/Lagerverkauf), ältestes MHD zuerst.

	Zum Antippen ohne Scanner. Reserviert (für einen offenen Kundenauftrag hergestellt): nur für diesen Auftrag,
	dort zuerst. Sonderanfertigung nach Auftrag: mit Auftrag nur die eigene Ware.
	"""
	# nicht aus Silo/Vorrat, Lagerverkauf oder von einer Linie (das gehört dem Produktionsauftrag)
	aus = list(
		set(frappe.get_all("Silo", pluck="warehouse"))
		| _verkaufslager()
		| set(frappe.get_all("Linie", pluck="lagerort"))
	) or [""]
	# Linienlager zuerst: es ist der Puffer an der Linie und wird zuerst leer verpackt (F7)
	linienlager = tuple(frappe.get_all("Linie", {"linienlager": ["is", "set"]}, pluck="linienlager")) or ("",)
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, sum(sbe.qty) as menge, b.expiry_date as mhd, b.kt_kundenauftrag as auftrag,
			sum(case when sbe.warehouse in %(ll)s then sbe.qty else 0 end) > 0.000001 as linienlager
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabBatch` b on b.name = sbe.batch_no
		where b.item = %(artikel)s and sbb.is_cancelled = 0 and sbb.docstatus = 1
			and ifnull(b.kt_status, '') != 'Gesperrt' and sbe.warehouse not in %(aus)s
		group by sbe.batch_no, b.expiry_date, b.creation, b.kt_kundenauftrag
		having sum(sbe.qty) > 0.000001
		order by linienlager desc, b.expiry_date is null, b.expiry_date, b.creation
		limit 200
		""",
		{"artikel": artikel, "aus": tuple(aus), "ll": linienlager},
		as_dict=True,
	)
	offen = _offene_auftraege(z.auftrag for z in zeilen)
	sonder = cint(frappe.get_cached_value("Item", artikel, "kt_nach_auftrag"))
	ergebnis = []
	for z in zeilen:
		reserviert = z.auftrag if z.auftrag in offen else None
		if reserviert and reserviert != auftrag:
			continue  # gehört einem anderen Auftrag
		if sonder and auftrag and reserviert != auftrag:
			continue  # Sonderanfertigung: nur die für diesen Auftrag gemachte
		ergebnis.append(
			{
				"charge": z.charge,
				"menge": flt(z.menge, 3),
				"mhd": formatdate(z.mhd) if z.mhd else None,
				"linienlager": cint(z.linienlager),
				"auftrag": reserviert,
			}
		)
	if auftrag:
		ergebnis.sort(key=lambda x: x["auftrag"] != auftrag)  # eigene zuerst, sonst Reihenfolge wie oben
	return ergebnis[:30]


@frappe.whitelist()
@einmalig
def anbrechen(station: str, code: str) -> dict:
	"""Neuen Karton / neue Rolle an den Tisch: die Charge kommt in den Vorrat und wird ab jetzt verbraucht."""
	s = _station(station)
	r = aufloesen(code)
	charge = r.get("charge")
	if r["typ"] != "charge" or not charge:
		_fehler(_("Bitte das Etikett des Kartons bzw. der Rolle scannen (Charge)."))
	artikel = frappe.db.get_value("Batch", charge, "item")
	vorrat = _vorraete().get(artikel)
	if not vorrat:
		_fehler(
			_("Für {0} ist kein Vorrat am Tisch eingerichtet.").format(
				frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	_pruefe_charge(charge, artikel)
	ziel = frappe.db.get_value("Silo", vorrat, "warehouse")
	vorrat_lager = set(frappe.get_all("Silo", pluck="warehouse")) | _verkaufslager()
	quellen = {w: m for w, m in charge_lager(charge).items() if w not in vorrat_lager}
	if not quellen:
		_fehler(_("Von Charge {0} ist nichts mehr im Lager.").format(charge))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile({"artikel": artikel, "charge": charge, "menge": m}, w, ziel)
				for w, m in quellen.items()
			],
		}
	)
	se.insert()
	se.submit()
	return {
		"vorrat": vorrat,
		"charge": charge,
		"menge": flt(sum(quellen.values()), 3),
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"buchung": se.name,
	}


@frappe.whitelist()
def rework_artikel() -> list[dict]:
	return frappe.get_all(
		"Item",
		filters={"kt_chargen_stufe": "Rework", "disabled": 0},
		fields=["name as artikel", "item_name as name", "kt_allergengruppe as allergengruppe"],
		order_by="item_name",
	)


GEBINDEARTEN = ("Sack", "Fass", "IBC", "Eimer", "Karton", "Kanister", "BigBag", "Sonstiges")


def _artikel_zur_gtin(gtin: str) -> dict | None:
	"""Artikel und Einheit zu einer GTIN/EAN aus der Barcode-Tabelle am Artikel (ERPNext-Standard)."""
	for g in gs1.gtin_varianten(gtin):
		z = frappe.db.get_value("Item Barcode", {"barcode": g}, ["parent", "uom"], as_dict=True)
		if z:
			return {"artikel": z.parent, "einheit": z.uom}
	return None


def _charge_name(artikel: str, lieferantencharge: str) -> str:
	"""Name unserer Charge zu einer Lieferanten-Charge: die Lieferanten-Charge selbst, bei gleicher Nummer
	eines anderen Artikels <Artikel>-<Lieferanten-Charge>. Eine Nummer je Sache, keine Zweitnummer."""
	if frappe.db.exists("Batch", lieferantencharge) and (
		frappe.db.get_value("Batch", lieferantencharge, "item") != artikel
	):
		return f"{artikel}-{lieferantencharge}"
	return lieferantencharge


def _pruefe_lieferantencharge(artikel: str, text: str) -> None:
	"""Plausibilität: eine Charge enthält eine Ziffer und ist nicht der Artikelname (z. B. „Präsentkarton“)."""
	if not 2 <= len(text) <= 60:
		_fehler(
			_("Charge {0}: bitte die Charge des Lieferanten (2 bis 60 Zeichen).").format(frappe.bold(text))
		)
	name = (frappe.get_cached_value("Item", artikel, "item_name") or "").casefold()
	if not any(z.isdigit() for z in text) or text.casefold() in (name, artikel.casefold()):
		_fehler(
			_(
				"{0} ist keine Charge. Bitte die Charge vom Etikett des Lieferanten scannen oder abtippen."
			).format(frappe.bold(text))
		)


@frappe.whitelist()
def wareneingang_scan(code: str) -> dict:
	"""Etikett des Lieferanten im Wareneingang lesen. Schlägt vor, bucht nichts.

	GS1-128/DataMatrix: Artikel (über GTIN), Charge, MHD, Gewicht. Einfache EAN: nur Artikel und Einheit.
	Alles andere: Text, wird als Charge vorgeschlagen.
	"""
	g = gs1.lesen(code)
	gtin = g.get("gtin") if g else gs1.ean(code)
	erg = {"code": (code or "").strip(), "gs1": bool(g), "gtin": gtin}
	if not g and not gtin:
		erg["charge"] = erg["code"]
		return erg
	if g:
		erg["charge"] = g.get("charge")
		erg["mhd"] = str(g["mhd"]) if g.get("mhd") else None
		erg["netto_kg"] = g.get("netto_kg")
		erg["unvollstaendig"] = bool(g.get("rest"))
	treffer = _artikel_zur_gtin(gtin) if gtin else None
	if not treffer:
		erg["unbekannt"] = True
		return erg
	artikel = treffer["artikel"]
	stufe = artikel_stufe(artikel)
	if stufe not in ("Rohstoff", "Packmittel") or not frappe.get_cached_value(
		"Item", artikel, "has_batch_no"
	):
		_fehler(
			_("Code {0} gehört zu {1} ({2}) - das ist kein Rohstoff oder Packmittel mit Charge.").format(
				gtin, artikel, frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	erg["artikel"] = artikel
	erg["einheit"] = treffer["einheit"]
	# Menge je Gebinde: Gewicht aus dem Etikett, sonst Umrechnung der Einheit des Barcodes (Karton = 25 Stk)
	lager_einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	je = None
	if erg.get("netto_kg") and lager_einheit in ("Kg", "kg"):
		je = erg["netto_kg"]
	elif treffer["einheit"] and treffer["einheit"] != lager_einheit:
		je = next(
			(
				e["faktor"]
				for e in paletten.einheiten(artikel, alle=True)
				if e["einheit"] == treffer["einheit"]
			),
			None,
		)
	erg["menge_je_gebinde"] = je
	erg["gebindeart"] = treffer["einheit"] if treffer["einheit"] in GEBINDEARTEN else None
	if erg.get("charge"):
		vorhanden = _charge_name(artikel, erg["charge"])
		erg["charge_bekannt"] = bool(frappe.db.exists("Batch", vorhanden))
	return erg


@frappe.whitelist()
def wareneingang_artikel() -> list[dict]:
	silos = _silo_je_artikel()
	artikel = frappe.get_all(
		"Item",
		filters={"kt_chargen_stufe": ["in", ["Rohstoff", "Packmittel"]], "disabled": 0, "has_batch_no": 1},
		fields=[
			"name as artikel",
			"item_name as name",
			"has_expiry_date",
			"kt_freigabe_pflicht",
			"stock_uom",
		],
		order_by="item_name",
	)
	lieferanten = _lieferanten()
	for a in artikel:
		a["silo"] = silos.get(a["artikel"]) if a["artikel"] not in _vorraete() else None
		a["bio"] = kennzeichnung.BIO in kennzeichnung.artikel_kennzeichen(a["artikel"])
		eigene = frappe.get_all("Item Supplier", {"parent": a["artikel"]}, pluck="supplier")
		a["lieferanten"] = [
			x
			for x in lieferanten
			if (not eigene or x["lieferant"] in eigene) and (x["bio_ok"] or not a["bio"])
		]
		a["pruefungen"] = [
			pruefung.beschreibung(p) for p in pruefung.fuer_artikel(pruefung.WARENEINGANG, a["artikel"])
		]
	return artikel


def _lieferanten() -> list[dict]:
	ergebnis = []
	for x in frappe.get_all("Supplier", {"disabled": 0}, ["name", "supplier_name"], order_by="supplier_name"):
		st = kennzeichnung.bio_lieferant_status(x.name)
		ergebnis.append({"lieferant": x.name, "name": x.supplier_name, "bio_ok": st["ok"]})
	return ergebnis


def _fuer_auftrag(kundenauftrag: str, ziel: str) -> bool:
	"""Ist der Artikel bestellt oder eine Vorstufe davon (garniertes Herz für ein bestelltes Herz)?"""
	bestellt = frappe.get_all(
		"Sales Order Item", {"parent": kundenauftrag, "docstatus": 1}, pluck="item_code"
	)
	if ziel in bestellt:
		return True
	for artikel in bestellt:
		if ziel in {z["artikel"] for z in rezept(artikel, 1)["zutaten"]}:
			return True
	return False


def _verfuegbar(artikel: str) -> float:
	return flt(sum(c["menge"] for c in _lager_chargen(artikel)), 3)


def _hauptzutat(artikel: str) -> str | None:
	"""Woraus ein Artikel hauptsächlich besteht (Herz verpackt: garniertes Herz; garniert: Rohling)."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		return None
	zeilen = [
		z
		for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code", "stock_qty"], order_by="idx")
		if artikel_stufe(z.item_code) not in ("Packmittel", "Rohstoff")
	]
	return max(zeilen, key=lambda z: flt(z.stock_qty)).item_code if zeilen else None


def _fertig_fuer(auftrag: str, artikel: str) -> float:
	"""Wie viel von artikel mit diesem Kundenauftrag hergestellt wurde (Lagereinheit)."""
	return flt(
		frappe.db.sql(
			"""select sum(sed.transfer_qty) from `tabStock Entry Detail` sed
			join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 1 and se.kt_kundenauftrag = %s and sed.item_code = %s and sed.is_finished_item = 1""",
			(auftrag, artikel),
		)[0][0]
	)


def _vorrat_je_auftrag(artikel: str) -> tuple[dict, float]:
	"""({Auftrag: reservierter Bestand}, freier Bestand) eines Artikels im Lager."""
	reserviert, frei = {}, 0.0
	for c in _lager_chargen_alle(artikel):
		if c["auftrag"]:
			reserviert[c["auftrag"]] = reserviert.get(c["auftrag"], 0) + c["menge"]
		else:
			frei += c["menge"]
	return reserviert, frei


def _lager_chargen_alle(artikel: str) -> list[dict]:
	"""Wie _lager_chargen, aber auch die für andere Aufträge reservierte Ware (zum Zählen)."""
	ergebnis = []
	for auftrag in [
		None,
		*_offene_auftraege(
			frappe.get_all(
				"Batch", {"item": artikel, "kt_kundenauftrag": ["is", "set"]}, pluck="kt_kundenauftrag"
			)
		),
	]:
		ergebnis += [c for c in _lager_chargen(artikel, auftrag) if c["auftrag"] == auftrag]
	return ergebnis


@frappe.whitelist()
def aufgaben(station: str) -> list[dict]:
	"""Offene Kundenaufträge als Arbeitsliste der Station (Herzenboden: Garnieren und Verpacken).

	Ein Auftrag läuft am Herzenboden durch: was beim Garnieren für ihn gemacht wird, ist für ihn reserviert und
	wird beim Verpacken zuerst genommen. Je Auftragsposition: was diese Station dafür herstellt, bestellt, erledigt
	(Verpacken: verpackt; Garnieren: schon verpackt plus für den Auftrag garniert und noch im Lager), ToDo und
	Vorrat der Vorstufe: erst die für den Auftrag reservierte, dann freie Ware nach Liefertermin verteilt
	(Sonderanfertigungen nur reserviert).
	"""
	s = _station(station)
	stufen = s.stufen_liste()
	ergebnis = []
	frei_rest, reserviert_je = {}, {}
	for z in frappe.db.sql(
		"""
		select so.name as auftrag, so.customer_name as kunde, soi.item_code as artikel, soi.stock_qty as menge,
			coalesce(soi.delivery_date, so.delivery_date) as termin
		from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		join `tabItem` i on i.name = soi.item_code
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed', 'On Hold')
			and i.kt_chargen_stufe = 'Fertigware' and soi.delivered_qty < soi.qty
			and ifnull(i.kt_linie, '') = %(linie)s
		order by termin, so.name, soi.idx
		""",
		{"linie": s.linie or ""},
		as_dict=True,
	):
		ziel, faktor = z.artikel, 1.0
		if "Fertigware" not in stufen:
			r = rezept(z.artikel, 1)
			passend = [x for x in r["zutaten"] if x["stufe"] in stufen]
			if not passend:
				continue
			ziel, faktor = passend[0]["artikel"], flt(passend[0]["menge"]) or 1
		bestellt = flt(z.menge) * faktor
		if ziel == z.artikel:
			erledigt = _fertig_fuer(z.auftrag, ziel)
		else:  # Vorstufe: was schon verpackt ist, plus was für den Auftrag gemacht im Lager liegt
			if ziel not in reserviert_je:
				reserviert_je[ziel] = _vorrat_je_auftrag(ziel)[0]
			erledigt = _fertig_fuer(z.auftrag, z.artikel) * faktor + reserviert_je[ziel].get(z.auftrag, 0)
		erledigt = flt(min(erledigt, bestellt), 3)
		todo = max(flt(bestellt - erledigt, 3), 0)
		if todo <= EPS:
			continue
		vor = _hauptzutat(ziel)
		eigen = zugeteilt = 0.0
		if vor:
			if vor not in frei_rest:
				reserviert_je[vor], frei_rest[vor] = _vorrat_je_auftrag(vor)
			eigen = flt(reserviert_je[vor].get(z.auftrag, 0), 3)
			if not cint(frappe.get_cached_value("Item", vor, "kt_nach_auftrag")):
				zugeteilt = flt(min(frei_rest[vor], max(todo - eigen, 0)), 3)
				frei_rest[vor] -= zugeteilt
		ergebnis.append(
			{
				"auftrag": z.auftrag,
				"kunde": z.kunde,
				"artikel": ziel,
				"name": frappe.get_cached_value("Item", ziel, "item_name"),
				"einheit": frappe.get_cached_value("Item", ziel, "stock_uom"),
				"bestellt": bestellt,
				"erledigt": erledigt,
				"todo": todo,
				"vorstufe": frappe.get_cached_value("Item", vor, "item_name") if vor else None,
				"verfuegbar": eigen + zugeteilt if vor else None,
				"vorrat_eigen": eigen,
				"vorrat_frei": zugeteilt,
				"termin": formatdate(z.termin) if z.termin else None,
			}
		)
	_mit_hinweis(ergebnis)
	return ergebnis


@frappe.whitelist()
def zum_verpacken(station: str) -> list[dict]:
	"""Lose Ware im Lager, die verpackt werden kann (nach Bedarf, ohne Auftrag): je Kiste bzw. Charge,
	älteste zuerst, mit den Fertigartikeln, in die sie verpackt werden kann."""
	s = _station(station)
	# Linien mit eigener Verpackung (Herzenboden: Herzen Verpackung) packen ihre Ware selbst
	eigene = {
		x.linie
		for x in frappe.get_all(
			"Terminal Station",
			{"aktiv": 1, "f_herstellen": 1, "linie": ["is", "set"], "name": ["!=", s.name]},
			["name", "linie", "stufen"],
		)
		if "Fertigware" in (x.stufen or "")
	}
	ziele = {}
	for b in frappe.db.sql(
		"""select bi.item_code as lose, bom.item as fertig, bom.quantity as menge, bi.stock_qty as je
		from `tabBOM Item` bi join `tabBOM` bom on bom.name = bi.parent
		join `tabItem` i on i.name = bom.item
		where bom.is_default = 1 and bom.is_active = 1 and bom.docstatus = 1 and i.kt_chargen_stufe = 'Fertigware'
			and i.disabled = 0""",
		as_dict=True,
	):
		if (
			artikel_stufe(b.lose) == "Ware lose"
			and frappe.get_cached_value("Item", b.fertig, "kt_linie") not in eigene
		):
			ziele.setdefault(b.lose, []).append(
				{"artikel": b.fertig, "name": frappe.get_cached_value("Item", b.fertig, "item_name")}
			)
	ergebnis = []
	for lose, fertig in ziele.items():
		for q in _quellen(lose):
			ergebnis.append(
				{
					**q,
					"lose": lose,
					"name": frappe.get_cached_value("Item", lose, "item_name"),
					"einheit": frappe.get_cached_value("Item", lose, "stock_uom"),
					"menge_text": paletten.zerlegen(lose, q["menge"]),
					"backtag": formatdate(frappe.db.get_value("Batch", q["charge"], "kt_backtag") or "")
					or "",
					"ziele": fertig,
				}
			)
	return ergebnis


@frappe.whitelist()
def verpacken_ziele(station: str, lose: str) -> dict:
	"""Was aus dieser losen Ware werden kann: erst offene Kundenaufträge, die sie brauchen, dann alle Artikel
	(jedes Gebinde, jeder Kundenartikel mit dieser losen Ware im Rezept)."""
	ziele = {}
	for b in frappe.db.sql(
		"""select distinct bom.item as artikel from `tabBOM Item` bi join `tabBOM` bom on bom.name = bi.parent
		join `tabItem` i on i.name = bom.item
		where bi.item_code = %s and bom.is_default = 1 and bom.is_active = 1 and bom.docstatus = 1
			and i.kt_chargen_stufe = 'Fertigware' and i.disabled = 0""",
		lose,
		as_dict=True,
	):
		ziele[b.artikel] = {
			"artikel": b.artikel,
			"name": frappe.get_cached_value("Item", b.artikel, "item_name"),
		}
	auftraege_ = [
		{
			"auftrag": z["auftrag"],
			"kunde": z["kundenname"],
			"artikel": z["artikel"],
			"name": z["name"],
			"bestellt": z["menge"],
			"erledigt": z["verpackt"],
			"todo": z["offen_verpacken"],
			"einheit": z["einheit"],
			"offen_text": z["offen_text"],
			"termin": z["termin"],
		}
		for z in auftraege(station)
		if z["artikel"] in ziele and z["offen_verpacken"] > EPS
	]
	return {"auftraege": auftraege_, "artikel": sorted(ziele.values(), key=lambda x: x["name"])}


@frappe.whitelist()
def auftraege(station: str, kunde: str | None = None) -> list[dict]:
	"""Offene Kundenaufträge (Fertigware und lose Ware/Kiloware): bestellt, verpackt, geliefert, offen."""
	s = _station(station)
	bedingung = "and so.customer = %(kunde)s" if kunde else ""
	if s.f_herstellen:
		# Verpacken: nur Aufträge über Artikel dieser Linie (Versand sieht alle)
		bedingung += " and ifnull(i.kt_linie, '') = %(linie)s"
	zeilen = frappe.db.sql(
		f"""
		select so.name as auftrag, so.customer as kunde, so.customer_name as kundenname,
			soi.name as position, soi.item_code as artikel, soi.item_name as name,
			soi.qty as menge, soi.uom as einheit, soi.conversion_factor as faktor,
			soi.stock_qty, soi.delivered_qty * soi.conversion_factor as geliefert,
			coalesce(soi.delivery_date, so.delivery_date) as termin
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		join `tabItem` i on i.name = soi.item_code
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed', 'On Hold')
			and i.kt_chargen_stufe in ('Fertigware', 'Ware lose') and soi.delivered_qty < soi.qty {bedingung}
		order by termin, so.name, soi.idx
		""",
		{"kunde": kunde, "linie": s.linie or ""},
		as_dict=True,
	)
	verpackt = {}
	if zeilen:
		for v in frappe.db.sql(
			"""
			select se.kt_kundenauftrag as auftrag, sed.item_code as artikel, sum(sed.transfer_qty) as menge
			from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 1 and se.kt_kundenauftrag in %(a)s and sed.is_finished_item = 1
			group by se.kt_kundenauftrag, sed.item_code
			""",
			{"a": tuple({z.auftrag for z in zeilen})},
			as_dict=True,
		):
			verpackt[(v.auftrag, v.artikel)] = flt(v.menge)
	for z in zeilen:
		f = flt(z.faktor) or 1
		verpackt_kg = flt(verpackt.get((z.auftrag, z.artikel), 0))
		z["verpackt"] = flt(verpackt_kg / f, 3)
		geliefert_kg = flt(z.geliefert)
		z["geliefert"] = flt(geliefert_kg / f, 3)
		z["offen_verpacken"] = max(flt(z.menge - z.verpackt, 3), 0)
		z["termin"] = formatdate(z.termin) if z.termin else None
		# Klartext in gemischten Einheiten, z. B. „3 Paletten + 5 Karton“
		z["menge_text"] = paletten.zerlegen(z.artikel, z.stock_qty)
		z["verpackt_text"] = paletten.zerlegen(z.artikel, verpackt_kg)
		z["offen_text"] = paletten.zerlegen(z.artikel, max(flt(z.stock_qty) - verpackt_kg, 0))
		z["offen_liefern_text"] = paletten.zerlegen(z.artikel, max(flt(z.stock_qty) - geliefert_kg, 0))
		z["offen_kg"] = max(flt(z.stock_qty) - verpackt_kg, 0)
		z["einheiten"] = paletten.einheiten(z.artikel, alle=True)
	_mit_hinweis(zeilen)
	return zeilen


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


# ---------------------------------------------------------------------------
# Scan auflösen
# ---------------------------------------------------------------------------


def charge_lager(charge) -> dict[str, float]:
	"""Bestand einer Charge je Lagerort."""
	zeilen = frappe.db.sql(
		"""
		select sbe.warehouse, sum(sbe.qty) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		where sbe.batch_no = %s and sbb.is_cancelled = 0 and sbb.docstatus = 1
		group by sbe.warehouse
		""",
		charge,
		as_dict=True,
	)
	return {z.warehouse: flt(z.menge) for z in zeilen if flt(z.menge) > EPS}


def aufloesen(code: str) -> dict:
	"""Was wurde gescannt? Behälter, Silo/Tank oder Charge."""
	code = (code or "").strip()
	if not code:
		_fehler(_("Leerer Scan."))

	nve = paletten.finde(code)
	if nve:
		return {"typ": "palette", "code": nve, "palette": nve}

	if frappe.db.exists("Produkttraeger", code):
		t = frappe.db.get_value(
			"Produkttraeger",
			code,
			["name", "typ", "status", "charge", "artikel", "menge", "gereinigt_am"],
			as_dict=True,
		)
		erg = {
			"typ": "behaelter",
			"code": code,
			"behaelter": code,
			"behaelter_typ": t.typ,
			"status": t.status,
			"gereinigt_am": frappe.utils.format_datetime(t.gereinigt_am, "dd.MM.yyyy HH:mm")
			if t.gereinigt_am
			else None,
		}
		if t.charge:
			lager = charge_lager(t.charge)
			erg.update(
				{
					"charge": t.charge,
					"artikel": t.artikel,
					"inhalt": flt(t.menge, 3),
					"lager": max(lager, key=lager.get) if lager else None,
				}
			)
		return erg

	if frappe.db.exists("Silo", code):
		s = frappe.get_cached_doc("Silo", code)
		return {"typ": "silo", "code": code, "silo": code, "artikel": s.artikel, "lager": s.warehouse}

	if frappe.db.exists("Batch", code):
		artikel = frappe.db.get_value("Batch", code, "item")
		lager = charge_lager(code)
		return {
			"typ": "charge",
			"code": code,
			"charge": code,
			"artikel": artikel,
			"lager": max(lager, key=lager.get) if lager else None,
			"inhalt": flt(sum(lager.values()), 3),
		}

	# Etikett des Lieferanten (GS1-128 mit GTIN und Charge) oder nur seine EAN
	g = gs1.lesen(code)
	if g and g.get("sscc") and not g.get("gtin"):
		nve = paletten.finde(g["sscc"])
		if nve:
			return aufloesen(nve)
	gtin = g.get("gtin") if g else gs1.ean(code)
	treffer = _artikel_zur_gtin(gtin) if gtin else None
	if treffer:
		name = frappe.get_cached_value("Item", treffer["artikel"], "item_name")
		if not (g and g.get("charge")):
			_fehler(
				_(
					"Das ist {0} ({1}), aber ohne Charge im Strichcode. Bitte das Gebinde-Etikett scannen oder die Charge eingeben."
				).format(treffer["artikel"], name)
			)
		if artikel_stufe(treffer["artikel"]) in ("Rohstoff", "Packmittel"):
			charge = _charge_name(treffer["artikel"], g["charge"])
			if not frappe.db.exists("Batch", charge):
				_fehler(
					_("{0} ({1}) Charge {2} ist nicht im Wareneingang gebucht.").format(
						treffer["artikel"], name, frappe.bold(g["charge"])
					)
				)
			return aufloesen(charge)
		return aufloesen(_charge_zum_eigenen_los(treffer["artikel"], name, g))

	# Ohne Scanner: aufgedruckte Los-Nummer oder Buchungsnummer (MAT-STE-...) eingetippt
	charge = _charge_aus_los_oder_buchung(code)
	if charge:
		return aufloesen(charge)

	_fehler(
		_("Code {0} ist unbekannt (kein Behälter, Silo, Palette, Charge, Los oder Buchungsnummer).").format(
			frappe.bold(code)
		)
	)


def _charge_zum_eigenen_los(artikel: str, name: str, g: dict) -> str:
	"""Eigenes GS1-Etikett (Karton): Los (10) und ggf. MHD (15) -> unsere Charge dieses Artikels mit Bestand."""
	kandidaten = frappe.get_all(
		"Batch", {"item": artikel, "kt_los": g["charge"]}, ["name", "expiry_date"], order_by="creation desc"
	)
	if g.get("mhd"):
		passend = [b for b in kandidaten if b.expiry_date and getdate(b.expiry_date) == g["mhd"]]
		kandidaten = passend or kandidaten
	mit_bestand = [b for b in kandidaten if charge_lager(b.name)]
	kandidaten = mit_bestand or kandidaten
	if not kandidaten:
		_fehler(_("{0} ({1}) Los {2} gibt es nicht.").format(artikel, name, frappe.bold(g["charge"])))
	if len(kandidaten) > 1:
		_fehler(
			_("{0} Los {1} gibt es mehrfach: {2}. Bitte die Charge wählen.").format(
				name, g["charge"], ", ".join(b.name for b in kandidaten[:6])
			)
		)
	return kandidaten[0].name


def _charge_aus_los_oder_buchung(code: str) -> str | None:
	"""Los-Nummer (Aufdruck) bzw. Buchungsnummer in die Charge übersetzen; bei mehreren: Rückfrage."""
	if frappe.db.exists("Stock Entry", code):
		chargen = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": code, "is_finished_item": 1, "batch_no": ["is", "set"]},
			pluck="batch_no",
		)
		if not chargen:
			_fehler(_("In Buchung {0} ist keine neue Charge entstanden.").format(code))
		chargen = list(dict.fromkeys(chargen))
		if len(chargen) > 1:
			_fehler(_("In Buchung {0} sind mehrere Chargen entstanden: {1}").format(code, ", ".join(chargen)))
		return chargen[0]
	chargen = [
		b.name
		for b in frappe.get_all("Batch", filters={"kt_los": code}, fields=["name"], order_by="creation desc")
		if charge_lager(b.name)
	]
	if len(chargen) > 1:
		texte = [
			f"{c} ({frappe.get_cached_value('Item', frappe.db.get_value('Batch', c, 'item'), 'item_name')})"
			for c in chargen[:6]
		]
		_fehler(
			_("Los {0} gibt es bei mehreren Artikeln: {1}. Bitte die Charge wählen.").format(
				code, ", ".join(texte)
			)
		)
	return chargen[0] if chargen else None


@frappe.whitelist()
def info(code: str) -> dict:
	"""Info-Scan: alles Wichtige zu einem Code."""
	from keks_trace import silo as silo_modul

	r = aufloesen(code)
	if r["typ"] == "palette":
		r.update(paletten.info(r["palette"]))
		return r
	if r["typ"] == "silo":
		i = silo_modul.info(r["silo"])
		r.update({"bestand": i["bestand"], "moeglich_enthalten": i["moeglich_enthalten"]})
	if r.get("charge"):
		b = frappe.db.get_value(
			"Batch",
			r["charge"],
			[
				"item_name",
				"kt_chargen_stufe",
				"kt_status",
				"kt_sperrgrund",
				"manufacturing_date",
				"expiry_date",
				"kt_backtag",
			],
			as_dict=True,
		)
		r.update(
			{
				"artikelname": b.item_name,
				"stufe": b.kt_chargen_stufe,
				"sperrstatus": b.kt_status,
				"sperrgrund": b.kt_sperrgrund,
				"hergestellt": formatdate(b.manufacturing_date) if b.manufacturing_date else None,
				"backtag": formatdate(b.kt_backtag) if b.kt_backtag else None,
				"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
				"abgelaufen": bool(b.expiry_date and getdate(b.expiry_date) < getdate(nowdate())),
			}
		)
	if r.get("artikel") and not r.get("artikelname"):
		r["artikelname"] = frappe.get_cached_value("Item", r["artikel"], "item_name")
	if r["typ"] == "charge":
		r["fundstellen"] = akte_modul.fundstellen(r["charge"])  # „Wo ist dieses Los?“
	return r


@frappe.whitelist()
def akte(code: str) -> dict:
	"""Lebenslauf einer Palette oder eines Behälters (akte.py)."""
	return akte_modul.akte(code)


@frappe.whitelist()
def herkunft(code: str) -> dict:
	"""Woraus besteht das? Für eine Charge bzw. ein Los (auch Kartonetikett) oder einen Behälter mit Inhalt."""
	r = aufloesen(code)
	charge = r.get("charge")
	if not charge:
		_fehler(
			_("Zu {0} gibt es keine Charge. Bei einer Palette bitte das Los wählen.").format(
				frappe.bold(code)
			)
		)
	return akte_modul.herkunft(charge)


# ---------------------------------------------------------------------------
# Prüfen einer gescannten Zutat
# ---------------------------------------------------------------------------


def _pruefe_charge(charge, artikel):
	status, grund, verfall = frappe.db.get_value(
		"Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"]
	)
	if status == "Gesperrt":
		_fehler(_("Charge {0} ist gesperrt: {1}").format(frappe.bold(charge), grund or "-"))
	if verfall and getdate(verfall) < getdate(nowdate()):
		_fehler(
			_("Charge {0} ({1}) ist abgelaufen seit {2}. Nicht verwenden.").format(
				frappe.bold(charge), artikel, formatdate(verfall)
			)
		)


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


def _quellen(artikel: str, auftrag: str | None = None) -> list[dict]:
	"""Wo liegt ein Artikel (ohne Silo/Vorrat/Lagerverkauf)? Behälter einzeln, älteste Ware zuerst."""
	ergebnis = []
	for c in _lager_chargen(artikel, auftrag):
		rest = c["menge"]
		for t in frappe.get_all(
			"Produkttraeger", {"status": "Belegt", "charge": c["charge"]}, ["code", "menge"], order_by="code"
		):
			m = min(flt(t.menge), rest)
			if m > EPS:
				ergebnis.append({**c, "code": t.code, "behaelter": t.code, "menge": flt(m, 3)})
				rest -= m
		if rest > EPS:
			ergebnis.append({**c, "code": c["charge"], "behaelter": None, "menge": flt(rest, 3)})
	return ergebnis


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


# ---------------------------------------------------------------------------
# Buchen
# ---------------------------------------------------------------------------


def _neue_charge(artikel, herstelldatum=None, charge_id=None, lieferant=None, verfall=None):
	if not charge_id:
		# Fertigware bekommt eine kurze Los-Nummer (passt auf Beutel und ins GS1-Etikett)
		kurz = artikel_stufe(artikel) == "Fertigware"
		praefix = ("L" if kurz else f"{artikel}-") + f"{now_datetime().strftime('%y%m%d')}-"
		n = frappe.db.count("Batch", {"name": ["like", praefix + "%"]}) + 1
		while frappe.db.exists("Batch", f"{praefix}{n:02d}"):
			n += 1
		charge_id = f"{praefix}{n:02d}"
	werte = {
		"doctype": "Batch",
		"item": artikel,
		"batch_id": charge_id,
		"manufacturing_date": herstelldatum,
		"supplier": lieferant,
	}
	if verfall:
		werte["expiry_date"] = verfall
	if artikel_stufe(artikel) == "Fertigware":
		werte["kt_los"] = charge_id
	return frappe.get_doc(werte).insert().name


def _se_zeile(z, s_warehouse=None, t_warehouse=None):
	uom = frappe.get_cached_value("Item", z["artikel"], "stock_uom")
	return {
		"item_code": z["artikel"],
		"qty": z["menge"],
		"transfer_qty": z["menge"],
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": z.get("charge"),
		"kt_traeger": z.get("behaelter"),
	}


def _neues_gebinde(gebindeart=None) -> str:
	from frappe.model.naming import getseries

	code = "G" + getseries("KT-GEBINDE-", 6)
	frappe.get_doc(
		{"doctype": "Produkttraeger", "code": code, "typ": "Gebinde", "gebindeart": gebindeart}
	).insert(ignore_permissions=True)
	return code


def _ziel_lager(s, artikel):
	silo = frappe.db.get_value(
		"Silo", {"artikel": artikel, "aktiv": 1}, "warehouse", order_by="creation desc"
	)
	if silo:
		return silo
	lager = s.fertiglager if versandfaehig(artikel) else s.produktionslager
	if not lager:
		_fehler(_("An der Station {0} ist kein Ziellager eingerichtet.").format(s.name))
	return lager


def _ziel_behaelter(code):
	if not code:
		return None
	r = aufloesen(code)
	if r["typ"] != "behaelter":
		_fehler(_("{0} ist kein Behälter.").format(code))
	if r["status"] == "Reinigung":
		_fehler(
			_("Behälter {0} ist zur Reinigung. Erst reinigen und im Info-Scan als gereinigt melden.").format(
				code
			)
		)
	if r["status"] == "Gesperrt":
		_fehler(_("Behälter {0} ist gesperrt.").format(code))
	if r["behaelter_typ"] == "Gebinde":
		_fehler(_("{0} ist ein Gebinde vom Wareneingang, kein Zielbehälter.").format(code))
	if r.get("charge"):
		_fehler(_("Behälter {0} ist noch mit {1} belegt.").format(code, r["charge"]))
	return code


def _meldungen():
	"""Hinweise (msgprint) aus dem Buchen als Text einsammeln."""
	texte = []
	for m in frappe.local.message_log or []:
		try:
			m = json.loads(m) if isinstance(m, str) else m
		except ValueError:
			m = {"message": m}
		text = frappe.utils.strip_html(str(m.get("message") or m))
		if text and text not in texte:
			texte.append(text)
	frappe.local.message_log = []
	return texte


@frappe.whitelist()
def vorschau(
	station: str, ziel: str, zeilen, kundenauftrag: str | None = None, mhd: str | None = None
) -> dict:
	"""Los und MHD, bevor gebucht wird (zum Einstellen des Beuteldruckers)."""
	from keks_trace.genealogie import daten_berechnen

	_station(station)
	if artikel_stufe(ziel) != "Fertigware":
		return {}
	eingaenge = []
	for z in _liste(zeilen):
		r = aufloesen(z["code"])
		if r.get("charge") and r["typ"] != "silo":
			eingaenge.append((r["charge"], r["artikel"], flt(z.get("menge"))))
	charge, los = None, None
	vorgabe = los_modul.mhd_vorgabe(kundenauftrag, nowdate(), mhd)
	if los_modul.format_() == "JWWT":
		los = los_modul.jwwt(nowdate())
		name = f"{ziel}-{getdate(nowdate()).isocalendar()[0]}-{los}"
		if vorgabe:
			name += "-M" + getdate(vorgabe).strftime("%y%m%d")
		charge = name if frappe.db.exists("Batch", name) else None
	werte = daten_berechnen(ziel, eingaenge, nowdate(), charge, "-")
	voll = werte.get("expiry_date")
	vorher = frappe.db.get_value("Batch", charge, "expiry_date") if charge else None
	mhd = min(voll, vorgabe) if voll and vorgabe else voll
	ziel_k = kennzeichnung.artikel_kennzeichen(ziel)
	return {
		"kennzeichen": [k for k in kennzeichnung.ALLE if k in ziel_k],
		"oeko_nr": frappe.db.get_single_value("Keks Trace Einstellungen", "oeko_kontrollnummer")
		if kennzeichnung.BIO in ziel_k
		else None,
		"los": los,
		"los_vorhanden": bool(charge),
		"mhd": formatdate(mhd) if mhd else None,
		"mhd_sinkt": bool(vorher and mhd and getdate(mhd) < getdate(vorher)),
		"mhd_bisher": formatdate(vorher) if vorher else None,
		"mhd_voll": formatdate(voll) if voll else None,
		"mhd_gekuerzt": bool(vorgabe and voll and vorgabe < getdate(voll)),
		"mhd_iso": str(mhd) if mhd else None,
	}


@frappe.whitelist()
@einmalig
def herstellen(
	station: str,
	ziel: str,
	zeilen,
	ausbringung: float | None = None,
	ziel_behaelter: str | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	kundenauftrag: str | None = None,
	pruefwerte=None,
	mhd: str | None = None,
	fefo_grund: str | None = None,
	sollmenge: float | None = None,
	rezept_grund: str | None = None,
) -> dict:
	"""Fertigung buchen: Zutaten (gescannt) -> neue Charge des Ziels, optional in einen Behälter.

	Fertigware: Ausbringung als Anzahl + Einheit (Karton/Beutel); ziel_behaelter darf eine Palette sein.
	fefo_grund: Pflicht, wenn ein Rohstoff/Packmittel mit späterem MHD genommen wird, obwohl ein früheres
	im Lager liegt (FEFO); wird mit der Buchung gespeichert.
	sollmenge / rezept_grund: Sollmenge vom Teigmacher; weicht eine Zutat über die Toleranz ab, ist ein Grund
	Pflicht (Einstellung), siehe _pruefe_rezept.
	"""
	s = _station(station)
	r = rezept(ziel, station=s.name)
	_darf(s, "herstellen")
	pruefung.pruefe_station_frei(s.name)
	if r["stufe"] not in s.stufen_liste():
		_fehler(_("{0} wird nicht an der Station {1} hergestellt.").format(r["name"], s.name))
	linie = frappe.get_cached_value("Item", ziel, "kt_linie")
	if s.linie and linie != s.linie and s.typ != "Verpackungs-PC":
		_fehler(_("{0} gehört nicht zur Linie {1}.").format(r["name"], s.linie))
	erlaubt = {z["artikel"] for z in r["zutaten"]}
	eingaenge = [_zeile(z["code"], z["menge"], ziel, erlaubt) for z in _liste(zeilen)]
	if not eingaenge:
		_fehler(_("Keine Zutaten gescannt."))
	fefo = _pruefe_fefo(eingaenge, fefo_grund)
	rezept_abw = _pruefe_rezept(ziel, sollmenge, eingaenge, rezept_grund)
	pruef_ergebnisse = pruefung.bei_buchung(pruefung.HERSTELLEN, ziel, pruefwerte, s.name)
	pruefung.verweigern_herstellen(pruef_ergebnisse, s.name, _("Herstellen {0}").format(r["name"]))

	summe = sum(
		z["menge"]
		for z in eingaenge
		if z.get("einheit", r["einheit"]) == r["einheit"] and artikel_stufe(z["artikel"]) != "Packmittel"
	)
	if flt(anzahl) > EPS and einheit:
		ausbringung = flt(flt(anzahl) * paletten.faktor(ziel, einheit), 6)
	else:
		anzahl, einheit = None, None
	ausbringung = flt(ausbringung) or flt(summe * r["ausbeute"], 3)
	if kundenauftrag and not _fuer_auftrag(kundenauftrag, ziel):
		_fehler(_("{0} ist im Kundenauftrag {1} nicht bestellt.").format(ziel, kundenauftrag))
	for z in eingaenge:  # für einen anderen Auftrag hergestellte Ware bleibt bei ihm
		reserviert = _reserviert(z.get("charge"))
		if reserviert and reserviert != kundenauftrag:
			_fehler(
				_("{0} ({1}) ist für Kundenauftrag {2} gemacht und dort reserviert.").format(
					z["name"], z["charge"], reserviert
				)
			)
	palette = paletten.finde(ziel_behaelter) if ziel_behaelter else None
	if palette and not versandfaehig(ziel):
		_fehler(_("Auf eine Palette kommen nur Fertigware und lose Ware im Karton."))
	behaelter = None if palette else _ziel_behaelter(ziel_behaelter)
	if palette:
		paletten._offen(palette)

	# Kneter an der Linie: der veredelte Teig geht direkt in den Former, also auf die Linie zum laufenden Auftrag
	linien_auftrag, ziel_lager = None, None
	if s.f_linie:
		from keks_trace import linienbuchung

		linien_auftrag = linienbuchung._laufender(s)
		if ziel not in linienbuchung.linienrezept(linien_auftrag.artikel):
			_fehler(_("{0} gehört nicht zu {1}.").format(r["name"], linien_auftrag.artikelname))
		ziel_lager = frappe.get_cached_value("Linie", s.linie, "lagerort")
		behaelter = None

	vorgabe = los_modul.mhd_vorgabe(kundenauftrag, nowdate(), mhd) if r["stufe"] == "Fertigware" else None
	if r["stufe"] == "Fertigware" and los_modul.format_() == "JWWT":
		charge, _los, _neu = los_modul.tages_charge(ziel, nowdate(), vorgabe)
	else:
		charge = _neue_charge(ziel, getdate(nowdate()))
		if vorgabe:
			frappe.db.set_value("Batch", charge, "kt_mhd_vorgabe", vorgabe)
	if kundenauftrag and r["stufe"] != "Fertigware":
		# Vorstufe für einen Auftrag (z. B. garniertes Herz): reserviert, bis der Auftrag erledigt ist
		frappe.db.set_value("Batch", charge, "kt_kundenauftrag", kundenauftrag)
	jetzt = now_datetime()
	ausgabe = _se_zeile(
		{"artikel": ziel, "charge": charge, "menge": ausbringung, "behaelter": behaelter},
		t_warehouse=ziel_lager or _ziel_lager(s, ziel),
	)
	ausgabe["is_finished_item"] = 1
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Manufacture",
			"purpose": "Manufacture",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_kundenauftrag": kundenauftrag,
			"kt_produktionsauftrag": linien_auftrag.name if linien_auftrag else None,
			"kt_fefo_abweichung": fefo,
			"kt_rezept_abweichung": rezept_abw,
			"items": [_se_zeile(z, s_warehouse=z["lager"]) for z in eingaenge] + [ausgabe],
		}
	)
	se.insert()
	se.submit()
	if palette and kundenauftrag:
		frappe.db.set_value(
			"Palette",
			palette,
			{
				"kundenauftrag": kundenauftrag,
				"kunde": frappe.db.get_value("Sales Order", kundenauftrag, "customer"),
			},
		)
	if palette:
		paletten.beladen(
			palette, charge, anzahl or ausbringung, einheit or frappe.get_cached_value("Item", ziel, "stock_uom"),
			s.name, "Verpackung", "Stock Entry", se.name,
		)  # fmt: skip

	hinweise = pruefung.nach_buchung(pruef_ergebnisse, s.name, charge, se.name)
	hinweise += list(se.flags.kt_fifo_warnungen or [])
	verfall = frappe.db.get_value("Batch", charge, "expiry_date")
	if mhd and verfall and getdate(verfall) < getdate(mhd):
		hinweise.append(
			_("MHD {0} geht nicht, laut Rohstoffen nur bis {1}.").format(formatdate(mhd), formatdate(verfall))
		)
	if se.flags.kt_fehlende_zutaten:
		hinweise.append(_("Laut Rezept nicht gescannt: {0}").format(", ".join(se.flags.kt_fehlende_zutaten)))
	b = frappe.db.get_value(
		"Batch", charge, ["expiry_date", "kt_status", "kt_los", "kt_kennzeichen"], as_dict=True
	)
	return {
		"charge": charge,
		"los": b.kt_los,
		"kennzeichen": b.kt_kennzeichen if b.kt_kennzeichen != kennzeichnung.KEINE else None,
		"artikel": ziel,
		"name": r["name"],
		"menge": ausbringung,
		"anzahl": anzahl,
		"einheit": einheit,
		"behaelter": behaelter,
		"palette": palette,
		"kundenauftrag": kundenauftrag,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"buchung": se.name,
		"hinweise": [h for h in dict.fromkeys(hinweise + _meldungen())],
	}


@frappe.whitelist()
@einmalig
def rework_erfassen(
	station: str, quelle: str, menge: float, rework_artikel: str, ziel_behaelter: str | None = None
) -> dict:
	"""Teigreste oder Bruch in einen Rework-Behälter umfüllen (neue Rework-Charge)."""
	s = _station(station)
	_darf(s, "rework")
	if artikel_stufe(rework_artikel) != "Rework":
		_fehler(_("{0} ist kein Rework-Artikel.").format(rework_artikel))
	q = _zeile(quelle, menge)
	if q["typ"] == "silo":
		_fehler(_("Aus einem Silo kann kein Rework erfasst werden."))

	zuviel = allergene(frappe.get_cached_value("Item", q["artikel"], "kt_allergengruppe")) - allergene(
		frappe.get_cached_value("Item", rework_artikel, "kt_allergengruppe")
	)
	if zuviel:
		_fehler(
			_(
				"{0} enthält Allergene, die {1} nicht hat: {2}. Bitte den passenden Rework-Behälter wählen."
			).format(q["name"], rework_artikel, ", ".join(sorted(a.capitalize() for a in zuviel)))
		)
	behaelter = _ziel_behaelter(ziel_behaelter)
	charge = _neue_charge(rework_artikel, getdate(nowdate()))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Repack",
			"purpose": "Repack",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile(q, s_warehouse=q["lager"]),
				_se_zeile(
					{
						"artikel": rework_artikel,
						"charge": charge,
						"menge": q["menge"],
						"behaelter": behaelter,
					},
					t_warehouse=_ziel_lager(s, rework_artikel),
				),
			],
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", rework_artikel, "item_name"),
		"menge": q["menge"],
		"behaelter": behaelter,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"buchung": se.name,
		"hinweise": _meldungen(),
	}


@frappe.whitelist()
@einmalig
def wareneingang(
	station: str,
	artikel: str,
	lieferantencharge: str,
	menge: float,
	mhd: str | None = None,
	lieferant: str | None = None,
	silo: str | None = None,
	gebinde: int | None = None,
	gebindeart: str | None = None,
	pruefwerte=None,
	etiketten=1,
) -> dict:
	"""Wareneingang mit Lieferantencharge, ins Rohstofflager oder direkt ins Silo.

	gebinde = Anzahl Gebinde (Sack, Fass, IBC, ...); menge ist dann die Menge JE Gebinde.
	etiketten = 1: jedes Gebinde bekommt einen eigenen Code (Etikett) und wird in der Backstube gescannt.
	etiketten = 0: kein eigenes Etikett - das Etikett des Lieferanten trägt die Charge (GS1-128) und wird
	in der Backstube gescannt; gebucht wird die Gesamtmenge auf die Charge.
	"""
	s = _station(station)
	_darf(s, "wareneingang")
	menge = flt(menge)
	gebinde = cint(gebinde) if not silo else 0
	lieferantencharge = (lieferantencharge or "").strip()
	if menge <= EPS:
		_fehler(_("Bitte eine Menge größer 0 eingeben."))
	if not lieferantencharge:
		_fehler(_("Bitte die Charge des Lieferanten scannen oder eingeben."))
	g = gs1.lesen(lieferantencharge)
	if g:
		# Ganzes Lieferanten-Etikett ins Chargenfeld gescannt: Charge herauslesen, Artikel muss passen
		treffer = _artikel_zur_gtin(g["gtin"]) if g.get("gtin") else None
		if treffer and treffer["artikel"] != artikel:
			_fehler(
				_("Das Etikett gehört zu {0} ({1}), nicht zu {2}.").format(
					treffer["artikel"],
					frappe.get_cached_value("Item", treffer["artikel"], "item_name"),
					artikel,
				)
			)
		if not g.get("charge"):
			_fehler(_("Auf diesem Etikett steht keine Charge im Strichcode. Bitte die Charge abtippen."))
		lieferantencharge = g["charge"]
	_pruefe_lieferantencharge(artikel, lieferantencharge)
	if frappe.get_cached_value("Item", artikel, "has_expiry_date") and not mhd:
		_fehler(_("Bitte das MHD eingeben."))
	if mhd:
		try:
			mhd = getdate(mhd)
		except Exception:
			_fehler(_("MHD {0} ist kein gültiges Datum.").format(mhd))
		if mhd < getdate(nowdate()):
			_fehler(
				_("MHD {0} liegt in der Vergangenheit: Ware abgelaufen, nicht annehmen.").format(
					formatdate(mhd)
				)
			)
	if kennzeichnung.BIO in kennzeichnung.artikel_kennzeichen(artikel):
		kennzeichnung.pruefe_bio_lieferant(lieferant, artikel)

	pruef_ergebnisse = pruefung.bei_buchung(pruefung.WARENEINGANG, artikel, pruefwerte, s.name)
	abgelehnt = pruefung.verweigert(pruef_ergebnisse)
	if abgelehnt:
		# Annahme verweigern: nichts buchen, aber die Prüfung protokollieren
		for p, ok, felder in pruef_ergebnisse:
			pruefung.protokoll(
				p, ok, felder, station=s.name,
				folge=_("Annahme verweigert") if not ok else None,
				bemerkung=_("Lieferantencharge {0}, {1} {2}").format(lieferantencharge, menge, artikel),
			)  # fmt: skip
		return {
			"abgelehnt": True,
			"name": frappe.get_cached_value("Item", artikel, "item_name"),
			"gruende": [
				_("{0}: gemessen {1} {2}, erlaubt {3}").format(
					p.titel,
					pruefung._zahl(f["wert"]) if "wert" in f else "-",
					f.get("einheit") or "",
					f.get("grenzwert"),
				)
				for p, _ok, f in abgelehnt
			],
			"korrektur": [p.korrekturmassnahme for p, _ok, _f in abgelehnt if p.korrekturmassnahme],
		}

	if silo:
		silo_doc = frappe.get_cached_doc("Silo", silo)
		if silo_doc.artikel != artikel:
			_fehler(_("{0} ist für {1}, nicht für {2}.").format(silo, silo_doc.artikel, artikel))
		lager = silo_doc.warehouse
	else:
		lager = s.rohstofflager
		if not lager:
			_fehler(_("An der Station {0} ist kein Rohstofflager eingerichtet.").format(s.name))

	charge_id = _charge_name(artikel, lieferantencharge)
	charge = (
		charge_id
		if frappe.db.exists("Batch", charge_id)
		else _neue_charge(artikel, None, charge_id, lieferant, getdate(mhd) if mhd else None)
	)

	jetzt = now_datetime()
	if gebinde and not cint(etiketten):
		menge, gebinde = menge * gebinde, 0
	codes = [_neues_gebinde(gebindeart) for _i in range(gebinde)]
	rate = flt(frappe.get_cached_value("Item", artikel, "valuation_rate"))
	zeilen = []
	for code in codes or [None]:
		zeile = _se_zeile(
			{"artikel": artikel, "charge": charge, "menge": menge, "behaelter": code}, t_warehouse=lager
		)
		if rate:
			zeile["basic_rate"] = rate
		else:
			zeile["allow_zero_valuation_rate"] = 1
		zeilen.append(zeile)
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": zeilen,
		}
	)
	se.insert()
	se.submit()
	pruef_hinweise = pruefung.nach_buchung(pruef_ergebnisse, s.name, charge, se.name)
	b = frappe.db.get_value("Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"menge": flt(menge * (len(codes) or 1), 3),
		"gebinde": codes,
		"pruef_hinweise": pruef_hinweise,
		"lager": silo or lager,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"sperrgrund": b.kt_sperrgrund,
		"buchung": se.name,
		"hinweise": pruef_hinweise + _meldungen(),
	}


def _lieferpositionen(z, aus_verkauf=False):
	"""Eine Lieferzeile vom Terminal in Positionen auflösen.

	{"palette": NVE, "ganz": 1}                          ganze Palette
	{"palette": NVE, "charge": Los, "anzahl", "einheit"}   einzelne Kartons von einer Palette
	{"code": Los, "anzahl", "einheit"}                     lose Kartons (auf keiner Palette)
	"""
	if z.get("palette") and z.get("ganz"):
		nve = paletten.finde(z["palette"])
		if not nve:
			_fehler(_("Palette {0} gibt es nicht.").format(z["palette"]))
		status = frappe.db.get_value("Palette", nve, "status")
		if status not in paletten.AKTIV:
			_fehler(_("Palette {0} ist {1}.").format(nve, status.lower()))
		pos = [(p, nve) for p in paletten.inhalt(nve)]
		# Versandkartons auf der Palette gehören dazu; gebucht wird je Karton (seine NVE an der Position)
		for k in paletten.kartons(nve):
			pos += [(p, k) for p in paletten.inhalt(k)]
		if not pos:
			_fehler(_("Palette {0} ist leer.").format(nve))
		return [_lieferposition(p["charge"], p["anzahl"], p["einheit"], von, aus_verkauf) for p, von in pos]
	if z.get("palette"):
		nve = paletten.finde(z["palette"])
		pos = paletten._position(nve, z.get("charge"), z.get("einheit")) if nve else None
		if not pos or flt(z.get("anzahl")) > pos["anzahl"] + EPS:
			_fehler(
				_("Auf Palette {0} sind von Los {1} nur {2} {3}.").format(
					z["palette"], z.get("charge"), flt(pos["anzahl"]) if pos else 0, z.get("einheit")
				)
			)
		return [_lieferposition(z["charge"], z["anzahl"], z["einheit"], nve, aus_verkauf)]
	r = aufloesen(z.get("code"))
	if r["typ"] == "palette":
		return _lieferpositionen({"palette": r["palette"], "ganz": 1}, aus_verkauf)
	if r["typ"] != "charge":
		_fehler(_("Bitte ein Los oder eine Palette scannen."))
	anzahl = flt(z.get("anzahl") if z.get("anzahl") is not None else z.get("menge"))
	einheit = z.get("einheit") or frappe.get_cached_value("Item", r["artikel"], "stock_uom")
	menge = anzahl * paletten.faktor(r["artikel"], einheit)
	frei = paletten.lose(r["charge"])
	if menge > frei + 1e-4:
		_fehler(
			_(
				"Von Los {0} sind nur {1} {2} lose. Der Rest steht auf Paletten: bitte die Palette scannen."
			).format(r["charge"], paletten._anzahl_text(r["artikel"], frei, einheit), einheit)
		)
	return [_lieferposition(r["charge"], anzahl, einheit, None, aus_verkauf)]


def _verkaufslager() -> set:
	"""Lagerorte des Lagerverkaufs: daraus wird nicht geliefert oder umgelagert."""
	return set(frappe.get_all("Warehouse", filters={"kt_lagerverkauf": 1}, pluck="name"))


@frappe.whitelist()
def umlager_ziele(station: str) -> list[dict]:
	"""Lagerorte, die an dieser Station beim Umlagern zur Auswahl stehen (fest eingestelltes Ziel zuerst)."""
	s = _station(station)
	ziele = frappe.get_all(
		"Warehouse",
		filters={"kt_umlagerziel": 1, "company": s.company, "disabled": 0},
		fields=["name", "warehouse_name", "kt_lagerverkauf"],
		order_by="kt_lagerverkauf desc, warehouse_name",
	)
	if s.umlager_ziel:
		fest = [
			{
				"name": s.umlager_ziel,
				"titel": frappe.get_cached_value("Warehouse", s.umlager_ziel, "warehouse_name"),
				"lagerverkauf": int(s.umlager_ziel in _verkaufslager()),
			}
		]
		if not fest[0]["lagerverkauf"]:
			return fest
		# Am Lagerverkauf: auch zurück ins Lager (Rücknahme, z. B. zu viel geholt)
		return fest + [
			{"name": z.name, "titel": z.warehouse_name, "lagerverkauf": 0, "zurueck": 1}
			for z in ziele
			if not z.kt_lagerverkauf
		]
	return [{"name": z.name, "titel": z.warehouse_name, "lagerverkauf": z.kt_lagerverkauf} for z in ziele]


def _lieferposition(charge, anzahl, einheit, palette, aus_verkauf=False):
	artikel = frappe.db.get_value("Batch", charge, "item")
	if not versandfaehig(artikel):
		_fehler(
			_("{0} ist weder Fertigware noch lose Ware im Karton.").format(
				frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	if flt(anzahl) <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	_pruefe_charge(charge, artikel)
	f = paletten.faktor(artikel, einheit)
	verkauf = _verkaufslager()
	auf_linie = set(frappe.get_all("Linie", pluck="lagerort"))  # gehört dem laufenden Produktionsauftrag
	# Rücknahme aus dem Lagerverkauf: nur Bestand dort; sonst nie aus dem Lagerverkauf
	lager = {
		w: m
		for w, m in charge_lager(charge).items()
		if (w in verkauf) == bool(aus_verkauf) and w not in auf_linie
	}
	if not lager:
		_fehler(
			_("Los {0} hat keinen Bestand im {1}.").format(
				charge, _("Lagerverkauf") if aus_verkauf else _("Lager")
			)
		)
	if flt(anzahl) * f > max(lager.values()) + 1e-4:
		_fehler(
			_("Von Los {0} sind im Lager nur {1} {2}.").format(
				charge, paletten._anzahl_text(artikel, max(lager.values()), einheit), einheit
			)
		)
	return {
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"charge": charge,
		"anzahl": flt(anzahl, 3),
		"einheit": einheit,
		"faktor": f,
		"menge": flt(flt(anzahl) * f, 3),
		"palette": palette,
		"lager": max(lager, key=lager.get),
	}


@frappe.whitelist()
def pruefe_lieferzeile(
	station: str,
	code: str | None = None,
	menge: float | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	palette: str | None = None,
	charge: str | None = None,
	ganz: int = 0,
) -> list[dict]:
	"""Sofortprüfung am Versand. Gibt die Positionen zurück (ganze Palette = mehrere)."""
	_station(station)
	return _lieferpositionen(
		{"code": code, "menge": menge, "anzahl": anzahl, "einheit": einheit, "palette": palette,
		 "charge": charge, "ganz": cint(ganz)}
	)  # fmt: skip


def _lieferzeile(p, kundenauftrag, auftrag_pos) -> dict:
	"""Lieferscheinposition. Mit Auftrag in dessen Einheit (z. B. 0,48 Palette), gezählt bleibt 20 Karton."""
	zeile = {
		"item_code": p["artikel"],
		"qty": p["anzahl"],
		"uom": p["einheit"],
		"conversion_factor": p["faktor"],
		"rate": flt(frappe.get_cached_value("Item", p["artikel"], "standard_rate")) * p["faktor"],
		"warehouse": p["lager"],
		"use_serial_batch_fields": 1,
		"batch_no": p["charge"],
		"kt_palette": p["palette"],
		"kt_anzahl": p["anzahl"],
		"kt_einheit": p["einheit"],
	}
	if kundenauftrag and auftrag_pos.get(p["artikel"]):
		uom, cf, rate = auftrag_pos[("einheit", p["artikel"])]
		zeile.update(
			{
				"qty": flt(p["menge"] / cf, 6),
				"uom": uom,
				"conversion_factor": cf,
				"rate": rate,
				"against_sales_order": kundenauftrag,
				"so_detail": auftrag_pos[p["artikel"]],
			}
		)
	return zeile


@frappe.whitelist()
@einmalig
def lieferung(station: str, kunde: str, zeilen, kundenauftrag: str | None = None) -> dict:
	"""Lieferschein an einen Kunden mit gescannten Paletten und Losen, optional zu einem Kundenauftrag."""
	s = _station(station)
	_darf(s, "lieferung")
	if not frappe.db.exists("Customer", kunde):
		_fehler(_("Kunde {0} unbekannt.").format(kunde))
	positionen = [p for z in _liste(zeilen) for p in _lieferpositionen(z)]
	if not positionen:
		_fehler(_("Nichts gescannt."))
	auftrag_pos = {}
	if kundenauftrag:
		if frappe.db.get_value("Sales Order", kundenauftrag, "customer") != kunde:
			_fehler(_("Kundenauftrag {0} gehört nicht zu {1}.").format(kundenauftrag, kunde))
		for r in frappe.get_all(
			"Sales Order Item",
			{"parent": kundenauftrag},
			["name", "item_code", "rate", "conversion_factor", "uom"],
			order_by="idx",
		):
			auftrag_pos.setdefault(r.item_code, r.name)
			# ERPNext verlangt im Lieferschein dieselbe Einheit wie im Auftrag (z. B. Palette)
			auftrag_pos.setdefault(
				("einheit", r.item_code), (r.uom, flt(r.conversion_factor) or 1, flt(r.rate))
			)
		fremd = sorted({p["artikel"] for p in positionen if p["artikel"] not in auftrag_pos})
		if fremd:
			_fehler(_("Nicht im Kundenauftrag {0} bestellt: {1}").format(kundenauftrag, ", ".join(fremd)))
	jetzt = now_datetime()
	dn = frappe.get_doc(
		{
			"doctype": "Delivery Note",
			"customer": kunde,
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [_lieferzeile(p, kundenauftrag, auftrag_pos) for p in positionen],
		}
	)
	dn.insert()
	dn.submit()
	return {
		"lieferschein": dn.name,
		"kundenauftrag": kundenauftrag,
		"kunde": dn.customer_name,
		"positionen": len(positionen),
		"menge": flt(sum(p["menge"] for p in positionen), 3),
		"paletten": sorted({p["palette"] for p in positionen if p["palette"]}),
		"hinweise": _meldungen(),
	}


# ---------------------------------------------------------------------------
# Paketversand (DHL) direkt vom Herzenboden: Lieferschein mit Paketen, gewogenem Gewicht, Sendungsnummer
# ---------------------------------------------------------------------------

KARTON_TARA_KG = 0.3  # Versandkarton je Paket, für den Plausibilitäts-Vorschlag


@frappe.whitelist()
def paket_vorschlag(station: str, artikel: str, stueck: float, pakete: int = 1) -> dict:
	"""Erwartetes Gewicht (Stückgewicht am Artikel mal Stück + Karton) und was vom verpackten Bestand da ist."""
	_station(station)
	je, einheit = frappe.get_cached_value("Item", artikel, ["weight_per_unit", "weight_uom"])
	faktor = 0.001 if (einheit or "").lower() in ("g", "gram", "gramm") else 1
	netto = flt(je) * faktor * flt(stueck)
	return {
		"erwartet_kg": flt(netto + KARTON_TARA_KG * max(cint(pakete), 1), 2) if je else None,
		"verfuegbar": _verfuegbar(artikel),
		"adresse": None,
	}


def _kundenadresse(artikel=None, kunde=None) -> str | None:
	if not kunde:
		return None
	from frappe.contacts.doctype.address.address import get_address_display, get_default_address

	name = get_default_address("Customer", kunde)
	return frappe.utils.strip_html(get_address_display(name)).strip() if name else None


@frappe.whitelist()
@einmalig
def paket_lieferung(
	station: str,
	kundenauftrag: str,
	artikel: str | None = None,
	stueck: float | None = None,
	gewichte=None,
	sendungsnummer: str | None = None,
	kartons=None,
) -> dict:
	"""Herzen direkt per DHL: Lieferschein über die Stückzahl (älteste Lose zuerst), dazu Pakete und das
	auf der Paketwaage abgelesene Gewicht je Paket. Die Sendungsnummer kann auch später nachgetragen werden."""
	s = _station(station)
	_darf(s, "lieferung")
	if kartons:
		return _paket_lieferung_kartons(s, kundenauftrag, _liste(kartons), sendungsnummer)
	gewichte = [flt(g, 3) for g in _liste(gewichte) if flt(g) > 0]
	if not gewichte:
		_fehler(_("Bitte das Gewicht jedes Pakets von der Paketwaage eintragen."))
	kunde = frappe.db.get_value("Sales Order", kundenauftrag, "customer")
	if not kunde:
		_fehler(_("Kundenauftrag {0} gibt es nicht.").format(kundenauftrag))
	einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	offen, zeilen = flt(stueck), []
	for c in _lager_chargen(artikel):
		if offen <= EPS:
			break
		frei = min(c["menge"], paletten.lose(c["charge"]))
		n = min(offen, frei)
		if n > EPS:
			zeilen.append({"code": c["charge"], "anzahl": n, "einheit": einheit})
			offen -= n
	if offen > EPS:
		_fehler(
			_("Verpackt im Lager sind nur {0}. Erst verpacken.").format(
				paletten._n(flt(stueck) - offen, einheit)
			)
		)
	erg = lieferung(s.name, kunde, zeilen, kundenauftrag)
	gesamt = flt(sum(gewichte), 3)
	frappe.db.set_value(
		"Delivery Note",
		erg["lieferschein"],
		{
			"kt_pakete": len(gewichte),
			"kt_gewicht_kg": gesamt,
			"kt_paket_gewichte": " / ".join(f"{g:g}".replace(".", ",") for g in gewichte),
			"kt_sendungsnummer": (sendungsnummer or "").strip() or None,
		},
	)
	vorschlag = paket_vorschlag(s.name, artikel, stueck, len(gewichte))
	hinweise = erg["hinweise"]
	erwartet = vorschlag["erwartet_kg"]
	if erwartet and abs(gesamt - erwartet) > erwartet * 0.15:
		hinweise.append(
			_("Gewogen {0} kg, erwartet etwa {1} kg. Bitte Stückzahl im Paket prüfen.").format(
				f"{gesamt:g}".replace(".", ","), f"{erwartet:g}".replace(".", ",")
			)
		)
	return {
		**erg,
		"pakete": len(gewichte),
		"gewicht_kg": gesamt,
		"erwartet_kg": erwartet,
		"adresse": _kundenadresse(kunde=kunde),
		"lose": [z["code"] for z in zeilen],
		"hinweise": hinweise,
	}


def _paket_lieferung_kartons(s, kundenauftrag: str, kartons: list, nummer: str | None) -> dict:
	"""Pakete als Versandkartons: jeder Karton ganz in den Lieferschein, Gewichte aus den Kartons."""
	kunde = frappe.db.get_value("Sales Order", kundenauftrag, "customer")
	if not kunde:
		_fehler(_("Kundenauftrag {0} gibt es nicht.").format(kundenauftrag))
	nves = []
	for code in kartons:
		nve = paletten.finde(code)
		if not nve or frappe.db.get_value("Palette", nve, "typ") != paletten.VERSANDKARTON:
			_fehler(_("{0} ist kein Versandkarton.").format(code))
		nves.append(nve)
	if len(set(nves)) != len(nves):
		_fehler(_("Ein Versandkarton ist doppelt gescannt."))
	erg = lieferung(s.name, kunde, [{"palette": n, "ganz": 1} for n in nves], kundenauftrag)
	gewichte = [flt(frappe.db.get_value("Palette", n, "gewicht_kg"), 3) for n in nves]
	frappe.db.set_value(
		"Delivery Note",
		erg["lieferschein"],
		{
			"kt_pakete": len(nves),
			"kt_gewicht_kg": flt(sum(gewichte), 3) or None,
			"kt_paket_gewichte": " / ".join(f"{g:g}".replace(".", ",") for g in gewichte if g) or None,
			"kt_sendungsnummer": None,
		},
	)
	if (nummer or "").strip():
		sendungsnummer(s.name, erg["lieferschein"], nummer)
	return {
		**erg,
		"pakete": len(nves),
		"gewicht_kg": flt(sum(gewichte), 3),
		"versandkartons": nves,
		"adresse": _kundenadresse(kunde=kunde),
		"lose": sorted({b for n in nves for b in _lose_im_karton(n, erg["lieferschein"])}),
	}


@frappe.whitelist()
@einmalig
def paket_karton(
	station: str, kundenauftrag: str, artikel: str, stueck: float, gewicht: float | None = None
) -> dict:
	"""Ein Paket als Versandkarton mit eigener NVE packen: Stück dieses Artikels (älteste Lose zuerst, lose im
	Lager) in einen neuen Versandkarton, dazu das Gewicht von der Paketwaage. Geliefert wird später mit
	paket_lieferung(kartons=…)."""
	s = _station(station)
	_darf(s, "lieferung")
	kunde = frappe.db.get_value("Sales Order", kundenauftrag, "customer")
	if not kunde:
		_fehler(_("Kundenauftrag {0} gibt es nicht.").format(kundenauftrag))
	stueck = flt(stueck)
	if stueck <= EPS:
		_fehler(_("Bitte die Stückzahl im Paket eingeben."))
	einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	offen, teile = stueck, []
	for c in _lager_chargen(artikel):
		if offen <= EPS:
			break
		n = min(offen, min(c["menge"], paletten.lose(c["charge"])))
		if n > EPS:
			teile.append((c["charge"], n))
			offen -= n
	if offen > EPS:
		_fehler(
			_("Verpackt im Lager sind nur {0}. Erst verpacken.").format(paletten._n(stueck - offen, einheit))
		)
	nve = paletten.anlegen(paletten.VERSANDKARTON, s.name, kunde)
	frappe.db.set_value(
		"Palette", nve, {"kundenauftrag": kundenauftrag, "gewicht_kg": flt(gewicht, 3) or None}
	)
	for charge, n in teile:
		paletten.beladen(nve, charge, n, einheit, s.name)
	paletten.schliessen(nve)
	return paletten.info(nve)


@frappe.whitelist()
def sendungsnummer(station: str, lieferschein: str, nummer: str) -> dict:
	"""DHL-Sendungsnummer nachtragen (vom Label scannen); mehrere Pakete: jede Nummer einzeln hinzufügen."""
	_station(station)
	nummer = (nummer or "").strip()
	if not nummer:
		_fehler(_("Bitte die Sendungsnummer scannen oder eintippen."))
	alt = frappe.db.get_value("Delivery Note", lieferschein, "kt_sendungsnummer") or ""
	neu = "\n".join([x for x in alt.splitlines() if x.strip()] + [nummer])
	frappe.db.set_value("Delivery Note", lieferschein, "kt_sendungsnummer", neu)
	# Pakete als Versandkarton: die Nummer gehört zum nächsten Karton dieses Lieferscheins ohne Nummer
	karton = None
	for k in _versandkartons_im_lieferschein(lieferschein):
		if not frappe.db.get_value("Palette", k, "sendungsnummer"):
			frappe.db.set_value("Palette", k, "sendungsnummer", nummer)
			karton = k
			break
	return {"lieferschein": lieferschein, "sendungsnummern": neu.splitlines(), "versandkarton": karton}


def _lose_im_karton(karton: str, lieferschein: str) -> list[str]:
	return frappe.get_all(
		"Paletten Bewegung",
		filters={"palette": karton, "beleg": lieferschein, "art": "Lieferung"},
		pluck="charge",
		distinct=True,
	)


def _versandkartons_im_lieferschein(lieferschein: str) -> list[str]:
	return [
		k
		for k in dict.fromkeys(
			frappe.get_all(
				"Paletten Bewegung",
				filters={"beleg_typ": "Delivery Note", "beleg": lieferschein, "art": "Lieferung"},
				pluck="palette",
				order_by="creation",
			)
		)
		if frappe.db.get_value("Palette", k, "typ") == paletten.VERSANDKARTON
	]


# ---------------------------------------------------------------------------
# Umlagern (z. B. ins Lager des Lagerverkaufs)
# ---------------------------------------------------------------------------


@frappe.whitelist()
@einmalig
def umlagern(
	station: str,
	code: str | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	palette: str | None = None,
	charge: str | None = None,
	ganz: int = 0,
	nach: str | None = None,
) -> dict:
	"""Lose, Kartons oder eine ganze Palette in einen anderen Lagerort umlagern (z. B. Lagerverkauf).

	Ist an der Station ein Ziel fest eingestellt, gilt es; sonst wird eins der Umlager-Ziele gewählt.
	"""
	s = _station(station)
	_darf(s, "umlagern")
	erlaubt = {z["name"] for z in umlager_ziele(s.name)}
	ziel = nach or s.umlager_ziel
	if not ziel:
		_fehler(_("Bitte wählen, wohin umgelagert wird."))
	if ziel not in erlaubt:
		_fehler(_("Nach {0} kann an der Station {1} nicht umgelagert werden.").format(ziel, s.name))
	verkauf = _verkaufslager()
	aus_verkauf = ziel not in verkauf and s.umlager_ziel in verkauf
	positionen = _lieferpositionen(
		{
			"code": code,
			"anzahl": anzahl,
			"einheit": einheit,
			"palette": palette,
			"charge": charge,
			"ganz": cint(ganz),
		},
		aus_verkauf,
	)
	for p in positionen:
		if p["lager"] == ziel:
			_fehler(_("Los {0} liegt schon in {1}.").format(p["charge"], ziel))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile(
					{"artikel": p["artikel"], "charge": p["charge"], "menge": p["menge"]}, p["lager"], ziel
				)
				for p in positionen
			],
		}
	)
	se.insert()
	se.submit()
	for p in positionen:
		if p["palette"]:
			paletten._bewegung(
				p["palette"], "Abgang", "Umlagerung", p["charge"], p["anzahl"], p["einheit"],
				s.name, "Stock Entry", se.name,
			)  # fmt: skip
	for nve in {p["palette"] for p in positionen if p["palette"]}:
		paletten._status_pruefen(nve)
	return {
		"buchung": se.name,
		"nach": ziel,
		"positionen": [
			{"name": p["name"], "charge": p["charge"], "anzahl": p["anzahl"], "einheit": p["einheit"]}
			for p in positionen
		],
		"hinweise": _meldungen(),
	}


# ---------------------------------------------------------------------------
# Paletten
# ---------------------------------------------------------------------------


def _palette(code):
	nve = paletten.finde(code)
	if not nve:
		_fehler(_("{0} ist keine Palette.").format(code))
	return nve


@frappe.whitelist()
def einheiten(artikel: str) -> list[dict]:
	return paletten.einheiten(artikel)


@frappe.whitelist()
@einmalig
def palette_neu(station: str, typ: str = "Lagerpalette", kunde: str | None = None) -> dict:
	s = _station(station)
	if not (s.f_paletten or s.f_herstellen):
		_darf(s, "paletten")
	nve = paletten.anlegen(typ, s.name, kunde)
	return paletten.info(nve)


@frappe.whitelist()
@einmalig
def karton_auf_palette(station: str, karton: str, palette: str) -> dict:
	"""Versandkarton (eigene NVE) auf eine Palette mit NVE stellen."""
	s = _station(station)
	if not (s.f_paletten or s.f_lieferung or s.f_herstellen or s.f_palette_fertig):
		_darf(s, "paletten")
	return paletten.karton_auf_palette(_palette(karton), _palette(palette), s.name)


@frappe.whitelist()
@einmalig
def karton_abnehmen(station: str, karton: str) -> dict:
	"""Versandkarton von seiner Palette nehmen; er bleibt im Lager."""
	s = _station(station)
	nve = _palette(karton)
	palette = frappe.db.get_value("Palette", nve, "auf_palette")
	paletten.karton_abnehmen(nve, s.name)
	return paletten.info(palette) if palette else paletten.info(nve)


@frappe.whitelist()
def palette_info(code: str) -> dict:
	return paletten.info(_palette(code))


@frappe.whitelist()
@einmalig
def palette_beladen(station: str, palette: str, code: str, anzahl: float, einheit: str) -> dict:
	"""Lose Kartons eines Loses auf die Palette (Los-Etikett scannen)."""
	s = _station(station)
	_darf(s, "paletten")
	r = aufloesen(code)
	if r["typ"] != "charge":
		_fehler(_("Bitte das Los scannen."))
	return paletten.beladen(_palette(palette), r["charge"], anzahl, einheit, s.name)


@frappe.whitelist()
@einmalig
def palette_umpacken(station: str, von: str, nach: str, charge: str, anzahl: float, einheit: str) -> dict:
	s = _station(station)
	_darf(s, "paletten")
	erg = paletten.umpacken(_palette(von), _palette(nach), charge, anzahl, einheit, s.name)
	erg["hinweise"] = _meldungen()  # z. B. „Etikett der Quellpalette neu drucken“
	return erg


@frappe.whitelist()
def palette_schliessen(station: str, palette: str) -> dict:
	_darf(_station(station), "paletten")
	return paletten.schliessen(_palette(palette))


@frappe.whitelist()
def palette_oeffnen(station: str, palette: str) -> dict:
	_darf(_station(station), "paletten")
	return paletten.oeffnen(_palette(palette))


@frappe.whitelist()
@einmalig
def silo_leer(station: str, silo: str) -> dict:
	from keks_trace.silo import leermeldung

	s = _station(station)
	_darf(s, "silo")
	erg = leermeldung(silo, bemerkung=_("Leermeldung am Terminal {0}").format(s.name))
	if erg.get("ausbuchung"):
		frappe.db.set_value("Stock Entry", erg["ausbuchung"], "kt_station", s.name)
	erg["hinweise"] = _meldungen()
	return erg


# ---------------------------------------------------------------------------
# Linie: Produktionsaufträge, Zuführen, Packstation, Palette fertig
# ---------------------------------------------------------------------------


def _linien_station(station):
	s = _station(station)
	if not (s.f_linie or s.f_packstation or s.f_palette_fertig):
		_fehler(_("Die Station {0} arbeitet nicht an einer Linie.").format(s.name))
	return s


@frappe.whitelist()
def linie_retour_liste(station: str) -> list[dict]:
	"""Retour: was vom laufenden Auftrag unbenutzt zurück ins Lager kann."""
	from keks_trace import linienbuchung

	return linienbuchung.retour_liste(_linien_station(station).name)


@frappe.whitelist()
@einmalig
def linie_rueckgabe(station: str, charge: str, menge: float) -> dict:
	from keks_trace import linienbuchung

	return linienbuchung.rueckgabe(_linien_station(station).name, charge, menge)


@frappe.whitelist()
def tagesuebersicht(station: str, datum: str | None = None) -> dict:
	"""Aufträge des Tages je Linie (nur lesen, jede Station)."""
	from keks_trace import linienbuchung

	_station(station)
	frappe.has_permission("Produktionsauftrag", "read", throw=True)
	return linienbuchung.tagesuebersicht(datum)


@frappe.whitelist()
def linie_auftraege(station: str) -> list[dict]:
	from keks_trace import linienbuchung

	return linienbuchung.auftraege(_linien_station(station).name)


@frappe.whitelist()
def linie_waehlen(station: str, auftrag: str) -> dict:
	from keks_trace import linienbuchung

	return linienbuchung.waehlen(_linien_station(station).name, auftrag)


@frappe.whitelist()
def linie_info(station: str) -> dict:
	from keks_trace import linienbuchung

	s = _linien_station(station)
	name = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	return linienbuchung.info(name) if name else {}


@frappe.whitelist()
@einmalig
def linie_zufuehren(
	station: str, code: str, menge: float | None = None, fefo_grund: str | None = None
) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "linie")
	return linienbuchung.zufuehren(s.name, code, menge, fefo_grund)


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


@frappe.whitelist()
@einmalig
def linie_palette(station: str, anzahl: float, einheit: str, palette: str | None = None) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "palette_fertig")
	return linienbuchung.palette_fertig(s.name, anzahl, einheit, palette)


@frappe.whitelist()
@einmalig
def linie_lose(
	station: str,
	anzahl: float,
	einheit: str | None = None,
	ziel: str = "lager",
	palette: str | None = None,
	kiste: str | None = None,
) -> dict:
	"""Lose Ware vom laufenden Auftrag: Kartons ins Lager (F5, optional auf Palette) oder ins Linienlager (F6)."""
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "palette_fertig")
	return linienbuchung.lose_fertig(s.name, anzahl, einheit, ziel, palette, kiste)


@frappe.whitelist()
def rework_linie_auftraege(station: str) -> list[dict]:
	"""Backstube: laufende Linienaufträge, je mit den passenden Rework-Sorten (Filter) und freien Behältern."""
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "rework")
	return [
		{**a, "sorten": linienbuchung.rework_sorten(a["auftrag"])} for a in linienbuchung.laufende_auftraege()
	]


@frappe.whitelist()
def freie_rework_behaelter(station: str) -> list[dict]:
	_station(station)
	return frappe.get_all(
		"Produkttraeger", {"typ": "Rework-Behälter", "status": "Frei"}, ["code"], order_by="code", limit=100
	)


@frappe.whitelist()
@einmalig
def rework_linie(station: str, auftrag: str, rework_artikel: str, kg: float, behaelter: str) -> dict:
	"""Backstube bucht einen gewogenen Rework-Behälter von der Linie (Flussschema F18)."""
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "rework")
	return linienbuchung.rework_von_linie(s.name, auftrag, rework_artikel, kg, behaelter)


@frappe.whitelist()
@einmalig
def behaelter_reinigung(station: str, code: str, gereinigt=1) -> dict:
	"""Behälter zur Reinigung geben (gereinigt=0) oder als gereinigt melden (gereinigt=1, dann wieder frei).

	Nur leere Behälter. Gesperrte bleiben gesperrt (Freigabe nur durch die QS im Büro).
	Die Meldung „gereinigt“ wird mit Zeit und Station am Behälter gespeichert; die Historie führt Frappe.
	"""
	s = _station(station)
	r = aufloesen(code)
	if r["typ"] != "behaelter":
		_fehler(_("{0} ist kein Behälter.").format(code))
	if r["behaelter_typ"] == "Gebinde":
		_fehler(
			_("{0} ist ein Gebinde vom Wareneingang, es wird nicht gereinigt und wiederverwendet.").format(
				code
			)
		)
	if r.get("charge"):
		_fehler(_("Behälter {0} enthält noch Charge {1}. Erst leeren.").format(code, r["charge"]))
	if r["status"] == "Gesperrt":
		_fehler(_("Behälter {0} ist gesperrt. Freigabe nur durch die QS.").format(code))
	t = frappe.get_doc("Produkttraeger", r["behaelter"])
	if cint(gereinigt):
		t.status = "Frei"
		t.gereinigt_am = now_datetime()
		t.gereinigt_station = s.name
	else:
		t.status = "Reinigung"
	t.save(ignore_permissions=True)
	return {"behaelter": t.name, "status": t.status, "gereinigt_am": t.gereinigt_am and str(t.gereinigt_am)}


@frappe.whitelist()
def freie_kisten(station: str) -> list[dict]:
	_station(station)
	return frappe.get_all(
		"Produkttraeger", {"typ": "Kiste lose Ware", "status": "Frei"}, ["code"], order_by="code", limit=200
	)


@frappe.whitelist()
def offene_paletten(station: str) -> list[dict]:
	"""Paletten, die noch nicht eingewickelt sind (Status Offen, mit Inhalt): zum Abschließen am Paletten-Terminal."""
	_station(station)
	ergebnis = []
	for p in frappe.get_all(
		"Palette", {"status": "Offen"}, ["name", "typ", "kunde"], order_by="creation desc", limit=100
	):
		i = paletten.info(p.name)
		if i.get("positionen"):
			ergebnis.append({"nve": p.name, "typ": p.typ, "kunde": p.kunde, "inhalt": i.get("kartons") or "",
			                 "lose": ", ".join(sorted({x["charge"] for x in i["positionen"]}))})  # fmt: skip
	return ergebnis


@frappe.whitelist()
@einmalig
def palette_versandbereit(station: str, palette: str) -> dict:
	"""Palette eingewickelt: abschließen, NVE-Etikett drucken, versandbereit im Lager."""
	_station(station)
	nve = paletten.finde(palette)
	if not nve:
		_fehler(_("{0} ist keine Palette.").format(palette))
	paletten.schliessen(nve)
	return paletten.info(nve)


@frappe.whitelist()
@einmalig
def linie_beenden(station: str, auftrag: str | None = None, abbrechen: int = 0) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	_darf(s, "palette_fertig")
	return linienbuchung.beenden(s.name, auftrag, bool(cint(abbrechen)))


@frappe.whitelist()
def packstation(station: str) -> dict:
	from keks_trace import linienbuchung

	s = _station(station)
	if not s.f_palette_fertig:  # Verpackungs-PC zeigt den Verpackungsauftrag auch
		_darf(s, "packstation")
	return linienbuchung.packstation(s.name)
