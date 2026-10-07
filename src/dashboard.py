"""Dashboard de resultados da análise visual.

Este módulo apresenta o dashboard final com métricas gerais, gráficos
comparativos (boxplots, barras, scatter PCA), testes estatísticos (Levene
e Mann-Whitney U), galeria de thumbnails e opções de exportação (CSV/PDF).

O dashboard só fica disponível depois de a análise estar completa.
"""

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from src.state import CSV_PATH, IA_DIR, HUMANAS_DIR, RESULTADOS_DIR

# Configuração visual do seaborn
sns.set_theme(style="whitegrid", palette="muted")

# Dimensões analisadas e respetivos rótulos
DIMENSOES = {
    "variancia_cor": "Variância Cromática",
    "num_cores": "Nº Cores Dominantes",
    "variancia_layout": "Variância de Layout",
    "num_blocos": "Nº Blocos",
    "densidade": "Densidade de Elementos",
    "variancia_tipografia": "Variância Tipográfica",
    "num_niveis_texto": "Nº Níveis de Texto",
    "variancia_hierarquia": "Variância de Hierarquia",
}

# Métricas para testes estatísticos (variâncias e médias)
METRICAS_TESTE = [
    "variancia_cor",
    "variancia_layout",
    "densidade",
    "variancia_tipografia",
    "variancia_hierarquia",
    "num_cores",
    "num_blocos",
    "num_niveis_texto",
]


def carregar_dados() -> pd.DataFrame | None:
    """Carrega os resultados do CSV.

    Returns:
        DataFrame com os resultados, ou None se o ficheiro não existir.
    """
    if not CSV_PATH.exists():
        return None
    try:
        df = pd.read_csv(CSV_PATH)
        return df
    except Exception as e:
        print(f"Erro ao carregar CSV: {e}")
        return None


def mostrar_metricas_gerais(df: pd.DataFrame) -> None:
    """Mostra métricas gerais: total de interfaces por grupo e data da análise.

    Args:
        df: DataFrame com os resultados.
    """
    import streamlit as st

    total_ia = len(df[df["grupo"] == "ia"])
    total_humana = len(df[df["grupo"] == "humana"])
    total = len(df)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Interfaces IA", total_ia)
    with col2:
        st.metric("Total Interfaces Humanas", total_humana)
    with col3:
        st.metric("Total Analisadas", total)

    st.info(f"Data da análise: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}")


