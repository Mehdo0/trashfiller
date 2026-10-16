// popup.js — l'interface : une identite, un bouton qui remplit la page, une boite qui
// remonte le lien de validation. Le popup ne fait rien tout seul : chaque action est
// un clic. Il ne parle au reseau que via le service worker (background.js).

const $ = (id) => document.getElementById(id);
const STATUT = $("statut");
let profil = null;
let minuteur = null;
let mdpVisible = false;

function dire(texte, couleur) {
  STATUT.textContent = texte;
  STATUT.style.color = couleur || "#9aa1b1";
}

function appeler(type) {
  return new Promise((resoudre, rejeter) => {
    chrome.runtime.sendMessage({ type }, (rep) => {
      if (chrome.runtime.lastError) return rejeter(new Error(chrome.runtime.lastError.message));
      if (!rep) return rejeter(new Error("pas de réponse du worker"));
      if (!rep.ok) return rejeter(new Error(rep.erreur));
      resoudre(rep.data);
    });
  });
}

function afficher(p) {
  profil = p;
  $("bloc-vide").hidden = !!p;
  $("identite").hidden = !p;
  if (!p) return;
  $("id-email").textContent = p.email;
  $("id-mdp").textContent = mdpVisible ? p.mot_de_passe : "•".repeat(12);
  $("id-nom-complet").textContent = `${p.prenom} ${p.nom}`;
  $("id-pseudo").textContent = p.pseudo;
  $("id-naissance").textContent = p.naissance_fr;
  $("id-adresse").textContent = p.adresse;
  $("id-npa-ville").textContent = `${p.npa} ${p.ville}`;
  $("id-telephone").textContent = p.telephone;
  $("pied-boite").textContent = `Boîte : ${p.email}`;
}

async function chargerBoite() {
  const { boite } = await appeler("etat");
  if (boite && boite.cree_le) {
    const age = Math.round((Date.now() - new Date(boite.cree_le)) / 60000);
    dire(`boîte active depuis ${age} min`);
  }
  await afficherMessages();
}

async function afficherMessages() {
  try {
    const msgs = await appeler("messages");
    const zone = $("messages");
    zone.innerHTML = "";
    $("inbox-vide").hidden = msgs.length > 0;
    for (const m of msgs) {
      const bloc = document.createElement("div");
      bloc.className = "message";
      const de = document.createElement("div");
      de.className = "de";
      de.textContent = `${m.de || "?"} · ${new Date(m.recu).toLocaleString("fr-CH")}`;
      const sujet = document.createElement("div");
      sujet.className = "sujet";
      sujet.textContent = m.sujet || "(sans objet)";
      bloc.append(de, sujet);
      const puces = document.createElement("div");
      puces.className = "puces";
      for (const code of m.codes) {
        const b = document.createElement("span");
        b.className = "puce";
        b.textContent = code;
        b.title = "cliquer pour copier";
        b.addEventListener("click", () => navigator.clipboard.writeText(code).then(() => dire(`code ${code} copié`)));
        puces.append(b);
      }
      for (const lien of m.liens) {
        const b = document.createElement("button");
        b.className = "copie";
        b.textContent = "ouvrir le lien de validation";
        b.addEventListener("click", () => chrome.tabs.create({ url: lien }));
        puces.append(b);
      }
      bloc.append(puces);
      zone.append(bloc);
    }
    if (msgs.length) dire(`${msgs.length} message(s) reçu(s)`, "#4ade80");
  } catch (e) {
    dire(`boîte : ${e.message}`, "#f87171");
  }
}

// ------------------------------------------------------------------ actions
$("btn-generer").addEventListener("click", async () => {
  dire("création de la boîte…");
  try {
    const { profil: p } = await appeler("creer");
    afficher(p);
    await chargerBoite();
  } catch (e) {
    dire(`échec : ${e.message}`, "#f87171");
  }
});

$("btn-nouvelle").addEventListener("click", () => {
  chrome.storage.local.clear().then(() => {
    afficher(null);
    $("messages").innerHTML = "";
    dire("effacé — génère une nouvelle identité");
  });
});

