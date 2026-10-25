# -*- coding: utf-8 -*-
"""
VoxOff : éteins, mets en veille, redémarre ou verrouille ton PC Windows à la voix.
VoxOff: shut down, sleep, restart or lock your Windows PC by voice.

    « Ordinateur, arrête-toi »  ·  « Ordinateur, mets-toi en veille »
    "Computer, shut down"       ·  "Computer, go to sleep"

Une icône près de l'horloge montre que l'écoute tourne (clic droit pour le menu).
La reconnaissance vocale (Vosk) fonctionne hors ligne : la voix ne quitte jamais le PC.
Le seul accès à internet est le téléchargement du modèle vocal (~40 Mo) au premier
lancement, et à nouveau si on change de langue.
"""

import array
import configparser
import functools
import io
import json
import logging
import logging.handlers
import math
import os
import queue
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback
import unicodedata
import wave
import zipfile
from pathlib import Path

VERSION = "3.1.0"
NOM_APPLI = "VoxOff"

DONNEES = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "VoxOff"
DOSSIER_MODELES = DONNEES / "modeles"
DOSSIER_SONS_PERSO = DONNEES / "sons"
FICHIER_REGLAGES = DONNEES / "reglages.ini"
JOURNAL = DONNEES / "voxoff.log"

MODELES = {
    "fr": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
    "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
}

# Surveillance du micro (secondes)
PAUSE_ENDORMI = 10         # programme figé plus longtemps que ça = le PC dormait
DELAI_REVEIL_WEBCAM = 6    # temps laissé à la webcam pour se réveiller avant de la rouvrir
SILENCE_SUSPECT = 30       # signal parfaitement plat depuis ce temps = micro « mort »

FENETRE_ACTION = 5         # l'ordre doit venir dans les premiers mots après le mot d'appel

# Mots reconnus par langue. Les commandes sont des suites de débuts de mots ;
# l'ordre compte : la première commande reconnue l'emporte.
LANGUES = {
    "fr": {
        "nom": "français",
        "appel": ["ordinateur", "ordinateurs", "ordi"],
        "remplissage": {"euh", "bon", "alors", "eh", "he", "hey", "ok", "okay", "dis", "allez"},
        "commandes": {
            "annuler": [("annul",), ("stop",)],
            # « arrête-toi » : éteint le PC, mais annule si un compte à rebours tourne
            # (« Ordinateur, arrête ! » veut alors dire « stop »).
            "arreter": [("arret",)],
            "veille": [("veille",), ("dodo",)],
            "redemarrer": [("redemar",)],
            "eteindre": [("etein",), ("eteign",)],
            "verrouiller": [("verrou",)],
        },
    },
    "en": {
        "nom": "English",
        "appel": ["computer", "computers"],
        "remplissage": {"hey", "ok", "okay", "um", "uh", "so", "oh", "hi"},
        "commandes": {
            "annuler": [("cancel",), ("abort",), ("stop",)],
            "veille": [("sleep",), ("suspend",), ("standby",)],
            "redemarrer": [("restart",), ("reboot",)],
            "eteindre": [("shut", "down"), ("shutdown",), ("turn", "off"), ("power", "off"),
                         ("switch", "off")],
            "verrouiller": [("lock",)],
        },
    },
}

LIBELLES_JOURNAL = {"annuler": "Annulation", "veille": "Mise en veille", "redemarrer": "Redémarrage",
                    "eteindre": "Extinction", "verrouiller": "Verrouillage"}

