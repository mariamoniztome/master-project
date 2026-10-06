"""Scraping do Behance para recolha de interfaces desenhadas por humanos.

Este módulo faz scraping automático do Behance usando Playwright (para
renderização dinâmica) e BeautifulSoup (para parsing HTML). Recolhe
projetos de Web Design publicados entre 2022 e 2026 com mínimo de 100
appreciations, excluindo projetos que mencionem ferramentas de IA.

O Behance embute os dados de cada página num JSON
(<script id="beconfig-store_state">), que inclui appreciations, data de
publicação, descrição, tags, ferramentas e URLs das imagens. É esse JSON
que é lido, em vez do texto visível dos cards.

Sem sessão iniciada, cada pesquisa devolve no máximo 24 projetos, por isso
são feitas várias pesquisas por tipo de página (os mesmos tipos usados na
geração por IA) e com diferentes ordenações.

A imagem principal de cada projeto é normalizada para 1440x900 (como os
screenshots da IA) e guardada em data/humanas/. Os metadados de cada
interface ficam em data/behance_metadados.json, o que permite retomar
o scraping sem repetir projetos. O objetivo é recolher 120 interfaces.
"""

from __future__ import annotations

import asyncio
import io
import json
import random
import re
from datetime import datetime
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from PIL import Image
from playwright.async_api import async_playwright

from src.state import DATA_DIR, HUMANAS_DIR, atualizar_estado, marcar_concluido

# URL de pesquisa de projetos do Behance
URL_PESQUISA = "https://www.behance.net/search/projects?search={termo}{ordenacao}"

# Ficheiro com os metadados das interfaces recolhidas (fora de HUMANAS_DIR
# para não ser contado como interface)
METADADOS_FICHEIRO = DATA_DIR / "behance_metadados.json"

# Tipos de página (iguais aos da geração por IA) e termos de pesquisa
TERMOS_PESQUISA = {
    "landing_page": ["landing page", "landing page web design", "website homepage"],
    "dashboard": ["dashboard", "admin dashboard", "saas dashboard"],
    "formulario_contacto": ["contact form ui", "contact page web design", "sign up form ui"],
    "pagina_produto": ["product page", "ecommerce product page", "online store website"],
}

# Ordenações a combinar com cada termo (cada pesquisa devolve até 24 projetos)
ORDENACOES = [
    "",  # Recomendados
    "&sort=appreciations&time=year",
    "&sort=appreciations&time=month",
    "&sort=appreciations",
]

# Interfaces a recolher por tipo (4 tipos x 30 = 120)
OBJETIVO_POR_TIPO = 30
OBJETIVO = OBJETIVO_POR_TIPO * len(TERMOS_PESQUISA)

# Critérios de inclusão
MIN_APPRECIATIONS = 100
ANO_MIN = 2022
ANO_MAX = 2026
LARGURA_MIN_IMAGEM = 1000
# Proporção altura/largura mínima (900/1440) para excluir faixas de título
PROPORCAO_MIN_IMAGEM = 0.6

# O projeto tem de mencionar pelo menos um destes termos (título, tags,
# descrição...) para ser considerado uma interface web
TERMOS_RELEVANCIA = [
    "web", "website", "ui", "ux", "landing", "dashboard", "interface",
    "e-commerce", "ecommerce", "saas", "app design", "figma",
]

# Dimensões finais (iguais aos screenshots das interfaces geradas por IA)
LARGURA_FINAL = 1440
ALTURA_FINAL = 900

# Pausa entre pedidos (segundos) para evitar bloqueio por rate limiting
PAUSA_MIN = 2.0
PAUSA_MAX = 4.0

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

# Termos de exclusão (menção explícita de IA)
TERMOS_EXCLUSAO = [
    "midjourney",
    "dall-e",
    "dall e",
    "stable diffusion",
    "chatgpt",
    "ai generated",
    "ai-generated",
    "generative ai",
    "artificial intelligence",
    "inteligência artificial",
    "firefly",
    "leonardo ai",
]


