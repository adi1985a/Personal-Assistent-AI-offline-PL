# Personal Assistant AI Offline (PL)

![Personal Assistant](https://via.placeholder.com/800x200.png?text=Personal+Assistant+AI+Offline)  
*Polskojęzyczny asystent AI działający lokalnie bez połączenia z Internetem.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

## Spis treści
- [Opis](#opis)
- [Funkcje](#funkcje)
- [Wymagania](#wymagania)
- [Instalacja](#instalacja)
- [Uruchomienie](#uruchomienie)
- [Struktura projektu](#struktura-projektu)
- [Licencja](#licencja)
- [Autor](#autor)

## Opis

Projekt jest osobistym asystentem AI działającym offline i wspierającym język polski. Umożliwia interakcję głosową i tekstową, zarządzanie notatkami, plan dnia oraz wizualizacje danych — wszystko bez konieczności łączenia się z Internetem, co zapewnia pełną prywatność użytkownika.

## Funkcje

- 💬 Obsługa języka polskiego
- 🧠 Model AI działający lokalnie (np. GPT-2 lub Bielik)
- 🎙️ Rozpoznawanie mowy (Vosk)
- 🗣️ Synteza mowy (pyttsx3)
- 📝 Zarządzanie notatkami lokalnymi (SQLite)
- 📊 Prezentacja danych na wykresach (Matplotlib)
- 🔐 Szyfrowanie notatek (Cryptography)
- 🕓 Automatyczne uruchamianie z systemem (opcjonalnie)
- 📆 Plan dnia i przypomnienia

## Wymagania

- **Python 3.10 lub nowszy**
- Zainstalowane biblioteki:
  - `vosk`
  - `pyttsx3`
  - `sqlite3` (wbudowane)
  - `matplotlib`
  - `cryptography`
  - `tkinter` (GUI)
  - `transformers` / `ollama` / `gpt2` (w zależności od modelu)

Pełną listę zależności znajdziesz w pliku `requirements.txt`.

## Instalacja

1. Sklonuj repozytorium:
   ```bash
   git clone https://github.com/yourusername/personal-assistant-ai-offline.git
   ```

2. Przejdź do katalogu projektu:
   ```bash
   cd "f:\My Portafolio IT ulepszona\AI\Personal assistent AI offline PL"
   ```

3. Zainstaluj wymagane biblioteki:
   ```bash
   pip install -r requirements.txt
   ```

## Uruchomienie

Uruchom program za pomocą komendy:
```bash
python main.py
```

## Struktura projektu

- `main.py` – Główna aplikacja (GUI, logika, sterowanie)
- `asystent/` – Moduły asystenta: AI, mowa, baza danych, interfejs
- `db/` – Pliki SQLite z lokalnymi notatkami
- `resources/` – Ikony, obrazy, modele głosowe
- `requirements.txt` – Lista zależności
- `README.markdown` – Opis projektu
- `LICENSE` – Licencja MIT

## Licencja

Projekt dostępny na licencji **MIT**. Szczegóły znajdziesz w pliku `LICENSE`.

## Autor

**Adrian Leśniak**  
*Inżynieria oprogramowania – specjalność: technologie programowania*  
📧 [Twoje dane kontaktowe, jeśli chcesz]

---

> ✅ Jeśli projekt Ci się podoba, zostaw ⭐ na GitHubie!
