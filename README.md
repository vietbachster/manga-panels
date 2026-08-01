# manga-panels

Corta páginas de manga (CBZ/CBR) em **painéis** e reempacota como um CBZ novo —
um painel por página — pra ler confortável em tela pequena (celular, Kindle).

- Detecção com **Magi v2**, um modelo transformer treinado em mangá: resolve
  páginas de ação, sangradas e não-retangulares, não só grid limpo.
- Ordem de leitura **direita→esquerda** (mangá), vinda do próprio modelo.
- Configura uma vez, depois é só escolher os volumes num menu.

Escolhe sozinho o melhor device do torch: **CUDA** (NVIDIA), **ROCm** (AMD),
**XPU** (Intel), **MPS** (Apple) ou **CPU** (uns poucos minutos por volume).

## Instalar

Precisa do [uv](https://docs.astral.sh/uv/). Clone e rode com `uv run` — ele cria
o ambiente e baixa as dependências (inclui o **torch**, ~2GB) sozinho:

```bash
git clone https://github.com/gfrcr/manga-panels
cd manga-panels
uv run manga-panels --help
```

No primeiro processamento, o modelo Magi (~1.5GB) é baixado automaticamente.

> Pra GPU **AMD/Intel/Apple**, instale o build do torch correspondente
> (ROCm/XPU/MPS) — o padrão é o build NVIDIA/CUDA. O código usa o que estiver
> disponível; sem GPU, roda na CPU.
>
> CBR (`.cbr`) precisa do binário **`unrar`** no sistema e do extra:
> `uv sync --extra cbr`.

Prefere o comando `manga-panels` solto, de qualquer pasta (sem `uv run` na
frente)? Instale como ferramenta do uv:

```bash
uv tool install "git+https://github.com/gfrcr/manga-panels"
```

Os exemplos abaixo mostram `manga-panels` direto — se você foi pelo `uv run`, é
só prefixar: `uv run manga-panels …`.

## Configurar (o jeito recomendado)

Em vez de repetir flags, guarde seus padrões num **`manga-panels.toml`** — na
pasta de onde você roda o comando, ou em `~/.config/manga-panels/config.toml`:

```toml
[defaults]
library   = "/caminho/para/seus/mangas"   # pasta que o menu abre quando roda sem input
max_width = 1264                          # largura do seu leitor (1264 = Kindle Paperwhite)
quality   = 85
page      = "before"                      # a página inteira antes dos painéis
```

Com isso, rode **sem argumentos** e escolha o que processar num menu — ele navega
nas subpastas de série e você seleciona os volumes:

```bash
manga-panels -o ~/saida
```

```
/caminho/para/seus/mangas
   1) [dir]  Monster
> 1
   0) ..
   1)       Monster Vol.01.cbz
   2)       Monster Vol.02.cbz
> 1,2        # números, faixas (1-4), 'a' pra todos, Enter pra cancelar
```

Pronto — cada volume vira um CBZ com um painel por página.

As chaves do config são os nomes das flags (`max_width`, `keep_first`, …). Uma
flag na linha de comando **sempre vence** o config. Veja
**[`manga-panels.example.toml`](manga-panels.example.toml)** com todas as opções
comentadas — copie e ajuste.

### Perfis de aparelho

`--device x4` não é só a largura da tela: é o conjunto que **aquele hardware exige**.
No X4, isso quer dizer `--format epub` (ele não abre cbz nem pdf), `--upscale` (o
firmware nunca amplia), `--pad-aspect 3:5` (centraliza só na horizontal) e `--page off`
(uma página inteira em 480px é ilegível). Nos leitores maiores o perfil traz **só a
largura** — formato e qualidade ali são gosto, não exigência.

Pra ajustar um perfil, crie uma seção `[device.<nome>]` no seu `manga-panels.toml`:

```toml
[defaults]                 # gosto geral, vale pra tudo
format  = "pdf"
quality = 85

[device.x4]                # em cima do preset embutido do X4
quality = 80
output  = "/mnt/sd/manga"

[device.mykobo]            # aparelho que a tool não conhece: vira opção de --device
max_width = 1264
grayscale = true
```

Do mais específico pro menos: **flag digitada** > `[device.NOME]` > **preset embutido**
> `[defaults]` > default. O `[defaults]` fica abaixo do preset de propósito — é o que
impede um `format = "pdf"` do dia a dia de virar um arquivo que o X4 não abre. Quando
um perfil é aplicado, a tool imprime o que ele fez.

## Rodar num arquivo ou pasta (sem menu)

Passe o caminho direto — pra um volume só, batch de uma pasta, ou quando não quer
usar a `library`:

```bash
manga-panels capitulo.cbz               # um arquivo -> capitulo_panels.cbz
manga-panels capitulo.cbz -o saida.cbz  # nome de saída específico
manga-panels ./capitulos -o ./saida     # pasta inteira (batch)
manga-panels pagina.png                 # uma imagem solta também vale (1 página)
```

Antes de processar um volume todo, **confira os cortes** com `--preview`: gera um
CBZ com os painéis desenhados e numerados na ordem de leitura, sem cortar.

```bash
manga-panels capitulo.cbz --preview
```

Pra ver **tudo** que o Magi entende — painéis, personagens (coloridos por
identidade), balões coloridos por quem fala e SFX marcado — use `--debug`, que
gera `<stem>_debug.cbz`. É pra inspeção/QA, não pra ler.

Outras flags (todas em `manga-panels --help`; qualquer uma vence o config):

| flag | o que faz |
|---|---|
| `--preview` | `<stem>_preview.cbz` com os painéis desenhados/numerados (confere os cortes) |
| `--debug` | `<stem>_debug.cbz` com tudo que o Magi vê (personagens, balões, quem fala) |
| `--device x4` | perfil do aparelho: largura da tela **+ formato e layout** onde o hardware exige (`x4`/`basic`/`pw11`/`paperwhite`/`sage`/`tablet`/`scribe`/`phone`) |
| `--grayscale` | tons de cinza — menor e nativo do e-ink |
| `--gamma 1.8` | escurece os meios-tons pro e-ink (mais contraste; `1.0` = off) |
| `--format epub` | gera um `.epub` (uma imagem por página, ordem RTL) — pra leitores que não abrem cbz nem pdf |
| `--upscale` | também **amplia** imagens até `--max-width` (default só encolhe) |
| `--rotate-wide 1.0` | gira 90° (horário) painel mais largo que N:1, pra ler virando o aparelho; `0` = nunca |
| `--pad-aspect 3:5` | preenche com branco até essa proporção, conteúdo centralizado |
| `--page before\|after\|off` | onde entra a página inteira (macro) — default `before` |
| `--split-ratio 1.0` | corta painel mais largo que N:1 em fatias verticais (direita→esquerda); o painel inteiro sai antes das fatias |
| `--keep-first N` | mantém as N primeiras páginas inteiras (capa/miolo) |
| `--cover img.jpg` | põe essa imagem como página 1 — a **thumbnail** do PDF na biblioteca |
| `--cover-crop 0.4` | tira a capa de uma **página 1 larga** (wraparound): fração da largura; `--cover-side left/right` |
| `--suffix _cortado` | muda o texto no nome de saída (default `_panels`) |
| `--overwrite` | sobrescreve o arquivo original no lugar (destrutivo) |

## Saída: formato e tamanho

Default: um **CBZ** (zip de imagens) em **JPEG q90** (~1x o tamanho da fonte).
`--format png` é sem perda mas ~3x maior; ajuste com `--quality 1..95`. Pra
leitores que não abrem cbz, `--format pdf` (Kindle) ou `--format epub` (Xteink
X4 e outros) — cada um coberto numa seção abaixo.

Pro **Kindle** (e outros leitores que só abrem PDF), use **`--format pdf`**: gera
um `.pdf` com um painel por página, com o JPEG embutido sem re-comprimir (mesmo
tamanho do cbz, sem perda extra). Precisa do extra: `uv sync --extra pdf`.

```bash
manga-panels capitulo.cbz --format pdf --device paperwhite --grayscale   # pronto pro Kindle
```

A **capa** (thumbnail na biblioteca do Kindle) é a **página 1** do PDF. Pra usar
uma imagem específica, `--cover cover.jpg` (ex.: o `cover.jpg` do volume) — ela
entra inteira como página 1.

Se a página 1 é uma **spread larga** (capa wraparound frente+verso), ela fica
deitada e vira uma thumbnail ruim. `--cover-crop 0.4` corta a **capa da frente**
(uma fração da largura) e usa como página 1. Ajuste a fração (menor = mais
retrato) e `--cover-side left|right` conforme o layout do teu scan.

Scans grandes (edições deluxe a 1600px+) geram arquivos pesados. Pra celular ou
Kindle, reduza com `--max-width`:

```bash
manga-panels capitulo.cbz --max-width 1264
```

`--max-width N` reduz qualquer imagem mais larga que N px (mantém proporção, nunca
amplia). Sem ele, mantém a resolução original. Use a **largura da tela** do seu
aparelho:

| dispositivo | tela (px) | `--max-width` |
|---|---|---|
| Xteink X4 (4.3", 220 ppi) | 800×480 | `480` |
| Kindle básico / Kobo Clara / Boox Poke (6", 300 ppi) | 1072×1448 | `1072` |
| Kindle Paperwhite 11ª (6.8") | 1236×1648 | `1236` |
| Kindle Paperwhite 12ª / Oasis / Colorsoft, Kobo Libra, Boox Page (7") | 1264×1680 | `1264` |
| Kobo Sage (8") | 1440×1920 | `1440` |
| Boox Note Air / reMarkable 2 / Kobo Elipsa (10.3") | 1404×1872 | `1404` |
| Kindle Scribe (10.2") | 1860×2480 | `1860` |
| Celular | ~1080–1284 | `1080` |

Valores aproximados (variam por modelo/ano). Na dúvida, `1264` cobre bem a maioria
dos leitores de 6–7". Em vez de decorar o número, use o preset: `--device paperwhite`
(= `--max-width 1264`), `--device scribe`, etc.

### Xteink X4 (e outros leitores que só abrem EPUB)

O X4 (4.3", 800×480) **não lê CBZ nem PDF** — o firmware CrossPoint aceita
`.epub`, `.txt` e `.bmp`. Converter no Calibre estraga os painéis: o "comic input"
dele redimensiona pro perfil de saída e assa o padding dentro da imagem. Por isso
`--format epub` gera o arquivo aqui, sem intermediário.

Duas particularidades do aparelho, ambas lidas do fonte do firmware:

- **Ele nunca amplia** (`if (scale > 1.0f) scale = 1.0f`). Um painel de 780px
  encolhe pra 480 e enche a tela — mas um painel menor que a tela, girado ou não,
  fica com sobra em branco ao redor, e é exatamente essa sobra que o `--pad-aspect`
  deveria preencher. Sem `--upscale` a imagem nunca chega perto do tamanho da tela
  pra começo de conversa, e o `--pad-aspect` vira decoração (números abaixo).
- **A tela tem 4 níveis de cinza** (cache interno de 2 bits/pixel). Medindo em
  páginas reais, `-q 80` já gera arquivos 27% menores que `-q 90` com só 1.1% dos
  pixels caindo num nível diferente — invisível no aparelho. Testado direto na
  tela, dá pra ir mais fundo ainda: o perfil `x4` usa `-q 75`, que em uso real não
  mostrou diferença perceptível nos 4 níveis de cinza e é menos byte pra empurrar
  pelo WiFi do ESP32.

```bash
manga-panels vol01.cbz --device x4
```

`--device x4` é exatamente a receita abaixo, que é a validada no aparelho — cada flag
explicada no resto desta seção:

```bash
manga-panels vol01.cbz --format epub --max-width 480 --upscale --grayscale -q 75 \
    --rotate-wide 1.0 --pad-aspect 3:5 --page off
```

`--rotate-wide 1.0` gira todo painel mais largo que 1:1 e você lê virando o X4 no
sentido anti-horário: o eixo longo passa de 480 pra 728px, 2,3x mais área.
`--split-ratio` — cortar o painel largo em fatias verticais em vez de girar —
segue existindo (veja a tabela de flags acima), mas pro X4 foi testado no
aparelho e descartado: cada fatia vira uma página a mais pra virar, e a costura
no meio da cena deixa a leitura massante. Girar preserva o painel inteiro numa
tela só.

`--pad-aspect 3:5` existe porque o firmware **centraliza só na horizontal** — sobra
vertical deixa a imagem colada no topo. Preenchendo até a proporção da tela não sobra
folga em eixo nenhum. Use 3:5 (a tela cheia) e não a área útil: se a barra de status
mudar a altura, o erro sobra na horizontal, que o firmware corrige sozinho.

**`--pad-aspect` sem `--upscale` não faz quase nada.** O firmware nunca amplia, então
uma imagem pequena preenchida até 3:5 continua pequena — a folga branca só muda de
lugar, e a metade vertical some colada no topo, o defeito exato que a flag existe
pra resolver. Medido em 973 painéis reais com `--rotate-wide 1.0 --pad-aspect 3:5
-w 480` **sem** `--upscale`: 758 de 973 saíram menores que a tela (197px de folga na
mediana), e o arquivo final ficou **maior** que sem nenhuma flag de geometria (31,8 MB
contra 28,4 MB) — só o branco extra, sem resolver o problema. Com `--upscale`:
589/973 saem exatamente 480×800, 0px de folga na mediana, no máximo 2px de
arredondamento. Use as duas juntas sempre.

`--upscale` tem um custo que vale saber antes de esperar a transferência: painéis
pequenos são reamostrados pra largura cheia da tela, o que engorda o JPEG. Medido
num volume real (FMA vol. 01, 2172 imagens de saída): 62 MB sem `--upscale` contra
114 MB com — quase o dobro. Se o tempo de transferência pelo WiFi do X4 doer mais
do que vale a pena, a alavanca é baixar o `-q` ainda mais — tirar o `--upscale` não
é opção, porque devolve o `--pad-aspect` ao quase-no-op medido acima.

Pra e-ink, `--grayscale` (menor e nativo do e-paper) e `--gamma 1.8` (escurece os
meios-tons, mais contraste) melhoram a leitura.

Os cortes já incluem os **balões que vazam** do painel e o **personagem que fala**
(o Magi detecta texto e personagens, não só o painel). Capa e splash saem inteiras
sozinhas (≤1 painel), sem duplicar.

### Capítulos

Se o CBZ tiver um `ComicInfo.xml` com marcações de capítulo, elas aparecem no
índice do EPUB e nos marcadores do PDF. O campo é o padrão do formato:

```xml
<Pages>
  <Page Image="5"  Bookmark="Kapitel 51. Richard" />
  <Page Image="27" Bookmark="Kapitel 52. A Prova" />
</Pages>
```

`Image` é a posição da imagem dentro do arquivo, contada a partir de 0 — **não** o
número impresso na página. Os dois costumam divergir: capa e miolo empurram a
contagem, e uma página dupla guardada como uma imagem só desloca tudo dali em diante.
Por isso a tool nunca calcula deslocamento; ela lê `Image` como está.

Sem capítulos, o índice lista as páginas e o livro é dividido em blocos de 20. Nada é
inventado: se a fonte não traz capítulo, a saída não inventa um.

## Desenvolvimento

```bash
uv sync --all-extras     # + pytest e rarfile (cbr) no .venv
uv run pytest -q         # os testes reais de ML são pulados por default (-m 'not ml')
```

Rode por `uv run`. Pra hackear o `manga-panels` instalado como ferramenta, use
`uv tool install -e . --force` (editable: só `.py` pega ao vivo; mudança no
`pyproject.toml` pede reinstalar).

## Licença

O código do manga-panels é **MIT** (veja [LICENSE](LICENSE)) — use, modifique e
distribua à vontade.

**Atenção:** a detecção usa o modelo **Magi v2**
([ragavsachdeva/magiv2](https://huggingface.co/ragavsachdeva/magiv2)), que tem
licença **própria e não-comercial** (uso pessoal, pesquisa e sem fins
lucrativos; comercial exige acordo com o autor). O manga-panels não redistribui
o modelo — baixa em tempo de execução — mas ao usá-lo você fica sujeito aos
termos do Magi.
