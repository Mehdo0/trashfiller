// background.js — service worker de TrashFiller.
//
// Deux responsabilites, et rien d'autre :
//   1. parler a mail.tm pour fabriquer une boite jetable (le contenu du message ne
//      transite jamais par un serveur a nous : il n'y en a pas) ;
//   2. garder l'identite courante dans chrome.storage.local, effacable en un clic.
//
// Aucune donnee n'est envoyee ailleurs. Aucun code distant n'est charge (MV3 l'interdit
// de toute facon, et c'est tant mieux).

const API = "https://api.mail.tm";

// Domaines jetables : on ne code AUCUN domaine en dur. mail.tm n'en publie qu'un seul
// aujourd'hui (maxxspace.com), mais la liste change : on la lit a chaque creation.
async function domaines() {
  const r = await fetch(`${API}/domains?page=1`);
  if (!r.ok) throw new Error(`domaines: HTTP ${r.status}`);
  const d = await r.json();
  const membres = d["hydra:member"] || [];
  const actifs = membres.filter((x) => x.isActive && !x.isPrivate).map((x) => x.domain);
  if (!actifs.length) throw new Error("aucun domaine disponible");
  return actifs;
}

function motDePasse() {
  // 20 caracteres, melange : assez pour ne jamais etre reutilisable ailleurs.
  const lettres = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ";
  const chiffres = "23456789";
  const speciaux = "!@#$%&*?";
  const tout = lettres + chiffres + speciaux;
  const octets = crypto.getRandomValues(new Uint32Array(20));
  let mdp = "";
  for (let i = 0; i < 20; i++) mdp += tout[octets[i] % tout.length];
  // garantir au moins un de chaque categorie (formulaires tatillons)
  mdp = lettres[octets[0] % lettres.length] + chiffres[octets[1] % chiffres.length]
      + speciaux[octets[2] % speciaux.length] + mdp.slice(3);
  return mdp;
}

function identite() {
  const prenoms = ["Camille", "Jules", "Alex", "Sam", "Noa", "Charlie", "Lou", "Maxime", "Sacha", "Eliott"];
  const noms = ["Perrin", "Aubert", "Morel", "Girard", "Bonnet", "Lefevre", "Marchand", "Roussel"];
  const rues = ["Rue des Tilleuls", "Avenue du Lac", "Chemin des Vignes", "Rue du Simplon", "Route de Berne"];
  const villes = ["Renens", "Yverdon", "Vevey", "Nyon", "Morges", "Bulle"];
  const b = crypto.getRandomValues(new Uint32Array(8));
  const prenom = prenoms[b[0] % prenoms.length];
  const nom = noms[b[1] % noms.length];
  const annee = 1990 + (b[2] % 20);            // 1990-2009 : un adulte credible
  const mois = 1 + (b[3] % 12);
  const jour = 1 + (b[4] % 28);
  const p = (n) => String(n).padStart(2, "0");
  return {
    prenom, nom,
    pseudo: (prenom + nom + b[5] % 100).toLowerCase(),
    naissance: `${p(annee)}-${p(mois)}-${p(jour)}`,
    naissance_fr: `${p(jour)}.${p(mois)}.${annee}`,
    jour: p(jour), mois: p(mois), annee: String(annee),
    adresse: `${rues[b[6] % rues.length]} ${1 + (b[7] % 120)}`,
    npa: String(1000 + (b[0] % 2000)),
    ville: villes[b[1] % villes.length],
    pays: "Suisse",
    telephone: `+41 7${(b[2] % 9) + 1} ${100 + (b[3] % 800)} ${10 + (b[4] % 89)} ${10 + (b[5] % 89)}`,
  };
}

async function demander(url, options) {
  const r = await fetch(url, options);
  const texte = await r.text();
  if (r.status === 429) {
    throw new Error("mail.tm limite le rythme de création, réessaie dans une minute");
  }
  if (!r.ok) {
    let detail = texte.slice(0, 160);
    try { detail = JSON.parse(texte).detail || detail; } catch (e) { /* corps non JSON */ }
    throw new Error(`HTTP ${r.status} — ${detail}`);
  }
  return JSON.parse(texte);
}

