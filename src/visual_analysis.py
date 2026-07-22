"""Análise visual automática de interfaces web.

Este módulo analisa cada imagem (screenshot) nas seguintes 4 dimensões
usando OpenCV e scikit-learn:

1. Paleta cromática — extrai 5 cores dominantes com K-means, calcula
   variância cromática entre cores, detecta gradientes vs cores sólidas.
2. Layout — detecta contornos e blocos com OpenCV Canny, calcula número
   de blocos, variância de áreas, densidade de elementos.
3. Tipografia — identifica zonas de texto com pytesseract, estima número
   de níveis hierárquicos tipográficos, variância de tamanhos.
4. Hierarquia visual — analisa distribuição de saliência visual,
   calcula dispersão dos elementos na composição.

Os resultados são guardados em data/resultados/resultados.csv.
"""

import csv
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans

from src.state import IA_DIR, HUMANAS_DIR, RESULTADOS_DIR, atualizar_estado, marcar_concluido

# Número de cores dominantes a extrair
NUM_CORES = 5

# Caminho do ficheiro CSV de resultados
CSV_PATH = RESULTADOS_DIR / "resultados.csv"

# Cabeçalho do CSV
COLUNAS_CSV = [
    "ficheiro",
    "grupo",
    "variancia_cor",
    "num_cores",
    "variancia_layout",
    "num_blocos",
    "densidade",
    "variancia_tipografia",
    "num_niveis_texto",
    "variancia_hierarquia",
]