def contem_termos_exclusao(texto: str) -> bool:
    """Verifica se o texto contém termos de IA a excluir.

    Args:
        texto: Texto do projeto (título, descrição, tags, etc.).

    Returns:
        True se contém algum termo de exclusão, False caso contrário.
    """
    texto_lower = texto.lower()
    for termo in TERMOS_EXCLUSAO:
        if termo in texto_lower:
            return True
    return False


def e_interface_web(texto: str) -> bool:
    """Verifica se o texto do projeto indica que se trata de uma interface web.

    Args:
        texto: Texto do projeto (título, descrição, tags, etc.).

    Returns:
        True se contém algum termo de relevância (como palavra inteira).
    """
    texto_lower = texto.lower()
    return any(re.search(rf"\b{re.escape(termo)}\b", texto_lower) for termo in TERMOS_RELEVANCIA)


def ano_publicacao(timestamp: int | None) -> int | None:
    """Converte o timestamp de publicação do Behance num ano.

    Args:
        timestamp: Segundos desde epoch (campo publishedOn).

    Returns:
        Ano como inteiro, ou None se não existir.
    """
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp).year


def total_appreciations(projeto: dict) -> int:
    """Obtém o número de appreciations de um projeto do Behance.

    Args:
        projeto: Dicionário do projeto (do JSON embutido).

    Returns:
        Número de appreciations (0 se não existir).
    """
    stats = projeto.get("stats") or {}
    return (stats.get("appreciations") or {}).get("all", 0)


def cumpre_criterios_basicos(projeto: dict) -> str | None:
    """Verifica data de publicação e appreciations.

    Args:
        projeto: Dicionário do projeto.

    Returns:
        Motivo de rejeição, ou None se cumpre os critérios.
    """
    ano = ano_publicacao(projeto.get("publishedOn"))
    if ano is None or not ANO_MIN <= ano <= ANO_MAX:
        return f"publicado em {ano}"
    appreciations = total_appreciations(projeto)
    if appreciations < MIN_APPRECIATIONS:
        return f"{appreciations} appreciations (< {MIN_APPRECIATIONS})"
    return None


def texto_do_projeto(projeto: dict) -> str:
    """Junta todo o texto de um projeto para verificar menções a IA.

    Inclui título, descrição, tags, ferramentas e módulos de texto.

    Args:
        projeto: Dicionário do projeto (página individual).

    Returns:
        Texto completo do projeto.
    """
    partes = [projeto.get("name") or "", projeto.get("description") or ""]
    partes += [tag.get("title") or "" for tag in projeto.get("tags") or []]
    partes += [ferramenta.get("title") or "" for ferramenta in projeto.get("tools") or []]
    for modulo in projeto.get("allModules") or projeto.get("modules") or []:
        if modulo.get("text"):
            partes.append(BeautifulSoup(modulo["text"], "lxml").get_text(" "))
        if modulo.get("caption"):
            partes.append(modulo["caption"])
    return " ".join(partes)


def escolher_imagem_principal(projeto: dict) -> str | None:
    """Escolhe a primeira imagem do projeto com resolução suficiente.

    Prefere a versão original (source) e evita versões webp.

    Args:
        projeto: Dicionário do projeto (página individual).

    Returns:
        URL da imagem, ou None se não houver imagem adequada.
    """
    for modulo in projeto.get("allModules") or projeto.get("modules") or []:
        if modulo.get("__typename") != "ImageModule":
            continue
        largura, altura = modulo.get("width") or 0, modulo.get("height") or 0
        if not largura or altura / largura < PROPORCAO_MIN_IMAGEM:
            continue
        tamanhos = (modulo.get("imageSizes") or {}).get("allAvailable") or []
        candidatas = [
            t for t in tamanhos
            if t.get("url") and "_webp" not in t["url"] and (t.get("width") or 0) >= LARGURA_MIN_IMAGEM
        ]
        if not candidatas:
            continue
        for candidata in candidatas:
            if "/source/" in candidata["url"]:
                return candidata["url"]
        return max(candidatas, key=lambda t: t["width"])["url"]
    return None


