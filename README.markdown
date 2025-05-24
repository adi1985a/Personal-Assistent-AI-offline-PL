# 🤖 Personal Assistant AI Offline (EN)  
A Polish-language AI assistant running entirely offline, focused on privacy and daily productivity.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)  
[![Python](https://img.shields.io/badge/Language-Python-blue.svg)](https://www.python.org/)  
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

---

## 📑 Table of Contents
- [Description](#description)  
- [Features](#features)  
- [Requirements](#requirements)  
- [Installation](#installation)  
- [Usage](#usage)  
- [Project Structure](#project-structure)  
- [License](#license)  
- [Author](#author)  

---

## 📝 Description  
Personal Assistant AI Offline is a desktop application designed to assist users in Polish through voice or text commands. It works fully offline to ensure user privacy, featuring a local database, smart scheduling, encrypted note storage, and rich visual data representation.

---

## ✨ Features  
- 💬 Polish language support  
- 🧠 Local AI model (e.g., GPT-2 or Bielik via Ollama)  
- 🎙️ Speech recognition using Vosk  
- 🗣️ Speech synthesis with pyttsx3  
- 📝 Note management using SQLite  
- 📊 Data visualization via Matplotlib charts  
- 🔐 Encrypted note storage with Cryptography  
- 🕓 Optional system startup integration  
- 📆 Daily schedule with reminders  

---

## 🛠 Requirements  
- Python 3.10 or newer  
- Python libraries:  
  - vosk  
  - pyttsx3  
  - sqlite3 (built-in)  
  - matplotlib  
  - cryptography  
  - tkinter (for GUI)  
  - transformers, ollama, or gpt2 (depending on AI model)  
- All dependencies are listed in `requirements.txt`.

---

## ⚙️ Installation  
```bash
git clone https://github.com/yourusername/personal-assistant-ai-offline.git
cd "f:\My Portafolio IT ulepszona\AI\Personal assistent AI offline PL"
pip install -r requirements.txt
```
---

## ▶️ Usage
Run the assistant by executing:

```bash
python main.py
```
---

## 📁 Project Structure

```
personal-assistant-ai-offline/
│
├── main.py                  # Main app with UI and logic  
├── asystent/                # Modules: AI core, speech, database, interface  
├── db/                      # SQLite database for local notes  
├── resources/               # Images, icons, speech models  
├── requirements.txt         # Python dependencies  
├── README.markdown          # Project documentation  
└── LICENSE                  # MIT license file  
```

## 📄 License  
This project is open-source and released under the [MIT License](https://opensource.org/licenses/MIT).  
See the LICENSE file for full details.

---

## 👨‍💻 Author  
**Adrian Leśniak**  
Software Developer


