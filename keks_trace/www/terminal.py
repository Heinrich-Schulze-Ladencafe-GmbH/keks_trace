import hashlib
import json
import os

import frappe
from frappe.sessions import get_csrf_token

no_cache = 1

JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "js")
URL = "/assets/keks_trace/js/terminal/"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/terminal"
		raise frappe.Redirect
	context.title = "Keks Trace Terminal"
	context.nutzer = frappe.session.user
	context.kt_csrf = get_csrf_token()
	context.kt_version, context.kt_importmap = skripte()


def skripte() -> tuple[str, str]:
	"""Version und Import-Map der Terminal-Skripte (ES-Module unter public/js/terminal/).

	nginx liefert /assets mit langer Cache-Zeit aus. Die Version ist ein Hash über den Inhalt aller Skripte;
	die Import-Map hängt sie an jedes Modul, auch an die, die main.js selbst nachlädt. Nach einem Update
	(git pull) holt der Browser so die neuen Dateien, ohne „bench build“ und ohne Cache leeren.
	"""
	ordner = os.path.join(JS, "terminal")
	module = sorted(f for f in os.listdir(ordner) if f.endswith(".js"))
	h = hashlib.sha1()
	for pfad in [os.path.join(ordner, f) for f in module] + [os.path.join(JS, "akte_ansicht.js")]:
		with open(pfad, "rb") as d:
			h.update(d.read())
	version = h.hexdigest()[:12]
	return version, json.dumps({"imports": {URL + f: f"{URL}{f}?v={version}" for f in module}})
