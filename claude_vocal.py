# -*- coding: utf-8 -*-
"""
Claude vocal : éteins, mets en veille, redémarre ou verrouille ton PC Windows à la voix.

Une icône près de l'horloge montre que l'écoute tourne (clic droit pour le menu).
La reconnaissance vocale (Vosk) fonctionne hors ligne : ta voix ne quitte jamais le PC.
Le seul accès à internet est le téléchargement du modèle français (~40 Mo) au
tout premier lancement.

Phrases (avec le prénom choisi dans les réglages, « Claude » par défaut) :
    « Claude, éteins l'ordinateur »           extinction, avec un délai pour annuler
    « Claude, mets en veille l'ordinateur »   mise en veille
    « Claude, redémarre l'ordinateur »        redémarrage, avec un délai pour annuler
    « Claude, verrouille l'ordinateur »       verrouillage de la session
    « Claude, annule »                        annule l'action en attente
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

VERSION = "2.0.0"
NOM_APPLI = "Claude vocal"
URL_MODELE = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip"

DONNEES = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ClaudeVocal"
DOSSIER_MODELE = DONNEES / "modele"
FICHIER_REGLAGES = DONNEES / "reglages.ini"
JOURNAL = DONNEES / "claude_vocal.log"

# Surveillance du micro (secondes)
PAUSE_ENDORMI = 10         # programme figé plus longtemps que ça = le PC dormait
DELAI_REVEIL_WEBCAM = 6    # temps laissé à la webcam pour se réveiller avant de la rouvrir
SILENCE_SUSPECT = 30       # signal parfaitement plat depuis ce temps = micro « mort »

# nom interne : (débuts de mots qui déclenchent, faut-il dire « l'ordinateur » ?)
# L'ordre compte : la première commande reconnue l'emporte.
COMMANDES = {
    "annuler": (("annul",), False),
    "veille": (("veille",), True),
    "redemarrer": (("redemar",), True),
    "eteindre": (("etein", "eteign"), True),
    "verrouiller": (("verrou",), True),
}
LIBELLES = {
    "annuler": "Annulation",
    "veille": "Mise en veille",
    "redemarrer": "Redémarrage",
    "eteindre": "Extinction",
    "verrouiller": "Verrouillage",
}
MOTS_CIBLE = {"ordinateur", "ordinateurs", "ordi", "pc"}
MOTS_WEBCAM = ("cam", "brio", "c920", "c922", "c925", "c930", "c270", "c310",
               "kiyo", "obsbot", "emeet", "insta360")

COULEURS = {"ecoute": "#2E7D32", "test": "#E67E22", "probleme": "#8A8A8A"}

NOM_VERROU = "Local\\ClaudeVocal-Appli"
ANCIEN_ARRET = "Local\\ClaudeVocal-Arret"          # première version (script + .bat)
CLE_DEMARRAGE = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM_DEMARRAGE = "ClaudeVocal"

MODELE_REGLAGES = """\
; ================================================================
;  Réglages de Claude vocal
;  Modifie, puis enregistre (Ctrl+S) : c'est pris en compte tout
;  seul en quelques secondes, sans redémarrer le programme.
; ================================================================
[reglages]

; Prénom(s) qui déclenchent les commandes, séparés par des virgules,
; un seul mot chacun. Le premier est celui affiché dans les messages.
; Choisis un prénom français courant : le modèle vocal ne connaît que
; les mots de son dictionnaire. Astuce : en mode test, regarde comment
; ton prénom est compris et ajoute cette variante à la liste.
prenoms = claude, clode, claud, clod

; Morceau du nom du micro à utiliser (ex. : C920, Webcam, Usb Audio).
; Laisse vide pour la détection automatique.
micro =

; Secondes pour annuler une extinction ou un redémarrage.
delai_extinction = 15

