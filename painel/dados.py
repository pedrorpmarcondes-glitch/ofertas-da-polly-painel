"""Camada de dados do painel: lê e grava a planilha e os arquivos de apoio (no GitHub, ou local).

A planilha ofertas-polly.xlsx continua sendo o banco. Nada de token do Z-API passa por aqui,
e nenhum telefone ou nome de cliente é lido.
"""
import sys, io, json, csv, base64, re, subprocess
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
import openpyxl
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import enviar_ofertas as eo  # mesmas regras de validação e mesmo modelo de mensagem da automação

STATUS_ORDEM = ["Rascunho", "Aguardando aprovação", "Aprovada", "Enviada", "Erro", "Expirada", "Removida"]


def segredo(chave, padrao=None):
    try: return st.secrets.get(chave, padrao)
    except Exception: return padrao  # sem arquivo de segredos = modo local


TOKEN, REPO = segredo("GITHUB_TOKEN"), segredo("GITHUB_REPO")
NUVEM = bool(TOKEN and REPO)
PERMITIDOS = [e.lower() for e in segredo("USUARIOS_PERMITIDOS", [])]


def quem_e():
    u = getattr(st, "user", None) or getattr(st, "experimental_user", None)
    return (getattr(u, "email", None) or "").lower() if u else ""


EMAIL = quem_e() or "painel-local"


def _h(raw=False):
    return {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}


def ler(path, binario=False):
    """Devolve (conteúdo, sha) do arquivo no repositório (nuvem) ou na pasta local."""
    if NUVEM:
        url = f"https://api.github.com/repos/{REPO}/contents/{path}"
        m = requests.get(url, headers=_h(), timeout=30)
        if m.status_code == 404: return None, None
        m.raise_for_status()
        r = requests.get(url, headers=_h(raw=True), timeout=30); r.raise_for_status()
        return (r.content if binario else r.text), m.json()["sha"]
    p = RAIZ / path
    if not p.exists(): return None, None
    return (p.read_bytes() if binario else p.read_text()), None


def _git(*args):
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, timeout=90)


def publicar_local(path, mensagem):
    """No Mac, a automação da nuvem só enxerga o que chega ao GitHub: toda gravação local sobe também."""
    if not (RAIZ / ".git").exists(): return
    _git("add", path)
    if _git("diff", "--cached", "--quiet").returncode == 0: return
    _git("commit", "-m", mensagem)
    if _git("pull", "--rebase", "--autostash", "-X", "theirs").returncode:
        _git("rebase", "--abort"); raise RuntimeError("Salvo neste Mac, mas não sincronizou com a nuvem. Tente de novo.")
    if _git("push").returncode: raise RuntimeError("Salvo neste Mac, mas não chegou à nuvem. Confira a internet e tente de novo.")


@st.cache_data(ttl=300, show_spinner=False)
def atualizar_local():
    """Traz para o Mac o que a automação gravou na nuvem (envios, erros, membros)."""
    if NUVEM:  # online o código vem de um repositório só de código: os textos ficam no privado
        for nome in ("modelo-mensagem.txt", "modelo-destaque.txt"):
            texto = ler(nome)[0]
            if texto: (eo.AQUI / nome).write_text(texto)
        return True
    if not (RAIZ / ".git").exists(): return False
    if _git("pull", "--rebase", "--autostash").returncode: _git("rebase", "--abort"); return False
    return True


def gravar(path, conteudo: bytes, sha, mensagem):
    if NUVEM:
        corpo = {"message": mensagem, "content": base64.b64encode(conteudo).decode(), "branch": "main"}
        if sha: corpo["sha"] = sha
        r = requests.put(f"https://api.github.com/repos/{REPO}/contents/{path}", headers=_h(), json=corpo, timeout=60)
        if r.status_code in (409, 422): raise RuntimeError("A planilha mudou enquanto você editava. Atualize a página e tente de novo.")
        r.raise_for_status()
        if path.startswith("modelo-"): (eo.AQUI / path).write_bytes(conteudo)
        return
    p = RAIZ / path
    if p.exists():  # cópia de segurança local antes de sobrescrever
        (RAIZ / "backups").mkdir(exist_ok=True)
        (RAIZ / "backups" / f"{p.stem}-{datetime.now():%Y%m%d-%H%M%S}{p.suffix}").write_bytes(p.read_bytes())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(conteudo)
    publicar_local(path, mensagem)