TEXTES = {
    "fr": {
        "libelles": {"annuler": "Annulation", "veille": "Mise en veille", "redemarrer": "Redémarrage",
                     "eteindre": "Extinction", "verrouiller": "Verrouillage"},
        "statut_demarrage": "démarrage…",
        "statut_ecoute": "à l'écoute ({micro})",
        "statut_reconnexion": "reconnexion au micro…",
        "statut_micro_ko": "micro indisponible, nouvel essai…",
        "statut_telechargement": "téléchargement du modèle vocal… {p} %",
        "statut_installation": "installation du modèle vocal…",
        "statut_pas_internet": "pas d'internet pour télécharger le modèle, nouvel essai dans 1 min",
        "statut_chargement": "chargement du modèle vocal…",
        "statut_erreur": "erreur, regarde le journal",
        "notif_premier_dl": "Je télécharge le modèle vocal ({langue}, ~40 Mo). Ça prend une minute.",
        "notif_dl_ko": "Impossible de télécharger le modèle vocal. Vérifie ta connexion : "
                       "je réessaie toutes les minutes.",
        "notif_pret": "Prêt ! Dis « {r}, arrête-toi » ou « {r}, mets-toi en veille ». "
                      "Clic droit sur l'icône pour le menu.",
        "notif_installe": "Installé ! Je me lancerai à chaque démarrage de Windows "
                          "(décochable dans le menu de l'icône).",
        "deja_lance": "VoxOff est déjà lancé : son icône est près de l'horloge "
                      "(clic droit dessus pour le menu).",
        "suffixe_test": " (mode test)",
        "menu_etat": "État : {s}",
        "menu_test": "Mode test (rien n'est vraiment fait)",
        "menu_demarrage": "Lancer au démarrage de Windows",
        "menu_phrases": "Phrases reconnues…",
        "menu_reglages": "Réglages (langue, mot d'appel, micro, délais)…",
        "menu_journal": "Ouvrir le journal",
        "menu_quitter": "Quitter",
        "rebours_test": "MODE TEST : rien ne sera vraiment fait",
        "rebours_titre": "{action} dans {n} s",
        "rebours_aide": "Dis « {r}, annule » ou clique sur Annuler.",
        "bouton_annuler": "Annuler",
        "bouton_maintenant": "Maintenant",
        "test_titre": "VoxOff : mode test",
        "test_explication": "Parle : ce que le micro comprend s'affiche ici.\n"
                            "Les commandes sont simulées, rien n'est vraiment éteint.",
        "test_terminer": "Terminer le test",
        "ligne_entendu": "entendu : « {t} »",
        "ligne_compris": "✔ compris : {a}",
        "ligne_rien": "   (rien à annuler)",
        "ligne_annule": "   annulé.",
        "ligne_aurait": "   → ici j'aurais lancé : {a}",
        "aide": "Phrases reconnues :\n\n"
                "« {r}, arrête-toi »  (ou « éteins-toi »)\n"
                "« {r}, mets-toi en veille »\n"
                "« {r}, redémarre »\n"
                "« {r}, verrouille-toi »\n"
                "« {r}, annule »\n\n"
                "Pour changer de langue, de mot d'appel, de micro ou de délais : clic droit "
                "sur l'icône, puis « Réglages ».\n\nÉtat : {s}\nVersion {v}",
    },
    "en": {
        "libelles": {"annuler": "Cancel", "veille": "Sleep", "redemarrer": "Restart",
                     "eteindre": "Shutdown", "verrouiller": "Lock"},
        "statut_demarrage": "starting…",
        "statut_ecoute": "listening ({micro})",
        "statut_reconnexion": "reconnecting to the microphone…",
        "statut_micro_ko": "microphone unavailable, retrying…",
        "statut_telechargement": "downloading the voice model… {p}%",
        "statut_installation": "installing the voice model…",
        "statut_pas_internet": "no internet to download the voice model, retrying in 1 min",
        "statut_chargement": "loading the voice model…",
        "statut_erreur": "error, see the log",
        "notif_premier_dl": "Downloading the voice model ({langue}, ~40 MB). This takes about a minute.",
        "notif_dl_ko": "Couldn't download the voice model. Check your connection: "
                       "I'll retry every minute.",
        "notif_pret": "Ready! Say “{r}, shut down” or “{r}, go to sleep”. "
                      "Right-click the icon for the menu.",
        "notif_installe": "Installed! I'll start with Windows (you can turn this off in the icon's menu).",
        "deja_lance": "VoxOff is already running: its icon is next to the clock "
                      "(right-click it for the menu).",
        "suffixe_test": " (test mode)",
        "menu_etat": "Status: {s}",
        "menu_test": "Test mode (nothing is really done)",
        "menu_demarrage": "Start with Windows",
        "menu_phrases": "Voice commands…",
        "menu_reglages": "Settings (language, wake word, microphone, delays)…",
        "menu_journal": "Open the log",
        "menu_quitter": "Quit",
        "rebours_test": "TEST MODE: nothing will really happen",
        "rebours_titre": "{action} in {n} s",
        "rebours_aide": "Say “{r}, cancel” or click Cancel.",
        "bouton_annuler": "Cancel",
        "bouton_maintenant": "Now",
        "test_titre": "VoxOff: test mode",
        "test_explication": "Speak: what the microphone hears shows up here.\n"
                            "Commands are simulated, nothing is really turned off.",
        "test_terminer": "End test",
        "ligne_entendu": "heard: “{t}”",
        "ligne_compris": "✔ understood: {a}",
        "ligne_rien": "   (nothing to cancel)",
        "ligne_annule": "   cancelled.",
        "ligne_aurait": "   → this would have run: {a}",
        "aide": "Voice commands:\n\n"
                "“{r}, shut down”\n"
                "“{r}, go to sleep”\n"
                "“{r}, restart”\n"
                "“{r}, lock”\n"
                "“{r}, cancel”\n\n"
                "To change the language, wake word, microphone or delays: right-click the "
                "icon, then “Settings”.\n\nStatus: {s}\nVersion {v}",
    },
}

MODELES_REGLAGES = {
    "fr": """\
; ================================================================
;  Réglages de VoxOff
;  Modifie, puis enregistre (Ctrl+S) : c'est pris en compte tout
;  seul en quelques secondes, sans redémarrer le programme.
; ================================================================
[reglages]

; Langue des commandes vocales et des menus : fr (français) ou en (anglais).
langue = fr

; Mot(s) d'appel dit(s) au début de chaque phrase, séparés par des
; virgules, un seul mot chacun. Vide = « ordinateur » en français,
; « computer » en anglais. Tu peux mettre un prénom : choisis-en un
; courant, car le modèle vocal ne connaît que les mots de son
; dictionnaire. Astuce : en mode test, regarde comment il est compris
; et ajoute cette variante à la liste.
mots_appel =

; Morceau du nom du micro à utiliser (ex. : C920, Webcam, Usb Audio).
; Laisse vide pour la détection automatique.
micro =

; Secondes pour annuler une extinction ou un redémarrage.
delai_extinction = 15

; Secondes avant la mise en veille.
delai_veille = 3

; Sons : pour utiliser les tiens, place des fichiers WAV nommés
; eteindre.wav, veille.wav, redemarrer.wav, verrouiller.wav et
; annuler.wav dans le dossier « sons », à côté de ce fichier.
""",
    "en": """\
; ================================================================
;  VoxOff settings
;  Edit, then save (Ctrl+S): changes apply automatically within a
;  few seconds, no restart needed.
; ================================================================
[settings]

; Language for voice commands and menus: en (English) or fr (French).
language = en

; Wake word(s) said at the start of each command, comma-separated,
; one word each. Empty = "computer" in English, "ordinateur" in French.
; You can use a first name: pick a common one, as the voice model only
; knows the words in its dictionary. Tip: in test mode, check how it is
; understood and add that variant to the list.
wake_words =

; Part of the microphone's name (e.g. C920, Webcam, Usb Audio).
; Leave empty for automatic detection.
microphone =

; Seconds to cancel a shutdown or restart.
shutdown_delay = 15

; Seconds before going to sleep.
sleep_delay = 3

; Sounds: to use your own, put WAV files named eteindre.wav (shutdown),
; veille.wav (sleep), redemarrer.wav (restart), verrouiller.wav (lock)
; and annuler.wav (cancel) in a "sons" folder next to this file.
""",
}

