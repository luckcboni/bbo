import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext, simpledialog
import threading
import time
import base64
import os
import socket
import subprocess
import tempfile
import requests
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService

# ── Firebase config ────────────────────────────────────────────────────────────
FIREBASE_URL = "https://chat-global-71464-default-rtdb.firebaseio.com"
CHAT_PATH    = "/chat.json"
BANS_PATH    = "/bans.json"
MAX_MSGS     = 100
MAX_CHARS    = 400
ADMIN_NICK   = "luck"   # nick do admin (case-insensitive)
# ──────────────────────────────────────────────────────────────────────────────

NAVEGADORES = {
    "Chrome": {
        "caminhos": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "driver": "chrome",
        "porta": 9222,
    },
    "Edge": {
        "caminhos": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "driver": "edge",
        "porta": 9223,
    },
    "Brave": {
        "caminhos": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "driver": "chrome",
        "porta": 9224,
    },
}


def achar_executavel(nome_nav):
    usuario = os.environ.get("USERNAME", "User")
    caminhos = NAVEGADORES[nome_nav]["caminhos"] + [
        rf"C:\Users\{usuario}\AppData\Local\Google\Chrome\Application\chrome.exe",
        rf"C:\Users\{usuario}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for c in caminhos:
        if os.path.exists(c):
            return c
    return None


def imagem_para_base64(caminho):
    with open(caminho, "rb") as f:
        dados = base64.b64encode(f.read()).decode("utf-8")
    ext = caminho.split(".")[-1].lower()
    mimes = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "webp": "image/webp", "gif": "image/gif"}
    mime = mimes.get(ext, "image/png")
    return f"data:{mime};base64,{dados}"


def url_para_base64(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, timeout=10, headers=headers)
    resp.raise_for_status()
    ext = url.split("?")[0].split(".")[-1].lower()
    mimes = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
             "webp": "image/webp", "gif": "image/gif"}
    ct = resp.headers.get("content-type", "").split(";")[0].strip()
    if "image" not in ct:
        ct = mimes.get(ext, "image/jpeg")
    dados = base64.b64encode(resp.content).decode("utf-8")
    return f"data:{ct};base64,{dados}"


# ── Firebase helpers ───────────────────────────────────────────────────────────

def firebase_get():
    try:
        r = requests.get(FIREBASE_URL + CHAT_PATH, timeout=5)
        data = r.json()
        if not data:
            return []
        if isinstance(data, list):
            return [m for m in data if m]
        if isinstance(data, dict):
            return list(data.values())
        return []
    except Exception:
        return []


def firebase_post(nick, texto):
    if is_banned(nick):
        return "banned"
    msgs = firebase_get()
    msgs.append({
        "nick": nick[:20],
        "texto": texto[:MAX_CHARS],
        "hora": datetime.now().strftime("%H:%M"),
        "ts": int(time.time()),
    })
    if len(msgs) > MAX_MSGS:
        msgs = msgs[-MAX_MSGS:]
    try:
        requests.put(FIREBASE_URL + CHAT_PATH, json=msgs, timeout=5)
        return True
    except Exception:
        return False


# ── Firebase ban helpers ───────────────────────────────────────────────────────

def firebase_get_bans():
    try:
        r = requests.get(FIREBASE_URL + BANS_PATH, timeout=5)
        data = r.json()
        if not data:
            return []
        if isinstance(data, list):
            return [b.lower() for b in data if b]
        if isinstance(data, dict):
            return [v.lower() for v in data.values() if v]
        return []
    except Exception:
        return []


def firebase_ban(nick):
    bans = firebase_get_bans()
    nick_lower = nick.strip().lower()
    if nick_lower not in bans:
        bans.append(nick_lower)
    try:
        requests.put(FIREBASE_URL + BANS_PATH, json=bans, timeout=5)
        return True
    except Exception:
        return False


def firebase_unban(nick):
    bans = firebase_get_bans()
    nick_lower = nick.strip().lower()
    bans = [b for b in bans if b != nick_lower]
    try:
        requests.put(FIREBASE_URL + BANS_PATH, json=bans, timeout=5)
        return True
    except Exception:
        return False


def firebase_kick(nick):
    """Remove todas as mensagens do nick do chat."""
    msgs = firebase_get()
    nick_lower = nick.strip().lower()
    msgs = [m for m in msgs if m.get("nick", "").lower() != nick_lower]
    try:
        requests.put(FIREBASE_URL + CHAT_PATH, json=msgs, timeout=5)
        return True
    except Exception:
        return False


def is_banned(nick):
    bans = firebase_get_bans()
    return nick.strip().lower() in bans


# ── Camera injector ────────────────────────────────────────────────────────────

