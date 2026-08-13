#
# /educador/web.py
#

import sys
import os
import random
import json
import base64
import re
import time
import psutil

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from collections import defaultdict
from core.contador import incrementar, total

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


# ============================================
# Rate Limit
# ============================================
RATE_LIMIT = 10
JANELA_SEG = 60
_contadores: dict = defaultdict(list)


# ============================================
# Sanitização
# ============================================
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
    "não tenho elementos",
    "ERRO_SISTEMA",
]

# ============================================
# Lista de Livros
# ============================================
PERFIL_NOME = "Educador Paulo Freire"

LIVROS = [
    "A África Ensinando a Gente",
    "A Importância do Ato de Ler",
    "À Sombra Dessa Mangueira",
    "Ação Cultural para a Liberdade",
    "Alfabetização - Leitura do Mundo, Leitura da Palavra",
    "Aprendendo com a Própria História",
    "Cartas a Cristina",
    "Cartas à Guiné-Bissau",
    "Conscientização",
    "Dialogando com a Própria História",
    "Educação como Prática da Liberdade",
    "Educação e Mudança",
    "Educar com a Mídia",
    "Extensão ou Comunicação?",
    "Lições de Casa",
    "Medo e Ousadia - O Cotidiano do Professor",
    "Medo e Ousadia",
    "Partir da Infância",
    "Pedagogia da Autonomia",
    "Pedagogia da Esperança",
    "Pedagogia da Indignação",
    "Pedagogia do Oprimido",
    "Política e Educação",
    "Por Uma Pedagogia da Pergunta",
    "Professora Sim, Tia Não",
]

livros_options = "\n".join(
    f'<option value="{l}">{l}</option>' for l in LIVROS
)

# Conjunto para validação rápida
LIVROS_VALIDOS_SET = set(l.lower() for l in LIVROS)

JARDIM_NOME = os.getenv("JARDIM_NOME", "educador")
NOME_CONTADOR_VISITAS   = f"visitas_{JARDIM_NOME}"    # → "visitas_buko"
NOME_CONTADOR_PERGUNTAS = f"perguntas_{JARDIM_NOME}"  # → "perguntas_buko"

# Filtro de bots/monitores — mesma disciplina do Chizu
ROBOTS = [
    "uptimerobot", "pingdom", "newrelic", "googlebot", "bingbot", "yandex",
    "facebookexternalhit", "bot", "crawler", "crawl", "spider", "scan",
    "monitor", "check", "headless", "phantom", "curl", "wget",
    "python-requests", "go-http-client", "libwww", "scrapy", "axios",
]


#--------------------------------------------
def _e_bot_monitor(request: Request) -> bool:
    """Filtra bots e monitores — não são visitas reais."""
    ua = request.headers.get("user-agent", "").strip().lower()
    if not ua or "mozilla" not in ua:
        return True
    if any(bot in ua for bot in ROBOTS):
        return True
    return False

#------------------------------------------
def checar_rate_limit(ip: str) -> bool:
    agora = time.time()
    _contadores[ip] = [t for t in _contadores[ip] if agora - t < JANELA_SEG]
    if len(_contadores[ip]) >= RATE_LIMIT:
        return False
    _contadores[ip].append(agora)
    return True

#------------------------------------------
def is_bloqueado(texto: str) -> bool:
    t = texto.upper()
    return any(m.upper() in t for m in MARCADORES_BLOQUEIO)

#------------------------------------------
def sanitizar_pergunta(texto: str) -> str | None:
    texto = texto.strip()
    if len(texto) > 400:
        return None
    for padrao in PADROES_INJECTION:
        if re.search(padrao, texto, re.IGNORECASE):
            return None
    return texto

#--------------------------------------------
def is_local(request: Request) -> bool:
    """Reconhece o IP real por trás de proxy/Cloudflare antes de decidir se é local."""
    ip = request.headers.get("cf-connecting-ip")
    if not ip:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host
    return (
        ip in ("127.0.0.1", "::1") or
        ip.startswith("192.168.") or
        ip == "177.104.74.30"
    )



# ============================================
# Inicialização
# ============================================
app = FastAPI()

ai_provider       = FreeAIProvider()
biblioteca_freire = carregar_biblioteca()

# Memória temporária em RAM — por sessão
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
    "Educador reflete...",
    "A consciência se forma...",
    "O diálogo se aprofunda...",
    "A palavra se prepara...",
    "O pensamento crítico emerge...",
    "Educador escuta o mundo...",
    "A práxis se organiza...",
    "A consciência crítica desperta...",
    "O oprimido toma a palavra...",
    "A educação se faz liberdade...",
    "O tema gerador surge...",
    "A leitura do mundo começa...",
    "A conscientização avança...",
    "O diálogo transforma...",
    "A palavra verdadeira ressoa...",
]

