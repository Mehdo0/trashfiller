#!/usr/bin/env python3
"""Efficacite reelle : on injecte le remplisseur dans de vraies pages d'inscription.

Regle absolue : on ne soumet JAMAIS un formulaire. On charge la page (GET), on remplit
le DOM en local, on mesure. Rien ne part chez le site.

Deux mesures par site :
  - couverture : champs visibles / reconnus / remplis ;
  - justesse : chaque champ rempli est revalide par ses propres signaux (un champ
    classe « email » dont le name/placeholder/label ne parle pas de mail est suspect).

Lancer : ~/stage42/.venv/bin/python tests/test_sites_reels.py
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
from playwright.sync_api import sync_playwright

RACINE = pathlib.Path(__file__).resolve().parent.parent
CHROME = pathlib.Path.home() / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
PROFIL = "/tmp/tf-sites"
PORT = 9447

IDENTITE = {
    "prenom": "Camille", "nom": "Perrin", "pseudo": "camilleperrin42",
    "email": "camilleperrin42ab12@maxxspace.com", "mot_de_passe": "Trash!Aa1Bc2De3",
    "naissance": "1994-03-17", "naissance_fr": "17.03.1994",
    "jour": "17", "mois": "03", "annee": "1994",
    "adresse": "Rue des Tilleuls 12", "npa": "1020", "ville": "Renens",
    "pays": "Suisse", "telephone": "+41 79 123 45 67",
}

# Ce qu'un champ de ce role doit contenir dans ses propres signaux pour etre credible.
ATTENDU = {
    "email": r"mail|courriel",
    "mot_de_passe": r"pass|mdp|mot ?de ?passe",
    "mot_de_passe_confirm": r"pass|mdp|mot ?de ?passe",
    "prenom": r"prenom|first|given|fname|vorname",
    "nom": r"nom|last|surname|family|lname|nachname",
    "pseudo": r"user|pseudo|login|identifiant|nick|compte|handle",
    "telephone": r"tel|phone|mobile|gsm|portable",
    "adresse": r"adresse|address|rue|street|strasse",
    "npa": r"npa|postal|zip|plz|cp\b|code",
    "ville": r"ville|city|localite|town|ort",
    "pays": r"pays|country|land",
    "naissance": r"naiss|birth|dob|date",
    "annee": r"annee|year|yyyy|birth|naiss",
    "mois": r"mois|month|birth|naiss",
    "jour": r"jour|day|birth|naiss",
}

SITES = [
    ("GitLab", "https://gitlab.com/users/sign_up"),
    ("GitHub", "https://github.com/signup"),
    ("Mastodon.social", "https://mastodon.social/auth/sign_up"),
    ("Hacker News", "https://news.ycombinator.com/login"),
    ("Bandcamp", "https://bandcamp.com/signup"),
    ("Vercel", "https://vercel.com/signup"),
    ("Netlify", "https://app.netlify.com/signup"),
    ("Reddit", "https://www.reddit.com/register/"),
    ("Twitch", "https://www.twitch.tv/signup"),
    ("Ricardo.ch", "https://www.ricardo.ch/fr/register"),
]


def champs_visibles(page) -> int:
    """Compte les champs remplissables, shadow DOM compris (les formulaires modernes
    y vivent souvent, et document.querySelectorAll les rate)."""
    return page.evaluate("""() => {
        const tout = (racine = document, prof = 0) => {
            const t = [...racine.querySelectorAll('input, textarea, select')];
            if (prof > 6) return t;
            for (const e of racine.querySelectorAll('*')) if (e.shadowRoot) t.push(...tout(e.shadowRoot, prof + 1));
            return t;
        };
        return tout()
            .filter(e => !['hidden','submit','button','reset','file','image','range','color'].includes((e.type||'').toLowerCase()))
            .filter(e => !e.disabled && !e.readOnly)
            .filter(e => e.offsetParent !== null || (e.type||'') === 'date')
            .length;
    }""")


def ouvrir_formulaire(page) -> bool:
    """Sur GitHub, Vercel ou Netlify, le formulaire n'existe pas avant un clic sur
    « Sign up », « Continue with email », « Créer un compte »... On tente le clic
    avant de conclure qu'il n'y a rien a remplir."""
    import re
    motif = re.compile(r"(sign ?up|s'?inscrire|inscription|créer un compte|creer un compte|"
                       r"create (an )?account|continue with e-?mail|avec e-?mail|register|"
                       r"s'inscrire par e-?mail|continuer|suivant|next|continue|"
                       r"j'?accepte|accepter|i agree)", re.I)
    for sel in ("button", "a", '[role="button"]'):
        for el in page.query_selector_all(sel):
            try:
                texte = (el.inner_text() or "").strip()
                if texte and motif.search(texte) and el.is_visible():
                    el.click(timeout=5000)
                    page.wait_for_timeout(2500)
                    return True
            except Exception:
                continue
    return False


def capturer(page, nom: str) -> str:
    """Une capture de ce que la page montre vraiment : c'est la seule facon de
    distinguer « formulaire absent » de « formulaire derriere un interstitiel »."""
    dossier = RACINE / "tests/captures"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom.lower().replace(' ', '-').replace('.', '-')}.png"
    try:
        page.screenshot(path=str(chemin))
        return str(chemin.relative_to(RACINE))
    except Exception:
        return ""


def attendre_champs(page, secondes: int = 12) -> int:
    """Un formulaire d'application web arrive apres le chargement : on attend qu'il
    apparaisse au lieu de conclure trop vite qu'il n'y en a pas."""
    fin = time.time() + secondes
    n = 0
    while time.time() < fin:
        n = champs_visibles(page)
        if n:
            return n
        page.wait_for_timeout(1000)
    return n


def statut_page(page, visibles: int) -> str:
    """Dire la verite : un mur anti-robot et un formulaire non rendu ne se confondent pas."""
    titre = (page.title() or "").lower()
    if any(m in titre for m in ("just a moment", "un instant", "attention required", "access denied", "robot")):
        return "mur anti-robot"
    return "page chargée, aucun champ visible"


def tester(page, nom: str, url: str) -> dict:
    res = {"site": nom, "url": url, "statut": "ok"}
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
    except Exception as e:
        res["statut"] = f"injoignable ({type(e).__name__})"
        return res

    titre = page.title()[:70]
    visibles = attendre_champs(page)
    if visibles == 0:
        # le formulaire est peut-être derrière un clic (« Sign up », « Continue with email »)
        if ouvrir_formulaire(page):
            visibles = attendre_champs(page, secondes=10)
            res["apres_clic"] = True
    res.update({"titre": titre, "champs_visibles": visibles})
    if visibles == 0:
        res["statut"] = statut_page(page, visibles)
        res["capture"] = capturer(page, nom)
        return res

    try:
        page.evaluate("(i) => { globalThis.__trashfiller_identite = i; }", IDENTITE)
        rapport = page.evaluate((RACINE / "content.js").read_text(encoding="utf-8"))
    except Exception as e:
        res["statut"] = f"injection impossible ({type(e).__name__})"
        return res

    remplis = rapport.get("remplis", [])
    res.update({
        "remplis": len(remplis),
        "non_reconnus": len(rapport.get("non_reconnus", [])),
        "sans_valeur": rapport.get("sans_valeur", []),
        "detail": remplis,
        "bandeau_absent_sans_chrome": page.evaluate("() => !document.getElementById('__tf_bandeau')"),
    })

    import re
    suspects = []
    for f in remplis:
        motif = ATTENDU.get(f["champ"])
        texte = f"{f.get('selecteur', '')} {f.get('signature', '')}".lower()
        if motif and not re.search(motif, texte):
            suspects.append(f"{f['champ']} <- {f.get('selecteur')}")
    res["suspects"] = suspects
    return res


def main() -> int:
    subprocess.run(["rm", "-rf", PROFIL], capture_output=True)
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=str(CHROME),
                                args=["--no-sandbox", "--disable-gpu", "--enable-unsafe-swiftshader"])
        contexte = nav.new_context(locale="fr-CH", viewport={"width": 1280, "height": 900})
        page = contexte.new_page()
        resultats = []
        for nom, url in SITES:
            r = tester(page, nom, url)
            resultats.append(r)
            ligne = f"{r['site']:<16} {r['statut']:<42}"
            if r.get("champs_visibles"):
                ligne += f" {r['remplis']:>2}/{r['champs_visibles']:<3} remplis"
                if r.get("suspects"):
                    ligne += f"  SUSPECTS: {r['suspects']}"
            print(ligne, flush=True)
        nav.close()

    ok = [r for r in resultats if r.get("champs_visibles")]
    total_v = sum(r["champs_visibles"] for r in ok)
    total_r = sum(r["remplis"] for r in ok)
    print(f"\npages exploitables : {len(ok)}/{len(resultats)}")
    if total_v:
        print(f"taux de remplissage : {total_r}/{total_v} = {total_r / total_v * 100:.0f} %")
    suspects = [(r["site"], s) for r in ok for s in r.get("suspects", [])]
    print(f"classements suspects : {len(suspects)}")
    for site, s in suspects:
        print(f"  - {site} : {s}")

    (RACINE / "tests/rapport_sites.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nrapport complet : tests/rapport_sites.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
