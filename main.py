import sys
import io 
import base64
import threading
from dotenv import load_dotenv
import os
import ctypes
from openai import OpenAI
from PyQt5 import QtWidgets, QtCore, QtGui
import keyboard
import mss
from flask import Flask, request, redirect
from ctypes import wintypes
import json
import html
import traceback

# Adições para áudio
try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("AVISO: PyAudio não encontrado. Funcionalidade de gravação de áudio desabilitada.")

# 1) Carrega .env e Configurações
load_dotenv()
CONFIG_FILE = "config.json"

# Constantes WinAPI
WDA_NONE                 = 0x00000000
WDA_MONITOR              = 0x00000001
WDA_EXCLUDEFROMCAPTURE   = 0x00000011
user32 = ctypes.windll.user32

# Constantes de Áudio
AUDIO_FORMAT = pyaudio.paInt16 if PYAUDIO_AVAILABLE else None
AUDIO_CHANNELS = 1; AUDIO_RATE = 16000; AUDIO_CHUNK = 1024
TEMP_AUDIO_FILENAME = "temp_overlay_audio.wav"


# --- Flask Web Server (MODIFICADO PARA DARK MODE E ESTILO) ---
def start_web_server(app_controller_ref):
    app_flask = Flask(__name__)

    @app_flask.route('/', methods=['GET', 'POST'])
    def root():
        config_ref_dict = app_controller_ref.get_config_copy_for_web()
        message_from_post = request.args.get('message', None) # Pega mensagem do redirect

        if request.method == 'POST':
            original_config_for_comparison = dict(config_ref_dict)
            changed_values = {} 
            post_message_feedback = "" # Feedback para redirect

            new_model = request.form.get('gpt_model')
            if new_model is not None and new_model != config_ref_dict.get('model'):
                changed_values['model'] = new_model
            
            opacity_str = request.form.get('opacity')
            if opacity_str is not None:
                try:
                    opacity_val = round(float(opacity_str), 2)
                    if 0.0 <= opacity_val <= 1.0 and opacity_val != config_ref_dict.get('opacity'):
                        changed_values['opacity'] = opacity_val
                except ValueError: post_message_feedback += "Erro opacidade. "

            position_str = request.form.get('position')
            if position_str is not None and position_str != config_ref_dict.get('position'):
                changed_values['position'] = position_str

            current_margin_list = list(config_ref_dict.get('margin', [0,0,0,0]))
            try:
                m_x1 = int(request.form.get('x1', current_margin_list[0]))
                m_y1 = int(request.form.get('y1', current_margin_list[1]))
                m_x2 = int(request.form.get('x2', current_margin_list[2]))
                m_y2 = int(request.form.get('y2', current_margin_list[3]))
                new_margin_list = [m_x1, m_y1, m_x2, m_y2]
                
                if new_margin_list != current_margin_list:
                    if m_x2 > m_x1 and m_y2 > m_y1:
                        changed_values['margin'] = new_margin_list
                        app_controller_ref.signal_show_temporary_margins_on_overlay.emit(new_margin_list)
                        post_message_feedback += f"Margens: X1={m_x1},Y1={m_y1},X2={m_x2},Y2={m_y2}. "
                    else:
                        post_message_feedback += "Erro: Margens inválidas. "
            except ValueError:
                post_message_feedback += "Erro: Margens devem ser números. "

            if changed_values:
                app_controller_ref.web_config_change_requested.emit(changed_values)
                if not post_message_feedback or "Erro" not in post_message_feedback:
                     post_message_feedback = "Configurações salvas! " + post_message_feedback
            
            return redirect(f'/?message={html.escape(post_message_feedback.strip())}')

        margin_vals = config_ref_dict.get('margin', [0,0,0,0])
        if not isinstance(margin_vals, list) or len(margin_vals) != 4: margin_vals = [0,0,0,0]
        
        html_content = f'''
        <!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Configurações OverlayGPT</title><meta http-equiv="refresh" content="45">
            <style>
                :root {{ --bg-color: #1e1e1e; --primary-text-color: #e0e0e0; --secondary-text-color: #b0b0b0; --card-bg-color: #2a2a2a; --input-bg-color: #333333; --input-border-color: #4f4f4f; --button-bg-color: #007acc; --button-hover-bg-color: #005fa3; --accent-color: #007acc; --border-radius: 6px; --font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
                body {{ font-family: var(--font-family); margin: 0; padding: 20px; background-color: var(--bg-color); color: var(--primary-text-color); display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; }}
                .container {{ background-color: var(--card-bg-color); padding: 30px; border-radius: var(--border-radius); box-shadow: 0 8px 25px rgba(0,0,0,0.3); width: 100%; max-width: 550px; }}
                h2 {{ color: var(--accent-color); border-bottom: 2px solid var(--accent-color); padding-bottom: 10px; margin-top: 0; margin-bottom: 25px; text-align: center; font-size: 1.8em; }}
                form label {{ display: block; margin-bottom: 8px; font-weight: 600; color: var(--secondary-text-color); }}
                form input[type="text"], form input[type="number"], form select {{ width: calc(100% - 22px); padding: 10px; margin-bottom: 20px; background-color: var(--input-bg-color); border: 1px solid var(--input-border-color); border-radius: var(--border-radius); color: var(--primary-text-color); box-sizing: border-box; font-size: 0.95em; }}
                .margin-inputs-container {{ display: flex; justify-content: space-between; gap: 10px; margin-bottom: 20px; }}
                .margin-inputs-container input[type="number"] {{ width: calc(25% - 10px); margin-bottom: 0; }}
                button[type="submit"] {{ width: 100%; padding: 12px 20px; background-color: var(--button-bg-color); color: white; border: none; border-radius: var(--border-radius); cursor: pointer; font-size: 1em; font-weight: 600; transition: background-color 0.3s ease; }}
                button[type="submit"]:hover {{ background-color: var(--button-hover-bg-color); }}
                .message {{ padding: 10px; margin-bottom: 15px; border-radius: var(--border-radius); text-align: center; font-size: 0.9em; }}
                .message.success {{ background-color: #2E7D32; color: #C8E6C9; }} /* Verde escuro com texto claro */
                .message.error {{ background-color: #C62828; color: #FFCDD2; }} /* Vermelho escuro com texto claro */
                small {{ color: var(--secondary-text-color); display: block; text-align: center; margin-top: 15px;}}
            </style></head><body><div class="container"><h2>Configurações Avançadas</h2>
            {'<div class="message success">' + html.escape(message_from_post) + '</div>' if message_from_post and "Erro" not in message_from_post else ''}
            {'<div class="message error">' + html.escape(message_from_post) + '</div>' if message_from_post and "Erro" in message_from_post else ''}
            <form method="post">
                <label for="gpt_model">Modelo GPT Visão:</label><input type="text" id="gpt_model" name="gpt_model" value="{html.escape(str(config_ref_dict.get('model','')))}"/>
                <label>Margem da Captura (X1, Y1, X2, Y2):</label><div class="margin-inputs-container">
                    <input type="number" name="x1" value="{margin_vals[0]}" placeholder="X1" title="X inicial"/>
                    <input type="number" name="y1" value="{margin_vals[1]}" placeholder="Y1" title="Y inicial"/>
                    <input type="number" name="x2" value="{margin_vals[2]}" placeholder="X2" title="X final"/>
                    <input type="number" name="y2" value="{margin_vals[3]}" placeholder="Y2" title="Y final"/></div>
                <label for="opacity">Opacidade do Overlay (0.0 - 1.0):</label><input type="number" id="opacity" step="0.05" name="opacity" min="0" max="1" value="{config_ref_dict.get('opacity',0.7):.2f}"/>
                <label for="position">Posição do Overlay:</label><select id="position" name="position">
                    <option value="top-right" {"selected" if config_ref_dict.get('position') == 'top-right' else ""}>Canto Sup. Direito</option>
                    <option value="top-left" {"selected" if config_ref_dict.get('position') == 'top-left' else ""}>Canto Sup. Esquerdo</option>
                    <option value="bottom-right" {"selected" if config_ref_dict.get('position') == 'bottom-right' else ""}>Canto Inf. Direito</option>
                    <option value="bottom-left" {"selected" if config_ref_dict.get('position') == 'bottom-left' else ""}>Canto Inf. Esquerdo</option></select>
                <button type="submit">Salvar Configurações</button></form>
            <small>A página será atualizada em 45s.</small></div></body></html>'''
        return html_content
    
    flask_port_from_config = app_controller_ref.get_config_value('port')
    thread = threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=flask_port_from_config, debug=False, use_reloader=False), daemon=True)
    thread.start()
    return thread

