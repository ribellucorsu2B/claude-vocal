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
   Si Windows affiche *« Windows a protégé votre ordinateur »*, clique sur **Informations complémentaires**, puis **Exécuter quand même**. Le programme n'est pas signé numériquement, c'est normal pour un petit projet perso.
4. Au premier lancement, il télécharge le modèle vocal français (~40 Mo). Après une minute, une **icône verte** apparaît près de l'horloge : c'est prêt !

Il se lance ensuite tout seul à chaque démarrage de Windows (décochable dans le menu).

Pas besoin d'installer Python ni quoi que ce soit d'autre.

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
