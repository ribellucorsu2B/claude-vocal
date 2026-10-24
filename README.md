# VoxOff

**Éteins, mets en veille, redémarre ou verrouille ton PC Windows à la voix**, avec le micro de ta webcam (ou n'importe quel micro).

> « Ordinateur, éteins-toi » · « Ordinateur, mets-toi en veille »

🇬🇧 *English version below: "Computer, shut down" · "Computer, go to sleep".*

- **100 % hors ligne** : la reconnaissance vocale tourne sur ton PC, ta voix n'est jamais envoyée sur internet.
- **Discret** : une petite icône près de l'horloge, et c'est tout.
- **Sans risque** : un compte à rebours te laisse le temps d'annuler, et les logiciels ne sont jamais fermés de force.
- **Français ou anglais**, et un mot d'appel personnalisable (un prénom, si tu préfères).

## 📥 Installation

1. Télécharge **[VoxOff.exe](https://github.com/ribellucorsu2B/voxoff/releases/latest/download/VoxOff.exe)** (page des versions : [Releases](https://github.com/ribellucorsu2B/voxoff/releases/latest)).
2. Range-le dans un dossier où il restera, par exemple `Documents\VoxOff`.
3. Double-clique dessus.
4. Au premier lancement, il télécharge le modèle vocal (~40 Mo). Après une minute, une **icône verte** apparaît près de l'horloge : c'est prêt ! (Si tu ne la vois pas, clique sur la petite flèche **^** à côté de l'horloge.)

Il se lance ensuite tout seul à chaque démarrage de Windows (décochable dans le menu).

Pas besoin d'installer Python ni quoi que ce soit d'autre, et pas besoin des droits administrateur.

### ⚠️ Un avertissement s'affiche ? C'est normal

Windows et les navigateurs se méfient de **tout nouveau programme** qu'ils ne connaissent pas encore. Ça ne veut pas dire qu'il est dangereux : seulement qu'il est récent et qu'il n'a pas de signature numérique payante. Tu peux voir deux avertissements :

**1. Au téléchargement**, Edge affiche *« VoxOff.exe n'est pas fréquemment téléchargé »* :
passe la souris sur le téléchargement, clique sur **…** puis **Conserver**, ensuite sur **Afficher plus** puis **Conserver quand même**.
(Avec Chrome, c'est le même principe : choisis de conserver le fichier.)

**2. Au premier lancement**, Windows affiche *« Windows a protégé votre ordinateur »* :
clique sur **Informations complémentaires**, puis sur **Exécuter quand même**.

Ces avertissements disparaissent d'eux-mêmes à mesure que le programme est téléchargé par d'autres personnes.

### 🔒 Est-ce que c'est sûr ?

- **Tout le code est visible** ici, dans un seul fichier : [voxoff.py](voxoff.py).
- **Le .exe n'est pas fabriqué sur mon PC** : il est construit publiquement par GitHub à partir de ce code. Chaque fabrication est consultable dans l'onglet [Actions](https://github.com/ribellucorsu2B/voxoff/actions).
- **Il ne va sur internet que pour télécharger le modèle vocal**, au premier lancement (et si tu changes de langue), sur le site officiel de [Vosk](https://alphacephei.com/vosk/models). Ta voix ne quitte jamais ton PC.
- **Rien de caché** : pas d'installation, pas de droits administrateur. Pour le désinstaller, il suffit de supprimer le fichier (voir la partie « Désinstaller » plus bas).
- **Tu peux le faire vérifier** gratuitement par des dizaines d'antivirus sur [virustotal.com](https://www.virustotal.com) : glisse simplement le fichier sur la page.

Il arrive qu'un antivirus se méfie d'un programme fabriqué avec PyInstaller, l'outil qui transforme le code Python en .exe : c'est une fausse alerte connue. Dans le doute, tu peux aussi lancer le programme depuis le code source (voir plus bas).

## 🗣️ Les phrases

| Tu dis… | Il fait… |
|---|---|
| « Ordinateur, éteins-toi » | Extinction, après 15 s pour annuler |
| « Ordinateur, mets-toi en veille » | Mise en veille, après 3 s |
| « Ordinateur, redémarre » | Redémarrage, après 15 s pour annuler |
| « Ordinateur, verrouille-toi » | Verrouille la session |
| « Ordinateur, annule » | Annule l'action en attente |

La phrase doit **commencer** par « Ordinateur » : une conversation normale (« j'ai éteint l'ordinateur hier ») ne déclenche rien. Chaque action a son propre son pour confirmer qu'il a compris, et une fenêtre affiche le compte à rebours, avec les boutons **Annuler** et **Maintenant**.

## 🖱️ Le menu (clic droit sur l'icône)

- **Mode test** : ouvre une fenêtre qui affiche ce que le micro comprend. Les commandes sont simulées, rien n'est vraiment éteint. Idéal pour essayer ou régler ton mot d'appel.
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
| `langue` | `fr` (français) ou `en` (anglais), pour les commandes et les menus. Au premier lancement, VoxOff prend la langue de Windows. |
| `mots_appel` | Le ou les mots d'appel, séparés par des virgules. Vide = « ordinateur » (ou « computer » en anglais). |
| `micro` | Un morceau du nom du micro à utiliser (ex. `C920`). Vide = détection automatique. |
| `delai_extinction` | Secondes pour annuler une extinction ou un redémarrage (15 par défaut). |
| `delai_veille` | Secondes avant la mise en veille (3 par défaut). |

**Un prénom comme mot d'appel ?** Choisis un prénom français assez courant, car le modèle vocal ne connaît que les mots de son dictionnaire (« Jarvis » risque de ne jamais être compris). Vérifie en **mode test** comment il est écrit, et ajoute les variantes à la liste si besoin.

**Plusieurs PC dans la même pièce ?** Donne un mot d'appel différent à chacun, sinon un seul ordre les éteindra tous !

**Tes propres sons :** place des fichiers WAV nommés `eteindre.wav`, `veille.wav`, `redemarrer.wav`, `verrouiller.wav` et `annuler.wav` dans un dossier `sons`, à côté du fichier de réglages.

## 💡 Bon à savoir

- Ton micro entend aussi tes haut-parleurs (vidéos, Discord…) : le compte à rebours sert aussi à ça.
- Si le PC passe en **hibernation** au lieu de la veille, tape dans un terminal administrateur : `powercfg /h off`.
- Le programme se reconnecte tout seul au micro après une mise en veille ou si la webcam est débranchée puis rebranchée.
- Les réglages, les modèles vocaux et le journal sont rangés dans `%LOCALAPPDATA%\VoxOff`. Ce que tu dis n'est jamais écrit dans le journal.
- VoxOff s'appelait auparavant « Claude vocal » : il remplace automatiquement l'ancienne version.

## 🗑️ Désinstaller

1. Clic droit sur l'icône : décoche **Lancer au démarrage de Windows**, puis **Quitter**.
2. Supprime `VoxOff.exe` et le dossier `%LOCALAPPDATA%\VoxOff` (colle ce chemin dans la barre d'adresse de l'Explorateur).

## 🛠️ Lancer depuis le code source

```
pip install -r requirements.txt
python voxoff.py
```

Le `.exe` est fabriqué automatiquement par GitHub Actions à chaque nouvelle version publiée dans l'onglet *Releases* : voir [.github/workflows/construire-exe.yml](.github/workflows/construire-exe.yml).

---

## 🇬🇧 English

**Shut down, sleep, restart or lock your Windows PC by voice**, using your webcam's microphone (or any microphone). 100% offline: speech recognition runs on your PC, your voice is never sent anywhere.

### Install

1. Download **[VoxOff.exe](https://github.com/ribellucorsu2B/voxoff/releases/latest/download/VoxOff.exe)** and keep it in a folder where it will stay (e.g. `Documents\VoxOff`).
2. Double-click it. Windows may warn you, as it does for any new program: in the browser choose **Keep**, then on *"Windows protected your PC"* click **More info**, then **Run anyway**.
3. On first launch it downloads the voice model (~40 MB). A green icon appears next to the clock (click the **^** arrow if you don't see it).

If Windows is in English, VoxOff starts in English. Otherwise: right-click the icon, open **Réglages** (settings) and set `langue = en`.

### Voice commands

| Say… | It does… |
|---|---|
| "Computer, shut down" (or "turn off") | Shuts down after a 15 s countdown |
| "Computer, go to sleep" | Sleeps after 3 s |
| "Computer, restart" | Restarts after a 15 s countdown |
| "Computer, lock" | Locks the session |
| "Computer, cancel" | Cancels the pending action |

Each action has its own sound. The sentence must **start** with the wake word, so normal conversation never triggers anything. Apps are never force-closed: if something is unsaved, Windows asks you first.

### Menu and settings

Right-click the icon for **test mode** (shows what the microphone hears, nothing is really done), **start with Windows**, **settings** and **quit**. In the settings file you can change the language, the wake word (`wake_words`), the microphone and the delays; changes apply within seconds. Data lives in `%LOCALAPPDATA%\VoxOff`. To uninstall, untick *Start with Windows*, quit, then delete `VoxOff.exe` and that folder.

## Crédits

- Reconnaissance vocale / speech recognition : [Vosk](https://alphacephei.com/vosk/) et ses modèles `vosk-model-small-fr` et `vosk-model-small-en-us`.
- Sons / sounds : créés au synthé par ribellucorsu2B.

Licence [MIT](LICENSE).
