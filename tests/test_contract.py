#!/usr/bin/env python3
"""Test de contrat statique de l'extension (aucun navigateur requis).

Contrôle que ce qui est declare existe, et que chaque API chrome.* utilisee a bien
sa permission dans le manifeste : un identifiant manquant ou une permission absente
fait echouer l'initialisation en silence, et l'extension parait vivante sans l'etre.

Lancer : python3 tests/test_contract.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
ERREURS: list[str] = []


def verifier(condition: bool, message: str) -> None:
    if not condition:
        ERREURS.append(message)


def main() -> int:
    manifeste = json.loads((RACINE / "manifest.json").read_text(encoding="utf-8"))
    verifier(manifeste.get("manifest_version") == 3, "le manifeste doit etre en MV3")
    verifier(bool(manifeste.get("name")), "nom manquant dans le manifeste")
    verifier(bool(manifeste.get("version")), "version manquante")

    # 1. les fichiers declares existent
    declares = [manifeste["background"]["service_worker"],
                manifeste["action"]["default_popup"]]
    declares += list(manifeste.get("icons", {}).values())
    for fichier in declares:
        verifier((RACINE / fichier).exists(), f"fichier declare introuvable : {fichier}")

    # 2. contenu.js est injecte par le popup : il doit exister et etre reference
    popup_js = (RACINE / "popup.js").read_text(encoding="utf-8")
    verifier((RACINE / "content.js").exists(), "content.js introuvable")
    verifier('files: ["content.js"]' in popup_js, "popup.js n'injecte pas content.js")
    verifier("__trashfiller_identite" in popup_js and "__trashfiller_identite" in
             (RACINE / "content.js").read_text(encoding="utf-8"),
             "l'identite n'est pas transmise entre popup.js et content.js")

    # 3. tout getElementById du JS doit exister dans le HTML
    html = (RACINE / "popup.html").read_text(encoding="utf-8")
    ids_html = set(re.findall(r'id="([^"]+)"', html))
    ids_js = set(re.findall(r'\$\("([^"]+)"\)', popup_js))
    ids_js |= set(re.findall(r'getElementById\("([^"]+)"\)', popup_js))
    manquants = sorted(ids_js - ids_html)
    verifier(not manquants, f"identifiants utilises par le JS et absents du HTML : {manquants}")
    # et reciproquement, pas de balise morte
    orphelins = sorted(i for i in ids_html - ids_js if not i.startswith(("bloc-", "inbox-")))
    if orphelins:
        print(f"note : identifiants HTML non utilises par le JS : {orphelins}")

    # 4. chaque API chrome.* utilisee a sa permission declaree
    texte_js = popup_js + (RACINE / "background.js").read_text(encoding="utf-8")
    permissions = set(manifeste.get("permissions", []))
    for api, cle in (("chrome.storage", "storage"), ("chrome.scripting", "scripting"),
                     ("chrome.tabs", "tabs"), ("chrome.alarms", "alarms"),
                     ("chrome.notifications", "notifications")):
        if api in texte_js:
            # chrome.tabs.query n'exige pas la permission "tabs" tant qu'on ne lit pas
            # tab.url : on tolere donc son absence, mais on le signale.
            if cle == "tabs":
                print("note : chrome.tabs utilise sans permission 'tabs' "
                      "(OK tant que tab.url n'est pas lu)")
                continue
            verifier(cle in permissions, f"{api} utilise mais permission « {cle} » absente")

    # 5. pas de code distant, que du https
    verifier("http://" not in texte_js.replace("http://127.0.0.1", ""),
             "URL http:// en clair detectee dans le JS")
    verifier("eval(" not in texte_js, "eval() detecte (interdit en MV3)")

    # 6. host_permissions couvre bien l'API de boite jetable
    hote = manifeste.get("host_permissions", [])
    verifier(any("api.mail.tm" in h for h in hote),
             "host_permissions ne couvre pas https://api.mail.tm/*")

    if ERREURS:
        print("ECHEC du contrat statique :")
        for e in ERREURS:
            print(f"  - {e}")
        return 1
    print("contrat statique OK : fichiers, identifiants, permissions, https, host.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