SONS_DE_SECOURS = {"eteindre": (988, 784, 523), "veille": (784, 523), "redemarrer": (523, 784, 1047),
                   "verrouiller": (1047, 1047), "annuler": (440, 330)}
MOTS_WEBCAM = ("cam", "brio", "c920", "c922", "c925", "c930", "c270", "c310",
               "kiyo", "obsbot", "emeet", "insta360")
COULEURS = {"ecoute": "#2E7D32", "test": "#E67E22", "probleme": "#8A8A8A"}

NOM_VERROU = "Local\\VoxOff-Appli"
CLE_DEMARRAGE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_DEMARRAGE = "VoxOff"

log = logging.getLogger("voxoff")
VERROU = None
REGLAGES = None   # réglages en cours, pour la langue de l'interface

# ------------------------------------------------------------ API Windows
if sys.platform == "win32":
    import ctypes
    import winreg
    import winsound
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenMutexW.restype = wintypes.HANDLE
    k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenEventW.restype = wintypes.HANDLE
    k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.SetEvent.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    u32 = ctypes.WinDLL("user32")
    u32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]

    powrprof = ctypes.WinDLL("powrprof")
    powrprof.SetSuspendState.argtypes = [wintypes.BOOLEAN, wintypes.BOOLEAN, wintypes.BOOLEAN]

    ERROR_ALREADY_EXISTS = 183
    SYNCHRONIZE = 0x00100000
    EVENT_MODIFY_STATE = 0x0002
    SANS_FENETRE = subprocess.CREATE_NO_WINDOW


def t(cle, **valeurs):
    """Texte de l'interface dans la langue choisie."""
    langue = REGLAGES.langue if REGLAGES else "fr"
    texte = TEXTES[langue][cle]
    return texte.format(**valeurs) if valeurs else texte


def libelle(nom):
    langue = REGLAGES.langue if REGLAGES else "fr"
    return TEXTES[langue]["libelles"][nom]


