# Git AutoPush

Petit logiciel Windows pour envoyer un dossier sur GitHub en quelques clics, sans taper de commande Git.

## Fonctionnement

1. Tu renseignes le lien du dépôt GitHub, la branche, ton identité Git et, si besoin, un token.
2. Tu cliques sur le bouton d'envoi : l'explorateur de fichiers s'ouvre.
3. Tu choisis le dossier à envoyer.
4. Le programme fait le reste : initialisation du dépôt, remote, branche, `add`, `commit` et `push`.

Si le dépôt GitHub contient déjà des fichiers, le programme propose de les récupérer (`pull --rebase`) puis réessaie l'envoi.

## Contenu du projet

| Fichier | Rôle |
|---|---|
| `git_autopush_gui.py` | L'application (interface graphique) |
| `build_exe.bat` | Compile l'application en `GitAutoPush.exe` et écrit un log |
| `git_autopush.py` | Ancienne version en ligne de commande (optionnelle) |

## Prérequis

- Windows 10 ou plus récent
- [Git](https://git-scm.com/downloads) installé (obligatoire pour utiliser l'application)
- [Python 3.12](https://www.python.org/downloads/) 64 bits, uniquement pour créer le `.exe`

## Utilisation sans compiler

```
python git_autopush_gui.py
```

## Créer le .exe

1. Place `git_autopush_gui.py` et `build_exe.bat` dans le même dossier.
2. Double-clique sur `build_exe.bat`.
3. Récupère `dist\GitAutoPush.exe`. Il fonctionne ensuite sans Python.

Le script utilise Python 3.12 en priorité, puis 3.13, puis le Python par défaut du système. Les versions très récentes de Python peuvent ne pas être compatibles avec PyInstaller.

## Logs de compilation

Chaque compilation écrit un fichier `build_AAAAMMJJ_HHMMSS.log` dans le dossier `logs`, créé à côté de `build_exe.bat`. Il contient :

- la version de Windows et l'architecture du processeur
- la version de Python utilisée
- la sortie complète de PyInstaller
- une vérification du `.exe` produit (taille, type, architecture)

En cas de problème, c'est ce fichier qu'il faut consulter ou partager.

## Authentification GitHub

GitHub n'accepte plus le mot de passe du compte en HTTPS. Deux options :

- **Token vide :** Git Credential Manager ouvre sa fenêtre de connexion GitHub la première fois.
- **Token renseigné :** crée un Personal Access Token (GitHub > Settings > Developer settings > Personal access tokens) avec le droit `repo`, puis saisis ton pseudo GitHub et le token dans l'application.

## Données enregistrées

Les champs saisis sont mémorisés dans `~/.git_autopush_gui.json` (dossier utilisateur) pour être préremplis au lancement suivant. Le token n'est jamais enregistré : il faut le ressaisir à chaque lancement. Il n'est pas écrit non plus dans la configuration Git du dossier envoyé.

## Dépannage

| Problème | Piste |
|---|---|
| « Cette application ne peut pas s'exécuter sur votre PC » | Recompiler avec Python 3.12 64 bits et lire le log pour vérifier l'architecture du `.exe` |
| Git introuvable | Installer Git et relancer l'application |
| Authentification refusée | Utiliser un token avec le droit `repo`, ou vérifier le pseudo |
| Dépôt introuvable | Vérifier le lien et créer le dépôt sur GitHub avant l'envoi |
| Push rejeté | Accepter le `pull --rebase` proposé par l'application |
| Git ne connaît pas l'identité | Remplir les champs Nom Git et Email Git |
