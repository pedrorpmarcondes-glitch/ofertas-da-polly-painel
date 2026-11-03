"""Página Instagram do painel: previa de feed e stories, aprovacao, agenda do feed e biblioteca de stories.

Guarda tudo em dados-painel/instagram-fila.json (repositorio privado). A rotina que publica le esse arquivo.
  feed:    {"P231": {"status": "aprovado"|"rejeitado", "agendado_para": "2026-11-03T10:30", "por": "...", "postado_em": null}}
  stories: {"P231": {"ativo": true, "horarios": ["09:00", "19:00"], "por": "..."}}   # repete todo dia ate desmarcar
"""
import base64, hashlib, json, re
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import importlib
import random

import pandas as pd
import streamlit as st

import dados as d
import arte_instagram as arte

ARQ = "dados-painel/instagram-fila.json"
FUSO = ZoneInfo("America/Sao_Paulo")
PERFIL = "ofertasdapolly_"

CSS = """
<style>
.ig{background:#000;color:#fff;border-radius:18px;overflow:hidden;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;border:1px solid #2a2a2a}
.ig .top{display:flex;align-items:center;gap:10px;padding:10px 12px}
.ig .av{width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#ff2d8f,#ffc2e0);padding:2px;flex:none}
.ig .av i{display:block;width:100%;height:100%;border-radius:50%;background:#111;border:2px solid #000}
.ig .nm{font-weight:600;font-size:13px;line-height:1.1}.ig .nm small{display:block;font-weight:400;color:#a8a8a8;font-size:11px}
.ig img.arte{display:block;width:100%}
.ig .acoes{display:flex;gap:14px;padding:10px 12px 4px}.ig .acoes svg{width:24px;height:24px;stroke:#fff;fill:none;stroke-width:1.7}
.ig .acoes .sv{margin-left:auto}
.ig .cap{padding:2px 12px 12px;font-size:13px;line-height:1.35;max-height:5.4em;overflow:hidden;color:#f5f5f5}
.ig .cap b{font-weight:600}.ig .cap .mais{color:#a8a8a8}
.st{position:relative;width:100%;aspect-ratio:9/16;background:#000;border-radius:18px;overflow:hidden;border:1px solid #2a2a2a;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif}
.st img.arte{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.st .barra{position:absolute;top:10px;left:10px;right:10px;height:3px;background:rgba(255,255,255,.35);border-radius:3px;z-index:3}
.st .barra i{display:block;height:100%;width:38%;background:#fff;border-radius:3px}
.st .id{position:absolute;top:22px;left:12px;display:flex;align-items:center;gap:8px;color:#fff;font-size:12px;font-weight:600;z-index:3;text-shadow:0 1px 3px #000}
.st .id .av{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,#ff2d8f,#ffc2e0);padding:2px}.st .id .av i{display:block;width:100%;height:100%;border-radius:50%;background:#111;border:2px solid #000}
.st .id small{font-weight:400;opacity:.8}
.st .resp{position:absolute;left:12px;right:12px;bottom:16px;height:40px;border:1px solid rgba(255,255,255,.75);border-radius:22px;color:#fff;font-size:13px;display:flex;align-items:center;padding:0 16px;z-index:3;background:rgba(0,0,0,.18)}
.st .seg{position:absolute;left:0;right:0;border-color:rgba(255,45,143,.9);border-style:dashed;border-width:0;z-index:4;background:rgba(255,45,143,.12);color:#fff;font-size:10px;text-align:center}
</style>
"""

SVG = ('<div class="acoes"><svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.6-9.5-9.2C1.2 8.5 3 5 6.5 5c2 0 3.5 1.1 5.5 3 2-1.9 3.5-3 5.5-3C21 5 22.8 8.5 21.5 11.8 19.5 16.4 12 21 12 21z"/></svg>'
       '<svg viewBox="0 0 24 24"><path d="M21 11.5a8.4 8.4 0 0 1-12.2 7.5L3 21l2-5.8A8.4 8.4 0 1 1 21 11.5z"/></svg>'
       '<svg viewBox="0 0 24 24"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></svg>'
       '<svg class="sv" viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V4a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1z"/></svg></div>')


