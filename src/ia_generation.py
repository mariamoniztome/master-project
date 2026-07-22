"""Geração de interfaces web com a API do Claude (Anthropic).

Este módulo gera 120 interfaces web em HTML/CSS usando o modelo
claude-sonnet-4-6 da Anthropic, 30 de cada tipo (landing page, dashboard,
formulário de contacto, página de produto). As prompts enviadas ao Claude
não contêm especificações visuais — apenas o tipo de página — para que a
IA decida livremente o aspeto visual.

Cada interface gerada é renderizada com Playwright e capturada como
screenshot em resolução 1440x900, guardada em data/ia/.
"""

import asyncio
import os
import time
from pathlib import Path

from anthropic import Anthropic
from playwright.async_api import async_playwright

from src.state import IA_DIR, atualizar_estado, marcar_concluido

# Modelo da Anthropic a utilizar
MODELO = "claude-sonnet-4-5-20250514"

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


def gerar_html_com_claude(api_key: str, tipo: str) -> str | None:
    """Envia a prompt ao Claude e recebe o HTML gerado.

    Args:
        api_key: Chave de API da Anthropic.
        tipo: Tipo de página a gerar.

    Returns:
        String com o código HTML, ou None em caso de erro.
    """
    try:
        cliente = Anthropic(api_key=api_key)
        prompt = construir_prompt(tipo)
        resposta = cliente.messages.create(
            model=MODELO,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extrai o texto da resposta
        html = resposta.content[0].text
        return html
    except Exception as e:
        print(f"Erro ao gerar HTML com Claude para '{tipo}': {e}")
        return None


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


async def gerar_todas_interfaces(api_key: str, callback_progresso=None) -> dict:
    """Gera todas as 120 interfaces IA.

    Para cada tipo de página, gera o número solicitado de interfaces,
    enviando prompts ao Claude, renderizando o HTML com Playwright e
    capturando screenshots.

    Args:
        api_key: Chave de API da Anthropic.
        callback_progresso: Função chamada com (geradas, total, tipo, indice)
            para atualizar a barra de progresso na interface.

    Returns:
        Dicionário com contagem de interfaces geradas por tipo.
    """
    HTML_DIR.mkdir(parents=True, exist_ok=True)
    total = sum(TIPOS_PAGINA.values())
    geradas = 0
    contagem_tipos = {}

    for tipo, quantidade in TIPOS_PAGINA.items():
        contagem_tipos[tipo] = 0
        for i in range(quantidade):
            # Nome do ficheiro: tipo_001.png
            nome_base = f"{tipo}_{i + 1:03d}"
            caminho_png = IA_DIR / f"{nome_base}.png"
            caminho_html = HTML_DIR / f"{nome_base}.html"

            # Verifica se já existe (estado persistente)
            if caminho_png.exists():
                geradas += 1
                contagem_tipos[tipo] += 1
                if callback_progresso:
                    callback_progresso(geradas, total, tipo, i + 1)
                continue

            # Gera HTML com Claude
            html = gerar_html_com_claude(api_key, tipo)
            if html is None:
                continue

            html = limpar_html(html)

            # Guarda HTML para referência
            with open(caminho_html, "w", encoding="utf-8") as f:
                f.write(html)

            # Captura screenshot
            sucesso = await capturar_screenshot(html, caminho_png)
            if sucesso:
                geradas += 1
                contagem_tipos[tipo] += 1

            # Atualiza estado persistente
            atualizar_estado("ia", total=geradas, tipos=contagem_tipos)

            if callback_progresso:
                callback_progresso(geradas, total, tipo, i + 1)

            # Pequena pausa para não exceder rate limits
            time.sleep(0.5)

    # Marca como concluído
    marcar_concluido("ia", total=geradas, tipos=contagem_tipos)
    return contagem_tipos


def gerar_interfaces_sync(api_key: str, callback_progresso=None) -> dict:
    """Versão síncrona de gerar_todas_interfaces para usar no Streamlit.

    Args:
        api_key: Chave de API da Anthropic.
        callback_progresso: Função de callback de progresso.

    Returns:
        Dicionário com contagem por tipo.
    """
    return asyncio.run(gerar_todas_interfaces(api_key, callback_progresso))
