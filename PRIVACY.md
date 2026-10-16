# Politique de confidentialité — TrashFiller

Dernière mise à jour : 16 octobre 2026

TrashFiller est une extension Chrome qui crée une identité jetable (adresse de courriel
temporaire, mot de passe aléatoire, nom, adresse, téléphone) et remplit les formulaires
d'inscription avec, pour éviter de donner ses vraies informations à un site qu'on ne
revisitera pas.

## Ce qui est enregistré, et où

Tout reste dans le navigateur, dans le stockage local de l'extension (`chrome.storage.local`) :

- l'identité générée (nom, prénom, adresse postale, date de naissance, téléphone, adresse
  de courriel jetable, mot de passe associé) ;
- le jeton d'accès à la boîte jetable, nécessaire pour lire les messages de validation.

Ces données ne sont transmises à personne, hormis le service de boîte jetable décrit
ci-dessous. Elles disparaissent dès que vous cliquez sur **Tout effacer** dans l'extension,
ou quand vous désinstallez celle-ci.

## Le seul service contacté

Pour fournir la boîte jetable, l'extension appelle **mail.tm** (`https://api.mail.tm`),
l'opérateur de la boîte temporaire. Ce service reçoit l'adresse générée et le mot de passe
généré, sans aucune autre information. Ses propres règles s'appliquent à ces échanges
(https://mail.tm). Aucun autre serveur, aucun service de mesure d'audience, aucune
télémétrie n'est contacté.

Important : les boîtes créées sur mail.tm sont **publiques** — toute personne qui connaît
l'adresse peut lire les messages. Il ne faut donc jamais s'en servir pour un compte bancaire,
administratif, ou rattaché à votre identité réelle.

## Ce que l'extension ne fait pas

- Elle ne lit pas votre historique de navigation, vos onglets ou vos pages en dehors de
  l'onglet où vous cliquez sur **Remplir la page**.
- Elle ne crée aucun compte chez l'éditeur, n'envoie aucun rapport d'usage, ne vend ni ne
  partage aucune donnée.
- Elle ne coche jamais les cases d'acceptation des conditions d'utilisation et ne résout
  aucun captcha : ces choix restent les vôtres.
- Elle n'écrit jamais dans les champs cachés, désactivés ou dans les jetons de sécurité des
  formulaires.

## Autorisations, et pourquoi

- **storage** : garder l'identité et le jeton de la boîte entre deux ouvertures du popup.
- **activeTab** : n'agir que sur l'onglet où vous cliquez explicitement sur l'extension.
- **scripting** : remplir les champs de cette page, à la demande.
- **https://api.mail.tm/\*** : créer la boîte jetable et lire le message de validation.

## Vos droits

Les données étant locales, vous en disposez directement : elles se suppriment depuis
l'extension ou en désinstallant celle-ci. Aucune copie n'existe ailleurs.

## Contact

Une question, un défaut, une donnée à signaler :
https://github.com/Mehdo0/trashfiller/issues
