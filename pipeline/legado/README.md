# Pipeline de dados — como o `data.json` foi gerado

O `data.json` do site é gerado em 4 etapas. As etapas 1 a 3 rodam em Python.

| Etapa | Arquivo | O que faz | Entrada | Saída |
|---|---|---|---|---|
| 0 | `00_extract_browser.js` | Extrai os dados do GeoSampa no navegador (o portal bloqueia acesso automatizado fora de um navegador comum). | GeoSampa (WFS) e IPTU 2026 | `sp_geometria.json.gz`, `sp_iptu_centro.csv.gz` |
| 1 | `01_prep.py` | Converte as geometrias em tabelas geoespaciais (EPSG:31983). | `sp_geometria.json.gz` | `L/E/D/T/Q/A.parquet` |
| 2 | `02_join.py` | Liga IPTU → lote pelo código fiscal (condomínios por setor+quadra+condomínio), recorta os 10 distritos e liga edificação → lote por junção espacial. | parquets + `sp_iptu_centro.csv.gz` | `E2.parquet`, `L2.parquet` |
| 3 | `03_build.py` | Estima volume pelo lote para prédios novos (2008+, 4+ pavimentos), marca patrimônio tombado, converte para metros locais e compacta. | `E2/L2/T/Q/D.parquet` | `data.json` |

## Como reproduzir

1. Rode os blocos A e B de `00_extract_browser.js` no Console do navegador, cada um na aba indicada no arquivo. Coloque os dois `.gz` baixados nesta pasta.
2. Instale as dependências: `pip install -r requirements.txt`
3. Rode em sequência:
   ```
   python 01_prep.py
   python 02_join.py
   python 03_build.py
   ```
4. Copie o `data.json` gerado para a raiz do repositório.

## Decisões de método

- **Ano por lote:** em condomínios, vale o ano mais antigo entre as unidades.
- **Edificação ↔ lote:** cada edificação recebe o ano do lote que contém o seu ponto interno (`representative_point`).
- **Sem ano:** edificações sem ano no IPTU ficam com ano 0 e aparecem em cinza.
- **Volume estimado:** em lotes com prédio de 2008 ou depois, com pelo menos 4 pavimentos e mais altos que o contorno levantado, o volume vem do próprio lote (3 m por pavimento).

Os dados brutos não estão no repositório. Eles seguem os termos de uso do GeoSampa e podem ser baixados de novo com a etapa 0.
