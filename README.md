# Ferramenta de Investigação Académica: IA vs Designers Humanos

Ferramenta de investigação académica que compara interfaces web geradas por IA com interfaces desenhadas por designers humanos, analisando o grau de padronização visual entre os dois grupos.

## Funcionalidades

A aplicação tem 4 secções principais acessíveis por menu lateral:

### 1. Geração de Interfaces IA
- Campo para introduzir a API key da Anthropic
- Gera 120 interfaces web em HTML/CSS usando o Claude (modelo claude-sonnet-4-6), 30 de cada tipo: landing page, dashboard, formulário de contacto, página de produto
- As prompts enviadas ao Claude não contêm especificações visuais — apenas o tipo de página
- Cada interface é renderizada com Playwright e capturada como screenshot em 1440x900
- Barra de progresso em tempo real
- Screenshots guardados em `data/ia/`

### 2. Scraping do Behance
- Scraping automático com Playwright + BeautifulSoup
- Critérios de inclusão: categoria Web Design, publicadas entre 2022 e 2026, mínimo 100 appreciations
- Critérios de exclusão: projetos que mencionem IA, Midjourney, DALL-E, Stable Diffusion, ChatGPT
- Scroll automático para carregar mais projetos
- Download automático das imagens principais
- Barra de progresso e log em tempo real
- Imagens guardadas em `data/humanas/`
- Objetivo: 120 interfaces

### 3. Análise Visual Automática
- Análise de cada imagem em 4 dimensões usando OpenCV e scikit-learn:
  - **Paleta cromática:** 5 cores dominantes com K-means, variância cromática, deteção de gradientes
  - **Layout:** contornos e blocos com Canny, número de blocos, variância de áreas, densidade
  - **Tipografia:** zonas de texto com pytesseract, níveis hierárquicos, variância de tamanhos
  - **Hierarquia visual:** distribuição de saliência visual, dispersão de elementos
- Barra de progresso por imagem
- Resultados guardados em `data/resultados/resultados.csv`

### 4. Dashboard de Resultados
- Métricas gerais (total por grupo, data da análise)
- Boxplots comparando os dois grupos em cada dimensão
- Gráficos de barras com médias por grupo
- Tabela de testes estatísticos (Levene para variâncias, Mann-Whitney U para médias, com p-values)
- Scatter plot PCA (distribuição 2D dos dois grupos)
- Galeria de thumbnails separadas por grupo
- Exportação em CSV e PDF

## Instalação

### Pré-requisitos

- Python 3.10 ou superior
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) instalado no sistema
  - Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
  - macOS: `brew install tesseract`
  - Windows: Descarregar o instalador do repositório oficial

### Passos

1. Clonar o repositório e entrar no diretório:
   ```bash
   cd projeto
   ```

2. Criar um ambiente virtual e ativar:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # ou: venv\Scripts\activate  # Windows
   ```

3. Instalar as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Instalar o browser do Playwright:
   ```bash
   playwright install chromium
   ```

## Uso

Executar a aplicação:
```bash
streamlit run app.py
```

A aplicação abre no browser em `http://localhost:8501`.

### Fluxo de utilização

1. **Geração IA:** Navegar para a secção "1. Geração de Interfaces IA", introduzir a API key da Anthropic e clicar em "Gerar Interfaces IA". O processo gera 120 interfaces e tira screenshots.

2. **Scraping Behance:** Navegar para a secção "2. Scraping do Behance" e clicar em "Iniciar Scraping". O processo recolhe interfaces humanas do Behance.

3. **Análise Visual:** Após ambos os corpus estarem completos, navegar para "3. Análise Visual Automática" e clicar em "Iniciar Análise". Cada imagem é analisada nas 4 dimensões.

4. **Dashboard:** Após a análise estar completa, navegar para "4. Dashboard de Resultados" para visualizar gráficos, testes estatísticos e exportar resultados.

### Estado persistente

A aplicação guarda o estado entre sessões em `data/estado.json`. Se o scraping ou a geração já foram concluídos, não é necessário repetir. As imagens e resultados também são guardados localmente, pelo que podem retomar o trabalho a qualquer momento.

## Estrutura do Projeto

```
projeto/
├── app.py                      # Aplicação principal (Streamlit)
├── requirements.txt            # Dependências Python
├── README.md                   # Este ficheiro
├── src/
│   ├── state.py                # Gestão de estado persistente
│   ├── ia_generation.py        # Geração de interfaces com Claude
│   ├── behance_scraper.py      # Scraping do Behance
│   ├── visual_analysis.py      # Análise visual (OpenCV, scikit-learn)
│   └── dashboard.py            # Dashboard de resultados e gráficos
└── data/
    ├── estado.json              # Estado persistente (gerado automaticamente)
    ├── ia/                      # Screenshots de interfaces IA
    ├── humanas/                 # Imagens de interfaces humanas
    └── resultados/
        └── resultados.csv      # Resultados da análise
```

## Dependências

- **Streamlit** — interface web
- **Anthropic** — API do Claude
- **Playwright** — browser automation e screenshots
- **BeautifulSoup4 + lxml** — parsing HTML
- **OpenCV** — análise de imagem (contornos, Canny)
- **scikit-learn** — K-means, PCA
- **pytesseract** — OCR para deteção de texto
- **Pillow** — manipulação de imagens
- **pandas + scipy** — dados e estatísticas
- **matplotlib + seaborn** — gráficos
- **fpdf2** — exportação PDF

## Notas

- A API key da Anthropic não é armazenada — é usada apenas durante a sessão.
- O scraping do Behance pode ser lento devido ao scroll automático e aos downloads.
- O Tesseract OCR precisa de estar instalado no sistema (não apenas o pacote Python).
- Para a análise estatística, são usados testes não paramétricos (Mann-Whitney U) por não se assumir normalidade dos dados.
