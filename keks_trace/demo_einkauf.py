"""Demo Einkauf: Zucker-Kontrakt (Rahmenauftrag) mit zwei Abrufen.

    bench --site keks.localhost execute keks_trace.demo_einkauf.anlegen

Börsenware wird per Kontrakt gekauft: Menge und Preis fest, abgerufen wird nach Bedarf. In ERPNext ist das
ein Rahmenauftrag (Blanket Order, Typ Einkauf); jede Bestellung zeigt auf ihn, ERPNext zählt mit, wie viel
schon abgerufen ist. Alle Zahlen sind Demo-Werte.
"""

import frappe
from frappe.utils import add_days, add_months, nowdate

LIEFERANT = "KT Demo Mühle"
KONTRAKT = {"artikel": "KT-ZUCKER", "menge": 50000, "preis": 0.62}  # 50 t zu 0,62 €/kg
ABRUFE = [(12000, -10, 3), (12000, 0, 14)]  # (kg, Bestelltag relativ zu heute, Liefertag)


def _firma():
	return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})


def kontrakt(firma: str) -> str:
	vorhanden = frappe.db.get_value(
		"Blanket Order",
		{"supplier": LIEFERANT, "docstatus": 1, "order_no": "DEMO-ZUCKER", "to_date": [">=", nowdate()]},
	)
	if vorhanden:
		return vorhanden
	bo = frappe.get_doc(
		{
			"doctype": "Blanket Order",
			"blanket_order_type": "Purchasing",
			"supplier": LIEFERANT,
			"company": firma,
			"from_date": add_days(nowdate(), -30),
			"to_date": add_months(nowdate(), 6),
			"order_no": "DEMO-ZUCKER",
			"order_date": add_days(nowdate(), -30),
			"items": [
				{"item_code": KONTRAKT["artikel"], "qty": KONTRAKT["menge"], "rate": KONTRAKT["preis"]}
			],
		}
	)
	bo.insert()
	bo.submit()
	return bo.name


def abrufen(firma: str, bo: str, menge: float, bestellt_am, liefern_am) -> str:
	lager = frappe.db.get_value(
		"Silo", {"artikel": KONTRAKT["artikel"], "aktiv": 1}, "warehouse"
	) or frappe.db.get_value("Warehouse", {"company": firma, "is_group": 0, "warehouse_name": "Stores"})
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": LIEFERANT,
			"company": firma,
			"transaction_date": bestellt_am,
			"schedule_date": liefern_am,
			"items": [
				{
					"item_code": KONTRAKT["artikel"],
					"qty": menge,
					"rate": KONTRAKT["preis"],
					"schedule_date": liefern_am,
					"warehouse": lager,
					"against_blanket_order": 1,
					"blanket_order": bo,
					"blanket_order_rate": KONTRAKT["preis"],
				}
			],
		}
	)
	po.insert()
	po.submit()
	return po.name


@frappe.whitelist()
def anlegen() -> dict:
	from keks_trace import demo

	demo.stammdaten()
	firma = _firma()
	bo = kontrakt(firma)
	abrufe = frappe.get_all("Purchase Order Item", {"blanket_order": bo, "docstatus": 1}, pluck="parent")
	if not abrufe:
		for menge, bestellt, liefern in ABRUFE:
			abrufe.append(
				abrufen(
					firma, bo, menge, add_days(nowdate(), bestellt), add_days(nowdate(), bestellt + liefern)
				)
			)
	frappe.db.commit()
	offen = frappe.db.get_value("Blanket Order Item", {"parent": bo}, ["qty", "ordered_qty"], as_dict=True)

	def kg(x):
		return f"{x:,.0f}".replace(",", ".")

	print(
		f"Kontrakt {bo}: {kg(offen.qty)} kg Zucker, abgerufen {kg(offen.ordered_qty)} kg, Bestellungen {', '.join(abrufe)}"
	)
	return {"kontrakt": bo, "abrufe": abrufe, "menge": offen.qty, "abgerufen": offen.ordered_qty}