$("btn-effacer").addEventListener("click", async () => {
  await appeler("effacer");
  afficher(null);
  $("messages").innerHTML = "";
  dire("tout effacé", "#4ade80");
});

$("btn-remplir").addEventListener("click", async () => {
  if (!profil) return dire("génère d'abord une identité", "#f87171");
  try {
    const [onglet] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!onglet) return dire("aucun onglet actif", "#f87171");
    // Pas de permission "tabs" : on ne lit pas l'URL, on tente l'injection et on
    // explique l'echec si la page est interdite (chrome://, onglet extension, PDF...).
    try {
      // 1. poser l'identité dans la page (tous les cadres : un formulaire d'inscription
      //    peut vivre dans une iframe), 2. injecter le remplisseur, 3. lire les rapports
      await chrome.scripting.executeScript({
        target: { tabId: onglet.id, allFrames: true },
        func: (i) => { globalThis.__trashfiller_identite = i; },
        args: [profil],
      });
    } catch (e) {
      return dire("page interdite à l'extension (chrome:// ou page interne)", "#f87171");
    }
    const cadres = await chrome.scripting.executeScript({
      target: { tabId: onglet.id, allFrames: true },
      files: ["content.js"],
    });
    // un rapport par cadre : on additionne, et on garde les details du cadre principal
    const rapports = cadres.map((c) => c.result).filter((r) => r && r.remplis);
    const r = rapports.reduce((acc, x) => ({
      remplis: [...acc.remplis, ...x.remplis],
      non_reconnus: [...acc.non_reconnus, ...(x.non_reconnus || [])],
      sans_valeur: [...acc.sans_valeur, ...(x.sans_valeur || [])],
      cases_a_cocher: (acc.cases_a_cocher || 0) + (x.cases_a_cocher || 0),
    }), { remplis: [], non_reconnus: [], sans_valeur: [], cases_a_cocher: 0 });
    $("rapport").textContent =
      `${r.remplis.length} champ(s) rempli(s)` +
      (r.non_reconnus.length ? ` · ${r.non_reconnus.length} non reconnu(s)` : "") +
      (r.sans_valeur && r.sans_valeur.length ? ` · ${r.sans_valeur.length} sans équivalent` : "") +
      (r.cases_a_cocher ? ` · ${r.cases_a_cocher} case(s) à cocher toi-même (CGU)` : "") +
      (r.remplis.length ? "\n" + r.remplis.map((x) => x.champ).join(", ") : "");
    dire(r.remplis.length ? "page remplie" : "aucun champ reconnu", r.remplis.length ? "#4ade80" : "#f87171");
    if (r.remplis.length) await afficherMessages();
  } catch (e) {
    dire(`remplissage : ${e.message}`, "#f87171");
  }
});

$("btn-rafraichir").addEventListener("click", () => { afficherMessages(); });

$("btn-voir-mdp").addEventListener("click", () => {
  mdpVisible = !mdpVisible;
  $("btn-voir-mdp").textContent = mdpVisible ? "cacher" : "voir";
  if (profil) $("id-mdp").textContent = mdpVisible ? profil.mot_de_passe : "•".repeat(12);
});

document.addEventListener("click", (ev) => {
  const bouton = ev.target.closest(".copie[data-copie]");
  if (!bouton || !profil) return;
  const valeur = profil[bouton.dataset.copie];
  if (valeur) {
    navigator.clipboard.writeText(valeur).then(() => dire(`${bouton.dataset.copie} copié`));
  }
});

// ------------------------------------------------------------------ demarrage
(async () => {
  const { profil: p } = await appeler("etat");
  afficher(p);
  if (p) await chargerBoite();
  // le popup ne vit que quelques secondes : on rafraichit tant qu'il est ouvert,
  // c'est plus simple (et plus robuste) qu'une alarme dans le service worker.
  minuteur = setInterval(() => { if (profil) afficherMessages(); }, 5000);
  window.addEventListener("unload", () => clearInterval(minuteur));
})();
