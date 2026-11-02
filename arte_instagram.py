"""Arte dos posts do Instagram (feed 4:5 e stories 9:16) em rosa e preto, feita com Pillow.

Usada pelo painel (previa) e pela rotina que publica: o que a Polly aprova na previa e o que vai ao ar sao
o mesmo arquivo. Nao depende de fonte instalada: usa a fonte vetorial embutida no Pillow.
"""
import io
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

PRETO, ROSA, ROSA_CLARO, BRANCO = (10, 5, 8), (255, 45, 143), (255, 194, 224), (255, 255, 255)
TAMANHOS = {"feed": (1080, 1350), "stories": (1080, 1920)}
# Stories: o Instagram cobre o topo (perfil) e a base (resposta). Nada importante nessas faixas.
SEGURO_TOPO, SEGURO_BASE = 250, 340
HASHTAGS = {"Beleza": "#beleza #skincare #cuidadoscomapele", "Casa e Cozinha": "#casa #cozinha #utilidadesdomesticas",
            "Moda": "#moda #look #estilo", "Eletrônicos": "#eletronicos #tecnologia #gadgets",
            "Organização e Limpeza": "#organizacao #limpeza #casaorganizada", "Natal e Decoração": "#natal #decoracao #decoracaodenatal",
            "Fitness e Esportes": "#fitness #treino #esportes"}
BASE_TAGS = "#ofertas #achadinhos #promocao #ofertasdapolly"


FONTES = Path(__file__).resolve().parent / "fonts"  # Liberation Sans (SIL OFL): tem acentos do portugues


def _fonte(tamanho, negrito=True):
    try: return ImageFont.truetype(str(FONTES / ("LiberationSans-Bold.ttf" if negrito else "LiberationSans-Regular.ttf")), tamanho)
    except OSError: return ImageFont.load_default(size=tamanho)


def _sem_emoji(txt):
    """A fonte embutida nao tem emoji: na imagem vai so o texto; a legenda do post mantem os emojis."""
    return re.sub(r"[^\w\s.,!?:;%$&()\-/+'\"°ªº@#]", "", str(txt or ""), flags=re.UNICODE).strip()


def _brl(v):
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def preco_texto(v):
    """Numero, faixa 'min-max' ou 'ap:valor' (mesmas formas da planilha)."""
    s = str(v)
    if s.startswith("ap:"): return f"a partir de {_brl(s[3:])}"
    if "-" in s and not s.startswith("-"):
        a, b = (float(x.replace(",", ".")) for x in s.split("-", 1))
        return _brl(a) if a == b else f"{_brl(a)} a {_brl(b)}"
    return _brl(float(s))


def _quebrar(draw, texto, fonte, largura, max_linhas):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if draw.textlength(teste, font=fonte) <= largura: atual = teste
        else:
            if atual: linhas.append(atual)
            atual = p
    if atual: linhas.append(atual)
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]; linhas[-1] = linhas[-1].rstrip(" .,") + "…"
    return linhas


def _negrito(draw, xy, texto, fonte, cor, forca=0, **kw):
    draw.text(xy, texto, font=fonte, fill=cor, **kw)


def _fundo(w, h):
    base = Image.new("RGB", (w, h), PRETO)
    lado = int(w * 1.4)
    brilho = Image.radial_gradient("L").resize((lado, lado)).point(lambda v: max(0, 255 - int(v * 1.45)))
    mascara = Image.new("L", (w, h), 0); mascara.paste(brilho, (int(-w * 0.2), int(-w * 0.5)))
    base.paste(Image.new("RGB", (w, h), (92, 15, 58)), (0, 0), mascara)
    return base


