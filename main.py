import sys
import io 
import base64
from colorama import init, Fore, Style
import threading
from dotenv import load_dotenv
import os
import ctypes
from openai import OpenAI
from PyQt5 import QtWidgets, QtCore, QtGui
import keyboard 
import mss
from flask import Flask, request, redirect 
import json
import html
import traceback

# Preparação do ambiente para cores
init(autoreset=True)

# Adições para áudio
try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print(Fore.YELLOW + "AVISO: PyAudio não encontrado. Funcionalidade de gravação de áudio desabilitada.")

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
AUDIO_CHANNELS_MIC = 1 
AUDIO_CHANNELS_SYSTEM = 2 
AUDIO_RATE = 16000 
AUDIO_CHUNK = 1024
TEMP_AUDIO_FILENAME = "temp_overlay_audio.wav"
TEMP_SYSTEM_AUDIO_FILENAME = "temp_overlay_system_audio.wav"


# --- Flask Web Server ---
def start_web_server(app_controller_ref):
    app_flask = Flask(__name__)

    @app_flask.route('/', methods=['GET', 'POST'])
    def root():
        config_ref_dict = app_controller_ref.get_config_copy_for_web()
        message_from_post = request.args.get('message', None) 

        if request.method == 'POST':
            original_config_for_comparison = dict(config_ref_dict)
            changed_values = {} 
            post_message_feedback = ""

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
                    if m_x2 > m_x1 and m_y2 > m_y1: # Validação básica
                        changed_values['margin'] = new_margin_list
                        app_controller_ref.signal_show_temporary_margins_on_overlay.emit(new_margin_list)
                        post_message_feedback += f"Margens: X1={m_x1},Y1={m_y1},X2={m_x2},Y2={m_y2}. "
                    else:
                        post_message_feedback += "Erro: Margens inválidas (X2>X1, Y2>Y1). "
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
                .message.success {{ background-color: #2E7D32; color: #C8E6C9; }}
                .message.error {{ background-color: #C62828; color: #FFCDD2; }}
                small {{ color: var(--secondary-text-color); display: block; text-align: center; margin-top: 15px;}}
            </style></head><body><div class="container"><h2>Configurações Avançadas</h2>
            {'<div class="message success">' + html.escape(message_from_post) + '</div>' if message_from_post and "Erro" not in message_from_post else ''}
            {'<div class="message error">' + html.escape(message_from_post) + '</div>' if message_from_post and "Erro" in message_from_post else ''}
            <form method="post">
                <label for="gpt_model">Modelo GPT Visão/Multimodal:</label><input type="text" id="gpt_model" name="gpt_model" value="{html.escape(str(config_ref_dict.get('model','')))}"/>
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
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        self.current_config = dict(initial_config_dict) 
        self.screen_geom = QtWidgets.QApplication.primaryScreen().geometry()
        self.text_label = QtWidgets.QLabel(self)
        self.text_label.setStyleSheet(
            "color: white; background: rgba(20,20,20,0.85); padding: 10px; "
            "border-radius: 8px; font-size: 10pt; border: 1px solid rgba(255,255,255,0.15);"
            "selection-background-color: rgba(0, 120, 215, 0.5);" 
            "selection-color: white;" 
        )
        self.text_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.text_label.setWordWrap(True)
        self.text_label.setOpenExternalLinks(False) 
        self.text_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.TextSelectableByKeyboard)


        self.apply_geometry_from_config(self.current_config)
        self.exclude_from_capture() 
        self.show()
        
        QtCore.QTimer.singleShot(50, self.make_window_click_through)

    def make_window_click_through(self):
        try:
            hwnd = self.winId().__int__() 
            if not hwnd:
                # print("Overlay HWND não disponível para make_window_click_through.") # Comentado para reduzir spam no console
                QtCore.QTimer.singleShot(100, self.make_window_click_through)
                return

            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020 
            current_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_ex_style = current_ex_style | WS_EX_TRANSPARENT
            
            if not user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style):
                # print(f"Falha ao definir SetWindowLongW com WS_EX_TRANSPARENT. Erro: {ctypes.get_last_error()}") # Comentado
                pass
            else:
                # print(f"Overlay (HWND: {hwnd}): Estilo WS_EX_TRANSPARENT aplicado para click-through.") # Comentado
                pass
        except Exception as e:
            print(Fore.RED + f"Erro crítico ao tornar a janela click-through: {e}\n{traceback.format_exc()}")

    def exclude_from_capture(self):
        try:
            hwnd = self.winId().__int__()
            if not hwnd: 
                # print("Overlay HWND não disponível para exclude_from_capture.") # Comentado
                return

            if hasattr(user32, 'SetWindowDisplayAffinity'):
                if not user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                    ctypes.set_last_error(0) 
                    if not user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
                         # print(f"Falha ao definir DisplayAffinity para MONITOR. Erro: {ctypes.get_last_error()}") # Comentado
                         pass
                    else:
                        # print(f"Overlay (HWND: {hwnd}): DisplayAffinity = MONITOR.") # Comentado
                        pass
                else:
                    # print(f"Overlay (HWND: {hwnd}): DisplayAffinity = EXCLUDEFROMCAPTURE.") # Comentado
                    pass
            # else: # Comentado
                # print("SetWindowDisplayAffinity não encontrado.")

            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080  
            WS_EX_NOACTIVATE = 0x08000000  
            
            current_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_ex_style_base = current_ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            
            if not user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style_base):
                # print(f"Falha ao definir SetWindowLongW (base). Erro: {ctypes.get_last_error()}") # Comentado
                pass
            # else: # Comentado
                # print(f"Overlay (HWND: {hwnd}): Estilos WS_EX_NOACTIVATE e WS_EX_TOOLWINDOW aplicados.")

        except Exception as e:
            print(Fore.RED + f"Erro crítico ao configurar estilos de janela/afinidade: {e}\n{traceback.format_exc()}")

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
        # CORREÇÃO: Declarar global PYAUDIO_AVAILABLE no início do método se for modificado.
        global PYAUDIO_AVAILABLE

        self.overlay = overlay_qt_widget 
        self.history = [] 
        self.menu_is_active = False
        self.menu_options_list = [
            "Alternar Opacidade", "Alternar Posição", "Alternar Modelo GPT Visão/Multimodal",
            "Margens (via Web)", "Configurações Web (CTRL+9)", "Sair"
        ]
        self.current_menu_selection_idx = 0
        
        try:
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            if not os.getenv("OPENAI_API_KEY"): 
                raise ValueError(Fore.YELLOW + "Chave OPENAI_API_KEY não encontrada no arquivo .env.")
        except Exception as e_openai:
            print(Fore.RED + f"ERRO CRÍTICO - Inicialização OpenAI Falhou: {e_openai}")
            self.openai_client = None
            if hasattr(self, 'signal_set_temporary_message'):
                 QtCore.QTimer.singleShot(100, lambda: self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado. Verifique a API KEY.</p>", 0) if self.openai_client is None else None)


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

        self.is_recording_mic_audio = False
        self.mic_audio_recorder_thread = None 
        self.stop_mic_audio_recording_event = threading.Event() 
        self.mic_audio_frames_buffer = [] 

        self.is_recording_system_audio = False
        self.system_audio_recorder_thread = None
        self.stop_system_audio_recording_event = threading.Event()
        self.system_audio_frames_buffer = []
        
        self.pyaudio_instance = None
        if PYAUDIO_AVAILABLE: # Leitura da global (agora corretamente referenciada)
            try:
                self.pyaudio_instance = pyaudio.PyAudio()
            except Exception as e:
                print(Fore.RED + f"Erro ao inicializar PyAudio globalmente: {e}")
                self.pyaudio_instance = None
                # Modifica a global PYAUDIO_AVAILABLE. Como 'global PYAUDIO_AVAILABLE' foi declarado no início do método,
                # esta atribuição refere-se à variável global.
                PYAUDIO_AVAILABLE = False 
                print(Fore.YELLOW + "Aviso: PYAUDIO_AVAILABLE foi definido como False devido a um erro de inicialização.")
                if hasattr(self, 'signal_set_temporary_message'):
                     QtCore.QTimer.singleShot(100, lambda: self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro PyAudio: {e}. Gravação desabilitada.</p>", 5000))

        self.is_text_input_mode = False
        self.current_input_text = ""
        self.user_input_active_for_overlay = False 
        self._text_input_hook_active = False
        self._current_keyboard_hook = None 

        self.cursor_timer = QtCore.QTimer(self)
        self.cursor_timer.timeout.connect(self._toggle_cursor_blink)
        self.cursor_visible = True


    def get_config_copy_for_web(self):
        with self._config_lock: 
            return dict(self.config)

    def get_config_value(self, key, default=None):
        with self._config_lock: 
            return self.config.get(key, default)

    @QtCore.pyqtSlot(dict)
    def handle_web_config_change(self, changed_values_from_web):
        config_actually_updated = False
        with self._config_lock:
            for key, value in changed_values_from_web.items():
                if key in self.config and self.config[key] != value:
                    self.config[key] = value
                    config_actually_updated = True
        if config_actually_updated:
            self.save_config() 
            self.signal_apply_config_to_overlay.emit(dict(self.config)) 

    def load_config_from_json(self):
        global CONFIG_FILE 
        with self._config_lock:
            default_cfg = {
                "opacity": 1.0, "position": "bottom-left", "model": "gpt-4o-2024-05-13",
                "port": 43000, "margin": [0, 0, 0, 0], "overlay_width": 420,
                "overlay_v_offset": 25, "overlay_h_offset": 25,
                "max_chat_history_pairs": 10, "vision_detail_level": "low",
                "api_max_tokens": 300, "overlay_height_ratio": 0.9,
                "whisper_model": "gpt-4o-transcribe", "chat_model": "gpt-4o-2024-05-13"
            }
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f: loaded_cfg = json.load(f)
                    for key, value in default_cfg.items(): 
                        if key not in loaded_cfg: loaded_cfg[key] = value
                    
                    margin_val = loaded_cfg.get('margin', default_cfg['margin'])
                    if not (isinstance(margin_val, list) and len(margin_val) == 4 and all(isinstance(x, (int, float)) for x in margin_val)):
                        loaded_cfg['margin'] = default_cfg['margin']
                    return loaded_cfg
                else: 
                    with open(CONFIG_FILE, 'w') as f: json.dump(default_cfg, f, indent=4)
                    return default_cfg
            except Exception as e:
                print(Fore.RED + f"ERRO ao carregar/criar '{CONFIG_FILE}': {e}. Usando defaults.\n{traceback.format_exc()}")
                return default_cfg
    
    def save_config(self, config_to_save=None):
        global CONFIG_FILE
        try:
            with self._config_lock:
                cfg_data = config_to_save if config_to_save else self.config
                with open(CONFIG_FILE, 'w') as f: json.dump(cfg_data, f, indent=4)
        except Exception as e: 
            print(Fore.RED + f"ERRO ao salvar configurações: {e}\n{traceback.format_exc()}")
    
    @QtCore.pyqtSlot(bool)
    def _set_processing_flag_slot(self, state: bool):
        self.is_currently_processing_chatgpt = state

    @QtCore.pyqtSlot(str, int)
    def _set_temporary_message_slot(self, html_message, duration_ms):
        if self.temporary_state_clear_timer.isActive():
            self.temporary_state_clear_timer.stop()
        self.signal_update_overlay_content.emit(html_message)
        self._temporary_message_active = True
        if duration_ms > 0: 
            self.temporary_state_clear_timer.start(duration_ms)

    def clear_temporary_message_and_restore_chat_view(self):
        self.temporary_state_clear_timer.stop()
        self._temporary_message_active = False
        if self.is_text_input_mode:
            self._update_text_input_overlay_display() 
        elif self.menu_is_active:
            self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        elif self.is_recording_mic_audio:
             self.signal_update_overlay_content.emit("<p style='color:#FFEB3B; text-align:center;'>🎙️ Gravando Microfone... (ESC+4)</p>")
        elif self.is_recording_system_audio:
             self.signal_update_overlay_content.emit("<p style='color:#FF80AB; text-align:center;'>🔊 Gravando Som do Sistema... (ESC+5)</p>")
        else:
            self.display_last_chat_message_or_default()


    @QtCore.pyqtSlot(list)
    def display_margins_temporarily_on_overlay_slot(self, margins_list):
        if len(margins_list) == 4:
            x1, y1, x2, y2 = margins_list
            width = x2 - x1; height = y2 - y1
            margin_text = (f"<div style='text-align:center; padding:10px; border:1px solid #00E676; background:rgba(0,0,0,0.75); border-radius:5px;'>"
                           f"<h4 style='color:#69F0AE; margin:0 0 5px 0;'>Margens Atualizadas</h4>"
                           f"<p style='margin:2px 0; color:#E0E0E0;'>X1: {x1}, Y1: {y1}</p>"
                           f"<p style='margin:2px 0; color:#E0E0E0;'>X2: {x2}, Y2: {y2}</p>"
                           f"<p style='margin:2px 0; color:#E0E0E0;'>W: {width}, H: {height}</p>"
                           f"</div>")
            self.signal_set_temporary_message.emit(margin_text, 5000) 

    def take_screenshot_bytes_for_api(self):
        try:
            with mss.mss() as sct:
                with self._config_lock:
                    margin_list = list(self.config.get('margin', [0,0,0,0]))
                    monitor_idx_mss = 1 
                
                if monitor_idx_mss >= len(sct.monitors): 
                    monitor_idx_mss = 0 if len(sct.monitors) > 0 else 1 
                    if monitor_idx_mss == 0 and len(sct.monitors) == 0 : 
                        raise Exception(Fore.YELLOW + "Nenhum monitor detectado pelo MSS.")

                base_monitor_details = sct.monitors[monitor_idx_mss]
                capture_details = dict(base_monitor_details) 
                
                if isinstance(margin_list, list) and len(margin_list) == 4 and any(m != 0 for m in margin_list):
                    x1, y1, x2, y2 = margin_list; width, height = x2 - x1, y2 - y1
                    if width > 0 and height > 0:
                        custom_left = base_monitor_details["left"] + x1
                        custom_top = base_monitor_details["top"] + y1
                        if (custom_left >= base_monitor_details["left"] and 
                            custom_top >= base_monitor_details["top"] and
                            custom_left + width <= base_monitor_details["left"] + base_monitor_details["width"] and
                            custom_top + height <= base_monitor_details["top"] + base_monitor_details["height"]):
                            capture_details = {"top": custom_top, "left": custom_left, "width": width, "height": height, "mon": monitor_idx_mss}
                        else: 
                            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Margens fora dos limites. Capturando tela cheia do monitor primário.</p>", 3000)
                    else: 
                        self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Margens inválidas (Largura/Altura <=0). Capturando tela cheia.</p>", 3000)
                
                sct_img_obj = sct.grab(capture_details)
                return mss.tools.to_png(sct_img_obj.rgb, sct_img_obj.size)
        except Exception as e:
            print(Fore.RED + f"ERRO MSS Captura de Tela: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao capturar tela: {html.escape(str(e))[:50]}</p>", 4000)
            return None

    def _threaded_call_to_openai_vision_api(self, image_bytes_data, is_new_chat_bool):
        if not self.openai_client: self.signal_update_overlay_content.emit("<p style='color:red;text-align:center;'>ERRO: Cliente OpenAI não iniciado.</p>"); return
        if self.is_currently_processing_chatgpt: return 
        
        self.signal_toggle_processing_flag.emit(True)
        self.signal_update_overlay_content.emit("<p style='text-align:center;'>Analisando imagem com IA...</p>")
        base64_image_str = base64.b64encode(image_bytes_data).decode('utf-8')

        if is_new_chat_bool or not self.history or self.history[0].get("content") != "Você é um assistente visual. Descreva a imagem de forma concisa e útil.": 
            self.history = [{"role": "system", "content": "Você é um assistente visual. Descreva a imagem de forma concisa e útil."}]
        
        with self._config_lock: 
            max_hist_pairs = self.config.get('max_chat_history_pairs', 7)
            vision_model_name = self.config.get('model', 'gpt-4o-2024-05-13') 
            detail_level = self.config.get('vision_detail_level', 'auto')
            max_tokens_api = self.config.get('api_max_tokens', 300)

        user_message_vision = {"role": "user", "content": [ 
            {"type": "text", "text": "Descreva esta imagem."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image_str}", "detail": detail_level }} 
        ]}
        
        current_history_for_api = list(self.history) + [user_message_vision] 
        if len(current_history_for_api) > (max_hist_pairs * 2 + 1): 
             current_history_for_api = [current_history_for_api[0]] + current_history_for_api[-(max_hist_pairs * 2):]
        
        try:
            api_response = self.openai_client.chat.completions.create(
                model=vision_model_name, messages=current_history_for_api, max_tokens=max_tokens_api )
            assistant_reply_str = api_response.choices[0].message.content
            
            self.history.append(user_message_vision)
            self.history.append({"role": "assistant", "content": assistant_reply_str})
            if len(self.history) > (max_hist_pairs * 2 + 1): 
                 self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]
            
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(assistant_reply_str, prefix="🖼️ Visão:"))
        except Exception as e:
            err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro API Visão: {html.escape(str(e))[:100]}</p>"
            self.signal_update_overlay_content.emit(err_msg)
            print(Fore.RED + f"ERRO API OpenAI (Visão): {e}\n{traceback.format_exc()}")
        finally: 
            self.signal_toggle_processing_flag.emit(False)


    def _format_gpt_response_for_html_display(self, raw_text_str, prefix=""):
        escaped_html_text = html.escape(raw_text_str)
        prefix_style = "color:#AED581;" 
        if "🎙️🖼️" in prefix or "🔊🖼️" in prefix: prefix_style = "color:#BA68C8;" 
        elif "🎙️" in prefix: prefix_style = "color:#81D4FA;" 
        elif "🔊" in prefix: prefix_style = "color:#FF80AB;" 
        elif "🖼️" in prefix: prefix_style = "color:#FFB74D;" 
        elif "💬" in prefix: prefix_style = "color:#9FA8DA;" 
        elif "👤" in prefix: prefix_style = "color:#FFF59D;" 


        prefix_html = f"<strong style='{prefix_style}'>{html.escape(prefix)} </strong>" if prefix else ""
        formatted_text = escaped_html_text.replace(chr(10), '<br/>')
        separator = ""
        if "IA:" in prefix or "Visão:" in prefix or "Multimodal:" in prefix or "💬" in prefix: 
            separator = "<hr style='border:0; height:1px; background:rgba(255,255,255,0.12); margin:8px 0 5px 0;'>"
        
        return f"<div style='padding:2px;'>{separator}{prefix_html}{formatted_text}</div>"

    def _initiate_chatgpt_request(self, is_new_chat_bool): 
        if not self.openai_client: 
            self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado.</p>",3000)
            return
        if self.is_text_input_mode or self.menu_is_active or self.is_currently_processing_chatgpt or \
           self.is_recording_mic_audio or self.is_recording_system_audio or \
           not AppController._chat_hotkeys_globally_enabled:
            if self.is_recording_mic_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação do microfone (ESC+4) primeiro.</p>", 2500)
            if self.is_recording_system_audio:
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação do som do sistema (ESC+5) primeiro.</p>", 2500)
            if self.is_text_input_mode:
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Saia do modo de entrada de texto (ESC+6) primeiro.</p>", 2500)
            return
        
        image_bytes = self.take_screenshot_bytes_for_api()
        if image_bytes:
            threading.Thread(target=self._threaded_call_to_openai_vision_api, args=(image_bytes, is_new_chat_bool), daemon=True).start()

    def on_hotkey_esc_4_mic_audio_toggle(self):
        if self.is_text_input_mode:
            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Saia do modo de texto (ESC+6) primeiro.</p>", 3000)
            return
        try:
            global PYAUDIO_AVAILABLE 
            if not PYAUDIO_AVAILABLE or not self.pyaudio_instance: 
                self.signal_set_temporary_message.emit("<p style='color:orange; text-align:center;'>PyAudio não instalado/iniciado. Tente 'pip install pyaudio'.</p>", 3500); return
            if not self.openai_client: 
                self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado.</p>",3000); return
            if self.menu_is_active or self.is_currently_processing_chatgpt or self.is_recording_system_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Menu, IA ou gravação do sistema está ocupado. Aguarde.</p>", 2500); return

            if self.is_recording_mic_audio: 
                self.stop_mic_audio_recording_event.set() 
            else: 
                self.is_recording_mic_audio = True
                self.mic_audio_frames_buffer = [] 
                self.stop_mic_audio_recording_event.clear()
                self.signal_update_overlay_content.emit("<p style='color:#FFEB3B; text-align:center;'>🎙️ Gravando microfone... (ESC+4 para parar)</p>")
                
                self.mic_audio_recorder_thread = threading.Thread(target=self._threaded_record_mic_audio, daemon=True)
                self.mic_audio_recorder_thread.start()
        except Exception as e:
            self.is_recording_mic_audio = False 
            print(Fore.RED + f"ERRO ESC+4: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro na gravação de microfone: {html.escape(str(e))[:50]}</p>", 3000)

    def _threaded_record_mic_audio(self):
        audio_stream = None 
        captured_screenshot_bytes = None 
        global AUDIO_FORMAT, AUDIO_CHANNELS_MIC, AUDIO_RATE, AUDIO_CHUNK 
        try:
            if not self.pyaudio_instance: raise Exception("Instância PyAudio não disponível.")
            audio_stream = self.pyaudio_instance.open(format=AUDIO_FORMAT, channels=AUDIO_CHANNELS_MIC, rate=AUDIO_RATE, input=True, frames_per_buffer=AUDIO_CHUNK)
            
            while not self.stop_mic_audio_recording_event.is_set() and self.is_recording_mic_audio:
                data = audio_stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                self.mic_audio_frames_buffer.append(data)
            
            if self.stop_mic_audio_recording_event.is_set(): 
                self.signal_update_overlay_content.emit("<p style='text-align:center;'>Áudio do microfone gravado. Capturando tela agora...</p>")
                captured_screenshot_bytes = self.take_screenshot_bytes_for_api() 
                if not captured_screenshot_bytes:
                     self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Falha ao capturar tela. Tentando enviar apenas áudio do microfone.</p>", 3500)
        except Exception as e:
            print(Fore.RED + f"ERRO PyAudio na gravação de microfone: {e}\n{traceback.format_exc()}"); self.is_recording_mic_audio = False
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro PyAudio (Mic): {html.escape(str(e))[:50]}</p>", 4000); return
        finally:
            if audio_stream: audio_stream.stop_stream(); audio_stream.close()
        
        self.is_recording_mic_audio = False 
        
        if self.stop_mic_audio_recording_event.is_set(): 
             if not self.mic_audio_frames_buffer and not captured_screenshot_bytes: 
                self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Nenhum áudio de microfone ou imagem para processar.</p>", 3000)
                self.display_last_chat_message_or_default(); return
            
             self.signal_update_overlay_content.emit("<p style='text-align:center;'>Preparando áudio (mic) e imagem para IA...</p>")
             threading.Thread(target=self._save_mic_audio_and_process_with_vision, 
                              args=(list(self.mic_audio_frames_buffer), captured_screenshot_bytes), 
                              daemon=True).start()
             self.mic_audio_frames_buffer = [] 

    def _save_mic_audio_and_process_with_vision(self, frames_copy, image_bytes_param):
        if not frames_copy and not image_bytes_param: return 
        
        audio_file_path_to_process = None
        global TEMP_AUDIO_FILENAME, AUDIO_CHANNELS_MIC, AUDIO_FORMAT, AUDIO_RATE
        
        if frames_copy: 
            try:
                if not self.pyaudio_instance: raise Exception("Instância PyAudio não disponível para salvar WAV.")
                with wave.open(TEMP_AUDIO_FILENAME, 'wb') as wf:
                    wf.setnchannels(AUDIO_CHANNELS_MIC)
                    wf.setsampwidth(self.pyaudio_instance.get_sample_size(AUDIO_FORMAT))
                    wf.setframerate(AUDIO_RATE)
                    wf.writeframes(b''.join(frames_copy))
                audio_file_path_to_process = TEMP_AUDIO_FILENAME
            except Exception as e:
                print(Fore.RED + f"ERRO ao salvar WAV (mic) para processamento multimodal: {e}\n{traceback.format_exc()}")
                self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao salvar áudio WAV (mic): {html.escape(str(e))[:50]}</p>", 3000)
        
        self._threaded_transcribe_audio_and_call_multimodal_vision(audio_file_path_to_process, image_bytes_param, "mic")

    def _find_loopback_device_index(self):
        if not PYAUDIO_AVAILABLE or not self.pyaudio_instance:
            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>PyAudio não está disponível.</p>", 3000)
            return None

        try:
            default_host_api_info = self.pyaudio_instance.get_default_host_api_info()
            if default_host_api_info['type'] == pyaudio.paWASAPI: 
                for i in range(self.pyaudio_instance.get_device_count()):
                    device_info = self.pyaudio_instance.get_device_info_by_index(i)
                    if device_info['hostApi'] == default_host_api_info['index'] and \
                       device_info['maxInputChannels'] > 0 and \
                       device_info.get('isLoopbackDevice'): 
                        print(Fore.YELLOW + f"Dispositivo loopback WASAPI (flag) encontrado: {device_info['name']} - Índice: {device_info['index']}")
                        return device_info['index']
                
                common_loopback_names = ["stereo mix", "mixagem estéreo", "wave out", "what u hear", "o que você ouve", "loopback", "monitor"]
                for i in range(self.pyaudio_instance.get_device_count()):
                    device_info = self.pyaudio_instance.get_device_info_by_index(i)
                    if device_info['hostApi'] == default_host_api_info['index'] and device_info['maxInputChannels'] > 0:
                        if any(name_part in device_info['name'].lower() for name_part in common_loopback_names):
                            print(Fore.GREEN + f"Dispositivo loopback WASAPI (nome) encontrado: {device_info['name']} - Índice: {device_info['index']}")
                            return device_info['index']
            
            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Loopback WASAPI não encontrado. Verifique 'Stereo Mix' nas configs de som do Windows.</p>", 5000)
            print(Fore.YELLOW + "AVISO: Nenhum dispositivo de loopback WASAPI encontrado explicitamente. Verifique se 'Stereo Mix' ou similar está habilitado e tente novamente.")
            return None

        except Exception as e:
            print(Fore.RED + f"Erro ao procurar dispositivo de loopback: {e}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao procurar loopback: {html.escape(str(e))[:30]}</p>", 4000)
            return None

    def on_hotkey_esc_5_system_audio_toggle(self):
        if self.is_text_input_mode:
            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Saia do modo de texto (ESC+6) primeiro.</p>", 3000)
            return
        try:
            global PYAUDIO_AVAILABLE
            if not PYAUDIO_AVAILABLE or not self.pyaudio_instance:
                self.signal_set_temporary_message.emit("<p style='color:orange; text-align:center;'>PyAudio não instalado/iniciado. Gravação de som do sistema desabilitada.</p>", 3500)
                return
            if not self.openai_client:
                self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: OpenAI não configurado.</p>", 3000)
                return
            if self.menu_is_active or self.is_currently_processing_chatgpt or self.is_recording_mic_audio:
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Menu, IA ou gravação de microfone está ocupado.</p>", 2500)
                return

            if self.is_recording_system_audio:
                self.stop_system_audio_recording_event.set()
            else:
                loopback_idx = self._find_loopback_device_index()
                if loopback_idx is None: 
                    return

                self.is_recording_system_audio = True
                self.system_audio_frames_buffer = []
                self.stop_system_audio_recording_event.clear()
                self.signal_update_overlay_content.emit("<p style='color:#FF80AB; text-align:center;'>🔊 Gravando Som do Sistema... (ESC+5 para parar)</p>")
                
                self.system_audio_recorder_thread = threading.Thread(target=self._threaded_record_system_audio, args=(loopback_idx,), daemon=True)
                self.system_audio_recorder_thread.start()
        except Exception as e:
            self.is_recording_system_audio = False
            print(Fore.RED + f"ERRO ESC+5: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro gravação Som Sistema: {html.escape(str(e))[:50]}</p>", 3000)


    def _threaded_record_system_audio(self, device_index):
        audio_stream_system = None
        captured_screenshot_bytes = None
        global AUDIO_FORMAT, AUDIO_CHANNELS_SYSTEM, AUDIO_RATE, AUDIO_CHUNK
        actual_channels = AUDIO_CHANNELS_SYSTEM
        actual_rate = AUDIO_RATE

        try:
            if not self.pyaudio_instance: raise Exception("Instância PyAudio não disponível.")
            
            try:
                device_info = self.pyaudio_instance.get_device_info_by_index(device_index)
                actual_rate = int(device_info.get('defaultSampleRate', AUDIO_RATE))
                actual_channels = int(device_info.get('maxInputChannels', AUDIO_CHANNELS_SYSTEM)) 
                print(Fore.CYAN + f"Gravando do dispositivo '{device_info['name']}' com {actual_channels} canais a {actual_rate} Hz.")
            except Exception as e_dev_info:
                print(Fore.YELLOW + f"Aviso: Não foi possível obter detalhes do dispositivo de loopback, usando defaults. Erro: {e_dev_info}")

            audio_stream_system = self.pyaudio_instance.open(format=AUDIO_FORMAT,
                                                             channels=actual_channels,
                                                             rate=actual_rate,
                                                             input=True,
                                                             frames_per_buffer=AUDIO_CHUNK,
                                                             input_device_index=device_index)
            
            while not self.stop_system_audio_recording_event.is_set() and self.is_recording_system_audio:
                data = audio_stream_system.read(AUDIO_CHUNK, exception_on_overflow=False)
                self.system_audio_frames_buffer.append(data)
            
            if self.stop_system_audio_recording_event.is_set():
                self.signal_update_overlay_content.emit("<p style='text-align:center;'>Som do sistema gravado. Capturando tela...</p>")
                captured_screenshot_bytes = self.take_screenshot_bytes_for_api()
                if not captured_screenshot_bytes:
                    self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Falha ao capturar tela. Tentando enviar apenas som do sistema.</p>", 3500)
        
        except Exception as e:
            print(Fore.RED + f"ERRO PyAudio na gravação de som do sistema: {e}\n{traceback.format_exc()}")
            self.is_recording_system_audio = False
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro PyAudio (Sistema): {html.escape(str(e))[:50]}</p>", 4000)
            return 
        finally:
            if audio_stream_system:
                audio_stream_system.stop_stream()
                audio_stream_system.close()
        
        self.is_recording_system_audio = False 
        
        if self.stop_system_audio_recording_event.is_set():
            if not self.system_audio_frames_buffer and not captured_screenshot_bytes:
                self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Nenhum som de sistema ou imagem para processar.</p>", 3000)
                self.display_last_chat_message_or_default()
                return
            
            self.signal_update_overlay_content.emit("<p style='text-align:center;'>Preparando som do sistema e imagem para IA...</p>")
            threading.Thread(target=self._save_system_audio_and_process_with_vision,
                             args=(list(self.system_audio_frames_buffer), captured_screenshot_bytes, actual_channels, actual_rate),
                             daemon=True).start()
            self.system_audio_frames_buffer = []

    def _save_system_audio_and_process_with_vision(self, frames_copy, image_bytes_param, channels, rate):
        if not frames_copy and not image_bytes_param: return

        audio_file_path_to_process = None
        global TEMP_SYSTEM_AUDIO_FILENAME, AUDIO_FORMAT
        
        if frames_copy:
            try:
                if not self.pyaudio_instance: raise Exception("Instância PyAudio não disponível para salvar WAV (sistema).")
                with wave.open(TEMP_SYSTEM_AUDIO_FILENAME, 'wb') as wf:
                    wf.setnchannels(channels) 
                    wf.setsampwidth(self.pyaudio_instance.get_sample_size(AUDIO_FORMAT))
                    wf.setframerate(rate) 
                    wf.writeframes(b''.join(frames_copy))
                audio_file_path_to_process = TEMP_SYSTEM_AUDIO_FILENAME
            except Exception as e:
                print(Fore.RED + f"ERRO ao salvar WAV (sistema) para processamento multimodal: {e}\n{traceback.format_exc()}")
                self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao salvar áudio WAV (sistema): {html.escape(str(e))[:50]}</p>", 3000)

        self._threaded_transcribe_audio_and_call_multimodal_vision(audio_file_path_to_process, image_bytes_param, "system")


    def _threaded_transcribe_audio_and_call_multimodal_vision(self, audio_filepath, image_bytes_param, audio_source_type: str):
        if not audio_filepath and not image_bytes_param: 
            self.display_last_chat_message_or_default()
            return

        transcribed_text = ""
        if audio_source_type == "mic":
            transcription_source_prefix = "🎙️ Microfone"
            multimodal_prefix = "🎙️🖼️ Multimodal (Mic)"
            system_prompt_content = "Você é um assistente multimodal. O usuário fornecerá áudio do microfone e/ou uma imagem. Combine as informações para responder."
            base_audio_prompt = "Aqui está o que foi dito (microfone): '{text}'. "
            empty_audio_text = "Microfone vazio ou sem fala detectável."
        elif audio_source_type == "system":
            transcription_source_prefix = "🔊 Som do Sistema"
            multimodal_prefix = "🔊🖼️ Multimodal (Sistema)"
            system_prompt_content = "Você é um assistente multimodal. O usuário fornecerá áudio capturado do sistema e/ou uma imagem. Combine as informações para responder."
            base_audio_prompt = "O seguinte áudio foi capturado do sistema: '{text}'. "
            empty_audio_text = "Som do sistema vazio ou sem áudio detectável."
        else: 
            self.display_last_chat_message_or_default(); return

        
        if audio_filepath:
            self.signal_update_overlay_content.emit(f"<p style='text-align:center;'>Transcrevendo {transcription_source_prefix.lower()} com Whisper...</p>")
            try:
                with open(audio_filepath, "rb") as audio_file_obj:
                    with self._config_lock:
                        whisper_model_name = self.config.get('whisper_model', 'gpt-4o-transcribe')
                    transcription_response = self.openai_client.audio.transcriptions.create(model=whisper_model_name, file=audio_file_obj)
                transcribed_text = transcription_response.text.strip()

                if not transcribed_text:
                    transcribed_text = empty_audio_text
                    if image_bytes_param:
                         self.signal_set_temporary_message.emit(f"<p style='color:orange;text-align:center;'>{transcription_source_prefix} vazio. Processando imagem com contexto de áudio vazio.</p>", 3500)
            except Exception as e_whisper:
                print(Fore.RED + f"ERRO API OpenAI (Whisper - {audio_source_type}): {e_whisper}\n{traceback.format_exc()}")
                transcribed_text = f"Erro ao transcrever {transcription_source_prefix.lower()}: {str(e_whisper)[:50]}"
                if not image_bytes_param: 
                    self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro Whisper ({audio_source_type}) e sem imagem: {html.escape(str(e_whisper))[:70]}</p>", 4000)
                    self.display_last_chat_message_or_default(); return
                else: 
                     self.signal_set_temporary_message.emit(f"<p style='color:orange;text-align:center;'>Erro Whisper ({audio_source_type}). Tentando processar imagem com contexto de erro.</p>", 3500)
            finally:
                if audio_filepath and os.path.exists(audio_filepath):
                    try: os.remove(audio_filepath)
                    except Exception as e_del: print(Fore.RED + f"ERRO ao deletar {audio_filepath}: {e_del}")
        elif not image_bytes_param: 
            self.signal_set_temporary_message.emit("<p style='color:red; text-align:center;'>Sem áudio ou imagem para processar.</p>", 4000)
            self.display_last_chat_message_or_default()
            return


        self.signal_update_overlay_content.emit(f"<p style='text-align:center;'>Enviando {transcription_source_prefix.lower()} (texto) e imagem para IA...</p>")
        self.signal_toggle_processing_flag.emit(True)

        try:
            with self._config_lock:
                multimodal_model_name = self.config.get('model', 'gpt-4o-2024-05-13') 
                max_tokens_api = self.config.get('api_max_tokens', 300)
                max_hist_pairs = self.config.get('max_chat_history_pairs', 7)
                detail_level = self.config.get('vision_detail_level', 'auto')

            user_content_list = []
            
            if transcribed_text and "Erro ao transcrever" not in transcribed_text and "vazio ou sem fala" not in transcribed_text and "vazio ou sem áudio" not in transcribed_text :
                prompt_text_for_multimodal = base_audio_prompt.format(text=transcribed_text)
            else: 
                prompt_text_for_multimodal = f"({transcribed_text}). " 
            
            if image_bytes_param:
                prompt_text_for_multimodal += "Agora, por favor, olhe para a imagem e responda levando em consideração o áudio (ou seu status) e a imagem."
            else: 
                prompt_text_for_multimodal += "Responda com base nesta informação de áudio (ou seu status)."


            user_content_list.append({"type": "text", "text": prompt_text_for_multimodal})

            if image_bytes_param:
                base64_image_str = base64.b64encode(image_bytes_param).decode('utf-8')
                user_content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image_str}", "detail": detail_level }})
            
            if not self.history or self.history[0].get("content") != system_prompt_content:
                 self.history = [{"role": "system", "content": system_prompt_content}]
            
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
            
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(assistant_reply_str, prefix=multimodal_prefix + ":"))
        except Exception as e_multimodal:
            err_msg = f"<p style='color:#FF7043; text-align:center;'>Erro IA Multimodal ({audio_source_type}): {html.escape(str(e_multimodal))[:80]}</p>"
            self.signal_update_overlay_content.emit(err_msg)
            print(Fore.RED + f"ERRO API OpenAI (Multimodal - {audio_source_type}): {e_multimodal}\n{traceback.format_exc()}")
        finally:
            self.signal_toggle_processing_flag.emit(False)


    def _toggle_cursor_blink(self):
        if self.is_text_input_mode and self.user_input_active_for_overlay:
            self.cursor_visible = not self.cursor_visible
            self._update_text_input_overlay_display() 

    def _update_text_input_overlay_display(self):
        if not self.is_text_input_mode:
            return

        history_html = "<div style='margin-bottom: 10px; max-height: 80%; overflow-y: auto;'>"
        num_messages_to_show = self.config.get('max_chat_history_pairs', 7) * 2 
        
        displayable_history = []
        system_prompt_seen = False
        for msg in reversed(self.history): 
            if msg.get("role") == "system":
                system_prompt_seen = True 
                continue 
            if msg.get("role") in ["user", "assistant"]:
                displayable_history.append(msg)
            if len(displayable_history) >= num_messages_to_show:
                break
        displayable_history.reverse() 

        for msg in displayable_history:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user":
                prefix_user = "👤 Você:"
                if isinstance(content, list): 
                    text_part_user = ""
                    for item_user in content:
                        if item_user.get("type") == "text": text_part_user = item_user.get("text",""); break
                    if "microfone" in text_part_user.lower(): prefix_user = "🎙️ Você (áudio):"
                    elif "sistema" in text_part_user.lower(): prefix_user = "🔊 Você (sistema):"
                    elif text_part_user: prefix_user = "🖼️ Você (visão):" 
                    else: prefix_user = "🖼️ (Imagem)" 
                    content_to_display = text_part_user if text_part_user else "(Conteúdo multimodal)"
                    history_html += self._format_gpt_response_for_html_display(content_to_display, prefix_user)
                else: 
                    history_html += self._format_gpt_response_for_html_display(content, prefix_user)
            elif role == "assistant":
                history_html += self._format_gpt_response_for_html_display(content, "💬 IA:")
        history_html += "</div>"

        input_prompt_html = (
            f"<div style='border-top: 1px solid rgba(255,255,255,0.2); padding-top: 5px;'>"
            f"<span style='color:#FFF59D;'><b>&gt;</b> </span><span>{html.escape(self.current_input_text)}</span>"
            f"<span class='blinking-cursor' style='font-weight:bold;'>{'_' if self.user_input_active_for_overlay and self.cursor_visible else ' ' if self.user_input_active_for_overlay else ''}</span>"
            f"</div>"
        )
        
        mode_status_text = "Digitando no Overlay (ESC+= alterna)" if self.user_input_active_for_overlay else "Foco Externo (ESC+= para digitar aqui)"
        status_html = f"<p style='font-size:8pt; color:#aaa; text-align:center;'>Chat Texto: {mode_status_text} | ESC+6 para Sair</p>"

        final_html = history_html + input_prompt_html + status_html
        self.signal_update_overlay_content.emit(final_html)

    def on_hotkey_esc_6_toggle_text_input_mode(self):
        if self.is_recording_mic_audio or self.is_recording_system_audio or self.menu_is_active or self.is_currently_processing_chatgpt:
            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Outra operação em progresso. Finalize-a primeiro.</p>", 3000)
            return

        self.is_text_input_mode = not self.is_text_input_mode
        AppController._chat_hotkeys_globally_enabled = not self.is_text_input_mode 

        if self.is_text_input_mode:
            self.user_input_active_for_overlay = True 
            self.current_input_text = ""
            self.cursor_visible = True
            self.cursor_timer.start(500) 
            
            if not self._text_input_hook_active: 
                try:
                    self._current_keyboard_hook = keyboard.hook(self._process_text_input_event, suppress=False) 
                    self._text_input_hook_active = True
                    print(Fore.GREEN + "Gancho de teclado para entrada de texto ATIVADO.")
                except Exception as e:
                    print(Fore.RED + f"Erro ao registrar gancho de teclado para texto: {e}")
                    self.is_text_input_mode = False 
                    AppController._chat_hotkeys_globally_enabled = True
                    self.signal_set_temporary_message.emit("<p style='color:red;'>Erro ao ativar modo de texto.</p>", 3000)
                    return
            self._update_text_input_overlay_display()
        else: 
            self.user_input_active_for_overlay = False
            self.cursor_timer.stop()
            if self._text_input_hook_active and self._current_keyboard_hook is not None:
                try:
                    keyboard.unhook(self._current_keyboard_hook)
                    self._current_keyboard_hook = None 
                    self._text_input_hook_active = False
                    print(Fore.YELLOW + "Gancho de teclado para entrada de texto DESATIVADO.")
                except Exception as e: 
                    print(Fore.RED + f"Erro ao remover gancho de teclado para texto: {e}")
            self.display_last_chat_message_or_default()


    def on_hotkey_esc_equals_toggle_input_focus(self):
        if self.is_text_input_mode:
            self.user_input_active_for_overlay = not self.user_input_active_for_overlay
            self.cursor_visible = True 
            if not self.user_input_active_for_overlay:
                self.cursor_timer.stop() 
            else:
                self.cursor_timer.start(500) 
            self._update_text_input_overlay_display()
            feedback_msg = "Entrada de texto no overlay ATIVADA." if self.user_input_active_for_overlay else "Entrada de texto no overlay DESATIVADA (foco externo)."
            self.signal_set_temporary_message.emit(f"<p style='text-align:center;'>{feedback_msg}</p>", 2000)


    def _process_text_input_event(self, event: keyboard.KeyboardEvent):
        should_suppress = False
        if self.is_text_input_mode and self.user_input_active_for_overlay and event.event_type == keyboard.KEY_DOWN:
            key_name = event.name
            
            if key_name == 'enter':
                self._send_current_text_input_to_ai()
                should_suppress = True 
            elif key_name == 'backspace':
                if self.current_input_text: 
                    self.current_input_text = self.current_input_text[:-1]
                self._update_text_input_overlay_display()
                should_suppress = True
            elif key_name == 'space':
                self.current_input_text += ' '
                self._update_text_input_overlay_display()
                should_suppress = True
            elif key_name == 'esc': 
                return True 
            elif key_name and len(key_name) == 1: 
                char_to_add = key_name
                if 'a' <= char_to_add.lower() <= 'z':
                    if keyboard.is_pressed('shift') or keyboard.is_pressed('left shift') or keyboard.is_pressed('right shift'):
                        char_to_add = char_to_add.upper()
                
                self.current_input_text += char_to_add
                self._update_text_input_overlay_display()
                should_suppress = True
        
        return not should_suppress 


    def _send_current_text_input_to_ai(self):
        if not self.current_input_text.strip():
            self.signal_set_temporary_message.emit("<p style='color:orange;text-align:center;'>Digite uma mensagem para enviar.</p>", 2000)
            return

        if not self.openai_client:
            self.signal_set_temporary_message.emit("<p style='color:red;text-align:center;'>ERRO: Cliente OpenAI não configurado.</p>", 3000)
            return

        self.signal_toggle_processing_flag.emit(True)
        text_to_send = self.current_input_text
        self.current_input_text = "" 
        self._update_text_input_overlay_display() 
        
        text_chat_system_prompt = "Você é um assistente de chat prestativo e conciso. Responda diretamente à pergunta do usuário."
        if not self.history or self.history[0].get("content") != text_chat_system_prompt:
             self.history = [{"role": "system", "content": text_chat_system_prompt}]


        self.history.append({"role": "user", "content": text_to_send})
        
        with self._config_lock:
            chat_model_name = self.config.get('chat_model', 'gpt-4o-2024-05-13') 
            max_tokens = self.config.get('api_max_tokens', 300)
            max_hist_pairs = self.config.get('max_chat_history_pairs', 10) 

        current_history_for_api = list(self.history)
        if len(current_history_for_api) > (max_hist_pairs * 2 + 1):
            current_history_for_api = [current_history_for_api[0]] + current_history_for_api[-(max_hist_pairs * 2):]
        
        try:
            api_response = self.openai_client.chat.completions.create(
                model=chat_model_name,
                messages=current_history_for_api,
                max_tokens=max_tokens
            )
            assistant_reply = api_response.choices[0].message.content
            self.history.append({"role": "assistant", "content": assistant_reply})

            if len(self.history) > (max_hist_pairs * 2 + 1):
                 self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]

        except Exception as e:
            error_message = f"Erro na API OpenAI (Chat): {html.escape(str(e))[:100]}"
            self.history.append({"role": "assistant", "content": f"Erro: {error_message}"}) 
            print(Fore.RED + f"ERRO API OpenAI (Chat Texto): {e}\n{traceback.format_exc()}")
        finally:
            self.signal_toggle_processing_flag.emit(False)
            self._update_text_input_overlay_display() 


    def _prompt_for_margins(self):
        msg = ("<p style='text-align:center;'>Use <b>CTRL+9</b> para configs. web<br/>e ajustar margens por lá.</p>"
               "<p style='text-align:center; font-size:small;'>(Voltando ao menu em 7s...)</p>")
        self.signal_set_temporary_message.emit(msg, 7000)
        
    def on_menu_option_selected_enter(self):
        if self.is_text_input_mode: 
            self.signal_set_temporary_message.emit("<p style='text-align:center;'>Saia do modo de texto (ESC+6) primeiro.</p>", 2500); return
        try:
            if not self.menu_is_active: return
            if self.is_recording_mic_audio or self.is_recording_system_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação (ESC+4 ou ESC+5) primeiro.</p>", 2500); return
            
            self.temporary_state_clear_timer.stop() 
            selected_opt_str = self.menu_options_list[self.current_menu_selection_idx]
            feedback_msg_html = ""; config_changed = False; keep_menu_open = True 
            
            with self._config_lock: current_config_copy = dict(self.config)

            if selected_opt_str == "Alternar Opacidade":
                opac_cycle = [0.4, 0.6, 0.8, 1.0]; current_opac = current_config_copy.get('opacity',0.8)
                try: idx = opac_cycle.index(current_opac)
                except ValueError: idx = opac_cycle.index(min(opac_cycle, key=lambda x:abs(x-current_opac))) 
                current_config_copy['opacity'] = opac_cycle[(idx + 1) % len(opac_cycle)]
                feedback_msg_html = f"Opacidade: {current_config_copy['opacity']*100:.0f}%"; config_changed = True
            elif selected_opt_str == "Alternar Posição":
                pos_cycle = ['top-right', 'top-left', 'bottom-right', 'bottom-left']; current_pos = current_config_copy.get('position','top-right')
                try: idx = pos_cycle.index(current_pos)
                except ValueError: idx = -1 
                current_config_copy['position'] = pos_cycle[(idx + 1) % len(pos_cycle)]
                feedback_msg_html = f"Posição: {current_config_copy['position'].replace('-', ' ').title()}"; config_changed = True
            elif selected_opt_str == "Alternar Modelo GPT Visão/Multimodal":
                model_cycle = ["gpt-4o-2024-05-13", "gpt-4o", "gpt-4-turbo"] 
                current_model = current_config_copy.get('model', 'gpt-4o-2024-05-13')
                try: idx = model_cycle.index(current_model)
                except ValueError: idx = -1 
                new_model_selection = model_cycle[(idx + 1) % len(model_cycle)]
                current_config_copy['model'] = new_model_selection
                current_config_copy['chat_model'] = new_model_selection 
                feedback_msg_html = f"Modelo Visão/Multimodal/Chat: {current_config_copy['model']}"; config_changed = True
            elif selected_opt_str == "Margens (via Web)": 
                self._prompt_for_margins(); return 
            elif selected_opt_str == "Configurações Web (CTRL+9)": 
                self.on_hotkey_web_config(); return 
            elif selected_opt_str == "Sair": 
                self.cleanup_on_exit(); QtWidgets.QApplication.quit(); return 
            else: 
                keep_menu_open = False

            if config_changed:
                with self._config_lock: self.config.update(current_config_copy) 
                self.save_config()
                self.signal_apply_config_to_overlay.emit(dict(current_config_copy)) 

            if feedback_msg_html: 
                self.signal_set_temporary_message.emit(f"<p style='text-align:center;'>{feedback_msg_html}</p>", 2000)
            elif not keep_menu_open : 
                self.menu_is_active = False; AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
        except Exception as e: 
            print(Fore.RED + f"ERRO Menu Enter: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit("<p style='color:red;text-align:center'>Erro ao processar opção do menu.</p>", 3000)
            
    def display_last_chat_message_or_default(self):
        if self._temporary_message_active or self.is_recording_mic_audio or self.is_recording_system_audio or self.is_text_input_mode: return 
        if self.is_currently_processing_chatgpt: 
             self.signal_update_overlay_content.emit("<p style='text-align:center;'>Processando com IA...</p>"); return
        
        last_assistant_msg_str = ""; prefix = "💬 IA:" 
        if self.history: 
            for msg_idx in range(len(self.history) - 1, -1, -1): 
                msg = self.history[msg_idx]
                if msg["role"] == "assistant":
                    last_assistant_msg_str = msg["content"]
                    if msg_idx > 0: 
                        prev_user_msg = self.history[msg_idx - 1]
                        if prev_user_msg["role"] == "user":
                            prev_user_content = prev_user_msg.get("content")
                            if isinstance(prev_user_content, list): 
                                has_image = any(item.get("type") == "image_url" for item in prev_user_content)
                                text_part_lower = ""
                                for item in prev_user_content:
                                    if item.get("type") == "text":
                                        text_part_lower = item.get("text","").lower(); break
                                
                                if has_image and ("microfone" in text_part_lower or "foi dito" in text_part_lower):
                                    prefix = "🎙️🖼️ Multimodal (Mic):"
                                elif has_image and ("sistema" in text_part_lower or "capturado do sistema" in text_part_lower):
                                    prefix = "🔊🖼️ Multimodal (Sistema):"
                                elif has_image: prefix = "🖼️ Visão:"
                            
                    self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(last_assistant_msg_str, prefix=prefix))
                    return 
        
        self.signal_update_overlay_content.emit("<p style='text-align:center; font-size:9pt; color:#ccc;'>"
                                               "<span style='color:#FFB74D;'>ESC+1</span>: Visão | <span style='color:#AED581;'>ESC+3</span>: Menu<br>"
                                               "<span style='color:#81D4FA;'>ESC+4</span>: Mic+Tela→IA | <span style='color:#FF80AB;'>ESC+5</span>: SomSis+Tela→IA<br>"
                                               "<span style='color:#9FA8DA;'>ESC+6</span>: Chat Texto (ESC+= Foco) | <span style='color:#CE93D8;'>CTRL+9</span>: Web</p>")
    
    def on_hotkey_esc_1(self): 
        try: self._initiate_chatgpt_request(True)
        except Exception as e: print(Fore.RED + f"ERRO ESC+1: {e}\n{traceback.format_exc()}")
    def on_hotkey_esc_2(self): 
        try: self._initiate_chatgpt_request(False)
        except Exception as e: print(Fore.RED + f"ERRO ESC+2: {e}\n{traceback.format_exc()}")
    
    def on_hotkey_esc_3_menu_toggle(self):
        if self.is_text_input_mode:
            self.signal_set_temporary_message.emit("<p style='text-align:center;'>Saia do modo de texto (ESC+6) primeiro.</p>", 2500); return
        try:
            if self.is_currently_processing_chatgpt or self.is_recording_mic_audio or self.is_recording_system_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>IA ou Gravação ocupada. Aguarde.</p>", 2000); return
            self.menu_is_active = not self.menu_is_active
            AppController._chat_hotkeys_globally_enabled = not self.menu_is_active 
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop() 
                self.current_menu_selection_idx = 0
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
            else: 
                self.display_last_chat_message_or_default()
        except Exception as e: print(Fore.RED + f"ERRO ESC+3: {e}\n{traceback.format_exc()}")

    def on_hotkey_esc_0_exit_menu_or_clear(self):
        try:
            if self.is_text_input_mode: 
                self.current_input_text = "" 
                self._update_text_input_overlay_display()
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Linha de entrada limpa. (ESC+6 para sair do modo)</p>", 2000)
                return

            if self.menu_is_active:
                self.menu_is_active = False; AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
            elif not self.is_currently_processing_chatgpt and not self.is_recording_mic_audio and not self.is_recording_system_audio: 
                self.signal_update_overlay_content.emit("") 
                self.history = [] 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Overlay e histórico limpos.</p>",1500)

            elif self.is_recording_mic_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Use ESC+4 para parar a gravação do microfone.</p>", 2500)
            elif self.is_recording_system_audio:
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Use ESC+5 para parar a gravação do som do sistema.</p>", 2500)
        except Exception as e: print(Fore.RED + f"ERRO ESC+0: {e}\n{traceback.format_exc()}")

    def on_hotkey_web_config(self): 
        if self.is_text_input_mode:
            self.signal_set_temporary_message.emit("<p style='text-align:center;'>Saia do modo de texto (ESC+6) primeiro.</p>", 2500); return
        try:
            if self.menu_is_active: self.on_hotkey_esc_3_menu_toggle() 
            if self.is_recording_mic_audio or self.is_recording_system_audio: 
                self.signal_set_temporary_message.emit("<p style='text-align:center;'>Finalize a gravação (ESC+4 ou ESC+5) antes.</p>", 2500); return
            
            flask_port = self.get_config_value('port', 43000); flask_url = f"http://127.0.0.1:{flask_port}"; msg_extra = ""
            
            if not self.flask_server_thread_obj or not self.flask_server_thread_obj.is_alive():
                 if 'start_web_server' in globals(): 
                    self.flask_server_thread_obj = globals()['start_web_server'](self) 
                    msg_extra = "Servidor de config. iniciado!"
                 else:
                    msg_extra = "Erro: Função start_web_server não encontrada."
            else:
                 msg_extra = "Servidor de config. já está rodando!"
                
            msg_html = (f"<div style='text-align:center;'><p>{msg_extra}<br/>"
                        f"Acesse: <a href='{flask_url}' style='color:#81D4FA;text-decoration:underline;'>{flask_url}</a></p>"
                        f"<p style='font-size:small;'>(Retornando em 15s ou ESC+0)</p></div>")
            self.signal_set_temporary_message.emit(msg_html, 15000)
        except Exception as e: 
            print(Fore.RED + f"ERRO CTRL+9 (Web Config): {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit(f"<p style='color:red;text-align:center;'>Erro ao abrir config web: {html.escape(str(e))[:50]}</p>", 4000)
            
    def on_menu_navigation_input(self, direction_str_up_down):
        if self.is_text_input_mode: return 
        try:
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop() 
                if direction_str_up_down == "up": 
                    self.current_menu_selection_idx = (self.current_menu_selection_idx - 1 + len(self.menu_options_list)) % len(self.menu_options_list)
                else: # "down"
                    self.current_menu_selection_idx = (self.current_menu_selection_idx + 1) % len(self.menu_options_list)
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        except Exception as e: 
            print(Fore.RED + f"ERRO Navegação Menu ({direction_str_up_down}):{e}\n{traceback.format_exc()}")
    
    def cleanup_on_exit(self):
        print(Fore.GREEN + "Limpando recursos antes de sair...")
        self.save_config()

        if self._text_input_hook_active and self._current_keyboard_hook is not None:
            try:
                keyboard.unhook(self._current_keyboard_hook) 
                self._current_keyboard_hook = None
                self._text_input_hook_active = False
                print(Fore.GREEN + "Gancho de teclado para entrada de texto DESATIVADO na saída.")
            except Exception as e: 
                print(Fore.RED + f"Erro ao remover gancho de texto na saída: {e}")
        elif self._text_input_hook_active: 
             print(Fore.YELLOW + "Aviso: Gancho de texto estava ativo mas sem handle para remover especificamente.")


        if self.pyaudio_instance:
            try:
                self.pyaudio_instance.terminate()
                print(Fore.GREEN + "Instância PyAudio finalizada.")
            except Exception as e:
                print(Fore.RED + f"Erro ao finalizar PyAudio: {e}")
        
        for temp_file in [TEMP_AUDIO_FILENAME, TEMP_SYSTEM_AUDIO_FILENAME]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    print(Fore.YELLOW + f"Arquivo temporário {temp_file} removido.")
                except Exception as e_del:
                    print(Fore.RED + f"Erro ao deletar {temp_file}: {e_del}")

# --- Main Application Setup & Execution ---
def main():
    try:
        if sys.platform == "win32": 
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
            try: QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
            except: pass 

        app = QtWidgets.QApplication(sys.argv)
        
        placeholder_initial_config = {'opacity':0.8, 'position':'top-right', 'overlay_width':420, 
            'overlay_v_offset':25, 'overlay_h_offset':25, 'overlay_height_ratio': 0.85 }
        overlay_widget_instance = Overlay(placeholder_initial_config)
        app_controller_instance = AppController(overlay_widget_instance) 

        hotkeys_config = [
            ('esc+1', app_controller_instance.on_hotkey_esc_1), 
            ('esc+2', app_controller_instance.on_hotkey_esc_2), 
            ('esc+3', app_controller_instance.on_hotkey_esc_3_menu_toggle), 
            ('esc+4', app_controller_instance.on_hotkey_esc_4_mic_audio_toggle), 
            ('esc+5', app_controller_instance.on_hotkey_esc_5_system_audio_toggle), 
            ('esc+6', app_controller_instance.on_hotkey_esc_6_toggle_text_input_mode), 
            ('esc+=', app_controller_instance.on_hotkey_esc_equals_toggle_input_focus),
            ('esc+0', app_controller_instance.on_hotkey_esc_0_exit_menu_or_clear), 
            ('ctrl+9', app_controller_instance.on_hotkey_web_config), 
            ('esc+up', lambda: app_controller_instance.on_menu_navigation_input("up")), 
            ('esc+down', lambda: app_controller_instance.on_menu_navigation_input("down")), 
            ('esc+enter', app_controller_instance.on_menu_option_selected_enter), 
            ('ctrl+alt+esc', lambda: (app_controller_instance.cleanup_on_exit(), QtWidgets.QApplication.quit())) 
        ]
        
        for key_combo, callback_func in hotkeys_config:
            try: 
                keyboard.add_hotkey(key_combo, callback_func, suppress=True, timeout=0.1, trigger_on_release=False)
            except Exception as e_hk: 
                print(Fore.RED + f"Erro ao registrar hotkey {key_combo}: {e_hk}")

        app.aboutToQuit.connect(app_controller_instance.cleanup_on_exit) 
        
        app_controller_instance.signal_set_temporary_message.emit(
            "<div style='text-align:center; font-size:9pt;'>"
            "<b>Peach Overlay Iniciado!</b><br>"
            "<span style='color:#FFB74D;'>ESC+1</span>: Visão | <span style='color:#AED581;'>ESC+3</span>: Menu<br>"
            "<span style='color:#81D4FA;'>ESC+4</span>: Mic+Tela→IA | <span style='color:#FF80AB;'>ESC+5</span>: SomSis+Tela→IA<br>"
            "<span style='color:#9FA8DA;'>ESC+6</span>: Chat Texto (ESC+= Foco) | <span style='color:#CE93D8;'>CTRL+9</span>: Web"
            "</div>", 10000 ) 
        
        exit_status_code = app.exec_()

    except Exception as e_main:
        print(Fore.RED + f"Erro fatal na aplicação: {e_main}\n{traceback.format_exc()}")
        try: keyboard.unhook_all() 
        except Exception: pass
        sys.exit(1) 
    finally:
        print(Fore.YELLOW + "Desregistrando todas as hotkeys e ganchos do teclado...")
        try: keyboard.unhook_all() 
        except Exception as e_final_unhook: print(Fore.RED + f"Erro ao desregistrar ganchos na finalização: {e_final_unhook}")
        
        for temp_file in [TEMP_AUDIO_FILENAME, TEMP_SYSTEM_AUDIO_FILENAME]:
            if os.path.exists(temp_file):
                try: os.remove(temp_file)
                except Exception as e_fdel: print(Fore.RED + f"Erro na limpeza final de {temp_file}: {e_fdel}")
    sys.exit(exit_status_code)


if __name__ == "__main__":
    if not PYAUDIO_AVAILABLE and os.name == 'nt': 
        print("-" * 70 + Fore.YELLOW + "\nAVISO: PyAudio não foi carregado. A funcionalidade de gravação de áudio estará desabilitada.\n"
              + Fore.WHITE + "Para habilitar, tente:\n"
              + Fore.CYAN + "1" + Fore.WHITE + ". Instalar o PyAudio: 'pip install pyaudio'\n"
              + Fore.CYAN + "2" + Fore.WHITE + ". Se a instalação direta falhar, você pode precisar instalar de um arquivo .whl:\n"
              + Fore.LIGHTBLUE_EX + "   a. Baixe o wheel apropriado para sua versão do Python e arquitetura do Windows\n"
              + Fore.LIGHTBLUE_EX + "      (procure por 'PyAudio wheels for Windows Python X.Y').\n"
              + Fore.LIGHTBLUE_EX + "   b. Instale com: 'pip install nome_do_arquivo.whl'\n"
              + Fore.CYAN + "3" + Fore.WHITE + ". Verifique também se o 'Microsoft Visual C++ Build Tools' está instalado.\n"
              + Fore.CYAN + "4" + Fore.WHITE + ". Para gravação do SOM DO SISTEMA (ESC+5), certifique-se que 'Stereo Mix' (ou 'Mixagem Estéreo') está HABILITADO nos seus dispositivos de gravação do Windows.\n" + "-" * 70)
    
    print(Fore.GREEN + "Iniciando Peach Overlay (OverlayGPT)...")
    main()
