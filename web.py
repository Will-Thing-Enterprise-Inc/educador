import sys
import os
import random
import json
import base64
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

try:
    from core.ai_provider import FreeAIProvider
    from core.engine import carregar_biblioteca, buscar_contexto, montar_prompt, ESTILOS_IA  # noqa
except ImportError as e:
    print(f"❌ Erro de importação: {e}. Verifique a pasta 'core'.")
    sys.exit(1)


RATE_LIMIT = 10        # máx requisições
JANELA_SEG = 60        # por minuto

_contadores: dict = defaultdict(list)

def checar_rate_limit(ip: str) -> bool:
    agora = time.time()
    historico = _contadores[ip]
    # Remove entradas antigas
    _contadores[ip] = [t for t in historico if agora - t < JANELA_SEG]
    if len(_contadores[ip]) >= RATE_LIMIT:
        return False
    _contadores[ip].append(agora)
    return True


PADROES_INJECTION = [
    r"###\s*\w+",
    r"REGRAS_FREIRE",
    r"system\s*prompt",
    r"ignore\s+(previous|all|above)",
    r"você (agora|deve|é|está)",
    r"act as",
    r"jailbreak",
    r"esquece\s+(tudo|as regras|as instruções)",
    r"a partir de agora",
    r"finja\s+que",
    r"novo\s+(papel|personagem|modo)",
    r"sem\s+(restrições|limites|regras)",
    r"prompt\s*(original|do sistema|interno)",
    r"repita\s+as\s+(regras|instruções)",
    r"ignor\w*\s+(as instruções|as regras|tudo|acima)", 
    r"você pode",                                             
]

MARCADORES_BLOQUEIO = [
    "BLOQUEADO", "VAZIO",
    "não tenho elementos",      # fallback do próprio prompt
    "ERRO_SISTEMA"                 # resposta de erro
]

def is_bloqueado(texto: str) -> bool:
    t = texto.upper()
    return any(m.upper() in t for m in MARCADORES_BLOQUEIO)


def sanitizar_pergunta(texto: str) -> str | None:
    texto = texto.strip()
    
    if len(texto) > 400:
        return None  # muito longo — rejeitar
    
    for padrao in PADROES_INJECTION:
        if re.search(padrao, texto, re.IGNORECASE):
            return None
    
    return texto

# ============================================
# Inicialização
# ============================================
app = FastAPI()

ai_provider      = FreeAIProvider()
biblioteca_freire = carregar_biblioteca()

conversation_memory = {}


def resposta_bloqueio() -> str:
    frases = [
        "Companheiro, este não é o caminho do diálogo que nos liberta.",
        "Companheira, o verdadeiro tema gerador nasce da existência concreta do povo.",
        "Companheiro, Freire nos convida a outro horizonte — o da consciência crítica.",
        "Companheira, a palavra autêntica transforma o mundo. Esta, não é ela.",
        "Companheiro, pronunciar o mundo exige compromisso com os oprimidos.",
    ]
    return random.choice(frases)


def limpar_resposta(texto: str) -> str:
    return texto.replace("(pausa)", "").lstrip("#").strip()


# ============================================
# Avatar
# ============================================
AVATAR_B64 = ""
avatar_path = os.path.join(BASE_DIR, "static", "img", "avatar.png")
if os.path.exists(avatar_path):
    with open(avatar_path, "rb") as img_file:
        AVATAR_B64 = f"data:image/png;base64,{base64.b64encode(img_file.read()).decode()}"

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


# ============================================
# Textos da Interface
# ============================================
DESPEDIDA_JS = [
    "Que o diálogo continue em sua caminhada.",
    "Ninguém liberta ninguém — mas podemos nos libertar juntos.",
    "Vá e pronuncie o mundo.",
]

AGUARDANDO_JS = [
    "Freire reflete...",
    "A consciência se forma...",
    "O diálogo se aprofunda...",
    "A palavra se prepara...",
    "O pensamento crítico emerge...",
    "Freire escuta o mundo...",
    "A práxis se organiza...",
    "A consciência crítica desperta...",
    "O oprimido toma a palavra...",
    "A educação se faz liberdade...",
]

