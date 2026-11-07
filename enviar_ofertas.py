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

# % de comissão usado para priorizar. Amazon: tabela oficial por categoria (06/11/2026). Shopee e Mercado Livre
# variam por produto: use a coluna S ("Comissão %") quando souber; sem ela, vale o padrão da loja.
COMISSAO_PADRAO = {"Amazon": {"Beleza": 13, "Moda": 11}, "Amazon*": 8, "Shopee*": 8, "Mercado Livre*": 8}
PRECO_TETO_IMPULSO = 250  # acima disso quase ninguém compra pelo WhatsApp: perde prioridade

def ganho_estimado(c):
    """Comissão estimada por venda (R$) = preço (limitado ao teto de impulso) x % de comissão."""
    try: preco = faixa(c["E"])[0]
    except (TypeError, ValueError): return 0.0
    if preco > PRECO_TETO_IMPULSO: preco = PRECO_TETO_IMPULSO ** 2 / preco  # mais caro = compra menos por impulso
    try: pct = float(str(c.get("S")).replace("%", "").replace(",", ".")) if c.get("S") not in (None, "") else None
    except ValueError: pct = None
    if pct is None:
        loja = c.get("D") or ""
        pct = COMISSAO_PADRAO.get(loja, {}).get(c.get("C")) if isinstance(COMISSAO_PADRAO.get(loja), dict) else None
        pct = pct or COMISSAO_PADRAO.get(loja + "*", 7)
    return preco * pct / 100

# Chamada padrão (time de copy, 06/11/2026). Regra do dono: nunca citar nota, estrelas ou quantidade vendida.
CHAMADAS = {
 "Beleza": (["✨ {nome}: um mimo de beleza que você merece", "Sua rotina de beleza pediu: {nome}", "{nome} para aquele momento só seu de autocuidado 💗", "Achadinho de beleza que separei pra você: {nome}", "Autocuidado também é prioridade: {nome}", "Um toque a mais na sua rotina: {nome} ✨"],
            ["✨ {nome} com {pct}% off: autocuidado com preço de mimo", "Sua rotina de beleza com {pct}% off: {nome}", "{nome} ficou {pct}% mais em conta 💗"]),
 "Casa e Cozinha": (["Pra deixar a casa com a sua cara: {nome} 🏡", "{nome}: o detalhe que faltava na sua casa", "Achadinho pra casa que separei pra você: {nome}", "Casa bonita começa nos detalhes: {nome} ✨", "{nome} para deixar o seu cantinho mais acolhedor", "Sua casa merece esse carinho: {nome}"],
            ["{nome} com {pct}% off pra deixar a casa com a sua cara 🏡", "Casa caprichada gastando menos: {nome} com {pct}% off", "Detalhe novo pra casa, {pct}% mais em conta: {nome}"]),
 "Moda": (["Pra montar um look que é a sua cara: {nome} ✨", "{nome}: a peça que o seu guarda-roupa pedia", "Achadinho de moda que separei pra você: {nome}", "Estilo mora nos detalhes: {nome} 💫", "{nome}: pra usar do seu jeito", "Look novo, sem complicação: {nome}"],
            ["{nome} com {pct}% off: estilo que cabe no bolso ✨", "Look novo com {pct}% off: {nome}", "A peça que faltava, {pct}% mais em conta: {nome}"]),
 "Eletrônicos": (["Tecnologia que facilita o seu dia: {nome} ⚡", "{nome}: praticidade que você vai amar", "Achadinho tech que separei pra você: {nome}", "Pra quem ama tecnologia bonita: {nome} ✨", "Seu dia a dia mais prático com {nome}", "Um upgrade na sua rotina: {nome}"],
            ["{nome} com {pct}% off: upgrade com preço amigo ⚡", "Tecnologia com {pct}% off: {nome}", "Aquele upgrade, {pct}% mais em conta: {nome}"]),
 "Organização e Limpeza": (["Tudo no lugar, do jeitinho que você gosta: {nome} ✨", "{nome}: casa organizada é casa leve", "Achadinho de organização que separei pra você: {nome}", "Pra rotina de limpeza ficar mais simples: {nome}", "Casa em ordem, cabeça leve: {nome}", "Menos bagunça, mais tranquilidade: {nome} 🧺"],
            ["{nome} com {pct}% off: casa em ordem gastando menos ✨", "Organização com {pct}% off: {nome}", "Casa em ordem, {pct}% mais em conta: {nome}"]),
 "Natal e Decoração": (["Pra deixar o seu Natal ainda mais encantador: {nome} 🎄", "{nome}: o detalhe que deixa a casa em clima de festa", "Achadinho de Natal que separei pra você: {nome}", "A magia mora nos detalhes: {nome} ✨", "Decoração que aquece a casa e o coração: {nome}", "Seu cantinho pronto para as festas com {nome}"],
            ["{nome} com {pct}% off pra decorar com encanto 🎄", "Clima de festa com {pct}% off: {nome}", "O detalhe que faltava, {pct}% mais em conta: {nome}"]),
 "Fitness e Esportes": (["Pra cuidar de você com estilo: {nome} ✨", "{nome}: um incentivo a mais pro seu treino", "Achadinho fitness que separei pra você: {nome}", "Seu treino merece esse capricho: {nome}", "Movimento também é autocuidado: {nome}", "Treino com mais estilo começa aqui: {nome} 💪"],
            ["{nome} com {pct}% off: treino com estilo gastando menos", "Rotina fitness com {pct}% off: {nome} 💪", "Incentivo pro treino, {pct}% mais em conta: {nome}"]),
}