# ------------------------------------------------------- reconnaissance
def normaliser(texte):
    """Minuscules, sans accents ni apostrophes, découpé en mots."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    for c in "'’-,.!?":
        texte = texte.replace(c, " ")
    return texte.split()


def trouver_commande(mots, commandes):
    """Cherche une commande dans les premiers mots (après le mot d'appel)."""
    for nom, motifs in commandes.items():
        for motif in motifs:
            for i in range(min(len(mots), FENETRE_ACTION)):
                morceau = mots[i:i + len(motif)]
                if len(morceau) == len(motif) and all(m.startswith(p) for m, p in zip(morceau, motif)):
                    return nom
    return None


class Detecteur:
    """Repère « <mot d'appel>, <ordre> » au début d'une phrase.

    Une phrase où « ordinateur » n'est pas en tête (« j'ai éteint l'ordinateur »)
    ne déclenche rien."""

    def __init__(self, reglages):
        self.reglages = reglages

    def analyser(self, mots, maintenant=None):
        """Renvoie ("commande", nom) ou (None, None)."""
        conf = LANGUES[self.reglages.langue]
        appel = set(self.reglages.mots_appel)
        debut = None
        for i, mot in enumerate(mots[:3]):
            if mot in appel:
                debut = i + 1
                break
            if mot not in conf["remplissage"]:
                break

        if debut is None:
            return None, None
        nom = trouver_commande(mots[debut:], conf["commandes"])
        return ("commande", nom) if nom else (None, None)


# --------------------------------------------------------------- réglages
def langue_systeme():
    try:
        return "fr" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x0C else "en"
    except Exception:
        return "fr"


class Reglages:
    def __init__(self):
        self.langue = "fr"
        self.mots_appel_perso = []
        self.micro = ""
        self.delai_extinction = 15
        self.delai_veille = 3
        self.premier_lancement = False
        self._date_fichier = None

    @property
    def mots_appel(self):
        return self.mots_appel_perso or LANGUES[self.langue]["appel"]

    @property
    def mot_affiche(self):
        return self.mots_appel[0].capitalize()

    def charger(self):
        """(Re)lit le fichier de réglages. Renvoie True s'il a changé."""
        if not FICHIER_REGLAGES.exists():
            DONNEES.mkdir(parents=True, exist_ok=True)
            FICHIER_REGLAGES.write_text(MODELES_REGLAGES[langue_systeme()], encoding="utf-8")
            self.premier_lancement = True
        date = FICHIER_REGLAGES.stat().st_mtime
        if date == self._date_fichier:
            return False
        self._date_fichier = date
        try:
            cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
            cp.read(FICHIER_REGLAGES, encoding="utf-8-sig")
            s = cp["reglages"] if cp.has_section("reglages") else cp["settings"]

            def lire(*cles, defaut=""):
                for cle in cles:
                    if cle in s:
                        return s.get(cle, "").strip()
                return defaut

            def entier(defaut, *cles):
                try:
                    return max(0, min(300, int(lire(*cles, defaut=str(defaut)) or defaut)))
                except ValueError:
                    return defaut

            langue = lire("langue", "language", defaut="fr").lower()[:2]
            self.langue = langue if langue in LANGUES else "fr"
            mots = [normaliser(m) for m in lire("mots_appel", "wake_words").split(",")]
            self.mots_appel_perso = [m[0] for m in mots if m]
            self.micro = lire("micro", "microphone")
            self.delai_extinction = entier(15, "delai_extinction", "shutdown_delay")
            self.delai_veille = entier(3, "delai_veille", "sleep_delay")
        except Exception as e:
            log.warning("Fichier de réglages illisible (%s) : je garde les réglages précédents.", e)
            return False
        return True


# ----------------------------------------------------------------- sons
def chemin_ressource(relatif):
    """Fichier embarqué dans le .exe (ou à côté du script)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relatif


def fichier_son(nom):
    for dossier in (DOSSIER_SONS_PERSO, chemin_ressource("sons")):
        fichier = dossier / f"{nom}.wav"
        if fichier.is_file():
            return fichier
    return None


@functools.lru_cache(maxsize=None)
def son(frequences, duree_ms=130):
    """Fabrique en mémoire un petit carillon WAV (une note par fréquence)."""
    taux = 44100
    echantillons = bytearray()
    for f in frequences:
        n = int(taux * duree_ms / 1000)
        for i in range(n):
            enveloppe = min(1.0, i / 300, (n - i) / 300)  # fondu : pas de « clic »
            echantillons += struct.pack("<h", int(14000 * enveloppe * math.sin(2 * math.pi * f * i / taux)))
    tampon = io.BytesIO()
    with wave.open(tampon, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taux)
        w.writeframes(bytes(echantillons))
    return tampon.getvalue()


def duree_son(nom):
    """Durée en secondes du son d'une action (0 si pas de fichier)."""
    fichier = fichier_son(nom)
    try:
        with wave.open(str(fichier)) as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


def jouer_son(nom):
    """Joue un son par les haut-parleurs : celui de l'utilisateur, celui fourni, ou un carillon."""
    fichier = fichier_son(nom)
    if fichier:
        try:
            winsound.PlaySound(str(fichier), winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_NODEFAULT)
            return
        except Exception:
            log.debug("Son %s illisible", fichier, exc_info=True)

    def carillon():
        try:
            winsound.PlaySound(son(SONS_DE_SECOURS[nom]), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass
    threading.Thread(target=carillon, daemon=True).start()


# ---------------------------------------------------------------- icône
def dessiner_icone(etat_icone, taille=64):
    """Dessine l'icône : un symbole « marche/arrêt » dont la barre est un micro."""
    from PIL import Image, ImageDraw
    e = taille / 64
    img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((1 * e, 1 * e, 63 * e, 63 * e), fill=COULEURS[etat_icone])
    blanc = (255, 255, 255, 255)
    trait = max(2, round(5.5 * e))
    d.arc((14 * e, 16 * e, 50 * e, 52 * e), start=-55, end=235, fill=blanc, width=trait)
    d.rounded_rectangle((27 * e, 9 * e, 37 * e, 35 * e), radius=5 * e, fill=blanc)
    return img


# ----------------------------------------------------------------- état
class Etat:
    """État partagé entre l'écoute, l'icône et les fenêtres."""

    def __init__(self, reglages):
        self.reglages = reglages
        self.statut_cle, self.statut_valeurs = "statut_demarrage", {}
        self.probleme = False
        self.test = False
        self.arret = threading.Event()
        self.ui = queue.Queue()      # messages pour les fenêtres (fil principal)
        self.icone = None

    @property
    def statut(self):
        return t(self.statut_cle, **self.statut_valeurs)

    def rafraichir(self):
        if not self.icone:
            return
        cle = "probleme" if self.probleme else ("test" if self.test else "ecoute")
        try:
            self.icone.icon = dessiner_icone(cle)
            suffixe = t("suffixe_test") if self.test else ""
            self.icone.title = f"{NOM_APPLI}{suffixe} : {self.statut}"[:120]
            self.icone.update_menu()
        except Exception:
            log.debug("Mise à jour de l'icône impossible", exc_info=True)

    def definir_statut(self, cle, probleme=False, **valeurs):
        self.statut_cle, self.statut_valeurs, self.probleme = cle, valeurs, probleme
        self.rafraichir()

    def definir_test(self, actif):
        self.test = actif
        log.info("Mode test %s.", "activé" if actif else "désactivé")
        self.ui.put(("test", actif))
        self.rafraichir()

    def notifier(self, message):
        try:
            if self.icone:
                self.icone.notify(message, NOM_APPLI)
        except Exception:
            pass

    def ligne_test(self, texte):
        if self.test:
            self.ui.put(("ligne", texte))


# ------------------------------------------------------------- actions
def action_systeme(nom):
    # Pas de /f : si un logiciel a un document non enregistré, Windows te
    # laisse la main au lieu de tout fermer de force.
    if nom == "eteindre":
        subprocess.run(["shutdown", "/s", "/t", "0"], creationflags=SANS_FENETRE)
    elif nom == "redemarrer":
        subprocess.run(["shutdown", "/r", "/t", "0"], creationflags=SANS_FENETRE)
    elif nom == "veille":
        powrprof.SetSuspendState(False, False, False)
    elif nom == "verrouiller":
        u32.LockWorkStation()


class Gestionnaire:
    """Reçoit les commandes reconnues et les exécute, avec compte à rebours si besoin."""

    def __init__(self, etat):
        self.etat = etat
        self.annulation = threading.Event()
        self.tout_de_suite = threading.Event()
        self.en_cours = None
        self.fin = 0.0
        self.derniere = 0.0

    def annuler(self):
        if self.en_cours:
            self.annulation.set()
            return True
        return False

    def recevoir(self, nom):
        if nom == "arreter":
            nom = "annuler" if self.en_cours else "eteindre"
        maintenant = time.monotonic()
        if nom != "annuler" and maintenant - self.derniere < 3:
            return
        self.derniere = maintenant
        test = self.etat.test
        log.info(">> Compris : %s%s", LIBELLES_JOURNAL[nom], "   [mode test]" if test else "")
        self.etat.ligne_test(t("ligne_compris", a=libelle(nom).lower()))

        if nom == "annuler":
            if not self.annuler():
                self.etat.ligne_test(t("ligne_rien"))
            return
        if self.en_cours:
            log.info("   (une action attend déjà)")
            return

        jouer_son(nom)  # chaque action a son propre son
        if nom == "verrouiller":
            self._executer(nom)
            return

        r = self.etat.reglages
        delai = r.delai_veille if nom == "veille" else r.delai_extinction
        if nom == "veille":
            delai = max(delai, math.ceil(duree_son("veille")))  # le son va jusqu'au bout
        self.annulation.clear()
        self.tout_de_suite.clear()
        self.fin = time.monotonic() + delai
        self.en_cours = nom
        if delai > 0:
            self.etat.ui.put(("rebours", nom))
        threading.Thread(target=self._compte_a_rebours, args=(nom,), daemon=True).start()

    def _compte_a_rebours(self, nom):
        while time.monotonic() < self.fin and not self.tout_de_suite.is_set():
            if self.annulation.wait(0.2):
                self.en_cours = None
                log.info("   Annulé.")
                self.etat.ligne_test(t("ligne_annule"))
                jouer_son("annuler")
                return
        self.en_cours = None
        self._executer(nom)

    def _executer(self, nom):
        if self.etat.test:
            log.info("   [mode test] ici j'aurais lancé : %s", LIBELLES_JOURNAL[nom].lower())
            self.etat.ligne_test(t("ligne_aurait", a=libelle(nom).lower()))
            return
        log.info("   C'est parti : %s", LIBELLES_JOURNAL[nom].lower())
        try:
            action_systeme(nom)
        except Exception as e:
            log.error("   Échec : %s", e)


# ---------------------------------------------------------------- micro
_prevenu_micro = False


def micros_candidats(micro_voulu):
    """Micros à essayer, dans l'ordre : la webcam (ou celui des réglages), puis celui par défaut."""
    global _prevenu_micro
    import sounddevice as sd
    apis = sd.query_hostapis()

    def api(d):
        return apis[d["hostapi"]]["name"]

    entrees = [(i, d) for i, d in enumerate(sd.query_devices())
               if d["max_input_channels"] > 0 and "WDM-KS" not in api(d)]
    cles = [micro_voulu.lower()] if micro_voulu else list(MOTS_WEBCAM)
    trouves = [(i, d) for i, d in entrees if any(c in d["name"].lower() for c in cles)]
    priorite = {"MME": 0, "Windows DirectSound": 1, "Windows WASAPI": 2}
    trouves.sort(key=lambda x: priorite.get(api(x[1]), 9))

    if not trouves and not _prevenu_micro:
        _prevenu_micro = True
        if micro_voulu:
            log.warning("Micro « %s » introuvable : j'utilise le micro par défaut de Windows.", micro_voulu)
        else:
            log.info("Micro de la webcam pas reconnu par son nom : j'utilise le micro par défaut de Windows.")
    try:
        trouves.append((None, sd.query_devices(kind="input")))
    except Exception:
        pass
    return trouves


def ouvrir_micro(micro_voulu, rappel):
    import sounddevice as sd
    for index, info in micros_candidats(micro_voulu):
        debit = int(info["default_samplerate"])
        try:
            flux = sd.RawInputStream(samplerate=debit, blocksize=debit // 4, device=index,
                                     dtype="int16", channels=1, callback=rappel)
            flux.start()
            return flux, info["name"], debit
        except Exception as e:
            log.debug("Impossible d'ouvrir %s : %s", info["name"], e)
    raise RuntimeError("aucun micro utilisable")


class Reconnexion(Exception):
    """Le micro doit être rouvert, après une pause de `pause` secondes."""

    def __init__(self, raison, pause):
        super().__init__(raison)
        self.pause = pause


def pause_avant_reconnexion(etat, secondes):
    """Attend avant de rouvrir le micro. Si le PC s'est endormi pendant l'attente,
    on laisse en plus à la webcam le temps de se réveiller : la rouvrir trop tôt
    donne un micro « fantôme » qui ne renvoie que du silence."""
    debut = time.time()
    etat.arret.wait(secondes)
    if time.time() - debut > secondes + PAUSE_ENDORMI:
        log.info("Sortie de veille détectée : j'attends que la webcam se réveille…")
        etat.arret.wait(DELAI_REVEIL_WEBCAM)


def ecouter(modele, etat, gestionnaire, langue):
    """Écoute jusqu'à l'arrêt (renvoie None) ou un changement de langue (renvoie "langue")."""
    import sounddevice as sd
    from vosk import KaldiRecognizer

    reglages = etat.reglages
    detecteur = Detecteur(reglages)
    pause = 0
    silence_tolere = SILENCE_SUSPECT
    while not etat.arret.is_set():
        if pause:
            pause_avant_reconnexion(etat, pause)
            if etat.arret.is_set():
                break
        flux = None
        # Heure murale du dernier tour de boucle : un grand saut veut dire que le
        # programme était figé, donc que le PC dormait (même pendant l'ouverture du micro).
        t_prec = time.time()
        try:
            # Recharge la liste des périphériques (indispensable après une veille
            # ou si la webcam a été débranchée puis rebranchée).
            sd._terminate()
            sd._initialize()
            file_audio = queue.Queue()
            micro_voulu = reglages.micro
            flux, nom_micro, debit = ouvrir_micro(micro_voulu, lambda data, *_: file_audio.put(bytes(data)))
            reco = KaldiRecognizer(modele, debit)
            log.info("À l'écoute sur : %s", nom_micro)
            etat.definir_statut("statut_ecoute", micro=nom_micro)

            derniere_donnee = derniere_vie = derniere_verif = time.time()
            while not etat.arret.is_set():
                try:
                    bloc = file_audio.get(timeout=0.5)
                except queue.Empty:
                    bloc = None

                maintenant = time.time()
                if maintenant - t_prec > PAUSE_ENDORMI:
                    raise Reconnexion("Sortie de veille détectée", DELAI_REVEIL_WEBCAM)
                t_prec = maintenant

                if maintenant - derniere_verif > 2:
                    derniere_verif = maintenant
                    if reglages.charger():
                        log.info("Réglages rechargés (langue : %s, mot d'appel : %s).",
                                 reglages.langue, reglages.mot_affiche)
                        etat.rafraichir()
                        if reglages.langue != langue:
                            return "langue"
                        if reglages.micro != micro_voulu:
                            raise Reconnexion("Nouveau micro choisi dans les réglages", 0)

                if bloc is None:
                    if maintenant - derniere_donnee > 5:
                        raise Reconnexion("Le micro ne renvoie plus de son", 3)
                    continue
                derniere_donnee = maintenant

                # Un vrai micro a toujours un léger souffle ; un signal parfaitement
                # plat veut dire que le micro est « mort » : on le rouvre.
                echantillons = array.array("h", bloc)
                if echantillons and max(echantillons) != min(echantillons):
                    derniere_vie = maintenant
                    silence_tolere = SILENCE_SUSPECT
                elif maintenant - derniere_vie > silence_tolere:
                    silence_tolere = min(silence_tolere * 2, 600)
                    raise Reconnexion("Le micro ne renvoie qu'un silence parfait", 1)

                if reco.AcceptWaveform(bloc):
                    texte = json.loads(reco.Result()).get("text", "")
                    if texte:
                        etat.ligne_test(t("ligne_entendu", t=texte))
                        quoi, nom = detecteur.analyser(normaliser(texte))
                        if quoi == "commande":
                            gestionnaire.recevoir(nom)
        except Reconnexion as r:
            log.info("%s : je me reconnecte au micro…", r)
            etat.definir_statut("statut_reconnexion")
            pause = r.pause
        except Exception as e:
            log.warning("Souci avec le micro : %s. Nouvel essai dans 5 s…", e)
            etat.definir_statut("statut_micro_ko", probleme=True)
            pause = 5
        finally:
            if flux is not None:
                try:
                    flux.close()
                except Exception:
                    pass
    return None


# --------------------------------------------------------------- modèle
def telecharger_modele(etat, langue):
    import urllib.request

    DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    zip_tmp = DOSSIER_MODELES / f"{langue}.zip"
    dossier_tmp = DOSSIER_MODELES / f"{langue}_en_cours"
    destination = DOSSIER_MODELES / langue
    dernier = [-1]

    def progression(n, taille_bloc, total):
        if total > 0:
            pourcent = min(100, n * taille_bloc * 100 // total)
            if pourcent // 5 != dernier[0]:
                dernier[0] = pourcent // 5
                etat.definir_statut("statut_telechargement", p=pourcent)

    urllib.request.urlretrieve(MODELES[langue], zip_tmp, progression)
    etat.definir_statut("statut_installation")
    shutil.rmtree(dossier_tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_tmp) as z:
        z.extractall(dossier_tmp)
    contenu = [p for p in dossier_tmp.iterdir() if p.is_dir()]
    source = contenu[0] if len(contenu) == 1 else dossier_tmp
    shutil.rmtree(destination, ignore_errors=True)
    shutil.move(str(source), str(destination))
    shutil.rmtree(dossier_tmp, ignore_errors=True)
    zip_tmp.unlink(missing_ok=True)


def preparer_modele(etat, langue):
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    dossier = DOSSIER_MODELES / langue
    prevenu = False
    while not dossier.is_dir() and not etat.arret.is_set():
        if not prevenu:
            log.info("Téléchargement du modèle vocal (%s, ~40 Mo)…", langue)
            etat.notifier(t("notif_premier_dl", langue=LANGUES[langue]["nom"]))
        try:
            telecharger_modele(etat, langue)
            log.info("Modèle vocal installé.")
        except Exception as e:
            log.error("Téléchargement du modèle impossible : %s", e)
            etat.definir_statut("statut_pas_internet", probleme=True)
            if not prevenu:
                etat.notifier(t("notif_dl_ko"))
            prevenu = True
            etat.arret.wait(60)
        prevenu = True
    if etat.arret.is_set():
        return None
    etat.definir_statut("statut_chargement")
    return Model(str(dossier))


def moteur(etat, gestionnaire, annoncer):
    """Fil d'écoute : prépare le modèle de la langue choisie puis écoute."""
    try:
        while not etat.arret.is_set():
            langue = etat.reglages.langue
            modele = preparer_modele(etat, langue)
            if modele is None:
                return
            if annoncer:
                r = etat.reglages.mot_affiche
                etat.notifier(t("notif_pret", r=r))
                annoncer = False
            if ecouter(modele, etat, gestionnaire, langue) == "langue":
                log.info("Nouvelle langue : %s.", etat.reglages.langue)
                annoncer = True
                continue
            return
    except Exception:
        log.error("Erreur inattendue :\n%s", traceback.format_exc())
        etat.definir_statut("statut_erreur", probleme=True)


# ------------------------------------------------- démarrage automatique
def commande_demarrage():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --demarrage'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreteur = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreteur}" "{Path(__file__).resolve()}" --demarrage'


def demarrage_actif():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE) as cle:
            return winreg.QueryValueEx(cle, NOM_DEMARRAGE)[0] == commande_demarrage()
    except OSError:
        return False


def supprimer_valeur_demarrage(nom):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE, 0, winreg.KEY_SET_VALUE) as cle:
            winreg.DeleteValue(cle, nom)
        return True
    except OSError:
        return False


def definir_demarrage(actif):
    try:
        if actif:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE, 0, winreg.KEY_SET_VALUE) as cle:
                winreg.SetValueEx(cle, NOM_DEMARRAGE, 0, winreg.REG_SZ, commande_demarrage())
        else:
            supprimer_valeur_demarrage(NOM_DEMARRAGE)
        log.info("Lancement au démarrage de Windows %s.", "activé" if actif else "désactivé")
    except OSError as e:
        log.error("Impossible de modifier le lancement au démarrage : %s", e)