HTML_PAGE = f"""
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paulo Freire · Pedagogia do Oprimido</title>
    <link rel="icon" type="image/x-icon" href="/static/img/favicon.ico">
    <link rel="stylesheet" href="/static/style.css?v=2">
</head>
<body>
    <div class="container">

        <div class="header-card">
            <div class="header-info">
                <h1>Paulo Freire</h1>
                <div class="sub">pedagogia do oprimido</div>
            </div>
            {"<div class='header-avatar'><img src='" + AVATAR_B64 + "' alt='Paulo Freire'></div>" if AVATAR_B64 else ""}
        </div>

        <div class="divider-stripe"></div>

        <div class="body-pad">

            <div class="livro-select-container">


            <div class="input-container">
                <input type="text" id="pergunta" placeholder="Dialogue com Freire..." autofocus autocomplete="off" spellcheck="false">
                <button id="btn-mic" title="Falar">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
                        <line x1="12" y1="19" x2="12" y2="23"/>
                        <line x1="8" y1="23" x2="16" y2="23"/>
                    </svg>
                </button>
                <button id="btn-enviar" onclick="fazerPergunta()">&#10148;</button>
            </div>
                <select id="livro-select">
                    <option value="todos">Todos os livros </option>
                    <option value="A África Ensinando a Gente">A África Ensinando a Gente</option>
                    <option value="A Importância do Ato de Ler">A Importância do Ato de Ler</option>
                    <option value="À Sombra Dessa Mangueira">À Sombra Dessa Mangueira</option>
                    <option value="Ação Cultural para a Liberdade">Ação Cultural para a Liberdade</option>
                    <option value="Alfabetização - Leitura do Mundo, Leitura da Palavra">Alfabetização - Leitura do Mundo, Leitura da Palavra</option>
                    <option value="Aprendendo com a Própria História">Aprendendo com a Própria História</option>
                    <option value="Cartas a Cristina">Cartas a Cristina</option>
                    <option value="Cartas à Guiné-Bissau">Cartas à Guiné-Bissau</option>
                    <option value="Conscientização">Conscientização</option>
                    <option value="Dialogando com a Própria História">Dialogando com a Própria História</option>
                    <option value="Educação como Prática da Liberdade">Educação como Prática da Liberdade</option>
                    <option value="Educação e Mudança">Educação e Mudança</option>
                    <option value="Educar com a Mídia">Educar com a Mídia</option>
                    <option value="Extensão ou Comunicação?">Extensão ou Comunicação?</option>
                    <option value="Lições de Casa">Lições de Casa</option>
                    <option value="Medo e Ousadia - O Cotidiano do Professor">Medo e Ousadia - O Cotidiano do Professor</option>
                    <option value="Medo e Ousadia">Medo e Ousadia</option>
                    <option value="Partir da Infância">Partir da Infância</option>
                    <option value="Pedagogia da Autonomia">Pedagogia da Autonomia</option>
                    <option value="Pedagogia da Esperança">Pedagogia da Esperança</option>
                    <option value="Pedagogia da Indignação">Pedagogia da Indignação</option>
                    <option value="Pedagogia do Oprimido">Pedagogia do Oprimido</option>
                    <option value="Política e Educação">Política e Educação</option>
                    <option value="Por Uma Pedagogia da Pergunta">Por Uma Pedagogia da Pergunta</option>
                    <option value="Professora Sim, Tia Não">Professora Sim, Tia Não</option>
                </select>

            </div>

            <div class="resposta" id="resposta"><em>A palavra verdadeira transforma o mundo...</em></div>
        </div>

        <footer class="footer">
            <p class="gassho-quote">«O diálogo é este encontro dos homens, mediatizados pelo mundo, para pronunciá-lo,<br>não se esgotando, portanto, na relação eu-tu.»<br><strong>— Paulo Freire</strong></p>
            <p style="margin-top:12px; font-size:11px; letter-spacing:0.08em;">
                <a href="/aviso-legal/" style="color:#a07060; text-decoration:none;">Aviso Legal</a>
                &nbsp;·&nbsp;
                <a href="/copyright/" style="color:#a07060; text-decoration:none;">Copyright</a>
            </p>
        </footer>

    </div>
    <script>
        window.DESPEDIDA_JS = {json.dumps(DESPEDIDA_JS)};
        window.AGUARDANDO_JS = {json.dumps(AGUARDANDO_JS)};
    </script>
    <script src="/static/script.js"></script>
</body>
</html>
"""


# ============================================
# Rotas
# ============================================
@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTML_PAGE


@app.head("/")
async def head_index():
    return Response(status_code=200)


@app.get("/aviso-legal/", response_class=HTMLResponse)
async def get_aviso_legal():
    path = os.path.join(BASE_DIR, "static", "legal", "aviso-legal.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


@app.get("/copyright/", response_class=HTMLResponse)
async def get_copyright():
    path = os.path.join(BASE_DIR, "static", "legal", "copyright.html")
    with open(path, encoding="utf-8") as f:
        return f.read()


@app.post("/ask")
async def ask(request: Request):
    ip = request.client.host
    if not checar_rate_limit(ip):
        return JSONResponse(
            {"resposta": "Companheiro, o diálogo precisa de pausa para reflexão."},
            status_code=429
        )    
    try:
        data     = await request.json()
        pergunta_raw = data.get("pergunta", "").strip()
        livro        = data.get("livro", "todos").strip() 
        pergunta = sanitizar_pergunta(pergunta_raw)

        if not pergunta:
            return JSONResponse({"resposta": resposta_bloqueio()})

        if pergunta.lower() in ["sair", "exit", "tchau", "obrigado", "ok", "quit"]:
            return JSONResponse({"resposta": random.choice(DESPEDIDA_JS)})

        contexto  = buscar_contexto(pergunta, biblioteca_freire, livro=livro)  
        mensagens = montar_prompt(pergunta, contexto)
        resposta_raw, ia_nome = ai_provider.chat(mensagens)
        resposta_limpa = limpar_resposta(resposta_raw)
        # print("-" * 50)        
        # print("LIVRO:", livro)
        # print("PERGUNTA:", pergunta)
        # print("CONTEXTO:", contexto[:50])
        # print("RESPOSTA BRUTA:\n", resposta_raw)
        # print("RESPOSTA LIMPA:\n", resposta_limpa)       
        # print("-" * 50)
        

        if is_bloqueado(resposta_limpa):
            return JSONResponse({"resposta": resposta_bloqueio()})

        resposta_exibida = f"{resposta_limpa}\n\n— {ia_nome}"
        return JSONResponse({"resposta": resposta_exibida})

    except Exception as e:
        print(f"❌ Erro: {e}")
        return JSONResponse({"resposta": resposta_bloqueio()}, status_code=500)
