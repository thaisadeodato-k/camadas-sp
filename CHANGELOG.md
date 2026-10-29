# Histórico de mudanças
As atualizações mensais dos dados são registradas aqui automaticamente pelo workflow `gera-dados.yml`; as mudanças no site e no método, à mão.

## 2026-10-20: dados atualizados

Mudança no código do pipeline.

Resultado:

- Lotes ligados ao IPTU: 98,1% na cidade; 0 distrito(s) abaixo de 90%.
- Distritos: 96.
- Edificações: 2.789.796 → 2.789.796 (+0,00%).
- Com ano no IPTU: 89,5% → 89,5%.

## 2026-10-20: dados atualizados

Mudança no código do pipeline.

Fontes que mudaram:

- **lote_cidadao**: feicoes: 1688001 → 1688012

Resultado:

- Lotes ligados ao IPTU: 98,1% na cidade; 0 distrito(s) abaixo de 90%.
- Distritos: 96.
- Edificações: 2.789.795 → 2.789.796 (+0,00%).
- Com ano no IPTU: 89,5% → 89,5%.
- Distritos que mais mudaram: BELA VISTA (5.658 → 5.659).

## 2026-10-29: aviso de carregamento e escolha da área

- Enquanto as edificações ou as quadras chegam, um aviso mostra quanto já carregou (aparece só se a espera passa de meio segundo).
- Novo botão **Área**: escolher uma ou mais regiões ou distritos. Só as edificações da área aparecem, e o mapa baixa só os blocos do retângulo dela; fora, a cidade continua em quadras. No teste, com a região Centro escolhida, a vista do centro no zoom 13 pediu 57 blocos em vez de 181. O cartão do distrito ganhou o botão "Só este distrito".

## 2026-10-29: o meio da tela carrega primeiro

- Ao chegar nas edificações, o meio da tela ficava vazio enquanto as bordas carregavam: o mapa passava os blocos à fila em lotes de 64, na ordem da grade, e a fila só escolhia o mais perto do meio dentro de cada lote. Agora a tela inteira entra na fila, e só saem os blocos que ainda aparecem na tela (os que ficaram para trás num voo esperam ser cancelados). No teste, o meio da tela ficou pronto em 0,4 s em vez de 1,3 s (computador, zoom 13); ao voar até o centro, o mapa baixa menos blocos (97 em vez de 131 no computador, 15 em vez de 37 no celular).

## 2026-10-26: centro com quadras

- O centro histórico também mostra as quadras até o zoom 13, como o resto da cidade. Antes, os prédios do centro apareciam a partir do zoom 12 e, na vista de quadras, pesavam o dobro de todas as quadras da cidade juntas. No teste, o desenho dessa vista ficou cerca de 65% mais rápido.

## 2026-10-20: quadras vistas de longe

- Entre os hexágonos e as edificações, cada quadra viária aparece como um volume: altura média das suas edificações (ponderada pela área), cor do ano médio ou do valor que predomina. As edificações de 30 m ou mais, e as poucas fora de qualquer quadra, aparecem inteiras.
- Na linha do tempo, cada volume cresce com a parte da quadra já construída.
- Um arquivo só (`quadras_longe.bin`, cerca de 4 MB, gerado por `gera_site.py longe`), no lugar de `edificacoes_longe.pmtiles`, que deixa de ser gerado. No teste, cerca de 1 segundo de travamento ao chegar e 300 MB de memória, contra 6 a 11 segundos e mais de 2 GB da tentativa anterior.

## 2026-10-20: prédios vistos de longe

- No computador, os prédios aparecem a partir do zoom 13 (antes 13,5), com todos os detalhes.
- Testada e desligada no mesmo dia: a vista de longe com todas as edificações simplificadas (`edificacoes_longe.pmtiles`, cerca de 33 MB para a cidade inteira). Com a cidade inteira na tela, o navegador travava de 6 a 11 segundos e passava de 2 GB de memória. O arquivo continua sendo gerado.

## 2026-10-19: dados atualizados

Mudança no código do pipeline.

Resultado:

- Lotes ligados ao IPTU: 98,1% na cidade; 0 distrito(s) abaixo de 90%.
- Distritos: 96.
- Edificações: 2.789.795 → 2.789.795 (+0,00%).
- Com ano no IPTU: 89,5% → 89,5%.

## 2026-10-19: atualização mensal automática e README

- Verificação mensal das fontes (`pipeline/verifica_fontes.py`): os dados só são gerados de novo quando alguma fonte muda no GeoSampa, ou depois de 180 dias.
- Controles de qualidade antes de publicar (`pipeline/controle.py`); se algum falhar, o site não é atualizado e uma issue explica o motivo.
- O site mostra a data da última verificação das fontes.
- README reescrito para os 96 distritos.

## 2026-10-19: site dos 96 distritos no ar

- Mapa da cidade inteira: 2.789.795 edificações nos 96 distritos, com distritos, hexágonos de 150 m e prédios em 3D.
- No centro histórico, os prédios aparecem de mais longe; os blocos do centro da tela carregam primeiro.
- Publicação pelo GitHub Actions; os dados ficam na release "dados", fora do histórico do Git.

## 2026-10-18: dados para o site

- ZEIS-1 (Lei 18.081/2024), quadras, datas históricas e contagens por distrito.

## 2026-10-17: pipeline dos 96 distritos

- Pipeline novo (`pipeline/camadas.py`), retomável, que registra a data e o hash de cada fonte.
- Blocos de mapa (PMTiles) gerados com tippecanoe no GitHub Actions.
- Edificações sem ano deixam de aparecer na linha do tempo; hierarquia de datas (registro histórico antes do IPTU).

## 2026-10-14: primeira versão

- Mapa 3D das 68.684 edificações dos dez distritos do centro.