def migrer_anciennes_versions():
    """Remplace proprement « Claude vocal », l'ancien nom de VoxOff."""
    appdata_local = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    ancien = appdata_local / "ClaudeVocal"

    # Version 2 (ClaudeVocal.exe) : on l'arrête et on retire son lancement automatique.
    h = k32.OpenMutexW(SYNCHRONIZE, False, "Local\\ClaudeVocal-Appli")
    if h:
        k32.CloseHandle(h)
        subprocess.run(["taskkill", "/F", "/IM", "ClaudeVocal.exe"], capture_output=True,
                       creationflags=SANS_FENETRE)
        log.info("Ancienne version (Claude vocal 2) arrêtée.")
        time.sleep(1)
    if supprimer_valeur_demarrage("ClaudeVocal"):
        log.info("Ancien lancement automatique (Claude vocal) retiré.")

    # Version 1 (script + fichiers .bat).
    h = k32.OpenEventW(EVENT_MODIFY_STATE, False, "Local\\ClaudeVocal-Arret")
    if h:
        k32.SetEvent(h)
        k32.CloseHandle(h)
        log.info("Ancienne version (Claude vocal 1) arrêtée.")
    raccourci = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" /
                 "Programs" / "Startup" / "Claude vocal.lnk")
    try:
        raccourci.unlink(missing_ok=True)
    except OSError:
        pass

    # On récupère le modèle français déjà téléchargé, puis on range.
    if ancien.is_dir():
        try:
            if (ancien / "modele").is_dir() and not (DOSSIER_MODELES / "fr").exists():
                DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
                shutil.move(str(ancien / "modele"), str(DOSSIER_MODELES / "fr"))
                log.info("Modèle français récupéré de Claude vocal.")
        except OSError as e:
            log.warning("Modèle de Claude vocal non récupéré : %s", e)
        shutil.rmtree(ancien, ignore_errors=True)


