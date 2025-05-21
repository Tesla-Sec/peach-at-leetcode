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

## 🛣️ Roadmap

### Coming Soon

* Output audio recording
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

This project is licensed under the **APACHE License**. See [LICENSE](LICENSE) for details.
