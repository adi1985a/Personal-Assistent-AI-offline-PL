# Personal Assistant AI Offline (EN)

![Personal Assistant](https://via.placeholder.com/800x200.png?text=Personal+Assistant+AI+Offline)  
*Polish-language AI assistant running entirely offline, focused on privacy and daily productivity.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

## Table of Contents
- [Description](#description)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [License](#license)
- [Author](#author)

## Description

**Personal Assistant AI Offline** is a desktop application designed to assist users in Polish through voice or text commands. It works entirely offline, ensuring user privacy, and includes a local database, smart scheduling, encrypted note storage, and visual data representation.

## Features

- 💬 Polish language support
- 🧠 Local AI model (e.g., GPT-2 or Bielik via Ollama)
- 🎙️ Speech recognition (Vosk)
- 🗣️ Speech synthesis (pyttsx3)
- 📝 Note management using SQLite
- 📊 Data visualization with charts (Matplotlib)
- 🔐 Encrypted note storage (Cryptography)
- 🕓 Optional system startup integration
- 📆 Daily schedule with reminders

## Requirements

- **Python 3.10 or newer**
- Required libraries:
  - `vosk`
  - `pyttsx3`
  - `sqlite3` (built-in)
  - `matplotlib`
  - `cryptography`
  - `tkinter` (GUI)
  - `transformers`, `ollama`, or `gpt2` (depending on your AI model)

All dependencies are listed in `requirements.txt`.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/personal-assistant-ai-offline.git
   ```

2. Navigate to the project folder:
   ```bash
   cd "f:\My Portafolio IT ulepszona\AI\Personal assistent AI offline PL"
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

To start the assistant, run:
```bash
python main.py
```

## Project Structure

- `main.py` – Main application with UI and logic
- `asystent/` – Modules: AI core, speech, database, interface
- `db/` – SQLite database for local notes
- `resources/` – Images, icons, speech models
- `requirements.txt` – List of required Python packages
- `README.markdown` – Project documentation
- `LICENSE` – MIT license file

## License

This project is licensed under the **MIT License**. See the `LICENSE` file for more information.

## Author

**Adrian Leśniak**  
*Software Engineering – Programming Technologies Specialization*  
📧 [Your contact info, if applicable]

---

> ✅ If you find this project useful, feel free to give it a ⭐ on GitHub!
