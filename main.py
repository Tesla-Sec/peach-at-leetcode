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
from flask import Flask, request, redirect # Removido jsonify por não ser usado
from ctypes import wintypes
import json
import html # Para escapar HTML na saída do GPT
import traceback # Para logar exceções completas

# 1) Carrega .env e Configurações
load_dotenv()

CONFIG_FILE = "config.json"

# Constantes WinAPI
WDA_NONE                 = 0x00000000
WDA_MONITOR              = 0x00000001
WDA_EXCLUDEFROMCAPTURE   = 0x00000011 # Requer Windows 10 Build 2004+

user32 = ctypes.windll.user32

# --- Flask Web Server ---
def start_web_server(app_controller_ref):
    app_flask = Flask(__name__)

    @app_flask.route('/', methods=['GET', 'POST'])
    def root():
        # app_controller_ref é a instância do AppController
        config_ref_dict = app_controller_ref.get_config_copy_for_web() # Pega uma cópia segura para ler/modificar
        
        if request.method == 'POST':
            original_config_for_comparison = dict(config_ref_dict) # Cópia para comparar o que mudou
            
            # As chaves a serem atualizadas diretamente
            keys_to_update = ['model', 'opacity', 'position']
            types_map = {'opacity': float, 'model':str, 'position':str}
            
            for key in keys_to_update:
                form_val = request.form.get(key)
                if form_val is not None:
                    try:
                        typed_val = types_map[key](form_val)
                        if types_map[key] == float: # Para opacidade
                            typed_val = round(typed_val, 2)
                            if not (0.0 <= typed_val <= 1.0): continue # Ignora se inválido
                        
                        if key not in config_ref_dict or config_ref_dict[key] != typed_val:
                            config_ref_dict[key] = typed_val
                    except ValueError:
                        print(f"Erro ao converter valor do form para {key}: {form_val}")
            
            # Margens (x1,y1,x2,y2)
            try:
                m_x1 = int(request.form.get('x1', config_ref_dict['margin'][0]))
                m_y1 = int(request.form.get('y1', config_ref_dict['margin'][1]))
                m_x2 = int(request.form.get('x2', config_ref_dict['margin'][2]))
                m_y2 = int(request.form.get('y2', config_ref_dict['margin'][3]))
                new_margin_list = [m_x1, m_y1, m_x2, m_y2]
                if config_ref_dict['margin'] != new_margin_list:
                    config_ref_dict['margin'] = new_margin_list
            except ValueError:
                print("Erro ao converter margens do formulário web.")
            
            # Compara se houve mudança efetiva
            changed_values = {}
            for key in config_ref_dict:
                if key not in original_config_for_comparison or original_config_for_comparison[key] != config_ref_dict[key]:
                    changed_values[key] = config_ref_dict[key]

            if changed_values:
                app_controller_ref.web_config_change_requested.emit(changed_values)

            return redirect('/')

        margin_vals = config_ref_dict.get('margin', [0,0,0,0])
        if not isinstance(margin_vals, list) or len(margin_vals) != 4:
            margin_vals = [0,0,0,0]

        return f'''
        <html><head><title>Configurações OverlayGPT</title>
        <meta http-equiv="refresh" content="30">
        <style> body {{ font-family: Segoe UI, sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }} 
                 label {{ display: inline-block; width: 160px; margin-bottom: 8px; font-weight: bold; }} 
                 input, select {{ margin-bottom: 12px; padding: 8px; border-radius: 4px; border: 1px solid #ccc; width: 200px; box-sizing: border-box; }} 
                 input[type="number"] {{ width: 70px; }}
                 .margin-inputs input {{ width:60px; margin-right: 5px;}}
                 button {{ padding: 10px 18px; background-color: #0078D4; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }} 
                 button:hover {{ background-color: #005a9e; }} 
                 h2 {{ border-bottom: 2px solid #0078D4; padding-bottom: 10px; color: #0078D4; }}
                 .container {{ background-color: white; padding: 25px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); }}
        </style>
        </head><body>
          <div class="container">
          <h2>Configurações Avançadas</h2>
          <form method="post">
            <label for="gpt_model">Modelo GPT:</label>
            <input type="text" id="gpt_model" name="gpt_model" value="{html.escape(str(config_ref_dict.get('model','')))}"/><br/>
            
            <label>Margem (X1,Y1,X2,Y2):</label>
            <span class="margin-inputs">
            <input type="number" name="x1" value="{margin_vals[0]}" placeholder="X1"/>
            <input type="number" name="y1" value="{margin_vals[1]}" placeholder="Y1"/>
            <input type="number" name="x2" value="{margin_vals[2]}" placeholder="X2"/>
            <input type="number" name="y2" value="{margin_vals[3]}" placeholder="Y2"/>
            </span><br/>
            
            <label for="opacity">Opacidade (0.0-1.0):</label>
            <input type="number" id="opacity" step="0.05" name="opacity" min="0" max="1" value="{config_ref_dict.get('opacity',0.7):.2f}"/><br/>

            <label for="position">Posição do Overlay:</label>
            <select id="position" name="position">
                <option value="top-right" {"selected" if config_ref_dict.get('position') == 'top-right' else ""}>Canto Sup. Direito</option>
                <option value="top-left" {"selected" if config_ref_dict.get('position') == 'top-left' else ""}>Canto Sup. Esquerdo</option>
                <option value="bottom-right" {"selected" if config_ref_dict.get('position') == 'bottom-right' else ""}>Canto Inf. Direito</option>
                <option value="bottom-left" {"selected" if config_ref_dict.get('position') == 'bottom-left' else ""}>Canto Inf. Esquerdo</option>
            </select><br/>

            <button type="submit">Salvar Configurações</button>
          </form>
          </div>
        </body></html>
        '''
    
    thread = threading.Thread(target=lambda: app_flask.run(host='0.0.0.0', port=app_controller_ref.get_config_value('port'), debug=False, use_reloader=False), daemon=True)
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
        # self.setFocusPolicy(QtCore.Qt.NoFocus) # Descomentar se WA_ShowWithoutActivating não for suficiente

        self.current_config = dict(initial_config_dict) 
        self.screen_geom = QtWidgets.QApplication.primaryScreen().geometry()

        self.text_label = QtWidgets.QLabel(self)
        self.text_label.setStyleSheet(
            "color: white; background: rgba(20,20,20,0.8); padding: 10px; "
            "border-radius: 8px; font-size: 10pt; border: 1px solid rgba(255,255,255,0.1);"
        )
        self.text_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.text_label.setWordWrap(True)
        self.text_label.setOpenExternalLinks(True)
        
        self.apply_geometry_from_config(self.current_config)
        self.show()
        QtCore.QTimer.singleShot(150, self.exclude_from_capture) # Aumentar um pouco o delay

    def apply_geometry_from_config(self, config_dict):
        #print(f"Overlay aplicando config: {config_dict}")
        self.current_config = dict(config_dict) 
        self.setWindowOpacity(self.current_config.get('opacity', 0.75))

        overlay_width = self.current_config.get('overlay_width', 400)
        v_offset = self.current_config.get('overlay_v_offset', 20)
        h_offset = self.current_config.get('overlay_h_offset', 20)
        # Altura do overlay é dinâmica ou fixa? Pela config é fixa (tela_cheia - offsets)
        overlay_height_ratio = self.current_config.get('overlay_height_ratio', 0.9) # Ex: 90% da tela
        effective_screen_height = self.screen_geom.height() - (2 * v_offset)
        overlay_height = effective_screen_height * overlay_height_ratio # Ou valor fixo da config.


        position_str = self.current_config.get('position', 'top-right')
        
        if position_str == 'top-right':
            pos_x = self.screen_geom.width() - overlay_width - h_offset
            pos_y = v_offset
        elif position_str == 'top-left':
            pos_x = h_offset
            pos_y = v_offset
        elif position_str == 'bottom-right':
            pos_x = self.screen_geom.width() - overlay_width - h_offset
            #pos_y = self.screen_geom.height() - overlay_height - v_offset # Se altura for fixa
            pos_y = self.screen_geom.height() * (1 - overlay_height_ratio) - v_offset if overlay_height_ratio < 1 else v_offset

        elif position_str == 'bottom-left':
            pos_x = h_offset
            #pos_y = self.screen_geom.height() - overlay_height - v_offset # Se altura for fixa
            pos_y = self.screen_geom.height() * (1 - overlay_height_ratio) - v_offset if overlay_height_ratio < 1 else v_offset
        else: # Default para top-right se config estranha
            pos_x = self.screen_geom.width() - overlay_width - h_offset
            pos_y = v_offset

        self.setGeometry(int(pos_x), int(pos_y), int(overlay_width), int(overlay_height))
        if hasattr(self, 'text_label'): # text_label pode não existir se construtor falhar
             self.text_label.setGeometry(0, 0, int(overlay_width), int(overlay_height))

    def exclude_from_capture(self):
        try:
            hwnd = self.winId().__int__() # Mais robusto que .__int__() em algumas versões
            if not hwnd: # Pode acontecer se a janela for destruída
                print("Overlay HWND não disponível (janela pode ter sido fechada).")
                return

            # Tenta primeiro WDA_EXCLUDEFROMCAPTURE (ideal)
            if hasattr(user32, 'SetWindowDisplayAffinity'):
                if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                    print(f"Overlay (HWND: {hwnd}): DisplayAffinity = EXCLUDEFROMCAPTURE (SUCESSO).")
                else:
                    error_code = ctypes.get_last_error()
                    # Se WDA_EXCLUDEFROMCAPTURE falhar (ex: versão antiga do Windows), tenta WDA_MONITOR
                    print(f"Overlay (HWND: {hwnd}): FALHA SetDisplayAffinity(EXCLUDEFROMCAPTURE). Erro: {error_code}. Tentando WDA_MONITOR.")
                    user32.SetLastError(0) # Limpa o erro para a próxima chamada
                    if not user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
                        error_code_monitor = ctypes.get_last_error()
                        user32.SetLastError(0)
                        print(f"Overlay (HWND: {hwnd}): FALHA SetDisplayAffinity(MONITOR). Erro: {error_code_monitor}")
                    else:
                        print(f"Overlay (HWND: {hwnd}): DisplayAffinity = MONITOR (SUCESSO - tela preta na captura).")
            else:
                print("Função SetWindowDisplayAffinity não encontrada (versão do Windows?).")

            # Estilos adicionais para 'stealth' (opcional, pode interferir com cliques se muito agressivo)
            # WS_EX_TOOLWINDOW para não aparecer na taskbar é uma boa
            # WS_EX_NOACTIVATE para não pegar foco
            # WS_EX_TRANSPARENT pode ser muito agressivo se precisar de cliques no overlay (para links)
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TRANSPARENT = 0x00000020

            current_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_ex_style = current_ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
            print(f"Overlay (HWND: {hwnd}): Estilos de janela estendidos aplicados.")

        except Exception as e:
            print(f"Erro crítico ao configurar estilos de janela/afinidade: {e}\n{traceback.format_exc()}")

    @QtCore.pyqtSlot(str) # Garante que este slot é chamado na thread da GUI
    def update_text_display(self, content_html_str):
        try:
            if self.text_label: # Checa se o label ainda existe
                self.text_label.setText(content_html_str)
        except Exception as e:
            print(f"Erro ao atualizar texto do overlay (QLabel): {e}\n{traceback.format_exc()}")
            if self.text_label:
                self.text_label.setText("<p style='color:red;'>Erro ao renderizar texto.</p>")

    @QtCore.pyqtSlot(list, int) # Slot para menu
    def show_menu_display_slot(self, options_list_str, selected_idx_int):
        # O nome do método foi alterado para indicar que é um slot
        # Este método agora SEMPRE roda na thread da GUI
        menu_html = "<div style='padding:5px;'>"
        menu_html += "<p style='margin-bottom:10px; font-weight:bold; color:#90CAF9;'>MENU DE OPÇÕES:</p><ul style='list-style:none; padding-left:0;'>"
        for i, opt_text_str in enumerate(options_list_str):
            style = "padding:3px 0; padding-left:8px;"
            prefix = "    "
            if i == selected_idx_int:
                style = "padding:3px 0; background-color:rgba(144, 202, 249, 0.2); border-left:3px solid #90CAF9; padding-left:5px;"
                prefix = "<b>→ "
                suffix = "</b>"
            else:
                suffix = ""
            menu_html += f"<li style='{style}'>{prefix}{html.escape(opt_text_str)}{suffix}</li>"
        menu_html += "</ul><p style='font-size:9pt; color:#BDBDBD; margin-top:15px;'><small>(ESC+Setas: Navegar | ESC+Enter: Selecionar | ESC+0: Fechar)</small></p>"
        menu_html += "</div>"
        self.update_text_display(menu_html) # update_text_display já é um slot

