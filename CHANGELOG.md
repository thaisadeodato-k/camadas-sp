# Histórico de mudanças
As atualizações mensais dos dados são registradas aqui automaticamente pelo workflow `gera-dados.yml`; as mudanças no site e no método, à mão.

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
