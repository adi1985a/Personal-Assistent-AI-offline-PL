import tkinter as tk
import sqlite3
import json
import ollama
from vosk import Model as VoskModel, KaldiRecognizer
import pyaudio
import pyttsx3
from PIL import Image, ImageTk
from tkcalendar import Calendar
import unicodedata
import datetime
import os
import random
from tkinter import ttk
from tkinter import filedialog
import base64
import hashlib
from cryptography.fernet import Fernet
import sys
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import winreg  # Add to existing imports
import signal  # Add to existing imports at top

# Define ChartsManager class first, before it's used
class ChartsManager:
    """Klasa zarządzająca wykresami"""
    def __init__(self, cursor):
        self.cursor = cursor
        
    def create_category_chart(self):
        """Tworzy wykres kołowy pokazujący rozkład notatek w kategoriach"""
        try:
            self.cursor.execute("""
                SELECT c.name, COUNT(n.id) 
                FROM categories c 
                LEFT JOIN notes n ON c.id = n.category_id 
                GROUP BY c.id, c.name
                HAVING COUNT(n.id) > 0
                ORDER BY COUNT(n.id) DESC
            """)
            data = self.cursor.fetchall()
            
            if not data:
                return None
                
            labels = [f"{row[0]} ({row[1]})" for row in data]
            sizes = [row[1] for row in data]
            
            fig, ax = plt.subplots(figsize=(10, 6))
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%',
                                            textprops={'fontsize': 9})
            ax.set_title('Rozkład notatek w kategoriach', pad=20)
            
            ax.legend(wedges, labels,
                     title="Kategorie",
                     loc="center left",
                     bbox_to_anchor=(1, 0, 0.5, 1))
            
            plt.tight_layout()
            return fig
        except Exception as e:
            print(f"Błąd podczas tworzenia wykresu kategorii: {e}")
            return None

    def create_notes_timeline(self):
        """Tworzy wykres liniowy pokazujący liczbę notatek w czasie"""
        try:
            self.cursor.execute("""
                SELECT DATE(creation_date) as date, COUNT(*) as count
                FROM notes
                GROUP BY DATE(creation_date)
                ORDER BY date
            """)
            data = self.cursor.fetchall()
            
            if not data:
                return None
                
            dates = [row[0] for row in data]
            counts = [row[1] for row in data]
            
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(dates, counts, marker='o', linestyle='-', linewidth=2, markersize=8)
            ax.set_title('Liczba notatek w czasie')
            ax.set_xlabel('Data')
            ax.set_ylabel('Liczba notatek')
            plt.xticks(rotation=45, ha='right')
            
            for x, y in zip(dates, counts):
                ax.annotate(str(y), (x, y), textcoords="offset points", 
                           xytext=(0,10), ha='center')
            
            ax.grid(True, linestyle='--', alpha=0.7)
            plt.tight_layout()
            return fig
        except Exception as e:
            print(f"Błąd podczas tworzenia wykresu czasowego: {e}")
            return None
            
    def create_notes_by_month_chart(self):
        """Tworzy wykres słupkowy pokazujący liczbę notatek w miesiącach"""
        try:
            self.cursor.execute("""
                SELECT strftime('%Y-%m', creation_date) as month, COUNT(*) as count
                FROM notes
                GROUP BY strftime('%Y-%m', creation_date)
                ORDER BY month
            """)
            data = self.cursor.fetchall()
            
            if not data:
                return None
                
            months = [row[0] for row in data]
            counts = [row[1] for row in data]
            
            fig, ax = plt.subplots(figsize=(10, 6))
            bars = ax.bar(months, counts, color='skyblue')
            
            ax.set_title('Liczba notatek w miesiącach')
            ax.set_xlabel('Miesiąc')
            ax.set_ylabel('Liczba notatek')
            plt.xticks(rotation=45, ha='right')
            
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom')
            
            plt.tight_layout()
            return fig
        except Exception as e:
            print(f"Błąd podczas tworzenia wykresu miesięcznego: {e}")
            return None

# Globalne zmienne
last_response = ""
# Używamy słownika do pamięci kontekstowej – klucze: "imie", "wiek", "ostatni_prompt"
context_memory = {}
auto_read = False  # domyślnie wyłączone auto czytanie
generating_response = False  # zmienna kontrolująca stan generowania odpowiedzi
voice_listening = False
voice_thread = None
should_stop_listening = False

# Dodaj do globalnych zmiennych na początku pliku:
history_memory = {
    'last_action': None,
    'last_category': None,
    'last_note': None
}

# Inicjalizacja klienta AI
client = ollama.Client()

# --- Inicjalizacja bazy danych SQLite ---
conn = sqlite3.connect('notes.db')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER,
        content TEXT NOT NULL,
        creation_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        scheduled_date DATETIME,
        priority INTEGER DEFAULT 3,
        FOREIGN KEY (category_id) REFERENCES categories (id)
    )