class CameraInjector:
    def __init__(self, log_callback):
        self.log = log_callback
        self.driver = None
        self.rodando = False
        self.image_url = None
        self.intervalo = 5

    def conectar(self, nome_nav):
        porta = NAVEGADORES[nome_nav]["porta"]
        tipo  = NAVEGADORES[nome_nav]["driver"]
        self.log("🔄 Preparando driver do navegador...")

        if tipo == "chrome":
            from webdriver_manager.chrome import ChromeDriverManager
            opts = ChromeOptions()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{porta}")
            if nome_nav == "Brave":
                exe = achar_executavel("Brave")
                if exe:
                    opts.binary_location = exe
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
        else:
            from webdriver_manager.microsoft import EdgeChromiumDriverManager
            opts = EdgeOptions()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{porta}")
            service = EdgeService(EdgeChromiumDriverManager().install())
            self.driver = webdriver.Edge(service=service, options=opts)

        aba_encontrada = None
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            url_atual = self.driver.current_url.lower()
            if "habblet.city/hotel" in url_atual:
                aba_encontrada = handle
                self.log("✅ Aba do jogo encontrada!")
                break

        if not aba_encontrada:
            for handle in self.driver.window_handles:
                self.driver.switch_to.window(handle)
                url_atual = self.driver.current_url.lower()
                if "habblet.city" in url_atual:
                    aba_encontrada = handle
                    self.log("⚠️ Aba do Habblet encontrada, mas não está no hotel.")
                    break

        if not aba_encontrada:
            self.driver.switch_to.window(self.driver.window_handles[0])
            self.log("⚠️ Aba do Habblet não encontrada. Redirecionando...")
            self.driver.get("https://www.habblet.city/hotel")
            time.sleep(2)
            self.log("✅ Redirecionado para o Habblet!")

        self.log("✅ Conectado ao navegador!")

    def injetar_hook(self, silencioso=False):
        if not self.image_url:
            self.log("⚠️ Nenhuma imagem definida!")
            return
        escaped = self.image_url.replace("'", "\\'")
        script = f"""
        if (!HTMLCanvasElement.prototype.__hookInstalado) {{
            HTMLCanvasElement.prototype.__hookInstalado = true;
            const tmp = document.createElement('canvas');
            tmp.width = 320; tmp.height = 320;
            const tmpCtx = tmp.getContext('2d');
            const img = new Image();
            img.src = '{escaped}';
            let cachedDataURL = null;
            let cachedBlob = null;
            img.onload = () => {{
                tmpCtx.drawImage(img, 0, 0, 320, 320);
                cachedDataURL = HTMLCanvasElement.prototype.__origToDataURL.call(tmp, 'image/png');
                HTMLCanvasElement.prototype.__origToBlob.call(tmp, b => {{ cachedBlob = b; }}, 'image/png');
            }};
            HTMLCanvasElement.prototype.__origToDataURL = HTMLCanvasElement.prototype.toDataURL;
            HTMLCanvasElement.prototype.__origToBlob   = HTMLCanvasElement.prototype.toBlob;
            HTMLCanvasElement.prototype.toDataURL = function(...args) {{
                if (this.width === 320 && this.height === 320 && cachedDataURL)
                    return cachedDataURL;
                return HTMLCanvasElement.prototype.__origToDataURL.apply(this, args);
            }};
            HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {{
                if (this.width === 320 && this.height === 320 && cachedBlob) {{
                    callback(cachedBlob); return;
                }}
                return HTMLCanvasElement.prototype.__origToBlob.call(this, callback, ...args);
            }};
        }} else {{
            const tmp2 = document.createElement('canvas');
            tmp2.width = 320; tmp2.height = 320;
            const ctx2 = tmp2.getContext('2d');
            const img2 = new Image();
            img2.src = '{escaped}';
            img2.onload = () => {{
                ctx2.drawImage(img2, 0, 0, 320, 320);
                HTMLCanvasElement.prototype.toDataURL = function(...args) {{
                    if (this.width === 320 && this.height === 320)
                        return HTMLCanvasElement.prototype.__origToDataURL.call(tmp2, 'image/png');
                    return HTMLCanvasElement.prototype.__origToDataURL.apply(this, args);
                }};
                HTMLCanvasElement.prototype.toBlob = function(callback, ...args) {{
                    if (this.width === 320 && this.height === 320) {{
                        HTMLCanvasElement.prototype.__origToBlob.call(tmp2, callback, 'image/png'); return;
                    }}
                    return HTMLCanvasElement.prototype.__origToBlob.call(this, callback, ...args);
                }};
            }};
        }}
        """
        self.driver.execute_script(script)
        if not silencioso:
            self.log("🎯 Hook injetado! Tire uma foto no jogo agora.")

    def rodar(self):
        self.rodando = True
        self.injetar_hook()
        while self.rodando:
            time.sleep(self.intervalo)
            if self.rodando and self.image_url:
                try:
                    self.injetar_hook(silencioso=True)
                except Exception as e:
                    self.log(f"⚠️ Erro ao reinjetar: {e}")
        self.log("⛔ Injector parado.")

    def parar(self):
        self.rodando = False


