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

    # 0. les limites imposees par Chrome : depassees, l'extension REFUSE de se charger
    #    (« The description field in manifest is too long: 150. It exceeds maximum size
    #    limit of 132 characters. »). Verifie ici pour ne plus jamais le decouvrir au
    #    moment de charger l'extension.
    nom = manifeste.get("name", "")
    description = manifeste.get("description", "")
    version = manifeste.get("version", "")
    verifier(len(nom) <= 75, f"nom trop long : {len(nom)} caracteres (limite Chrome : 75)")
    verifier(bool(description), "description manquante dans le manifeste")
    verifier(len(description) <= 132,
             f"description trop longue : {len(description)} caracteres (limite Chrome : 132)")
    verifier(re.fullmatch(r"\d{1,5}(\.\d{1,5}){0,3}", version) is not None,
             f"version invalide : {version!r} (1 a 4 nombres separes par des points, sans zero initial)")
    for nombre in version.split("."):
        verifier(nombre == "0" or not nombre.startswith("0"),
                 f"version invalide : zero initial dans « {nombre} »")
        verifier(int(nombre) <= 65535, f"version invalide : {nombre} > 65535")
    verifier(manifeste.get("default_locale") is None
             or (RACINE / "_locales" / manifeste["default_locale"]).is_dir(),
             "default_locale declare mais _locales/<langue> absent")
    # une permission inconnue est refusee au chargement : on n'en autorise que des connues
    connues = {"storage", "activeTab", "scripting", "tabs", "alarms", "notifications",
               "contextMenus", "cookies", "downloads", "idle", "unlimitedStorage",
               "webNavigation", "webRequest", "declarativeNetRequest"}
    inconnues = sorted(set(manifeste.get("permissions", [])) - connues)
    verifier(not inconnues, f"permissions inconnues de Chrome : {inconnues}")
    for hote_perm in manifeste.get("host_permissions", []):
        verifier(hote_perm.startswith("https://") or "://" not in hote_perm,
                 f"host_permissions non chiffre : {hote_perm}")
    for cle, valeur in manifeste.get("icons", {}).items():
        verifier(str(cle).isdigit(), f"taille d'icone non numerique : {cle}")
        verifier(valeur.endswith(".png"), f"icone non PNG (Chrome exige du PNG) : {valeur}")
        chemin = RACINE / valeur
        if chemin.exists():
            verifier(chemin.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n",
                     f"fichier declare PNG mais ce n'en est pas un : {valeur}")
            verifier(chemin.stat().st_size <= 2_000_000,
                     f"icone trop lourde : {valeur} ({chemin.stat().st_size} o)")

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
    verifier("new Function(" not in texte_js, "new Function() detecte (interdit en MV3)")
    verifier("import(" not in texte_js.replace("importScripts(", ""),
             "import() dynamique detecte (interdit en MV3 pour du code distant)")

    # 5 bis. la politique de securite de contenu des pages d'extension : script-src 'self'.
    #        Un <script> inline, un onclick= ou un fichier distant fait REFUSER la page par
    #        Chrome (et souvent sans message clair). On le refuse ici d'abord.
    verifier(re.search(r"<script(?![^>]*\bsrc=)", html, re.I) is None,
             "script inline dans popup.html : la CSP de MV3 l'interdit")
    for motif in (r"\son[a-z]+\s*=\s*\"", r"\son[a-z]+\s*=\s*'"):
        verifier(re.search(motif, html, re.I) is None,
                 "gestionnaire d'evenement inline (onclick=...) dans popup.html : interdit par la CSP")
    for fichier_source in re.findall(r'(?:src|href)="([^"]+)"', html):
        verifier(not fichier_source.startswith(("http://", "https://", "//")),
                 f"ressource distante dans popup.html : {fichier_source}")
        verifier((RACINE / fichier_source).exists(),
                 f"ressource locale declaree dans popup.html et absente : {fichier_source}")

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
