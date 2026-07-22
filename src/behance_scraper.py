"""Scraping do Behance para recolha de interfaces desenhadas por humanos.

Este módulo faz scraping automático do Behance usando Playwright (para
renderização dinâmica e scroll) e BeautifulSoup (para parsing HTML).
Recolhe projetos da categoria Web Design publicados entre 2022 e 2026
com mínimo de 100 appreciations, excluindo projetos que mencionem
ferramentas de IA na descrição.

As imagens principais de cada projeto são descarregadas e guardadas
em data/humanas/. O objetivo é recolher 120 interfaces.
"""

import asyncio
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from src.state import HUMANAS_DIR, atualizar_estado, marcar_concluido

# URL base do Behance — categoria Web Design
URL_BEHANCE = "https://www.behance.net/search/projects?search=web+design"

# Objetivo de interfaces a recolher
OBJETIVO = 120

# Termos de exclusão (menção explícita de IA)
TERMOS_EXCLUSAO = [
    "midjourney",
    "dall-e",
    "dall e",
    "stable diffusion",
    "chatgpt",
    "ai generated",
    "ai-generated",
    "artificial intelligence",
    "inteligência artificial",
]

# Ano mínimo e máximo de publicação
ANO_MIN = 2022
ANO_MAX = 2026


def contem_termos_exclusao(texto: str) -> bool:
    """Verifica se o texto contém termos de IA a excluir.

    Args:
        texto: Texto da descrição do projeto.

    Returns:
        True se contém algum termo de exclusão, False caso contrário.
    """
    texto_lower = texto.lower()
    for termo in TERMOS_EXCLUSAO:
        if termo in texto_lower:
            return True
    return False


def extrair_ano(texto_data: str) -> int | None:
    """Extrai o ano de uma string de data.

    Args:
        texto_data: Texto contendo uma data (ex: "Published May 15, 2023").

    Returns:
        Ano como inteiro, ou None se não for possível extrair.
    """
    match = re.search(r"\b(20\d{2})\b", texto_data)
    if match:
        return int(match.group(1))
    return None


def extrair_appreciations(texto: str) -> int:
    """Extrai o número de appreciations de um texto.

    Args:
        texto: Texto contendo o número de appreciations.

    Returns:
        Número de appreciations como inteiro (0 se não encontrado).
    """
    # Tenta padrões como "1.2K", "500", "12,345"
    match = re.search(r"([\d.,]+)\s*[KkMm]?", texto)
    if match:
        valor = match.group(1).replace(",", "").replace(".", "")
        # Verifica sufixos K/M
        if "K" in texto or "k" in texto:
            try:
                return int(float(match.group(1).replace(",", "")) * 1000)
            except ValueError:
                pass
        if "M" in texto or "m" in texto:
            try:
                return int(float(match.group(1).replace(",", "")) * 1000000)
            except ValueError:
                pass
        try:
            return int(valor)
        except ValueError:
            pass
    return 0


