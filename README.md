# 🎙️ Claude vocal

**Éteins, mets en veille, redémarre ou verrouille ton PC Windows à la voix**, avec le micro de ta webcam (ou n'importe quel micro).

> « Claude, éteins l'ordinateur » · « Claude, mets en veille l'ordinateur »

- **100 % hors ligne** : la reconnaissance vocale tourne sur ton PC, ta voix n'est jamais envoyée sur internet.
- **Discret** : une petite icône près de l'horloge, et c'est tout.
- **Sans risque** : un compte à rebours te laisse le temps d'annuler, et les logiciels ne sont jamais fermés de force.
- **Ton prénom** : « Claude » par défaut, mais tu peux choisir le prénom de ton choix.

## 📥 Installation

1. Télécharge **[ClaudeVocal.exe](https://github.com/ribellucorsu2B/claude-vocal/releases/latest/download/ClaudeVocal.exe)** (page des versions : [Releases](https://github.com/ribellucorsu2B/claude-vocal/releases/latest)).
2. Range-le dans un dossier où il restera, par exemple `Documents\ClaudeVocal`.
3. Double-clique dessus.
4. Au premier lancement, il télécharge le modèle vocal français (~40 Mo). Après une minute, une **icône verte** apparaît près de l'horloge : c'est prêt ! (Si tu ne la vois pas, clique sur la petite flèche **^** à côté de l'horloge.)

Il se lance ensuite tout seul à chaque démarrage de Windows (décochable dans le menu).

Pas besoin d'installer Python ni quoi que ce soit d'autre, et pas besoin des droits administrateur.

### ⚠️ Un avertissement s'affiche ? C'est normal

Windows et les navigateurs se méfient de **tout nouveau programme** qu'ils ne connaissent pas encore. Ça ne veut pas dire qu'il est dangereux : seulement qu'il est récent et qu'il n'a pas de signature numérique payante. Tu peux voir deux avertissements :

**1. Au téléchargement**, Edge affiche *« ClaudeVocal.exe n'est pas fréquemment téléchargé »* :
passe la souris sur le téléchargement, clique sur **…** puis **Conserver**, ensuite sur **Afficher plus** puis **Conserver quand même**.
(Avec Chrome, c'est le même principe : choisis de conserver le fichier.)

**2. Au premier lancement**, Windows affiche *« Windows a protégé votre ordinateur »* :
clique sur **Informations complémentaires**, puis sur **Exécuter quand même**.

Ces avertissements disparaissent d'eux-mêmes à mesure que le programme est téléchargé par d'autres personnes.

### 🔒 Est-ce que c'est sûr ?

- **Tout le code est visible** ici, dans un seul fichier : [claude_vocal.py](claude_vocal.py).
- **Le .exe n'est pas fabriqué sur mon PC** : il est construit publiquement par GitHub à partir de ce code. Chaque fabrication est consultable dans l'onglet [Actions](https://github.com/ribellucorsu2B/claude-vocal/actions).
- **Il ne va sur internet qu'une seule fois**, au premier lancement, pour télécharger le modèle vocal français sur le site officiel de [Vosk](https://alphacephei.com/vosk/models). Ta voix ne quitte jamais ton PC.
- **Rien de caché** : pas d'installation, pas de droits administrateur. Pour le désinstaller, il suffit de supprimer le fichier (voir la partie « Désinstaller » plus bas).
- **Tu peux le faire vérifier** gratuitement par des dizaines d'antivirus sur [virustotal.com](https://www.virustotal.com) : glisse simplement le fichier sur la page.

Il arrive qu'un antivirus se méfie d'un programme fabriqué avec PyInstaller, l'outil qui transforme le code Python en .exe : c'est une fausse alerte connue. Dans le doute, tu peux aussi lancer le programme depuis le code source (voir plus bas).

## 🗣️ Les phrases

| Tu dis… | Il fait… |
|---|---|
| « Claude, éteins l'ordinateur » | Extinction, après 15 s pour annuler |
| « Claude, mets en veille l'ordinateur » | Mise en veille, après 3 s |
| « Claude, redémarre l'ordinateur » | Redémarrage, après 15 s pour annuler |
| « Claude, verrouille l'ordinateur » | Verrouille la session |
| « Claude, annule » | Annule l'action en attente |

Un petit carillon confirme qu'il a compris, et une fenêtre affiche le compte à rebours (avec les boutons **Annuler** et **Maintenant**).

Il faut toujours dire le prénom **et** « l'ordinateur » : une conversation normale ne déclenche rien.

## 🖱️ Le menu (clic droit sur l'icône)

- **Mode test** : ouvre une fenêtre qui affiche ce que le micro comprend. Les commandes sont simulées, rien n'est vraiment éteint. Idéal pour essayer ou régler ton prénom.
- **Lancer au démarrage de Windows** : coché par défaut.
- **Phrases reconnues** : le rappel des commandes (aussi accessible d'un simple clic gauche sur l'icône).
- **Réglages** : ouvre le fichier de réglages dans le Bloc-notes.
- **Ouvrir le journal** : utile si quelque chose ne marche pas.
- **Quitter**.

La couleur de l'icône indique l'état : 🟢 à l'écoute · 🟠 mode test · ⚪ problème (micro introuvable, pas d'internet au premier lancement…).

## ⚙️ Réglages

Clic droit sur l'icône, puis **Réglages** : le fichier s'ouvre dans le Bloc-notes. Modifie, enregistre (Ctrl+S), et c'est pris en compte en quelques secondes, sans redémarrer.

| Réglage | Rôle |
|---|---|
| `prenoms` | Le ou les prénoms qui déclenchent les commandes, séparés par des virgules. Le premier est affiché dans les messages. |
| `micro` | Un morceau du nom du micro à utiliser (ex. `C920`). Vide = détection automatique. |
| `delai_extinction` | Secondes pour annuler une extinction ou un redémarrage (15 par défaut). |
| `delai_veille` | Secondes avant la mise en veille (3 par défaut). |

**Changer de prénom** : choisis un prénom français assez courant, car le modèle vocal ne connaît que les mots de son dictionnaire (« Jarvis » risque de ne jamais être compris). Vérifie en **mode test** comment il est écrit, et ajoute les variantes à la liste si besoin.

**Plusieurs PC dans la même pièce ?** Donne un prénom différent à chacun, sinon « Claude, éteins l'ordinateur » les éteindra tous !

## 💡 Bon à savoir

- Ton micro entend aussi tes haut-parleurs (vidéos, Discord…) : le compte à rebours sert aussi à ça.
- Si le PC passe en **hibernation** au lieu de la veille, tape dans un terminal administrateur : `powercfg /h off`.
- Le programme se reconnecte tout seul au micro après une mise en veille ou si la webcam est débranchée puis rebranchée.
- Les réglages, le modèle vocal et le journal sont rangés dans `%LOCALAPPDATA%\ClaudeVocal`. Ce que tu dis n'est jamais écrit dans le journal.

## 🗑️ Désinstaller

1. Clic droit sur l'icône : décoche **Lancer au démarrage de Windows**, puis **Quitter**.
2. Supprime `ClaudeVocal.exe` et le dossier `%LOCALAPPDATA%\ClaudeVocal` (colle ce chemin dans la barre d'adresse de l'Explorateur).

## 🛠️ Lancer depuis le code source

```
pip install -r requirements.txt
python claude_vocal.py
```

Le `.exe` est fabriqué automatiquement par GitHub Actions à chaque nouvelle version publiée dans l'onglet *Releases* : voir [.github/workflows/construire-exe.yml](.github/workflows/construire-exe.yml).

## Crédits

- Reconnaissance vocale : [Vosk](https://alphacephei.com/vosk/) et son modèle français `vosk-model-small-fr`.
- Projet perso, sans lien avec Anthropic : « Claude » n'est ici qu'un prénom de déclenchement.

Licence [MIT](LICENSE).
