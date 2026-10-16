# TrashFiller

Extension Chrome (Manifest V3) qui règle un agacement précis : devoir donner ses vraies
informations à un site qu'on ne revisitera jamais.

Elle génère une identité jetable — **boîte mail temporaire réelle**, mot de passe aléatoire,
nom, prénom, adresse, téléphone — la pose dans le formulaire d'inscription en un clic, puis
te donne **le lien de validation dès qu'il arrive**.

Rien n'est conservé en dehors de ton navigateur. Il n'y a aucun serveur à nous.

## Installation

1. Télécharge le dépôt (ou `TrashFiller-1.0.0.zip`, puis décompresse-le).
2. Ouvre `chrome://extensions` (ou `edge://extensions`).
3. Active **Mode développeur** en haut à droite.
4. Clique **Charger l'extension non empaquetée** et choisis le dossier qui contient
   `manifest.json`.
5. Épingle l'icône dans la barre d'outils.

## Usage

1. Sur la page d'inscription, clique l'icône → **Générer une identité**. La boîte jetable est
   créée pour de vrai (API mail.tm) et l'identité s'affiche.
2. **Remplir la page** : les champs reconnus sont remplis — email, mot de passe et sa
   confirmation, nom, prénom, pseudo, adresse, NPA, ville, téléphone, date de naissance
   (groupes jour / mois / année compris), listes déroulantes pays et date. Le rapport indique
   combien de champs ont été remplis et ce qui n'a pas été reconnu.
3. Coche les CGU toi-même, puis valide le formulaire.
4. Le mail de validation arrive : voir ci-dessous. **Tout effacer** supprime l'identité et la
   boîte du navigateur.

## Le mail de validation, concrètement

C'est la partie qui sépare « un formulaire rempli » de « un compte créé ».

1. La boîte est créée **avant** le remplissage, et son jeton d'accès est conservé dans
   `chrome.storage.local` : l'extension peut donc lire cette boîte à tout moment.
2. Deux endroits te le servent :
   - **le popup** : la boîte de réception se rafraîchit toutes les 5 secondes tant qu'il est
     ouvert, avec les messages, le lien cliquable et le code copiable ;
   - **un bandeau sur la page** : posé après le remplissage, il interroge la boîte toutes les
     5 secondes et fait apparaître « Ouvrir le lien de validation » dès que le mail tombe.
     C'est ce qui évite d'avoir à rouvrir le popup au bon moment. Il s'arrête au bout de
     10 minutes et se ferme d'un clic.
3. Les liens sont extraits **des attributs `href`** du HTML (avant tout nettoyage de balises),
   les codes sont cherchés dans le texte. Les liens de désabonnement et de politique de
   confidentialité sont écartés : il ne reste que ce qui ressemble à une validation.
4. Un clic ouvre le lien dans un nouvel onglet ; un clic sur un code le copie.

Limite assumée : la boîte de mail.tm est **publique** — quiconque connaît l'adresse peut lire
les messages. Ne t'en sers que là où tu n'as rien à perdre.

## Ce que l'outil ne fait pas, volontairement

- **Il ne coche pas les cases CGU / politique de confidentialité** : accepter des conditions
  au nom d'un utilisateur n'est pas à un outil de le décider.
- **Il ne résout aucun captcha.** Si un défi s'affiche, c'est à toi.
- Les champs invisibles, désactivés et les jetons cachés (`csrf_token`) ne sont jamais touchés.

## Limites à connaître

- Boîte publique (ci-dessus) : **jamais** pour un compte bancaire, administratif ou rattaché à
  ton identité réelle.
- Certains sites refusent les domaines jetables.
- mail.tm **limite le rythme de création** : le message d'erreur te le dit et te propose de
  réessayer dans une minute.
- Les conditions d'utilisation de certains sites interdisent les comptes jetables : c'est ton
  choix d'utilisateur, l'outil ne le contourne pas.

## Vie privée