def disparar_envio(oferta_id):
    """Pede ao GitHub Actions para enviar UMA oferta agora (os segredos do Z-API ficam lá)."""
    if not NUVEM: return False, "Modo local: nada foi enviado. O envio só funciona na versão online, pelo GitHub."
    r = requests.post(f"https://api.github.com/repos/{REPO}/actions/workflows/ofertas.yml/dispatches", headers=_h(),
                      json={"ref": "main", "inputs": {"modo": "oferta", "oferta": oferta_id, "janela": "60"}}, timeout=30)
    if r.status_code == 204: return True, "Envio pedido ao GitHub. Em alguns minutos o resultado aparece em “Resultado dos envios”."
    return False, f"Não foi possível pedir o envio (erro {r.status_code})."


def carregar():
    dados, sha = ler("ofertas-polly.xlsx", binario=True)
    return openpyxl.load_workbook(io.BytesIO(dados)), sha


def salvar(wb, sha, mensagem):
    buf = io.BytesIO(); wb.save(buf)
    gravar("ofertas-polly.xlsx", buf.getvalue(), sha, mensagem)
    st.cache_data.clear()


@st.cache_data(ttl=60, show_spinner=False)
def auxiliares():
    est, _ = ler("enviados.json"); lg, _ = ler("log.csv"); mt, _ = ler("dados-painel/metricas.json")
    vd, _ = ler("dados-painel/vendas.csv"); mp, _ = ler("grupos.json")
    return {"enviados": json.loads(est) if est else {}, "log": lg or "", "metricas": json.loads(mt) if mt else None,
            "vendas": vd or "", "grupos": json.loads(mp) if mp else {}}


@st.cache_data(ttl=600, show_spinner=False)
def foto(oid):
    try: return ler(f"imagens/oferta-{oid}.jpg", binario=True)[0]
    except Exception: return None


@st.cache_data(ttl=3600, show_spinner=False)
def foto_mini(oid, lado=96):
    """Miniatura em data URI para tabelas e cartões (leve, sem depender de caminho local)."""
    bruto = foto(oid)
    if not bruto: return None
    try:
        im = Image.open(io.BytesIO(bruto)).convert("RGB"); im.thumbnail((lado, lado))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=78)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception: return None


def log_linhas():
    return [l for l in csv.reader(io.StringIO(auxiliares()["log"])) if len(l) >= 4]


def preco_bonito(v):
    if v in (None, ""): return ""
    try:
        t = str(v)
        if t.startswith("ap:"): return "a partir de " + eo.brl(float(t[3:].replace(",", ".")))
        a, b = eo.faixa(v)
        return eo.brl(a) if a == b else f"{eo.brl(a)} a {eo.brl(b)}"
    except (TypeError, ValueError): return str(v)


def tabela(wb):
    ws = wb["Ofertas"]; aux = auxiliares(); estado = aux["enviados"]
    erros = {l[1]: l[0][:10] for l in log_linhas() if l[3] == "erro"}
    hoje = date.today(); linhas = []
    for r in ws.iter_rows(min_row=2, max_col=18):
        c = {x.column_letter: x.value for x in r}
        if not c.get("A"): continue
        bruto = str(c.get("L") or ""); val = eo.como_data(c.get("H")); env = estado.get(str(c["A"]))
        if bruto.startswith("Removido"): s = "Removida"
        elif val and val.date() < hoje: s = "Expirada"
        elif bruto in ("Rascunho", "Aguardando aprovação"): s = bruto
        elif erros.get(str(c["A"])) and (not env or erros[str(c["A"])] >= env): s = "Erro"
        elif env: s = "Enviada"
        else: s = "Aprovada"
        conf = eo.como_data(c.get("K"))
        linhas.append({"ID": c["A"], "Produto": c.get("B"), "Categoria": c.get("C"), "Loja": c.get("D"),
                       "Preço": preco_bonito(c.get("E")), "Antes": preco_bonito(c.get("F")),
                       "Validade": val.strftime("%d/%m/%Y") if val else "", "Status": s, "Enviada em": env or "",
                       "Conferido em": conf.date() if conf else None})
    df = pd.DataFrame(linhas)
    df["Próximo envio"] = proximos_envios(df, int(config(wb).get("CICLO_DIAS") or 1))
    return df


@st.cache_data(ttl=300, show_spinner=False)
def hora_envio():
    try: return ler_horarios()["envio"][0]
    except Exception: return "09:07"


