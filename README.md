# Camadas São Paulo

Mapa 3D interativo com as **68.684 edificações** dos dez distritos do centro de São Paulo (Sé, República, Bela Vista, Consolação, Santa Cecília, Bom Retiro, Brás, Pari, Liberdade e Cambuci), coloridas pelo ano de construção registrado no cadastro do IPTU e situadas na história urbana que as formou.

*An interactive 3D map of 68,684 buildings in downtown São Paulo, coloured by construction year from the municipal property-tax register. Available in Portuguese and English.*

## O que dá para fazer no mapa

- Arrastar a **linha do tempo** e ver o centro crescer ano a ano.
- Alternar entre **Período**, **Patrimônio** (bens tombados), **Pavimentos**, **Uso** e **Qualidade dos dados**.
- Clicar em qualquer edificação para ver ano, pavimentos, altura, uso, padrão e tombamento.
- Ler o contexto de 7 períodos históricos e 11 marcos (Pátio do Colégio, Theatro Municipal, Martinelli, Copan, Minhocão…).

## Principal achado de qualidade de dados

Os números abaixo contam edificações do mapa pelo ano do IPTU e são recalculados pelo site a partir do `data.json`.

- **O pico de 1970:** 9.628 edificações têm o ano 1970, contra 653 em 1969 e 964 em 1971 (cerca de 12 vezes a média dos anos vizinhos). O padrão sugere um valor provavelmente usado quando a data real não era conhecida, e não um surto de obras.
- **Anos em faixas de 5:** entre as edificações com ano de 1930 a 1959, 75% terminam em 4 ou 9 (com datas exatas, seriam cerca de 20%). Isso sugere que o "ano de construção corrigido" do IPTU agrupa prédios antigos em faixas de 5 anos.

## De onde vem o ano de cada edificação

O ano do IPTU é o "ano de construção corrigido" e pode refletir reformas. Por isso, o mapa segue uma hierarquia de fontes:

1. **Data histórica documentada**, para os marcos de referência que são edificações. As datas, os eventos (inauguração, conclusão, reconstrução) e as referências ficam em [`historical_dates.json`](historical_dates.json). No carregamento, cada data é aplicada à edificação cujo contorno contém o ponto do marco.
2. **Ano do IPTU 2026**, para as demais edificações.
3. **Sem data**, quando não há nenhum dos dois.

O cartão de cada edificação mostra a fonte da data e, quando a data histórica diverge, o ano registrado no IPTU. Por exemplo, o IPTU registra o Theatro Municipal (1911) como 1919 e a Estação da Luz (1901) como 2020. No Pátio do Colégio, 1554 é a fundação da cidade no local; o edifício atual é uma reconstrução concluída em 1979, e é esse o ano usado. O Minhocão está na lista de marcos, mas não é edificação e não altera nenhum ano.

**Edificações sem data** não entram na linha do tempo, porque não há como saber quando surgiram. Elas aparecem, em cinza, só na posição "Hoje", e também ficam fora das contagens enquanto a linha do tempo está em outro ano.

## Como foi feito

1. Recorte dos dez distritos do centro.
2. Download, pelo serviço WFS do GeoSampa, de 104.525 edificações (com altura), 72.443 lotes fiscais, quadras, distritos e 4.795 bens tombados.
3. Download do IPTU 2026 (3,9 milhões de linhas), filtro dos setores do centro e agregação por lote.
4. Junção lote ↔ IPTU pelo código fiscal (96% de correspondência).
5. Junção espacial edificação ↔ lote (97% das edificações com ano).
6. Estimativa de volume pelo lote para 935 prédios recentes ausentes do levantamento.
7. Marcação de patrimônio tombado (Conpresp, Condephaat, Iphan).
8. Verificação de marcos conhecidos e análise da distribuição dos anos.
9. Hierarquia das datas: data histórica documentada dos marcos (`historical_dates.json`) antes do ano do IPTU.
10. Visualização em 3D com [deck.gl](https://deck.gl).

Ferramentas: Python (GeoPandas, Shapely, pyproj) e JavaScript (deck.gl). Desenvolvido com apoio de IA (Claude); escolhas de fonte, recorte, validação e interpretação são da autora.

## Limitações

- Mostra apenas o que está de pé hoje; não inclui edificações demolidas.
- O ano do IPTU é o "ano de construção corrigido", que pode diferir da inauguração. Só os marcos de referência têm data histórica conferida.
- Cerca de 2 mil edificações (3%) não têm ano no cadastro, em geral imóveis públicos ou isentos. Elas ficam fora da linha do tempo e só aparecem em "Hoje".
- O uso mostrado é o declarado ao fisco, não a ocupação real.

## Fontes

- **GeoSampa**, Prefeitura de São Paulo: edificações, lotes, quadras, distritos e bens tombados (WFS), baixados em 14/10/2026.
- **IPTU 2026**, Secretaria Municipal da Fazenda, publicado no GeoSampa conforme o Decreto nº 56.701/2015.
- **Datas históricas dos marcos:** referências listadas em `historical_dates.json`.
- Inspiração: [LAYRS: Amsterdam](https://stop-token.com/lab/amsterdam/), de Alex Barakov.

Os dados seguem os termos de uso do GeoSampa. O código está sob licença MIT (veja `LICENSE`).

## Autora

**Thais Adeodato**, arquiteta e urbanista, governança de dados.
[LinkedIn](https://www.linkedin.com/in/thais-morais-adeodato-porto/) · [Instagram](https://www.instagram.com/thais.adeodato/)
