# -*- coding: utf-8 -*-
"""
Git AutoPush (interface graphique)

1. Tu remplis : lien du dépôt GitHub, branche, nom/email Git, token (optionnel)
2. Tu cliques sur "Choisir le dossier et envoyer"
3. L'explorateur de fichiers s'ouvre, tu choisis le dossier
4. Le programme fait init / add / commit / push tout seul

Nécessite Git installé sur le PC. Le token n'est JAMAIS enregistré sur le disque.
"""

import base64
import json
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

CONFIG_FILE = Path.home() / ".git_autopush_gui.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # évite les fenêtres noires sous Windows


# ---------------------------------------------------------------- Git helpers

def run_git(args, cwd, secrets=()):
    """Lance git, renvoie (code, sortie) avec les secrets masqués."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    out = (result.stdout + result.stderr).strip()
    for s in secrets:
        if s:
            out = out.replace(s, "***")
    return result.returncode, out


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- Application

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git AutoPush")
        self.geometry("640x620")
        self.minsize(560, 560)

        self.cfg = load_config()
        self.msgq = queue.Queue()
        self.busy = False

        self._build_ui()
        self.after(100, self._poll_queue)

    # ---- UI
    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=8, pady=8)
        frm.columnconfigure(1, weight=1)

        def row(r, label, value="", show=None):
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", **pad)
            var = tk.StringVar(value=value)
            ttk.Entry(frm, textvariable=var, show=show).grid(row=r, column=1, sticky="ew", **pad)
            return var

        self.url = row(0, "Lien du dépôt GitHub :", self.cfg.get("url", ""))
        self.branch = row(1, "Branche :", self.cfg.get("branch", "main"))
        self.name = row(2, "Nom Git (user.name) :", self.cfg.get("name", ""))
        self.email = row(3, "Email Git (user.email) :", self.cfg.get("email", ""))
        self.user = row(4, "Pseudo GitHub (si token) :", self.cfg.get("user", ""))
        self.token = row(5, "Token GitHub (optionnel) :", "", show="•")
        self.message = row(6, "Message de commit :", self.cfg.get("message", "auto"))

        ttk.Label(
            frm,
            text="Message \"auto\" = date/heure.  Token vide = connexion via Git Credential Manager (fenêtre GitHub).",
            foreground="#666",
            wraplength=580,
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        self.btn = ttk.Button(self, text="📁  Choisir le dossier et envoyer sur GitHub", command=self.on_click)
        self.btn.pack(fill="x", padx=20, pady=8, ipady=8)

        self.log = tk.Text(self, height=14, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ---- Logging thread-safe
    def log_line(self, text):
        self.msgq.put(("log", text))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", payload + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "done":
                    self.busy = False
                    self.btn.configure(state="normal")
                elif kind == "ask":
                    question, event, holder = payload
                    holder["answer"] = messagebox.askyesno("Git AutoPush", question)
                    event.set()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def ask_yes_no(self, question):
        """Pose une question oui/non depuis le thread de travail."""
        event, holder = threading.Event(), {}
        self.msgq.put(("ask", (question, event, holder)))
        event.wait()
        return holder.get("answer", False)

    # ---- Action
    def on_click(self):
        if self.busy:
            return
        url = self.url.get().strip()
        branch = self.branch.get().strip() or "main"

        if not url:
            messagebox.showwarning("Git AutoPush", "Indique le lien du dépôt GitHub.")
            return
        if shutil.which("git") is None:
            messagebox.showerror(
                "Git introuvable",
                "Git n'est pas installé (ou pas dans le PATH).\nTélécharge-le sur https://git-scm.com/downloads",
            )
            return
        if self.token.get().strip() and not self.user.get().strip():
            messagebox.showwarning("Git AutoPush", "Renseigne ton pseudo GitHub pour utiliser le token.")
            return

        folder = filedialog.askdirectory(
            title="Choisis le dossier à envoyer sur GitHub",
            initialdir=self.cfg.get("folder") or str(Path.home()),
        )
        if not folder:
            return

        settings = {
            "url": url,
            "branch": branch,
            "name": self.name.get().strip(),
            "email": self.email.get().strip(),
            "user": self.user.get().strip(),
            "token": self.token.get().strip(),
            "message": self.message.get().strip() or "auto",
            "folder": folder,
        }
        # On sauvegarde tout SAUF le token
        save_config({k: v for k, v in settings.items() if k != "token"})
        self.cfg = load_config()

        self.busy = True
        self.btn.configure(state="disabled")
        threading.Thread(target=self.worker, args=(settings,), daemon=True).start()

    # ---- Travail Git (thread)
    def worker(self, s):
        try:
            self._push(s)
        except Exception as e:  # sécurité
            self.log_line(f"❌ Erreur inattendue : {e}")
        finally:
            self.msgq.put(("done", None))

    def git(self, args, s, check=True):
        code, out = run_git(args, s["folder"], secrets=(s["token"],))
        if check and code != 0:
            raise RuntimeError(f"git {' '.join(args[:3])} a échoué :\n{out}")
        return code, out

    def _push(self, s):
        folder, url, branch = s["folder"], s["url"], s["branch"]
        self.log_line(f"📂 Dossier : {folder}")
        self.log_line(f"🔗 Dépôt   : {url}")

        # 1) init
        if not (Path(folder) / ".git").exists():
            self.log_line("• Initialisation du dépôt Git...")
            self.git(["init"], s)

        # 2) identité
        if s["name"]:
            self.git(["config", "user.name", s["name"]], s)
        if s["email"]:
            self.git(["config", "user.email", s["email"]], s)

        # 3) remote
        code, current = self.git(["remote", "get-url", "origin"], s, check=False)
        if code != 0:
            self.log_line("• Ajout du remote 'origin'...")
            self.git(["remote", "add", "origin", url], s)
        elif current != url:
            self.log_line(f"• Remote 'origin' mis à jour (ancien : {current})")
            self.git(["remote", "set-url", "origin", url], s)

        # 4) branche
        _, cur_branch = self.git(["branch", "--show-current"], s, check=False)
        if cur_branch != branch:
            code, _ = self.git(["rev-parse", "--verify", branch], s, check=False)
            self.git(["checkout", branch] if code == 0 else ["checkout", "-b", branch], s)
        self.log_line(f"• Branche : {branch}")

        # 5) add + commit
        self.git(["add", "-A"], s)
        _, status = self.git(["status", "--porcelain"], s)
        if status:
            msg = s["message"]
            if msg.lower() == "auto":
                msg = f"Auto-commit {datetime.now():%Y-%m-%d %H:%M:%S}"
            self.log_line("• Création du commit...")
            code, out = self.git(["commit", "-m", msg], s, check=False)
            if code != 0:
                if "user.name" in out or "user.email" in out or "identity" in out.lower():
                    raise RuntimeError("Git ne connaît pas ton identité : remplis 'Nom Git' et 'Email Git'.")
                raise RuntimeError(out)
        else:
            self.log_line("• Aucun nouveau changement à committer.")

        # 6) push
        push_args = self._push_args(s)
        self.log_line("• Envoi vers GitHub...")
        code, out = self.git(push_args, s, check=False)

        if code != 0 and any(k in out for k in ("rejected", "non-fast-forward", "fetch first")):
            self.log_line("⚠️ Le dépôt distant contient des commits absents en local.")
            if self.ask_yes_no(
                "Le dépôt GitHub contient déjà des fichiers/commits différents.\n\n"
                "Les récupérer (pull --rebase) puis réessayer l'envoi ?"
            ):
                pull = ["pull", "--rebase", "--allow-unrelated-histories", "origin", branch]
                pull = self._with_auth(pull, s)
                c, o = self.git(pull, s, check=False)
                self.log_line(o)
                if c == 0:
                    code, out = self.git(push_args, s, check=False)

        if code == 0:
            self.log_line(out) if out else None
            self.log_line("✅ Push réussi !")
        else:
            self.log_line(out)
            self.log_line("❌ Le push a échoué.")
            low = out.lower()
            if any(k in low for k in ("authentication", "denied", "403", "401", "could not read")):
                self.log_line(
                    "💡 Authentification refusée : renseigne ton pseudo + un Personal Access Token\n"
                    "   (GitHub > Settings > Developer settings > Personal access tokens),\n"
                    "   avec le droit 'repo'."
                )
            elif "not found" in low or "does not exist" in low:
                self.log_line("💡 Dépôt introuvable : vérifie le lien (et crée le repo vide sur GitHub avant).")

    # ---- Authentification par token (jamais écrit dans la config git)
    def _with_auth(self, args, s):
        if s["token"]:
            raw = f"{s['user']}:{s['token']}".encode()
            header = "Authorization: Basic " + base64.b64encode(raw).decode()
            return ["-c", f"http.extraheader={header}"] + args
        return args

    def _push_args(self, s):
        return self._with_auth(["push", "-u", "origin", s["branch"]], s)


if __name__ == "__main__":
    App().mainloop()