# ── Janela de chat ─────────────────────────────────────────────────────────────

class ChatWindow(tk.Toplevel):
    BG    = "#0d0d1a"
    CARD  = "#16213e"
    INPUT = "#0f3460"
    ACCENT= "#e94560"
    TEXT  = "#eaeaea"
    MUTED = "#a0a0b0"
    GREEN = "#00ff88"

    def __init__(self, parent, nick):
        super().__init__(parent)
        self.nick = nick
        self.title("💬 Chat Global — Habbo Injector")
        self.geometry("480x540")
        self.configure(bg=self.BG)
        self.resizable(False, False)
        self._ultimo_ts = 0
        self._rodando   = True
        self._build_ui()
        self._iniciar_polling()
        self.protocol("WM_DELETE_WINDOW", self._fechar)

    def _build_ui(self):
        tk.Label(self, text="💬 Chat Global", font=("Segoe UI", 14, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(12, 2))
        tk.Label(self, text=f"Logado como: {self.nick}  •  máx {MAX_CHARS} caracteres",
                 font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED).pack()

        self.chat_box = scrolledtext.ScrolledText(
            self, bg="#060612", fg=self.GREEN, font=("Consolas", 9),
            relief="flat", state="disabled", wrap="word", height=22)
        self.chat_box.pack(fill="both", expand=True, padx=12, pady=(10, 6))
        self.chat_box.tag_config("nick",    foreground="#e94560", font=("Consolas", 9, "bold"))
        self.chat_box.tag_config("hora",    foreground="#555577", font=("Consolas", 8))
        self.chat_box.tag_config("msg",     foreground="#eaeaea", font=("Consolas", 9))
        self.chat_box.tag_config("sistema", foreground="#00cc88", font=("Consolas", 8, "italic"))

        bottom = tk.Frame(self, bg=self.BG)
        bottom.pack(fill="x", padx=12, pady=(0, 12))

        self.entry_msg = tk.Entry(bottom, bg=self.INPUT, fg=self.TEXT,
                                   insertbackground=self.TEXT, relief="flat",
                                   font=("Segoe UI", 10))
        self.entry_msg.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))
        self.entry_msg.bind("<Return>", self._enviar)

        tk.Button(bottom, text="Enviar", font=("Segoe UI", 9, "bold"),
                  bg=self.ACCENT, fg="white", relief="flat", cursor="hand2",
                  command=self._enviar).pack(side="left", ipady=6, ipadx=12)

        self.label_chars = tk.Label(self, text=f"0/{MAX_CHARS}",
                                     font=("Segoe UI", 7), bg=self.BG, fg=self.MUTED)
        self.label_chars.pack(anchor="e", padx=14)
        self.entry_msg.bind("<KeyRelease>", self._atualizar_contador)

    def _atualizar_contador(self, event=None):
        n = len(self.entry_msg.get())
        cor = "#e74c3c" if n > MAX_CHARS else self.MUTED
        self.label_chars.config(text=f"{n}/{MAX_CHARS}", fg=cor)

    def _append(self, nick, hora, texto, sistema=False):
        self.chat_box.config(state="normal")
        if sistema:
            self.chat_box.insert("end", f"  {texto}\n", "sistema")
        else:
            self.chat_box.insert("end", f"[{hora}] ", "hora")
            self.chat_box.insert("end", f"{nick}: ", "nick")
            self.chat_box.insert("end", f"{texto}\n", "msg")
        self.chat_box.see("end")
        self.chat_box.config(state="disabled")

    def _enviar(self, event=None):
        texto = self.entry_msg.get().strip()
        if not texto:
            return
        if len(texto) > MAX_CHARS:
            messagebox.showwarning("Aviso", f"Mensagem muito longa! Máximo {MAX_CHARS} caracteres.")
            return
        self.entry_msg.delete(0, "end")
        self.label_chars.config(text=f"0/{MAX_CHARS}", fg=self.MUTED)

        def _post():
            resultado = firebase_post(self.nick, texto)
            if resultado == "banned":
                self.after(0, lambda: self._append("", "", "🚫 Você foi banido do chat.", sistema=True))
                self.after(0, lambda: self.entry_msg.config(state="disabled"))
            elif not resultado:
                self.after(0, lambda: self._append("", "", "❌ Erro ao enviar mensagem.", sistema=True))
        threading.Thread(target=_post, daemon=True).start()

    def _iniciar_polling(self):
        self._append("", "", "🔄 Conectando ao chat...", sistema=True)
        threading.Thread(target=self._loop_polling, daemon=True).start()

    def _loop_polling(self):
        primeiro = True
        while self._rodando:
            msgs = firebase_get()
            novos = [m for m in msgs if m.get("ts", 0) > self._ultimo_ts]
            if novos:
                self._ultimo_ts = max(m.get("ts", 0) for m in novos)
                if primeiro:
                    # Na primeira carga mostra as últimas 20
                    exibir = msgs[-20:]
                    self.after(0, lambda: self._append("", "", f"── {len(exibir)} mensagens anteriores ──", sistema=True))
                    for m in exibir:
                        m_ = m
                        self.after(0, lambda x=m_: self._append(x.get("nick","?"), x.get("hora",""), x.get("texto","")))
                    primeiro = False
                else:
                    for m in novos:
                        m_ = m
                        self.after(0, lambda x=m_: self._append(x.get("nick","?"), x.get("hora",""), x.get("texto","")))
            elif primeiro:
                self.after(0, lambda: self._append("", "", "💬 Nenhuma mensagem ainda. Seja o primeiro!", sistema=True))
                primeiro = False
            time.sleep(3)

    def _fechar(self):
        self._rodando = False
        self.destroy()


