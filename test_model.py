import ollama

client = ollama.Client()

# System Prompt (instrukcja dla modelu)
system_prompt = """
Jesteś pomocnym asystentem AI. Odpowiadaj zwięźle i na temat, w języku polskim. 
Jeśli nie znasz odpowiedzi, napisz, że nie wiesz.
"""

def generate_response(prompt, temperature=0.7):
    messages = [
        {
            'role': 'system',
            'content': system_prompt,  # Dodajemy system prompt
        },
        {
            'role': 'user',
            'content': prompt,
        },
    ]
    response = client.chat(model='llama3.2:3b', messages=messages, options={'temperature': temperature}) #Dodajemy temperature
    return response['message']['content']

# Pętla do interakcji
while True:
    user_input = input("Ty: ")
    if user_input.lower() == "koniec":
        break

    response = generate_response(user_input)
    print(f"Asystent: {response}")