def proximos_envios(df, ciclo):
    """Mesma conta do enviar_ofertas.py: cada oferta tem um dia fixo pela ordem do ID."""
    ciclo = max(1, ciclo); hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date(); ids = sorted(df["ID"].astype(str), key=lambda i: int(re.sub(r"\D", "", i) or 0))
    pos = {i: n for n, i in enumerate(ids)}; saida = []
    h, m = map(int, hora_envio().split(":")); agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    rodada_passou = agora.hour * 60 + agora.minute > h * 60 + m + 150  # a rodada espalha os envios por cerca de 2h
    for _, o in df.iterrows():
        if o["Status"] not in ("Aprovada", "Enviada", "Erro"): saida.append(""); continue
        dias = (pos[str(o["ID"])] % ciclo - hoje.toordinal() % ciclo) % ciclo
        if dias == 0 and (rodada_passou or o["Enviada em"] == hoje.isoformat()): dias = ciclo
        saida.append((hoje + timedelta(days=dias)).isoformat())
    return saida


COLUNAS_VENDAS = ["data", "loja", "produto_id", "cliques", "pedidos", "comissao"]


def vendas_df():
    """Lê dados-painel/vendas.csv. Sem arquivo, devolve tabela vazia (nada é estimado)."""
    txt = auxiliares()["vendas"]
    if not txt.strip(): return pd.DataFrame(columns=COLUNAS_VENDAS)
    v = pd.read_csv(io.StringIO(txt))
    for col in ("cliques", "pedidos", "comissao"):
        v[col] = pd.to_numeric(v[col], errors="coerce").fillna(0) if col in v else 0
    v["data"] = pd.to_datetime(v["data"], errors="coerce")
    return v.dropna(subset=["data"])


def registrar_venda(data, loja, cliques, pedidos, comissao, produto=""):
    txt, sha = ler("dados-painel/vendas.csv")
    txt = txt if txt and txt.strip() else ",".join(COLUNAS_VENDAS) + "\n"
    if not txt.endswith("\n"): txt += "\n"
    txt += f"{data.isoformat()},{loja},{produto},{int(cliques)},{int(pedidos)},{comissao:.2f}\n"
    gravar("dados-painel/vendas.csv", txt.encode(), sha, f"painel: comissão de {loja} em {data} por {EMAIL}")
    st.cache_data.clear()


def linha_da_oferta(wb, oid):
    for r in wb["Ofertas"].iter_rows(min_row=2, max_col=18):
        if str(r[0].value) == str(oid): return r
    return None


def dict_da_linha(r): return {x.column_letter: x.value for x in r}


def categorias(wb): return [r[0].value for r in wb["Grupos"].iter_rows(min_row=2, max_col=1) if r[0].value]


def config(wb): return {r[0].value: r[1].value for r in wb["Config"].iter_rows(min_row=2) if r[0].value}


def preco_num(t):
    t = (t or "").strip()
    if not t: return None
    if t.startswith("ap:") or "-" in t: return t
    return float(t.replace(",", "."))


def salvar_config(wb, sha, chave, valor, nota=""):
    ws = wb["Config"]
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 1).value == chave: ws.cell(r, 2).value = valor; break
    else:
        r = ws.max_row + 1; ws.cell(r, 1).value = chave; ws.cell(r, 2).value = valor; ws.cell(r, 3).value = nota
    salvar(wb, sha, f"painel: {chave}={valor} por {EMAIL}")


WORKFLOW = ".github/workflows/ofertas.yml"
DIAS_CRON = {"Domingo": 0, "Segunda": 1, "Terça": 2, "Quarta": 3, "Quinta": 4, "Sexta": 5, "Sábado": 6}
FUSO = 180  # Brasília = UTC-3, em minutos


def ler_horarios(txt=None):
    """Devolve {modo: (hh:mm, [dias])} a partir do agendamento em Brasília."""
    txt = txt if txt is not None else ler(WORKFLOW)[0]; saida = {}
    for modo in ("envio", "destaque", "enquete"):
        g = re.search(r'"(\d+) (\d+) \* \* ([\d,*]+)"\|"[^"]+"\)\s+MODO=' + modo, txt)
        if not g: continue
        total = int(g[2]) * 60 + int(g[1]) - FUSO; volta = -1 if total < 0 else 0; total %= 1440
        dias = [] if g[3] == "*" else [n for n, v in DIAS_CRON.items() if (v - volta) % 7 in {(int(x)) for x in g[3].split(",")}]
        saida[modo] = (f"{total // 60:02d}:{total % 60:02d}", dias)
    return saida