- L'identité et le jeton vivent uniquement dans `chrome.storage.local`.
- Le seul service contacté est `api.mail.tm` (l'opérateur de la boîte jetable).
- Aucune télémétrie, aucun serveur intermédiaire, aucun code distant (interdit en MV3).
- Permissions : `storage` (garder l'identité), `activeTab` + `scripting` (remplir la page sur
  laquelle tu cliques, iframes comprises), et `host_permissions` limité à `https://api.mail.tm/*`.

## Efficacité mesurée sur de vraies pages (16.10.2026)

Méthode : chaque page d'inscription réelle est chargée, le remplisseur est injecté, et on
mesure. **Aucun formulaire n'est jamais soumis.** Deux moteurs : Chrome headless, puis camoufox
(Firefox modifié) quand Chrome est bloqué.

| Page | Champs visibles | Remplis | Remarque |
|---|---|---|---|
| GitLab (inscription) | 6 | 5 | tous les champs utiles |
| Mastodon.social | 8 | 7 | après un clic sur « Continuer » (assistant en 3 étapes) |
| Hacker News | 4 | 4 | formulaire de connexion |
| Bandcamp | 6 | 4 | l'email et sa confirmation sont remplis |
| Vercel | 2 | 1 | après un clic sur « Sign up » |
| Netlify | 2 | 1 | après un clic sur « Sign up » |
| Twitch | 1 | 1 | la suite du formulaire arrive après l'email |
| Reddit | 2 | 1 | via camoufox ; le 2e champ est une case à cocher, jamais touchée |
| GitHub | 0 | — | « Accès temporairement restreint » : GitHub bloque l'IP du serveur |
| Ricardo.ch | 0 | — | mur anti-robot Cloudflare |

**Bilan : 7 pages exploitables sur 10, 23 champs remplis sur 29 (79 %), zéro classement
suspect** — chaque champ rempli est revalidé contre ses propres signaux (name, id, label,
placeholder) par le test, pas seulement compté.

Deux enseignements honnêtes :

- les pages restées à zéro le sont pour des raisons **d'environnement d'automatisation** (IP de
  datacenter bloquée, mur Cloudflare) ou parce que le formulaire **n'existe qu'après une
  interaction** — pas parce que le remplisseur échoue. GitHub le dit lui-même : « un robot est
  sur le même réseau (IP 188.213.130.220) que vous » ;
- un formulaire local complet (12 champs, cases à cocher, jeton caché, champs désactivés)
  passe à **12/12**, et ce chemin-là est vérifié à chaque exécution des tests.

## Tests

```bash
python3 tests/test_contract.py                     # contrat statique : fichiers, ids, permissions
node tests/test_parsing.mjs                        # parsing des mails, mots de passe, identités
~/stage42/.venv/bin/python tests/test_autofill.py  # bout en bout dans un vrai Chrome
~/stage42/.venv/bin/python tests/test_sites_reels.py     # 10 vraies pages d'inscription
~/stage42/.venv/bin/python tests/test_sites_camoufox.py  # les mêmes via camoufox
```

Ce que le test de bout en bout prouve réellement : 12 champs d'un vrai formulaire remplis avec
les bonnes valeurs, `Pays = CH` dans la liste déroulante, cases CGU et newsletter **intactes**,
champs désactivés, invisibles et jeton caché **intacts**, événements `input`/`change`/`blur`
émis, création d'une vraie boîte jetable depuis le popup, et un chemin d'erreur propre quand la
page interdit l'injection. Les rapports des deux passes sur sites réels sont versionnés
(`tests/rapport_sites*.json`) avec les captures d'écran (`tests/captures/`).

## Notes techniques (les pièges rencontrés)

- **mail.tm supprime les points** du nom d'utilisateur : créer `jean.dupont@…` puis demander un
  jeton pour cette chaîne renvoie `401 Invalid credentials`, le serveur ayant stocké
  `jeandupont@…`. L'extension n'utilise que `[a-z0-9]` et se sert de l'adresse renvoyée par la
  création.
- **Le lien d'un mail HTML vit dans un attribut `href`** : il faut l'extraire avant de retirer
  les balises, sinon aucun lien de validation n'est jamais remonté.
- **Écrire dans un champ ne suffit pas** : passer par le setter natif puis émettre `input`,
  `change` et `blur`, sinon React et Vue considèrent le champ vide.
- **`offsetParent` vaut `null` dans un shadow DOM** (le spec le dit) : s'en servir comme test de
  visibilité fait disparaître tous les formulaires en composants web. `getClientRects()` est le
  bon test de rendu.
- **Un `<select>` n'accepte pas le setter d'`HTMLInputElement`** (« Illegal invocation ») : les
  listes déroulantes ont leur propre boucle.
- **Le texte du bloc parent contient les libellés des autres champs** : il a fait classer un
  `<select>` « Pays » en « Ville ». Les signaux forts (name, id, label) sont testés d'abord, les
  faibles ensuite.
- **Un groupe de dates** (`date_of_birth(3i)/(2i)/(1i)`, style Rails ou Django) recevait la date
  complète dans chaque partie : les règles jour / mois / année passent maintenant avant la
  règle « naissance ».

## Fichiers

```
manifest.json         declaration MV3 (permissions minimales)
background.js         service worker : boîte jetable mail.tm + stockage local
content.js            remplissage + bandeau de validation (injecté à la demande, iframes comprises)
popup.html/.css/.js   interface : identité, bouton remplir, boîte de réception
icons/                icônes 16/48/128
tests/                contrat, parsing, bout en bout, vraies pages + rapports et captures
.push.py              envoi du dépôt par l'API Git Data (n'est pas poussé lui-même)
```

Licence MIT.
