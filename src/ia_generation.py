"""Geração de interfaces web com a API do Claude (Anthropic).

Este módulo gera até 120 interfaces web em HTML/CSS usando o modelo
claude-sonnet-4-6 da Anthropic, 30 de cada tipo (landing page, dashboard,
formulário de contacto, página de produto). As prompts enviadas ao Claude
não contêm especificações visuais — apenas o tipo de página — para que a
IA decida livremente o aspeto visual.

Os pedidos são enviados em lote pela Message Batches API, que custa metade
do preço normal e devolve os resultados de forma assíncrona (normalmente
em menos de uma hora). As interfaces são pedidas em ordem rotativa entre
os tipos, para que um lote parcial fique equilibrado.

Cada interface gerada é renderizada com Playwright e capturada como
screenshot em resolução 1440x900, guardada em data/ia/.
"""

import asyncio
import csv
import json
import time
from pathlib import Path

from anthropic import Anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from playwright.async_api import async_playwright

from src.state import DATA_DIR, IA_DIR, atualizar_estado, marcar_concluido

# Modelo da Anthropic a utilizar
MODELO = "claude-sonnet-4-6"

# Limite de tokens de saída. Fica bem acima do tamanho típico de uma página
# (~15 000 tokens) para nenhuma resposta ser cortada e desperdiçada; só se
# paga o que é efetivamente gerado.
MAX_TOKENS = 32000

# Preços da Batch API para o claude-sonnet-4-6 (USD por milhão de tokens,
# 50% do preço normal de 3 $ / 15 $)
PRECO_ENTRADA_LOTE = 1.50
PRECO_SAIDA_LOTE = 7.50

# Tokens de saída por página, usados na estimativa se ainda não houver registos
TOKENS_SAIDA_ESTIMADOS = 15000

# Tipos de página a gerar e respetiva quantidade
TIPOS_PAGINA = {
    "landing_page": 30,
    "dashboard": 30,
    "formulario_contacto": 30,
    "pagina_produto": 30,
}

# Resolução dos screenshots
LARGURA = 1440
ALTURA = 900

# Diretório temporário para ficheiros HTML
HTML_DIR = IA_DIR / "html"

# Registo dos tokens usados em cada pedido (para calcular o custo real)
TOKENS_CSV = DATA_DIR / "ia_tokens.csv"

# Lote enviado e ainda não processado (permite fechar a app e voltar depois)
LOTE_FICHEIRO = DATA_DIR / "ia_lote.json"


