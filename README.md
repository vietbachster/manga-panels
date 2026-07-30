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
| `--device paperwhite` | preset de `--max-width` por leitor (`x4`/`basic`/`pw11`/`paperwhite`/`sage`/`tablet`/`scribe`/`phone`) |
| `--grayscale` | tons de cinza — menor e nativo do e-ink |
| `--gamma 1.8` | escurece os meios-tons pro e-ink (mais contraste; `1.0` = off) |
| `--format epub` | gera um `.epub` (uma imagem por página, ordem RTL) — pra leitores que não abrem cbz nem pdf |
| `--upscale` | também **amplia** imagens até `--max-width` (default só encolhe) |
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
  encolhe pra 480 e enche a tela, mas uma fatia de `--split-ratio` (~390px) ficaria
  pequena com sobra branca dos lados. Daí o `--upscale`.
- **A tela tem 4 níveis de cinza** (cache interno de 2 bits/pixel). Medindo em
  páginas reais, `-q 80` gera arquivos 27% menores que `q 90` e só 1.1% dos pixels
  caem num nível diferente — invisível, e é menos byte pra empurrar via WiFi pro
  ESP32 do aparelho.

```bash
manga-panels vol01.cbz --format epub --max-width 480 --upscale --grayscale -q 80 --split-ratio 1.0
```

`--upscale` tem um custo que vale saber antes de esperar a transferência: painéis
estreitos são reamostrados pra largura cheia da tela, o que engorda o JPEG. Medido
num volume real (FMA vol. 01, 2172 imagens de saída): 62 MB sem `--upscale` contra
114 MB com — quase o dobro, bem mais que os 27% que o `-q 80` economiza acima. É o
preço de não deixar as fatias renderizarem como selo postal na tela. Se o tempo de
transferência pelo WiFi do X4 doer mais que os painéis pequenos, a alavanca é
baixar o `-q` ainda mais, ou simplesmente deixar `--upscale` de fora.

`--split-ratio 0` desliga o corte de painel largo, se quiser comparar.

Em telas pequenas (o X4 tem 480px de largura e proporção 0.6) um painel deitado
vira uma faixa ilegível. `--split-ratio 1.0` corta todo painel landscape em
fatias verticais, na ordem de leitura, com o painel inteiro antes delas pra dar
o contexto. As emendas desviam de balões e personagens. Comece em `1.0` e
calibre com `--preview` — um limiar perto da proporção da tela (0.6) estilhaça
quase tudo. Atenção: `--preview` mostra só a detecção de painel (**quais** são
largos demais), não onde as emendas caem nem quantas fatias saem — pra isso
compare o resultado com/sem `--split-ratio` no próprio cbz de saída.

`--split-ratio` aumenta o número de imagens e o tamanho do arquivo (o painel
inteiro **e** as fatias entram na saída). Medido num volume de 20 páginas com
`--device x4 --grayscale`: sem split, 140 imagens / 5,7 MB; `--split-ratio 1.5`,
240 imagens / 8,2 MB; `--split-ratio 1.0`, 400 imagens (2,9x) / 13,4 MB (2,4x).
Note também que `--page off` só suprime a página inteira (macro) — o painel
inteiro antes de cada conjunto de fatias continua saindo; é assim de propósito,
pra dar contexto antes das fatias.

```bash
manga-panels capitulo.cbz --device x4 --split-ratio 1.0 --grayscale
```

Pra e-ink, `--grayscale` (menor e nativo do e-paper) e `--gamma 1.8` (escurece os
meios-tons, mais contraste) melhoram a leitura.

Os cortes já incluem os **balões que vazam** do painel e o **personagem que fala**
(o Magi detecta texto e personagens, não só o painel). Capa e splash saem inteiras
sozinhas (≤1 painel), sem duplicar.

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
