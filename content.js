// content.js — remplit le formulaire de la page courante avec l'identite jetable.
//
// Injecte a la demande par le popup (chrome.scripting.executeScript), jamais declare
// en content_script permanent : l'extension ne tourne pas en fond sur tes pages.
//
// Deux precautions qui font la difference entre "ca marche" et "le site dit champ vide" :
//   1. on ecrit par le setter natif de HTMLInputElement, puis on emet input/change/blur
//      (React, Vue et Angular n'observent pas la propriete, ils ecoutent les evenements) ;
//   2. on ne touche ni aux champs desactives, ni aux champs caches, ni aux cases a cocher
//      (accepter des CGU a ta place, ce n'est pas a un outil de le faire).

(() => {
  const DEJA = "__trashfiller_pose";
  if (window[DEJA]) window[DEJA]();

  function norm(s) {
    return String(s || "").toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
  }

  // Signature d'un champ. Deux niveaux, et l'ordre compte :
  //   - fort  : name, id, placeholder, aria-label, autocomplete, type, label[for]
  //   - faible : le texte du bloc parent (utile pour les formulaires sans name,
  //     dangereux ailleurs : il contient les libelles des AUTRES champs, ce qui
  //     faisait passer un <select> « Pays » pour « Ville »).
  function signature(el, faible = false) {
    const morceaux = [
      el.name, el.id, el.placeholder, el.getAttribute("aria-label"),
      el.getAttribute("autocomplete"), el.type,
    ];
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) morceaux.push(l.textContent);
    }
    if (faible) {
      const parent = el.closest("label, .field, .form-group, .input-group, div");
      if (parent) morceaux.push(parent.textContent.slice(0, 120));
    }
    return norm(morceaux.filter(Boolean).join(" | "));
  }

  const REGLES = [
    ["email", /(^|[^a-z])(e-?mail|mail|adresse ?mail|courriel)/],
    ["mot_de_passe_confirm", /(confirm|verif|repeat|encore|again|2|retype|repeter).{0,12}(mot|pass|mdp)|(mot|pass|mdp).{0,12}(confirm|2|bis)/],
    ["mot_de_passe", /(mot ?de ?passe|password|passwd|mdp|pass\b)/],
    ["telephone", /(telephone|phone|mobile|portable|tel\b|gsm)/],
    // Les groupes de dates (Rails `date_of_birth(3i)`/`(2i)`/`(1i)`, Django, formulaires
    // maison) doivent passer AVANT la regle « naissance » : sinon chaque partie recoit la
    // date complete au lieu de son jour, son mois, son annee.
    ["jour", /\(3i\)|\[day\]|\bday\b|\bjour\b/],
    ["mois", /\(2i\)|\[month\]|\bmonth\b|\bmois\b/],
    ["annee", /\(1i\)|\[year\]|\byear\b|\bannee\b|\byyyy\b/],
    ["naissance", /(naissance|birth|birthday|dob|date de nais)/],
    ["npa", /(npa|code ?postal|postal|zip|plz|cp\b)/],
    ["ville", /(ville|city|localite|lieu de residence|town)/],
    ["adresse", /(adresse|address|rue|street|strasse|voie)/],
    ["pays", /(pays|country|land)/],
    ["pseudo", /(pseudo|username|user ?name|login|identifiant|nick|compte|handle|acct)/],
    ["prenom", /(prenom|first ?name|given|vorname|fname)/],
    ["nom", /(^|[^a-z])(nom|last ?name|surname|family|nachname|lname)/],
    ["societe", /(societe|company|entreprise|organisation|organization|firma)/],
    ["site", /(site|website|url|web\b)/],
  ];

  function champ(el) {
    // d'abord les signaux forts sur toutes les regles, ensuite les faibles
    for (const faible of [false, true]) {
      const sig = signature(el, faible);
      for (const [nom, motif] of REGLES) {
        if (motif.test(sig)) return nom;
      }
    }
    if (el.type === "email") return "email";
    if (el.type === "tel") return "telephone";
    return null;
  }

  function ecrire(el, valeur) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLInputElement ? HTMLInputElement.prototype : null;
    if (!proto) {
      // ni input ni textarea : on ecrit la propriete et on previent, sans setter natif
      el.value = valeur;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(el, valeur);
    for (const type of ["input", "change", "blur", "keyup"]) {
      el.dispatchEvent(new Event(type, { bubbles: true }));
    }
  }

  // Un champ cache a offsetParent === null DANS UN SHADOW ROOT (le spec le dit) :
  // tester offsetParent rate donc tous les formulaires en composants web.
  // getClientRects() est vrai des qu'un element est rendu, shadow DOM compris.
  function visible(el) {
    if ((el.type || "").toLowerCase() === "hidden") return false;
    return el.getClientRects().length > 0;
  }

  // Les formulaires modernes vivent souvent dans un shadow DOM (composants web) :
  // document.querySelectorAll les rate completement. On collecte donc recursivement.
  function collecter(racine = document, profondeur = 0) {
    const trouves = [...racine.querySelectorAll("input, textarea, select")];
    if (profondeur > 6) return trouves;
    for (const el of racine.querySelectorAll("*")) {
      if (el.shadowRoot) trouves.push(...collecter(el.shadowRoot, profondeur + 1));
    }
    return trouves;
  }

  function remplir(identite) {
    // Certains champs n'ont pas de valeur propre dans l'identite : ils reutilisent
    // une autre (le champ « confirmer le mot de passe » porte le meme secret).
    const ALIAS = {
      mot_de_passe_confirm: "mot_de_passe",
      confirmation: "mot_de_passe",
      mot_de_passe_2: "mot_de_passe",
    };
    const rapport = { remplis: [], ignores: [], non_reconnus: [], sans_valeur: [] };
    const champs = collecter();
    for (const el of champs) {
      const type = (el.type || "text").toLowerCase();
      if (el.tagName === "SELECT") continue;                          // traite plus bas
      if (["hidden", "submit", "button", "reset", "file", "image", "range", "color"].includes(type)) continue;
      if (el.disabled || el.readOnly) { rapport.ignores.push(el.name || el.id || type); continue; }
      if (el.type === "checkbox" || el.type === "radio") continue;   // jamais touche
      if (!visible(el)) continue;                                     // champ non rendu

      const c = champ(el);
      if (!c) {
        if (!el.value) rapport.non_reconnus.push({ name: el.name || el.id, placeholder: el.placeholder || "" });
        continue;
      }
      const valeur = identite[ALIAS[c] || c];
      if (valeur === undefined) {
        rapport.sans_valeur.push(c);
        continue;
      }
      ecrire(el, valeur);
      rapport.remplis.push({
        champ: c,
        selecteur: el.name || el.id || el.placeholder || el.type,
        signature: signature(el, false),          // pour auditer la justesse du classement
        valeur_ecrite: String(valeur).slice(0, 40),
      });
    }

    // les listes deroulantes : pays, et les selects qui ressemblent a un jour/mois/annee
    for (const el of collecter().filter((e) => e.tagName === "SELECT")) {
      const c = champ(el);
      const cible = c === "pays" ? /suisse|switzerland|swiss|ch\b/i
        : c === "jour" ? new RegExp(`^0?${String(Number(identite.jour))}$`)
        : c === "mois" ? new RegExp(`^0?${String(Number(identite.mois))}$`)
        : c === "annee" ? new RegExp(`^${identite.annee}$`) : null;
      if (!cible) continue;
      const option = [...el.options].find((o) => cible.test(o.textContent.trim()) || cible.test(o.value));
      if (option) {
        el.value = option.value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
        rapport.remplis.push({ champ: c, selecteur: "select" });
      }
    }

    const cases = collecter().filter((c) => c.type === "checkbox" && visible(c)).length;
    rapport.cases_a_cocher = cases;
    return rapport;
  }

  // ---------------------------------------------------------------- bandeau
  // Le mail de validation n'arrive pas pendant qu'on regarde le popup : on pose donc
  // un bandeau sur la page, qui interroge la boite toutes les 5 s et affiche le lien
  // des qu'il tombe. Sans l'API chrome (test hors extension), on ne fait rien.
  const MESSAGERIE = (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage)
    ? (msg) => new Promise((r) => chrome.runtime.sendMessage(msg, (rep) => r(rep)))
    : null;

  function bandeau(identite) {
    // le bandeau n'a de sens que dans la page principale : dans une iframe de 300 px
    // il serait illisible, et il y en aurait un par cadre
    if (window.top !== window.self) return;
    if (!MESSAGERIE || document.getElementById("__tf_bandeau")) return;
    const boite = document.createElement("div");
    boite.id = "__tf_bandeau";
    boite.style.cssText = [
      "position:fixed", "z-index:2147483647", "right:16px", "bottom:16px",
      "width:320px", "padding:12px 14px", "border-radius:10px",
      "background:#12141a", "color:#e7e9ee", "border:1px solid #2b2f3c",
      "box-shadow:0 8px 28px rgba(0,0,0,.4)",
      "font:13px/1.45 system-ui,-apple-system,Segoe UI,sans-serif",
    ].join(";");

    const titre = document.createElement("div");
    titre.textContent = "TrashFiller — en attente du mail de validation";
    titre.style.cssText = "font-weight:600;margin-bottom:4px";
    const adresse = document.createElement("div");
    adresse.textContent = identite.email;
    adresse.style.cssText = "font-family:ui-monospace,monospace;font-size:12px;color:#9aa1b1;word-break:break-all;margin-bottom:6px";
    const zone = document.createElement("div");
    const fermer = document.createElement("button");
    fermer.textContent = "fermer";
    fermer.style.cssText = "margin-top:8px;font-size:11px;padding:2px 6px;background:#1b1e27;color:#9aa1b1;border:1px solid #2b2f3c;border-radius:5px;cursor:pointer";

    boite.append(titre, adresse, zone, fermer);
    document.body.appendChild(boite);

    let arret = false;
    const stop = () => { arret = true; clearInterval(boucle); setTimeout(() => boite.remove(), 4000); };
    fermer.addEventListener("click", () => { arret = true; clearInterval(boucle); boite.remove(); });

    async function verifier() {
      if (arret) return;
      try {
        const rep = await MESSAGERIE({ type: "messages" });
        const msgs = (rep && rep.ok && rep.data) || [];
        const liens = msgs.flatMap((m) => m.liens || []);
        const codes = msgs.flatMap((m) => m.codes || []);
        if (!liens.length && !codes.length) return;
        zone.textContent = "";
        const dit = document.createElement("div");
        dit.textContent = `${msgs.length} message(s) reçu(s) :`;
        dit.style.cssText = "font-size:12px;color:#4ade80;margin-bottom:4px";
        zone.append(dit);
        for (const lien of liens.slice(0, 3)) {
          const a = document.createElement("a");
          a.href = lien;
          a.target = "_blank";
          a.rel = "noopener";
          a.textContent = "Ouvrir le lien de validation";
          a.style.cssText = "display:block;margin:4px 0;padding:6px 8px;background:#16351f;color:#b9f5cd;border-radius:6px;text-decoration:none;font-size:12px";
          zone.append(a);
        }
        for (const code of codes.slice(0, 3)) {
          const b = document.createElement("button");
          b.textContent = `copier le code ${code}`;
          b.style.cssText = "margin:3px 4px 0 0;font-family:ui-monospace,monospace;font-size:12px;padding:3px 7px;background:#16351f;color:#b9f5cd;border:1px solid #245c36;border-radius:5px;cursor:pointer";
          b.addEventListener("click", () => navigator.clipboard.writeText(code).then(() => { b.textContent = "copié"; }));
          zone.append(b);
        }
        arret = true;
        clearInterval(boucle);
      } catch (e) { /* bandeau sans consequence sur le remplissage */ }
    }

    const boucle = setInterval(verifier, 5000);
    verifier();
    setTimeout(stop, 10 * 60 * 1000);   // on n'interroge pas la boite indefiniment
  }

  window[DEJA] = () => {};
  const rapport = remplir(globalThis.__trashfiller_identite || {});
  if (rapport && rapport.remplis.length) bandeau(globalThis.__trashfiller_identite || {});
  return rapport;
})();
