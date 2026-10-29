# Camadas São Paulo

Mapa 3D interativo com as **2.789.795 edificações** dos 96 distritos de São Paulo, coloridas pelo ano de construção registrado no cadastro do IPTU e situadas na história urbana que as formou.

**No ar:** https://thaisadeodato-k.github.io/camadas-sp/

*An interactive 3D map of all 2,789,795 buildings in São Paulo's 96 districts, coloured by construction year from the municipal property-tax register (IPTU). Available in Portuguese and English. The data is rebuilt automatically when the city's open-data sources change.*

## O que dá para fazer no mapa

- Ver a cidade em três escalas: de longe, os **96 distritos** (cor = ano médio, altura = densidade construída); ao aproximar, **17.107 hexágonos de 150 m** com as mesmas medidas; depois, **cada quadra como um volume** (altura média das suas edificações, e as de 30 m ou mais inteiras); mais perto, as **próprias edificações** em 3D.
- Escolher uma **área** (regiões ou distritos): só as edificações dela aparecem e são baixadas, o que deixa o mapa mais rápido; fora dela, a cidade fica em quadras.
- Arrastar a **linha do tempo** e ver a cidade crescer ano a ano.
- Alternar entre **Período**, **Patrimônio** (bens tombados), **Pavimentos**, **Uso** e **Qualidade dos dados**.
- Buscar um distrito, abrir a **tabela dos 96 distritos** e clicar numa edificação para ver ano, fonte da data, pavimentos, uso, padrão e tombamento.

## Principais achados de qualidade de dados