; Secondes avant la mise en veille.
delai_veille = 3
"""

log = logging.getLogger("claude_vocal")
VERROU = None

# ------------------------------------------------------------ API Windows
if sys.platform == "win32":
    import ctypes
    import winreg
    import winsound
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.OpenEventW.restype = wintypes.HANDLE
    k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k32.SetEvent.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    u32 = ctypes.WinDLL("user32")
    u32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]

    powrprof = ctypes.WinDLL("powrprof")
    powrprof.SetSuspendState.argtypes = [wintypes.BOOLEAN, wintypes.BOOLEAN, wintypes.BOOLEAN]

    ERROR_ALREADY_EXISTS = 183
    EVENT_MODIFY_STATE = 0x0002
    SANS_FENETRE = subprocess.CREATE_NO_WINDOW


# ------------------------------------------------------- reconnaissance
def normaliser(texte):
    """Minuscules, sans accents ni apostrophes, découpé en mots."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    for c in "'’-":
        texte = texte.replace(c, " ")
    return texte.split()


def detecter(mots, prenoms):
    """Renvoie le nom de la commande prononcée, ou None."""
    mots_set = set(mots)
    if not set(prenoms) & mots_set:
        return None
    for nom, (debuts, faut_cible) in COMMANDES.items():
        if any(m.startswith(d) for m in mots for d in debuts):
            if faut_cible and not MOTS_CIBLE & mots_set:
                continue
            return nom
    return None


# --------------------------------------------------------------- réglages
class Reglages:
    def __init__(self):
        self.prenoms = ["claude", "clode", "claud", "clod"]
        self.micro = ""
        self.delai_extinction = 15
        self.delai_veille = 3
        self.premier_lancement = False
        self._date_fichier = None

    @property
    def prenom(self):
        return self.prenoms[0].capitalize()

    def charger(self):
        """(Re)lit le fichier de réglages. Renvoie True s'il a changé."""
        if not FICHIER_REGLAGES.exists():
            DONNEES.mkdir(parents=True, exist_ok=True)
            FICHIER_REGLAGES.write_text(MODELE_REGLAGES, encoding="utf-8")
            self.premier_lancement = True
        date = FICHIER_REGLAGES.stat().st_mtime
        if date == self._date_fichier:
            return False
        self._date_fichier = date
        try:
            cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
            cp.read(FICHIER_REGLAGES, encoding="utf-8-sig")
            s = cp["reglages"]
            prenoms = [normaliser(p) for p in s.get("prenoms", "").split(",")]
            prenoms = [p[0] for p in prenoms if p]
            self.prenoms = prenoms or ["claude"]
            self.micro = s.get("micro", "").strip()
            self.delai_extinction = max(0, min(300, s.getint("delai_extinction", 15)))
            self.delai_veille = max(0, min(300, s.getint("delai_veille", 3)))
        except Exception as e:
            log.warning("Fichier de réglages illisible (%s) : je garde les réglages précédents.", e)
            return False
        return True


# ----------------------------------------------------------------- sons
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