# --- App Controller (Lógica Principal) ---
class AppController(QtCore.QObject):
    # Sinais para atualizações da GUI (a serem emitidos por threads)
    signal_update_overlay_content = QtCore.pyqtSignal(str)
    signal_update_menu_display = QtCore.pyqtSignal(list, int)
    signal_set_temporary_message = QtCore.pyqtSignal(str, int)
    signal_apply_config_to_overlay = QtCore.pyqtSignal(dict)
    signal_toggle_processing_flag = QtCore.pyqtSignal(bool) # Para self.is_currently_processing_chatgpt
    web_config_change_requested = QtCore.pyqtSignal(dict) # Para o Flask

    _chat_hotkeys_globally_enabled = True

    def __init__(self, overlay_qt_widget):
        super().__init__()
        self.overlay = overlay_qt_widget
        self.history = []
        self.menu_is_active = False
        self.menu_options_list = [
            "Alternar Opacidade", "Alternar Posição", "Alternar Modelo GPT",
            "Margens da Captura", "Configurações Web", "Sair"
        ]
        self.current_menu_selection_idx = 0
        
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        if not os.getenv("OPENAI_API_KEY"):
            print("ERRO: Chave OPENAI_API_KEY não encontrada no .env!")
            # Você pode querer exibir isso no overlay também com um sinal
            # self.signal_set_temporary_message.emit("Chave OpenAI não configurada!", 10000)
            # sys.exit(1) # Ou sair
        
        self._config_lock = threading.Lock() # Lock para proteger self.config
        self.config = self.load_config_from_json() # Carrega antes de conectar sinais
        
        # Conectar sinais aos slots
        self.signal_update_overlay_content.connect(self.overlay.update_text_display)
        self.signal_update_menu_display.connect(self.overlay.show_menu_display_slot)
        self.signal_set_temporary_message.connect(self._set_temporary_message_slot)
        self.signal_apply_config_to_overlay.connect(self.overlay.apply_geometry_from_config)
        self.signal_toggle_processing_flag.connect(self._set_processing_flag_slot)
        self.web_config_change_requested.connect(self.handle_web_config_change)


        self.signal_apply_config_to_overlay.emit(dict(self.config)) # Aplica config inicial via sinal

        self.flask_server_thread_obj = None
        self.is_currently_processing_chatgpt = False
        self._temporary_message_active = False

        # Config watcher timer (para edições manuais do JSON, menos crítico agora com Flask usando sinais)
        # self.config_watcher_timer = QtCore.QTimer(self)
        # self.config_watcher_timer.timeout.connect(self.check_and_apply_config_changes_to_overlay)
        # self.config_watcher_timer.start(5000) 

        self.temporary_state_clear_timer = QtCore.QTimer(self)
        self.temporary_state_clear_timer.setSingleShot(True)
        self.temporary_state_clear_timer.timeout.connect(self.clear_temporary_message_and_restore_chat_view)

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
                elif key not in self.config: # Nova chave adicionada pelo Flask (improvável com o form atual)
                    self.config[key] = value
                    config_actually_updated = True
        
        if config_actually_updated:
            print(f"Configurações atualizadas via web: {changed_values_from_web}")
            self.save_config() # Salva toda a config (com lock)
            self.signal_apply_config_to_overlay.emit(dict(self.config)) # Emite cópia para overlay

    def load_config_from_json(self):
        with self._config_lock: # Protege acesso ao self.config durante a inicialização
            default_cfg = {
                'opacity': 0.8, 'position': 'top-right', 'model': 'gpt-4o', # gpt-4.1 não existe, gpt-4o é bom
                'port': 43000, 'margin': [0, 0, 0, 0], 'overlay_width': 420,
                'overlay_v_offset': 25, 'overlay_h_offset': 25, 'max_chat_history_pairs': 10,
                'vision_detail_level': 'low', 'api_max_tokens': 300,
                'overlay_height_ratio': 0.9 # Adicionado para altura flexível
            }
            try:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, 'r') as f:
                        loaded_cfg = json.load(f)
                    for key, value in default_cfg.items():
                        if key not in loaded_cfg:
                            loaded_cfg[key] = value
                    if not (isinstance(loaded_cfg.get('margin'), list) and len(loaded_cfg['margin']) == 4 and all(isinstance(x, (int, float)) for x in loaded_cfg['margin'])):
                        loaded_cfg['margin'] = default_cfg['margin']
                    return loaded_cfg # Retorna dentro do lock
                else:
                    # Salvar default se não existir
                    with open(CONFIG_FILE, 'w') as f:
                         json.dump(default_cfg, f, indent=4)
                    return default_cfg # Retorna dentro do lock
            except Exception as e:
                print(f"Erro ao carregar/criar {CONFIG_FILE}: {e}. Usando defaults.\n{traceback.format_exc()}")
                return default_cfg # Retorna dentro do lock

    def save_config(self, config_to_save=None): # config_to_save é opcional
        try:
            with self._config_lock: # Garante que estamos salvando a versão mais consistente de self.config
                cfg_data = config_to_save if config_to_save else self.config
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(cfg_data, f, indent=4)
            # print("Configurações salvas.")
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}\n{traceback.format_exc()}")
    
    # check_and_apply_config_changes_to_overlay removido, Flask atualiza via sinal agora.
    # Se edição manual do JSON for um caso de uso importante, o watcher pode ser reavaliado.

    @QtCore.pyqtSlot(bool) # Slot para definir o flag de processamento
    def _set_processing_flag_slot(self, state: bool):
        self.is_currently_processing_chatgpt = state

    @QtCore.pyqtSlot(str, int) # Slot para o sinal signal_set_temporary_message
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
        else:
            self.display_last_chat_message_or_default()

    def take_screenshot_bytes_for_api(self):
        try:
            with mss.mss() as sct:
                # Acessar config com lock porque esta função pode ser chamada de thread
                with self._config_lock:
                    margin_list = list(self.config.get('margin', [0,0,0,0])) # Faz cópia
                    monitor_idx = self.config.get('capture_monitor_idx', 1) # 1 para primário por default do mss, 0 para todos os monitores

                # Se len(sct.monitors) == 1, é o dict 'all'. Se > 1, o índice 0 é 'all', 1 é o primário etc.
                target_monitor_mss_idx = monitor_idx if len(sct.monitors) > 1 else 0
                if target_monitor_mss_idx >= len(sct.monitors):
                    print(f"Índice de monitor {target_monitor_mss_idx} inválido. Usando monitor primário/padrão.")
                    target_monitor_mss_idx = 1 if len(sct.monitors) > 1 else 0

                base_monitor_details = sct.monitors[target_monitor_mss_idx]
                capture_details = dict(base_monitor_details) # Começa com o monitor inteiro

                if isinstance(margin_list, list) and len(margin_list) == 4 and margin_list != [0,0,0,0]:
                    x1, y1, x2, y2 = margin_list
                    width = x2 - x1
                    height = y2 - y1
                    if width > 0 and height > 0:
                        custom_left = base_monitor_details["left"] + x1
                        custom_top = base_monitor_details["top"] + y1
                        # Verifica se a região customizada está DENTRO do monitor base
                        if (custom_left >= base_monitor_details["left"] and
                            custom_top >= base_monitor_details["top"] and
                            custom_left + width <= base_monitor_details["left"] + base_monitor_details["width"] and
                            custom_top + height <= base_monitor_details["top"] + base_monitor_details["height"]):
                            capture_details = {"top": custom_top, "left": custom_left, "width": width, "height": height, "mon": target_monitor_mss_idx}
                        else:
                            self.signal_set_temporary_message.emit("<p style='color:orange;'>Margens excedem limites do monitor. Capturando tela cheia do monitor selecionado.</p>", 3000)
                    else:
                        self.signal_set_temporary_message.emit("<p style='color:orange;'>Margens inválidas (largura/altura <= 0). Capturando tela cheia.</p>", 3000)
                
                sct_img_obj = sct.grab(capture_details)
                return mss.tools.to_png(sct_img_obj.rgb, sct_img_obj.size)
        except Exception as e:
            print(f"Erro MSS na captura: {e}\n{traceback.format_exc()}")
            error_msg = f"<p style='color:red;'>Erro ao capturar tela (MSS): {html.escape(str(e))[:100]}</p>"
            self.signal_set_temporary_message.emit(error_msg, 4000)
            return None

    def _threaded_call_to_openai_vision_api(self, image_bytes_data, is_new_chat_bool):
        if self.is_currently_processing_chatgpt: # Checagem rápida, mas o flag principal é via slot
            return 

        self.signal_toggle_processing_flag.emit(True)
        self.signal_update_overlay_content.emit("<p>Analisando imagem com GPT...</p>")
        base64_image_str = base64.b64encode(image_bytes_data).decode('utf-8')

        if is_new_chat_bool or not self.history:
            self.history = [{"role": "system", "content": "Você é um assistente visual conciso. Descreva a imagem de forma clara e útil. Max 150 palavras."}]
        
        with self._config_lock: # Acessando config em thread
            max_hist_pairs = self.config.get('max_chat_history_pairs', 10)
            model_name = self.config.get('model', 'gpt-4o')
            detail_level = self.config.get('vision_detail_level', 'low')
            max_tokens_api = self.config.get('api_max_tokens', 300)

        if len(self.history) > (max_hist_pairs * 2 + 1):
            self.history = [self.history[0]] + self.history[-(max_hist_pairs * 2):]

        user_message_content = [
            {"type": "text", "text": "Descreva esta imagem."},
            {"type": "image_url", "image_url": {
                "url": f"data:image/png;base64,{base64_image_str}",
                "detail": detail_level
            }}
        ]
        current_payload = self.history + [{"role": "user", "content": user_message_content}]
        
        try:
            api_response = self.openai_client.chat.completions.create(
                model=model_name,
                messages=current_payload,
                max_tokens=max_tokens_api
            )
            assistant_reply_str = api_response.choices[0].message.content
            self.history.append({"role": "user", "content": user_message_content}) # Manter conteúdo completo aqui
            self.history.append({"role": "assistant", "content": assistant_reply_str})
            
            formatted_html_reply = self._format_gpt_response_for_html_display(assistant_reply_str)
            self.signal_update_overlay_content.emit(formatted_html_reply)
        except Exception as e:
            print(f"Erro API OpenAI: {e}\n{traceback.format_exc()}")
            err_msg_html = f"<p style='color:red;'>Erro API OpenAI: {html.escape(str(e))[:150]}</p>"
            self.signal_update_overlay_content.emit(err_msg_html)
        finally:
            self.signal_toggle_processing_flag.emit(False)

    def _format_gpt_response_for_html_display(self, raw_text_str):
        escaped_html_text = html.escape(raw_text_str)
        return f"<div style='padding: 2px;'>{escaped_html_text.replace(chr(10), '<br/>')}</div>"


    def _initiate_chatgpt_request(self, is_new_chat_bool):
        if self.menu_is_active or self.is_currently_processing_chatgpt or not AppController._chat_hotkeys_globally_enabled:
            return
        
        image_bytes = self.take_screenshot_bytes_for_api() # Erros internos já emitem sinais
        if image_bytes:
            # O daemon=True é importante para a thread não impedir o app de fechar
            threading.Thread(target=self._threaded_call_to_openai_vision_api, args=(image_bytes, is_new_chat_bool), daemon=True).start()

    def on_hotkey_esc_1(self): 
        try: self._initiate_chatgpt_request(True)
        except Exception as e: print(f"Erro em on_hotkey_esc_1: {e}\n{traceback.format_exc()}")
            
    def on_hotkey_esc_2(self): 
        try: self._initiate_chatgpt_request(False)
        except Exception as e: print(f"Erro em on_hotkey_esc_2: {e}\n{traceback.format_exc()}")

    def on_hotkey_esc_3_menu_toggle(self):
        try:
            if self.is_currently_processing_chatgpt:
                self.signal_set_temporary_message.emit("<p>Aguarde a resposta do GPT...</p>", 2000)
                return

            self.menu_is_active = not self.menu_is_active
            AppController._chat_hotkeys_globally_enabled = not self.menu_is_active

            if self.menu_is_active:
                self.temporary_state_clear_timer.stop() 
                self.current_menu_selection_idx = 0
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
            else: 
                self.display_last_chat_message_or_default()
        except Exception as e: print(f"Erro em on_hotkey_esc_3_menu_toggle: {e}\n{traceback.format_exc()}")

    def on_hotkey_esc_0_exit_menu_or_clear(self):
        try:
            if self.menu_is_active:
                self.menu_is_active = False
                AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
            elif not self.is_currently_processing_chatgpt: 
                self.signal_update_overlay_content.emit("") 
        except Exception as e: print(f"Erro em on_hotkey_esc_0_exit_menu_or_clear: {e}\n{traceback.format_exc()}")


    def display_last_chat_message_or_default(self):
        if self._temporary_message_active: return

        if self.is_currently_processing_chatgpt:
             self.signal_update_overlay_content.emit("<p>Analisando imagem com GPT...</p>")
             return

        last_gpt_msg_str = ""
        for msg in reversed(self.history):
            if msg["role"] == "assistant":
                last_gpt_msg_str = msg["content"]
                break
        
        if last_gpt_msg_str:
            self.signal_update_overlay_content.emit(self._format_gpt_response_for_html_display(last_gpt_msg_str))
        else:
            self.signal_update_overlay_content.emit("<p>Pressione <code style='color:#90CAF9; background:rgba(0,0,0,0.3); padding:1px 3px; border-radius:2px;'>ESC+1</code>.</p>")

    def on_hotkey_esc_9_web_config(self):
        try:
            if self.menu_is_active:
                self.on_hotkey_esc_3_menu_toggle() 

            flask_port = self.get_config_value('port', 43000)
            flask_url = f"http://127.0.0.1:{flask_port}" # Usar 127.0.0.1 é mais seguro que 0.0.0.0 para link
            
            if not self.flask_server_thread_obj or not self.flask_server_thread_obj.is_alive():
                self.flask_server_thread_obj = start_web_server(self)
                msg_html = (f"<p>Servidor de config. iniciado!<br/>"
                            f"Acesse: <a href='{flask_url}' style='color:#81D4FA;'>{flask_url}</a><br/>"
                            f"<small>(Retornando em 15s ou ESC+0)</small></p>")
            else:
                msg_html = (f"<p>Servidor de config. já rodando!<br/>"
                            f"Acesse: <a href='{flask_url}' style='color:#81D4FA;'>{flask_url}</a><br/>"
                            f"<small>(Retornando em 15s ou ESC+0)</small></p>")
            
            self.signal_set_temporary_message.emit(msg_html, 15000)
        except Exception as e: print(f"Erro em on_hotkey_esc_9_web_config: {e}\n{traceback.format_exc()}")

    def on_menu_navigation_input(self, direction_str_up_down):
        try:
            if self.menu_is_active:
                self.temporary_state_clear_timer.stop()

                if direction_str_up_down == "up":
                    self.current_menu_selection_idx = (self.current_menu_selection_idx - 1 + len(self.menu_options_list)) % len(self.menu_options_list)
                else: 
                    self.current_menu_selection_idx = (self.current_menu_selection_idx + 1) % len(self.menu_options_list)
                self.signal_update_menu_display.emit(self.menu_options_list, self.current_menu_selection_idx)
        except Exception as e: print(f"Erro em on_menu_navigation_input:{e}\n{traceback.format_exc()}")

    def _prompt_for_margins(self): # Não é mais um "prompt" no overlay, apenas instrução.
        msg = ("<p>Para ajustar margens, use a interface web:<br/>"
               "ESC+9 → acesse o link.<br/>"
               "<small>(Voltando ao menu em 7s...)</small></p>")
        self.signal_set_temporary_message.emit(msg, 7000)
        # O retorno ao menu é gerenciado por clear_temporary_message_and_restore_chat_view


    def on_menu_option_selected_enter(self):
        try:
            if not self.menu_is_active: return
            self.temporary_state_clear_timer.stop() 

            selected_opt_str = self.menu_options_list[self.current_menu_selection_idx]
            feedback_msg_html = ""
            config_changed = False # Flag para salvar config no final
            
            # Copia local da config para modificar e depois aplicar via sinal se houver mudança
            # Leitura segura da config
            with self._config_lock:
                current_config_copy = dict(self.config)

            if selected_opt_str == "Alternar Opacidade":
                opac_cycle = [0.3, 0.5, 0.7, 0.9, 1.0] 
                current_opac = current_config_copy['opacity']
                try: idx = opac_cycle.index(current_opac)
                except ValueError: idx = opac_cycle.index(min(opac_cycle, key=lambda x:abs(x-current_opac))) # Pega o mais próximo
                next_opac = opac_cycle[(idx + 1) % len(opac_cycle)]
                current_config_copy['opacity'] = next_opac
                feedback_msg_html = f"Opacidade: {next_opac*100:.0f}%"
                config_changed = True

            elif selected_opt_str == "Alternar Posição":
                pos_cycle = ['top-right', 'top-left', 'bottom-right', 'bottom-left']
                current_pos = current_config_copy['position']
                try: idx = pos_cycle.index(current_pos)
                except ValueError: idx = -1
                next_pos = pos_cycle[(idx + 1) % len(pos_cycle)]
                current_config_copy['position'] = next_pos
                feedback_msg_html = f"Posição: {next_pos.replace('-', ' ').title()}"
                config_changed = True

            elif selected_opt_str == "Alternar Modelo GPT":
                # Ex: "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo" (confirme nomes válidos)
                model_cycle = ["gpt-4o", "gpt-4-turbo-preview", "gpt-3.5-turbo-0125"]
                current_model = current_config_copy['model']
                try: idx = model_cycle.index(current_model)
                except ValueError: idx = -1
                next_model = model_cycle[(idx + 1) % len(model_cycle)]
                current_config_copy['model'] = next_model
                feedback_msg_html = f"Modelo GPT: {next_model}"
                config_changed = True
            
            elif selected_opt_str == "Margens da Captura":
                self._prompt_for_margins()
                return 

            elif selected_opt_str == "Configurações Web":
                self.on_hotkey_esc_9_web_config() 
                return

            elif selected_opt_str == "Sair":
                self.save_config() # Salva config atual
                QtWidgets.QApplication.quit()
                return

            # Se a config mudou, atualize a principal e emita sinal
            if config_changed:
                with self._config_lock:
                    self.config.update(current_config_copy)
                self.save_config() # Salva no disco
                self.signal_apply_config_to_overlay.emit(dict(current_config_copy)) # Emite cópia para overlay


            if feedback_msg_html:
                self.signal_set_temporary_message.emit(f"<p>{feedback_msg_html}</p>", 2000)
                # O menu será reexibido pelo callback de temporary_state_clear_timer
            else: # Se não houve feedback, e não era uma ação que mantem o menu, fecha
                self.menu_is_active = False
                AppController._chat_hotkeys_globally_enabled = True
                self.display_last_chat_message_or_default()
        except Exception as e: 
            print(f"Erro em on_menu_option_selected_enter: {e}\n{traceback.format_exc()}")
            self.signal_set_temporary_message.emit("<p style='color:red'>Erro ao processar opção.</p>", 3000)

