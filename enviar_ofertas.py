#!/usr/bin/env python3
"""Ofertas da Polly: valida a planilha, monta as mensagens e (opcionalmente) envia pela Z-API.

Padrão = SIMULAÇÃO: nada é enviado, só gera mensagens-do-dia.txt.
Envio real exige: --enviar, ENVIO_REAL=SIM no .env e digitar CONFIRMO no terminal.
"""
import argparse, csv, re, json, os, sys, time, random, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
import openpyxl

AQUI = Path(__file__).parent
AVISO = "🔗 Link de afiliado: posso receber comissão se você comprar, sem custo adicional para você."
OBRIGATORIOS = {"B": "Produto", "C": "Categoria", "D": "Loja", "E": "Preço atual", "I": "Link afiliado", "J": "Fonte", "K": "Data da conferência"}

def carregar_env():
    env = dict(os.environ)
    f = AQUI / ".env"
    if f.exists():
        for linha in f.read_text().splitlines():
            if "=" in linha and not linha.strip().startswith("#"):
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def como_data(v):
    if isinstance(v, datetime): return v
    if isinstance(v, str):
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try: return datetime.strptime(v.strip(), fmt)
            except ValueError: pass
    return None

def brl(v): return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def faixa(v):
    """Preço pode ser número ou faixa 'min-max' (produto com variações). Devolve (min, max)."""
    if isinstance(v, str) and v.startswith("ap:"):
        x = float(v[3:]); return x, x
    if isinstance(v, str) and "-" in v:
        a, b = (float(x.replace(",", ".")) for x in v.split("-", 1)); return a, b
    x = float(v); return x, x

def preco_txt(v):
    a, b = faixa(v)
    if isinstance(v, str) and v.startswith("ap:"): return f"a partir de {brl(a)}"
    return brl(a) if a == b else f"{brl(a)} a {brl(b)} (conforme a variação)"

def validar(c, cfg, grupos):
    """Devolve None se OK, ou o motivo do bloqueio (mesmas regras da planilha)."""
    if cfg.get("PAUSA_GERAL", "NAO").upper() == "SIM": return "pausa geral ligada"
    falta = [n for col, n in OBRIGATORIOS.items() if c.get(col) in (None, "")]
    if falta: return "campo vazio: " + ", ".join(falta)
    try: atual, maximo = faixa(c["E"])
    except (TypeError, ValueError): return "preço atual inválido"
    if atual > maximo: return "faixa de preço invertida"
    if atual <= 0: return "preço atual inválido"
    if c.get("F") not in (None, ""):
        try:
            if float(c["F"]) <= atual: return "preço anterior não é maior que o atual"
        except (TypeError, ValueError): return "preço anterior inválido"
    val = como_data(c.get("H"))
    if c.get("H") not in (None, "") and (val is None or val.date() < datetime.now().date()): return "prazo de envio encerrado ou inválido"
    if como_data(c["K"]) is None: return "data da conferência ilegível"
    if not str(c["I"]).startswith("https://"): return "link inválido"
    if c["C"] not in grupos: return "categoria sem grupo configurado"
    return None

def mensagem(c, cfg):
    """Monta a mensagem a partir de modelo-mensagem.txt. Linha com campo vazio é omitida."""
    val = como_data(c.get("H"))
    campos = {"produto": c["B"], "preco": preco_txt(c["E"]) + (f" (antes: {brl(c['F'])})" if c.get("F") not in (None, "") else ""),
              "chamada": c.get("R") or "", "cupom": c.get("G") or "", "validade": f"{val:%d/%m/%Y %H:%M}" if val else "", "loja": c["D"], "link": c["I"]}
    saida = []
    for linha in (AQUI / "modelo-mensagem.txt").read_text().splitlines():
        usados = re.findall(r"{(\w+)}", linha)
        if any(not campos.get(u) for u in usados): continue
        saida.append(linha.format(**campos))
    return "\n".join(saida)