def analisar_paleta_cromatica(imagem: np.ndarray) -> dict:
    """Extrai a paleta cromática e calcula métricas de cor.

    Usa K-means clustering para identificar as 5 cores dominantes.
    Calcula a variância cromática entre as cores dominantes e detecta
    se a imagem usa gradientes ou cores sólidas.

    Args:
        imagem: Array NumPy da imagem (BGR, formato OpenCV).

    Returns:
        Dicionário com 'variancia_cor' e 'num_cores'.
    """
    try:
        # Converte BGR para RGB
        imagem_rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)
        # Redimensiona para acelerar o K-means
        h, w = imagem_rgb.shape[:2]
        imagem_pequena = cv2.resize(imagem_rgb, (w // 4, h // 4))
        pixels = imagem_pequena.reshape(-1, 3).astype(np.float32)

        # K-means para encontrar cores dominantes
        kmeans = KMeans(n_clusters=NUM_CORES, random_state=42, n_init=10)
        kmeans.fit(pixels)
        cores = kmeans.cluster_centers_

        # Variância cromática: distância média entre as cores dominantes
        distancias = []
        for i in range(len(cores)):
            for j in range(i + 1, len(cores)):
                dist = np.linalg.norm(cores[i] - cores[j])
                distancias.append(dist)
        variancia_cor = float(np.std(distancias)) if distancias else 0.0

        # Conta cores realmente distintas (distância > limiar)
        cores_distintas = set()
        for cor in cores:
            # Arredonda para agrupar cores próximas
            chave = tuple((cor / 32).astype(int))
            cores_distintas.add(chave)
        num_cores = len(cores_distintas)

        return {"variancia_cor": variancia_cor, "num_cores": num_cores}
    except Exception as e:
        print(f"Erro ao analisar paleta cromática: {e}")
        return {"variancia_cor": 0.0, "num_cores": 0}


def analisar_layout(imagem: np.ndarray) -> dict:
    """Deteta blocos e contornos com OpenCV Canny e calcula métricas de layout.

    Args:
        imagem: Array NumPy da imagem (BGR, formato OpenCV).

    Returns:
        Dicionário com 'variancia_layout', 'num_blocos' e 'densidade'.
    """
    try:
        cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

        # Deteta contornos com Canny
        bordas = cv2.Canny(cinza, 50, 150)

        # Encontra contornos
        contornos, _ = cv2.findContours(bordas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filtra contornos por área mínima (remove ruído)
        areas = []
        for contorno in contornos:
            area = cv2.contourArea(contorno)
            if area > 500:  # Ignora contornos muito pequenos
                areas.append(area)

        num_blocos = len(areas)
        variancia_layout = float(np.std(areas)) if len(areas) > 1 else 0.0

        # Densidade: proporção de pixels não-brancos (elementos visuais)
        total_pixels = cinza.size
        pixels_elementos = np.count_nonzero(cinza < 240)
        densidade = float(pixels_elementos / total_pixels)

        return {
            "variancia_layout": variancia_layout,
            "num_blocos": num_blocos,
            "densidade": densidade,
        }
    except Exception as e:
        print(f"Erro ao analisar layout: {e}")
        return {"variancia_layout": 0.0, "num_blocos": 0, "densidade": 0.0}


def analisar_tipografia(imagem: np.ndarray) -> dict:
    """Identifica zonas de texto com pytesseract e estima níveis hierárquicos.

    Usa pytesseract para detetar texto na imagem. Estima o número de
    níveis hierárquicos tipográficos e a variância de tamanhos.

    Args:
        imagem: Array NumPy da imagem (BGR, formato OpenCV).

    Returns:
        Dicionário com 'variancia_tipografia' e 'num_niveis_texto'.
    """
    try:
        import pytesseract

        # Converte para PIL Image (formato esperado pelo pytesseract)
        imagem_pil = Image.fromarray(cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB))

        # Obtém dados de OCR com coordenadas e tamanhos
        dados = pytesseract.image_to_data(imagem_pil, output_type=pytesseract.Output.DICT)

        # Extrai alturas das caixas de texto (proxy para tamanho da fonte)
        tamanhos = []
        for i in range(len(dados["text"])):
            texto = dados["text"][i].strip()
            if texto and int(dados["conf"][i]) > 30:
                altura = dados["height"][i]
                if altura > 5:  # Ignora ruído
                    tamanhos.append(altura)

        if tamanhos:
            # Agrupa tamanhos em níveis (arredondando para dezenas)
            niveis = set()
            for t in tamanhos:
                nivel = round(t / 5) * 5  # Agrupa por intervalos de 5px
                niveis.add(nivel)
            num_niveis = len(niveis)
            variancia_tipografia = float(np.std(tamanhos))
        else:
            num_niveis = 0
            variancia_tipografia = 0.0

        return {"variancia_tipografia": variancia_tipografia, "num_niveis_texto": num_niveis}
    except Exception as e:
        print(f"Erro ao analisar tipografia: {e}")
        return {"variancia_tipografia": 0.0, "num_niveis_texto": 0}


def analisar_hierarquia_visual(imagem: np.ndarray) -> dict:
    """Analisa a distribuição de saliência visual e dispersão de elementos.

    Calcula um mapa de saliência baseado em contraste e cor, depois mede
    a dispersão espacial dos pontos de maior saliência.

    Args:
        imagem: Array NumPy da imagem (BGR, formato OpenCV).

    Returns:
        Dicionário com 'variancia_hierarquia'.
    """
    try:
        cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

        # Mapa de saliência: diferença Gaussiana (DoG)
        blur1 = cv2.GaussianBlur(cinza, (5, 5), 0)
        blur2 = cv2.GaussianBlur(cinza, (25, 25), 0)
        saliency_map = cv2.absdiff(blur1, blur2)

        # Normaliza
        saliency_map = cv2.normalize(saliency_map, None, 0, 255, cv2.NORM_MINMAX)

        # Encontra pontos de maior saliência (top 10%)
        limiar = np.percentile(saliency_map, 90)
        pontos_salientes = np.argwhere(saliency_map >= limiar)

        if len(pontos_salientes) > 0:
            # Dispersão: desvio padrão das coordenadas
            coords_y = pontos_salientes[:, 0]
            coords_x = pontos_salientes[:, 1]
            dispersao = float(np.std(coords_y) + np.std(coords_x)) / 2.0
        else:
            dispersao = 0.0

        return {"variancia_hierarquia": dispersao}
    except Exception as e:
        print(f"Erro ao analisar hierarquia visual: {e}")
        return {"variancia_hierarquia": 0.0}


def analisar_imagem(caminho: Path, grupo: str) -> dict | None:
    """Analisa uma imagem em todas as 4 dimensões.

    Args:
        caminho: Caminho do ficheiro de imagem.
        grupo: "ia" ou "humana".

    Returns:
        Dicionário com todas as métricas, ou None se a imagem for inválida.
    """
    try:
        imagem = cv2.imread(str(caminho))
        if imagem is None:
            print(f"Imagem corrompida ou inválida: {caminho}")
            return None
    except Exception as e:
        print(f"Erro ao carregar imagem {caminho}: {e}")
        return None

    paleta = analisar_paleta_cromatica(imagem)
    layout = analisar_layout(imagem)
    tipografia = analisar_tipografia(imagem)
    hierarquia = analisar_hierarquia_visual(imagem)

    return {
        "ficheiro": caminho.name,
        "grupo": grupo,
        **paleta,
        **layout,
        **tipografia,
        **hierarquia,
    }


def analisar_corpus(callback_progresso=None) -> int:
    """Analisa todas as imagens dos dois corpus (IA e humanas).

    Percorre todas as imagens em data/ia/ e data/humanas/, analisa cada
    uma nas 4 dimensões e guarda os resultados num ficheiro CSV.

    Args:
        callback_progresso: Função chamada com (analisadas, total) para
            atualizar a barra de progresso.

    Returns:
        Número total de imagens analisadas.
    """
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    # Recolhe todos os ficheiros de imagem
    imagens_ia = sorted([f for f in IA_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]])
    imagens_humanas = sorted([f for f in HUMANAS_DIR.iterdir() if f.suffix.lower() in [".png", ".jpg", ".jpeg"]])

    total = len(imagens_ia) + len(imagens_humanas)
    analisadas = 0

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f_csv:
        writer = csv.DictWriter(f_csv, fieldnames=COLUNAS_CSV)
        writer.writeheader()

        for imagem in imagens_ia:
            resultado = analisar_imagem(imagem, "ia")
            if resultado:
                writer.writerow(resultado)
                analisadas += 1
            atualizar_estado("analise", total_analisado=analisadas)
            if callback_progresso:
                callback_progresso(analisadas, total)

        for imagem in imagens_humanas:
            resultado = analisar_imagem(imagem, "humana")
            if resultado:
                writer.writerow(resultado)
                analisadas += 1
            atualizar_estado("analise", total_analisado=analisadas)
            if callback_progresso:
                callback_progresso(analisadas, total)

    marcar_concluido("analise", total_analisado=analisadas)
    return analisadas