# --- Overlay (QtWidget) ---
class Overlay(QtWidgets.QWidget):
    def __init__(self, initial_config_dict):
        super().__init__(None, QtCore.Qt.WindowStaysOnTopHint | 
                               QtCore.Qt.FramelessWindowHint | 
                               QtCore.Qt.Tool)
        
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating) # Não rouba foco

        # >>> ADIÇÃO 1: Atributo Qt para transparência de mouse <<<
        # self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        # Nota: WA_TransparentForMouseEvents pode ser suficiente em alguns casos, mas WS_EX_TRANSPARENT é mais forte.
        # Se você definir WS_EX_TRANSPARENT (abaixo), WA_TransparentForMouseEvents pode se tornar redundante ou até conflitante.
        # Teste com e sem esta linha se WS_EX_TRANSPARENT por si só não for ideal (embora geralmente seja).

        # ... (resto do seu __init__ para text_label, etc.)
        self.current_config = dict(initial_config_dict) 
        self.screen_geom = QtWidgets.QApplication.primaryScreen().geometry()
        self.text_label = QtWidgets.QLabel(self)
        self.text_label.setStyleSheet(
            "color: white; background: rgba(20,20,20,0.85); padding: 10px; "
            "border-radius: 8px; font-size: 10pt; border: 1px solid rgba(255,255,255,0.15);"
        )
        self.text_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.text_label.setWordWrap(True)
        # IMPORTANTE: Se a janela for WS_EX_TRANSPARENT, os links dentro do QLabel não serão clicáveis
        # porque a janela inteira não processará cliques. Se precisar de links clicáveis, esta
        # abordagem de "click-through total" não funcionará para os links.
        self.text_label.setOpenExternalLinks(False) # Desabilitar se for tornar a janela totalmente transparente para cliques

        self.apply_geometry_from_config(self.current_config)
        self.show()
        
        # É crucial aplicar o WS_EX_TRANSPARENT DEPOIS que a janela é mostrada e tem um HWND válido.
        QtCore.QTimer.singleShot(50, self.make_window_click_through) # Um pequeno delay para garantir HWND

    def make_window_click_through(self):
        """Aplica o estilo WS_EX_TRANSPARENT para tornar a janela não clicável."""
        try:
            hwnd = self.winId().__int__() # ou int(self.winId())
            if not hwnd:
                print("Overlay HWND não disponível para make_window_click_through.")
                # Tentar novamente se o HWND ainda não estiver pronto
                QtCore.QTimer.singleShot(100, self.make_window_click_through)
                return

            # Constantes WinAPI para estilos estendidos
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000  # Necessário para SetLayeredWindowAttributes se você for usar
            WS_EX_TRANSPARENT = 0x00000020 # Chave para o "click-through"

            # Obter o estilo estendido atual
            current_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            # Adicionar WS_EX_TRANSPARENT
            # Nota: Se você já usa WA_TranslucentBackground com Qt, a janela já é "layered" de certa forma.
            # Adicionar WS_EX_LAYERED explicitamente pode não ser necessário, ou pode já estar implícito.
            # WS_EX_TRANSPARENT é a flag principal aqui.
            new_ex_style = current_ex_style | WS_EX_TRANSPARENT
            
            if not user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style):
                print(f"Falha ao definir SetWindowLongW com WS_EX_TRANSPARENT. Erro: {ctypes.get_last_error()}")
            else:
                print(f"Overlay (HWND: {hwnd}): Estilo WS_EX_TRANSPARENT aplicado para click-through.")
            
            # Opcional: Se você também quiser transparência alfa para a janela inteira (não apenas o fundo)
            # e o WA_TranslucentBackground não estiver fazendo o efeito desejado junto com WS_EX_TRANSPARENT.
            # Geralmente, WA_TranslucentBackground + WS_EX_TRANSPARENT funciona bem.
            # Se for definir transparência alfa com SetLayeredWindowAttributes, a janela PRECISA ter WS_EX_LAYERED.
            # E a opacidade definida pelo Qt (setWindowOpacity) pode interagir de forma complexa.
            #
            # user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current_ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            # opacity_level_winapi = int(self.windowOpacity() * 255) # Converter opacidade Qt para escala WinAPI (0-255)
            # user32.SetLayeredWindowAttributes(hwnd, 0, opacity_level_winapi, 0x00000002) # LWA_ALPHA
            # Se fizer isso, a opacidade do Qt pode não funcionar mais como esperado.

        except Exception as e:
            print(f"Erro crítico ao tornar a janela click-through: {e}\n{traceback.format_exc()}")


    def exclude_from_capture(self):
        """Configura a afinidade de exibição e outros estilos para 'stealth'."""
        try:
            hwnd = self.winId().__int__()
            if not hwnd: 
                print("Overlay HWND não disponível para exclude_from_capture.")
                # Poderia tentar novamente, mas make_window_click_through já tem um retry
                return

            # Configuração para não ser capturado (Display Affinity)
            if hasattr(user32, 'SetWindowDisplayAffinity'):
                WDA_EXCLUDEFROMCAPTURE = 0x00000011
                WDA_MONITOR = 0x00000001
                if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                    ctypes.set_last_error(0) # Limpa o erro
                    if not user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
                         print(f"Falha ao definir DisplayAffinity para MONITOR. Erro: {ctypes.get_last_error()}")
                    else:
                        print(f"Overlay (HWND: {hwnd}): DisplayAffinity = MONITOR.")
                else:
                    print(f"Overlay (HWND: {hwnd}): DisplayAffinity = EXCLUDEFROMCAPTURE.")
            else:
                print("SetWindowDisplayAffinity não encontrado.")

            # Estilos adicionais para 'stealth' e comportamento da janela
            # (WS_EX_TRANSPARENT será aplicado por make_window_click_through)
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080  # Não aparece na barra de tarefas nem no Alt+Tab
            WS_EX_NOACTIVATE = 0x08000000  # Janela não se torna ativa (não recebe foco do teclado)
            
            current_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # Aplicar estilos exceto WS_EX_TRANSPARENT aqui, pois será feito em make_window_click_through
            new_ex_style_base = current_ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            
            if not user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style_base):
                print(f"Falha ao definir SetWindowLongW (base). Erro: {ctypes.get_last_error()}")
            else:
                print(f"Overlay (HWND: {hwnd}): Estilos WS_EX_NOACTIVATE e WS_EX_TOOLWINDOW aplicados.")

        except Exception as e:
            print(f"Erro crítico ao configurar estilos de janela/afinidade: {e}\n{traceback.format_exc()}")

    def apply_geometry_from_config(self, config_dict):
        self.current_config = dict(config_dict) 
        self.setWindowOpacity(self.current_config.get('opacity', 0.8))
        overlay_width = self.current_config.get('overlay_width', 420)
        v_offset = self.current_config.get('overlay_v_offset', 25)
        h_offset = self.current_config.get('overlay_h_offset', 25)
        overlay_height_ratio = self.current_config.get('overlay_height_ratio', 0.85)
        overlay_height = (self.screen_geom.height() - (2 * v_offset)) * overlay_height_ratio
        position_str = self.current_config.get('position', 'top-right')
        
        pos_x, pos_y = 0,0 
        if position_str == 'top-right':
            pos_x = self.screen_geom.width() - overlay_width - h_offset; pos_y = v_offset
        elif position_str == 'top-left':
            pos_x = h_offset; pos_y = v_offset
        elif position_str == 'bottom-right':
            pos_x = self.screen_geom.width() - overlay_width - h_offset; pos_y = self.screen_geom.height() - overlay_height - v_offset 
        elif position_str == 'bottom-left':
            pos_x = h_offset; pos_y = self.screen_geom.height() - overlay_height - v_offset
        else: 
            pos_x = self.screen_geom.width() - overlay_width - h_offset; pos_y = v_offset

        self.setGeometry(int(pos_x), int(pos_y), int(overlay_width), int(overlay_height))
        if hasattr(self, 'text_label'):
             self.text_label.setGeometry(0, 0, int(overlay_width), int(overlay_height))

    def exclude_from_capture(self):
        try:
            hwnd = self.winId().__int__()
            if not hwnd: return
            if hasattr(user32, 'SetWindowDisplayAffinity'):
                # Tenta EXCLUDEFROMCAPTURE, se falhar (ou não existir), tenta MONITOR
                if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                    # Se SetWindowDisplayAffinity retornar 0 (falha), tentamos WDA_MONITOR
                    # Limpa o erro antes de tentar a segunda opção.
                    ctypes.set_last_error(0)
                    if not user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
                         print(f"Falha ao definir DisplayAffinity para MONITOR. Erro: {ctypes.get_last_error()}")
            GWL_EXSTYLE = -20; WS_EX_TOOLWINDOW = 0x00000080; WS_EX_NOACTIVATE = 0x08000000
            new_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
        except Exception as e:
            print(f"Erro ao configurar estilos de janela/afinidade: {e}\n{traceback.format_exc()}")

    @QtCore.pyqtSlot(str)
    def update_text_display(self, content_html_str):
        try:
            if self.text_label: self.text_label.setText(content_html_str)
        except Exception as e: print(f"Erro update_text_display: {e}")


    @QtCore.pyqtSlot(list, int)
    def show_menu_display_slot(self, options_list_str, selected_idx_int):
        menu_html = "<div style='padding:5px;'>"
        menu_html += "<p style='margin-bottom:10px; font-weight:bold; color:#90CAF9;'>MENU:</p><ul style='list-style:none; padding-left:0;'>"
        for i, opt_text_str in enumerate(options_list_str):
            style = "padding:4px 2px; padding-left:10px; border-radius:4px;"
            prefix = "    " 
            suffix = ""
            if i == selected_idx_int:
                style += "background-color:rgba(144, 202, 249, 0.25); border-left:3px solid #90CAF9;"
                prefix = "<b>→ </b>"
            menu_html += f"<li style='{style}'>{prefix}{html.escape(opt_text_str)}{suffix}</li>"
        menu_html += "</ul><p style='font-size:9pt; color:#BDBDBD; margin-top:15px; text-align:center;'><small>(Setas: Navegar | Enter: Sel. | ESC+0: Fechar)</small></p>"
        menu_html += "</div>"
        self.update_text_display(menu_html)
        # --- App Controller (Lógica Principal) ---
import sys
import io 
import base64
import threading
from dotenv import load_dotenv
import os
import ctypes
from openai import OpenAI # Garanta que a importação está correta
from PyQt5 import QtWidgets, QtCore, QtGui
import keyboard
import mss
# from flask import Flask, request, redirect # Removido pois AppController não usa diretamente
# from ctypes import wintypes # Removido se não usado diretamente em AppController
import json
import html
import traceback

# Adições para áudio (PYAUDIO_AVAILABLE e constantes de áudio devem estar definidas globalmente ou importadas)
try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    # print("AVISO: PyAudio não encontrado...") # Já impresso no main

# Constantes de Áudio - assumindo que estão definidas globalmente como no script anterior
# AUDIO_FORMAT = pyaudio.paInt16 if PYAUDIO_AVAILABLE else None
# AUDIO_CHANNELS = 1; AUDIO_RATE = 16000; AUDIO_CHUNK = 1024
# TEMP_AUDIO_FILENAME = "temp_overlay_audio.wav"
# Para referência dentro da classe, se precisar delas.
# Se for usar de forma mais isolada, elas deveriam ser passadas ou acessadas de uma config.