def bip(*frequences):
    """Joue le carillon par les haut-parleurs (le « bip système » est souvent désactivé)."""
    def jouer():
        try:
            winsound.PlaySound(son(frequences), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            for f in frequences:
                try:
                    winsound.Beep(f, 140)
                except Exception:
                    pass
    threading.Thread(target=jouer, daemon=True).start()


# ---------------------------------------------------------------- icône
def dessiner_icone(etat_icone, taille=64):
    """Dessine l'icône : un micro blanc sur un rond de couleur."""
    from PIL import Image, ImageDraw
    e = taille / 64
    img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((1 * e, 1 * e, 63 * e, 63 * e), fill=COULEURS[etat_icone])
    blanc = (255, 255, 255, 255)
    trait = max(1, round(4 * e))
    d.rounded_rectangle((24 * e, 11 * e, 40 * e, 37 * e), radius=8 * e, fill=blanc)
    d.arc((17 * e, 18 * e, 47 * e, 45 * e), start=0, end=180, fill=blanc, width=trait)
    d.line((32 * e, 45 * e, 32 * e, 52 * e), fill=blanc, width=trait)
    d.line((23 * e, 53 * e, 41 * e, 53 * e), fill=blanc, width=trait)
    return img


# ----------------------------------------------------------------- état
class Etat:
    """État partagé entre l'écoute, l'icône et les fenêtres."""

    def __init__(self, reglages):
        self.reglages = reglages
        self.statut = "Démarrage…"
        self.probleme = False
        self.test = False
        self.arret = threading.Event()
        self.ui = queue.Queue()      # messages pour les fenêtres (fil principal)
        self.icone = None

    def rafraichir(self):
        if not self.icone:
            return
        cle = "probleme" if self.probleme else ("test" if self.test else "ecoute")
        try:
            self.icone.icon = dessiner_icone(cle)
            suffixe = " (mode test)" if self.test else ""
            self.icone.title = f"{NOM_APPLI}{suffixe} : {self.statut}"[:120]
            self.icone.update_menu()
        except Exception:
            log.debug("Mise à jour de l'icône impossible", exc_info=True)

    def definir_statut(self, texte, probleme=False):
        self.statut, self.probleme = texte, probleme
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
        maintenant = time.monotonic()
        if nom != "annuler" and maintenant - self.derniere < 3:
            return
        self.derniere = maintenant
        test = self.etat.test
        log.info(">> Compris : %s%s", LIBELLES[nom], "   [mode test]" if test else "")
        self.etat.ligne_test(f"✔ compris : {LIBELLES[nom].lower()}")

        if nom == "annuler":
            if not self.annuler():
                self.etat.ligne_test("   (rien à annuler)")
            return
        if self.en_cours:
            log.info("   (une action attend déjà)")
            return

        bip(880, 1320)
        if nom == "verrouiller":
            self._executer(nom)
            return

        r = self.etat.reglages
        delai = r.delai_veille if nom == "veille" else r.delai_extinction
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
                self.etat.ligne_test("   annulé.")
                bip(660, 440)
                return
        self.en_cours = None
        self._executer(nom)

    def _executer(self, nom):
        if self.etat.test:
            log.info("   [mode test] ici j'aurais lancé : %s", LIBELLES[nom].lower())
            self.etat.ligne_test(f"   → ici j'aurais lancé : {LIBELLES[nom].lower()}")
            bip(1320)
            return
        log.info("   C'est parti : %s", LIBELLES[nom].lower())
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


def ecouter(modele, etat, gestionnaire):
    import sounddevice as sd
    from vosk import KaldiRecognizer

    reglages = etat.reglages
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
            etat.definir_statut(f"à l'écoute ({nom_micro})")

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
                        log.info("Réglages rechargés (prénom : %s).", reglages.prenom)
                        etat.rafraichir()
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
                        etat.ligne_test(f"entendu : « {texte} »")
                        commande = detecter(normaliser(texte), reglages.prenoms)
                        if commande:
                            gestionnaire.recevoir(commande)
        except Reconnexion as r:
            log.info("%s : je me reconnecte au micro…", r)
            etat.definir_statut("reconnexion au micro…")
            pause = r.pause
        except Exception as e:
            log.warning("Souci avec le micro : %s. Nouvel essai dans 5 s…", e)
            etat.definir_statut("micro indisponible, nouvel essai…", probleme=True)
            pause = 5
        finally:
            if flux is not None:
                try:
                    flux.close()
                except Exception:
                    pass


# --------------------------------------------------------------- modèle
def telecharger_modele(etat):
    import urllib.request

    DONNEES.mkdir(parents=True, exist_ok=True)
    zip_tmp = DONNEES / "modele.zip"
    dossier_tmp = DONNEES / "modele_en_cours"
    dernier = [-1]

    def progression(n, taille_bloc, total):
        if total > 0:
            pourcent = min(100, n * taille_bloc * 100 // total)
            if pourcent // 5 != dernier[0]:
                dernier[0] = pourcent // 5
                etat.definir_statut(f"téléchargement du modèle vocal… {pourcent} %")

    urllib.request.urlretrieve(URL_MODELE, zip_tmp, progression)
    etat.definir_statut("installation du modèle vocal…")
    shutil.rmtree(dossier_tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_tmp) as z:
        z.extractall(dossier_tmp)
    contenu = [p for p in dossier_tmp.iterdir() if p.is_dir()]
    source = contenu[0] if len(contenu) == 1 else dossier_tmp
    shutil.rmtree(DOSSIER_MODELE, ignore_errors=True)
    shutil.move(str(source), str(DOSSIER_MODELE))
    shutil.rmtree(dossier_tmp, ignore_errors=True)
    zip_tmp.unlink(missing_ok=True)


def preparer_modele(etat):
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    prevenu = False
    while not DOSSIER_MODELE.is_dir() and not etat.arret.is_set():
        if not prevenu:
            log.info("Premier lancement : téléchargement du modèle vocal français (~40 Mo)…")
            etat.notifier("Premier lancement : je télécharge le modèle vocal français (~40 Mo). "
                          "Ça prend une minute.")
        try:
            telecharger_modele(etat)
            log.info("Modèle vocal installé.")
        except Exception as e:
            log.error("Téléchargement du modèle impossible : %s", e)
            etat.definir_statut("pas d'internet pour télécharger le modèle, nouvel essai dans 1 min",
                                probleme=True)
            if not prevenu:
                etat.notifier("Impossible de télécharger le modèle vocal. Vérifie ta connexion : "
                              "je réessaie toutes les minutes.")
            prevenu = True
            etat.arret.wait(60)
        prevenu = True
    if etat.arret.is_set():
        return None
    etat.definir_statut("chargement du modèle vocal…")
    return Model(str(DOSSIER_MODELE))


def moteur(etat, gestionnaire, annoncer):
    """Fil d'écoute : prépare le modèle puis écoute jusqu'à l'arrêt."""
    try:
        modele = preparer_modele(etat)
        if modele is None:
            return
        if annoncer:
            p = etat.reglages.prenom
            etat.notifier(f"Prêt ! Dis « {p}, éteins l'ordinateur » ou « {p}, mets en veille "
                          "l'ordinateur ». Clic droit sur l'icône pour le menu.")
        ecouter(modele, etat, gestionnaire)
    except Exception:
        log.error("Erreur inattendue :\n%s", traceback.format_exc())
        etat.definir_statut("erreur, regarde le journal", probleme=True)


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


def definir_demarrage(actif):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_DEMARRAGE, 0, winreg.KEY_SET_VALUE) as cle:
            if actif:
                winreg.SetValueEx(cle, NOM_DEMARRAGE, 0, winreg.REG_SZ, commande_demarrage())
            else:
                try:
                    winreg.DeleteValue(cle, NOM_DEMARRAGE)
                except FileNotFoundError:
                    pass
        log.info("Lancement au démarrage de Windows %s.", "activé" if actif else "désactivé")
    except OSError as e:
        log.error("Impossible de modifier le lancement au démarrage : %s", e)


def arreter_ancienne_version():
    """Arrête la toute première version (script + .bat) si elle tourne encore."""
    h = k32.OpenEventW(EVENT_MODIFY_STATE, False, ANCIEN_ARRET)
    if h:
        k32.SetEvent(h)
        k32.CloseHandle(h)
        log.info("Ancienne version (script) arrêtée.")
    ancien = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" /
              "Programs" / "Startup" / "Claude vocal.lnk")
    try:
        if ancien.exists():
            ancien.unlink()
            log.info("Ancien raccourci de démarrage supprimé.")
    except OSError:
        pass


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
            tk.Label(cadre, text="MODE TEST : rien ne sera vraiment fait", fg=COULEURS["test"],
                     font=(self.POLICE, 9, "bold")).pack(pady=(0, 8))
        titre = tk.Label(cadre, font=(self.POLICE, 15, "bold"))
        titre.pack()
        tk.Label(cadre, text=f"Dis « {self.etat.reglages.prenom}, annule » ou clique sur Annuler.",
                 font=(self.POLICE, 10)).pack(pady=(8, 16))
        boutons = tk.Frame(cadre)
        boutons.pack()
        tk.Button(boutons, text="Annuler", width=12, font=(self.POLICE, 10),
                  command=self.g.annuler).pack(side="left", padx=6)
        tk.Button(boutons, text="Maintenant", width=12, font=(self.POLICE, 10),
                  command=self.g.tout_de_suite.set).pack(side="left", padx=6)

        def rafraichir():
            if self.fenetre_rebours is not f:
                return
            if self.g.en_cours != nom:
                f.destroy()
                self.fenetre_rebours = None
                return
            reste = max(0, math.ceil(self.g.fin - time.monotonic()))
            titre.config(text=f"{LIBELLES[nom]} dans {reste} s")
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
        f.title(f"{NOM_APPLI} : mode test")
        f.geometry("560x380")
        f.protocol("WM_DELETE_WINDOW", lambda: self.etat.definir_test(False))
        tk.Label(f, justify="left", padx=12, pady=10, font=(self.POLICE, 10),
                 text="Parle : ce que le micro comprend s'affiche ici.\n"
                      "Les commandes sont simulées, rien n'est vraiment éteint.").pack(anchor="w")
        self.zone_test = tk.Text(f, height=14, state="disabled", wrap="word", font=("Consolas", 10))
        self.zone_test.pack(fill="both", expand=True, padx=12)
        tk.Button(f, text="Terminer le test", font=(self.POLICE, 10),
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
        p = self.etat.reglages.prenom
        messagebox.showinfo(
            NOM_APPLI,
            f"Phrases reconnues :\n\n"
            f"« {p}, éteins l'ordinateur »\n"
            f"« {p}, mets en veille l'ordinateur »\n"
            f"« {p}, redémarre l'ordinateur »\n"
            f"« {p}, verrouille l'ordinateur »\n"
            f"« {p}, annule »\n\n"
            f"Pour changer de prénom, de micro ou de délais : clic droit sur l'icône, "
            f"puis « Réglages ».\n\nÉtat : {self.etat.statut}\nVersion {VERSION}",
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
        Item(lambda i: f"État : {etat.statut}"[:90], None, enabled=False),
        Menu.SEPARATOR,
        Item("Mode test (rien n'est vraiment fait)", lambda: etat.definir_test(not etat.test),
             checked=lambda i: etat.test),
        Item("Lancer au démarrage de Windows", lambda: definir_demarrage(not demarrage_actif()),
             checked=lambda i: demarrage_actif()),
        Menu.SEPARATOR,
        Item("Phrases reconnues…", lambda: etat.ui.put(("aide",)), default=True),
        Item("Réglages (prénom, micro, délais)…", ouvrir_dans_bloc_notes(FICHIER_REGLAGES)),
        Item("Ouvrir le journal", ouvrir_dans_bloc_notes(JOURNAL)),
        Menu.SEPARATOR,
        Item("Quitter", quitter),
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
        detecter(normaliser("Claude, éteins l'ordinateur"), ["claude"])
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
        print("Claude vocal fonctionne sous Windows.")
        return 1

    configurer_journal()
    global VERROU
    VERROU = k32.CreateMutexW(None, False, NOM_VERROU)  # gardé ouvert jusqu'à la fin
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        u32.MessageBoxW(None, "Claude vocal est déjà lancé : son icône est près de l'horloge "
                              "(clic droit dessus pour le menu).", NOM_APPLI, 0x40)
        return 0

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # fenêtres nettes sur les grands écrans
    except Exception:
        pass

    log.info("Démarrage de Claude vocal %s", VERSION)
    arreter_ancienne_version()
    reglages = Reglages()
    reglages.charger()
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
            etat.notifier("Installé ! Je me lancerai à chaque démarrage de Windows "
                          "(décochable dans le menu de l'icône).")
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
        log.info("Claude vocal arrêté.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
