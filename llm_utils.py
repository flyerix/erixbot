import os
import requests
import logging

OPENAI_API_KEY = os.environ.get("OPEN_API_KEY")
LLM_ENDPOINT = os.environ.get("LLM_ENDPOINT")  # opzionale, per LLM locale
logger = logging.getLogger(__name__)

def llm_query(prompt, system=None, temperature=0.3, max_tokens=300):
    """
    Esegue una query a OpenAI GPT (o LLM endpoint locale se impostato).
    """
    if LLM_ENDPOINT:
        # Custom local LLM endpoint
        try:
            resp = requests.post(LLM_ENDPOINT, json={"prompt": prompt, "system": system})
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as e:
            logger.error(f"LLM local error: {e}")
            return ""
    elif OPENAI_API_KEY:
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": system or "Sei un assistente Telegram per ticket di supporto."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            resp = requests.post(url, headers=headers, json=data)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return ""
    else:
        logger.error("Nessuna API KEY OpenAI o LLM endpoint configurato.")
        return ""

def classify_ticket(text):
    """
    Usa LLM per classificare il tipo di ticket e suggerire priorità.
    """
    prompt = f"Classifica questa richiesta utente in una delle categorie: 'assistenza', 'content_request', 'renewal', 'new_line'. Suggerisci anche una priorità (alta, media, bassa). Testo: {text}"
    resp = llm_query(prompt)
    return resp

def suggest_resolution(text):
    """
    Suggerisce una risposta/risoluzione automatica usando LLM.
    """
    prompt = f"Fornisci una breve risposta di assistenza al seguente ticket utente: {text}. Se possibile, suggerisci anche eventuali step o soluzioni."
    resp = llm_query(prompt)
    return resp

def faq_response(question):
    """
    Risponde automaticamente alle domande frequenti.
    """
    prompt = f"Rispondi come un helpdesk Telegram alle seguenti domanda frequente:\n{question}\nRisposta:"
    resp = llm_query(prompt)
    return resp

def summarize_ticket_history(tickets):
    """
    Crea una sintesi della storia ticket e incidenti per report.
    """
    prompt = f"Genera un report testuale su questi ticket e incidenti:\n{tickets}\nRisposta:"
    resp = llm_query(prompt, temperature=0.1)
    return resp