# --- App Controller (Lógica Principal) ---
class AppController(QtCore.QObject):
    signal_update_overlay_content = QtCore.pyqtSignal(str)
    signal_update_menu_display = QtCore.pyqtSignal(list, int)
    signal_set_temporary_message = QtCore.pyqtSignal(str, int)
    signal_apply_config_to_overlay = QtCore.pyqtSignal(dict)
    signal_toggle_processing_flag = QtCore.pyqtSignal(bool)
    web_config_change_requested = QtCore.pyqtSignal(dict)
    signal_show_temporary_margins_on_overlay = QtCore.pyqtSignal(list)

    _chat_hotkeys_globally_enabled = True

    def __init__(self, overlay_qt_widget):
        super().__init__()
        self.overlay = overlay_qt_widget # Referência ao widget do overlay
        self.history = []
        self.menu_is_active = False
        self.menu_options_list = [
            "Alternar Opacidade", "Alternar Posição", "Alternar Modelo GPT Visão",
            "Margens (via Web)", "Configurações Web (CTRL+9)", "Sair"
        ]
        self.current_menu_selection_idx = 0
        
        # Inicialização do cliente OpenAI
        try:
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            if not os.getenv("OPENAI_API_KEY"): 
                raise ValueError("Chave OPENAI_API_KEY não encontrada no arquivo .env.")
        except Exception as e_openai:
            print(f"ERRO CRÍTICO - Inicialização OpenAI Falhou: {e_openai}")
            self.openai_client = None # Define como None para checagens posteriores
            # Você pode querer emitir um sinal para o overlay mostrar um erro persistente.
            # self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado. Verifique a API KEY.</p>", 0) # 0 para persistir

        self._config_lock = threading.Lock() # Para acesso thread-safe à config
        self.config = self.load_config_from_json() # Carrega as configs do JSON
        
        # Conexão de Sinais e Slots
        self.signal_update_overlay_content.connect(self.overlay.update_text_display)
        self.signal_update_menu_display.connect(self.overlay.show_menu_display_slot)
        self.signal_set_temporary_message.connect(self._set_temporary_message_slot)
        self.signal_apply_config_to_overlay.connect(self.overlay.apply_geometry_from_config)
        self.signal_toggle_processing_flag.connect(self._set_processing_flag_slot)
        self.web_config_change_requested.connect(self.handle_web_config_change)
        self.signal_show_temporary_margins_on_overlay.connect(self.display_margins_temporarily_on_overlay_slot)

        # Aplica a configuração inicial ao overlay através de um sinal
        self.signal_apply_config_to_overlay.emit(dict(self.config))

        self.flask_server_thread_obj = None # Thread para o servidor Flask
        self.is_currently_processing_chatgpt = False # Flag global de processamento da IA
        self._temporary_message_active = False # Flag para mensagens temporárias no overlay
        
        # Timer para limpar mensagens temporárias
        self.temporary_state_clear_timer = QtCore.QTimer(self)
        self.temporary_state_clear_timer.setSingleShot(True)
        self.temporary_state_clear_timer.timeout.connect(self.clear_temporary_message_and_restore_chat_view)

        # Atributos para gravação de áudio
        self.is_recording_audio = False
        self.audio_recorder_thread = None # Thread para gravação de áudio
        self.stop_audio_recording_event = threading.Event() # Evento para parar a gravação
        self.audio_frames_buffer = [] # Buffer para os frames de áudio

    def get_config_copy_for_web(self):
        """Retorna uma cópia thread-safe da configuração para a interface web."""
        with self._config_lock: 
            return dict(self.config)

    def get_config_value(self, key, default=None):
        """Retorna um valor específico da configuração de forma thread-safe."""
        with self._config_lock: 
            return self.config.get(key, default)

    @QtCore.pyqtSlot(dict)
    def handle_web_config_change(self, changed_values_from_web):
        """Lida com as mudanças de configuração vindas da interface web."""
        config_actually_updated = False
        with self._config_lock:
            for key, value in changed_values_from_web.items():
                if key in self.config: 
                    if self.config[key] != value:
                        self.config[key] = value
                        config_actually_updated = True
        if config_actually_updated:
            self.save_config() # Salva a config no disco
            self.signal_apply_config_to_overlay.emit(dict(self.config)) # Aplica na UI

    def load_config_from_json(self):
        """Carrega as configurações do arquivo JSON ou usa defaults."""
        global CONFIG_FILE # Acessa a variável global
        with self._config_lock:
            default_cfg = {
                'opacity': 0.8, 'position': 'top-right', 'model': 'gpt-4o', # Visão
                'port': 43000, 'margin': [0, 0, 0, 0], 'overlay_width': 420,
                'overlay_v_offset': 25, 'overlay_h_offset': 25, 
                'max_chat_history_pairs': 7, # Reduzido para acomodar msgs mais longas (imagem+texto)
                'vision_detail_level': 'auto', # 'low', 'high', ou 'auto'
                'api_max_tokens': 300, # Aumentado um pouco para multimodal
                'overlay_height_ratio': 0.85,
                'whisper_model': 'whisper-1',
                'chat_model': 'gpt-4o' # Usar gpt-4o para chat multimodal também
            }
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f: loaded_cfg = json.load(f)
                    for key, value in default_cfg.items():
                        if key not in loaded_cfg: loaded_cfg[key] = value
                    # Validação de margem
                    margin_val = loaded_cfg.get('margin', default_cfg['margin'])
                    if not (isinstance(margin_val, list) and len(margin_val) == 4 and all(isinstance(x, (int, float)) for x in margin_val)):
                        loaded_cfg['margin'] = default_cfg['margin']
                    return loaded_cfg
                else: # Se o arquivo não existe, cria com defaults
                    with open(CONFIG_FILE, 'w') as f: json.dump(default_cfg, f, indent=4)
                    return default_cfg
            except Exception as e:
                print(f"ERRO ao carregar/criar '{CONFIG_FILE}': {e}. Usando defaults.\n{traceback.format_exc()}")
                return default_cfg
    
    def save_config(self, config_to_save=None):
        """Salva a configuração atual no arquivo JSON."""
        global CONFIG_FILE
        try:
            with self._config_lock:
                cfg_data = config_to_save if config_to_save else self.config
                with open(CONFIG_FILE, 'w') as f: json.dump(cfg_data, f, indent=4)
        except Exception as e: 
            print(f"ERRO ao salvar configurações: {e}\n{traceback.format_exc()}")
    
    @QtCore.pyqtSlot(bool)
    def _set_processing_flag_slot(self, state: bool):
        """Define o estado do flag de processamento da IA."""
        self.is_currently_processing_chatgpt = state

    @QtCore.pyqtSlot(str, int)
    def _set_temporary_message_slot(self, html_message, duration_ms):
        """Exibe uma mensagem temporária no overlay."""
        if self.temporary_state_clear_timer.isActive():
            self.temporary_state_clear_timer.stop()
        self.signal_update_overlay_content.emit(html_message)
        self._temporary_message_active = True
        if duration_ms > 0: # 0 ou negativo significa persistente até ser limpo
            self.temporary_state_clear_timer.start(duration_ms)

    def clear_temporary_message_and_restore_chat_view(self):
        """Limpa a mensagem temporária e restaura a visão do chat ou menu."""
        self.temporary_state_clear_timer.stop()
        self._temporary_message_active = False
        if self.menu_is_active:
            self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        elif self.is_recording_audio: # Se ainda estiver gravando (improvável aqui, mas por segurança)
             self.signal_update_overlay_content.emit("<p style='color:#FFEB3B; text-align:center;'>🎙️ Gravando... (ESC+4)</p>")
        else:
            self.display_last_chat_message_or_default()

    @QtCore.pyqtSlot(list)
    def display_margins_temporarily_on_overlay_slot(self, margins_list):
        """Exibe as dimensões das margens temporariamente no overlay."""
        if len(margins_list) == 4:
            x1, y1, x2, y2 = margins_list
            width = x2 - x1; height = y2 - y1
            margin_text = (f"<div style='text-align:center; padding:10px; border:1px solid #00E676; background:rgba(0,0,0,0.75); border-radius:5px;'>"
                           f"<h4 style='color:#69F0AE; margin:0 0 5px 0;'>Margens Atualizadas</h4>" # Cor mais vibrante
                           f"<p style='margin:2px 0; color:#E0E0E0;'>X1: {x1}, Y1: {y1}</p>"
                           f"<p style='margin:2px 0; color:#E0E0E0;'>X2: {x2}, Y2: {y2}</p>"
                           f"<p style='margin:2px 0; color:#E0E0E0;'>W: {width}, H: {height}</p>"
                           f"</div>")
            self.signal_set_temporary_message.emit(margin_text, 5000) # Exibe por 5 segundos

    def take_screenshot_bytes_for_api(self):
        """Captura a tela (ou uma região definida pelas margens) e retorna os bytes PNG."""
        try:
            with mss.mss() as sct:
                with self._config_lock:
                    margin_list = list(self.config.get('margin', [0,0,0,0]))
                    monitor_idx = self.config.get('capture_monitor_idx', 1) 
                
                target_monitor_mss_idx = monitor_idx if len(sct.monitors) > 1 else 0
                if target_monitor_mss_idx >= len(sct.monitors):
                    print(f"Índice de monitor inválido {target_monitor_mss_idx}, usando default.")
                    target_monitor_mss_idx = 1 if len(sct.monitors) > 1 else 0
                
                base_monitor_details = sct.monitors[target_monitor_mss_idx]
                capture_details = dict(base_monitor_details) # Default: tela cheia do monitor
                
                if isinstance(margin_list, list) and len(margin_list) == 4 and any(m != 0 for m in margin_list):
                    x1, y1, x2, y2 = margin_list; width, height = x2 - x1, y2 - y1
                    if width > 0 and height > 0:
                        custom_left = base_monitor_details["left"] + x1
                        custom_top = base_monitor_details["top"] + y1
                        if (custom_left >= base_monitor_details["left"] and custom_top >= base_monitor_details["top"] and
                            custom_left + width <= base_monitor_details["left"] + base_monitor_details["width"] and
                            custom_top + height <= base_monitor_details["top"] + base_monitor_details["height"]):
                            capture_details = {"top": custom_top, "left": custom_left, "width": width, "height": height, "mon": target_monitor_mss_idx}
                        else: 
                            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Margens fora dos limites. Capturando tela cheia.</p>", 3000)
                    else: 
                        self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Margens inválidas (W/H <=0). Capturando tela cheia.</p>", 3000)
                
                sct_img_obj = sct.grab(capture_details)
                return mss.tools.to_png(sct_img_obj.rgb, sct_img_obj.size)
        except Exception as e:
            print(f"ERRO MSS Captura de Tela: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao capturar tela: {html.escape(str(e))[:50]}</p>", 4000)
            return None

    def _threaded_call_to_openai_vision_api(self, image_bytes_data, is_new_chat_bool):
        """Lida com requisições de análise de imagem para a IA (sem áudio)."""
        if not self.openai_client: self.signal_update_overlay_content.emit("<p style='color:red;text-align:center;'>ERRO: Cliente OpenAI não iniciado.</p>"); return
        if self.is_currently_processing_chatgpt: return 
        
        self.signal_toggle_processing_flag.emit(True)
        self.signal_update_overlay_content.emit("<p style='text-align:center;'>Analisando imagem com IA...</p>")
        base64_image_str = base64.b64encode(image_bytes_data).decode('utf-8')

        if is_new_chat_bool or not self.history or self.history[0]["role"] != "system":
            self.history = [{"role": "system", "content": "Você é um assistente visual. Descreva a imagem de forma concisa e útil."}]
        
        with self._config_lock: # Acessa config de forma segura
            max_hist_pairs = self.config.get('max_chat_history_pairs', 7)
            vision_model_name = self.config.get('model', 'gpt-4o') # 'model' é para visão
            detail_level = self.config.get('vision_detail_level', 'auto')
            max_tokens_api = self.config.get('api_max_tokens', 300)

        user_message_vision = {"role": "user", "content": [ 
            {"type": "text", "text": "Descreva esta imagem."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image_str}", "detail": detail_level }} 
        ]}
        
        current_history_for_api = list(self.history) + [user_message_vision] # Adiciona a nova mensagem
        if len(current_history_for_api) > (max_hist_pairs * 2 + 1): # Limita histórico
             current_history_for_api = [current_history_for_api[0]] + current_history_for_api[-(max_hist_pairs * 2):]
        
        try:
            api_response = self.openai_client.chat.completions.create(
                model=vision_model_name, messages=current_history_for_api, max_tokens=max_tokens_api )
            assistant_reply_str = api_response.choices[0].message.content
            
            # Atualiza o histórico principal
            self.history.append(user_message_vision)
            self.history.append({"role": "assistant", "content": assistant_reply_str})
            if len(self.history) > (max_hist_pairs * 2 + 1): # Mantém o limite
                 self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]
            
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(assistant_reply_str, prefix="🖼️ Visão:"))
        except Exception as e:
            err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro API Visão: {html.escape(str(e))[:100]}</p>"
            self.signal_update_overlay_content.emit(err_msg)
            print(f"ERRO API OpenAI (Visão): {e}\n{traceback.format_exc()}")
        finally: 
            self.signal_toggle_processing_flag.emit(False)

    def _format_gpt_response_for_html_display(self, raw_text_str, prefix=""):
        """Formata a resposta da IA para exibição em HTML no overlay."""
        escaped_html_text = html.escape(raw_text_str)
        prefix_style = "color:#AED581;" # Verde para IA texto padrão
        if "🎙️🖼️" in prefix: prefix_style = "color:#BA68C8;" # Roxo para multimodal
        elif "🎙️" in prefix: prefix_style = "color:#81D4FA;" # Azul para áudio/você
        elif "🖼️" in prefix: prefix_style = "color:#FFB74D;" # Laranja para visão

        prefix_html = f"<strong style='{prefix_style}'>{html.escape(prefix)} </strong>" if prefix else ""
        formatted_text = escaped_html_text.replace(chr(10), '<br/>')
        separator = ""
        if "IA:" in prefix or "Visão:" in prefix or "Multimodal:" in prefix : # Só para respostas da IA
            separator = "<hr style='border:0; height:1px; background:rgba(255,255,255,0.12); margin:8px 0 5px 0;'>"
        
        return f"<div style='padding:2px;'>{separator}{prefix_html}{formatted_text}</div>"

    def _initiate_chatgpt_request(self, is_new_chat_bool): # Função para ESC+1 e ESC+2 (imagem apenas)
        """Inicia uma requisição de análise de imagem (sem áudio)."""
        if not self.openai_client: 
            self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado.</p>",3000)
            return
        if self.menu_is_active or self.is_currently_processing_chatgpt or self.is_recording_audio or not AppController._chat_hotkeys_globally_enabled:
            if self.is_recording_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação de áudio (ESC+4) primeiro.</p>", 2500)
            return
        
        image_bytes = self.take_screenshot_bytes_for_api()
        if image_bytes:
            threading.Thread(target=self._threaded_call_to_openai_vision_api, args=(image_bytes, is_new_chat_bool), daemon=True).start()

    # --- Lógica de Áudio + Visão (ESC+4) ---
    def on_hotkey_esc_4_audio_toggle(self):
        """Alterna a gravação de áudio. Ao parar, captura tela e envia ambos para a IA."""
        try:
            global PYAUDIO_AVAILABLE # Acessa a flag global
            if not PYAUDIO_AVAILABLE: 
                self.signal_set_temporary_message.emit("<p style='color:orange; text-align:center;'>PyAudio não instalado. Tente 'pip install pyaudio'.</p>", 3500); return
            if not self.openai_client: 
                self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado.</p>",3000); return
            if self.menu_is_active or self.is_currently_processing_chatgpt: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Menu ou IA está ocupado. Aguarde.</p>", 2500); return

            if self.is_recording_audio: # Se está gravando, para
                self.stop_audio_recording_event.set() 
            else: # Se não está gravando, começa
                self.is_recording_audio = True
                self.audio_frames_buffer = [] 
                self.stop_audio_recording_event.clear()
                self.signal_update_overlay_content.emit("<p style='color:#FFEB3B; text-align:center;'>🎙️ Gravando áudio e preparando tela... (ESC+4 para parar)</p>")
                
                self.audio_recorder_thread = threading.Thread(target=self._threaded_record_audio, daemon=True)
                self.audio_recorder_thread.start()
        except Exception as e:
            self.is_recording_audio = False # Garante reset do estado
            print(f"ERRO ESC+4: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro na gravação: {html.escape(str(e))[:50]}</p>", 3000)

    def _threaded_record_audio(self):
        """Grava áudio em uma thread e, ao finalizar, captura a tela."""
        pa_audio = None; audio_stream = None # Renomeado para evitar conflito com stream de imagem
        captured_screenshot_bytes = None # Bytes da imagem capturada
        global AUDIO_FORMAT, AUDIO_CHANNELS, AUDIO_RATE, AUDIO_CHUNK # Acessa globais de áudio
        try:
            pa_audio = pyaudio.PyAudio()
            audio_stream = pa_audio.open(format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, input=True, frames_per_buffer=AUDIO_CHUNK)
            
            while not self.stop_audio_recording_event.is_set() and self.is_recording_audio:
                data = audio_stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                self.audio_frames_buffer.append(data)
            
            if self.stop_audio_recording_event.is_set(): # Se parou pelo evento
                self.signal_update_overlay_content.emit("<p style='text-align:center;'>Áudio gravado. Capturando tela agora...</p>")
                captured_screenshot_bytes = self.take_screenshot_bytes_for_api() # Captura a tela
                if not captured_screenshot_bytes:
                     self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Falha ao capturar tela. Tentando enviar apenas áudio.</p>", 3500)
            
        except Exception as e:
            print(f"ERRO PyAudio na gravação: {e}\n{traceback.format_exc()}"); self.is_recording_audio = False
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro PyAudio: {html.escape(str(e))[:50]}</p>", 4000); return
        finally:
            if audio_stream: audio_stream.stop_stream(); audio_stream.close()
            if pa_audio: pa_audio.terminate()
        
        self.is_recording_audio = False # Reseta o flag de gravação
        
        if self.stop_audio_recording_event.is_set(): # Processa somente se parou pelo evento
             if not self.audio_frames_buffer: 
                self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Nenhum áudio gravado para processar.</p>", 3000)
                self.display_last_chat_message_or_default(); return
            
             self.signal_update_overlay_content.emit("<p style='text-align:center;'>Preparando áudio e imagem para IA...</p>")
             threading.Thread(target=self._save_audio_and_process_with_vision, 
                              args=(list(self.audio_frames_buffer), captured_screenshot_bytes), 
                              daemon=True).start()
             self.audio_frames_buffer = [] # Limpa buffer após cópia para thread

    def _save_audio_and_process_with_vision(self, frames_copy, image_bytes_param):
        """Salva o áudio e chama a função para processamento multimodal."""
        if not frames_copy: return
        global TEMP_AUDIO_FILENAME, AUDIO_CHANNELS, AUDIO_FORMAT, AUDIO_RATE
        try:
            with wave.open(TEMP_AUDIO_FILENAME, 'wb') as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                # Precisamos da instância de PyAudio para get_sample_size
                pa_temp = pyaudio.PyAudio()
                wf.setsampwidth(pa_temp.get_sample_size(AUDIO_FORMAT))
                pa_temp.terminate() # Libera instância temporária
                wf.setframerate(AUDIO_RATE)
                wf.writeframes(b''.join(frames_copy))
            
            self._threaded_transcribe_and_call_multimodal_vision(TEMP_AUDIO_FILENAME, image_bytes_param)
        except Exception as e:
            print(f"ERRO ao salvar WAV para processamento multimodal: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao salvar áudio WAV: {html.escape(str(e))[:50]}</p>", 3000)
            self.display_last_chat_message_or_default()

    def _threaded_transcribe_and_call_multimodal_vision(self, audio_filepath, image_bytes_param):
        """Transcreve o áudio e envia texto + imagem para a IA de visão multimodal."""
        self.signal_update_overlay_content.emit("<p style='text-align:center;'>Transcrevendo áudio com Whisper...</p>")
        transcribed_text = ""
        global TEMP_AUDIO_FILENAME # Para deletar o arquivo
        try:
            with open(audio_filepath, "rb") as audio_file_obj:
                with self._config_lock:
                    whisper_model_name = self.config.get('whisper_model', 'whisper-1')
                transcription_response = self.openai_client.audio.transcriptions.create(model=whisper_model_name, file=audio_file_obj)
            transcribed_text = transcription_response.text.strip()

            if not transcribed_text:
                transcribed_text = "Áudio vazio ou sem fala detectável." # Placeholder
                # Não emitir msg de erro se imagem existe, a IA pode descrever a imagem.
                if image_bytes_param:
                     self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Áudio vazio. Processando imagem com contexto de áudio vazio.</p>", 3500)
                else: # Nem áudio nem imagem
                     self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Nem áudio nem imagem para processar.</p>", 3500)
                     self.display_last_chat_message_or_default(); return
        except Exception as e_whisper:
            print(f"ERRO API OpenAI (Whisper): {e_whisper}\n{traceback.format_exc()}")
            transcribed_text = f"Erro ao transcrever áudio: {str(e_whisper)[:50]}"
            # Se Whisper falhar, mas tivermos uma imagem, ainda podemos prosseguir.
            if not image_bytes_param:
                self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro Whisper e sem imagem: {html.escape(str(e_whisper))[:70]}</p>", 4000)
                self.display_last_chat_message_or_default(); return
            else:
                 self.signal_set_temporary_message.emit(f"<p style='color:orange;text-align:center;'>Erro Whisper. Tentando processar imagem com contexto de erro.</p>", 3500)
        finally:
            if os.path.exists(audio_filepath):
                try: os.remove(audio_filepath)
                except Exception as e_del: print(f"ERRO ao deletar {audio_filepath}: {e_del}")

        self.signal_update_overlay_content.emit("<p style='text-align:center;'>Enviando áudio (texto) e imagem para IA...</p>")
        self.signal_toggle_processing_flag.emit(True)

        try:
            with self._config_lock:
                # Para multimodal, usamos o 'model' principal, que deve ser gpt-4o ou similar
                multimodal_model_name = self.config.get('model', 'gpt-4o') 
                max_tokens_api = self.config.get('api_max_tokens', 300)
                max_hist_pairs = self.config.get('max_chat_history_pairs', 7)
                detail_level = self.config.get('vision_detail_level', 'auto')

            user_content_list = []
            # Adapta o prompt de texto para ser mais aberto se o áudio falhou ou estava vazio.
            if "Erro ao transcrever áudio" in transcribed_text or "Áudio vazio" in transcribed_text:
                prompt_text_for_multimodal = f"Considere a imagem. {transcribed_text}" # Informa sobre o estado do áudio
            else:
                prompt_text_for_multimodal = f"Aqui está o que foi dito: '{transcribed_text}'. Agora, por favor, olhe para a imagem e responda levando em consideração o áudio e a imagem."
            
            user_content_list.append({"type": "text", "text": prompt_text_for_multimodal})

            if image_bytes_param:
                base64_image_str = base64.b64encode(image_bytes_param).decode('utf-8')
                user_content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image_str}", "detail": detail_level }})
            elif not image_bytes_param and ("Erro ao transcrever áudio" in transcribed_text or "Áudio vazio" in transcribed_text):
                 # Caso raro: falha no áudio E falha na imagem. Não deveríamos chegar aqui se tratado antes.
                 self.signal_set_temporary_message.emit("<p style='color:red; text-align:center;'>Sem áudio ou imagem para processar.</p>", 4000)
                 self.signal_toggle_processing_flag.emit(False); return


            # Gerenciamento do Histórico
            if not self.history or self.history[0]["role"] != "system":
                 self.history = [{"role": "system", "content": "Você é um assistente multimodal. Combine informações de texto e imagem para fornecer respostas úteis."}]
            
            user_message_multimodal = {"role": "user", "content": user_content_list}
            current_history_for_api = list(self.history) + [user_message_multimodal]
            if len(current_history_for_api) > (max_hist_pairs * 2 + 1):
                 current_history_for_api = [current_history_for_api[0]] + current_history_for_api[-(max_hist_pairs * 2):]

            api_response = self.openai_client.chat.completions.create(
                model=multimodal_model_name, messages=current_history_for_api, max_tokens=max_tokens_api)
            assistant_reply_str = api_response.choices[0].message.content
            
            self.history.append(user_message_multimodal)
            self.history.append({"role": "assistant", "content": assistant_reply_str})
            if len(self.history) > (max_hist_pairs * 2 + 1): self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]
            
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(assistant_reply_str, prefix="🎙️🖼️ Multimodal:"))
        except Exception as e_multimodal:
            err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro IA Multimodal: {html.escape(str(e_multimodal))[:80]}</p>"
            self.signal_update_overlay_content.emit(err_msg)
            print(f"ERRO API OpenAI (Multimodal): {e_multimodal}\n{traceback.format_exc()}")
        finally:
            self.signal_toggle_processing_flag.emit(False)

    # --- Callbacks de Hotkeys, Menu, etc. ---
    def _prompt_for_margins(self):
        """Instrui o usuário a usar a interface web para margens."""
        msg = ("<p style='text-align:center;'>Use <b>CTRL+9</b> para configs. web<br/>e ajustar margens por lá.</p>"
               "<p style='text-align:center; font-size:small;'>(Voltando ao menu em 7s...)</p>")
        self.signal_set_temporary_message.emit(msg, 7000)
        
    def on_menu_option_selected_enter(self):
        """Lida com a seleção de uma opção no menu do overlay."""
        try:
            if not self.menu_is_active: return
            if self.is_recording_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação (ESC+4) primeiro.</p>", 2500); return
            
            self.temporary_state_clear_timer.stop() 
            selected_opt_str = self.menu_options_list[self.current_menu_selection_idx]
            feedback_msg_html = ""; config_changed = False; keep_menu_open = True # Default: manter menu para ciclos
            
            with self._config_lock: current_config_copy = dict(self.config)

            if selected_opt_str == "Alternar Opacidade":
                opac_cycle = [0.4, 0.6, 0.8, 1.0]; current_opac = current_config_copy.get('opacity',0.8)
                try: idx = opac_cycle.index(current_opac)
                except ValueError: idx = opac_cycle.index(min(opac_cycle, key=lambda x:abs(x-current_opac))) # Encontra o mais próximo
                current_config_copy['opacity'] = opac_cycle[(idx + 1) % len(opac_cycle)]
                feedback_msg_html = f"Opacidade: {current_config_copy['opacity']*100:.0f}%"; config_changed = True
            elif selected_opt_str == "Alternar Posição":
                pos_cycle = ['top-right', 'top-left', 'bottom-right', 'bottom-left']; current_pos = current_config_copy.get('position','top-right')
                try: idx = pos_cycle.index(current_pos)
                except ValueError: idx = -1 # Default para o próximo do primeiro
                current_config_copy['position'] = pos_cycle[(idx + 1) % len(pos_cycle)]
                feedback_msg_html = f"Posição: {current_config_copy['position'].replace('-', ' ').title()}"; config_changed = True
            elif selected_opt_str == "Alternar Modelo GPT Visão":
                # Estes são os modelos usados para multimodal também (model principal)
                model_cycle = ["gpt-4o", "gpt-4-turbo"] # Simplificado, gpt-4-vision-preview é mais antigo
                current_model = current_config_copy.get('model', 'gpt-4o')
                try: idx = model_cycle.index(current_model)
                except ValueError: idx = -1 
                current_config_copy['model'] = model_cycle[(idx + 1) % len(model_cycle)]
                current_config_copy['chat_model'] = current_config_copy['model'] # Sincroniza o chat_model com o de visão se for gpt-4o
                feedback_msg_html = f"Modelo Visão/Multimodal: {current_config_copy['model']}"; config_changed = True
            elif selected_opt_str == "Margens (via Web)": 
                self._prompt_for_margins(); return # Não fecha menu, tem timer próprio
            elif selected_opt_str == "Configurações Web (CTRL+9)": 
                self.on_hotkey_web_config(); return # Também não fecha menu
            elif selected_opt_str == "Sair": 
                self.save_config(); QtWidgets.QApplication.quit(); return
            else: # Opção não tratada, fecha o menu
                keep_menu_open = False

            if config_changed:
                with self._config_lock: self.config.update(current_config_copy) # Aplica mudanças à config principal
                self.save_config()
                self.signal_apply_config_to_overlay.emit(dict(current_config_copy)) # Emite cópia para overlay

            if feedback_msg_html: 
                self.signal_set_temporary_message.emit(f"<p style='text-align:center;'>{feedback_msg_html}</p>", 2000)
                # O menu será reexibido pelo callback de clear_temporary_message se keep_menu_open for True (implícito aqui)
            elif not keep_menu_open : # Se não teve feedback E não é pra manter aberto
                self.menu_is_active = False; AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
        except Exception as e: 
            print(f"ERRO Menu Enter: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit("<p style='color:red;text-align:center'>Erro ao processar opção do menu.</p>", 3000)
            
    def display_last_chat_message_or_default(self):
        """Exibe a última mensagem do chat da IA ou uma mensagem padrão."""
        if self._temporary_message_active or self.is_recording_audio : return # Não sobrescreve
        if self.is_currently_processing_chatgpt: 
             self.signal_update_overlay_content.emit("<p style='text-align:center;'>Processando com IA...</p>"); return
        
        last_assistant_msg_str = ""; prefix = "🤖 IA:" # Default
        if self.history: # Verifica se há histórico
            for msg_idx in range(len(self.history) - 1, -1, -1): # Itera de trás para frente
                msg = self.history[msg_idx]
                if msg["role"] == "assistant":
                    last_assistant_msg_str = msg["content"]
                    # Heurística para prefixo (Visão, Multimodal, Texto)
                    if msg_idx > 0: # Precisa ter uma mensagem de usuário antes
                        prev_user_msg = self.history[msg_idx - 1]
                        if prev_user_msg["role"] == "user" and isinstance(prev_user_msg.get("content"), list):
                            is_vision_only = True; is_multimodal = False
                            for item in prev_user_msg["content"]:
                                if isinstance(item, dict):
                                    if item.get("type") == "image_url": is_multimodal = True # Tem imagem
                                    if item.get("type") == "text" and ("Áudio" in item.get("text", "") or "áudio" in item.get("text", "") or "fala" in item.get("text","")):
                                        is_vision_only = False # Se tem texto falando de áudio, não é só visão
                            if is_multimodal and not is_vision_only: # Se tem imagem e texto relacionado a áudio
                                prefix = "🎙️🖼️ Multimodal:"
                            elif is_multimodal : # Se tem imagem mas o texto não sugere áudio, assume visão
                                prefix = "🖼️ Visão:"
                    self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(last_assistant_msg_str, prefix=prefix))
                    return # Sai após exibir a última
        
        # Se não há histórico de assistente, mostra mensagem padrão
        self.signal_update_overlay_content.emit("<p style='text-align:center; font-size:9.5pt; color:#ccc;'>"
                                               "<span style='color:#FFB74D;'>ESC+1</span>: Visão | <span style='color:#AED581;'>ESC+3</span>: Menu<br>"
                                               "<span style='color:#BA68C8;'>ESC+4</span>: Áudio+Tela → IA | <span style='color:#CE93D8;'>CTRL+9</span>: Web</p>")
    
    def on_hotkey_esc_1(self): # Imagem (Novo chat)
        try: self._initiate_chatgpt_request(True)
        except Exception as e: print(f"ERRO ESC+1: {e}\n{traceback.format_exc()}")
    def on_hotkey_esc_2(self): # Imagem (Continuar chat)
        try: self._initiate_chatgpt_request(False)
        except Exception as e: print(f"ERRO ESC+2: {e}\n{traceback.format_exc()}")
    def on_hotkey_esc_3_menu_toggle(self):
        """Alterna a visibilidade do menu."""
        try:
            if self.is_currently_processing_chatgpt or self.is_recording_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>IA ou Gravação ocupada. Aguarde.</p>", 2000); return
            self.menu_is_active = not self.menu_is_active
            AppController._chat_hotkeys_globally_enabled = not self.menu_is_active # Desabilita ESC+1/2/4 com menu ativo
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop() # Garante que não há msgs temporárias
                self.current_menu_selection_idx = 0
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
            else: # Saindo do menu
                self.display_last_chat_message_or_default()
        except Exception as e: print(f"ERRO ESC+3: {e}\n{traceback.format_exc()}")

    def on_hotkey_esc_0_exit_menu_or_clear(self):
        """Fecha o menu ou limpa o overlay se nenhuma outra ação estiver pendente."""
        try:
            if self.menu_is_active:
                self.menu_is_active = False; AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
            elif not self.is_currently_processing_chatgpt and not self.is_recording_audio: 
                self.signal_update_overlay_content.emit("") # Limpa overlay
            elif self.is_recording_audio: # Se gravando, ESC+0 não faz nada (ESC+4 para)
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Use ESC+4 para parar a gravação de áudio.</p>", 2500)
            # Se processando IA, ESC+0 também não deve limpar.
        except Exception as e: print(f"ERRO ESC+0: {e}\n{traceback.format_exc()}")

    def on_hotkey_web_config(self): # Para CTRL+9
        """Abre a interface web de configurações."""
        try:
            # Permite abrir mesmo se OpenAI não estiver configurado, para caso a config da key seja feita pela web.
            if self.menu_is_active: self.on_hotkey_esc_3_menu_toggle() # Fecha menu se aberto
            if self.is_recording_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação (ESC+4) antes.</p>", 2500); return
            
            # Global para start_web_server vir do main
            # Precisa de uma referência ao start_web_server ou que a thread seja iniciada de outra forma
            # Assume-se que self.start_web_server_func é uma referência para a função global start_web_server
            # Essa referência precisa ser passada durante a inicialização de AppController
            # Ou, mais simples, a função `start_web_server` pode ser importada aqui se for definida em outro módulo.
            # Por agora, vou assumir que está no escopo global ou que é resolvida.

            # if hasattr(self, 'start_web_server_func'): # Se a função foi injetada
            flask_port = self.get_config_value('port', 43000); flask_url = f"http://127.0.0.1:{flask_port}"; msg_extra = ""
            # Como `start_web_server` não é um método de AppController,
            # ele precisa ser chamado do escopo onde está definido (main).
            # A lógica de iniciar o servidor Flask fica melhor no main.py
            # O hotkey pode apenas notificar o main ou exibir o link.
            # Para simplicidade aqui, se a thread já existe, só mostra o link.
            # Se não, assume que o main a iniciará.
            
            if not self.flask_server_thread_obj or not self.flask_server_thread_obj.is_alive():
                 # Idealmente, o `main` deveria cuidar de iniciar o flask_server_thread_obj na primeira chamada.
                 # Ou a função é passada como argumento para AppController.
                 # Vamos simular que já foi iniciada se não nula, ou mostrar que precisa ser.
                 if not hasattr(self, '_flask_initiated_once'): # Para evitar múltiplas threads de start_web_server do controller
                    if 'start_web_server' in globals(): # Checa se a função global existe
                        self.flask_server_thread_obj = globals()['start_web_server'](self) # Chama a global
                        self._flask_initiated_once = True
                        msg_extra = "Servidor de config. iniciado!"
                    else:
                        msg_extra = "Erro: Função start_web_server não encontrada."
                 else:
                     msg_extra = "Servidor de config. (re)iniciado ou já rodando." # Mensagem genérica se já tentou antes
            else:
                 msg_extra = "Servidor de config. já está rodando!"
                
            msg_html = (f"<div style='text-align:center;'><p>{msg_extra}<br/>"
                        f"Acesse: <a href='{flask_url}' style='color:#81D4FA;text-decoration:underline;'>{flask_url}</a></p>"
                        f"<p style='font-size:small;'>(Retornando em 15s ou ESC+0)</p></div>")
            self.signal_set_temporary_message.emit(msg_html, 15000)
            # else:
            #    self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>Função para iniciar servidor web não configurada.</p>", 5000)

        except Exception as e: 
            print(f"ERRO CTRL+9 (Web Config): {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao abrir config web: {html.escape(str(e))[:50]}</p>", 4000)
            
    def on_menu_navigation_input(self, direction_str_up_down):
        """Lida com a navegação no menu (seta para cima/baixo)."""
        try:
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop() # Cancela mensagens temporárias
                if direction_str_up_down == "up": 
                    self.current_menu_selection_idx = (self.current_menu_selection_idx - 1 + len(self.menu_options_list)) % len(self.menu_options_list)
                else: # "down"
                    self.current_menu_selection_idx = (self.current_menu_selection_idx + 1) % len(self.menu_options_list)
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        except Exception as e: 
            print(f"ERRO Navegação Menu ({direction_str_up_down}):{e}\n{traceback.format_exc()}")
            
    signal_update_overlay_content = QtCore.pyqtSignal(str)
    signal_update_menu_display = QtCore.pyqtSignal(list, int)
    signal_set_temporary_message = QtCore.pyqtSignal(str, int)
    signal_apply_config_to_overlay = QtCore.pyqtSignal(dict)
    signal_toggle_processing_flag = QtCore.pyqtSignal(bool)
    web_config_change_requested = QtCore.pyqtSignal(dict)
    signal_show_temporary_margins_on_overlay = QtCore.pyqtSignal(list)

    _chat_hotkeys_globally_enabled = True

    def __init__(self, overlay_qt_widget):
        super().__init__()
        self.overlay = overlay_qt_widget
        self.history = []
        self.menu_is_active = False
        self.menu_options_list = [
            "Alternar Opacidade", "Alternar Posição", "Alternar Modelo GPT Visão",
            "Margens (via Web)", "Configurações Web (CTRL+9)", "Sair"
        ]
        self.current_menu_selection_idx = 0
        try:
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            if not os.getenv("OPENAI_API_KEY"): raise ValueError("OPENAI_API_KEY não encontrada.")
        except Exception as e_openai:
            print(f"ERRO OpenAI Init: {e_openai}")
            self.openai_client = None # Permite que o app continue rodando mas sem funcionalidade OpenAI

        self._config_lock = threading.Lock()
        self.config = self.load_config_from_json()
        
        self.signal_update_overlay_content.connect(self.overlay.update_text_display)
        self.signal_update_menu_display.connect(self.overlay.show_menu_display_slot)
        self.signal_set_temporary_message.connect(self._set_temporary_message_slot)
        self.signal_apply_config_to_overlay.connect(self.overlay.apply_geometry_from_config)
        self.signal_toggle_processing_flag.connect(self._set_processing_flag_slot)
        self.web_config_change_requested.connect(self.handle_web_config_change)
        self.signal_show_temporary_margins_on_overlay.connect(self.display_margins_temporarily_on_overlay_slot)

        self.signal_apply_config_to_overlay.emit(dict(self.config))

        self.flask_server_thread_obj = None
        self.is_currently_processing_chatgpt = False
        self._temporary_message_active = False
        self.temporary_state_clear_timer = QtCore.QTimer(self)
        self.temporary_state_clear_timer.setSingleShot(True)
        self.temporary_state_clear_timer.timeout.connect(self.clear_temporary_message_and_restore_chat_view)

        self.is_recording_audio = False
        self.audio_recorder_thread = None
        self.stop_audio_recording_event = threading.Event()
        self.audio_frames_buffer = []

    def get_config_copy_for_web(self):
        with self._config_lock: return dict(self.config)
    def get_config_value(self, key, default=None):
        with self._config_lock: return self.config.get(key, default)

    @QtCore.pyqtSlot(dict)
    def handle_web_config_change(self, changed_values_from_web):
        config_actually_updated = False
        with self._config_lock:
            for key, value in changed_values_from_web.items():
                if key in self.config: # Só atualiza se a chave existe (evita adicionar chaves arbitrárias)
                    if self.config[key] != value:
                        self.config[key] = value
                        config_actually_updated = True
                # elif key not in self.config: # Não adiciona chaves novas aqui
                #    self.config[key] = value; config_actually_updated = True 
        if config_actually_updated:
            self.save_config()
            self.signal_apply_config_to_overlay.emit(dict(self.config))

    def load_config_from_json(self):
        with self._config_lock:
            default_cfg = {
                'opacity': 0.8, 'position': 'top-right', 'model': 'gpt-4o',
                'port': 43000, 'margin': [0, 0, 0, 0], 'overlay_width': 420,
                'overlay_v_offset': 25, 'overlay_h_offset': 25, 
                'max_chat_history_pairs': 8, 
                'vision_detail_level': 'auto', 'api_max_tokens': 250,
                'overlay_height_ratio': 0.85,
                'whisper_model': 'whisper-1',
                'chat_model': 'gpt-3.5-turbo-0125'
            }
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f: loaded_cfg = json.load(f)
                    for key, value in default_cfg.items():
                        if key not in loaded_cfg: loaded_cfg[key] = value
                    if not (isinstance(loaded_cfg.get('margin'), list) and len(loaded_cfg['margin']) == 4 and all(isinstance(x, (int, float)) for x in loaded_cfg['margin'])):
                        loaded_cfg['margin'] = default_cfg['margin']
                    return loaded_cfg
                else:
                    with open(CONFIG_FILE, 'w') as f: json.dump(default_cfg, f, indent=4)
                    return default_cfg
            except Exception as e:
                print(f"Erro ao carregar/criar {CONFIG_FILE}: {e}. Usando defaults.\n{traceback.format_exc()}")
                return default_cfg
    
    def save_config(self, config_to_save=None):
        try:
            with self._config_lock:
                cfg_data = config_to_save if config_to_save else self.config
                with open(CONFIG_FILE, 'w') as f: json.dump(cfg_data, f, indent=4)
        except Exception as e: print(f"Erro ao salvar config: {e}\n{traceback.format_exc()}")
    
    @QtCore.pyqtSlot(bool)
    def _set_processing_flag_slot(self, state: bool):
        self.is_currently_processing_chatgpt = state

    @QtCore.pyqtSlot(str, int)
    def _set_temporary_message_slot(self, html_message, duration_ms):
        if self.temporary_state_clear_timer.isActive():
            self.temporary_state_clear_timer.stop()
        self.signal_update_overlay_content.emit(html_message)
        self._temporary_message_active = True
        self.temporary_state_clear_timer.start(duration_ms)

    def clear_temporary_message_and_restore_chat_view(self):
        self.temporary_state_clear_timer.stop()
        self._temporary_message_active = False
        if self.menu_is_active:
            self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        elif self.is_recording_audio:
             self.signal_update_overlay_content.emit("<p style='color:#FFEB3B; text-align:center;'>🎙️ Gravando... (ESC+4)</p>")
        else:
            self.display_last_chat_message_or_default()

    @QtCore.pyqtSlot(list)
    def display_margins_temporarily_on_overlay_slot(self, margins_list):
        if len(margins_list) == 4:
            x1, y1, x2, y2 = margins_list
            width = x2 - x1; height = y2 - y1
            margin_text = (f"<div style='text-align:center; padding:10px; border:1px solid #00E676; background:rgba(0,0,0,0.7); border-radius:5px;'>"
                           f"<h4 style='color:#00E676; margin:0 0 5px 0;'>Margens Atualizadas</h4>"
                           f"<p style='margin:2px 0;'>X1: {x1}, Y1: {y1}</p>"
                           f"<p style='margin:2px 0;'>X2: {x2}, Y2: {y2}</p>"
                           f"<p style='margin:2px 0;'>W: {width}, H: {height}</p>"
                           f"</div>")
            self.signal_set_temporary_message.emit(margin_text, 5000)

    def take_screenshot_bytes_for_api(self): #Lógica interna parece OK
        try:
            with mss.mss() as sct:
                with self._config_lock:
                    margin_list = list(self.config.get('margin', [0,0,0,0]))
                    monitor_idx = self.config.get('capture_monitor_idx', 1) # mss 1 é primário
                target_monitor_mss_idx = monitor_idx if len(sct.monitors) > 1 else 0 # 0 para 'all'
                if target_monitor_mss_idx >= len(sct.monitors):
                    target_monitor_mss_idx = 1 if len(sct.monitors) > 1 else 0
                base_monitor_details = sct.monitors[target_monitor_mss_idx]
                capture_details = dict(base_monitor_details)
                if isinstance(margin_list, list) and len(margin_list) == 4 and any(m != 0 for m in margin_list): #any check
                    x1, y1, x2, y2 = margin_list; width, height = x2 - x1, y2 - y1
                    if width > 0 and height > 0:
                        custom_left = base_monitor_details["left"] + x1; custom_top = base_monitor_details["top"] + y1
                        if (custom_left >= base_monitor_details["left"] and custom_top >= base_monitor_details["top"] and
                            custom_left + width <= base_monitor_details["left"] + base_monitor_details["width"] and
                            custom_top + height <= base_monitor_details["top"] + base_monitor_details["height"]):
                            capture_details = {"top": custom_top, "left": custom_left, "width": width, "height": height, "mon": target_monitor_mss_idx}
                        else: self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Margens excedem. Tela cheia.</p>", 3000)
                    else: self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Margens inválidas. Tela cheia.</p>", 3000)
                sct_img_obj = sct.grab(capture_details)
                return mss.tools.to_png(sct_img_obj.rgb, sct_img_obj.size)
        except Exception as e:
            print(f"Erro MSS captura: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro captura: {html.escape(str(e))[:50]}</p>", 4000)
            return None

    def _threaded_call_to_openai_vision_api(self, image_bytes_data, is_new_chat_bool):
        if not self.openai_client: self.signal_update_overlay_content.emit("<p style='color:red;text-align:center;'>Cliente OpenAI não iniciado.</p>"); return
        if self.is_currently_processing_chatgpt: return 
        self.signal_toggle_processing_flag.emit(True)
        self.signal_update_overlay_content.emit("<p style='text-align:center;'>Analisando imagem com IA...</p>")
        base64_image_str = base64.b64encode(image_bytes_data).decode('utf-8')

        if is_new_chat_bool or not self.history or self.history[0]["role"] != "system":
            self.history = [{"role": "system", "content": "Você é um assistente visual conciso. Descreva a imagem claramente. Max 150 palavras."}]
        
        with self._config_lock:
            max_hist_pairs = self.config.get('max_chat_history_pairs', 8)
            vision_model_name = self.config.get('model', 'gpt-4o')
            detail_level = self.config.get('vision_detail_level', 'auto')
            max_tokens_api = self.config.get('api_max_tokens', 250)

        user_message_vision = {"role": "user", "content": [ {"type": "text", "text": "Descreva esta imagem."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image_str}", "detail": detail_level }} ]}
        
        current_history_for_api = list(self.history) + [user_message_vision]
        if len(current_history_for_api) > (max_hist_pairs * 2 + 1):
             current_history_for_api = [current_history_for_api[0]] + current_history_for_api[-(max_hist_pairs * 2):]
        
        try:
            api_response = self.openai_client.chat.completions.create(
                model=vision_model_name, messages=current_history_for_api, max_tokens=max_tokens_api )
            assistant_reply_str = api_response.choices[0].message.content
            self.history.append(user_message_vision); self.history.append({"role": "assistant", "content": assistant_reply_str})
            if len(self.history) > (max_hist_pairs * 2 + 1): self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(assistant_reply_str, prefix="🖼️ Visão:"))
        except Exception as e:
            err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro API Visão: {html.escape(str(e))[:100]}</p>"
            self.signal_update_overlay_content.emit(err_msg); print(f"Erro API OpenAI (Visão): {e}\n{traceback.format_exc()}")
        finally: self.signal_toggle_processing_flag.emit(False)

    def _format_gpt_response_for_html_display(self, raw_text_str, prefix=""):
        escaped_html_text = html.escape(raw_text_str); prefix_style = "color:#AED581;"
        if "🎙️" in prefix: prefix_style = "color:#81D4FA;"
        if "🖼️" in prefix: prefix_style = "color:#FFB74D;"
        prefix_html = f"<strong style='{prefix_style}'>{html.escape(prefix)} </strong>" if prefix else ""
        formatted_text = escaped_html_text.replace(chr(10), '<br/>'); separator = ""
        if "IA:" in prefix or "Visão:" in prefix: 
            separator = "<hr style='border:0; height:1px; background:rgba(255,255,255,0.1); margin:8px 0 5px 0;'>"
        return f"<div style='padding:2px;'>{separator}{prefix_html}{formatted_text}</div>"

    def _initiate_chatgpt_request(self, is_new_chat_bool):
        if not self.openai_client: self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>OpenAI não configurado.</p>",3000); return
        if self.menu_is_active or self.is_currently_processing_chatgpt or self.is_recording_audio or not AppController._chat_hotkeys_globally_enabled:
            if self.is_recording_audio: self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize gravação (ESC+4).</p>", 2500)
            return
        image_bytes = self.take_screenshot_bytes_for_api()
        if image_bytes:
            threading.Thread(target=self._threaded_call_to_openai_vision_api, args=(image_bytes, is_new_chat_bool), daemon=True).start()

    def on_hotkey_esc_4_audio_toggle(self):
        try:
            if not PYAUDIO_AVAILABLE: self.signal_set_temporary_message.emit("<p style='color:orange;'>PyAudio não instalado. Tente rodar 'pip install pyaudio'</p>", 3000); return
            if not self.openai_client: self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>OpenAI não configurado.</p>",3000); return
            if self.menu_is_active or self.is_currently_processing_chatgpt: self.signal_set_temporary_message.emit("<p style='text-align:center;'>Menu/IA ocupado.</p>", 2500); return
            if self.is_recording_audio: self.stop_audio_recording_event.set()
            else:
                self.is_recording_audio = True; self.audio_frames_buffer = []; self.stop_audio_recording_event.clear()
                self.signal_update_overlay_content.emit("<p style='color:#FFEB3B; text-align:center;'>🎙️ Gravando... (ESC+4)</p>")
                self.audio_recorder_thread = threading.Thread(target=self._threaded_record_audio, daemon=True); self.audio_recorder_thread.start()
        except Exception as e:
            self.is_recording_audio = False; print(f"Erro ESC+4: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro gravação: {html.escape(str(e))[:50]}</p>", 3000)

    def _threaded_record_audio(self):
        pa = None; stream = None
        try:
            pa = pyaudio.PyAudio()
            stream = pa.open(format=AUDIO_FORMAT,channels=AUDIO_CHANNELS,rate=AUDIO_RATE,input=True,frames_per_buffer=AUDIO_CHUNK)
            while not self.stop_audio_recording_event.is_set() and self.is_recording_audio :
                data = stream.read(AUDIO_CHUNK, exception_on_overflow=False) # No exception
                self.audio_frames_buffer.append(data)
        except Exception as e:
            print(f"Erro PyAudio: {e}\n{traceback.format_exc()}"); self.is_recording_audio = False
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro PyAudio: {html.escape(str(e))[:50]}</p>", 4000); return
        finally:
            if stream: stream.stop_stream(); stream.close()
            if pa: pa.terminate()
        self.is_recording_audio = False 
        if self.stop_audio_recording_event.is_set(): # Se parou por evento (ESC+4), então processa
             self.signal_update_overlay_content.emit("<p style='text-align:center;'>Preparando áudio...</p>")
             if not self.audio_frames_buffer: self.display_last_chat_message_or_default(); return
             threading.Thread(target=self._save_and_transcribe_audio, args=(list(self.audio_frames_buffer),), daemon=True).start()
             self.audio_frames_buffer = []
        # Se saiu do loop por self.is_recording_audio se tornar False por outra razão (ex: erro), não processa

    def _save_and_transcribe_audio(self, frames_copy):
        if not frames_copy: return
        try:
            with wave.open(TEMP_AUDIO_FILENAME, 'wb') as wf:
                wf.setnchannels(AUDIO_CHANNELS); wf.setsampwidth(pyaudio.PyAudio().get_sample_size(AUDIO_FORMAT))
                wf.setframerate(AUDIO_RATE); wf.writeframes(b''.join(frames_copy))
            self._threaded_transcribe_audio_with_whisper(TEMP_AUDIO_FILENAME)
        except Exception as e:
            print(f"Erro ao salvar WAV: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro WAV: {html.escape(str(e))[:50]}</p>", 3000)
            self.display_last_chat_message_or_default()

    def _threaded_transcribe_audio_with_whisper(self, audio_filepath):
        self.signal_update_overlay_content.emit("<p style='text-align:center;'>Transcrevendo com Whisper...</p>")
        try:
            with open(audio_filepath, "rb") as audio_file:
                with self._config_lock:
                    whisper_model_name = self.config.get('whisper_model', 'whisper-1')
                    chat_text_model_name = self.config.get('chat_model', 'gpt-3.5-turbo-0125')
                    max_tokens_api = self.config.get('api_max_tokens', 250)
                    max_hist_pairs = self.config.get('max_chat_history_pairs', 8)

                transcription_response = self.openai_client.audio.transcriptions.create( model=whisper_model_name, file=audio_file )
            transcribed_text = transcription_response.text.strip()
            if not transcribed_text: self.signal_set_temporary_message.emit("<p style='color:orange; text-align:center;'>Nenhuma fala detectada.</p>", 3000); self.display_last_chat_message_or_default(); return
            
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(transcribed_text, prefix="🎙️ Você:"))
            self.signal_toggle_processing_flag.emit(True); self.signal_update_overlay_content.emit("<p style='text-align:center;'>Enviando transcrição para IA...</p>")
            
            if not self.history or self.history[0]["role"] != "system": self.history = [{"role": "system", "content": "Você é um assistente prestativo e conciso."}]
            user_message_for_chat = {"role": "user", "content": transcribed_text}
            current_history_for_api = list(self.history) + [user_message_for_chat]
            if len(current_history_for_api) > (max_hist_pairs * 2 + 1): current_history_for_api = [current_history_for_api[0]] + current_history_for_api[-(max_hist_pairs * 2):]
            
            try:
                chat_api_response = self.openai_client.chat.completions.create( model=chat_text_model_name, messages=current_history_for_api, max_tokens=max_tokens_api )
                assistant_reply_str = chat_api_response.choices[0].message.content
                self.history.append(user_message_for_chat); self.history.append({"role": "assistant", "content": assistant_reply_str})
                if len(self.history) > (max_hist_pairs * 2 + 1): self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]
                self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(assistant_reply_str, prefix="🤖 IA:"))
            except Exception as e_chat:
                err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro IA Chat: {html.escape(str(e_chat))[:100]}</p>"
                self.signal_update_overlay_content.emit(err_msg); print(f"Erro API OpenAI (Chat pós Whisper): {e_chat}\n{traceback.format_exc()}")
            finally: self.signal_toggle_processing_flag.emit(False)
        except Exception as e_whisper:
            err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro API Whisper: {html.escape(str(e_whisper))[:100]}</p>"
            self.signal_update_overlay_content.emit(err_msg); print(f"Erro API OpenAI (Whisper): {e_whisper}\n{traceback.format_exc()}")
            if self.is_currently_processing_chatgpt: self.signal_toggle_processing_flag.emit(False)
        finally:
            if os.path.exists(audio_filepath):
                try: os.remove(audio_filepath)
                except Exception as e_del: print(f"Erro ao deletar {audio_filepath}: {e_del}")
    def _prompt_for_margins(self):
        msg = ("<p style='text-align:center;'>Use <b>CTRL+9</b> para configs. web<br/>e ajustar margens por lá.</p>"
               "<p style='text-align:center; font-size:small;'>(Voltando ao menu em 7s...)</p>")
        self.signal_set_temporary_message.emit(msg, 7000)
        
    def on_menu_option_selected_enter(self):
        try:
            if not self.menu_is_active: return
            if self.is_recording_audio: self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize gravação (ESC+4).</p>", 2500); return
            
            self.temporary_state_clear_timer.stop() 
            selected_opt_str = self.menu_options_list[self.current_menu_selection_idx]
            feedback_msg_html = ""; config_changed = False; keep_menu_open = True
            
            with self._config_lock: current_config_copy = dict(self.config)

            if selected_opt_str == "Alternar Opacidade":
                opac_cycle = [0.4, 0.6, 0.8, 1.0]; current_opac = current_config_copy['opacity']
                try: idx = opac_cycle.index(current_opac)
                except ValueError: idx = opac_cycle.index(min(opac_cycle, key=lambda x:abs(x-current_opac)))
                current_config_copy['opacity'] = opac_cycle[(idx + 1) % len(opac_cycle)]
                feedback_msg_html = f"Opacidade: {current_config_copy['opacity']*100:.0f}%"; config_changed = True
            elif selected_opt_str == "Alternar Posição":
                pos_cycle = ['top-right', 'top-left', 'bottom-right', 'bottom-left']; current_pos = current_config_copy['position']
                try: idx = pos_cycle.index(current_pos)
                except ValueError: idx = -1
                current_config_copy['position'] = pos_cycle[(idx + 1) % len(pos_cycle)]
                feedback_msg_html = f"Posição: {current_config_copy['position'].replace('-', ' ').title()}"; config_changed = True
            elif selected_opt_str == "Alternar Modelo GPT Visão":
                model_cycle = ["gpt-4o", "gpt-4-turbo", "gpt-4-vision-preview"] 
                current_model = current_config_copy['model']
                try: idx = model_cycle.index(current_model)
                except ValueError: idx = -1 
                current_config_copy['model'] = model_cycle[(idx + 1) % len(model_cycle)]
                feedback_msg_html = f"Modelo Visão: {current_config_copy['model']}"; config_changed = True
            elif selected_opt_str == "Margens (via Web)": self._prompt_for_margins(); return 
            elif selected_opt_str == "Configurações Web (CTRL+9)": self.on_hotkey_web_config(); return # Usar o nome da função de CTRL+9
            elif selected_opt_str == "Sair": self.save_config(); QtWidgets.QApplication.quit(); return
            else: keep_menu_open = False

            if config_changed:
                with self._config_lock: self.config.update(current_config_copy)
                self.save_config(); self.signal_apply_config_to_overlay.emit(dict(current_config_copy))

            if feedback_msg_html: self.signal_set_temporary_message.emit(f"<p style='text-align:center;'>{feedback_msg_html}</p>", 2000)
            elif not keep_menu_open : 
                self.menu_is_active = False; AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
        except Exception as e: 
            print(f"Erro menu enter: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit("<p style='color:red;text-align:center'>Erro menu.</p>", 3000)
            
    def display_last_chat_message_or_default(self):
        if self._temporary_message_active or self.is_recording_audio : return
        if self.is_currently_processing_chatgpt: self.signal_update_overlay_content.emit("<p style='text-align:center;'>Processando IA...</p>"); return
        last_assistant_msg_str = ""; prefix = "🤖 IA:"
        if self.history:
            for msg_idx in range(len(self.history) - 1, -1, -1):
                msg = self.history[msg_idx]
                if msg["role"] == "assistant":
                    last_assistant_msg_str = msg["content"]
                    if msg_idx > 0:
                        prev_user_msg = self.history[msg_idx - 1]
                        if prev_user_msg["role"] == "user" and isinstance(prev_user_msg.get("content"), list):
                            for item in prev_user_msg["content"]:
                                if isinstance(item, dict) and item.get("type") == "image_url": prefix = "🖼️ Visão:"; break
                    self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(last_assistant_msg_str, prefix=prefix))
                    return
        self.signal_update_overlay_content.emit("<p style='text-align:center; font-size:9.5pt; color:#ccc;'>"
                                               "<span style='color:#FFB74D;'>ESC+1</span>: Visão | <span style='color:#AED581;'>ESC+3</span>: Menu<br>"
                                               "<span style='color:#81D4FA;'>ESC+4</span>: Áudio → IA | <span style='color:#CE93D8;'>CTRL+9</span>: Web</p>")
    
    def on_hotkey_esc_1(self): 
        try: self._initiate_chatgpt_request(True)
        except Exception as e: print(f"Erro ESC+1: {e}\n{traceback.format_exc()}")
    def on_hotkey_esc_2(self): 
        try: self._initiate_chatgpt_request(False)
        except Exception as e: print(f"Erro ESC+2: {e}\n{traceback.format_exc()}")
    def on_hotkey_esc_3_menu_toggle(self):
        try:
            if self.is_currently_processing_chatgpt or self.is_recording_audio: self.signal_set_temporary_message.emit("<p style='text-align:center;'>Aguarde...</p>", 2000); return
            self.menu_is_active = not self.menu_is_active; AppController._chat_hotkeys_globally_enabled = not self.menu_is_active
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop(); self.current_menu_selection_idx = 0
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
            else: self.display_last_chat_message_or_default()
        except Exception as e: print(f"Erro ESC+3: {e}\n{traceback.format_exc()}")
    def on_hotkey_esc_0_exit_menu_or_clear(self):
        try:
            if self.menu_is_active:
                self.menu_is_active = False; AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
            elif not self.is_currently_processing_chatgpt and not self.is_recording_audio: self.signal_update_overlay_content.emit("") 
            elif self.is_recording_audio: self.signal_set_temporary_message.emit("<p style='text-align:center;'>ESC+4 para gravação.</p>", 2500)
        except Exception as e: print(f"Erro ESC+0: {e}\n{traceback.format_exc()}")

    # Renomeado de on_hotkey_esc_9_web_config para on_hotkey_web_config para generalizar
    def on_hotkey_web_config(self): 
        try:
            if not self.openai_client: # Se OpenAI não estiver configurado, ainda permitir acesso web para configurar API KEY se for adicionado no futuro.
                 pass # Ainda abre o server
            if self.menu_is_active: self.on_hotkey_esc_3_menu_toggle() 
            if self.is_recording_audio: self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize gravação (ESC+4).</p>", 2500); return
            flask_port = self.get_config_value('port', 43000); flask_url = f"http://127.0.0.1:{flask_port}"; msg_extra = ""
            if not self.flask_server_thread_obj or not self.flask_server_thread_obj.is_alive():
                self.flask_server_thread_obj = start_web_server(self); msg_extra = "Servidor de config. iniciado!"
            else: msg_extra = "Servidor de config. já rodando!"
            msg_html = (f"<div style='text-align:center;'><p>{msg_extra}<br/>"
                        f"Acesse: <a href='{flask_url}' style='color:#81D4FA;text-decoration:underline;'>{flask_url}</a></p>"
                        f"<p style='font-size:small;'>(Retornando em 15s ou ESC+0)</p></div>")
            self.signal_set_temporary_message.emit(msg_html, 15000)
        except Exception as e: print(f"Erro CTRL+9: {e}\n{traceback.format_exc()}")
    def on_menu_navigation_input(self, direction_str_up_down):
        try:
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop()
                if direction_str_up_down == "up": self.current_menu_selection_idx = (self.current_menu_selection_idx - 1 + len(self.menu_options_list)) % len(self.menu_options_list)
                else: self.current_menu_selection_idx = (self.current_menu_selection_idx + 1) % len(self.menu_options_list)
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        except Exception as e: print(f"Erro navegação menu:{e}\n{traceback.format_exc()}")