def normalizar_imagem(conteudo: bytes) -> Image.Image:
    """Redimensiona para 1440 de largura e recorta os primeiros 900 px.

    Assim a área analisada é comparável aos screenshots 1440x900 das
    interfaces geradas por IA (a "primeira dobra" da página).

    Args:
        conteudo: Bytes da imagem descarregada.

    Returns:
        Imagem RGB normalizada.
    """
    imagem = Image.open(io.BytesIO(conteudo)).convert("RGB")
    altura = round(imagem.height * LARGURA_FINAL / imagem.width)
    imagem = imagem.resize((LARGURA_FINAL, altura), Image.LANCZOS)
    return imagem.crop((0, 0, LARGURA_FINAL, min(altura, ALTURA_FINAL)))


def carregar_metadados() -> list[dict]:
    """Carrega os metadados das interfaces já recolhidas.

    Returns:
        Lista de registos (um por interface), vazia se não existir.
    """
    if METADADOS_FICHEIRO.exists():
        try:
            with open(METADADOS_FICHEIRO, "r", encoding="utf-8") as f:
                registos = json.load(f)
            # Ignora registos cuja imagem foi apagada
            return [r for r in registos if (HUMANAS_DIR / r["ficheiro"]).exists()]
        except (json.JSONDecodeError, IOError, KeyError):
            pass
    return []


def guardar_metadados(registos: list[dict]) -> None:
    """Guarda os metadados das interfaces recolhidas.

    Args:
        registos: Lista de registos a guardar.
    """
    with open(METADADOS_FICHEIRO, "w", encoding="utf-8") as f:
        json.dump(registos, f, indent=2, ensure_ascii=False)


async def ler_estado_pagina(pagina, url: str) -> dict | None:
    """Abre um URL do Behance e devolve o JSON embutido na página.

    Args:
        pagina: Página do Playwright.
        url: URL a abrir.

    Returns:
        Dicionário com o estado da página, ou None se não existir.
    """
    await pagina.goto(url, wait_until="domcontentloaded", timeout=60000)
    await pagina.wait_for_timeout(2000)
    soup = BeautifulSoup(await pagina.content(), "lxml")
    script = soup.find("script", id="beconfig-store_state")
    if not script:
        return None
    return json.loads(script.text)


async def pausa() -> None:
    """Espera um tempo aleatório entre pedidos."""
    await asyncio.sleep(random.uniform(PAUSA_MIN, PAUSA_MAX))


