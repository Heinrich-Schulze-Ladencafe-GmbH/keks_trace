"""Aufgeteilte Module: jede Funktion der Untermodule ist weiter unter dem alten Pfad erreichbar.

hooks.py, die API (/api/method/keks_trace.terminal.<funktion>) und andere Module rufen
keks_trace.<paket>.<funktion> auf. Die Untermodule sind nur die Ordnung darunter.

	bench --site <site> run-tests --module keks_trace.tests.test_pakete
"""

import importlib
import inspect
import os
import pkgutil

from frappe.tests import IntegrationTestCase

PAKETE = ("keks_trace.terminal", "keks_trace.palette")


class TestPakete(IntegrationTestCase):
	def test_paket_bietet_alle_funktionen(self):
		for name in PAKETE:
			paket = importlib.import_module(name)
			for info in pkgutil.iter_modules([os.path.dirname(paket.__file__)]):
				modul = importlib.import_module(f"{name}.{info.name}")
				for f_name, f in inspect.getmembers(modul, inspect.isfunction):
					if f.__module__ == modul.__name__:
						self.assertIs(getattr(paket, f_name, None), f, f"{modul.__name__}.{f_name}")
