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
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_git(args, cwd, secrets=()):
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
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Git AutoPush")
        self.geometry("640x620")
        self.minsize(560, 560)

        self.cfg = load_config()
        self.msgq = queue.Queue()
        self.busy = False

        self.build_ui()
        self.after(100, self.poll_queue)

    def build_ui(self):
        pad = {"padx": 12, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=8, pady=8)
        frm.columnconfigure(1, weight=1)

        def row(index, label, value="", show=None):
            ttk.Label(frm, text=label).grid(row=index, column=0, sticky="w", **pad)
            var = tk.StringVar(value=value)
            ttk.Entry(frm, textvariable=var, show=show).grid(row=index, column=1, sticky="ew", **pad)
            return var

        self.url = row(0, "Lien du depot GitHub :", self.cfg.get("url", ""))
        self.branch = row(1, "Branche :", self.cfg.get("branch", "main"))
        self.name = row(2, "Nom Git (user.name) :", self.cfg.get("name", ""))
        self.email = row(3, "Email Git (user.email) :", self.cfg.get("email", ""))
        self.user = row(4, "Pseudo GitHub (si token) :", self.cfg.get("user", ""))
        self.token = row(5, "Token GitHub (optionnel) :", "", show="*")
        self.message = row(6, "Message de commit :", self.cfg.get("message", "auto"))

        ttk.Label(
            frm,
            text="Message \"auto\" = date et heure. Token vide = connexion via Git Credential Manager.",
            foreground="#666666",
            wraplength=580,
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        self.btn = ttk.Button(self, text="Choisir le dossier et envoyer sur GitHub", command=self.on_click)
        self.btn.pack(fill="x", padx=20, pady=8, ipady=8)

        self.log = tk.Text(self, height=14, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def log_line(self, text):
        self.msgq.put(("log", text))

    def poll_queue(self):
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
        self.after(100, self.poll_queue)

    def ask_yes_no(self, question):
        event, holder = threading.Event(), {}
        self.msgq.put(("ask", (question, event, holder)))
        event.wait()
        return holder.get("answer", False)

    def on_click(self):
        if self.busy:
            return

        url = self.url.get().strip()
        branch = self.branch.get().strip() or "main"

        if not url:
            messagebox.showwarning("Git AutoPush", "Indique le lien du depot GitHub.")
            return
        if shutil.which("git") is None:
            messagebox.showerror(
                "Git introuvable",
                "Git n'est pas installe ou pas dans le PATH.\nTelechargement : https://git-scm.com/downloads",
            )
            return
        if self.token.get().strip() and not self.user.get().strip():
            messagebox.showwarning("Git AutoPush", "Renseigne ton pseudo GitHub pour utiliser le token.")
            return

        folder = filedialog.askdirectory(
            title="Choisis le dossier a envoyer sur GitHub",
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
        save_config({k: v for k, v in settings.items() if k != "token"})
        self.cfg = load_config()

        self.busy = True
        self.btn.configure(state="disabled")
        threading.Thread(target=self.worker, args=(settings,), daemon=True).start()

    def worker(self, settings):
        try:
            self.push(settings)
        except Exception as error:
            self.log_line(f"Erreur : {error}")
        finally:
            self.msgq.put(("done", None))

    def auth_header(self, settings):
        raw = f"{settings['user']}:{settings['token']}".encode()
        return "Authorization: Basic " + base64.b64encode(raw).decode()

    def git(self, args, settings, check=True):
        secrets = ()
        if settings["token"]:
            secrets = (settings["token"], self.auth_header(settings))
        code, out = run_git(args, settings["folder"], secrets=secrets)
        if check and code != 0:
            raise RuntimeError(f"git {' '.join(args[:3])} a echoue :\n{out}")
        return code, out

    def with_auth(self, args, settings):
        if settings["token"]:
            return ["-c", f"http.extraheader={self.auth_header(settings)}"] + args
        return args

    def push(self, settings):
        folder = settings["folder"]
        url = settings["url"]
        branch = settings["branch"]

        self.log_line(f"Dossier : {folder}")
        self.log_line(f"Depot   : {url}")

        if not (Path(folder) / ".git").exists():
            self.log_line("Initialisation du depot Git...")
            self.git(["init"], settings)

        if settings["name"]:
            self.git(["config", "user.name", settings["name"]], settings)
        if settings["email"]:
            self.git(["config", "user.email", settings["email"]], settings)

        code, current = self.git(["remote", "get-url", "origin"], settings, check=False)
        if code != 0:
            self.log_line("Ajout du remote origin...")
            self.git(["remote", "add", "origin", url], settings)
        elif current != url:
            self.log_line(f"Remote origin mis a jour (ancien : {current})")
            self.git(["remote", "set-url", "origin", url], settings)

        _, current_branch = self.git(["branch", "--show-current"], settings, check=False)
        if current_branch != branch:
            code, _ = self.git(["rev-parse", "--verify", branch], settings, check=False)
            self.git(["checkout", branch] if code == 0 else ["checkout", "-b", branch], settings)
        self.log_line(f"Branche : {branch}")

        self.git(["add", "-A"], settings)
        _, status = self.git(["status", "--porcelain"], settings)
        if status:
            message = settings["message"]
            if message.lower() == "auto":
                message = f"Auto-commit {datetime.now():%Y-%m-%d %H:%M:%S}"
            self.log_line("Creation du commit...")
            code, out = self.git(["commit", "-m", message], settings, check=False)
            if code != 0:
                lowered = out.lower()
                if "user.name" in out or "user.email" in out or "identity" in lowered:
                    raise RuntimeError("Git ne connait pas ton identite : remplis Nom Git et Email Git.")
                raise RuntimeError(out)
        else:
            self.log_line("Aucun nouveau changement a committer.")

        push_args = self.with_auth(["push", "-u", "origin", branch], settings)
        self.log_line("Envoi vers GitHub...")
        code, out = self.git(push_args, settings, check=False)

        if code != 0 and any(k in out for k in ("rejected", "non-fast-forward", "fetch first")):
            self.log_line("Le depot distant contient des commits absents en local.")
            question = (
                "Le depot GitHub contient deja des fichiers ou commits differents.\n\n"
                "Les recuperer (pull --rebase) puis reessayer l'envoi ?"
            )
            if self.ask_yes_no(question):
                pull_args = self.with_auth(
                    ["pull", "--rebase", "--allow-unrelated-histories", "origin", branch], settings
                )
                pull_code, pull_out = self.git(pull_args, settings, check=False)
                self.log_line(pull_out)
                if pull_code == 0:
                    code, out = self.git(push_args, settings, check=False)

        if code == 0:
            if out:
                self.log_line(out)
            self.log_line("Push reussi.")
            return

        self.log_line(out)
        self.log_line("Le push a echoue.")
        lowered = out.lower()
        if any(k in lowered for k in ("authentication", "denied", "403", "401", "could not read")):
            self.log_line(
                "Authentification refusee : renseigne ton pseudo et un Personal Access Token "
                "avec le droit repo (GitHub > Settings > Developer settings > Personal access tokens)."
            )
        elif "not found" in lowered or "does not exist" in lowered:
            self.log_line("Depot introuvable : verifie le lien et cree le depot sur GitHub avant.")


if __name__ == "__main__":
    App().mainloop()
