const PALAVRAS_SAIDA = ['sair', 'exit', 'quit', 'tchau', 'obrigado', 'ok'];

// ID único por sessão — gerado ao abrir a aba, some ao fechar
const SESSION_ID = Math.random().toString(36).slice(2) + Date.now();

const input       = document.getElementById('pergunta');
const respostaDiv = document.getElementById('resposta');
const btnMic      = document.getElementById('btn-mic');
let vozEscolhida = null;

//--------------------------------------------
function carregarVozes() {
    const vozes = window.speechSynthesis.getVoices();
    if (!vozes.length) return;

    const candidatas = vozes.filter(v => v.lang.toLowerCase().startsWith('pt'));

    vozEscolhida =
        candidatas.find(v => /google/i.test(v.name)) ||
        candidatas.find(v => /natural|premium|enhanced/i.test(v.name)) ||
        candidatas.find(v => v.lang.toLowerCase() === 'pt-br') ||
        candidatas[0] ||
        null;
}

if (window.speechSynthesis) {
    carregarVozes();
    window.speechSynthesis.onvoiceschanged = carregarVozes; // vozes carregam de forma assíncrona
}

// ============================================
// CONTADORES - SALVOS E FUNCIONANDO
// ============================================
function atualizarContadores() {
    fetch('/contador')
        .then(r => {
            if (!r.ok) throw new Error('Erro na requisição');
            return r.json();
        })
        .then(d => {
            const visitaEl = document.getElementById('contador-visitas');
            const perguntaEl = document.getElementById('contador-perguntas');
            
            if (visitaEl) {
                visitaEl.textContent = d.visitas || '0';
            }
            if (perguntaEl) {
                perguntaEl.textContent = d.perguntas || '0';
            }
            
        })
        .catch(err => {
            // Fallback: mostrar 0 se não conseguir buscar
            const visitaEl = document.getElementById('contador-visitas');
            const perguntaEl = document.getElementById('contador-perguntas');
            if (visitaEl && !visitaEl.textContent.match(/^\d+$/)) {
                visitaEl.textContent = '0';
            }
            if (perguntaEl && !perguntaEl.textContent.match(/^\d+$/)) {
                perguntaEl.textContent = '0';
            }
        });
}

function randomMsg(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
}

function limparParaVoz(texto) {
    return texto
        .replace(/— .*$/gm, '')
        .replace(/\*\*(.*?)\*\*/g, '$1')
        .replace(/\*(.*?)\*/g, '$1')
        .replace(/#{1,6}\s/g, '')
        .replace(/<[^>]+>/g, '')
        .trim();
}

// --- SÍNTESE DE VOZ ---
let falando = false;

function falar(texto) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const fala = new SpeechSynthesisUtterance(limparParaVoz(texto));
    fala.lang  = 'pt-BR';
    if (vozEscolhida) fala.voice = vozEscolhida;   
    fala.rate  = 0.9;
    fala.pitch = 1.0;
    fala.onstart = () => { falando = true;  atualizarBotaoVoz(); };
    fala.onend   = () => { falando = false; atualizarBotaoVoz(); };
    window.speechSynthesis.speak(fala);
}

function pausarVoz() {
    if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
        window.speechSynthesis.pause();
        falando = false;
        atualizarBotaoVoz();
    } else if (window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
        falando = true;
        atualizarBotaoVoz();
    }
}

function pararVoz() {
    window.speechSynthesis.cancel();
    falando = false;
    atualizarBotaoVoz();
}

function atualizarBotaoVoz() {
    const btnFalar = document.getElementById('btn-falar');
    if (btnFalar) btnFalar.textContent = falando ? 'Pausar' : 'Ouvir';
}

// --- MICROFONE ---
let reconhecendo = false;
let recognition  = null;
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function iniciarMicrofone() {
    if (!SpeechRecognition) {
        respostaDiv.innerHTML = '<em>Seu navegador não suporta reconhecimento de voz.</em>';
        return;
    }
    if (reconhecendo) return;

    recognition = new SpeechRecognition();
    recognition.lang            = 'pt-BR';
    recognition.interimResults  = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        reconhecendo = true;
        btnMic.classList.add('ouvindo');
        btnMic.title      = 'Solte para enviar';
        input.placeholder = 'Ouvindo...';
        respostaDiv.innerHTML = '<em>Educador ouvindo...</em>';
    };

    recognition.onresult = (e) => {
        input.value = e.results[0][0].transcript;
    };

    recognition.onerror = (e) => {
        reconhecendo = false;
        btnMic.classList.remove('ouvindo');
        btnMic.title      = 'Falar';
        input.placeholder = 'Dialogue com Educador...';
        respostaDiv.innerHTML = `<em>Não consegui ouvir — tente novamente. (${e.error})</em>`;
    };

    recognition.onend = () => {
        reconhecendo = false;
        btnMic.classList.remove('ouvindo');
        btnMic.title      = 'Falar';
        input.placeholder = 'Dialogue com Educador...';
        if (input.value.trim()) fazerPergunta();
    };

    recognition.start();
}

