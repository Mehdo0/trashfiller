#!/usr/bin/env python3
"""Deuxieme passe sur les sites qui ont muré Chrome headless : camoufox.

Un WAF qui renvoie un mur anti-robot a un client HTTP ne le renvoie pas forcement a un
Firefox patche : c'est la meme page, chargee pour de vrai, avec le meme remplisseur
injecte. Toujours aucune soumission de formulaire.

Lancer : ~/stage42/.venv/bin/python tests/test_sites_camoufox.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent

IDENTITE = json.loads((RACINE / "tests/rapport_sites.json").read_text(encoding="utf-8"))[0] and {
    "prenom": "Camille", "nom": "Perrin", "pseudo": "camilleperrin42",
    "email": "camilleperrin42ab12@maxxspace.com", "mot_de_passe": "Trash!Aa1Bc2De3",
    "naissance": "1994-03-17", "naissance_fr": "17.03.1994",
    "jour": "17", "mois": "03", "annee": "1994",
    "adresse": "Rue des Tilleuls 12", "npa": "1020", "ville": "Renens",
    "pays": "Suisse", "telephone": "+41 79 123 45 67",
}

ATTENDU = {
    "email": r"mail|courriel",
    "mot_de_passe": r"pass|mdp|mot ?de ?passe",
    "mot_de_passe_confirm": r"pass|mdp|mot ?de ?passe",
    "prenom": r"prenom|first|given|fname|vorname",
    "nom": r"nom|last|surname|family|lname|nachname",
    "pseudo": r"user|pseudo|login|identifiant|nick|compte|handle|acct",
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
    ("GitHub", "https://github.com/signup"),
    ("Mastodon.social", "https://mastodon.social/auth/sign_up"),
    ("Vercel", "https://vercel.com/signup"),
    ("Netlify", "https://app.netlify.com/signup"),
    ("Reddit", "https://www.reddit.com/register/"),
    ("Ricardo.ch", "https://www.ricardo.ch/fr/register"),
]

def champs_visibles(page) -> int:
    """Champs remplissables, shadow DOM compris."""
    return page.evaluate("""() => {
        const tout = (racine = document, prof = 0) => {
            const t = [...racine.querySelectorAll('input, textarea, select')];
            if (prof > 6) return t;
            for (const e of racine.querySelectorAll('*')) if (e.shadowRoot) t.push(...tout(e.shadowRoot, prof + 1));
            return t;
        };
        return tout()
            .filter(e => !['hidden','submit','button','reset','file','image','range','color',
                            'checkbox','radio'].includes((e.type||'').toLowerCase()))
            .filter(e => !e.disabled && !e.readOnly)
            .filter(e => e.getClientRects().length > 0 || (e.type||'') === 'date')
            .length;
    }""")


def attendre_champs(page, secondes: int = 15) -> int:
    """Un formulaire d'application web arrive apres le chargement."""
    import time as _t
    fin = _t.time() + secondes
    n = 0
    while _t.time() < fin:
        n = champs_visibles(page)
        if n:
            return n
        page.wait_for_timeout(1500)
    return n


def ouvrir_formulaire(page) -> bool:
    """Comme pour la passe Chrome : sur GitHub, Vercel, Netlify ou Mastodon le formulaire
    n'existe qu'apres un clic (« Sign up », « Continuer », assistant en plusieurs etapes)."""
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
    dossier = RACINE / "tests/captures/camoufox"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom.lower().replace(' ', '-').replace('.', '-')}.png"
    try:
        page.screenshot(path=str(chemin))
        return str(chemin.relative_to(RACINE))
    except Exception:
        return ""


def tester(page, nom: str, url: str) -> dict:
    res = {"site": nom, "url": url, "moteur": "camoufox", "statut": "ok"}
    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception as e:
        res["statut"] = f"injoignable ({type(e).__name__})"
        return res

    res["titre"] = (page.title() or "")[:80]
    visibles = attendre_champs(page)
    if visibles == 0 and ouvrir_formulaire(page):
        visibles = attendre_champs(page, secondes=12)
        res["apres_clic"] = True
    res["champs_visibles"] = visibles
    if visibles == 0:
        titre = (page.title() or "").lower()
        mur = any(m in titre for m in ("just a moment", "un instant", "attention required", "access denied"))
        res["statut"] = "mur anti-robot" if mur else "page chargée, formulaire non rendu"
        res["capture"] = capturer(page, nom)
        return res

    try:
        page.evaluate("(i) => { globalThis.__trashfiller_identite = i; }", IDENTITE)
        rapport = page.evaluate((RACINE / "content.js").read_text(encoding="utf-8"))
    except Exception as e:
        res["statut"] = f"injection impossible ({type(e).__name__})"
        return res

    remplis = rapport.get("remplis", [])
    suspects = []
    for f in remplis:
        motif = ATTENDU.get(f["champ"])
        texte = f"{f.get('selecteur', '')} {f.get('signature', '')}".lower()
        if motif and len(texte) >= 8 and not re.search(motif, texte):
            suspects.append(f"{f['champ']} <- {f.get('selecteur')} ({f.get('signature', '')[:40]})")
    res.update({"remplis": len(remplis), "non_reconnus": len(rapport.get("non_reconnus", [])),
                "cases_a_cocher": rapport.get("cases_a_cocher", 0),
                "detail": remplis, "suspects": suspects})
    return res


def main() -> int:
    try:
        from camoufox.sync_api import Camoufox
    except Exception as e:
        print(f"camoufox indisponible : {e}")
        print("installer : uv venv /tmp/pw && uv pip install --python /tmp/pw/bin/python 'camoufox[geoip]' && python -m camoufox fetch")
        return 1

    resultats = []
    with Camoufox(headless=True, humanize=True, locale="fr-CH") as navigateur:
        page = navigateur.new_page()
        for nom, url in SITES:
            r = tester(page, nom, url)
            resultats.append(r)
            ligne = f"{r['site']:<16} {r['statut']:<38}"
            if r.get("champs_visibles"):
                ligne += f" {r['remplis']:>2}/{r['champs_visibles']:<3} remplis"
                if r.get("suspects"):
                    ligne += f"  SUSPECTS: {r['suspects']}"
            print(ligne, flush=True)

    ok = [r for r in resultats if r.get("champs_visibles")]
    tv = sum(r["champs_visibles"] for r in ok)
    tr = sum(r["remplis"] for r in ok)
    print(f"\npages exploitables : {len(ok)}/{len(resultats)}")
    if tv:
        print(f"taux de remplissage : {tr}/{tv} = {tr / tv * 100:.0f} %")
    for r in ok:
        for s in r.get("suspects", []):
            print(f"  suspect {r['site']} : {s}")
    (RACINE / "tests/rapport_sites_camoufox.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nrapport : tests/rapport_sites_camoufox.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
