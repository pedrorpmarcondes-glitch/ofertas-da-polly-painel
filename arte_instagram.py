"""Arte dos posts do Instagram (feed 4:5 e stories 9:16) no estilo Pinterest rosa e preto, feita com Pillow.

Usada pelo painel (previa) e pela rotina que publica: o que a Polly aprova na previa e o que vai ao ar sao
o mesmo arquivo. Duas formas:
- capa (estilo "capa A"): foto da modelo em tela cheia com o produto, frase amarela, faixa branca e estrelas.
  Usada quando existe imagens/capa-<ID>.jpg.
- produto: fundo rosa claro, foto do produto num cartao branco e o preco. Usada quando nao ha foto da modelo.
Fontes livres (SIL OFL) na pasta fonts: Poppins, Playfair Display Italic e Great Vibes.
"""
import io
import math
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

AMARELO, BRANCO, ROSA, ROSA_CLARO, CREME = (255, 232, 150), (255, 255, 255), (255, 120, 178), (255, 206, 228), (255, 247, 232)
VINHO, ROSA_FORTE, FUNDO_ROSA, ESCURO = (120, 30, 70), (190, 50, 110), (253, 233, 240), (26, 6, 16)
TAMANHOS = {"feed": (1080, 1350), "stories": (1080, 1920)}
# Stories: o Instagram cobre o topo (perfil) e a base (resposta). Nada importante nessas faixas.
SEGURO_TOPO, SEGURO_BASE = 250, 340
HASHTAGS = {"Beleza": "#beleza #skincare #cuidadoscomapele", "Casa e Cozinha": "#casa #cozinha #utilidadesdomesticas",
            "Moda": "#moda #look #estilo", "Eletrônicos": "#eletronicos #tecnologia #gadgets",
            "Organização e Limpeza": "#organizacao #limpeza #casaorganizada", "Natal e Decoração": "#natal #decoracao #decoracaodenatal",
            "Fitness e Esportes": "#fitness #treino #esportes",
            "Decoração": "#decoracao #casadecorada #decor", "Kids": "#kids #infantil #maternidade"}
BASE_TAGS = "#ofertas #achadinhos #promocao #ofertasdapolly"
# Frase da capa por categoria: (linha amarela, linha branca). A faixa do meio vem dos vendidos ou do preco.
FRASES = {"Beleza": ("o queridinho", "pro seu skincare"), "Casa e Cozinha": ("o achadinho", "pra sua cozinha"),
          "Moda": ("o achadinho", "pro seu look"), "Eletrônicos": ("o achadinho", "que facilita a vida"),
          "Organização e Limpeza": ("o achadinho", "pra casa organizada"), "Natal e Decoração": ("o achadinho", "pro seu natal"),
          "Fitness e Esportes": ("o achadinho", "pro seu treino"),
          "Decoração": ("o achadinho", "pra decorar"), "Kids": ("o achadinho", "pros pequenos")}
ASSUNTO = {"Beleza": "achadinho de beleza", "Casa e Cozinha": "achadinho de casa", "Moda": "achadinho de moda",
           "Eletrônicos": "achadinho de tecnologia", "Organização e Limpeza": "achadinho de organização",
           "Natal e Decoração": "achadinho de natal", "Fitness e Esportes": "achadinho fitness",
           "Decoração": "achadinho de decoração", "Kids": "achadinho kids"}

FONTES = Path(__file__).resolve().parent / "fonts"
_ARQ = {"forte": "Poppins-Bold.ttf", "media": "Poppins-SemiBold.ttf", "leve": "Poppins-Medium.ttf",
        "serifa": "PlayfairDisplay-Italic.ttf", "cursiva": "GreatVibes-Regular.ttf"}


def _fonte(tamanho, tipo="forte"):
    for nome in (_ARQ.get(tipo), "LiberationSans-Bold.ttf"):
        try: return ImageFont.truetype(str(FONTES / nome), tamanho)
        except (OSError, TypeError): pass
    return ImageFont.load_default(size=tamanho)


def _sem_emoji(txt):
    """As fontes nao tem emoji: na imagem vai so o texto; a legenda do post mantem os emojis."""
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


