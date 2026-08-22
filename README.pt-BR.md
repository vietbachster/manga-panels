# manga-panels

[English](README.md) · **Português**

Corta páginas de mangá (CBZ/CBR) em **painéis** e reempacota como um CBZ novo —
um painel por página — pra ler confortável em tela pequena.

<p align="center">
  <img src="docs/images/panels.jpg" width="680" alt="A página fonte à esquerda; uma seta; à direita os nove painéis em que ela foi cortada, com setas traçando a ordem de leitura entre eles">
</p>

- Detecção com **Magi v2**, um transformer treinado em mangá: resolve páginas de
  ação, sangradas e não-retangulares, não só grid limpo.
- Ordem de leitura **direita→esquerda** (mangá), vinda do próprio modelo.
- Configura uma vez, depois é só escolher os volumes num menu.

Escolhe sozinho o melhor device do torch: **CUDA** (NVIDIA), **ROCm** (AMD),
**XPU** (Intel), **MPS** (Apple) ou **CPU** (uns poucos minutos por volume).

---

## Índice

- [Instalar](#instalar)
- [Começando](#começando)
- [Configurar (o jeito recomendado)](#configurar-o-jeito-recomendado)
- [Perfis de aparelho](#perfis-de-aparelho)
- [Conferir os cortes antes do volume inteiro](#conferir-os-cortes-antes-do-volume-inteiro)
- [Todas as flags](#todas-as-flags)
- [Formatos de saída: CBZ, PDF, EPUB](#formatos-de-saída-cbz-pdf-epub)
- [Tamanho do arquivo: onde os bytes realmente estão](#tamanho-do-arquivo-onde-os-bytes-realmente-estão)
- [Larguras de tela](#larguras-de-tela)
- [Kindle](#kindle)
- [Xteink X4 (leitores que só abrem EPUB)](#xteink-x4-leitores-que-só-abrem-epub)
- [Capítulos](#capítulos)
- [Desenvolvimento](#desenvolvimento)
- [Licença](#licença)

---

## Instalar

Precisa do [uv](https://docs.astral.sh/uv/). Clone e rode com `uv run` — ele cria
o ambiente e baixa as dependências (inclui o **torch**, ~2 GB) sozinho:

```bash
git clone https://github.com/gfrcr/manga-panels
cd manga-panels
uv run manga-panels --help
```

No primeiro processamento, o modelo Magi (~1,5 GB) é baixado automaticamente.

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

## Começando

```bash
manga-panels capitulo.cbz               # um arquivo -> capitulo_panels.cbz
manga-panels capitulo.cbz -o saida.cbz  # nome de saída específico
manga-panels ./capitulos -o ./saida     # pasta inteira (batch)
manga-panels pagina.png                 # uma imagem solta também vale (1 página)
manga-panels                            # sem input -> escolhe no menu da library
```

Cada página vira: a página inteira primeiro (contexto), depois os painéis dela na
ordem de leitura. Página em que o modelo acha um painel ou menos — capa, splash,
spread — sai inteira, uma vez só, sem duplicar.

## Configurar (o jeito recomendado)

Em vez de repetir flags, guarde seus padrões num **`manga-panels.toml`** — na
pasta de onde você roda o comando, ou em `~/.config/manga-panels/config.toml`:

```toml
[defaults]
library    = "/caminho/para/seus/mangas"   # pasta que o menu abre quando roda sem input
max_width  = 1264                          # largura do seu leitor (1264 = Kindle Paperwhite)
quality    = 85
page       = "before"                      # a página inteira antes dos painéis
page_scale = 0.6                           # encolhe só essa página inteira: ~23% a menos no arquivo
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

As chaves do config são os nomes das flags (`max_width`, `keep_first`, …). Uma
flag na linha de comando **sempre vence** o config. Veja
**[`manga-panels.example.toml`](manga-panels.example.toml)** com todas as opções
comentadas — copie e ajuste.

## Perfis de aparelho

`--device x4` não é só a largura da tela: é o conjunto que **aquele hardware
exige**. No X4, isso quer dizer `--format epub` (ele não abre cbz nem pdf),
`--upscale` (o firmware nunca amplia), `--pad-aspect 3:5` (centraliza só na
horizontal) e `--page off` (uma página inteira em 480 px é ilegível). Nos leitores
maiores o perfil traz **só a largura** — formato e qualidade ali são gosto, não
exigência.

Pra ajustar um perfil, crie uma seção `[device.<nome>]` no seu `manga-panels.toml`:

```toml
[defaults]                 # gosto geral, vale pra tudo
quality = 85

[device.x4]                # em cima do preset embutido do X4
quality = 80
output  = "/mnt/sd/manga"

[device.mykobo]            # aparelho que a tool não conhece: vira opção de --device
max_width = 1264
grayscale = true
```

Do mais específico pro menos: **flag digitada** > `[device.NOME]` > **preset
embutido** > `[defaults]` > default. O `[defaults]` fica abaixo do preset de
propósito — é o que impede um `format = "pdf"` do dia a dia de virar um arquivo
que o X4 não abre. Quando um perfil é aplicado, a tool imprime o que ele fez.

## Conferir os cortes antes do volume inteiro

`--preview` gera um CBZ com os painéis desenhados e numerados na ordem de
leitura, sem cortar nada:

```bash
manga-panels capitulo.cbz --preview
```

<p align="center">
  <img src="docs/images/preview.jpg" width="300" alt="Uma página com os painéis contornados e numerados de 0 a 8 na ordem de leitura">
</p>

Siga os números: **0** atravessa o topo, **1** desce a coluna alta da direita, e
daí cada faixa é lida da direita pra esquerda, terminando no **8** embaixo à
esquerda. Isso é ordem de mangá, e vem do modelo — o pipeline nunca reordena.

Pra ver **tudo** que o Magi entende — painéis, personagens (coloridos por
identidade), balões coloridos por quem fala e SFX marcado — use `--debug`, que
gera `<stem>_debug.cbz`. É pra inspeção/QA, não pra ler.

<p align="center">
  <img src="docs/images/debug.jpg" width="300" alt="A mesma página com o overlay completo do Magi: painéis, personagens, textos e ligação com quem fala">
</p>

É por isso também que os cortes saem certos: o corte **inclui o balão que vaza**
do painel e o **personagem que está falando**, porque o Magi detecta texto e
pessoas, não só as molduras.

## Todas as flags

Todas em `manga-panels --help`; qualquer uma vence o config.

| flag | o que faz |
|---|---|
| `--preview` | `<stem>_preview.cbz` com os painéis desenhados/numerados (confere os cortes) |
| `--debug` | `<stem>_debug.cbz` com tudo que o Magi vê (personagens, balões, quem fala) |
| `--device x4` | perfil do aparelho: largura da tela **+ formato e layout** onde o hardware exige (`x4`/`basic`/`pw11`/`paperwhite`/`sage`/`tablet`/`scribe`/`phone`) |
| `--max-width 1264` | reduz qualquer imagem mais larga que N px (mantém proporção, nunca amplia) |
| `--grayscale` | tons de cinza — menor e nativo do e-ink |
| `--gamma 1.8` | escurece os meios-tons pro e-ink (mais contraste; `1.0` = off) |
| `--quality 85` | qualidade JPEG, 1–95 |
| `--format pdf\|epub\|png` | container/codec (default: JPEG dentro de um CBZ) |
| `--upscale` | também **amplia** imagens até `--max-width` (default só encolhe) |
| `--rotate-wide 1.0` | gira 90° (horário) painel mais largo que N:1, pra ler virando o aparelho; `0` = nunca |
| `--pad-aspect 3:5` | preenche com branco até essa proporção, conteúdo centralizado |
| `--page before\|after\|off` | onde entra a página inteira (macro) — default `before` |
| `--lang en\|pt` | idioma do índice do PDF/EPUB (`Capa` / `Página N`) — default `en` |
| `--page-scale 0.6` | encolhe **só a página macro** para N× a largura dos painéis (~23% a menos no arquivo); `1.0` = off |
| `--split-ratio 1.0` | corta painel mais largo que N:1 em fatias verticais (direita→esquerda); o painel inteiro sai antes das fatias |
| `--keep-first N` | mantém as N primeiras páginas inteiras (capa/miolo) |
| `--cover img.jpg` | põe essa imagem como página 1 — a **thumbnail** do PDF na biblioteca |
| `--cover-crop 0.4` | tira a capa de uma **página 1 larga** (wraparound): fração da largura (com `--cover-side left/right`) ou uma fatia, `0.385:0.72` |
| `--rtl` | vira as páginas do EPUB da direita pra esquerda (estilo mangá); default é da esquerda pra direita |
| `--suffix _cortado` | muda o texto no nome de saída (default `_panels`) |
| `--overwrite` | sobrescreve o arquivo original no lugar (destrutivo) |

## Formatos de saída: CBZ, PDF, EPUB

O default é um **CBZ** (zip de imagens) em **JPEG q90**. Os outros dois existem
pra leitores que não abrem CBZ.

**Por que JPEG e não algo sem perda?** Porque foi medido, em 973 painéis reais,
pontuando a distorção como *a fração de pixels que muda de nível depois de
reduzir a imagem aos 16 tons de cinza que uma tela e-ink realmente mostra* —
abaixo desse degrau, a diferença é invisível no aparelho:

| codec | tamanho | pixels alterados | veredito |
|---|---|---|---|
| PNG sem perda | **202%** | 0% | o dobro do arquivo: screentone é ruído de alta frequência, o pior caso do PNG |
| WebP sem perda | 188% | 0% | mesmo problema |
| **JPEG q85** | **100%** | 7,0% | o default |
| WebP q85 | 88% | 7,0% | melhor em tudo — mas veja abaixo |
| JPEG 2000 1:4 | 94% | 7,6% | sem ganho real de bytes, ~10× mais lento pra decodificar |

O WebP é o único codec que bate o JPEG, e mesmo assim você não pode usá-lo num
CBZ: **o `cbz_ext_list` do MuPDF não tem `.webp`**, e é o MuPDF que o KOReader (e
a maioria dos leitores) usa pra abrir arquivo de quadrinho. Verificado na fonte,
não na documentação.

### CBZ vs PDF

`--format pdf` embute **os mesmos bytes JPEG, sem re-comprimir** (via `img2pdf`),
então os dois pesam igual. Precisa do extra: `uv sync --extra pdf`.

| | CBZ | PDF |
|---|---|---|
| tamanho | referência | +0,8% |
| **índice de capítulos** | **não existe** | **sim** — outline, via pikepdf |
| título/autor | só o nome do arquivo | embutidos no docinfo |
| dependência | nenhuma | `uv sync --extra pdf` |
| se der problema | é um zip: abre, olha, extrai | opaco, precisa de ferramenta |
| reprocessar depois | o `manga-panels` lê de volta | não — `unpack()` não abre PDF |

**A decisão inteira é uma pergunta: você navega por capítulo?** Se seus volumes
têm marcações no `ComicInfo.xml`, o PDF vale a pena — o outline é a única
navegação que sobrevive até o aparelho, e custa 0,8%. Se você lê direto do começo
ao fim, CBZ, e pula a dependência.

`--format epub` está coberto em [Xteink X4](#xteink-x4-leitores-que-só-abrem-epub).
`--format png` é sem perda, mas cerca de 3× maior.

## Tamanho do arquivo: onde os bytes realmente estão

### `--page-scale`, a maior alavanca que existe

A **página macro** (`--page before`) é contexto: ela mostra o layout da página, e
na largura de um leitor o texto dela já é pequeno demais pra ler — é pra isso que
servem os painéis. Só que ela é a imagem mais cara do arquivo. Medido no FMA vol.
01 (973 imagens), as macro são **20% das imagens e 51% dos bytes** (189 KB cada,
contra 45 KB por painel).

`--page-scale` encolhe **só ela**, em fração da largura dos painéis:

<p align="center">
  <img src="docs/images/page-scale.jpg" width="460" alt="A mesma página macro em largura cheia e em 0.6, lado a lado">
</p>

<p align="center"><em>Esquerda: <code>--page-scale 1.0</code> (679×1100, 190 KB).
Direita: <code>0.6</code> (407×659, 82 KB) — ainda perfeita no que ela existe pra
fazer: layout, ordem de leitura, o peso da página.</em></p>

| tratamento da macro | volume | economia |
|---|---|---|
| `--page-scale 1.0` (default) | 3,31 MB | — |
| `--page-scale 0.8` | 2,91 MB | 12% |
| **`--page-scale 0.6`** | **2,54 MB** | **23%** |
| `--page-scale 0.5` | 2,37 MB | 28% |

*Medido de ponta a ponta em 10 páginas reais → 43 imagens de saída, `--device
paperwhite --grayscale -q 85`.*

Encolher vale mais que comprimir: `0.6` corta mais do arquivo do que jogar essas
páginas pra qualidade 40 cortaria, e sem espalhar artefato de JPEG pela página.
Se a macro não te serve pra nada, `--page off` tira os 51% inteiros.

A escala é sobre a largura que a página **realmente** teria — `min(--max-width, a
largura dela)`. Um scan de 765 px com `--device paperwhite` (1264) nunca chega a
1264, então escalar sobre o teto encolheria pela folga em vez de pelo fator que
você pediu.

Ignorado com `--upscale` (o `pack()` devolveria a página ao tamanho cheio) — e
avisa quando isso acontece.

### As outras alavancas

- **`--page off`** — sem página macro nenhuma: 51% dos bytes, fora.
- **`--max-width`** — case com a sua tela, abaixo.
- **`--grayscale`** — menor e nativo do e-paper.
- **`--gamma`** — custa 2–4% de bytes e assa a mudança dentro do pixel. Se o seu
  leitor ajusta contraste sozinho (o KOReader ajusta), faça lá.

## Larguras de tela

`--max-width N` reduz qualquer imagem mais larga que N px (mantém proporção,
nunca amplia). Sem ele, mantém a resolução original. Use a **largura da tela** do
seu aparelho:

| dispositivo | tela (px) | `--max-width` |
|---|---|---|
| Xteink X4 (4,3", 220 ppi) | 800×480 | `480` |
| Kindle básico / Kobo Clara / Boox Poke (6", 300 ppi) | 1072×1448 | `1072` |
| Kindle Paperwhite 11ª (6,8") | 1236×1648 | `1236` |
| Kindle Paperwhite 12ª / Oasis / Colorsoft, Kobo Libra, Boox Page (7") | 1264×1680 | `1264` |
| Kobo Sage (8") | 1440×1920 | `1440` |
| Boox Note Air / reMarkable 2 / Kobo Elipsa (10,3") | 1404×1872 | `1404` |
| Kindle Scribe (10,2") | 1860×2480 | `1860` |
| Celular | ~1080–1284 | `1080` |

Valores aproximados (variam por modelo/ano). Na dúvida, `1264` cobre bem a
maioria dos leitores de 6–7". Em vez de decorar o número, use o perfil: `--device
paperwhite` (= `--max-width 1264`), `--device scribe`, etc.

## Kindle

**Com o KOReader** (aparelho desbloqueado), o Kindle lê CBZ direto — sem
conversão, sem Calibre, sem teto de tamanho. Copie o arquivo por USB:

```bash
manga-panels vol01.cbz --device paperwhite --grayscale -q 85 --page-scale 0.6
```

Deixe o `--gamma` desligado e ajuste o contraste no aparelho: é o mesmo resultado
sem assar a perda dentro do arquivo.

**No firmware de fábrica**, o Kindle não abre CBZ — use `--format pdf`, que
preenche a tela de ponta a ponta e leva a capa e o índice de capítulos:

```bash
manga-panels vol01.cbz --format pdf --device paperwhite --grayscale -q 85
```

Transfira por USB pra pasta `documents/`. O Send to Kindle sem fio corta em
~50 MB, e um volume desses passa fácil disso.

> **EPUB no Kindle é beco sem saída**, resolvido num Paperwhite real: um livro
> reflowable é diagramado na coluna de texto do leitor, então nunca preenche a
> tela, e o formato fixed-layout (uma imagem por documento, a abordagem do KCC)
> **congela em 66 documentos** — um volume tem milhares. O `--pad-aspect
> 1264:1680` resolve a centralização, mas não as margens. Use CBZ (KOReader) ou
> PDF (de fábrica).

### A capa

A página 1 é a thumbnail que a sua biblioteca mostra. `--cover capa.jpg` põe uma
imagem específica ali.

Se a página 1 é uma **spread larga** (sobrecapa wraparound), ela fica deitada e
vira uma thumbnail ruim. `--cover-crop` tira a **capa da frente** dela, de duas
formas:

```bash
--cover-crop 0.4                 # fração da largura, a partir de --cover-side
--cover-crop 0.385:0.72          # uma fatia: do 38,5% ao 72% da largura
```

A fatia existe porque uma **sobrecapa de mangá é orelha + capa + contracapa**: a
capa da frente fica no *meio*, onde nenhuma fração a partir da borda chega. E as
proporções mudam de volume pra volume (a orelha e a lombada variam), então o
número é por arquivo — vale conferir antes de rodar o volume inteiro:

```bash
python -c "
import sys, zipfile, io; from PIL import Image
z = zipfile.ZipFile(sys.argv[1]); n = sorted(x for x in z.namelist() if x.endswith('.jpg'))[0]
im = Image.open(io.BytesIO(z.read(n))); w, h = im.size
a, b = (float(v) for v in sys.argv[2].split(':'))
im.crop((int(w*a), 0, int(w*b), h)).save('/tmp/capa.png')
" vol01.cbz 0.385:0.72 && xdg-open /tmp/capa.png
```

`--cover-crop 0` desliga (útil pra sobrescrever um valor vindo do config).

## Xteink X4 (leitores que só abrem EPUB)

O X4 (4,3", 800×480) **não lê CBZ nem PDF** — o firmware CrossPoint aceita
`.epub`, `.txt` e `.bmp`. Converter no Calibre estraga os painéis: o "comic
input" dele redimensiona pro perfil de saída e assa o padding dentro da imagem.
Por isso `--format epub` gera o arquivo aqui, sem intermediário.

```bash
manga-panels vol01.cbz --device x4
```

Esse perfil é exatamente a receita validada no aparelho:

```bash
manga-panels vol01.cbz --format epub --max-width 480 --upscale --grayscale -q 75 \
    --rotate-wide 1.0 --pad-aspect 3:5 --page off
```

Duas particularidades do aparelho, ambas lidas do fonte do firmware:

- **Ele nunca amplia** (`if (scale > 1.0f) scale = 1.0f`). Um painel de 780 px
  encolhe pra 480 e enche a tela — mas um painel menor que a tela fica com sobra
  em branco ao redor, e é exatamente essa sobra que o `--pad-aspect` deveria
  preencher.
- **A tela tem 4 níveis de cinza** (cache interno de 2 bits/pixel). Em páginas
  reais, `-q 80` já gera arquivos 27% menores que `-q 90` com só 1,1% dos pixels
  caindo num nível diferente — invisível no aparelho. O perfil usa `-q 75`, que
  em uso real não mostrou diferença perceptível e é menos byte pra empurrar pelo
  WiFi do ESP32.

`--rotate-wide 1.0` gira todo painel mais largo que 1:1, e você lê virando o X4
no sentido anti-horário: o eixo longo passa de 480 pra 728 px, 2,3× mais área.
`--split-ratio` (fatiar o painel largo em vez de girar) segue existindo, mas foi
testado no aparelho e descartado: cada fatia é mais uma página pra virar, e a
costura no meio da cena deixa a leitura massante.

**`--pad-aspect` sem `--upscale` não faz quase nada.** Medido em 973 painéis
reais com `--rotate-wide 1.0 --pad-aspect 3:5 -w 480` **sem** `--upscale`: 758 de
973 saíram menores que a tela (197 px de folga na mediana), e o arquivo final
ficou *maior* que sem nenhuma flag de geometria (31,8 MB contra 28,4 MB) — só o
branco extra, sem resolver o problema. Com `--upscale`: 589/973 saem exatamente
480×800, 0 px de folga na mediana. Use as duas sempre juntas.

`--upscale` tem um custo que vale saber antes de esperar a transferência: painéis
pequenos são reamostrados pra largura cheia da tela, o que engorda o JPEG. Num
volume real (FMA vol. 01, 2172 imagens de saída): 62 MB sem ele, 114 MB com —
quase o dobro. Se o tempo de transferência doer mais do que vale, a alavanca é
baixar o `-q` ainda mais; tirar o `--upscale` não é opção, porque devolve o
`--pad-aspect` ao quase-no-op medido acima.

## Capítulos

Se o CBZ de origem tem um `ComicInfo.xml` com marcações de capítulo, elas
aparecem no índice do EPUB e nos marcadores do PDF. O campo é o padrão do
formato:

```xml
<Pages>
  <Page Image="5"  Bookmark="Capítulo 51. Richard" />
  <Page Image="27" Bookmark="Capítulo 52. A Prova" />
</Pages>
```

`Image` é a posição da imagem dentro do arquivo, contada a partir de 0 — **não**
o número impresso na página. Os dois costumam divergir: capa e miolo empurram a
contagem, e uma página dupla guardada como uma imagem só desloca tudo dali em
diante. Por isso a tool nunca calcula deslocamento; ela lê `Image` como está.

Esses rótulos — `Capa` e `Página N` — são o único texto que a ferramenta grava
dentro da saída, e a `--lang` escolhe o idioma deles (`en` default, `pt`
disponível). Eles seguem o mangá, não a CLI: uma scan brasileira indexada como
"Page 12" é que seria a estranha. Um idioma novo é uma linha no `LABELS`
(`pipeline.py`).

Sem capítulos, o índice lista as páginas e o livro é dividido em blocos de 20.
Nada é inventado: se a fonte não traz capítulo, a saída não inventa um.

> **CBZ não carrega metadado nenhum.** Capítulos, título e autor sobrevivem só
> nas saídas PDF e EPUB — o CBZ é imagem e mais nada. Gravar um `ComicInfo.xml`
> dentro dele também não ajudaria no aparelho: o KOReader não tem uma referência
> sequer a esse arquivo em todo o código-fonte dele.

## Desenvolvimento

```bash
uv sync --all-extras     # + pytest e rarfile (cbr) no .venv
uv run pytest -q         # os testes reais de ML são pulados por default (-m 'not ml')
uv run pytest -m ml      # roda eles: baixa/carrega o Magi de verdade
```

Rode por `uv run`. Pra hackear o `manga-panels` instalado como ferramenta, use
`uv tool install -e . --force` (editable: só `.py` pega ao vivo; mudança no
`pyproject.toml` pede reinstalar).

## Licença

O código do manga-panels é **MIT** (veja [LICENSE](LICENSE)) — use, modifique e
distribua à vontade.

**Atenção:** a detecção usa o modelo **Magi v2**
([ragavsachdeva/magiv2](https://huggingface.co/ragavsachdeva/magiv2)), que tem
licença **própria e não-comercial** (uso pessoal, pesquisa e sem fins lucrativos;
comercial exige acordo com o autor). O manga-panels não redistribui o modelo —
baixa em tempo de execução — mas ao usá-lo você fica sujeito aos termos do Magi.

As páginas de mangá das imagens são de *Fullmetal Alchemist* (Hiromu Arakawa) e
aparecem aqui apenas pra ilustrar o que a ferramenta faz.
