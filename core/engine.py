import json
import random
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()

BASE_DIR        = Path(__file__).resolve().parent.parent
EMBEDDINGS_PATH = BASE_DIR / "data" / "acervo_freire.json"
_biblioteca     = None
_vectorizer     = None
_corpus_matrix  = None

# ============================================
# Regras Freire — base do prompt
# ============================================
REGRAS_FREIRE = (
    "### REGRA ABSOLUTA — EXECUTE PRIMEIRO ###\n"
    "Para QUALQUER nome próprio de pessoa famosa, empresa, marca, "
    "produto, tecnologia, esporte ou política que NÃO seja Paulo Freire, "
    "responda ÚNICA e EXCLUSIVAMENTE:\n"
    "BLOQUEADO\n"
    "NÃO adicione mais nenhuma palavra. NÃO explique. NÃO filosofe.\n\n"
    "### REGRAS FREIRE ###\n"
    "1. Comece SEMPRE com 'Companheiro,' ou 'Companheira,' — nunca com 'Como ensina', 'Segundo' ou 'De acordo'.\n"
    "2. Use APENAS o CONTEXTO abaixo. NUNCA invente. NUNCA crie frases atribuídas a Freire que não estejam no contexto.\n"
    "3. OBRIGATÓRIO: Mencione a obra de forma natural. "
    "Exemplos: 'Na Pedagogia do Oprimido, Freire nos lembra...', "
    "'Como escreve Freire em Pedagogia do Oprimido...', "
    "'Freire, em sua obra fundamental, aponta que...'. "
    "PROIBIDO inventar citações ou referências.\n"
    "4. NUNCA mencione 'contexto', 'fonte' ou mecânica interna.\n"
    "5. Se CONTEXTO VAZIO → BLOQUEADO\n"
    "6. MÁXIMO 5 FRASES. Conte as frases. Se passar de 5, corte. Sem exceções.\n"
    "7. Linguagem acessível, dialógica e comprometida — como Freire escrevia.\n\n"
)

# ============================================
# Estilos por IA
# ============================================
ESTILOS_IA = {
    "Gemini":    "### SEU ESTILO ###\nSeja criativo e instigante. Use imagens do cotidiano popular.\n\n",
    "Groq":      "### SEU ESTILO ###\nSeja direto e combativo. Uma ideia central, sem rodeios.\n\n",
    "Cerebras":  "### SEU ESTILO ###\nSeja claro e acolhedor. Linguagem simples e próxima.\n\n",
    "SambaNova": "### SEU ESTILO ###\nSeja reflexivo e pausado. Convide à consciência crítica.\n\n",
}


# ============================================
# Carregar Biblioteca
# ============================================
def carregar_biblioteca():
    global _biblioteca, _vectorizer, _corpus_matrix

    if not EMBEDDINGS_PATH.exists():
        print(f"⚠️ Arquivo {EMBEDDINGS_PATH} não encontrado!")
        return []

    with open(EMBEDDINGS_PATH, "r", encoding="utf-8") as f:
        _biblioteca = json.load(f)

    textos         = [item["texto"] for item in _biblioteca]
    _vectorizer    = TfidfVectorizer(max_features=8000)
    _corpus_matrix = _vectorizer.fit_transform(textos)

    print(f"✅ Biblioteca carregada: {len(_biblioteca)} trechos de Paulo Freire.")
    return _biblioteca


# ============================================
# Buscar Contexto
# ============================================
def buscar_contexto(pergunta: str, biblioteca, top_k: int = 3,
                    threshold: float = 0.05) -> str:
    if not _vectorizer or _corpus_matrix is None:
        return "Nenhum ensinamento encontrado."

    vetor       = _vectorizer.transform([pergunta])
    scores      = cosine_similarity(vetor, _corpus_matrix).flatten()
    indices_top = np.argsort(scores)[-top_k:][::-1]

    trechos = []
    for i in indices_top:
        if scores[i] < threshold:
            continue
        item  = biblioteca[i]
        livro = item.get("fonte", "Pedagogia do Oprimido")
        trechos.append(f"[FONTE: Paulo Freire — '{livro}']\n{item['texto']}")

    if not trechos:
        return "VAZIO"
    return "\n\n---\n\n".join(trechos)


# ============================================
# Montar Prompt
# ============================================
def montar_prompt(pergunta: str, contexto: str) -> list:
    contexto_final = (
        "VAZIO"
        if not contexto or "Nenhum ensinamento encontrado" in contexto
        else contexto
    )

    system_prompt = (
        "Você é Freire, um assistente que fala com a voz e o pensamento de Paulo Freire.\n"
        "Seu compromisso é com a conscientização, o diálogo e a libertação dos oprimidos.\n\n"
        + REGRAS_FREIRE
        + f"### CONTEXTO ###\n{contexto_final}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": pergunta}
    ]
