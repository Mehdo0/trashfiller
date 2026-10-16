#!/usr/bin/env python3
"""Test de bout en bout de TrashFiller dans un vrai Chrome.

Le navigateur est le seul juge : on charge l'extension pour de vrai, on remplit un
vrai formulaire, et on cree une vraie boite jetable via le popup.

Lancer (playwright est dans le venv de stage42) :
  ~/stage42/.venv/bin/python tests/test_autofill.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

RACINE = pathlib.Path(__file__).resolve().parent.parent
CHROME = pathlib.Path.home() / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
PORT = 9443
PROFIL = "/tmp/tf-profile-e2e"

IDENTITE = {
    "prenom": "Camille", "nom": "Perrin", "pseudo": "camilleperrin42",
    "email": "camille.perrin.abc123@maxxspace.com", "mot_de_passe": "Trash!Aa1Bc2De3",
    "naissance": "1994-03-17", "naissance_fr": "17.03.1994",
    "jour": "17", "mois": "03", "annee": "1994",
    "adresse": "Rue des Tilleuls 12", "npa": "1020", "ville": "Renens",
    "pays": "Suisse", "telephone": "+41 79 123 45 67",
}

echecs: list[str] = []


def attendre(condition, message: str, timeout: float = 30.0):
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            if condition():
                return
        except Exception:
            pass
        time.sleep(0.4)
    echecs.append(message)
    raise SystemExit(f"ECHEC : {message}")


def cdp(chemin: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{chemin}", timeout=5) as r:
        return json.load(r)


def identifiant_attendu() -> str:
    """Chrome calcule l'identifiant d'une extension non empaquetee a partir du CHEMIN
    ABSOLU : SHA-256 du chemin, 16 premiers octets, projetes sur a-p.

    On ne peut PAS le lire dans /json/list : un service worker MV3 est tue apres ~30 s
    d'inactivite, donc sa cible n'existe plus quand le test demarre. Et chercher la
    premiere cible qui finit par « background.js » tombe sur une extension integree de
    Chrome (il y en a deux) : deux pieges verifies.
    """
    import hashlib
    h = hashlib.sha256(str(RACINE).encode()).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in h)


def worker_actif(eid: str) -> bool:
    return any(c.get("type") == "service_worker" and (c.get("url") or "").startswith(f"chrome-extension://{eid}/")
               for c in cdp("/json/list"))


def main() -> int:
    subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], capture_output=True)
    subprocess.run(["rm", "-rf", PROFIL], capture_output=True)
    chrome = subprocess.Popen([
        str(CHROME), "--headless=new", "--no-sandbox", "--disable-gpu",
        "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFIL}",
        f"--load-extension={RACINE}", f"--disable-extensions-except={RACINE}",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        attendre(lambda: cdp("/json/version"), "Chrome n'a pas ouvert CDP")
        eid = identifiant_attendu()
        print(f"identifiant attendu de l'extension : {eid}")

        with sync_playwright() as p:
            navigateur = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
            contexte = navigateur.contexts[0]

            # ---- 1. remplissage d'un vrai formulaire -------------------------------
            page = contexte.new_page()
            page.goto((RACINE / "tests/page_form.html").as_uri())
            page.evaluate("(i) => { globalThis.__trashfiller_identite = i; }", IDENTITE)
            rapport = page.evaluate((RACINE / "content.js").read_text(encoding="utf-8"))
            print(f"\nrapport du remplissage : {len(rapport['remplis'])} champ(s) rempli(s), "
                  f"{len(rapport['non_reconnus'])} non reconnu(s), "
                  f"{rapport['cases_a_cocher']} case(s) a cocher")

            attendus = {
                "#email": IDENTITE["email"], "#mdp": IDENTITE["mot_de_passe"],
                "#mdp2": IDENTITE["mot_de_passe"], "#prenom": IDENTITE["prenom"],
                "#nom": IDENTITE["nom"], "#pseudo": IDENTITE["pseudo"],
                "#rue": IDENTITE["adresse"], "#npa": IDENTITE["npa"],
                "#ville": IDENTITE["ville"], "#tel": IDENTITE["telephone"],
                "#naissance": IDENTITE["naissance"],
            }
            for selecteur, attendu in attendus.items():
                obtenu = page.input_value(selecteur)
                if obtenu != attendu:
                    echecs.append(f"{selecteur} : attendu {attendu!r}, obtenu {obtenu!r}")
                else:
                    print(f"  ok {selecteur:<12} = {obtenu}")

            pays = page.input_value("#pays")
            if pays != "CH":
                echecs.append(f"#pays : attendu 'CH', obtenu {pays!r}")
            else:
                print("  ok #pays        = CH (Suisse)")

            # ce qui ne doit PAS etre touche
            for selecteur, nom in (("#cgu", "case CGU"), ("#news", "case newsletter")):
                if page.is_checked(selecteur):
                    echecs.append(f"{nom} cochee alors qu'un outil ne doit pas accepter des CGU")
            for selecteur in ("#desactive", "#poison"):
                if page.input_value(selecteur):
                    echecs.append(f"{selecteur} rempli alors qu'il est desactive ou invisible")
            if page.input_value('input[name="csrf_token"]') != "jeton-initial":
                echecs.append("le jeton cache du formulaire a ete ecrase")
            print("  ok cases a cocher, champs desactives/invisibles et jeton cache : intacts")

            evts = page.evaluate("window.__evts")
            if not (evts["input"] and evts["change"] and evts["blur"]):
                echecs.append(f"evenements manquants : {evts}")
            else:
                print(f"  ok evenements  = {evts} (React/Vue les ecoutent, pas value)")
            page.close()

            # ---- 2. le popup cree une vraie boite jetable --------------------------
            popup = contexte.new_page()
            popup.goto(f"chrome-extension://{eid}/popup.html")
            popup.wait_for_selector("#btn-generer")
            # preuve que l'extension est bien chargee : le popup a reveille le worker
            attendre(lambda: worker_actif(eid), "le service worker de l'extension n'a pas demarre")
            print("service worker de l'extension demarre (manifeste accepte)")
            popup.click("#btn-generer")
            # mail.tm limite le rythme de creation : quand on a enchaine les tests, la
            # boite n'est pas creee tout de suite. On attend, et on le DIT au lieu de
            # faire echouer le test pour une raison exterieure.
            quota = False
            try:
                popup.wait_for_function(
                    "() => document.getElementById('id-email').textContent.includes('@')", timeout=90000)
            except Exception:
                etat = popup.text_content("#statut") or ""
                if "rythme" in etat or "429" in etat:
                    quota = True
                    print(f"\nquota mail.tm atteint — creation non verifiee cette fois : « {etat.strip()} »")
                else:
                    raise
            if quota:
                print("  (le reste du test continue : remplissage reel deja verifie)")
                popup.close()
                print()
                if echecs:
                    print(f"ECHECS ({len(echecs)}) :")
                    for e in echecs:
                        print(f"  - {e}")
                    return 1
                print("bout en bout OK (remplissage reel) — creation de boite non verifiee (quota)")
                return 0
            adresse = popup.text_content("#id-email").strip()
            print(f"\nboite jetable creee par le popup : {adresse}")

            domaines = json.loads(urllib.request.urlopen("https://api.mail.tm/domains?page=1", timeout=20).read())
            valides = [d["domain"] for d in domaines["hydra:member"] if d["isActive"]]
            if adresse.split("@")[1] not in valides:
                echecs.append(f"domaine {adresse.split('@')[1]} absent de la liste mail.tm {valides}")
            else:
                print(f"  ok domaine {adresse.split('@')[1]} publie par mail.tm")

            stocke = popup.evaluate("() => chrome.storage.local.get(['boite','profil'])")
            if not (stocke.get("boite") and stocke["boite"].get("adresse") == adresse):
                echecs.append(f"la boite n'est pas dans chrome.storage.local : {list(stocke)}")
            else:
                print("  ok identite conservee dans chrome.storage.local (et nulle part ailleurs)")

            inbox = popup.text_content("#inbox-vide")
            print(f"  boite vide au depart : {inbox.strip()[:60]}")

            # ---- 3. le chemin d'erreur du bouton, sans casser l'interface ----------
            # Le popup est ici ouvert dans un ONGLET : l'injection doit donc echouer
            # proprement (page chrome-extension://) et l'afficher, pas lever en silence.
            popup.click("#btn-remplir")
            popup.wait_for_timeout(1500)
            etat = popup.text_content("#statut") or ""
            if "interdite" in etat or "échec" in etat.lower() or "echec" in etat.lower():
                print(f"  ok chemin d'erreur : « {etat.strip()} »")
            else:
                echecs.append(f"le bouton Remplir ne signale pas l'echec d'injection (statut : {etat!r})")
            popup.close()

        print()
        if echecs:
            print(f"ECHECS ({len(echecs)}) :")
            for e in echecs:
                print(f"  - {e}")
            return 1
        print("bout en bout OK : remplissage reel + boite jetable reelle.")
        return 0
    finally:
        chrome.terminate()


if __name__ == "__main__":
    sys.exit(main())