# --- Main Application Setup & Execution ---
def main():
    try:
        if sys.platform == "win32":
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
            try: QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
            except: pass # Ignora se Fusion não estiver disponível

        app = QtWidgets.QApplication(sys.argv)
        overlay_initial_config = {'opacity':0.8, 'position':'top-right', 'overlay_width':420, 
            'overlay_v_offset':25, 'overlay_h_offset':25, 'overlay_height_ratio': 0.85 }
        overlay_widget_instance = Overlay(overlay_initial_config)
        app_controller_instance = AppController(overlay_widget_instance)

        hotkeys_config = [
            ('esc+1', app_controller_instance.on_hotkey_esc_1),
            ('esc+2', app_controller_instance.on_hotkey_esc_2),
            ('esc+3', app_controller_instance.on_hotkey_esc_3_menu_toggle),
            ('esc+4', app_controller_instance.on_hotkey_esc_4_audio_toggle),
            ('esc+0', app_controller_instance.on_hotkey_esc_0_exit_menu_or_clear),
            ('esc+9', app_controller_instance.on_hotkey_web_config), # MUDADO PARA CTRL+9
            ('esc+up', lambda: app_controller_instance.on_menu_navigation_input("up")),
            ('esc+down', lambda: app_controller_instance.on_menu_navigation_input("down")),
            ('esc+enter', app_controller_instance.on_menu_option_selected_enter),
            ('ctrl+alt+esc', lambda: (app_controller_instance.save_config(), QtWidgets.QApplication.quit())) 
        ]
        
        for key_combo, callback_func in hotkeys_config:
            try: keyboard.add_hotkey(key_combo, callback_func, suppress=False, timeout=0.3, trigger_on_release=False)
            except Exception as e_hk: print(f"Erro ao registrar hotkey {key_combo}: {e_hk}")

        app.aboutToQuit.connect(app_controller_instance.save_config) 
        app_controller_instance.signal_set_temporary_message.emit(
            "<div style='text-align:center; font-size:9.5pt;'>"
            "<b>OverlayGPT Iniciado!</b><br>"
            "<span style='color:#FFB74D;'>ESC+1</span>: Visão | "
            "<span style='color:#AED581;'>ESC+3</span>: Menu<br>"
            "<span style='color:#81D4FA;'>ESC+4</span>: Áudio → IA | "
            "<span style='color:#CE93D8;'>CTRL+9</span>: Web Conf."
            "</div>", 10000 )
        exit_status_code = app.exec_()
    except Exception as e_main:
        print(f"Erro fatal: {e_main}\n{traceback.format_exc()}")
        try: keyboard.unhook_all()
        except Exception: pass
        sys.exit(1)
    finally:
        try:
            print("Desregistrando hotkeys..."); keyboard.unhook_all()
            if os.path.exists(TEMP_AUDIO_FILENAME): os.remove(TEMP_AUDIO_FILENAME)
        except Exception as e_final: print(f"Erro na finalização: {e_final}")
    sys.exit(exit_status_code)

if __name__ == "__main__":
    if not PYAUDIO_AVAILABLE and os.name == 'nt':
        print("-" * 60 + "\nPyAudio não carregado. Para gravação de áudio, tente:\n1. pip install PyAudio\n2. Se falhar, procure por 'PyAudio wheels for Windows Python X.Y'\n   e instale com: pip install nome_do_arquivo.whl\n" + "-" * 60)
    print("Iniciando OverlayGPT...")
    main()