def gerar_boxplots(df: pd.DataFrame, por: str = "grupo") -> None:
    """Gera boxplots comparando os dois grupos em cada dimensão.

    Args:
        df: DataFrame com os resultados.
        por: Coluna usada para separar as caixas ("grupo" ou "tipo").
    """
    import streamlit as st

    st.subheader("Boxplots por Dimensão")

    metricas_boxplot = [
        "variancia_cor",
        "variancia_layout",
        "densidade",
        "variancia_tipografia",
        "variancia_hierarquia",
    ]

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()

    for i, metrica in enumerate(metricas_boxplot):
        ax = axes[i]
        if por == "grupo":
            sns.boxplot(data=df, x="grupo", y=metrica, hue="grupo", ax=ax, legend=False,
                        palette={"ia": "#4A90D9", "humana": "#D97706"})
        else:
            sns.boxplot(data=df, x=por, y=metrica, hue=por, ax=ax, legend=False)
            ax.tick_params(axis="x", labelrotation=20)
        ax.set_title(DIMENSOES.get(metrica, metrica), fontsize=11)
        ax.set_xlabel("")
        ax.set_ylabel("")

    # Esconde eixos extra
    for j in range(len(metricas_boxplot), len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close()


def gerar_graficos_barras(df: pd.DataFrame) -> None:
    """Gera gráficos de barras com as médias por grupo.

    Args:
        df: DataFrame com os resultados.
    """
    import streamlit as st

    st.subheader("Médias por Grupo")

    medias = df.groupby("grupo")[METRICAS_TESTE].mean()

    fig, axes = plt.subplots(2, 4, figsize=(18, 8))
    axes = axes.flatten()

    for i, metrica in enumerate(METRICAS_TESTE):
        ax = axes[i]
        valores = [medias.loc["ia", metrica], medias.loc["humana", metrica]]
        bars = ax.bar(["IA", "Humana"], valores, color=["#4A90D9", "#D97706"])
        ax.set_title(DIMENSOES.get(metrica, metrica), fontsize=10)
        ax.set_ylabel("Média")
        # Adiciona valores nas barras
        for bar, val in zip(bars, valores):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{val:.2f}",
                    ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close()


def calcular_testes_estatisticos(df: pd.DataFrame) -> pd.DataFrame:
    """Executa testes estatísticos: Levene (variâncias) e Mann-Whitney U (médias).

    Args:
        df: DataFrame com os resultados.

    Returns:
        DataFrame com os resultados dos testes (estatística, p-value, significância).
    """
    resultados = []

    for metrica in METRICAS_TESTE:
        grupo_ia = df[df["grupo"] == "ia"][metrica].dropna()
        grupo_humana = df[df["grupo"] == "humana"][metrica].dropna()

        if len(grupo_ia) < 2 or len(grupo_humana) < 2:
            resultados.append({
                "Métrica": DIMENSOES.get(metrica, metrica),
                "Teste Levene (p)": np.nan,
                "Levene Significativo": "",
                "Teste Mann-Whitney U (p)": np.nan,
                "Mann-Whitney Significativo": "",
            })
            continue

        # Teste de Levene para igualdade de variâncias
        try:
            levene_stat, levene_p = stats.levene(grupo_ia, grupo_humana)
        except Exception:
            levene_stat, levene_p = np.nan, np.nan

        # Teste de Mann-Whitney U para diferença de medianas
        try:
            mw_stat, mw_p = stats.mannwhitneyu(grupo_ia, grupo_humana, alternative="two-sided")
        except Exception:
            mw_stat, mw_p = np.nan, np.nan

        resultados.append({
            "Métrica": DIMENSOES.get(metrica, metrica),
            "Teste Levene (p)": f"{levene_p:.4f}" if not np.isnan(levene_p) else "N/A",
            "Levene Significativo": "Sim" if not np.isnan(levene_p) and levene_p < 0.05 else "Não",
            "Teste Mann-Whitney U (p)": f"{mw_p:.4f}" if not np.isnan(mw_p) else "N/A",
            "Mann-Whitney Significativo": "Sim" if not np.isnan(mw_p) and mw_p < 0.05 else "Não",
        })

    return pd.DataFrame(resultados)


def mostrar_tabela_estatistica(df: pd.DataFrame) -> None:
    """Mostra a tabela de testes estatísticos na interface.

    Args:
        df: DataFrame com os resultados.
    """
    import streamlit as st

    st.subheader("Testes Estatísticos")
    st.markdown("**Teste de Levene** — compara variâncias entre grupos | **Mann-Whitney U** — compara medianas entre grupos")
    st.markdown("*p < 0.05 indica diferença estatisticamente significativa*")

    tabela = calcular_testes_estatisticos(df)
    st.dataframe(tabela, use_container_width=True, hide_index=True)


def gerar_scatter_pca(df: pd.DataFrame, por: str = "grupo") -> None:
    """Gera um scatter plot PCA mostrando a distribuição dos dois grupos em 2D.

    Args:
        df: DataFrame com os resultados.
        por: Coluna usada para colorir os pontos ("grupo" ou "tipo").
    """
    import streamlit as st

    st.subheader("Distribuição PCA (2D)")

    # Seleciona apenas colunas numéricas
    colunas_numericas = METRICAS_TESTE
    dados_numericos = df[colunas_numericas].dropna()

    if len(dados_numericos) < 3:
        st.warning("Dados insuficientes para PCA.")
        return

    # Padroniza os dados
    scaler = StandardScaler()
    dados_padronizados = scaler.fit_transform(dados_numericos)

    # PCA para 2 componentes
    pca = PCA(n_components=2)
    componentes = pca.fit_transform(dados_padronizados)

    # Cria DataFrame para visualização
    df_pca = pd.DataFrame({
        "PC1": componentes[:, 0],
        "PC2": componentes[:, 1],
        "categoria": df.loc[dados_numericos.index, por].values,
    })

    fig, ax = plt.subplots(figsize=(10, 7))
    if por == "grupo":
        cores = [("ia", "#4A90D9"), ("humana", "#D97706")]
    else:
        categorias = sorted(df_pca["categoria"].unique())
        cores = list(zip(categorias, sns.color_palette("muted", len(categorias))))
    for categoria, cor in cores:
        subset = df_pca[df_pca["categoria"] == categoria]
        ax.scatter(subset["PC1"], subset["PC2"], label=str(categoria).upper(), alpha=0.6, color=cor, s=50)

    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} variância)", fontsize=12)
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} variância)", fontsize=12)
    ax.set_title("Distribuição das Interfaces no Espaço PCA 2D", fontsize=14)
    ax.legend(fontsize=11)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close()