# --- Main Application Setup & Execution ---
def main():
    try: # Bloco try-except geral para capturar erros na inicialização
        if sys.platform == "win32":
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
            QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create('Fusion'))

        app = QtWidgets.QApplication(sys.argv)
        
        # Carregar config padrão para o Overlay inicialmente. AppController irá carregar do JSON e atualizar.
        overlay_initial_config = {
            'opacity':0.8, 'position':'top-right', 
            'overlay_width':420, 'overlay_v_offset':25, 
            'overlay_h_offset':25, 'overlay_height_ratio': 0.9
        }
        overlay_widget_instance = Overlay(overlay_initial_config)
        
        app_controller_instance = AppController(overlay_widget_instance)

        hotkeys_config = [
            ('esc+1', app_controller_instance.on_hotkey_esc_1),
            ('esc+2', app_controller_instance.on_hotkey_esc_2),
            ('esc+3', app_controller_instance.on_hotkey_esc_3_menu_toggle),
            ('esc+0', app_controller_instance.on_hotkey_esc_0_exit_menu_or_clear),
            ('esc+9', app_controller_instance.on_hotkey_esc_9_web_config),
            ('esc+up', lambda: app_controller_instance.on_menu_navigation_input("up")),
            ('esc+down', lambda: app_controller_instance.on_menu_navigation_input("down")),
            ('esc+enter', app_controller_instance.on_menu_option_selected_enter),
            # Saída de emergência não deve usar 'esc' como modificador primário, use algo menos comum
            ('ctrl+alt+shift+end', lambda: (app_controller_instance.save_config(), QtWidgets.QApplication.quit())) 
        ]
        
        # Registro das hotkeys: suppress=False é geralmente mais seguro para 'esc'
        # pois permite que o 'esc' funcione em outros apps se não for parte de uma hotkey completa.
        for key_combo, callback_func in hotkeys_config:
            try:
                # O timeout para hotkeys multi-passo (como 'esc+1') pode ser um fator.
                # A lib `keyboard` tem um timeout padrão (geralmente 1s).
                keyboard.add_hotkey(key_combo, callback_func, suppress=False, timeout=0.5, trigger_on_release=False)
            except Exception as e_hk:
                print(f"Erro ao registrar hotkey {key_combo}: {e_hk}")

        app.aboutToQuit.connect(app_controller_instance.save_config) 

        exit_status_code = app.exec_()

    except Exception as e_main:
        print(f"Erro fatal na aplicação: {e_main}\n{traceback.format_exc()}")
        # Tentar limpar hotkeys mesmo em caso de erro
        try:
            keyboard.unhook_all()
        except Exception as e_unhook:
            print(f"Erro ao desregistrar hotkeys na saída com falha: {e_unhook}")
        sys.exit(1) # Sai com código de erro

    finally: # Garante que as hotkeys sejam desregistradas
        try:
            print("Desregistrando hotkeys...")
            keyboard.unhook_all()
            print("Hotkeys desregistradas.")
        except Exception as e_unhook_final:
            print(f"Erro ao desregistrar hotkeys na saída normal: {e_unhook_final}")

    sys.exit(exit_status_code)

if __name__ == "__main__":
    # Removido o aviso de admin, pois WDA_EXCLUDEFROMCAPTURE geralmente não requer.
    # Se WDA_MONITOR for o único que funciona, e precisar que funcione em apps elevados, aí sim.
    print("Iniciando OverlayGPT...")
    main()