function pararMicrofone(e) {
    e.preventDefault();
    if (recognition && reconhecendo) recognition.stop();
}

// --- INICIALIZAÇÃO ---
window.addEventListener('DOMContentLoaded', () => {
    respostaDiv.innerHTML = `<em>A palavra verdadeira transforma o mundo...</em>`;
    if (btnMic) {
        btnMic.addEventListener('mousedown',  iniciarMicrofone);
        btnMic.addEventListener('mouseup',    pararMicrofone);
        btnMic.addEventListener('touchstart', (e) => { e.preventDefault(); iniciarMicrofone(); }, { passive: false });
        btnMic.addEventListener('touchend',   pararMicrofone);
        atualizarContadores();                    // ← CARREGA OS CONTADORES AO INICIAR
        setInterval(atualizarContadores, 30000);  // ← ATUALIZA A CADA 30 SEGUNDOS        
    }
});

// --- ENVIO DA PERGUNTA ---
async function fazerPergunta() {
    const textoRaw = input.value.trim();
    if (!textoRaw) return;

    // Validação de 400 chars — cobre microfone (maxlength não cobre)
    if (textoRaw.length > 400) {
        respostaDiv.innerHTML = '<em>Companheiro, a pergunta é longa demais. Simplifique o caminho do diálogo.</em>';
        return;
    }

    const livroSelect    = document.getElementById('livro-select');
    const livroEscolhido = livroSelect ? livroSelect.value : "todos";

    if (PALAVRAS_SAIDA.includes(textoRaw.toLowerCase())) {
        const despedida = randomMsg(window.DESPEDIDA_JS);
        respostaDiv.innerHTML = `<em>${despedida}</em>`;
        falar(despedida);
        input.value    = '';
        input.disabled = true;
        return;
    }

    input.disabled    = true;
    input.placeholder = 'Educador reflete...';

    // Rotação de mensagens enquanto aguarda — troca a cada 2.5s
    const _msgs = [...window.AGUARDANDO_JS].sort(() => Math.random() - 0.5);
    let _idx = 0;
    respostaDiv.innerHTML = `<em>${_msgs[0]}</em>`;
    const _rotacao = setInterval(() => {
        _idx = (_idx + 1) % _msgs.length;
        respostaDiv.innerHTML = `<em>${_msgs[_idx]}</em>`;
    }, 2500);

    try {
        const response = await fetch('/ask', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                pergunta:   textoRaw,
                livro:      livroEscolhido,
                session_id: SESSION_ID,
            })
        });

        const data     = await response.json();
        const resposta = data.resposta;

        const respostaHTML = resposta
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/^\* (.+)/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>')
            .replace(/\. ([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÇ])/g, '.</p><p>$1');

        respostaDiv.innerHTML = `
            <p>${respostaHTML}</p>
            <div class="share-buttons">
                <button id="btn-falar" title="Ouvir">Ouvir</button>
                <button id="btn-parar" title="Parar">Parar</button>
                <button id="btn-whatsapp">WhatsApp</button>
                <button id="btn-email">Email</button>
            </div>
        `;

        document.getElementById('btn-falar').addEventListener('click', () => {
            if (falando || window.speechSynthesis.paused) pausarVoz();
            else falar(resposta);
        });
        document.getElementById('btn-parar').addEventListener('click',    () => pararVoz());
        document.getElementById('btn-whatsapp').addEventListener('click', () => compartilharWhatsApp(resposta));
        document.getElementById('btn-email').addEventListener('click',    () => compartilharEmail(resposta));

    } catch (error) {
        respostaDiv.innerHTML = '<em>(a voz encontrou um obstáculo...)</em>';
    } finally {
        clearInterval(_rotacao);
        input.disabled    = false;
        input.value       = '';
        input.placeholder = 'Dialogue com Educador...';
        input.focus();
        setTimeout(atualizarContadores, 300);  // ← ATUALIZA APÓS CADA PERGUNTA
    }
}

input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') fazerPergunta();
});

function compartilharWhatsApp(texto) {
    const msg = encodeURIComponent("Educador IA:\n\n" + texto + "\n\neducador.willthing.ia.br");
    window.open(`https://wa.me/?text=${msg}`, 'whatsapp_share');
}

function compartilharEmail(texto) {
    const assunto = encodeURIComponent("Educador IA — Pedagogia do Oprimido");
    const corpo   = encodeURIComponent("Educador IA:\n\n" + texto + "\n\neducador.willthing.ia.br");
    window.open(`mailto:?subject=${assunto}&body=${corpo}`, '_blank');
}