def registar_tokens(tipo: str, resposta) -> None:
    """Acrescenta ao CSV os tokens de entrada e saída de um pedido.

    Args:
        tipo: Tipo de página gerada.
        resposta: Resposta da API do Claude.
    """
    novo = not TOKENS_CSV.exists()
    with open(TOKENS_CSV, "a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        if novo:
            escritor.writerow(["data", "tipo", "modelo", "tokens_entrada", "tokens_saida", "stop_reason"])
        escritor.writerow([
            time.strftime("%Y-%m-%d %H:%M:%S"), tipo, resposta.model,
            resposta.usage.input_tokens, resposta.usage.output_tokens, resposta.stop_reason,
        ])


def construir_prompt(tipo: str) -> str:
    """Constrói a prompt para o Claude, sem especificações visuais.

    A prompt contém apenas o tipo de página solicitado, para que a IA
    decida livremente as cores, layout, tipografia e hierarquia visual.

    Args:
        tipo: Tipo de página (landing_page, dashboard, etc.).

    Returns:
        String com a prompt a enviar ao Claude.
    """
    descricoes = {
        "landing_page": "uma landing page",
        "dashboard": "um dashboard",
        "formulario_contacto": "um formulário de contacto",
        "pagina_produto": "uma página de produto",
    }
    descricao = descricoes.get(tipo, tipo)
    return (
        f"Gera {descricao} completa e funcional em HTML e CSS inline. "
        f"O código deve ser uma página web autónoma (um único ficheiro HTML "
        f"com CSS incorporado). Não uses JavaScript. Responde apenas com "
        f"o código HTML, sem explicações."
    )


def limpar_html(html: str) -> str:
    """Remove marcações de código markdown caso existam.

    O Claude por vezes envolve o código em blocos ```html ... ```.
    Esta função remove esses marcadores.

    Args:
        html: HTML potencialmente envolvido em markdown.

    Returns:
        HTML limpo.
    """
    html = html.strip()
    if html.startswith("```"):
        # Remove a primeira linha (```html ou ```)
        linhas = html.split("\n")
        linhas = linhas[1:]  # remove primeira linha
        if linhas and linhas[-1].strip() == "```":
            linhas = linhas[:-1]  # remove última linha
        html = "\n".join(linhas)
    return html


async def capturar_screenshot(html: str, caminho_saida: Path) -> bool:
    """Renderiza HTML com Playwright e captura screenshot em 1440x900.

    Args:
        html: Código HTML a renderizar.
        caminho_saida: Caminho onde guardar o screenshot (PNG).

    Returns:
        True se o screenshot foi capturado com sucesso, False caso contrário.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            pagina = await browser.new_page(viewport={"width": LARGURA, "height": ALTURA})
            # Carrega o HTML diretamente no navegador
            await pagina.set_content(html, wait_until="networkidle", timeout=30000)
            # Pequena pausa para garantir renderização completa
            await pagina.wait_for_timeout(1000)
            await pagina.screenshot(path=str(caminho_saida), full_page=False)
            await browser.close()
        return True
    except Exception as e:
        print(f"Erro ao capturar screenshot: {e}")
        return False


def contar_por_tipo() -> dict:
    """Conta as interfaces IA já geradas (screenshots) por tipo.

    Returns:
        Dicionário {tipo: quantidade}.
    """
    return {
        tipo: sum(1 for i in range(quantidade) if (IA_DIR / f"{tipo}_{i + 1:03d}.png").exists())
        for tipo, quantidade in TIPOS_PAGINA.items()
    }


def proximas_interfaces(quantidade: int) -> list[str]:
    """Escolhe as próximas interfaces a gerar, em ordem rotativa entre tipos.

    Percorre landing_page_001, dashboard_001, formulario_contacto_001,
    pagina_produto_001, landing_page_002, ... e devolve as primeiras que
    ainda não existem. Assim, um lote parcial fica equilibrado entre tipos.

    Args:
        quantidade: Número máximo de interfaces a devolver.

    Returns:
        Lista de nomes base (ex.: "dashboard_004").
    """
    nomes = []
    for i in range(max(TIPOS_PAGINA.values())):
        for tipo, total_tipo in TIPOS_PAGINA.items():
            if i >= total_tipo:
                continue
            nome_base = f"{tipo}_{i + 1:03d}"
            if not (IA_DIR / f"{nome_base}.png").exists():
                nomes.append(nome_base)
            if len(nomes) >= quantidade:
                return nomes
    return nomes


def tipo_de(nome_base: str) -> str:
    """Obtém o tipo de página a partir do nome base (ex.: "dashboard_004")."""
    return nome_base.rsplit("_", 1)[0]


def custo_estimado_por_interface() -> float:
    """Estima o custo (USD) de uma interface na Batch API.

    Usa a média de tokens de saída já registada em ia_tokens.csv; se ainda
    não houver registos, usa TOKENS_SAIDA_ESTIMADOS.

    Returns:
        Custo estimado em dólares.
    """
    tokens_entrada, tokens_saida = 70, TOKENS_SAIDA_ESTIMADOS
    if TOKENS_CSV.exists():
        with open(TOKENS_CSV, encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        if linhas:
            tokens_entrada = sum(int(l["tokens_entrada"]) for l in linhas) / len(linhas)
            tokens_saida = sum(int(l["tokens_saida"]) for l in linhas) / len(linhas)
    return (tokens_entrada * PRECO_ENTRADA_LOTE + tokens_saida * PRECO_SAIDA_LOTE) / 1_000_000


def carregar_lote() -> dict | None:
    """Devolve o lote pendente (id e interfaces pedidas), se existir."""
    if LOTE_FICHEIRO.exists():
        with open(LOTE_FICHEIRO, encoding="utf-8") as f:
            return json.load(f)
    return None


def enviar_lote(api_key: str, quantidade: int) -> dict:
    """Envia um lote de pedidos de geração à Message Batches API.

    Erros de configuração (API key inválida, saldo insuficiente, etc.)
    são lançados para aparecerem na interface.

    Args:
        api_key: Chave de API da Anthropic.
        quantidade: Número de interfaces a pedir.

    Returns:
        Dicionário com o id do lote e os nomes das interfaces pedidas.
    """
    nomes = proximas_interfaces(quantidade)
    if not nomes:
        raise ValueError("Todas as interfaces IA já foram geradas.")

    cliente = Anthropic(api_key=api_key.strip())
    lote = cliente.messages.batches.create(
        requests=[
            Request(
                custom_id=nome_base,
                params=MessageCreateParamsNonStreaming(
                    model=MODELO,
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": construir_prompt(tipo_de(nome_base))}],
                ),
            )
            for nome_base in nomes
        ]
    )

    registo = {"id": lote.id, "interfaces": nomes, "enviado": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(LOTE_FICHEIRO, "w", encoding="utf-8") as f:
        json.dump(registo, f, indent=2)
    return registo


def estado_lote(api_key: str, lote_id: str):
    """Consulta o estado de um lote na API.

    Args:
        api_key: Chave de API da Anthropic.
        lote_id: Id do lote.

    Returns:
        Objeto do lote (processing_status, request_counts, ...).
    """
    return Anthropic(api_key=api_key.strip()).messages.batches.retrieve(lote_id)


async def processar_lote(api_key: str, lote_id: str, callback_progresso=None) -> dict:
    """Descarrega os resultados de um lote terminado e captura os screenshots.

    Respostas cortadas por max_tokens ou com erro são ignoradas; essas
    interfaces continuam em falta e entram no próximo lote.

    Args:
        api_key: Chave de API da Anthropic.
        lote_id: Id do lote (já com processing_status "ended").
        callback_progresso: Função chamada com (processadas, total, nome_base).

    Returns:
        Dicionário com contagens: geradas, falhadas.
    """
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    cliente = Anthropic(api_key=api_key.strip())
    resultados = list(cliente.messages.batches.results(lote_id))

    geradas, falhadas = 0, 0
    for indice, resultado in enumerate(resultados, start=1):
        nome_base = resultado.custom_id
        tipo = tipo_de(nome_base)

        if resultado.result.type != "succeeded":
            print(f"{nome_base}: pedido {resultado.result.type}")
            falhadas += 1
        else:
            mensagem = resultado.result.message
            registar_tokens(tipo, mensagem)
            if mensagem.stop_reason == "max_tokens":
                print(f"{nome_base}: resposta cortada por max_tokens; descartada.")
                falhadas += 1
            else:
                html = limpar_html("".join(b.text for b in mensagem.content if b.type == "text"))
                with open(HTML_DIR / f"{nome_base}.html", "w", encoding="utf-8") as f:
                    f.write(html)
                if await capturar_screenshot(html, IA_DIR / f"{nome_base}.png"):
                    geradas += 1
                else:
                    falhadas += 1

        if callback_progresso:
            callback_progresso(indice, len(resultados), nome_base)

    # Atualiza o estado persistente e remove o lote pendente
    contagem = contar_por_tipo()
    total = sum(contagem.values())
    if total >= sum(TIPOS_PAGINA.values()):
        marcar_concluido("ia", total=total, tipos=contagem)
    else:
        atualizar_estado("ia", total=total, tipos=contagem)
    LOTE_FICHEIRO.unlink(missing_ok=True)

    return {"geradas": geradas, "falhadas": falhadas}


def processar_lote_sync(api_key: str, lote_id: str, callback_progresso=None) -> dict:
    """Versão síncrona de processar_lote para usar no Streamlit."""
    return asyncio.run(processar_lote(api_key, lote_id, callback_progresso))