HTML_PAGE = f"""
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Educador IA · Pedagogia do Oprimido</title>
    <link rel="icon" type="image/x-icon" href="/static/img/favicon.ico">
    <link rel="stylesheet" href="/static/style.css?v=2">
</head>
<body>
    <div class="container">

        <div class="header-card">
            <div class="header-info">
                <h1>Educador IA</h1>
                <div class="sub">pedagogia do oprimido</div>
            </div>
            {"<div class='header-avatar'><img src='" + AVATAR_B64 + "' alt='Educador ia'></div>" if AVATAR_B64 else ""}
        </div>

        <div class="divider-stripe"></div>

        <div class="body-pad">

            <div class="livro-select-container">

            <div class="input-container">
                <input type="text" id="pergunta" placeholder="Dialogue com Educador..." autofocus autocomplete="off" spellcheck="false" maxlength="400">
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

                <div class="obra-wrap">
                    <select id="livro-select">
                        <option value="todos">Todos os livros</option>
                        {livros_options}
                    </select>
                </div>

            </div>

            <div class="resposta" id="resposta"><em>A palavra verdadeira transforma o mundo...</em></div>
        </div>


        <footer class="footer">
            <p class="gassho-quote">«Quando a educação não é libertadora, o sonho do oprimido é ser o opressor» <br><strong>(Paulo Freire).</strong></p>
            <p style="margin-top:12px; font-size:11px; letter-spacing:0.08em;">
            <a href="/aviso-legal/" style="color:#a07060; text-decoration:none;">Aviso Legal</a>
            &nbsp;·&nbsp;
            <a href="/copyright/" style="color:#a07060; text-decoration:none;">Copyright</a>
            &nbsp;·&nbsp;
            <a href="mailto:contato@willthing.ia.br" style="color:#a07060; text-decoration:none;">Contato</a>
            </p>
            <p style="margin-top:8px; font-size:11px; letter-spacing:0.08em; color:#a07060;">
                <span id="contador-visitas">…</span> companheiros já passaram por este jardim e <span id="contador-perguntas">…</span> perguntas foram feitas.
            </p>
        </footer>

    </div>
    <script>
        window.DESPEDIDA_JS = {json.dumps(DESPEDIDA_JS)};
        window.AGUARDANDO_JS = {json.dumps(AGUARDANDO_JS)};
    </script>
    <script src="/static/script.js?v=1"></script>
</body>        
</html>
"""


# ============================================
# Rotas
# ============================================
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    if not _e_bot_monitor(request):
        incrementar(NOME_CONTADOR_VISITAS)
    return HTML_PAGE


@app.head("/")
async def head_index():
    return Response(status_code=200)


