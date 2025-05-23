# Peach 🍑

**Peach** is an open-source Windows-only script inspired by *Perssua* (by Lucas Montano) and *F\*ck Leetcode* (by Roy). It automates and speeds up problem-solving tasks, boosting your productivity — and sometimes making you a “sneaky hacker” (use responsibly 😉).

---

## 🚀 Use Cases

* **LeetCode Solver**: Generate quick solutions for classic coding challenges.
* **Productivity Booster**: Save time on repetitive programming tasks.
* **Knowledge Tester**: Assess and challenge your skills (beware of feeling like an impostor 😂).

---

## 📋 Prerequisites

* **Operating System**: Windows 10 or higher
* **Python**: Version 3.8 or above (ensure `pythonw` is in your PATH)
* **OpenAI API Key**: Set `OPENAI_API_KEY` in a `.env` file

---

## ⚙️ Installation

1. Clone this repository and navigate into it:

   ```bash
   git clone https://github.com/tesla-sec/peach-at-leetcode-not-strawberry peach
   cd peach
   ```
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```
3. Copy and configure the environment file:

   ```bash
   cp .env.example .env
   ```

   Open `.env` and set:

   ```dotenv
   OPENAI_API_KEY=your_api_key_here
   ```

---

## ▶️ Running the Script
### 1. From an Elevated Command Prompt
```bash
Execute the init.bat
```
### 2. From an Elevated Command Prompt

```bash
python main.py
```

### 3. Creating a Standalone Executable

If you prefer an independent `.exe`:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py
```

The executable will be available in the `dist/` folder.

---

## 📓 How to Use?

Once the script is running, an overlay will appear on your screen. You can interact with it using the following hotkeys:

**Core Functions:**

* **`ESC+1`**: **Capture & Analyze Image (New Chat)**
    * Takes a screenshot of your primary monitor (or a defined region).
    * Sends the image to the AI for analysis, starting a new chat session.
    * The AI's description or analysis will appear in the overlay.
* **`ESC+2`**: **Capture & Analyze Image (Continue Chat)**
    * Similar to `ESC+1`, but adds the new image analysis to the current chat session.
* **`ESC+4`**: **Record Microphone + Capture Screen & Analyze**
    * Press once to start recording audio from your microphone. The overlay will indicate it's recording.
    * Press `ESC+4` again to stop recording.
    * Upon stopping, a screenshot is taken.
    * The recorded audio is transcribed, and both the transcript and the screenshot are sent to the AI for a multimodal response.
* **`ESC+5`**: **Record System Audio + Capture Screen & Analyze**
    * Press once to start recording your system's audio output (e.g., a video playing, game sounds). The overlay will indicate it's recording.
        * **Note**: This requires "Stereo Mix" or a similar loopback audio device to be enabled in your Windows sound settings.
    * Press `ESC+5` again to stop recording.
    * Upon stopping, a screenshot is taken.
    * The recorded system audio is transcribed, and both the transcript and the screenshot are sent to the AI for a multimodal response.
* **`ESC+6`**: **Toggle Text Chat Mode**
    * Press to enter or exit a text-based chat mode directly within the overlay.
    * When active, your chat history will be displayed.
    * Other hotkeys for image/audio capture are disabled while in this mode.
* **`ESC+=`**: **Toggle Text Input Focus (in Text Chat Mode)**
    * When in Text Chat Mode (`ESC+6`), press `ESC+=` to switch keyboard input focus.
    * **Focus on Overlay**: Your typing will appear in the overlay's input prompt. Press `Enter` to send your message to the AI.
    * **Focus on Other Windows**: Your typing will go to the currently active application on your system, not the overlay.
    * The overlay will indicate where the text input is currently directed.

**Overlay & Menu Management:**

* **`ESC+3`**: **Toggle Overlay Menu**
    * Opens or closes a menu within the overlay for quick settings adjustments.
* **`ESC+0`**: **Close Menu / Clear Overlay / Clear Text Input**
    * If the menu is open, this closes it.
    * If in Text Chat Mode, this clears the current text you're typing.
    * If no menu or special mode is active, this clears the overlay content and chat history.
* **`ESC+UP` / `ESC+DOWN`**: **Navigate Menu**
    * Use these to navigate through options when the overlay menu is open.
* **`ESC+ENTER`**: **Select Menu Option**
    * Selects the highlighted option in the overlay menu.

**Configuration & Exit:**

* **`CTRL+9`**: **Open Web Configuration**
    * Opens a local web page in your browser for more detailed configuration of the script (e.g., margins, AI model, opacity).
* **`CTRL+ALT+ESC`**: **Exit Application**
    * Saves current settings and closes the Peach overlay application.

---

## 🛣️ Roadmap

### Coming Soon

* Separate uploads for screenshots and audio transcripts
* Prompt editing interface
* Model list management
* Support for additional backends:

  * Astral
  * Claude
  * DeepSeek
  * Gemini
  * Grok
  * Llama
  * Perplexity
  * Qwen

### Coming Later

* Cross-platform support (Linux/macOS)
* Stable release
* Performance and memory optimizations
* (Possibly) Port to Go

---

## 🤝 Contributing

Contributions are very welcome!

1. Open an issue to discuss features or report bugs.
2. Submit a pull request with clean code, tests, and documentation.

---
## No Donate for Now :)

 yep, i make this and the code with AI.

---
## 📄 License

This project is licensed under the **Apache 2.0 License**. See [LICENSE](LICENSE) for details.
