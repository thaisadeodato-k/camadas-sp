# Camadas São Paulo

Mapa 3D interativo com as **68.684 edificações** dos dez distritos do centro de São Paulo (Sé, República, Bela Vista, Consolação, Santa Cecília, Bom Retiro, Brás, Pari, Liberdade e Cambuci), coloridas pelo ano de construção registrado no cadastro do IPTU e situadas na história urbana que as formou.

*An interactive 3D map of 68,684 buildings in downtown São Paulo, coloured by construction year from the municipal property-tax register. Available in Portuguese and English.*

## O que dá para fazer no mapa

- Arrastar a **linha do tempo** e ver o centro crescer ano a ano.
- Alternar entre **Período**, **Patrimônio** (bens tombados), **Pavimentos**, **Uso** e **Qualidade dos dados**.
- Clicar em qualquer edificação para ver ano, pavimentos, altura, uso, padrão e tombamento.
- Ler o contexto de 7 períodos históricos e 11 marcos (Pátio do Colégio, Theatro Municipal, Martinelli, Copan, Minhocão…).

## Principal achado de qualidade de dados

- **O pico de 1970:** 9.628 edificações têm o ano 1970, cerca de 12 vezes a média de 1969 e 1971. Tudo indica um valor padrão do cadastro, não um surto de obras.
- **Anos em faixas de 5:** entre 1930 e 1959, 75% dos anos terminam em 4 ou 9 (o esperado seria cerca de 20%). O "ano de construção corrigido" do IPTU agrupa prédios antigos em faixas de 5 anos.

## Como foi feito

1. Recorte dos dez distritos do centro.
2. Download, pelo serviço WFS do GeoSampa, de 104.525 edificações (com altura), 72.443 lotes fiscais, quadras, distritos e 4.795 bens tombados.
3. Download do IPTU 2026 (3,9 milhões de linhas), filtro dos setores do centro e agregação por lote.
4. Junção lote ↔ IPTU pelo código fiscal (96% de correspondência).
5. Junção espacial edificação ↔ lote (97% das edificações com ano).
6. Estimativa de volume pelo lote para 935 prédios recentes ausentes do levantamento.
7. Marcação de patrimônio tombado (Conpresp, Condephaat, Iphan).
8. Verificação de marcos conhecidos e análise da distribuição dos anos.
9. Visualização em 3D com [deck.gl](https://deck.gl).

Ferramentas: Python (GeoPandas, Shapely, pyproj) e JavaScript (deck.gl). Desenvolvido com apoio de IA (Claude); escolhas de fonte, recorte, validação e interpretação são da autora.

## Limitações

- Mostra apenas o que está de pé hoje; não inclui edificações demolidas.
- O ano do IPTU é o "ano de construção corrigido", que pode diferir da inauguração.
- Cerca de 2 mil edificações (3%) não têm ano no cadastro, em geral imóveis públicos ou isentos.
- O uso mostrado é o declarado ao fisco, não a ocupação real.

## Fontes

- **GeoSampa**, Prefeitura de São Paulo: edificações, lotes, quadras, distritos e bens tombados (WFS), baixados em 14/10/2026.
- **IPTU 2026**, Secretaria Municipal da Fazenda, publicado no GeoSampa conforme o Decreto nº 56.701/2015.
- Inspiração: [LAYRS: Amsterdam](https://stop-token.com/lab/amsterdam/), de Alex Barakov.

Os dados seguem os termos de uso do GeoSampa. O código está sob licença MIT (veja `LICENSE`).

## Autora

**Thais Adeodato**, arquiteta e urbanista, governança de dados.
[LinkedIn](https://www.linkedin.com/in/thais-morais-adeodato-porto/) · [Instagram](https://www.instagram.com/thais.adeodato/)
