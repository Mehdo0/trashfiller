// Test des fonctions de parsing du worker (Node, sans navigateur).
//
// Lancer : node tests/test_parsing.mjs
//
// On teste ce qui casse silencieusement l'usage reel : ne pas voir le lien de
// validation noye dans un mail HTML, ou sortir un code qui n'en est pas un.

// stubs minimalistes : le module touche chrome.* au chargement
globalThis.chrome = {
  runtime: { onMessage: { addListener() {} } },
  storage: { local: { get: async () => ({}), set: async () => {}, clear: async () => {} } },
};
globalThis.crypto ??= (await import("node:crypto")).webcrypto;

const { liensEtCodes, texteDuMessage, motDePasse, identite } = await import("../background.js");

let echecs = 0;
function verifier(condition, message) {
  console.log(`${condition ? "  ok  " : "ECHEC "} ${message}`);
  if (!condition) echecs++;
}

// ---- 1. un mail de validation typique --------------------------------------
const mailHtml = `
<html><body><p>Bienvenue sur le site !</p>
<p>Confirme ton adresse en cliquant ici :
<a href="https://exemple.ch/confirm?token=9f2b7c1d&amp;u=42">Confirmer mon compte</a></p>
<p>Ou saisis le code 884213 dans le formulaire.</p>
<p><a href="https://mail.tm/unsubscribe">se désabonner</a></p>
<p><a href="https://exemple.ch/privacy">politique de confidentialité</a></p>
</body></html>`;
const texte = texteDuMessage({ html: [mailHtml], text: [] });
const { liens, codes } = liensEtCodes(texte);

verifier(texte.includes("Confirme ton adresse"), "le HTML est converti en texte lisible");
verifier(liens.some((l) => l.includes("exemple.ch/confirm")), "le lien de validation est remonte");
verifier(codes.includes("884213"), "le code a 6 chiffres est remonte");
verifier(!liens.some((l) => /mail\.tm|unsubscribe/.test(l)), "les liens de désabonnement sont ecartes");
verifier(!liens.some((l) => /privacy|confidentialite/.test(l)), "les liens de politique sont ecartes");

// ---- 2. sortie propre meme sur un corps vide -------------------------------
const vide = liensEtCodes(texteDuMessage({ html: [], text: [] }));
verifier(vide.liens.length === 0 && vide.codes.length === 0, "corps vide : aucune exception, listes vides");

// ---- 3. mot de passe -------------------------------------------------------
const mdp = motDePasse();
verifier(mdp.length === 20, `mot de passe de 20 caracteres (obtenu ${mdp.length})`);
verifier(/[a-z]/.test(mdp) && /[A-Z]/.test(mdp), "contient minuscule et majuscule");
verifier(/[0-9]/.test(mdp), "contient un chiffre");
verifier(/[!@#$%&*?]/.test(mdp), "contient un caractere special");
verifier(motDePasse() !== mdp, "deux appels donnent deux mots de passe differents");

// ---- 4. identite -----------------------------------------------------------
const id = identite();
verifier(/^[A-Za-z]+$/.test(id.prenom) && /^[A-Za-z]+$/.test(id.nom), "prenom et nom plausibles");
verifier(/^\d{4}-\d{2}-\d{2}$/.test(id.naissance), `naissance au format ISO (${id.naissance})`);
const annee = Number(id.naissance.slice(0, 4));
verifier(annee >= 1990 && annee <= 2009, `annee de naissance credible (${annee})`);
verifier(/^[a-z0-9]+$/.test(id.pseudo), `pseudo sans point ni tiret (${id.pseudo})`);

console.log(echecs ? `\n${echecs} echec(s)` : "\nparsing OK");
process.exit(echecs ? 1 : 0);