''')
conn.commit()

# Remove the ALTER TABLE statements as they're not needed anymore

# Update the database handling functions:
def migrate_database():
    """Migruje bazę danych do nowej wersji jeśli potrzeba"""
    try:
        pass
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        # Sprawdź czy kolumny istnieją
        cursor.execute("PRAGMA table_info(notes)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'scheduled_date' not in columns or 'priority' not in columns:
            # Backup starych danych
            cursor.execute("SELECT * FROM notes")
            old_notes = cursor.fetchall()
            
            # Utwórz tymczasową tabelę
            cursor.execute("""
                CREATE TABLE notes_temp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category_id INTEGER,
                    content TEXT NOT NULL,
                    creation_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    scheduled_date DATETIME,
                    priority INTEGER DEFAULT 3,
                    FOREIGN KEY (category_id) REFERENCES categories (id)
                )
            """)
            
            # Przenieś dane
            for note in old_notes:
                cursor.execute("""
                    INSERT INTO notes_temp (category_id, content, creation_date)
                    VALUES (?, ?, ?)
                """, (note[1], note[2], note[3]))
                
            # Usuń starą tabelę
            cursor.execute("DROP TABLE notes")
            
            # Zmień nazwę nowej tabeli
            cursor.execute("ALTER TABLE notes_temp RENAME TO notes")
            
            conn.commit()
            print("Baza danych została zaktualizowana")
    except Exception as e:
        print(f"Błąd migracji bazy danych: {e}")

# Add call to migrate_database after database initialization
migrate_database()

# --- System Prompt dla AI ---
system_prompt = """
Jesteś pomocnym, polskojęzycznym asystentem AI o imieniu 'Eliza'. 
Odpowiadasz zwięźle i rzeczowo. Jeśli nie znasz odpowiedzi, mów: "Przepraszam, nie wiem."

WAŻNE ZASADY DOTYCZĄCE PAMIĘCI:
1. Gdy pytają "jak mam na imię" sprawdź context_memory["imie"]
   - Jeśli imię istnieje, odpowiedz: "Masz na imię [imię]"
   - Jeśli imię nie istnieje, odpowiedz: "Przepraszam, nie znam jeszcze Twojego imienia"
   
2. Gdy pytają "ile mam lat" sprawdź context_memory["wiek"]
   - Jeśli wiek istnieje, odpowiedz: "Masz [wiek] lat"
   - Jeśli wiek nie istnieje, odpowiedz: "Przepraszam, nie znam Twojego wieku"

3. Gdy przedstawiają się ("mam na imię X" lub "nazywam się X"), zapisz imię do context_memory["imie"]

4. Gdy mówią o swoim wieku ("mam X lat"), zapisz wiek do context_memory["wiek"]

5. Zawsze używaj zapisanych informacji w kontekście rozmowy

[Lista pozostałych komend pozostaje bez zmian...]
"""

# --- Funkcje operujące na bazie danych i notatkami ---
def parse_date_from_text(text):
    """Wyciąga datę i czas z tekstu notatki"""
    import re
    
    # Wzorce dla różnych formatów dat
    patterns = [
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',  # 2025-03-15 10:00
        r'(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})',  # 15-03-2025 10:00
        r'(\d{4}-\d{2}-\d{2})',                 # 2025-03-15
        r'(\d{2}-\d{2}-\d{4})'                  # 15-03-2025
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            try:
                if ':' in date_str:
                    return datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                else:
                    return datetime.datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                try:
                    if ':' in date_str:
                        return datetime.datetime.strptime(date_str, '%d-%m-%Y %H:%M')
                    else:
                        return datetime.datetime.strptime(date_str, '%d-%m-%Y')
                except ValueError:
                    pass
    return None

def add_note(category_name, content):
    """Zmodyfikowana funkcja dodawania notatki z obsługą dat"""
    if not category_name.strip() or not content.strip():
        return "Błąd: Nieprawidłowy format komendy. Użyj: !dodaj notatkę [kategoria] [treść]"
    try:
        category_name = category_name.capitalize()
        cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
            conn.commit()
            cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
            row = cursor.fetchone()
        category_id = row[0]
        cursor.execute("SELECT id FROM notes WHERE category_id = ? AND content = ?", (category_id, content))
        if cursor.fetchone() is not None:
            return "Notatka już istnieje!"
            
        # Sprawdź czy w treści jest data
        scheduled_date = parse_date_from_text(content)
        
        # Użyj datetime.now() z pełną datą
        current_time = datetime.datetime.now().replace(microsecond=0)
        
        # Zmodyfikowane zapytanie z obsługą daty planowanej
        cursor.execute("""
            INSERT INTO notes (category_id, content, creation_date, scheduled_date) 
            VALUES (?, ?, ?, ?)
        """, (category_id, content, current_time.isoformat(), 
              scheduled_date.isoformat() if scheduled_date else None))
        conn.commit()
        note_id = cursor.lastrowid  # Pobierz ID utworzonej notatki
        
        # Odśwież widoki i kalendarz
        window.after(100, lambda: [
            refresh_notes(),
            update_today_notes(),
            update_calendar_notes(),
            # Sprawdź czy wybrana data w kalendarzu to dzisiaj i odśwież widok
            update_calendar_display_if_today()
        ])
        return "Notatka dodana!"
    except Exception as e:
        return f"Błąd dodawania notatki: {e}"

def get_notes(category_name=None):
    try:
        if (category_name):
            category_name = category_name.capitalize()
            cursor.execute("""
                SELECT n.content
                FROM notes n
                JOIN categories c ON n.category_id = c.id
                WHERE LOWER(c.name) = LOWER(?)
            """, (category_name,))
            notes = cursor.fetchall()
            if not notes:
                return f"Brak notatek w kategorii '{category_name}'."
            return "\n".join([f"- {note[0]}" for note in notes])
        else:
            cursor.execute("SELECT name FROM categories ORDER BY name")
            categories = cursor.fetchall()
            if not categories:
                return "Brak notatek."
            all_notes = ""
            for cat in categories:
                cat_name = cat[0].capitalize()
                all_notes += f"\nKategoria: {cat_name}\n"
                cursor.execute("""
                    SELECT n.content
                    FROM notes n
                    JOIN categories c ON n.category_id = c.id
                    WHERE LOWER(c.name) = LOWER(?)
                """, (cat_name,))
                notes = cursor.fetchall()
                if notes:
                    for note in notes:
                        all_notes += f"- {note[0]}\n"
                else:
                    all_notes += "- Brak notatek w tej kategorii\n"
            return all_notes.strip()
    except Exception as e:
        return f"Błąd pobierania notatek: {e}"

def create_category(category_name):
    """Tworzy nową kategorię w bazie danych"""
    if not category_name.strip():
        return "Błąd: Nieprawidłowy format komendy. Użyj: stwórz kategorię [nazwa kategorii]"
    try:
        # Zachowujemy pełną nazwę kategorii, bez modyfikacji
        cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
        if cursor.fetchone() is not None:
            return f"Kategoria '{category_name}' już istnieje!"
            
        cursor.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
        conn.commit()
        window.after(100, refresh_notes)
        return f"Kategoria '{category_name}' została utworzona!"
    except Exception as e:
        return f"Błąd tworzenia kategorii: {e}"

def delete_category(category_name):
    if not category_name.strip():
        return "Błąd: Użyj: !usuń kategorię [nazwa kategorii]"
    try:
        category_name = category_name.capitalize()
        cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
        row = cursor.fetchone()
        if row is None:
            return "Kategoria nie istnieje!"
        cat_id = row[0]
        
        # Zapisz informację o usuniętej kategorii przed jej usunięciem
        history_memory['last_action'] = 'delete_category'
        history_memory['last_category'] = category_name
        
        cursor.execute("DELETE FROM notes WHERE category_id = ?", (cat_id,))
        cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        conn.commit()
        return "Kategoria usunięta!"
    except Exception as e:
        return f"Błąd usuwania kategorii: {e}"

def delete_note(category_name, content):
    if not category_name.strip() or not content.strip():
        return "Błąd: Użyj: !usuń notatkę [kategoria] [treść]"
    try:
        category_name = category_name.capitalize()
        cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
        row = cursor.fetchone()
        if row is None:
            return "Kategoria nie istnieje!"
        cat_id = row[0]
        cursor.execute("DELETE FROM notes WHERE category_id = ? AND content = ?", (cat_id, content))
        conn.commit()
        if cursor.rowcount > 0:
            window.after(100, refresh_notes)  # Automatyczne odświeżenie po usunięciu
            return "Notatka usunięta!"
        else:
            return "Notatka nie została znaleziona!"
    except Exception as e:
        return f"Błąd usuwania notatki: {e}"

def edit_note(category_name, old_content, new_content):
    if not category_name.strip() or not old_content.strip() or not new_content.strip():
        return "Błąd: Użyj: !edytuj notatkę [kategoria] [stara treść] || [nowa treść]"
    try:
        category_name = category_name.capitalize()
        cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (category_name,))
        row = cursor.fetchone()
        if row is None:
            return "Kategoria nie istnieje!"
        cat_id = row[0]
        cursor.execute("SELECT id FROM notes WHERE category_id = ? AND content = ?", (cat_id, old_content))
        note_row = cursor.fetchone()
        if note_row is None:
            return "Notatka nie została znaleziona!"
        note_id = note_row[0]
        cursor.execute("UPDATE notes SET content = ? WHERE id = ?", (new_content, note_id))
        conn.commit()
        window.after(100, refresh_notes)  # Automatyczne odświeżenie po edycji
        return "Notatka zedytowana!"
    except Exception as e:
        return f"Błąd edycji notatki: {e}"

def search_notes(keyword):
    if not keyword.strip():
        return "Błąd: Użyj: !wyszukaj notatki [słowo_kluczowe]"
    try:
        cursor.execute("""
            SELECT c.name, n.content 
            FROM notes n
            JOIN categories c ON n.category_id = c.id
            WHERE n.content LIKE ?
        """, ('%' + keyword + '%',))
        results = cursor.fetchall()
        if not results:
            return f"Nie znaleziono notatek zawierających '{keyword}'."
        output = ""
        for cat, content in results:
            output += f"Kategoria: {cat.capitalize()}\n- {content}\n"
        return output.strip()
    except Exception as e:
        return f"Błąd wyszukiwania notatek: {e}"

def generate_daily_plan(date=None):
    """Generuje plan dnia na określoną datę lub dzisiaj"""
    try:
        if date is None:
            date = datetime.datetime.now()
        
        # Konwertuj datę na format ISO
        date_str = date.strftime('%Y-%m-%d')
        
        # Pobierz wszystkie notatki na dany dzień
        cursor.execute("""
            SELECT 
                c.name,
                n.content,
                n.creation_date,
                n.scheduled_date,
                n.priority
            FROM notes n
            JOIN categories c ON n.category_id = c.id
            WHERE DATE(n.scheduled_date) = DATE(?)
               OR DATE(n.creation_date) = DATE(?)
            ORDER BY 
                n.priority ASC,
                COALESCE(n.scheduled_date, n.creation_date) ASC
        """, (date_str, date_str))
        
        notes = cursor.fetchall()
        
        if not notes:
            return f"Brak notatek na dzień {date.strftime('%d.%m.%Y')}."
            
        plan = f"Plan na dzień {date.strftime('%d.%m.%Y')}:\n\n"
        
        # Grupuj notatki według pór dnia
        morning = []    # 6-12
        afternoon = []  # 12-18
        evening = []    # 18-23
        other = []      # pozostałe
        
        for cat, content, created, scheduled, priority in notes:
            note_time = scheduled if scheduled else created
            note_str = f"[{cat.capitalize()}] - {content}"
            
            if isinstance(note_time, str):
                note_time = datetime.datetime.fromisoformat(note_time)
            
            hour = note_time.hour
            if 6 <= hour < 12:
                morning.append((note_time, note_str))
            elif 12 <= hour < 18:
                afternoon.append((note_time, note_str))
            elif 18 <= hour < 23:
                evening.append((note_time, note_str))
            else:
                other.append((note_time, note_str))
        
        # Funkcja pomocnicza do formatowania sekcji
        def format_section(title, items):
            if not items:
                return ""
            result = f"\n{title}:\n"
            for time, note in sorted(items, key=lambda x: x[0]):
                result += f"{time.strftime('%H:%M')} - {note}\n"
            return result
        
        # Dodaj sekcje do planu
        plan += format_section("Poranek (6:00 - 12:00)", morning)
        plan += format_section("Popołudnie (12:00 - 18:00)", afternoon)
        plan += format_section("Wieczór (18:00 - 23:00)", evening)
        if other:
            plan += format_section("Pozostałe", other)
            
        return plan.strip()
        
    except Exception as e:
        return f"Błąd generowania planu dnia: {e}"

def export_notes():
    try:
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        data = {}
        for cat_id, cat_name in categories:
            cursor.execute("SELECT content, creation_date FROM notes WHERE category_id = ?", (cat_id,))
            notes = cursor.fetchall()
            data[cat_name.capitalize()] = [{"content": note[0], "creation_date": note[1]} for note in notes]
        with open("notes_export.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return "Notatki wyeksportowane do notes_export.json!"
    except Exception as e:
        return f"Błąd eksportu notatek: {e}"

def import_notes():
    try:
        if not os.path.exists("notes_export.json"):
            return "Błąd: Plik notes_export.json nie istnieje!"
            
        with open("notes_export.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        for cat_name, notes in data.items():
            cat_name = cat_name.capitalize()
            cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (cat_name,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("INSERT INTO categories (name) VALUES (?)", (cat_name,))
                conn.commit()
                cursor.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?)", (cat_name,))
                row = cursor.fetchone()
            cat_id = row[0]
            
            for note in notes:
                content = note["content"]
                creation_date = note.get("creation_date")
                
                cursor.execute("SELECT id FROM notes WHERE category_id = ? AND content = ?", (cat_id, content))
                if cursor.fetchone() is None:
                    if creation_date:
                        cursor.execute(
                            "INSERT INTO notes (category_id, content, creation_date) VALUES (?, ?, ?)",
                            (cat_id, content, creation_date)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO notes (category_id, content) VALUES (?, ?)",
                            (cat_id, content)
                        )
        
        conn.commit()
        
        # Odśwież wszystkie widoki natychmiast po imporcie
        refresh_notes()  # Odświeża listę notatek
        update_today_notes()  # Odświeża dzisiejsze notatki
        update_calendar_notes()  # Odświeża widok kalendarza
        update_calendar_display_if_today()  # Sprawdza i aktualizuje widok kalendarza jeśli wybrana jest dzisiejsza data
        
        return "Notatki zaimportowane i wyświetlone!"
    except Exception as e:
        return f"Błąd importu notatek: {e}"

def show_statistics():
    try:
        cursor.execute("SELECT c.name, COUNT(n.id) FROM categories c LEFT JOIN notes n ON c.id = n.category_id GROUP BY c.id")
        stats = cursor.fetchall()
        if not stats:
            return "Brak statystyk do wyświetlenia."
        output = "Statystyki notatek:\n"
        for cat, count in stats:
            output += f"{cat.capitalize()}: {count} notatek\n"
        return output.strip()
    except Exception as e:
        return f"Błąd generowania statystyk: {e}"

def generate_response(prompt, temperature=0.7, max_tokens=500):
    global generating_response
    try:
        generating_response = True
        if not generating_response:
            return "[Przerwano generowanie odpowiedzi]"
        
        # Adjust response length based on context
        length = context_memory.get("dlugosc", "normalne")
        if length == "krotkie":
            max_tokens = 100
        elif length == "dlugie":
            max_tokens = 1000
        
        # Add style to context
        style = context_memory.get("styl", "neutralny")
        style_prompt = ""
        if style == "formalny":
            style_prompt = "Odpowiadaj formalnie i profesjonalnie."
        elif style == "luźny":
            style_prompt = "Odpowiadaj luźno i przyjaźnie."
            
        # Przygotuj kontekst dla modelu
        context_info = []
        if "imie" in context_memory:
            context_info.append(f"Użytkownik ma na imię {context_memory['imie']}")
        if "wiek" in context_memory:
            context_info.append(f"Użytkownik ma {context_memory['wiek']} lat")
            
        # Dodaj informacje o ostatniej akcji
        if history_memory['last_action']:
            if history_memory['last_action'] == 'delete_category':
                context_info.append(f"Ostatnio usunięta kategoria: {history_memory['last_category']}")
                
        # Dodaj informacje kontekstowe do promptu
        if context_info:
            context_str = "Kontekst: " + ". ".join(context_info) + "." + style_prompt
            full_prompt = f"{context_str}\n\nPytanie użytkownika: {prompt}"
        else:
            full_prompt = prompt
            
        print(f"Wysyłam prompt: {full_prompt}")  # Debug info
        
        messages = [
            {'role': 'system', 'content': system_prompt + style_prompt},
            {'role': 'user', 'content': full_prompt}
        ]
        
        response = client.chat(
            model='SpeakLeash/bielik-11b-v2.3-instruct:Q4_K_M',
            messages=messages,
            options={'temperature': temperature, 'num_predict': max_tokens}
        )
        
        generating_response = False
        return response['message']['content']
    except Exception as e:
        generating_response = False
        return f"Wystąpił błąd: {e}"

def stop_generation():
    global generating_response
    if generating_response:
        generating_response = False
        text_area.insert(tk.END, "\n[Przerwano generowanie odpowiedzi]\n", "assistant")
        text_area.see(tk.END)

def show_categories():
    try:
        cursor.execute("SELECT name FROM categories ORDER BY name")
        categories = cursor.fetchall()
        if not categories:
            return "Brak kategorii."
        return "\n".join([f"- {cat[0].capitalize()}" for cat in categories])
    except Exception as e:
        return f"Błąd pobierania kategorii: {e}"
    except Exception as e:
        print(f"An error occurred: {e}")
        pass  # Add your code here
    except Exception as e:
        print(f"An error occurred: {e}")
        pass  # Add your code here
    except Exception as e:
        print(f"An error occurred: {e}")
        pass  # Placeholder for the code that should be inside the try block
    except Exception as e:
        print(f"An error occurred: {e}")
        cursor.execute("SELECT name FROM categories ORDER BY name")
        categories = cursor.fetchall()
        if not categories:
            return "Brak kategorii."
        return "\n".join([f"- {category[0].capitalize()}" for category in categories])
    except Exception as e:
        return f"Błąd pobierania kategorii: {e}"

# --- Funkcje obsługi głosu ---
vosk_model = VoskModel("model")
def voice_input(continuous=True):
    global voice_listening, should_stop_listening, voice_thread
    
    def listen_loop():
        global should_stop_listening, shutdown_requested
        recognizer = KaldiRecognizer(vosk_model, 16000)
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, 
                       input=True, frames_per_buffer=4096)
        
        while not (should_stop_listening or shutdown_requested):
            try:
                data = stream.read(4096)
                if recognizer.AcceptWaveform(data):
                    if not shutdown_requested:  # Only process if not shutting down
                        result = json.loads(recognizer.Result())
                        recognized_text = result.get("text", "").strip()
                        if recognized_text:
                            window.after(0, lambda t=recognized_text: process_voice_command(t))
            except Exception as e:
                print(f"Błąd rozpoznawania mowy: {e}")
                
        try:
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            print(f"Błąd zamykania strumienia audio: {e}")

    def process_voice_command(text):
        if text:
            entry.delete(0, tk.END)
            entry.insert(0, text)
            on_send()

    if continuous:
        import threading
        global voice_thread
        
        if not voice_listening:
            # Rozpocznij nasłuchiwanie
            voice_listening = True
            should_stop_listening = False
            voice_button.config(text="Słuchaj: ON", bg='#2196F3', fg='white')
            voice_thread = threading.Thread(target=listen_loop)
            voice_thread.daemon = True
            voice_thread.start()
        else:
            # Zatrzymaj nasłuchiwanie
            voice_listening = False
            should_stop_listening = True
            voice_button.config(text="Słuchaj: OFF", bg='SystemButtonFace', fg='black')
            if voice_thread:
                voice_thread.join(timeout=1)

engine = pyttsx3.init()
voices = engine.getProperty('voices')
polish_voice_found = False
for voice in voices:
    try:
        langs = voice.languages
    except Exception:
        langs = []
    if any("pl" in lang.decode("utf-8").lower() for lang in langs if isinstance(lang, bytes)) or "pl" in voice.id.lower():
        engine.setProperty('voice', voice.id)
        polish_voice_found = True
        break
if not polish_voice_found:
    print("Brak polskiego głosu w dostępnych głosach. Aby go zainstalować, przejdź do ustawień systemowych i dodaj język polski.")
engine.setProperty('volume', 1.0)
def speak(text):
    engine.say(text)
    engine.runAndWait()

# --- Dodatkowy przycisk - Auto czytaj ---
def toggle_auto_read():
    global auto_read
    auto_read = not auto_read
    if auto_read:
        auto_read_button.config(text="Auto czytaj: ON")
    else:
        auto_read_button.config(text="Auto czytaj: OFF")
    # Wymuszenie poprawnego przerysowania tła po zmianie tekstu przycisku
    window.update_idletasks()
    resize_bg(type('Event', (), {'width': window.winfo_width(), 'height': window.winfo_height()})())

# --- Funkcja otwierająca kalendarz ---
def open_calendar():
    cal_win = tk.Toplevel(window)
    cal_win.title("Kalendarz")
    cal = Calendar(cal_win, selectmode='day')
    cal.pack(padx=10, pady=10)
    tk.Button(cal_win, text="Zamknij", command=cal_win.destroy).pack(pady=10)

# --- Integracja kalendarza w notes_frame ---
def update_calendar_notes(event=None):
    try:
        # Pobierz datę z kalendarza
        selected_date = cal.get_date()  # format: "02/01/25"
        dt = datetime.datetime.strptime(selected_date, "%m/%d/%y")
        if dt.year < 2000:
            dt = dt.replace(year=dt.year + 2000)
            
        # Ustaw zakres czasowy na cały dzień
        start_date = dt.replace(hour=0, minute=0, second=0).isoformat()
        end_date = dt.replace(hour=23, minute=59, second=59).isoformat()
        
        # Zapytanie SQL używające zakresu dat
        cursor.execute("""
            SELECT c.name, n.content, n.creation_date
            FROM notes n
            JOIN categories c ON n.category_id = c.id
            WHERE n.creation_date BETWEEN ? AND ?
            ORDER BY n.creation_date ASC
        """, (start_date, end_date))
        
        notes = cursor.fetchall()
        
        # Aktualizacja widoku
        daily_text.delete(1.0, tk.END)
        if not notes:
            daily_text.insert(tk.END, f"Brak notatek na dzień {dt.strftime('%d.%m.%Y')}")
        else:
            daily_text.insert(tk.END, f"Notatki z dnia {dt.strftime('%d.%m.%Y')}:\n\n")
            for cat, content, creation_date in notes:
                daily_text.insert(tk.END, f"[{cat.capitalize()}] - {content}\n")
        daily_text.see(tk.END)
    except Exception as e:
        daily_text.delete(1.0, tk.END)
        daily_text.insert(tk.END, f"Wystąpił błąd: {e}")

# --- Odświeżanie notatek na dzisiaj w main_frame ---
def update_today_notes():
    today = datetime.date.today().isoformat()
    cursor.execute("""
        SELECT c.name, n.content
        FROM notes n
        JOIN categories c ON n.category_id = c.id
        WHERE DATE(n.creation_date) = ?
        ORDER BY n.creation_date ASC
    """, (today,))
    notes = cursor.fetchall()
    today_notes_text.delete(1.0, tk.END)
    if not notes:
        today_notes_text.insert(tk.END, "Brak notatek na dzisiaj.")
    else:
        for cat, content in notes:
            today_notes_text.insert(tk.END, f"[{cat.capitalize()}] - {content}\n")
    today_notes_text.see(tk.END)

# --- Okno statystyk ---
def open_statistics_window():
    stats = show_statistics()
    stats_win = tk.Toplevel(window)
    stats_win.title("Statystyki Notatek")
    text = tk.Text(stats_win, font=('Arial', 14))
    text.pack(fill=tk.BOTH, expand=True)
    text.insert(tk.END, stats)
    tk.Button(stats_win, text="Zamknij", command=stats_win.destroy).pack(pady=5)

# --- Okno zmiany hasła ---
def open_change_password_window():
    change_win = tk.Toplevel(window)
    change_win.title("Zmiana hasła")
    change_win.geometry("400x250")
    tk.Label(change_win, text="Podaj stare hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    old_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    old_pass_entry.pack(padx=10, pady=5)
    tk.Label(change_win, text="Podaj nowe hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    new_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    new_pass_entry.pack(padx=10, pady=5)
    tk.Label(change_win, text="Potwierdź nowe hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    confirm_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    confirm_pass_entry.pack(padx=10, pady=5)
    status_label_change = tk.Label(change_win, text="", font=('Arial', 12))
    status_label_change.pack(padx=10, pady=5)
    def change_password():
        current = load_password()
        if old_pass_entry.get() != current:
            status_label_change.config(text="Stare hasło niepoprawne!")
        elif new_pass_entry.get() != confirm_pass_entry.get():
            status_label_change.config(text="Nowe hasło i potwierdzenie nie zgadzają się!")
        else:
            save_password(new_pass_entry.get())
            status_label_change.config(text="Hasło zmienione pomyślnie!")
            change_win.after(2000, change_win.destroy)
    tk.Button(change_win, text="Zmień hasło", font=('Arial', 14), command=change_password).pack(pady=10)

# --- Logo aplikacji ---
def load_logo():
    try:
        logo_img = Image.open("graphics/logo.png")
        logo_img = logo_img.resize((50, 50), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(logo_img)
    except Exception as e:
        print("Błąd ładowania logo:", e)
        return None

# --- Funkcja do dynamicznego skalowania tła ---
def resize_bg(event=None):
    """Dynamicznie skaluje tło do aktualnego rozmiaru okna"""
    try:
        if hasattr(bg_image, 'is_animated') and bg_image.is_animated:
            # Dla animowanego GIF-a nie robimy nic - jest obsługiwany przez update_background_animation
            return
            
        # Dla statycznego obrazu - poprzednia logika
        width = window.winfo_width()
        height = window.winfo_height()
        
        if width <= 1 or height <= 1:
            return
            
        resized = bg_image.resize((width, height), Image.Resampling.LANCZOS)
        new_bg = ImageTk.PhotoImage(resized)
        canvas.itemconfig(bg_item, image=new_bg)
        canvas.image = new_bg
        
        canvas.configure(width=width, height=height)
        canvas.pack(fill="both", expand=True)
    except Exception as e:
        print(f"Błąd skalowania tła: {e}")

# -------------------------
# Definicja funkcji on_enter (przy naciśnięciu Enter w polu input)
def on_enter(event):
    on_send()
# -------------------------

# -------------------------
# Mechanizm uwierzytelniania (okno logowania) – dodano obsługę Enter
def show_login():
    """Pokazuje okno logowania i kończy program jeśli logowanie się nie powiedzie"""
    login_success = False
    
    def on_login_close():
        nonlocal login_success
        if not login_success:
            window.quit()
            sys.exit()
    
    login_win = tk.Toplevel()
    login_win.title("Logowanie")
    login_win.geometry("350x200")
    login_win.protocol("WM_DELETE_WINDOW", on_login_close)  # Obsługa zamknięcia okna
    
    tk.Label(login_win, text="Podaj hasło:", font=('Arial', 14)).pack(padx=10, pady=10)
    password_entry = tk.Entry(login_win, show="*", font=('Arial', 14))
    password_entry.pack(padx=10, pady=5)
    status = tk.Label(login_win, text="", font=('Arial', 12))
    status.pack(padx=10, pady=5)
    
    def check_password(event=None):
        nonlocal login_success
        current = load_password()
        if current and password_entry.get() == current:
            login_success = True
            login_win.destroy()
        else:
            status.config(text="Nieprawidłowe hasło!")
            password_entry.delete(0, tk.END)
    
    password_entry.bind("<Return>", check_password)
    tk.Button(login_win, text="Zaloguj", font=('Arial', 14), command=check_password).pack(pady=10)
    
    login_win.grab_set()
    login_win.wait_window()
    
    if not login_success:
        window.quit()
        sys.exit()

# -------------------------

# -------------------------
# Mechanizm uwierzytelniania – okno logowania z obsługą Enter
def show_login():
    login_win = tk.Toplevel()
    login_win.title("Logowanie")
    login_win.geometry("350x200")
    tk.Label(login_win, text="Podaj hasło:", font=('Arial', 14)).pack(padx=10, pady=10)
    password_entry = tk.Entry(login_win, show="*", font=('Arial', 14))
    password_entry.pack(padx=10, pady=5)
    status = tk.Label(login_win, text="", font=('Arial', 12))
    status.pack(padx=10, pady=5)
    def check_password(event=None):
        current = open("password.txt", "r", encoding="utf-8").read().strip() if os.path.exists("password.txt") else "admin"
        if password_entry.get() == current:
            login_win.destroy()
        else:
            status.config(text="Nieprawidłowe hasło!")
    password_entry.bind("<Return>", check_password)
    tk.Button(login_win, text="Zaloguj", font=('Arial', 14), command=check_password).pack(pady=10)
    login_win.grab_set()
    login_win.wait_window()
# -------------------------

# --- Funkcja do obsługi menu (natychmiastowe wykonanie akcji) ---
def on_menu_action(command):
    if command in ["!plan dnia", "!statystyki", "!eksport notatek", "!import notatek"]:
        if command == "!plan dnia":
            result = generate_daily_plan()
        elif command == "!statystyki":
            result = show_statistics()
        elif command == "!eksport notatek":
            result = export_notes()
        elif command == "!import notatek":
            result = import_notes()
        text_area.insert(tk.END, f"\nEliza: {result}\n\n", "assistant")
        text_area.see(tk.END)  # Automatyczne przewijanie
    elif command == "!pokaż kategorie":
        result = show_categories()
        text_area.insert(tk.END, f"\nEliza: {result}\n\n", "assistant")
        text_area.see(tk.END)  # Automatyczne przewijanie
    elif command == "!kalendarz":
        open_calendar()
    elif command == "!zmień hasło":
        open_change_password_window()
    else:
        entry.delete(0, tk.END)
        entry.insert(0, command + " ")

# --- Funkcja obsługi menu kontekstowego ---
def show_context_menu(event):
    context_menu.tk_popup(event.x_root, event.y_root)

# --- Aktualizacja pamięci kontekstowej ---
def update_context(user_input):
    """Aktualizacja pamięci kontekstowej"""
    lower_input = user_input.lower()
    try:
        # Obsługa preferencji długości odpowiedzi
        if "lubię" in lower_input and "odpowiedzi" in lower_input:
            if "krótkie" in lower_input:
                context_memory["dlugosc"] = "krotkie"
                print("Ustawiono krótkie odpowiedzi")
            elif "długie" in lower_input:
                context_memory["dlugosc"] = "dlugie"
                print("Ustawiono długie odpowiedzi")

        # Zapisywanie imienia
        if "mam na imię" in lower_input or "nazywam się" in lower_input:
            pattern = "mam na imię" if "mam na imię" in lower_input else "nazywam się"
            parts = lower_input.split(pattern)
            if len(parts) > 1:
                name = parts[1].strip().split()[0].capitalize()
                context_memory["imie"] = name
                print(f"Zapisano imię: {name}")  # Debug info
        
        # Zapisywanie wieku
        if "mam" in lower_input and "lat" in lower_input:
            words = lower_input.split()
            for i, word in enumerate(words):
                if word == "mam" and i+1 < len(words):
                    try:
                        age = int(''.join(filter(str.isdigit, words[i+1])))
                        context_memory["wiek"] = age
                        print(f"Zapisano wiek: {age}")  # Debug info
                        break
                    except ValueError:
                        continue
        
        # Add style preferences
        if "wolę formalnie" in lower_input:
            context_memory["styl"] = "formalny"
            print("Ustawiono styl formalny")
        elif "wolę luźno" in lower_input:
            context_memory["styl"] = "luźny"
            print("Ustawiono styl luźny")
            
        # Zawsze zapisuj ostatni prompt
        context_memory["ostatni_prompt"] = user_input
        print(f"Aktualny kontekst: {context_memory}")  # Debug info
        
    except Exception as e:
        print(f"Błąd w update_context: {e}")

# --- Główna funkcja obsługi komend ---
def normalize_command(text):
    """Normalizuje komendę usuwając wykrzyknik i ewentualne podwójne spacje"""
    text = text.strip()
    if text.startswith('!'):
        text = text[1:]

    # Normalizacja polskich znaków i wariantów kategorii
    polish_chars = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'
    }
    
    # Zamień "kategorię" na "kategorie"
    text = text.replace("kategorię", "kategorie")
    
    # Normalizuj tylko pierwsze dwa słowa
    parts = text.split(' ', 2)
    if len(parts) >= 1:
        for old, new in polish_chars.items():
            parts[0] = parts[0].lower().replace(old, new)
    if len(parts) >= 2:
        for old, new in polish_chars.items():
            parts[1] = parts[1].lower().replace(old, new)
    
    return ' '.join(parts)

def extract_category_name(command, user_input):
    """Wyciąga nazwę kategorii z komendy"""
    # Konwertuj oba argumenty na małe litery do porównania
    command_lower = command.lower()
    user_input_lower = user_input.lower()
    
    # Lista możliwych wariantów słowa "kategoria"
    variants = ["kategorie", "kategorię", "kategoria"]
    
    # Znajdź najdłuższy pasujący wariant
    found_variant = None
    for variant in variants:
        if variant in command_lower:
            found_variant = variant
            break
            
    if not found_variant:
        return ""
        
    # Znajdź pozycję końca słowa "kategoria" w oryginalnym tekście
    variant_pos = user_input_lower.find(found_variant)
    if variant_pos == -1:
        return ""
        
    # Weź tekst po końcu wariantu "kategoria"
    category_name = user_input[variant_pos + len(found_variant):].strip()
    return category_name

def extract_note_parts(command, user_input):
    """Wyciąga kategorię i treść notatki z komendy"""
    cmd = "dodaj notatk"  # Bazowy początek komendy
    if command.startswith(cmd):
        # Znajdź pozycję pierwszego znaku po komendzie
        cmd_end = user_input.lower().find(cmd) + len(cmd)
        # Pomiń "ę", "e" lub "a" na końcu słowa "notatka"
        while cmd_end < len(user_input) and user_input[cmd_end] in ['ę', 'e', 'a']:
            cmd_end += 1
        # Pomiń spacje po komendzie
        while cmd_end < len(user_input) and user_input[cmd_end].isspace():
            cmd_end += 1
            
        rest = user_input[cmd_end:].strip()
        if rest:
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
    return None, None

def extract_edit_note_parts(command, user_input):
    """Wyciąga kategorię, starą i nową treść z komendy edycji"""
    cmd = "edytuj notatk"  # Bazowy początek komendy
    if command.startswith(cmd):
        # Znajdź pozycję pierwszego znaku po komendzie
        cmd_end = user_input.lower().find(cmd) + len(cmd)
        # Pomiń "ę", "e" lub "a" na końcu słowa "notatka"
        while cmd_end < len(user_input) and user_input[cmd_end] in ['ę', 'e', 'a']:
            cmd_end += 1
        # Pomiń spacje po komendzie
        while cmd_end < len(user_input) and user_input[cmd_end].isspace():
            cmd_end += 1
        
        rest = user_input[cmd_end:].strip()
        if rest and "||" in rest:
            before_sep, new_content = rest.split("||", 1)
            parts = before_sep.strip().split(" ", 1)
            if len(parts) == 2:
                return parts[0], parts[1].strip(), new_content.strip()
    return None, None, None

def extract_delete_note_parts(command, user_input):
    """Wyciąga kategorię i treść z komendy usuwania notatki"""
    cmd = "usun notatk"  # Bazowy początek komendy
    if normalized_cmd := normalize_command(command.lower()):
        if not normalized_cmd.startswith(cmd):
            return None, None
            
        # Znajdź pozycję pierwszego znaku po komendzie w oryginalnym tekście
        cmd_end = user_input.lower().find("notatk") + len("notatk")
        # Pomiń "ę", "e" lub "a" na końcu słowa "notatka"
        while cmd_end < len(user_input) and user_input[cmd_end] in ['ę', 'e', 'a']:
            cmd_end += 1
        # Pomiń spacje po komendzie
        while cmd_end < len(user_input) and user_input[cmd_end].isspace():
            cmd_end += 1
            
        rest = user_input[cmd_end:].strip()
        if rest:
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
    return None, None

def extract_delete_category_parts(command, user_input):
    """Wyciąga nazwę kategorii z komendy usuwania kategorii"""
    cmd = "usun kategori"  # Bazowy początek komendy
    if normalized_cmd := normalize_command(command.lower()):
        if not normalized_cmd.startswith(cmd):
            return None
            
        # Znajdź pozycję pierwszego znaku po komendzie w oryginalnym tekście
        cmd_end = user_input.lower().find("kategori") + len("kategori")
        # Pomiń "ę", "e" lub "a" na końcu słowa "kategoria"
        while cmd_end < len(user_input) and user_input[cmd_end] in ['ę', 'e', 'a']:
            cmd_end += 1
        # Pomiń spacje po komendzie
        while cmd_end < len(user_input) and user_input[cmd_end].isspace():
            cmd_end += 1
            
        return user_input[cmd_end:].strip()
    return None

def on_send():
    global last_response, auto_read, generating_response
    user_input = entry.get().strip()
    if not user_input:
        status_label.config(text="Wpisz polecenie lub pytanie.")
        return
    
    # Normalizacja komendy
    normalized_input = normalize_command(user_input.lower())
    
    update_context(user_input)
    text_area.insert(tk.END, f"Ty: {user_input}\n\n", "user")
    entry.delete(0, tk.END)
    
    # Reset flag przed generowaniem
    generating_response = False
    
    # Sprawdzanie komend bez wykrzyknika
    if normalized_input.startswith("dodaj notatk"):
        category_name, content = extract_note_parts(normalized_input, user_input)
        if not category_name or not content:
            response = "Błąd: Nieprawidłowy format komendy. Użyj: dodaj notatkę [kategoria] [treść]"
        else:
            response = add_note(category_name, content)
            
    elif normalized_input.startswith("edytuj notatk"):  # Obsługa wszystkich wariantów edycji
        category_name, old_content, new_content = extract_edit_note_parts(normalized_input, user_input)
        if not category_name or not old_content or not new_content:
            response = "Błąd: Użyj jednego z formatów:\n" + \
                       "1. edytuj notatkę [kategoria] [stara treść] || [nowa treść]\n" + \
                       "2. edytuj notatkę [kategoria] zamień [stara treść] na [nowa treść]"
        else:
            response = edit_note(category_name, old_content, new_content)
            
    elif normalized_input.startswith("usun notatk"):  # Obsługa wszystkich wariantów usuwania
        category_name, content = extract_delete_note_parts(normalized_input, user_input)
        if not category_name or not content:
            response = "Błąd: Użyj formatu: usuń notatkę [kategoria] [treść]"
        else:
            response = delete_note(category_name, content)
    
    elif normalized_input.startswith(("stworz kategorie", "stwórz kategorie", "stwórz kategorię")):
        # Znajdź pozycję po słowie "kategorie" lub "kategorię"
        parts = user_input.lower().split()
        category_start = -1
        for i, word in enumerate(parts):
            if word.startswith(("kategori")):
                category_start = i + 1
                break
                
        if category_start >= len(parts):
            response = "Błąd: Nieprawidłowy format komendy. Użyj: stwórz kategorię [nazwa kategorii]"
        else:
            category_name = ' '.join(parts[category_start:])
            response = create_category(category_name)
    
    elif normalized_input.startswith("dodaj notatkę"):
        command_prefix = "dodaj notatkę"
        arguments = normalized_input[len(command_prefix):].strip()
        if not arguments or len(arguments.split(" ", 1)) != 2:
            response = "Błąd: Nieprawidłowy format komendy. Użyj: dodaj notatkę [kategoria] [treść]"
        else:
            category_name, content = arguments.split(" ", 1)
            response = add_note(category_name, content)
            
    elif normalized_input.startswith("edytuj notatkę"):
        command_prefix = "edytuj notatkę"
        arguments = normalized_input[len(command_prefix):].strip()
        if "||" not in arguments:
            response = "Błąd: Użyj jednego z formatów:\n" + \
                       "1. edytuj notatkę [kategoria] [stara treść] || [nowa treść]\n" + \
                       "2. edytuj notatkę [kategoria] zamień [stara treść] na [nowa treść]"
        else:
            before_sep, new_content = arguments.split("||", 1)
            parts = before_sep.strip().split(" ", 1)
            if len(parts) != 2:
                response = "Błąd: Użyj jednego z formatów:\n" + \
                           "1. edytuj notatkę [kategoria] [stara treść] || [nowa treść]\n" + \
                           "2. edytuj notatkę [kategoria] zamień [stara treść] na [nowa treść]"
            else:
                category_name, old_content = parts
                response = edit_note(category_name, old_content.strip(), new_content.strip())
                
    elif normalized_input.startswith("usuń notatkę"):
        command_prefix = "usuń notatkę"
        arguments = normalized_input[len(command_prefix):].strip()
        if not arguments or len(arguments.split(" ", 1)) != 2:
            response = "Błąd: Użyj: usuń notatkę [kategoria] [treść]"
        else:
            category_name, content = arguments.split(" ", 1)
            response = delete_note(category_name, content)
            
    elif normalized_input.startswith(("usuń kategorię", "usun kategorie")):  # Obsługa wszystkich wariantów usuwania kategorii
        category_name = extract_delete_category_parts(normalized_input, user_input)
        if not category_name:
            response = "Błąd: Użyj formatu: usuń kategorię [nazwa]"
        else:
            response = delete_category(category_name)
            window.after(100, refresh_notes)  # Odśwież widok notatek po usunięciu kategorii
            
    elif normalized_input.startswith("wyszukaj notatki"):
        command_prefix = "wyszukaj notatki"
        arguments = normalized_input[len(command_prefix):].strip()
        if not arguments:
            response = "Błąd: Użyj: wyszukaj notatki [słowo_kluczowe]"
        else:
            response = search_notes(arguments)
            
    elif normalized_input == "plan dnia":
        response = generate_daily_plan()
    elif normalized_input == "eksport notatek":
        response = export_notes()
    elif normalized_input == "import notatek":
        response = import_notes()
    elif normalized_input == "statystyki":
        response = show_statistics()
        
    elif normalized_input.startswith(("pokaż notatki", "pokaz notatki")):
        command_prefix = "pokaż notatki" if "pokaż" in normalized_input else "pokaz notatki"
        arguments = normalized_input[len(command_prefix):].strip()
        if arguments:
            response = get_notes(arguments)
        else:
            response = get_notes()
            
    elif normalized_input.startswith(("stwórz kategorię", "stworz kategorie")):
        command_prefix = "stwórz kategorię" if "kategorię" in normalized_input else "stworz kategorie"
        arguments = normalized_input[len(command_prefix):].strip()
        if not arguments:
            response = "Błąd: Nieprawidłowy format komendy. Użyj: stwórz kategorię [nazwa kategorii]"
        else:
            response = create_category(arguments)
            
    elif normalized_input.startswith(("pokaż kategorie", "pokaz kategorie")):
        parts = normalized_input.split(" ", 2)
        if len(parts) == 2:
            response = show_categories()
        else:
            category_name = parts[2]
            response = get_notes(category_name)
    else:
        response = generate_response(user_input)
    if response and not generating_response:
        text_area.insert(tk.END, f"\nEliza: {response}\n\n", "assistant")
        last_response = response
        status_label.config(text="Operacja zakończona pomyślnie.")
        text_area.see(tk.END)
        if auto_read:
            speak(response)

# --- Funkcja odświeżania notatek w notes_frame ---
def refresh_notes():
    try:
        cursor.execute("""
            SELECT c.name, n.id, n.content 
            FROM notes n
            JOIN categories c ON n.category_id = c.id 
            ORDER BY c.name, n.creation_date
        """)
        results = cursor.fetchall()
        
        notes_data = {}
        for cat_name, note_id, content in results:
            if cat_name not in notes_data:
                notes_data[cat_name] = []
            notes_data[cat_name].append({
                'id': note_id,
                'content': content
            })
            
        if notes_data:  # Dodano sprawdzenie czy są dane
            notes_tile_frame.refresh_notes(notes_data)
        else:
            # Wyświetl informację o braku notatek
            for widget in notes_tile_frame.scrollable_frame.winfo_children():
                widget.destroy()
            tk.Label(
                notes_tile_frame.scrollable_frame,
                text="Brak notatek",
                font=('Arial', 14),
                bg='white'
            ).pack(pady=20)
            
    except Exception as e:
        print(f"Błąd odświeżania notatek: {e}")

# --- Funkcja odświeżania notatek na dzisiaj w main_frame ---
def update_today_notes():
    today = datetime.date.today().isoformat()
    cursor.execute("""
        SELECT c.name, n.content
        FROM notes n
        JOIN categories c ON n.category_id = c.id
        WHERE DATE(n.creation_date) = ?
        ORDER BY n.creation_date ASC
    """, (today,))
    notes = cursor.fetchall()
    today_notes_text.delete(1.0, tk.END)
    if not notes:
        today_notes_text.insert(tk.END, "Brak notatek na dzisiaj.")
    else:
        for cat, content in notes:
            today_notes_text.insert(tk.END, f"[{cat.capitalize()}] - {content}\n")
    today_notes_text.see(tk.END)

# --- Funkcja otwierająca okno statystyk ---
def open_statistics_window():
    stats = show_statistics()
    stats_win = tk.Toplevel(window)
    stats_win.title("Statystyki Notatek")
    text = tk.Text(stats_win, font=('Arial', 14))
    text.pack(fill=tk.BOTH, expand=True)
    text.insert(tk.END, stats)
    tk.Button(stats_win, text="Zamknij", command=stats_win.destroy).pack(pady=5)

# --- Funkcja do otwierania okna zmiany hasła ---
def open_change_password_window():
    def load_password():
        if os.path.exists("password.txt"):
            with open("password.txt", "r", encoding="utf-8") as f:
                return f.read().strip()
        else:
            return "admin"
    def save_password(new_pass):
        with open("password.txt", "w", encoding="utf-8") as f:
            f.write(new_pass.strip())
    change_win = tk.Toplevel(window)
    change_win.title("Zmiana hasła")
    change_win.geometry("600x450")
    tk.Label(change_win, text="Podaj stare hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    old_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    old_pass_entry.pack(padx=10, pady=5)
    tk.Label(change_win, text="Podaj nowe hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    new_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    new_pass_entry.pack(padx=10, pady=5)
    tk.Label(change_win, text="Potwierdź nowe hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    confirm_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    confirm_pass_entry.pack(padx=10, pady=5)
    status_label_change = tk.Label(change_win, text="", font=('Arial', 12))
    status_label_change.pack(padx=10, pady=5)
    def change_password():
        current = load_password()
        if old_pass_entry.get() != current:
            status_label_change.config(text="Stare hasło niepoprawne!")
        elif new_pass_entry.get() != confirm_pass_entry.get():
            status_label_change.config(text="Nowe hasło i potwierdzenie nie zgadzają się!")
        else:
            save_password(new_pass_entry.get())
            status_label_change.config(text="Hasło zmienione pomyślnie!")
            change_win.after(2000, change_win.destroy)
    tk.Button(change_win, text="Zmień hasło", font=('Arial', 14), command=change_password).pack(pady=10)

# --- Logo aplikacji ---
def load_logo():
    try:
        logo_img = Image.open("graphics/logo.png")
        logo_img = logo_img.resize((50, 50), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(logo_img)
    except Exception as e:
        print("Błąd ładowania logo:", e)
        return None

# -------------------------
# Definicja funkcji on_enter (Enter w polu inputu)
def on_enter(event):
    on_send()
# -------------------------

# -------------------------
# Mechanizm uwierzytelniania – okno logowania z obsługą Enter
def show_login():
    login_win = tk.Toplevel()
    login_win.title("Logowanie")
    login_win.geometry("350x200")
    tk.Label(login_win, text="Podaj hasło:", font=('Arial', 14)).pack(padx=10, pady=10)
    password_entry = tk.Entry(login_win, show="*", font=('Arial', 14))
    password_entry.pack(padx=10, pady=5)
    status = tk.Label(login_win, text="", font=('Arial', 12))
    status.pack(padx=10, pady=5)
    def check_password(event=None):
        current = open("password.txt", "r", encoding="utf-8").read().strip() if os.path.exists("password.txt") else "admin"
        if password_entry.get() == current:
            login_win.destroy()
        else:
            status.config(text="Nieprawidłowe hasło!")
    password_entry.bind("<Return>", check_password)
    tk.Button(login_win, text="Zaloguj", font=('Arial', 14), command=check_password).pack(pady=10)
    login_win.grab_set()
    login_win.wait_window()
# -------------------------

def add_attachment(note_id, file_path):
    """Dodaje załącznik do notatki"""
    try:
        filename = os.path.basename(file_path)
        file_type = os.path.splitext(filename)[1].lower()
        
        # Utwórz folder na załączniki jeśli nie istnieje
        attachments_dir = os.path.join(os.path.dirname(__file__), "attachments")
        if not os.path.exists(attachments_dir):
            os.makedirs(attachments_dir)
            
        # Skopiuj plik do folderu załączników
        new_path = os.path.join(attachments_dir, f"{note_id}_{filename}")
        import shutil
        shutil.copy2(file_path, new_path)
        
        cursor.execute("""
            INSERT INTO attachments (note_id, filename, file_type, file_path)
            VALUES (?, ?, ?, ?)
        """, (note_id, filename, file_type, new_path))
        conn.commit()
        return True
    except Exception as e:
        print(f"Błąd dodawania załącznika: {e}")
        return False

def get_attachments(note_id):
    """Pobiera listę załączników dla notatki"""
    cursor.execute("""
        SELECT id, filename, file_type, file_path 
        FROM attachments 
        WHERE note_id = ?
    """, (note_id,))
    return cursor.fetchall()

def open_attachment(file_path):
    """Otwiera załącznik w domyślnym programie"""
    import subprocess
    import platform
    
    try:
        if platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', file_path])
        elif platform.system() == 'Windows':  # Windows
            os.startfile(file_path)
        else:  # Linux
            subprocess.run(['xdg-open', file_path])
    except Exception as e:
        print(f"Błąd otwierania załącznika: {e}")

class NoteTile(tk.Frame):
    """Widget reprezentujący pojedynczą notatkę w formie kafelka"""
    def __init__(self, master, category, content, note_id, bg_color, **kwargs):
        super().__init__(master, **kwargs)
        self.note_id = note_id
        self.bg_color = bg_color
        self.category = category  # Dodajemy przechowywanie kategorii
        self.configure(relief=tk.RAISED, borderwidth=2, bg=self.bg_color)
        
        # Kontener na nagłówek i przyciski
        header_frame = tk.Frame(self, bg=self.bg_color)
        header_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # Nagłówek z kategorią (po lewej)
        self.header = tk.Label(
            header_frame, 
            text=category.capitalize(),
            font=('Arial', 12, 'bold'),
            bg=self.bg_color,
            fg='white'
        )
        self.header.pack(side=tk.LEFT)
        
        # Kontener na przyciski (po prawej)
        buttons_frame = tk.Frame(header_frame, bg=self.bg_color)
        buttons_frame.pack(side=tk.RIGHT)
        
        # Ładowanie ikon
        try:
            # Ikony dla wszystkich przycisków
            attach_icon = Image.open("graphics/attach.png")
            attach_icon = attach_icon.resize((20, 20), Image.Resampling.LANCZOS)
            self.attach_icon = ImageTk.PhotoImage(attach_icon)
            
            edit_icon = Image.open("graphics/edit.png")
            edit_icon = edit_icon.resize((20, 20), Image.Resampling.LANCZOS)
            self.edit_icon = ImageTk.PhotoImage(edit_icon)
            
            delete_icon = Image.open("graphics/delete.png")
            delete_icon = delete_icon.resize((20, 20), Image.Resampling.LANCZOS)
            self.delete_icon = ImageTk.PhotoImage(delete_icon)
            
            has_attach_icon = Image.open("graphics/attach.png")
            has_attach_icon = has_attach_icon.resize((16, 16), Image.Resampling.LANCZOS)
            self.has_attach_icon = ImageTk.PhotoImage(has_attach_icon)
        except Exception as e:
            print(f"Błąd ładowania ikon: {e}")
            self.attach_icon = None
            self.edit_icon = None
            self.delete_icon = None
            self.has_attach_icon = None

        # Przycisk usuwania
        self.delete_button = tk.Button(
            buttons_frame,
            image=self.delete_icon if self.delete_icon else None,
            text="?" if not self.delete_icon else None,
            bg=self.bg_color,
            fg='white',
            command=self.delete_note,
            bd=0,
            highlightthickness=0
        )
        self.delete_button.pack(side=tk.RIGHT, padx=2)
        
        # Przycisk edycji
        self.edit_button = tk.Button(
            buttons_frame,
            image=self.edit_icon if self.edit_icon else None,
            text="?" if not self.edit_icon else None,
            bg=self.bg_color,
            fg='white',
            command=self.edit_note,
            bd=0,
            highlightthickness=0
        )
        self.edit_button.pack(side=tk.RIGHT, padx=2)
        
        # Przycisk załączników
        self.attach_button = tk.Button(
            buttons_frame,
            image=self.attach_icon if self.attach_icon else None,
            text="?" if not self.attach_icon else None,
            bg=self.bg_color,
            fg='white',
            command=self.manage_attachments,
            bd=0,
            highlightthickness=0
        )
        self.attach_button.pack(side=tk.RIGHT, padx=2)

        # Treść notatki i oznaczenie załączników
        content_frame = tk.Frame(self, bg=self.bg_color)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        
        self.content = content
        self.content_label = tk.Label(
            content_frame,
            text=content[:50] + "..." if len(content) > 50 else content,
            wraplength=200,
            justify=tk.LEFT,
            bg=self.bg_color,
            fg='white'
        )
        self.content_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Sprawdź czy notatka ma załączniki i dodaj ikonę jeśli tak
        attachments = get_attachments(self.note_id)
        if attachments:
            self.has_attachments_label = tk.Label(
                content_frame,
                image=self.has_attach_icon if self.has_attach_icon else None,
                text="*" if not self.has_attach_icon else None,
                bg=self.bg_color,
                fg='white'
            )
            self.has_attachments_label.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Stan rozwinięcia
        self.expanded = False
        
        # Bind kliknięcia
        self.bind('<Button-1>', self.toggle_expand)
        self.header.bind('<Button-1>', self.toggle_expand)
        self.content_label.bind('<Button-1>', self.toggle_expand)
        
    def toggle_expand(self, event=None):
        if self.expanded:
            self.content_label.configure(text=self.content[:50] + "..." if len(self.content) > 50 else self.content)
        else:
            self.content_label.configure(text=self.content)
        self.expanded = not self.expanded

    def manage_attachments(self):
        """Otwiera okno zarządzania załącznikami"""
        attach_win = tk.Toplevel(self)
        attach_win.title("Załączniki")
        attach_win.geometry("400x300")
        
        # Lista załączników
        files_frame = tk.Frame(attach_win)
        files_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Etykieta informacyjna
        info_label = tk.Label(files_frame, text="Lista załączników:", font=('Arial', 10, 'bold'))
        info_label.pack(pady=(0, 5))
        
        # Scrollowana lista
        scrollbar = tk.Scrollbar(files_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        files_list = tk.Listbox(files_frame, yscrollcommand=scrollbar.set, font=('Arial', 10))
        files_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar.config(command=files_list.yview)
        
        def refresh_list():
            files_list.delete(0, tk.END)
            attachments = get_attachments(self.note_id)
            for att in attachments:
                files_list.insert(tk.END, att[1])  # filename
                
            # Dodaj lub zaktualizuj ikonę załączników
            if attachments and not hasattr(self, 'has_attachments_label'):
                self.has_attachments_label = tk.Label(
                    self.content_label.master,  # używamy content_frame jako rodzica
                    image=self.has_attach_icon if self.has_attach_icon else None,
                    text="*" if not self.has_attach_icon else None,
                    bg=self.bg_color,
                    fg='white'
                )
                self.has_attachments_label.pack(side=tk.RIGHT, padx=(5, 0))
                
            # Wymuszenie przerysowania kafelka
            self.update_idletasks()
        
        refresh_list()
        
        # Przyciski
        btn_frame = tk.Frame(attach_win)
        btn_frame.pack(fill=tk.X, pady=5)
        
        def add_file():
            file_path = tk.filedialog.askopenfilename(
                title="Wybierz plik do załączenia",
                filetypes=[
                    ("Wszystkie obsługiwane", "*.txt;*.pdf;*.png;*.jpg;*.jpeg;*.gif"),
                    ("Pliki tekstowe", "*.txt"),
                    ("Pliki PDF", "*.pdf"),
                    ("Obrazy", "*.png;*.jpg;*.jpeg;*.gif")
                ]
            )
            if file_path:
                if add_attachment(self.note_id, file_path):
                    refresh_list()
                    
        def open_selected():
            selection = files_list.curselection()
            if selection:
                idx = selection[0]
                attachments = get_attachments(self.note_id)
                if idx < len(attachments):
                    open_attachment(attachments[idx][3])  # file_path
        
        tk.Button(btn_frame, text="Dodaj plik", command=add_file).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Otwórz", command=open_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Zamknij", command=attach_win.destroy).pack(side=tk.RIGHT, padx=5)

    def delete_note(self):
        if tk.messagebox.askyesno("Usuń notatkę", "Czy na pewno chcesz usunąć tę notatkę?"):
            try:
                cursor.execute("""
                    DELETE FROM notes 
                    WHERE id = ?
                """, (self.note_id,))
                conn.commit()
                self.master.after(100, lambda: refresh_notes())  # Odśwież widok po usunięciu
            except Exception as e:
                tk.messagebox.showerror("Błąd", f"Nie udało się usunąć notatki: {e}")

    def edit_note(self):
        edit_win = tk.Toplevel(self)
        edit_win.title("Edytuj notatkę")
        edit_win.geometry("400x300")
        
        tk.Label(edit_win, text="Nowa treść notatki:", font=('Arial', 12)).pack(pady=5)
        
        edit_text = tk.Text(edit_win, font=('Arial', 12), height=10)
        edit_text.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)
        edit_text.insert('1.0', self.content)
        
        def save_changes():
            new_content = edit_text.get('1.0', tk.END).strip()
            if new_content:
                try:
                    cursor.execute("""
                        UPDATE notes 
                        SET content = ? 
                        WHERE id = ?
                    """, (new_content, self.note_id))
                    conn.commit()
                    self.master.after(100, lambda: refresh_notes())  # Odśwież widok po edycji
                    edit_win.destroy()
                except Exception as e:
                    tk.messagebox.showerror("Błąd", f"Nie udało się zaktualizować notatki: {e}")
        
        tk.Button(edit_win, text="Zapisz", command=save_changes).pack(pady=10)

class NoteTileFrame(tk.Frame):
    """Frame zawierający kafelki notatek"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(bg='white')
        
        # Słownik kolorów dla kategorii
        self.category_colors = {}
        self.color_palette = [
            '#2196F3', '#4CAF50', '#F44336', '#9C27B0', 
            '#FF9800', '#795548', '#607D8B', '#E91E63',
            '#009688', '#673AB7', '#3F51B5', '#FFC107'
        ]
        
        # Canvas i scrollbar
        self.canvas = tk.Canvas(self, bg='white')
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg='white')
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Bind przewijania
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Bind zmiany rozmiaru
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
        
    def get_category_color(self, category):
        if category not in self.category_colors:
            if len(self.category_colors) < len(self.color_palette):
                color = self.color_palette[len(self.category_colors)]
            else:
                color = random.choice(self.color_palette)
            self.category_colors[category] = color
        return self.category_colors[category]
        
    def refresh_notes(self, notes_data):
        # Usuń stare kafelki
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        # Dodaj nowe kafelki
        row = 0
        col = 0
        max_cols = 2  # Liczba kolumn
        
        for category, notes in notes_data.items():
            color = self.get_category_color(category)
            for note in notes:
                tile = NoteTile(
                    self.scrollable_frame,
                    category,
                    note['content'],
                    note['id'],  # Pass note_id from the dictionary
                    color
                )
                tile.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
        
        # Konfiguracja siatki
        for i in range(max_cols):
            self.scrollable_frame.grid_columnconfigure(i, weight=1)

class FilterSortPanel(tk.Frame):
    """Panel kontrolny do filtrowania i sortowania notatek"""
    def __init__(self, master, on_filter_change, on_sort_change, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(bg='white')
        
        # Filtrowanie
        filter_frame = tk.LabelFrame(self, text="Filtry", bg='white')
        filter_frame.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        
        # Filtr kategorii
        tk.Label(filter_frame, text="Kategoria:", bg='white').pack(side=tk.LEFT, padx=5)
        self.category_var = tk.StringVar(value="Wszystkie")
        self.category_filter = ttk.Combobox(filter_frame, textvariable=self.category_var, width=15)
        self.category_filter.pack(side=tk.LEFT, padx=5)
        self.update_categories()
        
        # Filtr daty
        tk.Label(filter_frame, text="Data:", bg='white').pack(side=tk.LEFT, padx=5)
        self.date_var = tk.StringVar(value="Wszystkie")
        self.date_filter = ttk.Combobox(filter_frame, textvariable=self.date_var, 
                                      values=["Wszystkie", "Dziś", "Ostatni tydzień", "Ostatni miesiąc"])
        self.date_filter.pack(side=tk.LEFT, padx=5)
        
        # Filtr tekstu
        tk.Label(filter_frame, text="Szukaj:", bg='white').pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(filter_frame, textvariable=self.search_var, width=20)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        
        # Sortowanie
        sort_frame = tk.LabelFrame(self, text="Sortowanie", bg='white')
        sort_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.sort_var = tk.StringVar(value="Data (najnowsze)")
        sort_options = [
            "Data (najnowsze)", 
            "Data (najstarsze)", 
            "Kategoria (A-Z)", 
            "Kategoria (Z-A)",
            "Treść (A-Z)",
            "Treść (Z-A)"
        ]
        self.sort_combo = ttk.Combobox(sort_frame, textvariable=self.sort_var, values=sort_options, width=15)
        self.sort_combo.pack(side=tk.LEFT, padx=5)
        
        # Bindy na zmiany
        self.category_filter.bind('<<ComboboxSelected>>', lambda e: on_filter_change())
        self.date_filter.bind('<<ComboboxSelected>>', lambda e: on_filter_change())
        self.search_var.trace('w', lambda *args: on_filter_change())
        self.sort_combo.bind('<<ComboboxSelected>>', lambda e: on_sort_change())
        
    def update_categories(self):
        """Aktualizuje listę kategorii w filtrze"""
        cursor.execute("SELECT DISTINCT name FROM categories ORDER BY name")
        categories = ["Wszystkie"] + [row[0] for row in cursor.fetchall()]
        self.category_filter['values'] = categories
        
    def get_filter_criteria(self):
        """Zwraca aktualne kryteria filtrowania"""
        return {
            'category': self.category_var.get(),
            'date': self.date_var.get(),
            'search': self.search_var.get()
        }
        
    def get_sort_criteria(self):
        """Zwraca aktualne kryterium sortowania"""
        return self.sort_var.get()

# Modyfikacja klasy NoteTileFrame
class NoteTileFrame(tk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(bg='white')
        
        # Dodaj panel filtrowania i sortowania
        self.filter_panel = FilterSortPanel(self, 
                                          self.apply_filters_and_sort,
                                          self.apply_filters_and_sort)
        self.filter_panel.pack(fill=tk.X, padx=5, pady=5)
        
        # Słownik kolorów dla kategorii
        self.category_colors = {}
        self.color_palette = [
            '#2196F3', '#4CAF50', '#F44336', '#9C27B0', 
            '#FF9800', '#795548', '#607D8B', '#E91E63',
            '#009688', '#673AB7', '#3F51B5', '#FFC107'
        ]
        
        # Canvas i scrollbar
        self.canvas = tk.Canvas(self, bg='white')
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg='white')
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Bind przewijania
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # Bind zmiany rozmiaru
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
        
    def get_category_color(self, category):
        if category not in self.category_colors:
            if len(self.category_colors) < len(self.color_palette):
                color = self.color_palette[len(self.category_colors)]
            else:
                color = random.choice(self.color_palette)
            self.category_colors[category] = color
        return self.category_colors[category]
        
    def refresh_notes(self, notes_data):
        # Usuń stare kafelki
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        # Dodaj nowe kafelki
        row = 0
        col = 0
        max_cols = 2  # Liczba kolumn
        
        for category, notes in notes_data.items():
            color = self.get_category_color(category)
            for note in notes:
                tile = NoteTile(
                    self.scrollable_frame,
                    category,
                    note['content'],
                    note['id'],  # Pass note_id from the dictionary
                    color
                )
                tile.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
        
        # Konfiguracja siatki
        for i in range(max_cols):
            self.scrollable_frame.grid_columnconfigure(i, weight=1)

    def apply_filters_and_sort(self):
        """Aplikuje filtry i sortowanie do notatek"""
        criteria = self.filter_panel.get_filter_criteria()
        sort_by = self.filter_panel.get_sort_criteria()
        
        # Podstawowe zapytanie
        query = """
            SELECT c.name, n.id, n.content, n.creation_date
            FROM notes n
            JOIN categories c ON n.category_id = c.id
            WHERE 1=1
        """
        params = []
        
        # Dodaj filtry
        if criteria['category'] != "Wszystkie":
            query += " AND c.name = ?"
            params.append(criteria['category'])
            
        if criteria['search']:
            query += " AND n.content LIKE ?"
            params.append(f"%{criteria['search']}%")
            
        if criteria['date'] != "Wszystkie":
            today = datetime.datetime.now()
            if criteria['date'] == "Dziś":
                query += " AND DATE(n.creation_date) = DATE(?)"
                params.append(today.strftime('%Y-%m-%d'))
            elif criteria['date'] == "Ostatni tydzień":
                week_ago = today - datetime.timedelta(days=7)
                query += " AND n.creation_date >= ?"
                params.append(week_ago.isoformat())
            elif criteria['date'] == "Ostatni miesiąc":
                month_ago = today - datetime.timedelta(days=30)
                query += " AND n.creation_date >= ?"
                params.append(month_ago.isoformat())
                
        # Dodaj sortowanie
        if sort_by == "Data (najnowsze)":
            query += " ORDER BY n.creation_date DESC"
        elif sort_by == "Data (najstarsze)":
            query += " ORDER BY n.creation_date ASC"
        elif sort_by == "Kategoria (A-Z)":
            query += " ORDER BY c.name ASC"
        elif sort_by == "Kategoria (Z-A)":
            query += " ORDER BY c.name DESC"
        elif sort_by == "Treść (A-Z)":
            query += " ORDER BY n.content ASC"
        elif sort_by == "Treść (Z-A)":
            query += " ORDER BY n.content DESC"
            
        # Wykonaj zapytanie i odśwież widok
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Przygotuj dane dla refresh_notes
        notes_data = {}
        for cat_name, note_id, content, _ in results:
            if cat_name not in notes_data:
                notes_data[cat_name] = []
            notes_data[cat_name].append({
                'id': note_id,
                'content': content
            })
            
        self.refresh_notes(notes_data)

# -------------------------
# Główna część – tworzenie okna głównego
window = tk.Tk()
window.title("Osobisty Asystent AI")
window.geometry("1600x1000")  # Większy rozmiar okna
window.minsize(1400, 900)     # Minimalne wymiary okna
window.bind("<Configure>", resize_bg)
window.withdraw()
show_login()
window.deiconify()

# Poczekaj aż okno się pokaże i wymuś aktualizację tła
def init_window():
    window.update_idletasks()
    resize_bg()
    
window.after(100, init_window)
# -------------------------

# --- Ustawienie tła z obrazkiem ---
# Dodaj nową funkcję do obsługi animowanego GIF-a
def update_background_animation():
    """Aktualizuje klatkę animowanego GIF-a"""
    try:
        # Pobierz następną klatkę
        bg_image.seek(bg_image.tell() + 1)
    except EOFError:
        # Gdy dojdziemy do końca animacji, wracamy do początku
        bg_image.seek(0, 0)
    
    # Przeskaluj klatkę do rozmiaru okna
    frame = bg_image.copy()
    width = window.winfo_width()
    height = window.winfo_height()
    frame = frame.resize((width, height), Image.Resampling.LANCZOS)
    
    # Konwertuj na PhotoImage
    photo = ImageTk.PhotoImage(frame)
    
    # Aktualizuj obraz na canvasie
    canvas.itemconfig(bg_item, image=photo)
    canvas.image = photo  # Zachowaj referencję
    
    # Zaplanuj następną aktualizację (czas w milisekundach)
    delay = bg_image.info.get('duration', 100)  # Domyślnie 100ms jeśli nie określono
    window.after(delay, update_background_animation)

# Zmień sekcję ładowania tła
try:
    bg_image = Image.open("graphics/background.gif")
    # Sprawdź czy to animowany GIF
    is_animated = hasattr(bg_image, 'is_animated') and bg_image.is_animated
    
    if is_animated:
        # Inicjalizacja pierwszej klatki
        frame = bg_image.copy()
        frame = frame.resize((1600, 1000), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(frame)
        
        canvas = tk.Canvas(window, width=1600, height=1000)
        canvas.pack(fill="both", expand=True)
        bg_item = canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.image = photo  # Zachowaj referencję
        
        # Uruchom animację
        window.after(0, update_background_animation)
    else:
        # Jeśli to nie jest animowany GIF, zachowaj obecne zachowanie
        resized_image = bg_image.resize((1600, 1000), Image.Resampling.LANCZOS)
        bg_photo = ImageTk.PhotoImage(resized_image)
        canvas = tk.Canvas(window, width=1600, height=1000)
        canvas.pack(fill="both", expand=True)
        bg_item = canvas.create_image(0, 0, image=bg_photo, anchor="nw")
        canvas.image = bg_photo  # Zachowaj referencję
except Exception as e:
    print(f"Błąd ładowania tła: {e}")
    # Próba załadowania alternatywnego tła
    try:
        bg_image = Image.open("graphics/background.jpg")
        resized_image = bg_image.resize((1600, 1000), Image.Resampling.LANCZOS)
        bg_photo = ImageTk.PhotoImage(resized_image)
        canvas = tk.Canvas(window, width=1600, height=1000)
        canvas.pack(fill="both", expand=True)
        bg_item = canvas.create_image(0, 0, image=bg_photo, anchor="nw")
        canvas.image = bg_photo
    except Exception as e:
        print(f"Błąd ładowania alternatywnego tła: {e}")

# --- Nagłówek z logo ---
header_frame = tk.Frame(window)
header_frame.configure(bg='#ffffff')  # Set white background
header_frame.place(relx=0.5, rely=0.02, relwidth=0.96, relheight=0.08, anchor="n")

# Create header content with white background
logo_img = load_logo()
header_content = tk.Frame(header_frame, bg='#ffffff')
header_content.pack(expand=True)

if logo_img:
    tk.Label(header_content, image=logo_img, bg='#ffffff').pack(side=tk.LEFT, padx=10)

tk.Label(
    header_content, 
    text="Osobisty Asystent AI", 
    font=('Arial', 24, 'bold'), 
    bg='#ffffff',
    fg='black'
).pack(side=tk.LEFT, padx=20)

# --- Główna ramka (main_frame) dla konwersacji (lewa strona) ---
main_frame = tk.Frame(window, bg="white")
main_frame.place(relx=0.25, rely=0.12, relwidth=0.48, relheight=0.85, anchor="n")

# --- Ramka notatek (notes_frame) po prawej ---
notes_frame = tk.Frame(window, bg="white")
notes_frame.place(relx=0.75, rely=0.12, relwidth=0.48, relheight=0.85, anchor="n")

# Kalendarz
cal_frame = tk.Frame(notes_frame, bg="white")
cal_frame.pack(fill=tk.X, pady=5)
cal = Calendar(cal_frame, selectmode='day', width=20, height=20)
# Ustaw dzisiejszą datę w kalendarzu
today = datetime.datetime.now()
cal.selection_set(today)  # Ustawienie aktualnej daty
cal.pack(pady=5)
cal.bind("<<CalendarSelected>>", update_calendar_notes)

def update_calendar_display_if_today():
    """Sprawdza czy wybrana data w kalendarzu to dzisiaj i odświeża widok jeśli tak"""
    selected_date = cal.get_date()  # format: "02/01/25"
    today = datetime.datetime.now().strftime("%m/%d/%y")
    if selected_date == today:
        update_calendar_notes()

# Wywołaj update_calendar_notes po ustawieniu daty
window.after(100, lambda: update_calendar_notes())

# Pole na notatki z wybranej daty (z suwakiem)
daily_frame = tk.Frame(notes_frame)
daily_frame.pack(fill=tk.X, expand=False, padx=5, pady=5)

daily_scroll = tk.Scrollbar(daily_frame)
daily_scroll.pack(side=tk.RIGHT, fill=tk.Y)

daily_text = tk.Text(daily_frame, font=('Arial', 14), bg="#e8e8e8", height=8, wrap=tk.WORD)
daily_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

daily_text.config(yscrollcommand=daily_scroll.set)
daily_scroll.config(command=daily_text.yview)

# Wywołanie funkcji przy starcie, aby pokazać dzisiejsze notatki
window.after(100, lambda: update_calendar_notes())

# Sekcja notatek według kategorii (z suwakiem)
notes_title_frame = tk.Frame(notes_frame, bg="white")
notes_title_frame.pack(pady=5)

# Ładowanie ikony przy1.png
try:
    notes_icon = Image.open("graphics/przy1.png")
    notes_icon = notes_icon.resize((24, 24), Image.Resampling.LANCZOS)
    notes_icon_photo = ImageTk.PhotoImage(notes_icon)
    notes_icon_label = tk.Label(notes_title_frame, image=notes_icon_photo, bg="white")
    notes_icon_label.image = notes_icon_photo  # Zachowanie referencji
    notes_icon_label.pack(side=tk.LEFT, padx=(0, 5))
except Exception as e:
    print(f"Błąd ładowania ikony przy1.png: {e}")

notes_title = tk.Label(notes_title_frame, text="Zapisane notatki", 
                      font=('Arial', 16, 'bold'), bg="white")
notes_title.pack(side=tk.LEFT)

notes_tile_frame = NoteTileFrame(notes_frame)
notes_tile_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

# --- Widgety w main_frame ---
text_frame = tk.Frame(main_frame)
text_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

text_scroll = tk.Scrollbar(text_frame)
text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

text_area = tk.Text(text_frame, height=12, width=80, font=('Arial', 16), bg="#ffffff", wrap=tk.WORD)
text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

text_area.config(yscrollcommand=text_scroll.set)
text_scroll.config(command=text_area.yview)
text_area.tag_configure("user", foreground="black", justify="center")
text_area.tag_configure("assistant", foreground="white", background="black", justify="center")
text_area.bind("<Button-3>", lambda event: context_menu.tk_popup(event.x_root, event.y_root))

entry = tk.Entry(main_frame, width=70, font=('Arial', 16), bg="#e0e0e0")
entry.pack(padx=10, pady=(0,10))
entry.bind("<Return>", on_enter)

button_frame = tk.Frame(main_frame, bg="white")
button_frame.pack(padx=10, pady=5)
send_button = tk.Button(button_frame, text="Wyślij", font=('Arial', 14), command=on_send)
send_button.grid(row=0, column=0, padx=5)
voice_button = tk.Button(button_frame, text="Słuchaj: OFF", font=('Arial', 14), 
                        command=lambda: voice_input(continuous=True))
voice_button.grid(row=0, column=1, padx=5)
speak_button = tk.Button(button_frame, text="Odtwórz", font=('Arial', 14), command=lambda: speak(last_response))
speak_button.grid(row=0, column=2, padx=5)
auto_read_button = tk.Button(button_frame, text="Auto czytaj: OFF", font=('Arial', 14), command=toggle_auto_read)
auto_read_button.grid(row=0, column=3, padx=5)
try:
    lupa_img = Image.open("graphics/lupa.png")
    lupa_img = lupa_img.resize((30, 30), Image.Resampling.LANCZOS)
    lupa_photo = ImageTk.PhotoImage(lupa_img)
    search_button = tk.Button(button_frame, image=lupa_photo, command=lambda: on_menu_action("!wyszukaj notatki"))
    search_button.grid(row=0, column=4, padx=5)
except Exception as e:
    print("Błąd ładowania ikony lupy:", e)

stop_button = tk.Button(button_frame, text="Przerwij", font=('Arial', 14), command=stop_generation, bg='#ff4444', fg='white')
stop_button.grid(row=0, column=5, padx=5)

status_label = tk.Label(main_frame, text="Gotowy", bd=1, relief=tk.SUNKEN, anchor=tk.W, font=('Arial', 12))
status_label.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)

# --- Widget na notatki dzisiejsze (z suwakiem) ---
today_frame = tk.Frame(main_frame)
today_frame.pack(padx=10, pady=(0,10), fill=tk.BOTH)

today_scroll = tk.Scrollbar(today_frame)
today_scroll.pack(side=tk.RIGHT, fill=tk.Y)

today_notes_text = tk.Text(today_frame, height=4, font=('Arial', 14), bg="#f7f7f7", wrap=tk.WORD)
today_notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

today_notes_text.config(yscrollcommand=today_scroll.set)
today_scroll.config(command=today_notes_text.yview)

# --- Funkcje pomocnicze dla menu ---
def show_about_window():
    """Pokazuje okno z informacją o programie"""
    about_win = tk.Toplevel(window)
    about_win.title("O programie")
    about_win.geometry("400x300")
    
    info_text = """
    Osobisty Asystent AI
    
    Program służy do zarządzania notatkami 
    z wykorzystaniem sztucznej inteligencji.
    
    Wersja: 1.0
    © 4 Wszelkie prawa zastrzeżone
    """
    
    label = tk.Label(about_win, text=info_text, font=('Arial', 12), justify=tk.LEFT, padx=20, pady=20)
    label.pack(expand=True)
    
    tk.Button(about_win, text="Zamknij", command=about_win.destroy).pack(pady=10)

def show_commands_window():
    """Pokazuje okno z dostępnymi komendami"""
    commands_win = tk.Toplevel(window)
    commands_win.title("Dostępne komendy")
    commands_win.geometry("600x700")
    
    commands_text = """
    Dostępne komendy:
    
    Notatki:
    !dodaj notatkę [kategoria] [treść] – Dodaje nową notatkę
    
    !edytuj notatkę - dwa możliwe formaty:
    1. !edytuj notatkę [kategoria] [stara treść] || [nowa treść]
    2. !edytuj notatkę [kategoria] zamień [stara treść] na [nowa treść]
    
    !usuń notatkę [kategoria] [treść] – Usuwa notatkę
    !wyszukaj notatki [słowo_kluczowe] – Wyszukuje notatki
    !pokaż notatki [kategoria] – Wyświetla notatki z kategorii
    !pokaż notatki – Wyświetla wszystkie notatki
    
    Kategorie:
    !stwórz kategorię [nazwa kategorii] – Tworzy kategorię
    !usuń kategorię [nazwa kategorii] – Usuwa kategorię
    !pokaż kategorie – Wyświetla listę kategorii
    
    Funkcje dodatkowe:
    !plan dnia – Generuje plan dnia
    !eksport notatek – Eksportuje notatki do pliku
    !import notatek – Importuje notatki z pliku
    !statystyki – Wyświetla statystyki notatek
    !kalendarz – Otwiera kalendarz
    """
    
    text_widget = tk.Text(commands_win, font=('Arial', 12), wrap=tk.WORD, padx=20, pady=20)
    text_widget.pack(fill=tk.BOTH, expand=True)
    text_widget.insert(tk.END, commands_text)
    text_widget.config(state=tk.DISABLED)
    
    tk.Button(commands_win, text="Zamknij", command=commands_win.destroy).pack(pady=10)

def show_charts_window():
    """Pokazuje okno z wykresami"""
    charts_win = tk.Toplevel(window)
    charts_win.title("Wykresy")
    charts_win.geometry("1200x800")
    
    # Inicjalizacja managera wykresów
    charts_manager = ChartsManager(cursor)
    
    # Utwórz zakładki
    notebook = ttk.Notebook(charts_win)
    notebook.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Zakładka z wykresem kołowym kategorii
    pie_tab = ttk.Frame(notebook)
    notebook.add(pie_tab, text='Kategorie')
    
    pie_chart = charts_manager.create_category_chart()
    if pie_chart:
        canvas = FigureCanvasTkAgg(pie_chart, pie_tab)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
    else:
        tk.Label(pie_tab, text="Brak danych do wyświetlenia").pack()
    
    # Zakładka z wykresem czasowym
    timeline_tab = ttk.Frame(notebook)
    notebook.add(timeline_tab, text='Oś czasu')
    
    timeline_chart = charts_manager.create_notes_timeline()
    if timeline_chart:
        canvas = FigureCanvasTkAgg(timeline_chart, timeline_tab)
        canvas.draw()
        canvas.get_tk_widget().pack(fill='both', expand=True)
    else:
        tk.Label(timeline_tab, text="Brak danych do wyświetlenia").pack()

# --- Menu główne ---
menu_bar = tk.Menu(window)
window.config(menu=menu_bar)

file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Eksport notatek", command=lambda: on_menu_action("!eksport notatek"))
file_menu.add_command(label="Import notatek", command=lambda: on_menu_action("!import notatek"))
file_menu.add_separator()
file_menu.add_command(label="Wyjście", command=window.quit)
menu_bar.add_cascade(label="Plik", menu=file_menu)

notes_menu = tk.Menu(menu_bar, tearoff=0)
notes_menu.add_command(label="Dodaj notatkę", command=lambda: entry.insert(tk.END, "!dodaj notatkę "))
notes_menu.add_command(label="Edytuj notatkę", command=lambda: entry.insert(tk.END, "!edytuj notatkę "))
notes_menu.add_command(label="Usuń notatkę", command=lambda: entry.insert(tk.END, "!usuń notatkę "))
notes_menu.add_command(label="Wyszukaj notatki", command=lambda: entry.insert(tk.END, "!wyszukaj notatki "))
menu_bar.add_cascade(label="Notatki", menu=notes_menu)

cat_menu = tk.Menu(menu_bar, tearoff=0)
cat_menu.add_command(label="Stwórz kategorię", command=lambda: entry.insert(tk.END, "!stwórz kategorię "))
cat_menu.add_command(label="Usuń kategorię", command=lambda: entry.insert(tk.END, "!usuń kategorię "))
cat_menu.add_command(label="Pokaż kategorie", command=lambda: on_menu_action("!pokaż kategorie"))
menu_bar.add_cascade(label="Kategorie", menu=cat_menu)

ust_menu = tk.Menu(menu_bar, tearoff=0)
ust_menu.add_command(label="Zmień hasło", command=lambda: on_menu_action("!zmień hasło"))
ust_menu.add_command(label="O programie", command=show_about_window)
ust_menu.add_command(label="Komendy", command=show_commands_window)
menu_bar.add_cascade(label="Ustawienia", menu=ust_menu)

extra_menu = tk.Menu(menu_bar, tearoff=0)
extra_menu.add_command(label="Plan dnia", command=lambda: on_menu_action("!plan dnia"))
extra_menu.add_command(label="Statystyki", command=lambda: on_menu_action("!statystyki"))
extra_menu.add_command(label="Kalendarz", command=lambda: on_menu_action("!kalendarz"))
extra_menu.add_separator()
extra_menu.add_command(label="Wykresy", command=show_charts_window)
menu_bar.add_cascade(label="Funkcje", menu=extra_menu)

# --- Menu kontekstowe ---
context_menu = tk.Menu(window, tearoff=0)
context_menu.add_command(label="Kopiuj", command=lambda: window.focus_get().event_generate("<<Copy>>"))
context_menu.add_command(label="Wklej", command=lambda: window.focus_get().event_generate("<<Paste>>"))

# Po utworzeniu głównego okna i wszystkich widgetów, przed window.mainloop():
# Dodaj początkowe załadowanie notatek
window.after(100, refresh_notes)  # Załaduj notatki przy starcie aplikacji

# Add global shutdown flag
shutdown_requested = False

# Modify on_closing function
def on_closing():
    """Bezpieczne zamykanie aplikacji"""
    global should_stop_listening, shutdown_requested
    
    try:
        # Set shutdown flags
        shutdown_requested = True
        should_stop_listening = True
        
        # Stop voice recognition
        if voice_thread and voice_thread.is_alive():
            print("Zatrzymywanie rozpoznawania mowy...")
            voice_thread.join(timeout=2)
            if voice_thread.is_alive():
                print("Nie można zatrzymać wątku rozpoznawania mowy")
        
        # Close database connection
        if conn:
            print("Zamykanie połączenia z bazą danych...")
            conn.commit()
            conn.close()
        
        # Destroy window
        print("Zamykanie okna głównego...")
        window.quit()
        window.destroy()
        
        # Force exit if needed
        print("Zamykanie aplikacji...")
        os._exit(0)
        
    except Exception as e:
        print(f"Błąd podczas zamykania: {e}")
        os._exit(1)

# Add signal handlers
def signal_handler(signum, frame):
    """Handle system signals"""
    print(f"\nOtrzymano sygnał {signum}. Zamykanie aplikacji...")
    window.after(0, on_closing)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
if hasattr(signal, 'SIGBREAK'):  # Windows Ctrl+Break
    signal.signal(signal.SIGBREAK, signal_handler)

# Update window protocol handler
window.protocol("WM_DELETE_WINDOW", on_closing)

window.mainloop()

def get_key():
    """Generuje klucz szyfrowania na podstawie stałej wartości"""
    return base64.urlsafe_b64encode(hashlib.sha256(b"ElizaAI2024").digest())

def create_secure_storage():
    """Tworzy ukryty folder do przechowywania danych wrażliwych"""
    secure_dir = os.path.join(os.path.expanduser("~"), ".eliza_secure")
    if not os.path.exists(secure_dir):
        os.makedirs(secure_dir)
        # Ustaw atrybut ukryty w Windows
        if os.name == 'nt':
            import subprocess
            subprocess.check_call(["attrib", "+H", secure_dir])
    return secure_dir

def save_password(password):
    """Zapisuje zaszyfrowane hasło"""
    try:
        secure_dir = create_secure_storage()
        password_file = os.path.join(secure_dir, ".auth")
        
        # Szyfrowanie hasła
        f = Fernet(get_key())
        encrypted_password = f.encrypt(password.encode())
        
        with open(password_file, "wb") as file:
            file.write(encrypted_password)
    except Exception as e:
        print(f"Błąd zapisywania hasła: {e}")

def load_password():
    """Odczytuje zaszyfrowane hasło"""
    try:
        secure_dir = create_secure_storage()
        password_file = os.path.join(secure_dir, ".auth")
        
        if not os.path.exists(password_file):
            # Przy pierwszym uruchomieniu zapisz domyślne hasło
            save_password("admin")
            return "admin"
            
        with open(password_file, "rb") as file:
            encrypted_password = file.read()
            
        # Odszyfrowanie hasła
        f = Fernet(get_key())
        decrypted_password = f.decrypt(encrypted_password)
        return decrypted_password.decode()
    except Exception as e:
        print(f"Błąd odczytywania hasła: {e}")
        return None

# Zmodyfikuj funkcję show_login
def show_login():
    """Pokazuje okno logowania i kończy program jeśli logowanie się nie powiedzie"""
    login_success = False
    
    def on_login_close():
        nonlocal login_success
        if not login_success:
            window.quit()
            sys.exit()
    
    login_win = tk.Toplevel()
    login_win.title("Logowanie")
    login_win.geometry("350x200")
    login_win.protocol("WM_DELETE_WINDOW", on_login_close)  # Obsługa zamknięcia okna
    
    tk.Label(login_win, text="Podaj hasło:", font=('Arial', 14)).pack(padx=10, pady=10)
    password_entry = tk.Entry(login_win, show="*", font=('Arial', 14))
    password_entry.pack(padx=10, pady=5)
    status = tk.Label(login_win, text="", font=('Arial', 12))
    status.pack(padx=10, pady=5)
    
    def check_password(event=None):
        nonlocal login_success
        current = load_password()
        if current and password_entry.get() == current:
            login_success = True
            login_win.destroy()
        else:
            status.config(text="Nieprawidłowe hasło!")
            password_entry.delete(0, tk.END)
    
    password_entry.bind("<Return>", check_password)
    tk.Button(login_win, text="Zaloguj", font=('Arial', 14), command=check_password).pack(pady=10)
    
    login_win.grab_set()
    login_win.wait_window()
    
    if not login_success:
        window.quit()
        sys.exit()

# Zmodyfikuj funkcję open_change_password_window
def open_change_password_window():
    change_win = tk.Toplevel(window)
    change_win.title("Zmiana hasła")
    change_win.geometry("400x250")
    
    tk.Label(change_win, text="Podaj stare hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    old_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    old_pass_entry.pack(padx=10, pady=5)
    
    tk.Label(change_win, text="Podaj nowe hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    new_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    new_pass_entry.pack(padx=10, pady=5)
    
    tk.Label(change_win, text="Potwierdź nowe hasło:", font=('Arial', 14)).pack(padx=10, pady=5)
    confirm_pass_entry = tk.Entry(change_win, show="*", font=('Arial', 14))
    confirm_pass_entry.pack(padx=10, pady=5)
    
    status_label_change = tk.Label(change_win, text="", font=('Arial', 12))
    status_label_change.pack(padx=10, pady=5)
    
    def change_password():
        current = load_password()
        if old_pass_entry.get() != current:
            status_label_change.config(text="Stare hasło niepoprawne!")
        elif new_pass_entry.get() != confirm_pass_entry.get():
            status_label_change.config(text="Nowe hasło i potwierdzenie nie zgadzają się!")
        else:
            save_password(new_pass_entry.get())
            status_label_change.config(text="Hasło zmienione pomyślnie!")
            change_win.after(2000, change_win.destroy)
            
    tk.Button(change_win, text="Zmień hasło", font=('Arial', 14), command=change_password).pack(pady=10)

# ...rest of the existing code...

def show_charts_window():
    """Pokazuje okno z wykresami"""
    charts_win = tk.Toplevel(window)
    charts_win.title("Wykresy")
    charts_win.geometry("1200x800")
    
    # Inicjalizacja managera wykresów
    charts_manager = ChartsManager(cursor)
    
    # Utwórz zakładki
    notebook = ttk.Notebook(charts_win)
    notebook.pack(fill='both', expand=True, padx=10, pady=10)
    
    # Zakładki
    pie_tab = ttk.Frame(notebook)
    timeline_tab = ttk.Frame(notebook)
    monthly_tab = ttk.Frame(notebook)
    
    notebook.add(pie_tab, text='Kategorie')
    notebook.add(timeline_tab, text='Oś czasu')
    notebook.add(monthly_tab, text='Miesięczne')
    
    def refresh_charts():
        for widget in pie_tab.winfo_children():
            widget.destroy()
        for widget in timeline_tab.winfo_children():
            widget.destroy()
        for widget in monthly_tab.winfo_children():
            widget.destroy()
            
        # Wykres kołowy
        pie_chart = charts_manager.create_category_chart()
        if pie_chart:
            canvas = FigureCanvasTkAgg(pie_chart, pie_tab)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
        else:
            tk.Label(pie_tab, text="Brak danych do wyświetlenia wykresów.\nDodaj notatki aby zobaczyć statystyki.",
                    font=('Arial', 12)).pack(pady=20)
        
        # Wykres czasowy
        timeline_chart = charts_manager.create_notes_timeline()
        if timeline_chart:
            canvas = FigureCanvasTkAgg(timeline_chart, timeline_tab)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
        else:
            tk.Label(timeline_tab, text="Brak danych do wyświetlenia wykresów.\nDodaj notatki aby zobaczyć statystyki.",
                    font=('Arial', 12)).pack(pady=20)
        
        # Wykres miesięczny
        monthly_chart = charts_manager.create_notes_by_month_chart()
        if monthly_chart:
            canvas = FigureCanvasTkAgg(monthly_chart, monthly_tab)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
        else:
            tk.Label(monthly_tab, text="Brak danych do wyświetlenia wykresów.\nDodaj notatki aby zobaczyć statystyki.",
                    font=('Arial', 12)).pack(pady=20)
    
    # Przycisk odświeżania
    refresh_btn = tk.Button(charts_win, text="Odśwież wykresy", command=refresh_charts,
                           font=('Arial', 10, 'bold'))
    refresh_btn.pack(pady=5)
    
    # Początkowe załadowanie wykresów
    refresh_charts()


# Add startup configuration functions
def set_startup(enable):
    """Ustawia lub usuwa autostart aplikacji"""
    key = winreg.HKEY_CURRENT_USER
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "AIAssistant"
    app_path = os.path.abspath(__file__)

    try:
        reg = winreg.OpenKey(key, key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(reg, app_name, 0, winreg.REG_SZ, f'"{app_path}"')
            print(f"Dodano autostart: {app_path}")
        else:
            try:
                winreg.DeleteValue(reg, app_name)
                print("Usunięto autostart")
            except FileNotFoundError:
                print("Autostart nie był ustawiony")
        winreg.CloseKey(reg)
    except Exception as e:
        print(f"Błąd ustawiania autostartu: {e}")

def check_startup_enabled():
    """Sprawdza czy autostart jest włączony"""
    try:
        key = winreg.HKEY_CURRENT_USER
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        reg = winreg.OpenKey(key, key_path, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(reg, "AIAssistant")
            winreg.CloseKey(reg)
            return True
        except FileNotFoundError:
            winreg.CloseKey(reg)
            return False
    except Exception as e:
        print(f"Błąd sprawdzania autostartu: {e}")
        return False

# Add startup variable before creating menus
startup_var = tk.BooleanVar(value=check_startup_enabled())

# Modify menu creation to include autostart options
def create_menus():
    # ...existing menu creation code...

    # Modify settings menu
    ust_menu = tk.Menu(menu_bar, tearoff=0)
    ust_menu.add_checkbutton(
        label="Uruchamiaj z systemem",
        variable=startup_var,
        command=lambda: set_startup(startup_var.get())
    )
    ust_menu.add_command(label="Zmień hasło", command=lambda: on_menu_action("!zmień hasło"))
    ust_menu.add_command(label="O programie", command=show_about_window)
    ust_menu.add_command(label="Komendy", command=show_commands_window)
    menu_bar.add_cascade(label="Ustawienia", menu=ust_menu)

# Modify window closing handler
def on_closing():
    """Bezpieczne zamykanie aplikacji"""
    global should_stop_listening
    try:
        # Stop voice listening if active
        should_stop_listening = True
        if voice_thread and voice_thread.is_alive():
            voice_thread.join(timeout=1)
            
        # Close database connection
        if conn:
            conn.close()
            
        # Destroy window
        window.quit()
        window.destroy()
    except Exception as e:
        print(f"Błąd podczas zamykania: {e}")
        sys.exit(1)

# Replace existing window protocol handler
window.protocol("WM_DELETE_WINDOW", on_closing)