async function nouvelIdentite() {
  const doms = await domaines();
  const domaine = doms[Math.floor(Math.random() * doms.length)];
  const id = identite();
  // mail.tm NORMALISE l'adresse : les points du nom d'utilisateur sont supprimes
  // (envoye « tf.a12 », stocke « tfa12 »). Creer avec une adresse a points puis
  // demander le jeton avec la meme chaine renvoie 401 « Invalid credentials » :
  // on ne garde donc que [a-z0-9] dans la partie locale.
  const suffixe = Array.from(crypto.getRandomValues(new Uint8Array(3)))
    .map((n) => n.toString(16).padStart(2, "0")).join("");
  const locale = `${id.pseudo}${suffixe}`.toLowerCase().replace(/[^a-z0-9]/g, "");
  const adresse = `${locale}@${domaine}`;
  const mdp = motDePasse();

  const compte = await demander(`${API}/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address: adresse, password: mdp }),
  });
  // l'adresse fait foi telle que le serveur l'a enregistree, pas celle qu'on a envoyee
  const adresseReelle = compte.address || adresse;

  const { token } = await demander(`${API}/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address: adresseReelle, password: mdp }),
  });

  const boite = {
    adresse: adresseReelle, mot_de_passe: mdp, token,
    cree_le: new Date().toISOString(),
    // l'identite (nom, adresse postale...) n'a rien a faire sur un serveur : elle reste ici
  };
  const profil = { ...id, email: adresseReelle, mot_de_passe: mdp };
  await chrome.storage.local.set({ boite, profil });
  return { boite: sansToken(boite), profil };
}

const sansToken = ({ token, ...reste }) => reste;

async function etat() {
  const { boite, profil } = await chrome.storage.local.get(["boite", "profil"]);
  return { boite: boite ? sansToken(boite) : null, profil: profil || null };
}

function liensEtCodes(texte) {
  // Un mail de validation contient soit un lien, soit un code : on remonte les deux.
  const liens = [...new Set((texte.match(/https?:\/\/[^\s"'<>)]+/g) || [])
    .filter((u) => !/mail\.tm|unsubscribe|desabonn|privacy|confidentialite/i.test(u)))];
  const codes = [...new Set((texte.match(/\b[A-Z0-9]{4,8}\b|\b\d{4,8}\b/g) || [])
    .filter((c) => /\d/.test(c)))];
  return { liens: liens.slice(0, 6), codes: codes.slice(0, 6) };
}

function texteDuMessage(m) {
  // mail.tm renvoie le corps en texte et/ou html, en tableau de chaines.
  const morceaux = [];
  for (const partie of m.html || []) {
    const html = String(partie);
    // Les liens vivent dans les ATTRIBUTS : on les recolte avant de retirer les
    // balises, sinon un mail HTML ne remonte aucun lien de validation
    // (bug verifie : le texte resultant perdait tous les href).
    for (const trouve of html.matchAll(/href\s*=\s*["']([^"']+)["']/gi)) {
      morceaux.push(trouve[1].replace(/&amp;/g, "&"));
    }
    morceaux.push(html.replace(/<[^>]+>/g, " "));
  }
  for (const partie of m.text || []) morceaux.push(String(partie));
  return morceaux.join("\n")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&")
    .replace(/\s+/g, " ").trim();
}

async function messages() {
  const { boite } = await chrome.storage.local.get("boite");
  if (!boite) return [];
  const r = await fetch(`${API}/messages?page=1`, {
    headers: { Authorization: `Bearer ${boite.token}` },
  });
  if (!r.ok) throw new Error(`messages: HTTP ${r.status}`);
  const d = await r.json();
  return (d["hydra:member"] || []).map((m) => {
    const texte = texteDuMessage(m);
    return {
      id: m.id, de: m.from && m.from.address, sujet: m.subject,
      recu: m.createdAt, texte: texte.slice(0, 4000), ...liensEtCodes(texte),
    };
  });
}

async function effacer() {
  await chrome.storage.local.clear();
  return { ok: true };
}

// Le popup parle au worker par messages : c'est le seul point d'entree.
chrome.runtime.onMessage.addListener((msg, _exp, repondre) => {
  const taches = {
    creer: nouvelIdentite,
    etat,
    messages,
    effacer,
  };
  const tache = taches[msg && msg.type];
  if (!tache) return false;
  tache()
    .then((data) => repondre({ ok: true, data }))
    .catch((e) => repondre({ ok: false, erreur: String(e.message || e) }));
  return true; // reponse asynchrone
});

// Exports utilises par tests/test_parsing.mjs (Node) : Chrome ignore les exports
// d'un service worker de type module, on peut donc s'en servir pour tester.
export { liensEtCodes, texteDuMessage, motDePasse, identite };