def mostrar_galeria() -> None:
    """Mostra galeria com thumbnails das interfaces, separadas por grupo."""
    import streamlit as st

    st.subheader("Galeria de Interfaces")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Interfaces IA")
        imagens_ia = sorted([f for f in IA_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]])
        if imagens_ia:
            # Mostra até 12 thumbnails (4 linhas de 3)
            for i in range(0, min(12, len(imagens_ia)), 3):
                row = st.columns(3)
                for j in range(3):
                    if i + j < len(imagens_ia):
                        with row[j]:
                            st.image(str(imagens_ia[i + j]), use_container_width=True)
            if len(imagens_ia) > 12:
                st.info(f"A mostrar 12 de {len(imagens_ia)} interfaces IA.")
        else:
            st.warning("Sem interfaces IA disponíveis.")

    with col2:
        st.markdown("### Interfaces Humanas")
        imagens_h = sorted([f for f in HUMANAS_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]])
        if imagens_h:
            for i in range(0, min(12, len(imagens_h)), 3):
                row = st.columns(3)
                for j in range(3):
                    if i + j < len(imagens_h):
                        with row[j]:
                            st.image(str(imagens_h[i + j]), use_container_width=True)
            if len(imagens_h) > 12:
                st.info(f"A mostrar 12 de {len(imagens_h)} interfaces humanas.")
        else:
            st.warning("Sem interfaces humanas disponíveis.")


def exportar_pdf(df: pd.DataFrame) -> bytes:
    """Gera um relatório PDF com os resultados da análise.

    Args:
        df: DataFrame com os resultados.

    Returns:
        Bytes do PDF gerado.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Página de capa
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 40, "Relatório de Análise Visual", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, "Comparação: Interfaces IA vs Interfaces Humanas", ln=True, align="C")
    pdf.cell(0, 10, f"Data: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align="C")

    # Métricas gerais
    pdf.ln(20)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Métricas Gerais", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Total Interfaces IA: {len(df[df['grupo'] == 'ia'])}", ln=True)
    pdf.cell(0, 8, f"Total Interfaces Humanas: {len(df[df['grupo'] == 'humana'])}", ln=True)
    pdf.cell(0, 8, f"Total Analisadas: {len(df)}", ln=True)

    # Tabela de testes estatísticos
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Testes Estatísticos", ln=True)
    pdf.set_font("Helvetica", "", 9)

    tabela = calcular_testes_estatisticos(df)
    # Cabeçalho
    colunas = list(tabela.columns)
    larguras = [55, 30, 30, 35, 30]
    for col, larg in zip(colunas, larguras):
        pdf.cell(larg, 8, col[:20], border=1)
    pdf.ln()
    # Linhas
    for _, linha in tabela.iterrows():
        for col, larg in zip(colunas, larguras):
            valor = str(linha[col])[:20]
            pdf.cell(larg, 8, valor, border=1)
        pdf.ln()

    # Médias por grupo
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Médias por Grupo", ln=True)
    pdf.set_font("Helvetica", "", 10)
    medias = df.groupby("grupo")[METRICAS_TESTE].mean()
    for metrica in METRICAS_TESTE:
        ia_val = medias.loc["ia", metrica] if "ia" in medias.index else 0
        h_val = medias.loc["humana", metrica] if "humana" in medias.index else 0
        pdf.cell(0, 7, f"{DIMENSOES.get(metrica, metrica)}: IA={ia_val:.2f} | Humana={h_val:.2f}", ln=True)

    return bytes(pdf.output())


def mostrar_exportacao(df: pd.DataFrame) -> None:
    """Mostra botões de exportação em CSV e PDF.

    Args:
        df: DataFrame com os resultados.
    """
    import streamlit as st

    st.subheader("Exportar Resultados")

    col1, col2 = st.columns(2)

    with col1:
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Exportar CSV",
            data=csv_data,
            file_name="resultados_analise.csv",
            mime="text/csv",
        )

    with col2:
        try:
            pdf_bytes = exportar_pdf(df)
            st.download_button(
                label="Exportar PDF",
                data=pdf_bytes,
                file_name="relatorio_analise.pdf",
                mime="application/pdf",
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")


def adicionar_tipo(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a coluna "tipo" (tipo de página) a partir do nome do ficheiro.

    Ex.: "humana_landing_page_003.png" e "landing_page_003.png" dão
    "landing_page".

    Args:
        df: DataFrame com os resultados.

    Returns:
        DataFrame com a coluna "tipo".
    """
    df = df.copy()
    df["tipo"] = (
        df["ficheiro"]
        .str.replace(r"^humana_", "", regex=True)
        .str.replace(r"_\d+\.\w+$", "", regex=True)
    )
    return df


