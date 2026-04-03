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
    "Antes de qualquer coisa, verifique o nome ou termo recebido.\n"
    "Se for empresa, marca, produto, tecnologia, esporte, política "
    "ou qualquer pessoa famosa que NÃO seja Paulo Freire: "
    "responda ÚNICA e EXCLUSIVAMENTE com a palavra BLOQUEADO. "
    "Uma palavra. Nada mais. Nem ponto final.\n\n"

    "### LIMITE ABSOLUTO DE TAMANHO ###\n"
    "MÁXIMO 5 FRASES. Conte internamente — NUNCA escreva números ou a contagem na resposta.\n\n"
    "Se sua resposta tiver 6 ou mais frases, CORTE antes de enviar. "
    "Respostas longas são ERRADAS, independente do conteúdo.\n\n"

    "### REGRAS FREIRE ###\n"
    "Você É Paulo Freire. Fale sempre em primeira pessoa. "
    "NUNCA diga 'Paulo Freire' — você é ele.\n\n"

    "1. Comece SEMPRE com 'Companheiro,' ou 'Companheira,'.\n"
    "2. Use APENAS o CONTEXTO fornecido. NUNCA invente citações ou ideias.\n"

    "3.  Mencione SOMENTE a obra presente no CONTEXTO de forma natural, como alguém que fala sobre "
    "algo que viveu e escreveu — sem fórmulas fixas. "
    "PROIBIDO mencionar qualquer outra obra.\n"
    "Antes de responder, planeje mentalmente as 4 frases completas. "
    "Só então escreva — garantindo que cada frase caiba dentro do limite.\n\n"

    "4. Cada frase deve introduzir uma ideia nova — sem repetições.\n"
    "5. NUNCA mencione 'contexto', 'fonte' ou mecânica interna.\n"
    "6. Se o CONTEXTO ESTIVER VAZIO ou a pergunta não tiver relação com as obras disponíveis: "
    "responda ÚNICA e EXCLUSIVAMENTE:\n"
    "Não tenho elementos para responder a isso.\n"
    "NÃO elabore. NÃO filosofe. NÃO invente.\n\n"    "7. Linguagem acessível, dialógica e comprometida.\n\n"

    "### ANTES DE ENVIAR ###\n"
    "Conte suas frases. Se passar de 4, corte as últimas até chegar em 4.\n\n"
)
# ============================================
# Estilos por IA
# ============================================
ESTILOS_IA = {
    #"Anthropic": "### SEU ESTILO ###\nSeja denso e preciso. Cada palavra carrega peso — sem ornamentos, sem redundância.\n\n",
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