Todos os números vêm do relatório gerado pelo pipeline (`linha_de_base.json`, publicado na [release "dados"](https://github.com/thaisadeodato-k/camadas-sp/releases/tag/dados)).

- **95,0%** das edificações estão dentro de um lote fiscal e **89,5%** têm ano de construção no IPTU. **98,1%** dos 1.687.733 lotes se ligam ao IPTU.
- **O pico de 1970:** 217.905 edificações têm o ano 1970, contra 12.652 em 1969 e 38.747 em 1971 (8,5 vezes a média dos anos vizinhos). O padrão sugere um valor usado quando a data real não era conhecida, e não um surto de obras.
- **Anos em faixas de 5:** entre as edificações com ano de 1930 a 1959, 76,6% têm ano terminado em 4 ou 9; de 1980 a 2019, são 20,2%, perto dos 20% esperados. O "ano de construção corrigido" do IPTU parece agrupar prédios antigos em faixas de 5 anos.
- **Onde falta o ano:** 140.139 edificações estão fora de qualquer lote fiscal, e 111.001 delas ficam em favela, loteamento irregular ou ZEIS-1. Os distritos com menos edificações datadas são os do extremo sul e leste (Parelheiros 34,2%, Grajaú 56,2%).

## De onde vem o ano de cada edificação

O ano do IPTU é o "ano de construção corrigido" e pode refletir reformas. Por isso, o mapa segue uma hierarquia de fontes:

1. **Data histórica documentada**, para os marcos de referência que são edificações. As datas, os eventos (inauguração, conclusão, reconstrução) e as referências ficam em [`historical_dates.json`](historical_dates.json). Cada data vale para a edificação cujo contorno contém o ponto do marco.
2. **Ano do IPTU**, para as demais edificações. Quando um lote tem várias unidades, vale o ano mais antigo.
3. **Sem data**, quando não há nenhum dos dois.

O cartão de cada edificação mostra a fonte da data e, quando a data histórica diverge, o ano registrado no IPTU. Por exemplo, o IPTU registra o Theatro Municipal (1911) como 1919 e a Estação da Luz (1901) como 2020.

**Edificações sem data** (293.304) não entram na linha do tempo, porque não há como saber quando surgiram. Elas aparecem em cinza só na posição "Hoje".

## Como foi feito

O pipeline (`pipeline/`) roda sem intervenção e guarda o progresso: se for interrompido, continua de onde parou.

1. **Fontes** (`camadas.py`): lê a data de atualização de cada fonte no catálogo de metadados do GeoSampa e na pasta de downloads do IPTU, e grava tudo, com o hash de cada arquivo, em `cache/fontes.json`.
2. **IPTU:** baixa o cadastro completo da cidade (3,9 milhões de linhas) e agrega por lote, ou por condomínio.
3. **Camadas do GeoSampa (WFS):** distrito por distrito, em quadrículas de 1 km, baixa edificações (com altura), lotes fiscais, quadras, bens tombados, favelas e loteamentos irregulares. As ZEIS-1 vêm de uma vez para a cidade inteira.
4. **Cruzamentos:** lote ↔ IPTU pelo código fiscal; edificação ↔ lote pela posição. Quando o ponto da edificação cai em mais de um lote, vale o lote que tem ano no IPTU. Prédios recentes ausentes do levantamento (8.675) têm o volume estimado pelo lote.
5. **Relatório** (`resumo.py`): métricas de qualidade por distrito e a linha de base usada nos controles.
6. **Arquivos do site** (`gera_site.py`): resumo por distrito (`distritos.json`), hexágonos (`hexagonos.json`), bens tombados (`tombados.json`), a vista de longe por quadras (`quadras_longe.bin`, cerca de 4 MB) e a entrada dos blocos de mapa.
7. **Blocos de mapa:** [tippecanoe](https://github.com/felt/tippecanoe) gera `edificacoes.pmtiles` (cerca de 260 MB), lido pelo site aos pedaços. `mede_blocos.py` mostra o tamanho dos blocos de cada nível.
8. **Visualização:** [deck.gl](https://deck.gl) e [PMTiles](https://github.com/protomaps/PMTiles), num único `index.html`, sem etapa de build.

Ferramentas: Python (GeoPandas, Shapely, pyproj, pandas), tippecanoe e JavaScript (deck.gl, PMTiles). Desenvolvido com apoio de IA (Claude); escolhas de fonte, recorte, validação e interpretação são da autora.

### Rodar no próprio computador

```bash
python -m venv .venv
.venv/Scripts/pip install -r pipeline/requirements.txt   # no Linux/Mac: .venv/bin/pip

# alguns distritos, para testar
python pipeline/camadas.py --distritos "JARDIM ANGELA" PERUS
# a cidade inteira (cerca de 1h30 e 2 GB de cache)
python pipeline/camadas.py --todos
python pipeline/resumo.py
python pipeline/gera_site.py distritos
python pipeline/gera_site.py tombados
python pipeline/gera_site.py hexagonos
python pipeline/gera_site.py longe
python pipeline/gera_site.py tiles        # depois, tippecanoe (veja .github/workflows/gera-dados.yml)
```

Para ver o site localmente, o servidor precisa aceitar requisições parciais (HTTP Range), que o PMTiles usa; o `python -m http.server` não aceita. Os arquivos de dados ficam na raiz do projeto, e o `edificacoes.pmtiles`, em `tiles/`.

## Atualização automática

Dois workflows do GitHub Actions mantêm o site em dia:

- **`gera-dados.yml`**, todo dia 5 de cada mês:
  1. `verifica_fontes.py` confere, em poucos segundos e sem baixar os dados, se alguma fonte mudou: o arquivo do IPTU (tamanho e data), e as datas no catálogo de metadados e o número de feições de cada camada do GeoSampa. Se nada mudou, só registra a data da verificação. Depois de 180 dias sem download completo, baixa tudo de novo mesmo assim.
  2. Se algo mudou, roda o pipeline, baixando de novo só as fontes que mudaram.
  3. `controle.py` confere o resultado antes de publicar: pelo menos 90% dos lotes ligados ao IPTU em cada distrito e na cidade; total de edificações sem variar mais de 5% em relação à publicação anterior; os 96 distritos presentes.
  4. Se tudo passar, os arquivos vão para a [release "dados"](https://github.com/thaisadeodato-k/camadas-sp/releases/tag/dados) e a atualização é registrada no [CHANGELOG](CHANGELOG.md). Se algum controle falhar, nada é publicado e uma issue explica o motivo.
  5. Quando o GeoSampa publicar o IPTU de um ano novo, uma issue avisa: a troca de ano pede revisão manual.
- **`publica-site.yml`** monta o site com o `index.html` e os arquivos da release, e publica no GitHub Pages. Os dados não entram no histórico do Git, porque o arquivo dos prédios passa do limite de 100 MB.

O site mostra a data de processamento dos dados e a da última verificação das fontes. Nenhuma senha ou chave é necessária: os workflows usam só a permissão padrão do próprio repositório.

## Limitações

- Mostra apenas o que está de pé no levantamento de edificações; não inclui edificações demolidas.
- O levantamento de edificações do GeoSampa ("Edificações 2D") é antigo: a publicação nos metadados é de 2004 e a última alteração registrada nos dados, de 2014. Prédios mais novos só aparecem quando o lote tem ano no IPTU (com volume estimado pelo lote), e mudanças recentes de forma não aparecem.
- Marsilac não está coberto pelo levantamento (4 edificações) e aparece sem dados.
- O ano do IPTU é o "ano de construção corrigido", que pode diferir da inauguração. Só os marcos de referência têm data histórica conferida.
- Edificações em favelas, loteamentos irregulares e ZEIS-1 muitas vezes ficam fora do cadastro fiscal e, por isso, sem ano. A camada "Qualidade dos dados" mostra onde isso acontece.
- O uso mostrado é o declarado ao fisco, não a ocupação real.
- Os textos dos períodos e os marcos tratam da história do centro.

## Fontes

Datas da versão publicada (o site mostra as datas atualizadas, em "Sobre e método" → "Fontes"):

- **[GeoSampa](https://geosampa.prefeitura.sp.gov.br)**, Prefeitura de São Paulo (SMUL/Prodam): edificações, lotes fiscais, quadras, bens tombados, favelas e loteamentos irregulares, pelo serviço WFS. Baixados em 17 e 18/10/2026.
- **ZEIS-1:** perímetros de zona do Mapa 1 da Lei 18.081/2024 (GeoSampa).
- **IPTU 2026:** cadastro imobiliário fiscal da Secretaria Municipal da Fazenda, publicado no GeoSampa conforme o [Decreto nº 56.701/2015](https://prefeitura.sp.gov.br/web/licenciamento/w/disponibiliza%C3%A7%C3%A3o-do-cadastro-fiscal). Arquivo `IPTU_2026.zip`, atualizado no servidor em 11/02/2026, baixado em 17/10/2026.
- **Distritos:** camada de distritos municipais do GeoSampa.
- **População:** IBGE, Censo Demográfico 2022, tabela 9923 (SIDRA).
- **Patrimônio:** camada de bens tombados do GeoSampa (DPH/SMC), com resoluções do Conpresp, Condephaat e Iphan.
- **Datas históricas dos marcos:** referências listadas em `historical_dates.json`.
- Inspiração: [LAYRS: Amsterdam](https://stop-token.com/lab/amsterdam/), de Alex Barakov, inspirado em *Paris, building by building*, de Sasha Bogachev.

Os dados são usados com citação das fontes e seguem os termos de uso do GeoSampa e do IBGE. O código está sob licença MIT (veja `LICENSE`).

## Autora

**Thais Adeodato**, arquiteta e urbanista, governança de dados.
[LinkedIn](https://www.linkedin.com/in/thais-morais-adeodato-porto/) · [Instagram](https://www.instagram.com/thais.adeodato/)