# -------------------------------------------------------------- fenêtres
class Interface:
    """Fenêtres (compte à rebours, mode test, aide). Tourne dans le fil principal."""

    POLICE = "Segoe UI"

    def __init__(self, etat, gestionnaire):
        import tkinter as tk
        self.tk = tk
        self.etat = etat
        self.g = gestionnaire
        self.racine = tk.Tk()
        self.racine.withdraw()
        self.racine.title(NOM_APPLI)
        self.fenetre_rebours = None
        self.fenetre_test = None
        self.zone_test = None
        self.racine.after(100, self._pomper)

    def lancer(self):
        self.racine.mainloop()

    def _pomper(self):
        try:
            while True:
                self._traiter(*self.etat.ui.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            log.error("Erreur d'affichage :\n%s", traceback.format_exc())
        self.racine.after(100, self._pomper)

    def _traiter(self, quoi, *args):
        if quoi == "rebours":
            self._ouvrir_rebours(args[0])
        elif quoi == "test":
            self._ouvrir_test() if args[0] else self._fermer_test()
        elif quoi == "ligne":
            self._ajouter_ligne(args[0])
        elif quoi == "aide":
            self._aide()
        elif quoi == "quitter":
            self.racine.quit()

    def _placer(self, f, hauteur=3):
        f.update_idletasks()
        x = (f.winfo_screenwidth() - f.winfo_width()) // 2
        y = (f.winfo_screenheight() - f.winfo_height()) // hauteur
        f.geometry(f"+{x}+{y}")
        f.lift()
        f.attributes("-topmost", True)
        f.focus_force()

    # --- compte à rebours
    def _ouvrir_rebours(self, nom):
        tk = self.tk
        if self.fenetre_rebours is not None:
            self.fenetre_rebours.destroy()
        f = tk.Toplevel(self.racine)
        self.fenetre_rebours = f
        f.title(NOM_APPLI)
        f.resizable(False, False)
        f.protocol("WM_DELETE_WINDOW", self.g.annuler)
        cadre = tk.Frame(f, padx=28, pady=20)
        cadre.pack()
        if self.etat.test:
            tk.Label(cadre, text=t("rebours_test"), fg=COULEURS["test"],
                     font=(self.POLICE, 9, "bold")).pack(pady=(0, 8))
        titre = tk.Label(cadre, font=(self.POLICE, 15, "bold"))
        titre.pack()
        tk.Label(cadre, text=t("rebours_aide", r=self.etat.reglages.mot_affiche),
                 font=(self.POLICE, 10)).pack(pady=(8, 16))
        boutons = tk.Frame(cadre)
        boutons.pack()
        tk.Button(boutons, text=t("bouton_annuler"), width=12, font=(self.POLICE, 10),
                  command=self.g.annuler).pack(side="left", padx=6)
        tk.Button(boutons, text=t("bouton_maintenant"), width=12, font=(self.POLICE, 10),
                  command=self.g.tout_de_suite.set).pack(side="left", padx=6)

        def rafraichir():
            if self.fenetre_rebours is not f:
                return
            if self.g.en_cours != nom:
                f.destroy()
                self.fenetre_rebours = None
                return
            reste = max(0, math.ceil(self.g.fin - time.monotonic()))
            titre.config(text=t("rebours_titre", action=libelle(nom), n=reste))
            f.after(200, rafraichir)

        rafraichir()
        self._placer(f)

    # --- mode test
    def _ouvrir_test(self):
        tk = self.tk
        if self.fenetre_test is not None:
            self.fenetre_test.lift()
            return
        f = tk.Toplevel(self.racine)
        self.fenetre_test = f
        f.title(t("test_titre"))
        f.geometry("560x380")
        f.protocol("WM_DELETE_WINDOW", lambda: self.etat.definir_test(False))
        tk.Label(f, justify="left", padx=12, pady=10, font=(self.POLICE, 10),
                 text=t("test_explication")).pack(anchor="w")
        self.zone_test = tk.Text(f, height=14, state="disabled", wrap="word", font=("Consolas", 10))
        self.zone_test.pack(fill="both", expand=True, padx=12)
        tk.Button(f, text=t("test_terminer"), font=(self.POLICE, 10),
                  command=lambda: self.etat.definir_test(False)).pack(pady=10)
        self._placer(f, hauteur=4)
        f.attributes("-topmost", False)

    def _fermer_test(self):
        if self.fenetre_test is not None:
            self.fenetre_test.destroy()
        self.fenetre_test = self.zone_test = None

    def _ajouter_ligne(self, texte):
        if self.zone_test is None:
            return
        self.zone_test.config(state="normal")
        self.zone_test.insert("end", f"{time.strftime('%H:%M:%S')}  {texte}\n")
        self.zone_test.see("end")
        self.zone_test.config(state="disabled")

    # --- aide
    def _aide(self):
        from tkinter import messagebox
        messagebox.showinfo(
            NOM_APPLI,
            t("aide", r=self.etat.reglages.mot_affiche, s=self.etat.statut, v=VERSION),
            parent=self.racine)


# ------------------------------------------------------------------ menu
def creer_icone(etat):
    import pystray
    from pystray import Menu, MenuItem as Item

    def ouvrir_dans_bloc_notes(chemin):
        def action():
            if not chemin.exists():
                chemin.parent.mkdir(parents=True, exist_ok=True)
                chemin.touch()
            subprocess.Popen(["notepad.exe", str(chemin)])
        return action

    def quitter(icone):
        log.info("Arrêt demandé depuis le menu.")
        etat.arret.set()
        etat.ui.put(("quitter",))
        icone.stop()

    menu = Menu(
        Item(lambda i: t("menu_etat", s=etat.statut)[:90], None, enabled=False),
        Menu.SEPARATOR,
        Item(lambda i: t("menu_test"), lambda: etat.definir_test(not etat.test),
             checked=lambda i: etat.test),
        Item(lambda i: t("menu_demarrage"), lambda: definir_demarrage(not demarrage_actif()),
             checked=lambda i: demarrage_actif()),
        Menu.SEPARATOR,
        Item(lambda i: t("menu_phrases"), lambda: etat.ui.put(("aide",)), default=True),
        Item(lambda i: t("menu_reglages"), ouvrir_dans_bloc_notes(FICHIER_REGLAGES)),
        Item(lambda i: t("menu_journal"), ouvrir_dans_bloc_notes(JOURNAL)),
        Menu.SEPARATOR,
        Item(lambda i: t("menu_quitter"), quitter),
    )
    return pystray.Icon(NOM_DEMARRAGE, dessiner_icone("ecoute"), NOM_APPLI, menu)


# ----------------------------------------------------------------- divers
def configurer_journal():
    DONNEES.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    fichier = logging.handlers.RotatingFileHandler(JOURNAL, maxBytes=500_000, backupCount=1,
                                                   encoding="utf-8")
    fichier.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%d/%m %H:%M:%S"))
    log.addHandler(fichier)
    if sys.stdout is not None and sys.stdout.isatty():
        ecran = logging.StreamHandler(sys.stdout)
        ecran.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        log.addHandler(ecran)


def verifier(fichier):
    """Auto-test utilisé par le robot GitHub : tout doit se charger dans le .exe."""
    try:
        import importlib
        for module in ("PIL", "pystray", "sounddevice", "tkinter"):
            importlib.import_module(module)
        import vosk
        vosk.SetLogLevel(-1)  # charge libvosk.dll
        dessiner_icone("ecoute")
        son((880,))
        manquants = [n for n in SONS_DE_SECOURS if not (chemin_ressource("sons") / f"{n}.wav").is_file()]
        if manquants:
            raise RuntimeError(f"sons absents du .exe : {manquants}")

        class R:
            langue, mots_appel = "fr", ["ordinateur"]
        assert Detecteur(R).analyser(normaliser("Ordinateur, éteins-toi"), 0) == ("commande", "eteindre")
        Path(fichier).write_text(f"OK {VERSION}", encoding="utf-8")
        return 0
    except Exception:
        Path(fichier).write_text("ERREUR\n" + traceback.format_exc(), encoding="utf-8")
        return 1


def fabriquer_ico(chemin):
    tailles = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    dessiner_icone("ecoute", 256).save(chemin, sizes=tailles)
    return 0


def main():
    global VERROU, REGLAGES
    # Dans le .exe sans console, il n'y a pas de sortie : on évite tout plantage
    # d'une bibliothèque qui voudrait écrire un message.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    args = sys.argv[1:]
    if "--icone" in args:
        return fabriquer_ico(args[args.index("--icone") + 1])
    if "--verifier" in args:
        return verifier(args[args.index("--verifier") + 1])
    if sys.platform != "win32":
        print("VoxOff fonctionne sous Windows.")
        return 1

    configurer_journal()
    reglages = Reglages()
    REGLAGES = reglages
    reglages.charger()

    VERROU = k32.CreateMutexW(None, False, NOM_VERROU)  # gardé ouvert jusqu'à la fin
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        u32.MessageBoxW(None, t("deja_lance"), NOM_APPLI, 0x40)
        return 0

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # fenêtres nettes sur les grands écrans
    except Exception:
        pass

    log.info("Démarrage de VoxOff %s (langue : %s)", VERSION, reglages.langue)
    migrer_anciennes_versions()
    if reglages.premier_lancement:
        definir_demarrage(True)

    etat = Etat(reglages)
    gestionnaire = Gestionnaire(etat)
    interface = Interface(etat, gestionnaire)
    etat.icone = creer_icone(etat)
    annoncer = "--demarrage" not in args  # pas de notification à chaque démarrage de Windows

    def au_lancement(icone):
        icone.visible = True
        etat.rafraichir()
        if reglages.premier_lancement:
            etat.notifier(t("notif_installe"))
        threading.Thread(target=moteur, args=(etat, gestionnaire, annoncer), daemon=True).start()

    etat.icone.run_detached(au_lancement)
    try:
        interface.lancer()
    finally:
        etat.arret.set()
        try:
            etat.icone.stop()
        except Exception:
            pass
        log.info("VoxOff arrêté.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