async def fazer_scraping_behance(callback_progresso=None, callback_log=None) -> int:
    """Executa o scraping do Behance para recolher interfaces humanas.

    Para cada tipo de página, percorre os termos de pesquisa e ordenações,
    filtra os resultados pelos critérios de inclusão (ano e appreciations),
    abre cada projeto candidato para verificar menções a IA e descarrega a
    imagem principal. Retoma a partir dos metadados já guardados.

    Args:
        callback_progresso: Função chamada com (recolhidas, objetivo) para
            atualizar a barra de progresso.
        callback_log: Função chamada com uma string de log para mostrar
            o que está a acontecer na interface.

    Returns:
        Número total de interfaces recolhidas.
    """
    HUMANAS_DIR.mkdir(parents=True, exist_ok=True)
    registos = carregar_metadados()
    projetos_verificados = {r["id"] for r in registos}

    def log(mensagem: str):
        if callback_log:
            callback_log(mensagem)
        print(mensagem)

    if registos:
        log(f"A retomar: {len(registos)} interfaces já recolhidas.")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            contexto = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=USER_AGENT
            )
            pagina = await contexto.new_page()

            for tipo, termos in TERMOS_PESQUISA.items():
                recolhidas_tipo = sum(1 for r in registos if r["tipo"] == tipo)

                for termo in termos:
                    for ordenacao in ORDENACOES:
                        if recolhidas_tipo >= OBJETIVO_POR_TIPO:
                            break

                        url = URL_PESQUISA.format(termo=quote_plus(termo), ordenacao=ordenacao)
                        log(f"[{tipo}] A pesquisar '{termo}' {ordenacao or '(recomendados)'}...")
                        try:
                            estado = await ler_estado_pagina(pagina, url)
                            resultados = estado["search"]["projects"]["search"]["nodes"]
                        except Exception as e:
                            log(f"Falha na pesquisa '{termo}': {e}")
                            await pausa()
                            continue
                        await pausa()

                        for resultado in resultados:
                            if recolhidas_tipo >= OBJETIVO_POR_TIPO:
                                break

                            projeto_id = resultado.get("id")
                            if not projeto_id or projeto_id in projetos_verificados:
                                continue
                            projetos_verificados.add(projeto_id)

                            # Filtro rápido com os dados da pesquisa
                            motivo = cumpre_criterios_basicos(resultado)
                            if motivo:
                                log(f"Projeto {projeto_id} rejeitado: {motivo}")
                                continue
                            if contem_termos_exclusao(resultado.get("name") or ""):
                                log(f"Projeto {projeto_id} rejeitado: menciona IA")
                                continue

                            # Abre o projeto para ver descrição, tags e imagens
                            try:
                                estado_projeto = await ler_estado_pagina(pagina, resultado["url"])
                                projeto = estado_projeto["project"]["project"]
                            except Exception as e:
                                log(f"Projeto {projeto_id}: falha ao abrir ({e})")
                                await pausa()
                                continue
                            await pausa()

                            texto = texto_do_projeto(projeto)
                            if contem_termos_exclusao(texto):
                                log(f"Projeto {projeto_id} rejeitado: menciona IA")
                                continue
                            if not e_interface_web(texto):
                                log(f"Projeto {projeto_id} rejeitado: não parece ser uma interface web")
                                continue

                            img_url = escolher_imagem_principal(projeto)
                            if not img_url:
                                log(f"Projeto {projeto_id} rejeitado: sem imagem com resolução suficiente")
                                continue

                            # Descarrega a imagem com o mesmo contexto do browser
                            try:
                                resposta = await contexto.request.get(img_url, timeout=60000)
                                if not resposta.ok:
                                    raise RuntimeError(f"HTTP {resposta.status}")
                                imagem = normalizar_imagem(await resposta.body())
                            except Exception as e:
                                log(f"Projeto {projeto_id}: falha ao descarregar imagem ({e})")
                                continue

                            recolhidas_tipo += 1
                            nome_ficheiro = f"humana_{tipo}_{recolhidas_tipo:03d}.png"
                            imagem.save(HUMANAS_DIR / nome_ficheiro)

                            appreciations = total_appreciations(projeto)
                            registos.append({
                                "id": projeto_id,
                                "ficheiro": nome_ficheiro,
                                "tipo": tipo,
                                "titulo": projeto.get("name"),
                                "url": resultado["url"],
                                "autores": [o.get("displayName") for o in projeto.get("owners") or []],
                                "publicado": datetime.fromtimestamp(projeto["publishedOn"]).date().isoformat(),
                                "appreciations": appreciations,
                                "visualizacoes": ((projeto.get("stats") or {}).get("views") or {}).get("all"),
                                "imagem_original": img_url,
                                "termo_pesquisa": termo,
                            })
                            guardar_metadados(registos)

                            log(f"Projeto {projeto_id} guardado como {nome_ficheiro} ({appreciations} appreciations)")
                            atualizar_estado("behance", total=len(registos))
                            if callback_progresso:
                                callback_progresso(len(registos), OBJETIVO)

                if recolhidas_tipo < OBJETIVO_POR_TIPO:
                    log(f"[{tipo}] Só foram encontradas {recolhidas_tipo}/{OBJETIVO_POR_TIPO} interfaces. "
                        "Acrescente termos em TERMOS_PESQUISA.")

            await browser.close()

    except Exception as e:
        log(f"Erro durante o scraping: {e}")

    recolhidas = len(registos)
    if recolhidas >= OBJETIVO:
        marcar_concluido("behance", total=recolhidas)
    else:
        atualizar_estado("behance", total=recolhidas)
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