def _b64(jpeg):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


@st.cache_data(ttl=600, show_spinner=False)
def _arte(oid, formato, chave, foto, campos, link):
    return arte.renderizar(dict(campos), foto, formato, mostrar_link=link)


def _campos(c):
    return tuple(sorted((k, str(v) if v is not None else "") for k, v in c.items() if k in ("B", "C", "E", "G", "I", "R")))


def previa_feed(jpeg, legenda):
    corpo = re.sub(r"\s+", " ", legenda)[:140]
    return (f'<div class="ig"><div class="top"><div class="av"><i></i></div><div class="nm">{PERFIL}<small>Ofertas da Polly</small></div></div>'
            f'<img class="arte" src="{_b64(jpeg)}" alt="">{SVG}<div class="cap"><b>{PERFIL}</b> {corpo.replace("<", "&lt;")} <span class="mais">... mais</span></div></div>')


def previa_stories(jpeg, zonas):
    seg = ""
    if zonas:
        topo, base = arte.SEGURO_TOPO / 1920 * 100, arte.SEGURO_BASE / 1920 * 100
        seg = (f'<div class="seg" style="top:0;height:{topo}%;border-bottom-width:2px">o Instagram cobre aqui</div>'
               f'<div class="seg" style="bottom:0;height:{base}%;border-top-width:2px;display:flex;align-items:flex-end;justify-content:center">o Instagram cobre aqui</div>')
    return (f'<div class="st"><img class="arte" src="{_b64(jpeg)}" alt=""><div class="barra"><i></i></div>'
            f'<div class="id"><div class="av"><i></i></div>{PERFIL} <small>agora</small></div>{seg}<div class="resp">Enviar mensagem</div></div>')


# ------------------------------------------------------------------ dados
def ler_fila():
    txt, sha = d.ler(ARQ)
    f = json.loads(txt) if txt else {}
    f.setdefault("feed", {}); f.setdefault("stories", {})
    # O que a rotina ja publicou fica em outro arquivo (so ela escreve nele); aqui so entra na tela.
    pt, _ = d.ler("dados-painel/instagram-publicados.json")
    publ = json.loads(pt) if pt else {}
    f["_publicados"] = publ
    for oid, v in f["feed"].items():
        p = publ.get("feed", {}).get(f"{oid}|{v.get('agendado_para')}")
        if p: v["postado_em"] = p.get("em")
    return f, sha


def salvar_fila(f, sha, msg):
    limpo = {k: v for k, v in f.items() if not k.startswith("_")}
    for v in limpo["feed"].values(): v.pop("postado_em", None)  # vem do arquivo da rotina, nao daqui
    d.gravar(ARQ, json.dumps(limpo, ensure_ascii=False, indent=1).encode(), sha, f"painel: {msg} por {d.EMAIL}")
    st.cache_data.clear()


def horarios_de(txt):
    """'9:00, 19h30' -> ['09:00', '19:30']; None se algum horario for invalido."""
    out = []
    for p in re.split(r"[,;\s]+", txt.strip()):
        if not p: continue
        m = re.fullmatch(r"(\d{1,2})[:hH](\d{2})?", p)
        if not m or int(m.group(1)) > 23 or int(m.group(2) or 0) > 59: return None
        out.append(f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}")
    return sorted(set(out))



def _agendar_por_intervalo(ids, inicio, intervalo, jan_ini, jan_fim):
    """Um post a cada `intervalo`, a partir de `inicio`. Fora da janela diaria (ex.: de madrugada) o post vai para o inicio da janela do dia seguinte."""
    out, t = [], inicio
    for o in ids:
        dia_ini = t.replace(hour=jan_ini.hour, minute=jan_ini.minute, second=0, microsecond=0)
        dia_fim = t.replace(hour=jan_fim.hour, minute=jan_fim.minute, second=0, microsecond=0)
        if t < dia_ini: t = dia_ini
        elif t > dia_fim: t = dia_ini + timedelta(days=1)
        out.append((o, t)); t = t + intervalo
    return out