def link_curto(c):
    """Link do produto sem o https://, para caber na arte e ser digitado."""
    return re.sub(r"^https?://", "", str(c.get("I") or "")).strip("/")


def _vendidos(c):
    """Desligado (06/11/2026): por decisão do dono, a arte não mostra quantidade vendida nem nota."""
    return ""


def _nome_curto(c):
    """Nome do produto sem o detalhe depois da virgula ou do traco: cabe em duas linhas."""
    n = re.split(r",| - | – | \| ", _sem_emoji(c.get("B")))[0].strip()
    return n.lower() if n.isupper() or len(n) > 18 else n


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


def _cabe(texto, tipo, tam, largura, minimo=30):
    while tam > minimo and _fonte(tam, tipo).getlength(texto) > largura: tam -= 2
    return _fonte(tam, tipo)


# ------------------------------------------------------------------ pecas
def _texto(im, xy, t, f, cor, sombra=70, sp=0):
    """Texto centralizado em x com sombra macia e letras mais juntas (sp<0), como nas referencias."""
    larg = sum(f.getlength(ch) + sp for ch in t) - sp
    cam = Image.new("RGBA", im.size, (0, 0, 0, 0)); som = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dc, ds = ImageDraw.Draw(cam), ImageDraw.Draw(som); x, y = xy[0] - larg / 2, xy[1]
    for ch in t:
        if sombra: ds.text((x, y + 3), ch, font=f, fill=(50, 10, 30, sombra), anchor="lm")
        dc.text((x, y), ch, font=f, fill=cor, anchor="lm"); x += f.getlength(ch) + sp
    if sombra:
        som = som.filter(ImageFilter.GaussianBlur(7)); im.paste(som, (0, 0), som)
    im.paste(cam, (0, 0), cam)
    return larg


def _estrela(im, cx, cy, r, cor, rot=-10):
    ss = 3; lado = int(r * 2.4) * ss; c = Image.new("RGBA", (lado, lado), (0, 0, 0, 0)); o = lado / 2; p = []
    for k in range(10):
        a = math.radians(rot - 90 + k * 36); q = (r if k % 2 == 0 else r * .45) * ss; p.append((o + q * math.cos(a), o + q * math.sin(a)))
    ImageDraw.Draw(c).polygon(p, fill=cor + (255,)); c = c.resize((lado // ss,) * 2, Image.LANCZOS)
    im.paste(c, (int(cx - c.width / 2), int(cy - c.height / 2)), c)


def _assinatura(im, y, tam=210, alfa=150, cor=ROSA_CLARO):
    """'achadinhos' em letra cursiva, grande e cortada nas bordas."""
    c = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(c).text((im.width / 2, y), "achadinhos", font=_fonte(tam, "cursiva"), fill=cor + (alfa,), anchor="mm")
    im.paste(c, (0, 0), c)


def _traco(im, y, larg, cor=ROSA_CLARO):
    d = ImageDraw.Draw(im); w = im.width
    d.rectangle(((w - larg) / 2, y, (w + larg) / 2, y + 5), fill=cor); d.rectangle(((w - larg) / 2 + 60, y + 13, (w + larg) / 2 - 60, y + 16), fill=cor)


def _faixa(im, cy, t):
    """Faixa branca com fundo rosinha e dois alfinetes, como na referencia."""
    f = _cabe(t.upper(), "leve", 40, 760); w = f.getlength(t.upper()) + 160; h = 98; cx = im.width // 2
    som = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(som).rounded_rectangle((cx - w / 2, cy - h / 2 + 7, cx + w / 2, cy + h / 2 + 7), 26, fill=(50, 10, 30, 90))
    som = som.filter(ImageFilter.GaussianBlur(12)); im.paste(som, (0, 0), som)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), 26, fill=BRANCO)
    d.rounded_rectangle((cx - w / 2 + 14, cy - h / 2 + 14, cx + w / 2 - 14, cy + h / 2 - 14), 12, fill=(255, 233, 242))
    for lx in (cx - w / 2 + 36, cx + w / 2 - 36):
        d.line((lx, cy - 20, lx, cy + 20), fill=VINHO, width=4); d.ellipse((lx - 6, cy - 26, lx + 6, cy - 14), fill=VINHO)
    d.text((cx, cy), t.upper(), font=f, fill=(70, 40, 55), anchor="mm")
    return w