# ── App principal ──────────────────────────────────────────────────────────────

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("📷 Habbo Camera Injector")
        self.root.geometry("780x640")
        self.root.configure(bg="#1a1a2e")
        self.root.resizable(False, False)

        self.nav_selecionado = tk.StringVar(value="Chrome")
        self.fonte_selecionada = tk.StringVar(value="arquivo")
        self.caminho_imagem = tk.StringVar(value="")
        self.url_imagem = tk.StringVar(value="")
        self.injector = None
        self.thread = None
        self.nick = None
        self.chat_win = None

        self._ui()

    def _ui(self):
        BG     = "#1a1a2e"
        CARD   = "#16213e"
        ACCENT = "#e94560"
        TEXT   = "#eaeaea"
        MUTED  = "#a0a0b0"
        INPUT  = "#0f3460"
        GREEN  = "#27ae60"

        tk.Label(self.root, text="📷 Habbo Camera Injector",
                 font=("Segoe UI", 18, "bold"), bg=BG, fg=ACCENT).pack(pady=(16, 2))
        tk.Label(self.root, text="Injete qualquer imagem nas fotos do Habbo",
                 font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(pady=(0, 12))

        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=18)

        # ── Painel esquerdo ───────────────────────────────────────────────────
        left = tk.Frame(main, bg=CARD, relief="flat")
        left.pack(side="left", fill="y", padx=(0, 10), pady=4, ipadx=14, ipady=10)

        tk.Label(left, text="⚙️  Configurações", font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=TEXT).pack(anchor="w", pady=(4, 10))

        tk.Label(left, text="Navegador", font=("Segoe UI", 9, "bold"),
                 bg=CARD, fg=MUTED).pack(anchor="w", pady=(6, 2))
        nf = tk.Frame(left, bg=CARD)
        nf.pack(anchor="w")
        for nav in ["Chrome", "Edge", "Brave"]:
            exe = achar_executavel(nav)
            cor = TEXT if exe else MUTED
            tk.Radiobutton(nf, text=nav, variable=self.nav_selecionado, value=nav,
                           bg=CARD, fg=cor, selectcolor=INPUT, activebackground=CARD,
                           font=("Segoe UI", 9),
                           command=self._atualizar_instrucoes).pack(side="left", padx=(0, 8))

        self.frame_inst = tk.Frame(left, bg="#0a1628")
        self.frame_inst.pack(fill="x", pady=(6, 0))
        self.label_inst = tk.Label(self.frame_inst, text="", font=("Consolas", 7),
                                   bg="#0a1628", fg="#00cc88", wraplength=200, justify="left")
        self.label_inst.pack(padx=6, pady=4)
        self._atualizar_instrucoes()

        tk.Label(left, text="Intervalo de reinjeção (s)", font=("Segoe UI", 9, "bold"),
                 bg=CARD, fg=MUTED).pack(anchor="w", pady=(12, 2))
        self.entry_intervalo = tk.Entry(left, bg=INPUT, fg=TEXT, insertbackground=TEXT,
                                        relief="flat", font=("Segoe UI", 10), width=22)
        self.entry_intervalo.insert(0, "5")
        self.entry_intervalo.pack(anchor="w", ipady=4)

        tk.Label(left, text="💡 Quanto menor, mais rápido\natualiza a imagem no jogo",
                 font=("Segoe UI", 8), bg=CARD, fg=MUTED).pack(anchor="w", pady=(2, 0))

        self.btn_abrir_nav = tk.Button(
            left, text="🌐  ABRIR NAVEGADOR",
            font=("Segoe UI", 10, "bold"), bg=INPUT, fg=TEXT,
            activebackground="#1a4a80", relief="flat", cursor="hand2",
            command=self.abrir_navegador)
        self.btn_abrir_nav.pack(fill="x", pady=(8, 4), ipady=8)

        self.btn_iniciar = tk.Button(
            left, text="▶  CONECTAR E INJETAR",
            font=("Segoe UI", 10, "bold"), bg=ACCENT, fg="white",
            activebackground="#c73652", relief="flat", cursor="hand2",
            command=self.iniciar)
        self.btn_iniciar.pack(fill="x", pady=(12, 4), ipady=8)

        self.btn_parar = tk.Button(
            left, text="⛔  PARAR",
            font=("Segoe UI", 10, "bold"), bg="#444466", fg=MUTED,
            relief="flat", cursor="hand2", state="disabled",
            command=self.parar)
        self.btn_parar.pack(fill="x", ipady=8)

        # Botão chat
        tk.Frame(left, bg=CARD, height=1).pack(fill="x", pady=(14, 6))
        self.btn_chat = tk.Button(
            left, text="💬  CHAT GLOBAL",
            font=("Segoe UI", 10, "bold"), bg="#1a4a3a", fg="#00ff88",
            activebackground="#226644", relief="flat", cursor="hand2",
            command=self.abrir_chat)
        self.btn_chat.pack(fill="x", ipady=8)

        # ── Painel direito ────────────────────────────────────────────────────
        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True, pady=4)

        img_card = tk.Frame(right, bg=CARD)
        img_card.pack(fill="x", pady=(0, 8), ipadx=10, ipady=12)

        tk.Label(img_card, text="🖼️  Imagem a Injetar", font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=TEXT).pack(anchor="w", padx=10, pady=(4, 10))

        tab_frame = tk.Frame(img_card, bg=CARD)
        tab_frame.pack(fill="x", padx=10)

        self.btn_tab_arquivo = tk.Button(
            tab_frame, text="📁 Arquivo do PC",
            font=("Segoe UI", 9, "bold"), bg=ACCENT, fg="white",
            relief="flat", cursor="hand2",
            command=lambda: self._trocar_fonte("arquivo"))
        self.btn_tab_arquivo.pack(side="left", padx=(0, 4), ipady=4, ipadx=8)

        self.btn_tab_url = tk.Button(
            tab_frame, text="🔗 URL da Internet",
            font=("Segoe UI", 9, "bold"), bg=INPUT, fg=MUTED,
            relief="flat", cursor="hand2",
            command=lambda: self._trocar_fonte("url"))
        self.btn_tab_url.pack(side="left", ipady=4, ipadx=8)

        self.painel_arquivo = tk.Frame(img_card, bg=CARD)
        self.painel_arquivo.pack(fill="x", padx=10, pady=(10, 0))
        arq_row = tk.Frame(self.painel_arquivo, bg=CARD)
        arq_row.pack(fill="x")
        self.entry_arquivo = tk.Entry(arq_row, textvariable=self.caminho_imagem,
                                      bg=INPUT, fg=TEXT, insertbackground=TEXT,
                                      relief="flat", font=("Segoe UI", 9), state="readonly")
        self.entry_arquivo.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        tk.Button(arq_row, text="Selecionar",
                  font=("Segoe UI", 9, "bold"), bg=GREEN, fg="white",
                  relief="flat", cursor="hand2",
                  command=self._selecionar_arquivo).pack(side="left", ipady=5, ipadx=8)
        tk.Label(self.painel_arquivo,
                 text="Formatos suportados: PNG, JPG, JPEG, WEBP, GIF",
                 font=("Segoe UI", 8), bg=CARD, fg=MUTED).pack(anchor="w", pady=(4, 0))

        self.painel_url = tk.Frame(img_card, bg=CARD)
        url_row = tk.Frame(self.painel_url, bg=CARD)
        url_row.pack(fill="x")
        self.entry_url = tk.Entry(url_row, textvariable=self.url_imagem,
                                   bg=INPUT, fg=TEXT, insertbackground=TEXT,
                                   relief="flat", font=("Segoe UI", 9))
        self.entry_url.insert(0, "https://...")
        self.entry_url.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        tk.Button(url_row, text="Testar URL",
                  font=("Segoe UI", 9, "bold"), bg=GREEN, fg="white",
                  relief="flat", cursor="hand2",
                  command=self._testar_url).pack(side="left", ipady=5, ipadx=8)
        tk.Label(self.painel_url,
                 text="A imagem precisa ser acessível publicamente (sem login)",
                 font=("Segoe UI", 8), bg=CARD, fg=MUTED).pack(anchor="w", pady=(4, 0))

        self.label_preview = tk.Label(img_card, text="Nenhuma imagem selecionada",
                                      font=("Segoe UI", 9), bg=CARD, fg=MUTED)
        self.label_preview.pack(anchor="w", padx=10, pady=(8, 4))

        # Log
        lf = tk.Frame(right, bg=CARD)
        lf.pack(fill="both", expand=True, ipadx=10, ipady=8)

        header_lf = tk.Frame(lf, bg=CARD)
        header_lf.pack(fill="x", padx=8, pady=(4, 4))
        tk.Label(header_lf, text="📋  Log", font=("Segoe UI", 11, "bold"),
                 bg=CARD, fg=TEXT).pack(side="left")
        tk.Button(header_lf, text="🗑 Limpar", font=("Segoe UI", 8),
                  bg="#222244", fg=MUTED, relief="flat", cursor="hand2",
                  command=self._limpar_log).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(
            lf, bg="#060612", fg="#00ff88", insertbackground="white",
            font=("Consolas", 9), relief="flat", state="disabled", height=10)
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        cmd_frame = tk.Frame(lf, bg="#060612")
        cmd_frame.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(cmd_frame, text=">", font=("Consolas", 9), bg="#060612",
                 fg="#00ff88").pack(side="left", padx=(4, 2))
        self.cmd_input = tk.Entry(cmd_frame, bg="#060612", fg="#00ff88",
                                   insertbackground="#00ff88", relief="flat",
                                   font=("Consolas", 9))
        self.cmd_input.pack(side="left", fill="x", expand=True, ipady=3)
        self.cmd_input.bind("<Return>", self._executar_comando)

        self._log("💡 Selecione uma imagem, conecte o navegador e clique em Injetar!")
        self._log("ℹ️  Na primeira vez, o driver será baixado automaticamente.")
        self._log("💬 Digite /clear para limpar o log | /chat para abrir o chat.")

    # ── helpers UI ────────────────────────────────────────────────────────────

    def _trocar_fonte(self, fonte):
        ACCENT = "#e94560"; INPUT = "#0f3460"; MUTED = "#a0a0b0"
        self.fonte_selecionada.set(fonte)
        if fonte == "arquivo":
            self.painel_url.pack_forget()
            self.painel_arquivo.pack(fill="x", padx=10, pady=(10, 0))
            self.btn_tab_arquivo.config(bg=ACCENT, fg="white")
            self.btn_tab_url.config(bg=INPUT, fg=MUTED)
        else:
            self.painel_arquivo.pack_forget()
            self.painel_url.pack(fill="x", padx=10, pady=(10, 0))
            self.btn_tab_url.config(bg=ACCENT, fg="white")
            self.btn_tab_arquivo.config(bg=INPUT, fg=MUTED)

    def _selecionar_arquivo(self):
        tipos = [("Imagens", "*.png *.jpg *.jpeg *.webp *.gif"), ("Todos", "*.*")]
        caminho = filedialog.askopenfilename(title="Selecionar imagem", filetypes=tipos)
        if caminho:
            self.caminho_imagem.set(caminho)
            nome = os.path.basename(caminho)
            tamanho = os.path.getsize(caminho) // 1024
            self.label_preview.config(text=f"✅ {nome} ({tamanho} KB)", fg="#00cc88")
            self._log(f"📁 Imagem selecionada: {nome}")

    def _testar_url(self):
        url = self.url_imagem.get().strip()
        if not url or url == "https://...":
            messagebox.showwarning("Aviso", "Digite uma URL válida!")
            return
        self._log("🔗 Testando URL...")
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, timeout=8, headers=headers, stream=True)
            chunk = next(resp.iter_content(512))
            is_img = (chunk[:4] in [b'\x89PNG', b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1']
                      or chunk[:6] in [b'GIF87a', b'GIF89a'])
            if is_img or "image" in resp.headers.get("content-type", ""):
                self.label_preview.config(text="✅ URL válida! Imagem acessível.", fg="#00cc88")
                self._log(f"✅ URL válida: {url}")
            else:
                self.label_preview.config(text="⚠️ Pode não ser imagem, mas vai tentar", fg="#f39c12")
                self._log("⚠️ Conteúdo pode não ser imagem, mas vai tentar mesmo assim")
        except Exception as e:
            self.label_preview.config(text=f"❌ Erro: {e}", fg="#e74c3c")
            self._log(f"❌ Erro: {e}")

    def _atualizar_instrucoes(self):
        nav = self.nav_selecionado.get()
        exe = achar_executavel(nav)
        msg = (f"✅ {nav} encontrado!\nAbra o {nav} com o Habbo\ne clique em Conectar."
               if exe else f"⚠️ {nav} não encontrado.\nEscolha outro navegador.")
        self.label_inst.config(text=msg)

    def _log(self, txt):
        self.log_box.config(state="normal")
        self.log_box.insert("end", txt + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _limpar_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def _executar_comando(self, event=None):
        cmd = self.cmd_input.get().strip()
        self.cmd_input.delete(0, "end")
        cmd_lower = cmd.lower()

        if cmd_lower in ("/clear", "clear", "cls"):
            self._limpar_log()
            return

        if cmd_lower in ("/chat", "chat"):
            self.abrir_chat()
            return

        # Comandos admin — só funcionam se o nick for Luck
        is_admin = self.nick and self.nick.lower() == ADMIN_NICK

        if cmd_lower.startswith("/ban "):
            if not is_admin:
                self._log("🚫 Apenas o admin pode usar este comando.")
                return
            alvo = cmd[5:].strip()
            if not alvo:
                self._log("❓ Uso: /ban <nick>")
                return
            def _ban():
                ok = firebase_ban(alvo)
                msg = f"✅ {alvo} foi banido do chat." if ok else f"❌ Erro ao banir {alvo}."
                self.root.after(0, lambda: self._log(msg))
            threading.Thread(target=_ban, daemon=True).start()
            return

        if cmd_lower.startswith("/unban "):
            if not is_admin:
                self._log("🚫 Apenas o admin pode usar este comando.")
                return
            alvo = cmd[7:].strip()
            if not alvo:
                self._log("❓ Uso: /unban <nick>")
                return
            def _unban():
                ok = firebase_unban(alvo)
                msg = f"✅ {alvo} foi desbanido." if ok else f"❌ Erro ao desbanir {alvo}."
                self.root.after(0, lambda: self._log(msg))
            threading.Thread(target=_unban, daemon=True).start()
            return

        if cmd_lower.startswith("/kick "):
            if not is_admin:
                self._log("🚫 Apenas o admin pode usar este comando.")
                return
            alvo = cmd[6:].strip()
            if not alvo:
                self._log("❓ Uso: /kick <nick>")
                return
            def _kick():
                ok = firebase_kick(alvo)
                msg = f"✅ Mensagens de {alvo} removidas do chat." if ok else f"❌ Erro ao kickar {alvo}."
                self.root.after(0, lambda: self._log(msg))
            threading.Thread(target=_kick, daemon=True).start()
            return

        if cmd_lower == "/bans":
            if not is_admin:
                self._log("🚫 Apenas o admin pode usar este comando.")
                return
            def _listar():
                bans = firebase_get_bans()
                if bans:
                    self.root.after(0, lambda: self._log(f"🚫 Banidos: {', '.join(bans)}"))
                else:
                    self.root.after(0, lambda: self._log("✅ Nenhum usuário banido."))
            threading.Thread(target=_listar, daemon=True).start()
            return

        if cmd_lower == "/help":
            self._log("📋 Comandos disponíveis:")
            self._log("  /clear  — limpa o log")
            self._log("  /chat   — abre o chat")
            
        self._log(f"❓ Comando desconhecido: {cmd}  (use /help)")

    def _obter_image_url(self):
        fonte = self.fonte_selecionada.get()
        if fonte == "arquivo":
            caminho = self.caminho_imagem.get()
            if not caminho:
                messagebox.showwarning("Aviso", "Selecione uma imagem do PC!")
                return None
            self._log("🔄 Convertendo imagem para base64...")
            return imagem_para_base64(caminho)
        else:
            url = self.url_imagem.get().strip()
            if not url or url == "https://...":
                messagebox.showwarning("Aviso", "Digite uma URL válida!")
                return None
            self._log("🔄 Baixando imagem da URL...")
            return url_para_base64(url)

    def _copiar_cookies_chrome(self, nav, perfil_tmp):
        try:
            import shutil
            usuario = os.environ.get("USERNAME", "User")
            origens = {
                "Chrome": rf"C:\Users\{usuario}\AppData\Local\Google\Chrome\User Data\Default",
                "Edge":   rf"C:\Users\{usuario}\AppData\Local\Microsoft\Edge\User Data\Default",
            }
            origem = origens.get(nav)
            if not origem:
                return
            destino_default = os.path.join(perfil_tmp, "Default")
            os.makedirs(destino_default, exist_ok=True)
            for arq in ["Cookies", "Login Data"]:
                src = os.path.join(origem, arq)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(destino_default, arq))
            ls_src = os.path.join(os.path.dirname(origem), "Local State")
            if os.path.exists(ls_src):
                shutil.copy2(ls_src, os.path.join(perfil_tmp, "Local State"))
            self._log("🍪 Cookies copiados — você já vai estar logado!")
        except Exception as e:
            self._log(f"⚠️ Não foi possível copiar cookies: {e}")

    # ── ações principais ──────────────────────────────────────────────────────

    def iniciar(self):
        nav = self.nav_selecionado.get()
        if not achar_executavel(nav):
            messagebox.showerror("Erro", f"{nav} não encontrado no PC!")
            return
        try:
            intervalo = float(self.entry_intervalo.get())
        except ValueError:
            messagebox.showerror("Erro", "Intervalo inválido!")
            return
        try:
            image_url = self._obter_image_url()
            if not image_url:
                return
        except Exception as e:
            messagebox.showerror("Erro ao carregar imagem", str(e))
            return

        porta = NAVEGADORES[nav]["porta"]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        porta_aberta = sock.connect_ex(("127.0.0.1", porta)) == 0
        sock.close()

        if not porta_aberta:
            resposta = messagebox.askyesno(
                "Navegador não detectado",
                f"O {nav} não está no modo de depuração.\n\n"
                f"Deseja abri-lo automaticamente? (login será mantido)")
            if resposta:
                self.abrir_navegador()
                time.sleep(4)
            else:
                return

        if self.injector and self.injector.driver:
            self._log("♻️ Reutilizando conexão existente...")
            self.injector.image_url = image_url
            self.injector.intervalo = intervalo
            self.injector.rodando   = False
        else:
            self.injector = CameraInjector(self._log)
            self.injector.image_url = image_url
            self.injector.intervalo = intervalo
            try:
                self.injector.conectar(nav)
            except Exception as e:
                messagebox.showerror("Erro de conexão", str(e))
                return

        self.btn_iniciar.config(state="disabled", bg="#444466", fg="#a0a0b0")
        self.btn_parar.config(state="normal", bg="#e94560", fg="white")
        self.thread = threading.Thread(target=self.injector.rodar, daemon=True)
        self.thread.start()
        self._log("🚀 Injector rodando! Pode tirar fotos no jogo.")

    def abrir_navegador(self):
        nav = self.nav_selecionado.get()
        exe = achar_executavel(nav)
        if not exe:
            messagebox.showerror("Erro", f"{nav} não encontrado no PC!")
            return

        porta = NAVEGADORES[nav]["porta"]
        proc  = {"Chrome": "chrome.exe", "Edge": "msedge.exe", "Brave": "brave.exe"}[nav]

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ja_aberto = sock.connect_ex(("127.0.0.1", porta)) == 0
        sock.close()
        if ja_aberto:
            self._log(f"✅ {nav} já está no modo debug!")
            messagebox.showinfo("Já conectado!", f"O {nav} já está pronto!\n\nSó clicar em 'Conectar e Injetar'.")
            return

        self._log(f"🔄 Fechando {nav}...")
        for _ in range(3):
            subprocess.call(["taskkill", "/f", "/im", proc],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.8)

        usuario = os.environ.get("USERNAME", "User")
        if nav == "Brave":
            perfil = rf"C:\Users\{usuario}\AppData\Local\BraveSoftware\Brave-Browser\User Data"
            args_perfil = [f"--user-data-dir={perfil}"]
        else:
            perfil_tmp = os.path.join(tempfile.gettempdir(), f"blet_{nav.lower()}_profile")
            os.makedirs(perfil_tmp, exist_ok=True)
            self._copiar_cookies_chrome(nav, perfil_tmp)
            args_perfil = [f"--user-data-dir={perfil_tmp}"]

        self._log(f"🌐 Abrindo {nav} com modo de depuração...")
        subprocess.Popen([exe, f"--remote-debugging-port={porta}", *args_perfil,
                          "--no-first-run", "--no-default-browser-check",
                          "https://www.habblet.city/hotel"])

        def _aguardar():
            for i in range(40):
                time.sleep(0.5)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ok = s.connect_ex(("127.0.0.1", porta)) == 0
                s.close()
                if ok:
                    self._log(f"✅ {nav} pronto! Entre no jogo e clique em 'Conectar e Injetar'.")
                    return
                if i % 6 == 0 and i > 0:
                    self._log(f"⏳ Aguardando {nav}... ({i//2}s)")
            self._log("⚠️ Navegador aberto! Entre no jogo e clique em 'Conectar e Injetar'.")

        threading.Thread(target=_aguardar, daemon=True).start()

    def parar(self):
        if self.injector:
            self.injector.parar()
        self.btn_iniciar.config(state="normal", bg="#e94560", fg="white")
        self.btn_parar.config(state="disabled", bg="#444466", fg="#a0a0b0")
        self._log("⛔ Parado.")

    def abrir_chat(self):
        if self.chat_win and self.chat_win.winfo_exists():
            self.chat_win.lift()
            return
        if not self.nick:
            nick = simpledialog.askstring(
                "Chat Global",
                "Digite seu apelido para o chat (máx 20 caracteres):",
                parent=self.root)
            if not nick or not nick.strip():
                return
            self.nick = nick.strip()[:20]
        self.chat_win = ChatWindow(self.root, self.nick)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