def _lote(H, ofertas, fila, fsha):
    H.secao("Escolher produtos", "Filtre por categoria, marque os produtos (ou todos) e aplique a mesma configuração neles")
    cats = sorted(ofertas["Categoria"].dropna().unique())
    c1, c2 = st.columns([2, 1])
    cat_sel = c1.multiselect("Categorias", cats, default=cats, key="lt_cat")
    busca = c2.text_input("Buscar no nome", key="lt_busca")
    ja_feed = {o for o, v in fila["feed"].items() if v.get("status") == "aprovado" and not v.get("postado_em")}
    ja_st = {o for o, v in fila["stories"].items() if v.get("ativo")}
    so_novos = st.checkbox("Mostrar só quem ainda não está agendado (feed ou stories)", key="lt_novos")
    f = ofertas[ofertas["Categoria"].isin(cat_sel)]
    if busca.strip(): f = f[f["Produto"].str.contains(busca.strip(), case=False, na=False)]
    if so_novos: f = f[~f["ID"].isin(ja_feed | ja_st)]
    if f.empty:
        with st.container(border=True): H.vazio("search_off", "Nenhum produto neste filtro", "Mude as categorias ou a busca.")
        return
    ver = st.session_state.setdefault("lt_ver", 0)
    b1, b2, _ = st.columns([1, 1, 3])
    if b1.button("Selecionar todos do filtro", width="stretch"): st.session_state["lt_padrao"] = True; st.session_state["lt_ver"] = ver + 1; st.rerun()
    if b2.button("Limpar seleção", width="stretch"): st.session_state["lt_padrao"] = False; st.session_state["lt_ver"] = ver + 1; st.rerun()
    base = pd.DataFrame({"Selecionar": bool(st.session_state.get("lt_padrao", False)), "ID": f["ID"].values, "Produto": f["Produto"].str.slice(0, 70).values,
                         "Categoria": f["Categoria"].values, "Preço": f["Preço"].values,
                         "Feed": ["agendado" if i in ja_feed else "" for i in f["ID"]], "Stories": ["todo dia" if i in ja_st else "" for i in f["ID"]]})
    ed = st.data_editor(base, key=f"lt_ed_{ver}_{len(f)}_{hash(tuple(f['ID']))}", hide_index=True, width="stretch", height=min(440, 42 + 36 * len(base)),
                        disabled=[c for c in base.columns if c != "Selecionar"], column_config={"Selecionar": st.column_config.CheckboxColumn(required=True)})
    ids = ed.loc[ed["Selecionar"], "ID"].tolist()
    st.caption(f"{len(ids)} de {len(base)} produtos selecionados")
    if not ids: return
    st.divider()
    H.secao("Configuração", "Vale para todos os produtos selecionados")
    g1, g2 = st.columns(2, gap="large")
    with g1:
        usar_feed = st.toggle("Agendar no feed (post único)", value=True, key="lt_feed")
        dia0 = st.date_input("Começar no dia", value=(datetime.now(FUSO) + timedelta(days=1)).date(), min_value=date.today(), format="DD/MM/YYYY", key="lt_dia")
        hora0 = st.time_input("Horário do primeiro post", value=time(10, 30), step=900, key="lt_h0")
        i1, i2 = st.columns(2)
        qtd = i1.number_input("Intervalo entre os posts", min_value=1, max_value=999, value=4, step=1, key="lt_int")
        unid = i2.selectbox("Unidade", ["horas", "minutos", "dias"], key="lt_un")
        j1, j2 = st.columns(2)
        jan_ini = j1.time_input("Não postar antes de", value=time(8, 0), step=900, key="lt_j1")
        jan_fim = j2.time_input("Nem depois de", value=time(22, 0), step=900, key="lt_j2")
        ordem = st.radio("Ordem dos posts", ["Como está na lista", "Embaralhar"], horizontal=True, key="lt_ordem")
    with g2:
        usar_st = st.toggle("Stories todos os dias", value=False, key="lt_st")
        modo_st = st.radio("Como postar os stories", ["Rotação aleatória (sem repetir)", "Fixo: todos nos horários marcados"], key="lt_modo_st")
        rot = modo_st.startswith("Rot")
        if rot:
            r1, r2 = st.columns(2)
            por_dia_r = int(r1.number_input("Stories por dia", min_value=1, max_value=100, value=25, step=1, key="lt_pd"))
            ini_r = r2.time_input("Horário do primeiro story", value=time(9, 0), step=900, key="lt_ir")
            int_r = int(st.number_input("Intervalo entre stories (minutos)", min_value=5, max_value=240, value=30, step=5, key="lt_ii"))
            st.caption("Cada dia sorteia produtos que ainda não saíram. Quando todos tiverem saído, recomeça do zero, sem repetir os do dia anterior.")
            slots_s = ["rot"]
        else:
            slots_s = horarios_de(st.text_input("Horários dos stories", "09:00, 19:00", key="lt_hs"))
            st.caption("Todos os produtos selecionados são postados em cada horário, todos os dias, até você desmarcar.")
    link = st.toggle("Mostrar também o link do produto na arte e na legenda (padrão: só “link na bio”)", value=False, key="lt_link")
    intervalo = timedelta(**{{"horas": "hours", "minutos": "minutes", "dias": "days"}[unid]: int(qtd)})
    if usar_feed and jan_ini >= jan_fim: st.error("A janela de horário está invertida: “antes de” precisa ser menor que “depois de”."); return
    if usar_st and not rot and not slots_s: st.error("Horários dos stories inválidos. Use o formato 09:00, 19:00."); return
    if usar_st and rot:
        fim_r = datetime.combine(date.today(), ini_r) + timedelta(minutes=int_r * (min(por_dia_r, len(ids)) - 1))
        if fim_r.date() != date.today(): st.error("Os stories não cabem no dia: diminua a quantidade, o intervalo ou comece mais cedo."); return
    if not (usar_feed or usar_st): st.info("Ligue o feed, os stories ou os dois."); return
    ord_ids = list(ids)
    if ordem == "Embaralhar": random.Random(len(ids) + dia0.toordinal()).shuffle(ord_ids)
    ja_postado = {o for o, v in fila["feed"].items() if v.get("postado_em")}
    feed_ids = [o for o in ord_ids if o not in ja_postado] if usar_feed else []
    agenda = _agendar_por_intervalo(feed_ids, datetime.combine(dia0, hora0), intervalo, jan_ini, jan_fim) if usar_feed else []
    plano = [(o, t.date(), f"{t:%H:%M}") for o, t in agenda]
    por_dia_st = (min(por_dia_r, len(ids)) if rot else len(ids) * len(slots_s)) if usar_st else 0
    st.divider(); H.secao("Resumo antes de aplicar")
    r1, r2 = st.columns(2, gap="large")
    nomes = ofertas.set_index("ID")["Produto"]
    with r1:
        if usar_feed:
            if agenda:
                ult = agenda[-1][1]; dias = (ult.date() - agenda[0][1].date()).days + 1
                st.markdown(f"**Feed:** {len(plano)} posts, de {agenda[0][1]:%d/%m} a **{ult:%d/%m/%Y} às {ult:%H:%M}** ({dias} dias)")
                st.success(f"O último post sai em {ult:%d/%m/%Y} às {ult:%H:%M}.")
            else: st.markdown("**Feed:** nenhum post novo")
            if len(ids) != len(feed_ids): st.caption(f"{len(ids) - len(feed_ids)} já foram postados no feed e ficam de fora.")
            st.dataframe(pd.DataFrame([{"Dia": f"{d_:%d/%m}", "Hora": h_, "Produto": str(nomes.get(o, o))[:60]} for o, d_, h_ in plano[:12]]), hide_index=True, width="stretch")
            if len(plano) > 12: st.caption(f"… e mais {len(plano) - 12} posts")
            por_dia = max((sum(1 for _, t in agenda if t.date() == dd) for dd in {t.date() for _, t in agenda}), default=0)
            if por_dia > 4: st.warning(f"Até {por_dia} posts por dia no feed pode parecer spam e levar a restrição da conta. Aumente o intervalo.")
            if intervalo < timedelta(minutes=60): st.warning("Intervalo menor que 1 hora entre posts do feed não é recomendado.")
    with r2:
        if usar_st:
            if rot:
                dias_ciclo = -(-len(ids) // max(1, min(por_dia_r, len(ids))))
                st.markdown(f"**Stories:** {por_dia_st} por dia, sorteados entre {len(ids)} produtos")
                st.caption(f"Das {ini_r:%H:%M} até {fim_r:%H:%M}, um a cada {int_r} min. O ciclo completo leva cerca de {dias_ciclo} dia(s); depois recomeça do zero.")
                if len(ids) < 2 * por_dia_r: st.warning("Com poucos produtos para a quantidade por dia, alguns aparecem em dias seguidos. Selecione mais produtos ou reduza os stories por dia.")
            else:
                st.markdown(f"**Stories:** {por_dia_st} por dia, todos os dias, até você desmarcar")
                st.caption(f"{len(ids)} stories em cada um dos {len(slots_s)} horário(s) ({', '.join(slots_s)}), um depois do outro.")
            if por_dia_st > 30: st.warning("Mais de 30 stories por dia é muito: o Instagram limita 100 publicações por dia pela API e a audiência cansa.")
    with st.expander("Ver como fica um desses produtos"):
        pid = st.selectbox("Produto", ids, format_func=lambda o: f"{o} · {str(nomes.get(o, o))[:50]}", key="lt_prev")
        wb, _, _, _ = H.contexto(); c = d.dict_da_linha(d.linha_da_oferta(wb, pid)); foto = d.foto(pid); campos = _campos(c)
        chave = hashlib.md5(repr((campos, bool(foto))).encode()).hexdigest()
        p1, p2 = st.columns(2)
        p1.html(previa_feed(_arte(pid, "feed", chave, foto, campos, link), arte.legenda(c, link_produto=link)))
        p2.html(previa_stories(_arte(pid, "stories", chave, foto, campos, link), True))
    conf = st.checkbox(f"Confirmo: {len(plano)} post(s) no feed e {por_dia_st} story(ies) por dia serão publicados sozinhos nos horários marcados", key="lt_conf")
    if st.button("Salvar e publicar no site", type="primary", disabled=not conf, key="lt_go"):
        for o, d_, h_ in plano:
            fila["feed"][o] = {"status": "aprovado", "agendado_para": f"{d_:%Y-%m-%d}T{h_}", "por": d.EMAIL, "postado_em": None, "link_produto": bool(link)}
        if usar_st and rot:
            fila["rotacao"] = {"ativo": True, "produtos": sorted(ord_ids), "por_dia": por_dia_r, "inicio": f"{ini_r:%H:%M}", "intervalo_min": int_r, "link_produto": bool(link), "por": d.EMAIL}
        elif usar_st:
            for i, o in enumerate(ord_ids):
                fila["stories"][o] = {"ativo": True, "horarios": list(slots_s), "por": d.EMAIL, "link_produto": bool(link)}
        salvar_fila(fila, fsha, f"lote: {len(plano)} feed e {len(ord_ids) if usar_st else 0} stories")
        # A caixa ja foi desenhada nesta execucao: o Streamlit nao deixa atribuir valor a ela, so apagar o estado.
        st.session_state.pop("lt_conf", None); st.toast("Lote agendado"); st.rerun()


# ------------------------------------------------------------------ pagina
def pagina(H):
    # arte_instagram.py fica fora da pasta do painel: o Streamlit nao recarrega esse arquivo sozinho quando ele muda
    # (isso causava TypeError logo apos uma atualizacao). Recarregar aqui garante que as duas pecas andem juntas.
    importlib.reload(arte)
    st.html(CSS)
    wb, sha, df, aux = H.contexto()
    H.cabecalho("Instagram", "Veja como o post fica, aprove e agende. Só o que você aprovar vai ao ar.")
    ofertas = df[df["Status"].isin(["Aprovada", "Enviada"])]
    if ofertas.empty:
        with st.container(border=True): H.vazio("image", "Nenhuma oferta aprovada", "Aprove ofertas em “Revisar e enviar” para criar posts.")
        return
    fila, fsha = ler_fila()
    t1, tl, t2, t3 = st.tabs(["Prévia e aprovação", "Em lote (vários produtos)",
                                  f"Agenda do feed ({sum(1 for v in fila['feed'].values() if v.get('status') == 'aprovado' and not v.get('postado_em'))})",
                                  f"Biblioteca de stories ({sum(1 for v in fila['stories'].values() if v.get('ativo')) + (1 if (fila.get('rotacao') or {}).get('ativo') else 0)} ativos)"])
    with t1:
        esc = st.selectbox("Produto", (ofertas["ID"] + " · " + ofertas["Produto"].str.slice(0, 70)).tolist()); oid = esc.split(" · ")[0]
        c = d.dict_da_linha(d.linha_da_oferta(wb, oid)); foto = d.foto(oid); campos = _campos(c)
        chave = hashlib.md5(repr((campos, bool(foto))).encode()).hexdigest()
        if not foto: st.warning("Esta oferta não tem foto: a arte sai sem imagem do produto.")
        link = st.toggle("Mostrar também o link do produto (padrão: só “link na bio”)", value=False, help="O Instagram não deixa o link clicável no feed nem nos stories postados pela rotina: ele aparece escrito, para a pessoa copiar ou digitar. O link clicável é o da bio.")
        feed_jpg = _arte(oid, "feed", chave, foto, campos, link); st_jpg = _arte(oid, "stories", chave, foto, campos, link)
        a, b = st.columns([1, 1], gap="large")
        with a:
            H.secao("Feed (4:5)", "Como aparece no perfil e no feed dos seguidores")
            st.html(previa_feed(feed_jpg, arte.legenda(c, link_produto=link)))
            with st.expander("Legenda completa"): st.text(arte.legenda(c, link_produto=link))
        with b:
            H.secao("Stories (9:16)", "As faixas rosa mostram onde o Instagram cobre a arte")
            zonas = st.toggle("Mostrar faixas de segurança", value=True)
            st.html(previa_stories(st_jpg, zonas))
        st.divider()
        f1, f2 = st.columns(2, gap="large")
        with f1:
            H.secao("Agendar no feed", "Post único, no dia e na hora que você escolher")
            atual = fila["feed"].get(oid, {})
            amanha = datetime.now(FUSO) + timedelta(days=1)
            dia = st.date_input("Dia", value=amanha.date(), min_value=date.today(), format="DD/MM/YYYY", key=f"dia_{oid}")
            hora = st.time_input("Hora", value=time(10, 30), step=900, key=f"hora_{oid}")
            if atual: st.caption(f"Situação atual: {atual.get('status')} · {str(atual.get('agendado_para', ''))[:16].replace('T', ' ')}" + (" · já postado" if atual.get("postado_em") else ""))
            g1, g2 = st.columns(2)
            if g1.button("Aprovar e agendar", type="primary", key=f"ap_{oid}", width="stretch"):
                fila["feed"][oid] = {"status": "aprovado", "agendado_para": f"{dia:%Y-%m-%d}T{hora:%H:%M}", "por": d.EMAIL, "postado_em": None, "link_produto": bool(link)}
                salvar_fila(fila, fsha, f"feed {oid} aprovado para {dia:%d/%m} {hora:%H:%M}"); st.toast("Feed agendado"); st.rerun()
            if g2.button("Rejeitar", key=f"rj_{oid}", width="stretch"):
                fila["feed"][oid] = {"status": "rejeitado", "por": d.EMAIL}; salvar_fila(fila, fsha, f"feed {oid} rejeitado"); st.rerun()
        with f2:
            H.secao("Stories todo dia", "Fica postando sozinho até você desmarcar")
            s = fila["stories"].get(oid, {})
            ativo = st.toggle("Postar este story todos os dias", value=bool(s.get("ativo")), key=f"sa_{oid}")
            txt = st.text_input("Horários (separe por vírgula)", value=", ".join(s.get("horarios", ["09:00"])), key=f"sh_{oid}", help="Ex.: 09:00, 19:30")
            hs = horarios_de(txt)
            if hs is None: st.error("Horário inválido. Use o formato 09:00, 19:30.")
            elif st.button("Salvar stories", type="primary", key=f"ss_{oid}", width="stretch"):
                fila["stories"][oid] = {"ativo": bool(ativo), "horarios": hs, "por": d.EMAIL, "link_produto": bool(link)}
                salvar_fila(fila, fsha, f"stories {oid} {'ativo' if ativo else 'desligado'} {','.join(hs)}"); st.toast("Stories salvos"); st.rerun()
        st.caption("A rotina confere a agenda de 15 em 15 minutos, então o post sai até 15 minutos depois do horário marcado.")
    with tl:
        _lote(H, ofertas, fila, fsha)
    nome = lambda o: ofertas.set_index("ID")["Produto"].get(o, o)
    with t2:
        itens = sorted(((o, v) for o, v in fila["feed"].items() if v.get("status") == "aprovado"), key=lambda x: x[1].get("agendado_para", ""))
        if not itens:
            with st.container(border=True): H.vazio("pending_actions", "Nada agendado", "Aprove um post na aba Prévia para ele entrar aqui.")
        for o, v in itens:
            with st.container(border=True):
                x, y, z = st.columns([5, 2, 1.4], vertical_alignment="center")
                x.markdown(f"**{o}** · {str(nome(o))[:70]}"); y.caption(("Postado em " + str(v["postado_em"])[:16].replace("T", " ")) if v.get("postado_em") else "Agendado: " + v.get("agendado_para", "")[:16].replace("T", " "))
                if not v.get("postado_em") and z.button("Cancelar", key=f"cx_{o}"):
                    del fila["feed"][o]; salvar_fila(fila, fsha, f"feed {o} cancelado"); st.rerun()
    with t3:
        rt = fila.get("rotacao") or {}
        if rt.get("ativo"):
            pl = fila["_publicados"].get("rotacao", {})
            with st.container(border=True):
                x, z = st.columns([6, 1.6], vertical_alignment="center")
                x.markdown(f"**Rotação aleatória:** {rt.get('por_dia')} stories por dia, a partir das {rt.get('inicio')}, a cada {rt.get('intervalo_min')} min · {len(rt.get('produtos', []))} produtos")
                x.caption(f"Ciclo {pl.get('ciclo', 1)} · {len(pl.get('usados', []))} de {len(rt.get('produtos', []))} já saíram neste ciclo. Quando todos saírem, recomeça sozinho.")
                if z.button("Desligar rotação", key="rot_off"):
                    fila["rotacao"]["ativo"] = False; salvar_fila(fila, fsha, "rotacao de stories desligada"); st.rerun()
        itens = sorted((o, v) for o, v in fila["stories"].items() if v.get("ativo"))
        if not itens and not rt.get("ativo"):
            with st.container(border=True): H.vazio("pending_actions", "Nenhum story ativo", "Na aba Prévia, ligue “Postar este story todos os dias” e escolha os horários.")
        for o, v in itens:
            with st.container(border=True):
                x, y, z = st.columns([5, 2, 1.4], vertical_alignment="center")
                x.markdown(f"**{o}** · {str(nome(o))[:70]}"); ult = max((k.split("|")[2] for k in fila["_publicados"].get("stories", {}) if k.startswith(o + "|")), default=None)
                y.caption("Todo dia às " + ", ".join(v.get("horarios", [])) + (f" · último: {ult[8:10]}/{ult[5:7]}" if ult else ""))
                if z.button("Desmarcar", key=f"dm_{o}"):
                    fila["stories"][o]["ativo"] = False; salvar_fila(fila, fsha, f"stories {o} desligado"); st.rerun()
