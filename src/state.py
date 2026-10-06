"""Gestão de estado persistente entre sessões da aplicação.

Este módulo garante que o estado da aplicação sobrevive entre sessões,
armazenando metadados em ficheiros JSON locais. Isto permite que, por
exemplo, o scraping do Behance não precise de ser refeito se já foi
concluído numa sessão anterior.
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent.parent

# Diretório de dados
DATA_DIR = BASE_DIR / "data"
IA_DIR = DATA_DIR / "ia"
HUMANAS_DIR = DATA_DIR / "humanas"
RESULTADOS_DIR = DATA_DIR / "resultados"
CSV_PATH = RESULTADOS_DIR / "resultados.csv"

# Ficheiro de estado persistente
STATE_FILE = DATA_DIR / "estado.json"

# Estrutura padrão do estado
ESTADO_PADRAO = {
    "ia": {
        "concluido": False,
        "total": 0,
        "tipos": {},  # ex: {"landing_page": 30, "dashboard": 30, ...}
        "ultima_atualizacao": None,
    },
    "behance": {
        "concluido": False,
        "total": 0,
        "ultima_atualizacao": None,
    },
    "analise": {
        "concluido": False,
        "total_analisado": 0,
        "ultima_atualizacao": None,
    },
}


def garantir_diretorios() -> None:
    """Cria os diretórios necessários caso não existam."""
    for diretorio in [DATA_DIR, IA_DIR, HUMANAS_DIR, RESULTADOS_DIR]:
        diretorio.mkdir(parents=True, exist_ok=True)


def carregar_estado() -> dict:
    """Carrega o estado persistente a partir do ficheiro JSON.

    Returns:
        Dicionário com o estado atual. Se não existir ficheiro, retorna o
        estado padrão.
    """
    garantir_diretorios()
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                estado = json.load(f)
            # Mescla com o padrão para garantir chaves novas
            for chave, valor in ESTADO_PADRAO.items():
                estado.setdefault(chave, valor)
                for sub_chave, sub_valor in valor.items():
                    estado[chave].setdefault(sub_chave, sub_valor)
            return estado
        except (json.JSONDecodeError, IOError):
            pass
    return ESTADO_PADRAO.copy()


def guardar_estado(estado: dict) -> None:
    """Persiste o estado atual no ficheiro JSON.

    Args:
        estado: Dicionário de estado a guardar.
    """
    garantir_diretorios()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)


def marcar_concluido(seccao: str, **dados_extra) -> None:
    """Marca uma secção como concluída e regista a data/hora.

    Args:
        seccao: Nome da secção ("ia", "behance", "analise").
        **dados_extra: Campos adicionais a atualizar na secção.
    """
    estado = carregar_estado()
    if seccao in estado:
        estado[seccao]["concluido"] = True
        estado[seccao]["ultima_atualizacao"] = datetime.now().isoformat()
        for chave, valor in dados_extra.items():
            estado[seccao][chave] = valor
        guardar_estado(estado)


def atualizar_estado(seccao: str, **dados_extra) -> None:
    """Atualiza campos de uma secção sem marcar como concluído.

    Args:
        seccao: Nome da secção.
        **dados_extra: Campos a atualizar.
    """
    estado = carregar_estado()
    if seccao in estado:
        for chave, valor in dados_extra.items():
            estado[seccao][chave] = valor
        guardar_estado(estado)


def contar_ficheiros(diretorio: Path) -> int:
    """Conta o número de ficheiros num diretório.

    Args:
        diretorio: Caminho do diretório.

    Returns:
        Número de ficheiros (apenas ficheiros, não diretórios).
    """
    if not diretorio.exists():
        return 0
    return len([f for f in diretorio.iterdir() if f.is_file()])


def obter_progresso(seccao: str) -> int:
    """Obtém o progresso atual de uma secção contando ficheiros.

    Args:
        seccao: "ia" ou "humanas".

    Returns:
        Número de ficheiros no diretório correspondente.
    """
    if seccao == "ia":
        return contar_ficheiros(IA_DIR)
    elif seccao == "humanas":
        return contar_ficheiros(HUMANAS_DIR)
    return 0