def imagem_da_oferta(c):
    for arq in sorted((AQUI / "imagens").glob(f"oferta-{c['A']}.*")): return arq
    return None

def enviar_imagem_zapi(env, destino, arq, legenda):
    import base64
    tipo = "png" if arq.suffix.lower() == ".png" else "jpeg"
    b64 = f"data:image/{tipo};base64," + base64.b64encode(arq.read_bytes()).decode()
    url = f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}/token/{env['ZAPI_TOKEN']}/send-image"  # NÃO VERIFICADO na doc oficial
    req = urllib.request.Request(url, json.dumps({"phone": destino, "image": b64, "caption": legenda}).encode(),
        {"Content-Type": "application/json", "Client-Token": env["ZAPI_CLIENT_TOKEN"]})
    with urllib.request.urlopen(req, timeout=60) as r: return r.status, r.read().decode()[:300]

def enviar_zapi(env, destino, texto):
    url = f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}/token/{env['ZAPI_TOKEN']}/send-text"  # NÃO VERIFICADO na doc oficial
    req = urllib.request.Request(url, json.dumps({"phone": destino, "message": texto}).encode(),
        {"Content-Type": "application/json", "Client-Token": env["ZAPI_CLIENT_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r: return r.status, r.read().decode()[:300]

def log(linha):
    novo = not (AQUI / "log.csv").exists()
    with open(AQUI / "log.csv", "a", newline="") as f:
        w = csv.writer(f)
        if novo: w.writerow(["quando", "id", "grupo", "acao", "resultado"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), *linha])

def enviar_enquete(env, destino, pergunta, opcoes):
    url = f"https://api.z-api.io/instances/{env['ZAPI_INSTANCE_ID']}/token/{env['ZAPI_TOKEN']}/send-poll"
    body = {"phone": destino, "message": pergunta, "poll": [{"name": o} for o in opcoes], "pollMaxOptions": 1}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "Client-Token": env["ZAPI_CLIENT_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r: return r.status, r.read().decode()[:300]

def extras(a, env, cfg, wb, mapa, estado, hoje, prontas):
    """Destaque do dia (12:00) e enquete (semanal) no grupo de Avisos."""
    destino = mapa.get("__AVISOS__")
    real = a.enviar and a.auto
    if not destino: sys.exit("__AVISOS__ não configurado.")
    if real and env.get("ENVIO_REAL", "NAO").upper() != "SIM": sys.exit("ENVIO_REAL não está SIM.")
    chave = "__DESTAQUE__" if a.destaque else "__ENQUETE__"
    if estado.get(chave) == hoje and real: print("já enviado hoje"); return
    if a.enquete:
        arq = AQUI / "modelo-enquete.txt"
        pergunta = (arq.read_text().strip() if arq.exists() else "") or "Qual categoria você quer ver mais ofertas por aqui? 👇"
        opcoes = [k for k in mapa if not k.startswith("__")]
        print("ENQUETE:", pergunta, opcoes)
        if real:
            st, corpo = enviar_enquete(env, destino, pergunta, opcoes); log(["enquete", destino, "enviada", f"{st} {corpo}"])
            estado[chave] = hoje; (AQUI / "enviados.json").write_text(json.dumps(estado))
        return
    if not prontas: print("nenhuma oferta válida para destaque"); return
    prontas.sort(key=lambda x: (estado.get("D:" + str(x[0]["A"]), ""), str(x[0]["A"])))
    c = prontas[0][0]
    links = {r[0].value: r[2].value for r in wb["Grupos"].iter_rows(min_row=2) if r[0].value}
    campos = {"chamada": c.get("R") or "", "produto": c["B"], "preco": preco_txt(c["E"]), "link": c["I"], "categoria": c["C"], "link_grupo": links.get(c["C"]) or ""}
    texto = "\n".join(l.format(**campos) for l in (AQUI / "modelo-destaque.txt").read_text().splitlines() if all(campos.get(u) for u in re.findall(r"{(\w+)}", l)))
    print("DESTAQUE:", c["A"], "\n" + texto)
    if real:
        img = imagem_da_oferta(c)
        st, corpo = enviar_imagem_zapi(env, destino, img, texto) if img else enviar_zapi(env, destino, texto)
        log(["destaque " + str(c["A"]), destino, "enviada", f"{st} {corpo}"])
        estado["D:" + str(c["A"])] = hoje; estado[chave] = hoje; (AQUI / "enviados.json").write_text(json.dumps(estado))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--planilha", default=str(AQUI / "ofertas-polly.xlsx"))
    ap.add_argument("--enviar", action="store_true", help="envio real (padrão: simulação)")
    ap.add_argument("--destaque", action="store_true", help="posta 1 oferta em destaque no Avisos (12:00)")
    ap.add_argument("--enquete", action="store_true", help="posta a enquete de categorias no Avisos")
    ap.add_argument("--auto", action="store_true", help="rodada agendada: envia sem perguntar (exige ENVIO_REAL=SIM)")
    ap.add_argument("--oferta", help="envia só esta oferta agora (ex.: P231), ignorando o ciclo de dias; usado pelo painel")
    ap.add_argument("--grupo-teste", action="store_true", help="manda tudo para o grupo de teste (ZAPI_GRUPO_TESTE)")
    a = ap.parse_args()
    env = carregar_env()
    wb = openpyxl.load_workbook(a.planilha, data_only=False)
    cfg = {r[0].value: r[1].value for r in wb["Config"].iter_rows(min_row=2) if r[0].value}
    cfg["PAUSA_GERAL"] = str(cfg.get("PAUSA_GERAL", "NAO"))
    mapa = json.loads((AQUI / "grupos.json").read_text()) if (AQUI / "grupos.json").exists() else {}
    estado = json.loads((AQUI / "enviados.json").read_text()) if (AQUI / "enviados.json").exists() else {}
    if isinstance(estado, list): estado = {i: "2026-11-02" for i in estado}  # formato antigo
    hoje = env.get("DATA_HOJE") or datetime.now().strftime("%Y-%m-%d")
    limite = int(cfg.get("MAX_OFERTAS_DIA_TOTAL") or 20)
    prontas, bloqueadas = [], []
    for row in wb["Ofertas"].iter_rows(min_row=2, max_col=18):
        c = {cell.column_letter: cell.value for cell in row}
        if not c.get("A") and not c.get("B"): continue
        if a.oferta and str(c.get("A")) != a.oferta: continue
        if c.get("L") != "Aprovado" or (estado.get(str(c.get("A"))) == hoje and not a.destaque and not a.oferta): continue
        motivo = validar(c, cfg, mapa)
        (bloqueadas if motivo else prontas).append((c, motivo))
    for c, m in bloqueadas: print(f"BLOQUEADA {c.get('A')} - {c.get('B')}: {m}"); log([c.get("A"), "", "bloqueada", m])
    if a.destaque or a.enquete:
        return extras(a, env, cfg, wb, mapa, estado, hoje, prontas)
    ciclo = int(cfg.get("CICLO_DIAS") or 0)
    if ciclo > 1 and not a.oferta:  # a rede inteira sai em `ciclo` dias e recomeça: cada oferta tem um dia fixo (pela ordem do ID)
        ordem = {}
        for row in wb["Ofertas"].iter_rows(min_row=2, max_col=1):
            i = row[0].value
            if i: ordem[str(i)] = int(re.sub(r"\D", "", str(i)) or 0)
        ids = sorted(ordem, key=lambda k: ordem[k])
        turno = datetime.strptime(hoje, "%Y-%m-%d").toordinal() % ciclo
        prontas = [(c, m) for c, m in prontas if ids.index(str(c["A"])) % ciclo == turno]
    prontas.sort(key=lambda x: estado.get(str(x[0]["A"]), ""))  # quem foi enviado há mais tempo vai primeiro
    por_grupo = int(cfg.get("MAX_POR_GRUPO_DIA") or 0)
    if por_grupo:
        usados, sel = {}, []
        for c, m in prontas:
            usados[c["C"]] = usados.get(c["C"], 0) + 1
            if usados[c["C"]] <= por_grupo: sel.append((c, m))
        prontas = sel
    prontas = prontas[:limite]
    saida = [f"=== {c['A']} | {c['C']} ===\n{mensagem(c, cfg)}\n" for c, _ in prontas]
    if mapa.get("__AVISOS__"): saida.insert(0, "=== BOAS-VINDAS | Avisos ===\n" + (AQUI / "modelo-boasvindas.txt").read_text().strip() + "\n")
    (AQUI / "mensagens-do-dia.txt").write_text("\n".join(saida) or "(nenhuma oferta pronta)\n")
    print(f"{len(prontas)} pronta(s), {len(bloqueadas)} bloqueada(s). Veja mensagens-do-dia.txt")
    if not a.enviar: print("SIMULAÇÃO: nada foi enviado."); return
    if env.get("ENVIO_REAL", "NAO").upper() != "SIM": sys.exit("ENVIO_REAL não está SIM no .env. Nada enviado.")
    if not a.auto and input(f"Enviar {len(prontas)} mensagem(ns) de verdade? Digite CONFIRMO: ").strip() != "CONFIRMO": sys.exit("Cancelado.")
    erros = 0; falhas_destino = {}
    passo = 1.0 if a.oferta else max(20.0, float(env.get("JANELA_SEG") or 6900) / (len(prontas) + 1))  # espalha o envio em ~115 min (09:00 a ~11:00)
    if mapa.get("__AVISOS__") and not a.grupo_teste and not a.oferta and estado.get("__AVISOS__") != hoje:
        try:
            st, corpo = enviar_zapi(env, mapa["__AVISOS__"], (AQUI / "modelo-boasvindas.txt").read_text().strip())
            log(["boas-vindas", mapa["__AVISOS__"], "enviada", f"{st} {corpo}"]); print("enviada boas-vindas -> Avisos")
            estado["__AVISOS__"] = hoje; (AQUI / "enviados.json").write_text(json.dumps(estado))
        except (urllib.error.URLError, KeyError) as e:
            log(["boas-vindas", mapa["__AVISOS__"], "erro", str(e)]); print(f"ERRO na boas-vindas: {e}")
        time.sleep(random.uniform(0.8 * passo, 1.2 * passo))
    for c, _ in prontas:
        destinos = [env.get("ZAPI_GRUPO_TESTE")] if a.grupo_teste else [mapa[c["C"]]] + ([mapa["__GERAL__"]] if mapa.get("__GERAL__") else [])
        img = imagem_da_oferta(c)
        ok = True
        for destino in destinos:
            if falhas_destino.get(destino, 0) >= 2:  # grupo com problema: pula o resto dele sem derrubar os outros grupos
                ok = False; log([c["A"], destino, "pulada", "grupo falhou 2 vezes nesta rodada"]); print(f"pulada {c['A']} ({destino})"); continue
            try:
                st, corpo = enviar_imagem_zapi(env, destino, img, mensagem(c, cfg)) if img else enviar_zapi(env, destino, mensagem(c, cfg))
                log([c["A"], destino, "enviada", f"{st} {corpo}"]); print(f"enviada {c['A']} -> {destino}"); erros = 0
            except (urllib.error.URLError, KeyError) as e:
                ok = False; log([c["A"], destino, "erro", str(e)]); erros += 1; falhas_destino[destino] = falhas_destino.get(destino, 0) + 1; print(f"ERRO na oferta {c['A']} ({destino}): {e}")
                if erros >= 3: sys.exit("3 erros seguidos. Parei por segurança.")
            time.sleep(random.uniform(0.8 * passo, 1.2 * passo))
        if ok:
            estado[str(c["A"])] = hoje
            (AQUI / "enviados.json").write_text(json.dumps(estado))
        continue

if __name__ == "__main__":
    main()