def nome_curto(produto, n=6, maximo=38):
    t = re.split(r",\s| [-–|/] | \(| \+ ", str(produto or "").strip())[0].strip(" .:;-")
    p = t.split()[:n]
    while len(p) > 2 and len(" ".join(p)) > maximo: p.pop()
    while len(p) > 2 and p[-1].lower().strip(".,") in {"para", "pra", "com", "de", "do", "da", "dos", "das", "e", "em", "p/", "c/", "no", "na", "ou", "a", "o"}: p.pop()
    t = " ".join(p).rstrip(" .:;,-")
    return t.title() if t.isupper() else t

def chamada_padrao(c, vez=None):
    """Chamada elegante por categoria. `vez` escolhe a variação (rodízio); sem ela, usa o ID da oferta."""
    sem, com = CHAMADAS.get(c.get("C"), CHAMADAS["Casa e Cozinha"])
    if vez is None: vez = int(re.sub(r"\D", "", str(c.get("A"))) or 0)
    pct = 0
    try:
        atual = faixa(c["E"])[0]
        if c.get("F") not in (None, "") and float(c["F"]) > atual: pct = round((1 - atual / float(c["F"])) * 100)
    except (TypeError, ValueError, KeyError): pct = 0
    modelos = com if pct >= 5 else sem
    return modelos[vez % len(modelos)].format(nome=nome_curto(c.get("B")), pct=pct)

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
    # O GitHub chega a atrasar horas: fora da janela, não envia (evita enquete de madrugada e repetida na virada do dia).
    janela = (12, 14) if a.destaque else (20, 22)
    if real and not janela[0] <= datetime.now().hour < janela[1]: print(f"fora da janela {janela[0]}h-{janela[1]}h: não envia"); return
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
    prontas, bloqueadas, aprovadas = [], [], {}
    for row in wb["Ofertas"].iter_rows(min_row=2, max_col=19):
        c = {cell.column_letter: cell.value for cell in row}
        if not c.get("A") and not c.get("B"): continue
        if c.get("L") == "Aprovado": aprovadas.setdefault(c.get("C"), []).append(str(c["A"]))
        if a.oferta and str(c.get("A")) != a.oferta: continue
        if c.get("L") != "Aprovado" or (estado.get(str(c.get("A"))) == hoje and not a.destaque and not a.oferta): continue
        motivo = validar(c, cfg, mapa)
        (bloqueadas if motivo else prontas).append((c, motivo))
    for c, m in bloqueadas: print(f"BLOQUEADA {c.get('A')} - {c.get('B')}: {m}"); log([c.get("A"), "", "bloqueada", m])
    if a.destaque or a.enquete:
        return extras(a, env, cfg, wb, mapa, estado, hoje, prontas)
    ciclo = int(cfg.get("CICLO_DIAS") or 0)
    por_grupo = int(cfg.get("MAX_POR_GRUPO_DIA") or 0)
    if por_grupo and not a.oferta:
        # Modo "melhores do dia": cada grupo recebe até MAX_POR_GRUPO_DIA ofertas, as que pagam mais por venda
        # (preço x % de comissão), sem repetir oferta enviada nos últimos CICLO_DIAS dias.
        hoje_d = datetime.strptime(hoje, "%Y-%m-%d").date()
        def recente(c):
            ult = estado.get(str(c["A"]))
            try: return ult and (hoje_d - datetime.strptime(ult, "%Y-%m-%d").date()).days < max(ciclo, 1)
            except ValueError: return False
        frescas = [(c, m) for c, m in prontas if not recente(c)]
        if frescas: prontas = frescas
        prontas.sort(key=lambda x: (-ganho_estimado(x[0]), estado.get(str(x[0]["A"]), "")))
    elif ciclo > 1 and not a.oferta:
        # A base inteira sai em `ciclo` dias e recomeca. Cada categoria (= grupo) se divide em partes iguais pelos dias,
        # pela ordem do ID entre as aprovadas, entao todo grupo recebe a mesma quantidade por dia.
        # Ciclo de 7 = semana: segunda e o dia 1 (a base e renovada na segunda e o ciclo recomeca).
        dia = datetime.strptime(hoje, "%Y-%m-%d")
        turno = dia.weekday() if ciclo == 7 else dia.toordinal() % ciclo
        num = lambda i: int(re.sub(r"\D", "", i) or 0)
        posicao = {i: k for ids in aprovadas.values() for k, i in enumerate(sorted(ids, key=num))}
        prontas = [(c, m) for c, m in prontas if posicao.get(str(c["A"]), 0) % ciclo == turno]
    if not (por_grupo and not a.oferta):
        prontas.sort(key=lambda x: estado.get(str(x[0]["A"]), ""))  # quem foi enviado há mais tempo vai primeiro
    if por_grupo:
        usados, sel = {}, []
        for c, m in prontas:
            usados[c["C"]] = usados.get(c["C"], 0) + 1
            if usados[c["C"]] <= por_grupo: sel.append((c, m))
        prontas = sel
    prontas = prontas[:limite]
    vez_grupo = {}
    for c, _ in prontas:  # chamada padrão em rodízio: o mesmo grupo não repete a variação em sequência
        k = vez_grupo.get(c["C"], datetime.strptime(hoje, "%Y-%m-%d").toordinal()); vez_grupo[c["C"]] = k + 1
        c["R"] = chamada_padrao(c, k)
    saida = [f"=== {c['A']} | {c['C']} ===\n{mensagem(c, cfg)}\n" for c, _ in prontas]
    if mapa.get("__AVISOS__"): saida.insert(0, "=== BOAS-VINDAS | Avisos ===\n" + (AQUI / "modelo-boasvindas.txt").read_text().strip() + "\n")
    (AQUI / "mensagens-do-dia.txt").write_text("\n".join(saida) or "(nenhuma oferta pronta)\n")
    print(f"{len(prontas)} pronta(s), {len(bloqueadas)} bloqueada(s). Veja mensagens-do-dia.txt")
    if not a.enviar: print("SIMULAÇÃO: nada foi enviado."); return
    if env.get("ENVIO_REAL", "NAO").upper() != "SIM": sys.exit("ENVIO_REAL não está SIM no .env. Nada enviado.")
    if not a.auto and input(f"Enviar {len(prontas)} mensagem(ns) de verdade? Digite CONFIRMO: ").strip() != "CONFIRMO": sys.exit("Cancelado.")
    if a.auto and not a.oferta and not 8 <= datetime.now().hour < 19:
        print("fora da janela 08h-19h: envio automático não sai à noite nem de madrugada"); return
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