def _degrade(im, inicio, forca=205):
    w, h = im.size; m = Image.new("L", (1, h), 0)
    for y in range(h):
        t = max(0, (y - inicio) / max(1, h - inicio)); m.putpixel((0, y), int(forca * min(1, t * 1.5) ** 1.3))
    im.paste(Image.new("RGB", (w, h), ESCURO), (0, 0), m.resize((w, h)))


def _botao(im, y, t):
    d = ImageDraw.Draw(im); f = _cabe(t, "forte", 50, 780)
    d.rounded_rectangle((90, y, 990, y + 120), 60, fill=ROSA_FORTE)
    d.text((im.width / 2, y + 60), t, font=f, fill=BRANCO, anchor="mm")


def _jpeg(im):
    buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92, subsampling=0)
    return buf.getvalue()


# ------------------------------------------------------------------ capa (foto da modelo)
def _capa(c, capa_bytes, formato, cta, mostrar_link):
    w, h = TAMANHOS[formato]
    im = ImageOps.fit(Image.open(io.BytesIO(capa_bytes)).convert("RGB"), (w, h), Image.LANCZOS, centering=(.5, .1))
    im = ImageEnhance.Color(ImageEnhance.Brightness(im).enhance(1.05)).enhance(1.05)
    base = h - 470 if formato == "feed" else h - SEGURO_BASE - 420
    _degrade(im, base - 200)
    for x, y, r in [(90, 150, 26), (980, 120, 20), (830, 250, 16), (70, 430, 18), (1000, 520, 24)]:
        _estrela(im, x, y + (0 if formato == "feed" else SEGURO_TOPO), r, BRANCO)
    if formato == "feed": _assinatura(im, h - 70)
    l1, l2 = FRASES.get(c.get("C"), ("o achadinho", "que você precisa ter"))
    faixa = f"com {_vendidos(c)}" if _vendidos(c) else f"por {preco_texto(c.get('E'))}"
    _texto(im, (w / 2, base + 15), l1, _cabe(l1, "forte", 74, 900), AMARELO, sp=-3)
    _faixa(im, base + 125, faixa)
    _texto(im, (w / 2, base + 235), l2, _cabe(l2, "forte", 74, 900), BRANCO, sp=-3)
    _traco(im, base + 295, 520)
    _estrela(im, w / 2 + 455, base - 60, 44, ROSA); _estrela(im, w / 2 - 385, base + 225, 44, ROSA, rot=8)
    if formato == "feed":
        if mostrar_link and link_curto(c):
            _texto(im, (w / 2, h - 150), "link do produto: " + link_curto(c), _cabe("link do produto: " + link_curto(c), "media", 30, 960, 18), BRANCO, sombra=120)
    else:
        rodape = cta or "toque no link da bio"
        if mostrar_link and link_curto(c): rodape = "ou digite: " + link_curto(c)
        _texto(im, (w / 2, base + 375), rodape, _cabe(rodape, "media", 40, 960, 20), ROSA_CLARO, sombra=120)
    return _jpeg(im)


