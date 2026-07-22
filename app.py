"""Aplicação principal — Ferramenta de Investigação Académica.

Esta aplicação compara interfaces web geradas por IA com interfaces
desenhadas por designers humanos, analisando o grau de padronização
visual entre os dois grupos.

Tem 4 secções principais acessíveis por menu lateral:
1. Geração de Interfaces IA
2. Scraping do Behance
3. Análise Visual Automática
4. Dashboard de Resultados

Execute com: streamlit run app.py
"""

import streamlit as st

from src.state import (
    carregar_estado,
    obter_progresso,
    IA_DIR,
    HUMANAS_DIR,
)
from src.ia_generation import gerar_interfaces_sync, TIPOS_PAGINA
from src.behance_scraper import scraping_behance_sync
from src.visual_analysis import analisar_corpus
from src.dashboard import mostrar_dashboard

# Configuração da página
st.set_page_config(
    page_title="Investigação Visual: IA vs Humanos",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_estado() -> dict:
    """Inicializa o estado da sessão e carrega o estado persistente.

    Returns:
        Dicionário com o estado persistente.
    """
    if "estado" not in st.session_state:
        st.session_state.estado = carregar_estado()
    return st.session_state.estado


def secao_geracao_ia(estado: dict) -> None:
    """Secção 1: Geração de Interfaces IA.

    Permite introduzir a API key da Anthropic e gerar 120 interfaces
    web usando o Claude, com barra de progresso.

    Args:
        estado: Estado persistente da aplicação.
    """
    st.header("1. Geração de Interfaces IA")
    st.markdown(
        "Gera 120 interfaces web em HTML/CSS usando o Claude (modelo "
        "claude-sonnet-4-6), 30 de cada tipo: landing page, dashboard, "
        "formulário de contacto e página de produto. As prompts não "
        "contêm especificações visuais."
    )

    # Campo para API key
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        value="",
        help="Introduz a tua chave de API da Anthropic.",
    )

    # Mostra progresso atual
    geradas = obter_progresso("ia")
    total_objetivo = sum(TIPOS_PAGINA.values())
    st.info(f"Interfaces IA geradas: {geradas} / {total_objetivo}")

    if estado.get("ia", {}).get("concluido", False):
        st.success("Geração de interfaces IA concluída!")

    # Botão para gerar
    if st.button("Gerar Interfaces IA", type="primary", disabled=not api_key):
        if not api_key:
            st.error("Introduz a API key da Anthropic.")
            return

        barra = st.progress(0, text="A iniciar geração...")
        texto_status = st.empty()

        def callback_progresso(geradas, total, tipo, indice):
            percentagem = int(geradas / total * 100)
            barra.progress(percentagem, text=f"A gerar {tipo} ({indice}/{TIPOS_PAGINA[tipo]}) — {geradas}/{total} total")
            texto_status.text(f"Última: {tipo}_{indice:03d}.png")

        with st.spinner("A gerar interfaces com Claude..."):
            try:
                resultado = gerar_interfaces_sync(api_key, callback_progresso)
                barra.progress(100, text="Geração concluída!")
                st.success(f"Interfaces geradas: {sum(resultado.values())}")
                st.session_state.estado = carregar_estado()
            except Exception as e:
                st.error(f"Erro durante a geração: {e}")


def secao_scraping_behance(estado: dict) -> None:
    """Secção 2: Scraping do Behance.

    Inicia o scraping automático do Behance para recolher interfaces
    humanas, com barra de progresso e log em tempo real.

    Args:
        estado: Estado persistente da aplicação.
    """
    st.header("2. Scraping do Behance")
    st.markdown(
        "Recolhe projetos da categoria Web Design (2022–2026, mínimo "
        "100 appreciations), excluindo projetos que mencionem IA. "
        "Objetivo: 120 interfaces."
    )

    # Mostra progresso atual
    recolhidas = obter_progresso("humanas")
    st.info(f"Interfaces humanas recolhidas: {recolhidas} / 120")

    if estado.get("behance", {}).get("concluido", False):
        st.success("Scraping do Behance concluído!")

    # Botão para iniciar scraping
    if st.button("Iniciar Scraping", type="primary"):
        barra = st.progress(0, text="A iniciar scraping...")
        area_log = st.empty()
        logs = []

        def callback_progresso(recolhidas, objetivo):
            percentagem = int(recolhidas / objetivo * 100)
            barra.progress(percentagem, text=f"Recolhidas: {recolhidas}/{objetivo}")

        def callback_log(mensagem):
            logs.append(mensagem)
            # Mostra últimos 10 logs
            area_log.text("\n".join(logs[-10:]))

        with st.spinner("A fazer scraping do Behance..."):
            try:
                total = scraping_behance_sync(callback_progresso, callback_log)
                barra.progress(100, text=f"Scraping concluído: {total} interfaces")
                st.success(f"Recolhidas {total} interfaces humanas.")
                st.session_state.estado = carregar_estado()
            except Exception as e:
                st.error(f"Erro durante o scraping: {e}")