def _cron(hhmm, dias=None, extra=0):
    h, m = map(int, hhmm.split(":")); total = h * 60 + m + FUSO + extra; avanco = total // 1440; total %= 1440
    dow = "*" if not dias else ",".join(str(x) for x in sorted({(DIAS_CRON[d] + avanco) % 7 for d in dias}))
    return f"{total % 60} {total // 60} * * {dow}"


def montar_workflow(txt, envio, destaque, enquete, dias_enquete):
    """Reescreve só os horários do arquivo da automação. Cada rotina mantém o disparo de reserva 30 min depois."""
    pares = {"envio": (envio, None), "destaque": (destaque, None), "enquete": (enquete, dias_enquete)}
    rot = {"envio": "boas-vindas + ofertas", "destaque": "destaque do dia", "enquete": "enquete"}; bloco = ""
    for modo, (hora, dias) in pares.items():
        a, b = _cron(hora, dias), _cron(hora, dias, 30)
        bloco += f'    - cron: "{a}"  # ~{hora} (Brasília): {rot[modo]}\n    - cron: "{b}"  # reserva\n'
        txt, n = re.subn(r'"[^"]+"\|"[^"]+"\)(\s+)MODO=' + modo, f'"{a}"|"{b}")\\1MODO={modo}', txt)
        if n != 1: raise RuntimeError("Não encontrei a rotina no arquivo da automação.")
    novo, n = re.subn(r"(  schedule:\n)(?:    #.*\n|    - cron:.*\n)+", lambda m: m[1] + "    # Cada rotina tem um disparo de reserva; o script não repete o que já saiu no dia.\n" + bloco, txt)
    if n != 1: raise RuntimeError("Não encontrei o agendamento no arquivo da automação.")
    return novo


def salvar_horarios(envio, destaque, enquete, dias_enquete):
    txt, sha = ler(WORKFLOW)
    gravar(WORKFLOW, montar_workflow(txt, envio, destaque, enquete, dias_enquete).encode(), sha, f"painel: horários alterados por {EMAIL}")


TEMPLATES = {"modelo-mensagem.txt": ("Mensagem da oferta", {"chamada", "produto", "preco", "cupom", "validade", "loja", "link"}, {"link"}),
             "modelo-boasvindas.txt": ("Boas-vindas (Avisos)", set(), set()),
             "modelo-destaque.txt": ("Destaque do dia (Avisos)", {"chamada", "produto", "preco", "link", "categoria", "link_grupo"}, {"link"}),
             "modelo-enquete.txt": ("Pergunta da enquete (Avisos)", set(), set())}
EXEMPLO = {"chamada": "🔥 40% OFF! Corre que acaba.", "produto": "Kit 3 Toalhas de Banho", "preco": "R$ 49,90 (antes: R$ 79,90)", "cupom": "CUPOM-EXEMPLO", "validade": "",
           "loja": "Shopee", "link": "https://s.shopee.com.br/exemplo", "categoria": "Casa e Cozinha", "link_grupo": "https://chat.whatsapp.com/exemplo"}


def validar_template(nome, texto):
    if not texto.strip(): return "O texto não pode ficar vazio."
    _, permitidos, obrig = TEMPLATES[nome]
    if not permitidos: return None
    if texto.count("{") != texto.count("}"): return "Há uma chave { ou } sem par."
    usados = set(re.findall(r"{(\w*)}", texto))
    if usados - permitidos: return "Campo desconhecido: " + ", ".join(sorted("{" + u + "}" for u in usados - permitidos))
    if obrig - usados: return "O texto precisa ter " + ", ".join("{" + o + "}" for o in sorted(obrig)) + "."
    try: texto.format(**{k: "x" for k in permitidos})  # mesma montagem da automação: se falhar aqui, falharia no envio
    except (ValueError, KeyError, IndexError): return "Há chaves { } fora do lugar. Use só campos como {produto}."
    return None


def previa_template(nome, texto):
    if not TEMPLATES[nome][1]: return texto
    saida = []
    for linha in texto.splitlines():
        if any(not EXEMPLO.get(u) for u in re.findall(r"{(\w+)}", linha)): continue
        saida.append(linha.format(**EXEMPLO))
    return "\n".join(saida)