# ------------------------------------------------------------------ produto (sem foto da modelo)
def _produto(c, foto_bytes, formato, cta, mostrar_link):
    w, h = TAMANHOS[formato]; im = Image.new("RGB", (w, h), FUNDO_ROSA); d = ImageDraw.Draw(im)
    topo = 70 if formato == "feed" else SEGURO_TOPO + 20
    for x, y, r in [(90, 30, 22), (1000, 10, 16), (980, 200, 26), (60, 380, 16)]: _estrela(im, x, topo + y, r, BRANCO)
    if formato == "feed": _assinatura(im, h - 110, tam=230, alfa=120)
    f_nome = _fonte(62, "forte"); y = topo + 40
    for linha in _quebrar(d, _nome_curto(c), f_nome, 940, 2):
        _texto(im, (w / 2, y), linha, f_nome, VINHO, sombra=0, sp=-2); y += 74
    sub = _vendidos(c) or ASSUNTO.get(c.get("C"), "achadinho do dia")
    _texto(im, (w / 2, y + 6), sub, _fonte(60, "serifa"), ROSA_FORTE, sombra=0); y += 70
    by = h - SEGURO_BASE - 150 - (64 if mostrar_link and link_curto(c) else 0)  # botao do stories
    cw = 800; ch = (h - 330 - y - 40) if formato == "feed" else (by - 190 - (y + 20)); cx0, cy0 = (w - cw) // 2, y + 20
    som = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(som).rounded_rectangle((cx0, cy0 + 12, cx0 + cw, cy0 + ch + 12), 46, fill=ROSA_FORTE + (80,))
    som = som.filter(ImageFilter.GaussianBlur(24)); im.paste(som, (0, 0), som)
    d.rounded_rectangle((cx0, cy0, cx0 + cw, cy0 + ch), 46, fill=BRANCO)
    if foto_bytes:
        p = Image.open(io.BytesIO(foto_bytes)).convert("RGB"); p.thumbnail((cw - 80, ch - 80), Image.LANCZOS)
        im.paste(p, ((w - p.width) // 2, cy0 + (ch - p.height) // 2))
    _estrela(im, cx0 + cw - 10, cy0 + 20, 62, ROSA); _estrela(im, cx0 + 5, cy0 + ch - 30, 50, ROSA, rot=12)
    y = cy0 + ch + 90; preco = preco_texto(c.get("E"))
    _texto(im, (w / 2, y), preco, _cabe(preco, "forte", 96, 940, 40), ROSA_FORTE, sombra=0, sp=-3)
    if formato == "feed":
        if mostrar_link and link_curto(c):
            lt = "link do produto: " + link_curto(c); _texto(im, (w / 2, h - 165), lt, _cabe(lt, "media", 30, 960, 18), VINHO, sombra=0)
        _texto(im, (w / 2, h - 50), "LINK NA BIO  ·  @ofertasdapolly_", _fonte(28, "media"), VINHO, sombra=0)
    else:
        _botao(im, by, (cta or "toque no link da bio").upper()); yy = by + 160
        if mostrar_link and link_curto(c):
            lt = "ou digite: " + link_curto(c); _texto(im, (w / 2, yy), lt, _cabe(lt, "media", 40, 960, 20), VINHO, sombra=0); yy += 60
        _texto(im, (w / 2, yy), "entre na comunidade e escolha seus grupos", _fonte(30, "leve"), VINHO, sombra=0)
    return _jpeg(im)


def renderizar(c, foto_bytes, formato="feed", cta=None, mostrar_link=False, capa_bytes=None):
    """c: dict com as colunas da planilha (B produto, E preco, R chamada, C categoria). Devolve bytes JPEG.
    capa_bytes: foto da modelo com o produto (imagens/capa-<ID>.jpg); sem ela, sai o slide de produto."""
    if capa_bytes: return _capa(c, capa_bytes, formato, cta, mostrar_link)
    return _produto(c, foto_bytes, formato, cta, mostrar_link)


def legenda(c, link_bio="Link na bio 👆 (entre na comunidade e escolha seus grupos)", link_produto=False):
    """Legenda do feed. O link de afiliado nao vai aqui (nao clica no Instagram): o post leva a bio."""
    preco = preco_texto(c.get("E"))
    linhas = [c.get("R") or "", f"🛍️ {c.get('B')}", f"💰 {preco}"]
    if c.get("G"): linhas.append(f"🏷️ Cupom: {c['G']}")
    if link_produto and c.get("I"): linhas += ["", f"🔗 Link do produto (copie e cole no navegador): {c['I']}"]
    linhas += ["", f"👉 {link_bio}", "", f"{BASE_TAGS} {HASHTAGS.get(c.get('C'), '')}".strip()]
    return "\n".join(x for i, x in enumerate(linhas) if x or (i and linhas[i - 1]))[:2200].strip()