def _cartao(base, foto_bytes, caixa):
    x0, y0, x1, y1 = caixa; w, h = x1 - x0, y1 - y0
    sombra = Image.new("RGBA", (w + 120, h + 120), (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((60, 70, w + 60, h + 70), 44, fill=(0, 0, 0, 150))
    base.paste(sombra.filter(ImageFilter.GaussianBlur(26)), (x0 - 60, y0 - 60), sombra.filter(ImageFilter.GaussianBlur(26)))
    cartao = Image.new("RGB", (w, h), BRANCO)
    if foto_bytes:
        im = Image.open(io.BytesIO(foto_bytes)).convert("RGB")
        im.thumbnail((w - 60, h - 60), Image.LANCZOS)
        cartao.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    mascara = Image.new("L", (w, h), 0); ImageDraw.Draw(mascara).rounded_rectangle((0, 0, w, h), 44, fill=255)
    base.paste(cartao, (x0, y0), mascara)
    ImageDraw.Draw(base).rounded_rectangle((x0, y0, x1, y1), 44, outline=ROSA, width=6)


def link_curto(c):
    """Link do produto sem o https://, para caber na arte e ser digitado."""
    return re.sub(r"^https?://", "", str(c.get("I") or "")).strip("/")


def renderizar(c, foto_bytes, formato="feed", cta=None, mostrar_link=False):
    """c: dict com as colunas da planilha (B produto, E preco, R chamada, C categoria). Devolve bytes JPEG."""
    w, h = TAMANHOS[formato]; im = _fundo(w, h); d = ImageDraw.Draw(im)
    nome = _sem_emoji(c.get("B")); chamada = re.split(r"(?<=[!?])\s", _sem_emoji(c.get("R")))[0]  # so a 1a frase: nunca corta no meio
    selo = _fonte(34)
    if formato == "feed":
        topo, cartao_h = 60, 560
        d.rounded_rectangle((60, topo, 60 + d.textlength("OFERTA DA POLLY", font=selo) + 70, topo + 76), 38, fill=ROSA)
        _negrito(d, (95, topo + 17), "OFERTA DA POLLY", selo, BRANCO)
        _cartao(im, foto_bytes, (90, 170, 990, 170 + cartao_h))
        y = 170 + cartao_h + 50
    else:
        topo = SEGURO_TOPO + 10
        d.rounded_rectangle((60, topo, 60 + d.textlength("OFERTA DA POLLY", font=selo) + 70, topo + 76), 38, fill=ROSA)
        _negrito(d, (95, topo + 17), "OFERTA DA POLLY", selo, BRANCO)
        _cartao(im, foto_bytes, (90, topo + 120, 990, topo + 120 + 520))
        y = topo + 120 + 520 + 40
    f_nome = _fonte(50)
    for linha in _quebrar(d, nome, f_nome, 940, 2):
        _negrito(d, (70, y), linha, f_nome, BRANCO); y += 60
    y += 14
    _negrito(d, (70, y), "por apenas", _fonte(34, False), BRANCO); y += 44
    preco, tam = preco_texto(c.get("E")), 112
    while tam > 40 and d.textlength(preco, font=_fonte(tam)) > 940: tam -= 4  # faixas de preco ("R$ 23,99 a R$ 74,99") ficam menores
    _negrito(d, (70, y + (112 - tam) // 2), preco, _fonte(tam), ROSA_CLARO); y += 130
    if chamada and formato == "feed" and y < h - 190:
        for linha in _quebrar(d, chamada, _fonte(32, False), 940, 2):
            _negrito(d, (70, y), linha, _fonte(32, False), BRANCO); y += 42
    if formato == "feed":
        if mostrar_link and link_curto(c):
            fl = _fonte(34); lt = "link do produto: " + link_curto(c)
            d.text(((w - d.textlength(lt, font=fl)) / 2, h - 135), lt, font=fl, fill=BRANCO)
        rod = "LINK NA BIO  ·  @ofertasdapolly_"
        d.text(((w - d.textlength(rod, font=_fonte(30))) / 2, h - 72), rod, font=_fonte(30), fill=ROSA_CLARO)
    else:
        txt = cta or "TOQUE NO LINK DA BIO"; f = _fonte(50); ty = 1330 if mostrar_link else h - SEGURO_BASE - 150
        d.rounded_rectangle((90, ty, 990, ty + 120), 60, fill=ROSA)
        _negrito(d, ((w - d.textlength(txt, font=f)) / 2, ty + 33), txt, f, BRANCO)
        yy = ty + 140
        if mostrar_link and link_curto(c):
            fl = _fonte(46); lt = "ou digite: " + link_curto(c)
            d.text(((w - d.textlength(lt, font=fl)) / 2, yy), lt, font=fl, fill=BRANCO); yy += 64
        rod = "entre na comunidade e escolha seus grupos"; fr = _fonte(32, False)
        d.text(((w - d.textlength(rod, font=fr)) / 2, yy), rod, font=fr, fill=ROSA_CLARO)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=92, subsampling=0)
    return buf.getvalue()


def legenda(c, link_bio="Link na bio 👆 (entre na comunidade e escolha seus grupos)"):
    """Legenda do feed. O link de afiliado nao vai aqui (nao clica no Instagram): o post leva a bio."""
    preco = preco_texto(c.get("E"))
    linhas = [c.get("R") or "", f"🛍️ {c.get('B')}", f"💰 {preco}"]
    if c.get("G"): linhas.append(f"🏷️ Cupom: {c['G']}")
    if c.get("I"): linhas += ["", f"🔗 Link do produto (copie e cole no navegador): {c['I']}"]
    linhas += ["", f"👉 {link_bio}", "", f"{BASE_TAGS} {HASHTAGS.get(c.get('C'), '')}".strip()]
    return "\n".join(x for i, x in enumerate(linhas) if x or (i and linhas[i - 1]))[:2200].strip()