@app.get("/contador")
async def get_contador():
    return JSONResponse({
        "jardim": JARDIM_NOME,
        "visitas": total(NOME_CONTADOR_VISITAS),
        "perguntas": total(NOME_CONTADOR_PERGUNTAS),
    })

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
    start_time = time.time()
    DEBUG = is_local(request)

    ip = request.client.host
    if not checar_rate_limit(ip):
        return JSONResponse(
            {"resposta": "Companheiro, o diálogo precisa de pausa para reflexão."},
            status_code=429
        )

    try:
        data = await request.json()
        pergunta_raw = data.get("pergunta", "").strip()
        livro = data.get("livro", "todos").strip()
        pergunta = sanitizar_pergunta(pergunta_raw)

        if not pergunta:
            return JSONResponse({"resposta": resposta_bloqueio()})

        if pergunta.lower() in ["sair", "exit", "tchau", "obrigado", "ok", "quit", "bye", "thanks"]:
            return JSONResponse({"resposta": random.choice(DESPEDIDA_JS)})

        session_id = data.get("session_id", ip)
        historico_usuario = conversation_memory.get(session_id, [])

        provider_nome, provider_cfg = ai_provider.sortear_provider()
        top_k = provider_cfg.get("top_k", 5)

        t0_busca = time.time()

        # ========== BUSCA CONTEXTO ==========
        livro_validado = livro if livro.lower() in LIVROS_VALIDOS_SET else "todos"
        contexto = buscar_contexto(pergunta, biblioteca_freire, top_k=top_k, livro=livro_validado)
        
        # ========== EXTRAI OBRAS USADAS (IGUAL BUKO) ==========
        fontes = re.findall(r"\[OBRA: '(.+?)'\]", contexto or "")
        fontes_unicas = list(dict.fromkeys(
            f.split(" · ")[0].strip() for f in fontes
            if f.split(" · ")[0].strip().lower() in LIVROS_VALIDOS_SET
        ))
        obra_usada = " · ".join(fontes_unicas) if fontes_unicas else ""

        tempo_busca = time.time() - t0_busca

        mensagens = montar_prompt(pergunta, contexto)

        if historico_usuario:
            msgs_historico = []
            for troca in historico_usuario[-3:]:
                msgs_historico.append({"role": "user", "content": troca["pergunta"]})
                msgs_historico.append({"role": "assistant", "content": troca["resposta"]})
            prompt_completo = [mensagens[0]] + msgs_historico + [mensagens[-1]]
        else:
            prompt_completo = mensagens

        resposta_raw, ia_nome = ai_provider.chat(prompt_completo, provider_nome=provider_nome)
        resposta_limpa = limpar_resposta(resposta_raw)

        # ========== VERIFICA BLOQUEIO ANTES DE CONTAR ==========
        if is_bloqueado(resposta_limpa):
            return JSONResponse({
                "resposta": resposta_bloqueio(),
                "obra_usada": obra_usada,
                "ia_nome": ia_nome
            })

        # ========== SÓ CONTABILIZA SE NÃO FOR BLOQUEADO ==========
        incrementar(NOME_CONTADOR_PERGUNTAS)

        # ========== BLOCO DE LOG (DEBUG) - IGUAL BUKO ==========
        if DEBUG:
            elapsed_total = time.time() - start_time
            process = psutil.Process(os.getpid())
            mem_rss = process.memory_info().rss / 1024 / 1024
            mem_percent = process.memory_percent()
            cpu_percent = process.cpu_percent(interval=None)
            threads = process.num_threads()

            modelo = provider_cfg.get('model', 'N/A')
            temperatura = provider_cfg.get('temperature', 'N/A')
            max_tokens = provider_cfg.get('max_tokens', 'N/A')
            top_p = provider_cfg.get('top_p', 'N/A')

            print("\n" + "=" * 60)
            print(f"IA              : {ia_nome} ({modelo})")
            print(f"Config          : temp={temperatura} | max_tokens={max_tokens} | top_p={top_p}")
            print(f"Livro           : {livro_validado}")
            print(f"Obra usada      : {obra_usada or '—'}")
            print("-" * 60)
            print(f"Pergunta        : {pergunta}")
            print(f"Contexto (120c) : {contexto[:120]}...")
            print("-" * 60)
            print(f"Busca (rede)    : {tempo_busca:.3f} s")
            print(f"Tempo total     : {elapsed_total:.3f} s")
            print(f"Memória (RAM)   : {round(mem_rss, 2)} MB ({round(mem_percent, 2)}% do sistema)")
            print(f"CPU / Threads   : {cpu_percent}% de uso | {threads} threads ativas")
            print(f"Sessões ativas  : {len(conversation_memory)}")
            print(f"IPs monitorados : {len(_contadores)}")
            print(f"Visitas         : {total(NOME_CONTADOR_VISITAS)}")
            print(f"Perguntas       : {total(NOME_CONTADOR_PERGUNTAS)}")
            print("=" * 60 + "\n")

        # ========== SALVA HISTÓRICO ==========
        if session_id not in conversation_memory:
            conversation_memory[session_id] = []
        conversation_memory[session_id].append({
            "pergunta": pergunta[:150],
            "resposta": resposta_limpa[:200],
        })
        if len(conversation_memory[session_id]) > 10:
            conversation_memory[session_id] = conversation_memory[session_id][-10:]
        if len(conversation_memory) > 1000:
            conversation_memory.clear()

        # ========== LINHA DE RODAPÉ COM METADADOS (IGUAL KUSHIN-K) ==========
        elapsed_total = time.time() - start_time

        # Monta a linha de metadados
        metadata_parts = [
            PERFIL_NOME,                 # "Educador Freire"
            ia_nome,                     # IA usada
        ]

        # Adiciona obra usada se houver
        if obra_usada:
            metadata_parts.append(f"📖 {obra_usada}")

        # Adiciona tempo de resposta
        metadata_parts.append(f"{elapsed_total:.2f} s")

        # Junta tudo com " · "
        linha_metadados = " · ".join(metadata_parts)

        # Resposta final com rodapé
        resposta_final = f"{resposta_limpa}\n\n— {linha_metadados}"

        # ========== RETORNA COM METADADOS ==========
        return JSONResponse({
            "resposta": resposta_final,
            "obra_usada": obra_usada,
            "ia_nome": ia_nome,
            "tempo_resposta": f"{elapsed_total:.2f} s"
        })

    except Exception as e:
        print(f"❌ Erro: {e}")
        return JSONResponse({"resposta": resposta_bloqueio()}, status_code=500)