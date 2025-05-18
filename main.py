import sys
import io
import base64
import threading
from functools import partial
from dotenv import load_dotenv
import os
import ctypes
from openai import OpenAI
from PyQt5 import QtWidgets, QtCore, QtGui
import keyboard
import mss
import openai
from flask import Flask, request, redirect
from io import BytesIO
from ctypes import wintypes
import tempfile, os
import base64

# 1) Carrega .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# 2) Constantes WinAPI
WDA_NONE                 = 0x00000000
WDA_MONITOR              = 0x00000001
WDA_EXCLUDEFROMCAPTURE   = 0x00000011  # ! requires Win10 2004+

user32 = ctypes.windll.user32
gdi32  = ctypes.windll.gdi32
def start_web_server(config):
    app = Flask(__name__)

    @app.route('/', methods=['GET', 'POST'])
    def root():
        if request.method == 'POST':
            # troca de modelo
            if request.form.get('gpt_model'):
                config['model'] = request.form['gpt_model']
            # troca de margem
            x1, y1 = request.form.get('x1'), request.form.get('y1')
            x2, y2 = request.form.get('x2'), request.form.get('y2')
            if all([x1, y1, x2, y2]):
                config['margin'] = (int(x1), int(y1), int(x2), int(y2))
            return redirect('/')

        return f'''
        <html><body>
          <h2>Configurações Avançadas</h2>
          <form method="post">
            <label>GPT Model:</label>
            <input name="gpt_model" value="{config['model']}"/><br/>
            <label>Margem (x1,y1,x2,y2):</label>
            <input name="x1" placeholder="{config['margin'][0]}"/>
            <input name="y1" placeholder="{config['margin'][1]}"/>
            <input name="x2" placeholder="{config['margin'][2]}"/>
            <input name="y2" placeholder="{config['margin'][3]}"/><br/>
            <button type="submit">Salvar</button>
          </form>
          <script>setTimeout(()=>{"window.location='/'"},10000)</script>
        </body></html>
        '''

    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=config['port'], debug=False), daemon=True).start()

# 3) Classe do overlay
class Overlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(None, QtCore.Qt.WindowStaysOnTopHint | 
                               QtCore.Qt.FramelessWindowHint | 
                               QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setWindowOpacity(0.7)
        self.resize(400, QtWidgets.QApplication.primaryScreen().size().height() - 40)
        self.move(QtWidgets.QApplication.primaryScreen().size().width() - 420, 20)

        # Text widget para resposta
        self.text = QtWidgets.QLabel(self)
        self.text.setStyleSheet("color: white; background: rgba(0,0,0,0.7);")
        self.text.setAlignment(QtCore.Qt.AlignTop)
        self.text.setWordWrap(True)
        self.text.setGeometry(0, 0, 400, QtWidgets.QApplication.primaryScreen().size().height() - 40)

        self.show()
        self.exclude_from_capture()

    def exclude_from_capture(self):
        WS_EX_NOACTIVATE  = 0x08000000
        WS_EX_TRANSPARENT = 0x00000020
        GWL_EXSTYLE       = -20

        hwnd = self.winId().__int__()
        old_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
    hwnd, GWL_EXSTYLE,
    old_style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
)
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)


    def update_text(self, content):
        # Atualiza a resposta invisível
        try:
            self.text.setText(content)
        except Exception as e:
            print(f"Error updating text widget: {e}")
    # Para o menu de configurações (esc+3)
    def show_menu(self, options, idx):
        items = []
        for i, opt in enumerate(options):
            prefix = "→ " if i == idx else "   "
            items.append(f"{prefix}{opt}")
        self.update_text("\n".join(items))

# 4) Funções de captura e envio
class AppController:
    def __init__(self, overlay):
        self.overlay = overlay
        self.conv_id = None
        self.history = []
        self.menu_open = False
        self.menu_opts = [
        "Opacidade",
        "Posição",
        "Modelo do GPT",
        "Configurações Avançadas",
        "Sair"
    ]
        self.menu_idx = 0
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.history = []
            # configurações de overlay
        self.config = {
            'opacity': 0.7,
            'position': 'top-right',
            'model': 'gpt-4.1',
            'port': 43000,
            'margin': (0, 0, 0, 0)
        }
        self.advanced_thread = None


    def screenshot(self):
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])
            img = mss.tools.to_png(shot.rgb, shot.size)
            return img

    def send_to_chatgpt(self, img_bytes, new_chat=False):
        
        # Encode the image to base64
        base64_image = base64.b64encode(img_bytes).decode('utf-8')

        if new_chat:
            self.history = [
                {"role": "system", "content": "Você é um assistente que descreve imagens."}
            ]

        # Construct the message content with text and image
        message_content = [
            {"type": "text", "text": "O que você vê nessa foto?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
        ]

        # Append the new user message with image
        self.history.append({"role": "user", "content": message_content})

        response = self.client.chat.completions.create(
            model=self.config['model'],
            messages=self.history,
        )
        answer = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": answer})
        return answer
    def on_esc1(self):
        def worker():
            img = self.screenshot()  # bytes do PNG         
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.write(img)
            tmp.close()
            try:
                resp = self.send_to_chatgpt(img, new_chat=True)
            finally:
                os.unlink(tmp.name)

    def on_esc2(self):
        def worker():
            img = self.screenshot()
            resp = self.send_to_chatgpt(img, new_chat=False)
            self.overlay.update_text(resp)
        threading.Thread(target=worker, daemon=True).start()

    def on_esc3(self):
        self.menu_open = True
        self.menu_idx = 0
        self.overlay.show_menu(self.menu_opts, self.menu_idx)


    def on_esc9(self):
        # inicia servidor web uma única vez
        if not self.advanced_thread:
            self.advanced_thread = start_web_server(self.config)
        # notifica o usuário
        self.overlay.update_text(
            f"As configurações avançadas estão habilitadas!\n"
            f"Acesse http://localhost:{self.config['port']} em outro dispositivo.\n"
            "Você será redirecionado ao menu principal em 10s."
        )



    def on_esc0(self):
        if self.menu_open:
            self.menu_open = False
            self.overlay.update_text(self.history[-1]["content"] if self.history else "")

    def on_esc_enter(self):
        if self.menu_open:
            opt = self.menu_opts[self.menu_idx]
            # Implementar ação de cada opção aqui...
            if opt == "Sair":
                QtWidgets.QApplication.quit()
            # depois de ação, fecha menu:
            self.on_esc0()

    def on_esc_arrow(self, dir):
        if self.menu_open:
            if dir == "up":
                self.menu_idx = (self.menu_idx - 1) % len(self.menu_opts)
            else:
                self.menu_idx = (self.menu_idx + 1) % len(self.menu_opts)
            self.overlay.show_menu(self.menu_opts, self.menu_idx)

# 5) Boot da aplicação
def main():
    app = QtWidgets.QApplication(sys.argv)
    overlay = Overlay()
    esc = AppController(overlay)

    # Hotkeys globais
    keyboard.add_hotkey('esc+1', esc.on_esc1)
    keyboard.add_hotkey('esc+2', esc.on_esc2)
    keyboard.add_hotkey('esc+3', esc.on_esc3)
    keyboard.add_hotkey('esc+0', esc.on_esc0)
    keyboard.add_hotkey('esc+9', esc.on_esc9) #abrir servidor
    keyboard.add_hotkey('esc+enter', esc.on_esc_enter)
    keyboard.add_hotkey('esc+up',   lambda: esc.on_esc_arrow("up"))
    keyboard.add_hotkey('esc+down', lambda: esc.on_esc_arrow("down"))

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