def secao_analise_visual(estado: dict) -> None:
    """Secção 3: Análise Visual Automática.

    Inicia a análise das imagens nas 4 dimensões (cor, layout, tipografia,
    hierarquia) com barra de progresso por imagem.

    Args:
        estado: Estado persistente da aplicação.
    """
    st.header("3. Análise Visual Automática")
    st.markdown(
        "Analisa cada imagem em 4 dimensões: paleta cromática, layout, "
        "tipografia e hierarquia visual — usando OpenCV, scikit-learn e "
        "pytesseract."
    )

    # Verifica se ambos os corpus têm dados
    total_ia = obter_progresso("ia")
    total_humana = obter_progresso("humanas")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Interfaces IA", total_ia)
    with col2:
        st.metric("Interfaces Humanas", total_humana)

    if total_ia == 0 and total_humana == 0:
        st.warning("Ambos os corpus estão vazios. Gera interfaces IA e faz scraping do Behance primeiro.")
        return

    if estado.get("analise", {}).get("concluido", False):
        st.success("Análise concluída!")

    # Botão para iniciar análise
    if st.button("Iniciar Análise", type="primary"):
        barra = st.progress(0, text="A iniciar análise...")
        texto_atual = st.empty()

        def callback_progresso(analisadas, total):
            percentagem = int(analisadas / total * 100) if total > 0 else 0
            barra.progress(percentagem, text=f"Analisadas: {analisadas}/{total}")
            texto_atual.text(f"A analisar imagem {analisadas} de {total}...")

        with st.spinner("A analisar imagens..."):
            try:
                total = analisar_corpus(callback_progresso)
                barra.progress(100, text="Análise concluída!")
                st.success(f"Analisadas {total} imagens. Resultados guardados em data/resultados/resultados.csv")
                st.session_state.estado = carregar_estado()
            except Exception as e:
                st.error(f"Erro durante a análise: {e}")


def secao_dashboard(estado: dict) -> None:
    """Secção 4: Dashboard de Resultados.

    Só fica disponível depois de a análise estar completa.

    Args:
        estado: Estado persistente da aplicação.
    """
    st.header("4. Dashboard de Resultados")

    if not estado.get("analise", {}).get("concluido", False):
        st.warning("O dashboard só fica disponível depois de a análise estar completa.")
        return

    mostrar_dashboard()


def main() -> None:
    """Função principal que configura a sidebar e renderiza a secção ativa."""
    estado = init_estado()

    # Sidebar com menu de navegação
    st.sidebar.title("Investigação Visual")
    st.sidebar.markdown("**IA vs Designers Humanos**")
    st.sidebar.divider()

    opcoes = [
        "1. Geração de Interfaces IA",
        "2. Scraping do Behance",
        "3. Análise Visual Automática",
        "4. Dashboard de Resultados",
    ]

    # Indicadores de estado na sidebar
    st.sidebar.markdown("### Estado do Projeto")
    ia_concluido = estado.get("ia", {}).get("concluido", False)
    behance_concluido = estado.get("behance", {}).get("concluido", False)
    analise_concluido = estado.get("analise", {}).get("concluido", False)

    for nome, concluido in [
        ("Geração IA", ia_concluido),
        ("Scraping Behance", behance_concluido),
        ("Análise Visual", analise_concluido),
    ]:
        icon = "[x]" if concluido else "[ ]"
        st.sidebar.text(f"{icon} {nome}")

    st.sidebar.divider()

    selecao = st.sidebar.radio("Navegação", opcoes, index=0)

    st.sidebar.divider()
    st.sidebar.markdown(
        "Ferramenta de investigação académica para análise "
        "comparativa de padronização visual entre interfaces "
        "geradas por IA e desenhadas por humanos."
    )

    # Renderiza a secção selecionada
    if selecao == opcoes[0]:
        secao_geracao_ia(estado)
    elif selecao == opcoes[1]:
        secao_scraping_behance(estado)
    elif selecao == opcoes[2]:
        secao_analise_visual(estado)
    elif selecao == opcoes[3]:
        secao_dashboard(estado)


if __name__ == "__main__":
    main()