async def descarregar_imagem(url: str, caminho: Path) -> bool:
    """Descarrega uma imagem de um URL e guarda num caminho local.

    Args:
        url: URL da imagem.
        caminho: Caminho local onde guardar a imagem.

    Returns:
        True se descarregou com sucesso, False caso contrário.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            pagina = await browser.new_page()
            resposta = await pagina.goto(url, wait_until="load", timeout=30000)
            if resposta and resposta.ok:
                conteudo = await resposta.body()
                with open(caminho, "wb") as f:
                    f.write(conteudo)
                await browser.close()
                return True
            await browser.close()
        return False
    except Exception as e:
        print(f"Erro ao descarregar imagem {url}: {e}")
        return False


async def fazer_scraping_behance(callback_progresso=None, callback_log=None) -> int:
    """Executa o scraping do Behance para recolher interfaces humanas.

    Navega até à página de pesquisa de Web Design, faz scroll automático
    para carregar mais projetos, verifica os critérios de inclusão/exclusão
    e descarrega as imagens principais.

    Args:
        callback_progresso: Função chamada com (recolhidas, objetivo) para
            atualizar a barra de progresso.
        callback_log: Função chamada com uma string de log para mostrar
            o que está a acontecer na interface.

    Returns:
        Número total de interfaces recolhidas.
    """
    HUMANAS_DIR.mkdir(parents=True, exist_ok=True)
    recolhidas = 0
    projetos_verificados = set()

    def log(mensagem: str):
        if callback_log:
            callback_log(mensagem)
        print(mensagem)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            pagina = await browser.new_page(viewport={"width": 1920, "height": 1080})

            log("A abrir Behance — categoria Web Design...")
            await pagina.goto(URL_BEHANCE, wait_until="networkidle", timeout=60000)
            await pagina.wait_for_timeout(3000)

            tentativas_scroll = 0
            max_scroll = 50  # Limite de scrolls para evitar loop infinito

            while recolhidas < OBJETIVO and tentativas_scroll < max_scroll:
                # Obtém o HTML da página atual
                html = await pagina.content()
                soup = BeautifulSoup(html, "lxml")

                # Procura links de projetos
                links = soup.find_all("a", href=re.compile(r"/projects/\d+"))

                for link in links:
                    if recolhidas >= OBJETIVO:
                        break

                    href = link.get("href", "")
                    # Extrai ID do projeto para evitar duplicados
                    match_id = re.search(r"/projects/(\d+)", href)
                    if not match_id:
                        continue
                    projeto_id = match_id.group(1)

                    if projeto_id in projetos_verificados:
                        continue
                    projetos_verificados.add(projeto_id)

                    url_projeto = urljoin("https://www.behance.net", href)

                    # Tenta extrair metadados do card
                    card_text = link.get_text(" ", strip=True)
                    # Verifica appreciations
                    appreciations = extrair_appreciations(card_text)

                    # Verifica se tem pelo menos 100 appreciations
                    if appreciations < 100:
                        log(f"Projeto {projeto_id} rejeitado: {appreciations} appreciations (< 100)")
                        continue

                    # Verifica termos de exclusão na descrição do card
                    if contem_termos_exclusao(card_text):
                        log(f"Projeto {projeto_id} rejeitado: menciona IA")
                        continue

                    # Procura imagem no card
                    img_tag = link.find("img")
                    if not img_tag:
                        # Procura imagem em elementos próximos
                        parent = link.parent
                        if parent:
                            img_tag = parent.find("img")

                    if img_tag:
                        img_url = img_tag.get("src") or img_tag.get("data-src")
                        if img_url and img_url.startswith("http"):
                            nome_ficheiro = f"humana_{recolhidas + 1:03d}.png"
                            caminho = HUMANAS_DIR / nome_ficheiro

                            sucesso = await descarregar_imagem(img_url, caminho)
                            if sucesso:
                                recolhidas += 1
                                log(f"Projeto {projeto_id} guardado como {nome_ficheiro} ({appreciations} appreciations)")
                                atualizar_estado("behance", total=recolhidas)
                                if callback_progresso:
                                    callback_progresso(recolhidas, OBJETIVO)
                            else:
                                log(f"Projeto {projeto_id}: falha ao descarregar imagem")
                        else:
                            log(f"Projeto {projeto_id} rejeitado: sem imagem válida")
                    else:
                        log(f"Projeto {projeto_id} rejeitado: sem imagem")

                if recolhidas < OBJETIVO:
                    # Faz scroll para carregar mais projetos
                    log(f"A fazer scroll para carregar mais projetos... ({recolhidas}/{OBJETIVO})")
                    await pagina.evaluate("window.scrollBy(0, 3000)")
                    await pagina.wait_for_timeout(3000)
                    tentativas_scroll += 1

            await browser.close()

    except Exception as e:
        log(f"Erro durante o scraping: {e}")

    marcar_concluido("behance", total=recolhidas)
    log(f"Scraping concluído: {recolhidas} interfaces recolhidas.")
    return recolhidas


def scraping_behance_sync(callback_progresso=None, callback_log=None) -> int:
    """Versão síncrona de fazer_scraping_behance para usar no Streamlit.

    Args:
        callback_progresso: Função de callback de progresso.
        callback_log: Função de callback de log.

    Returns:
        Número total de interfaces recolhidas.
    """
    return asyncio.run(fazer_scraping_behance(callback_progresso, callback_log))