def mostrar_estatistica_descritiva(df: pd.DataFrame) -> None:
    """Mostra média, desvio-padrão, mediana, mínimo e máximo por grupo.

    Args:
        df: DataFrame com os resultados.
    """
    import streamlit as st

    st.subheader("Estatística Descritiva")
    tabela = (
        df.groupby("grupo")[METRICAS_TESTE]
        .agg(["mean", "std", "median", "min", "max"])
        .T.rename(index=DIMENSOES, level=0)
        .rename(index={"mean": "média", "std": "desvio-padrão", "median": "mediana",
                       "min": "mínimo", "max": "máximo"}, level=1)
    )
    st.dataframe(tabela.round(3), use_container_width=True)


def mostrar_dashboard(modo_teste: bool = False) -> None:
    """Função principal que renderiza o dashboard completo.

    Args:
        modo_teste: Se True, mostra os resultados mesmo com um só grupo,
            comparando os tipos de página em vez de IA vs humanos.
    """
    import streamlit as st

    st.header("Dashboard de Resultados")

    df = carregar_dados()
    if df is None or len(df) == 0:
        st.error("Nenhum resultado encontrado. Execute a análise primeiro.")
        return

    if modo_teste:
        df = adicionar_tipo(df)
        st.info(
            "Modo teste: resultados descritivos dos grupos disponíveis, com os "
            "tipos de página comparados entre si. Os testes IA vs humanos "
            "só aparecem com os dois grupos e o modo teste desligado."
        )
        mostrar_metricas_gerais(df)
        st.divider()
        mostrar_estatistica_descritiva(df)
        st.divider()
        gerar_boxplots(df, por="tipo")
        st.divider()
        gerar_scatter_pca(df, por="tipo")
        st.divider()
        mostrar_galeria()
        st.divider()
        mostrar_exportacao(df)
        return

    # Os gráficos e testes estatísticos comparam os dois grupos
    grupos = set(df["grupo"].unique())
    em_falta = {"ia", "humana"} - grupos
    if em_falta:
        nomes = {"ia": "IA", "humana": "humanas"}
        st.warning(
            f"Os resultados não incluem interfaces {' nem '.join(nomes[g] for g in sorted(em_falta))}. "
            "Gere as interfaces em falta e volte a correr a análise (secção 3)."
        )
        return

    mostrar_metricas_gerais(df)
    st.divider()
    gerar_boxplots(df)
    st.divider()
    gerar_graficos_barras(df)
    st.divider()
    mostrar_tabela_estatistica(df)
    st.divider()
    gerar_scatter_pca(df)
    st.divider()
    mostrar_galeria()
    st.divider()
    mostrar_exportacao(df)
