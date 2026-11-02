"""Página Instagram do painel: previa de feed e stories, aprovacao, agenda do feed e biblioteca de stories.

Guarda tudo em dados-painel/instagram-fila.json (repositorio privado). A rotina que publica le esse arquivo.
  feed:    {"P231": {"status": "aprovado"|"rejeitado", "agendado_para": "2026-11-03T10:30", "por": "...", "postado_em": null}}
  stories: {"P231": {"ativo": true, "horarios": ["09:00", "19:00"], "por": "..."}}   # repete todo dia ate desmarcar
"""
import base64, hashlib, json, re
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

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
    return f, sha


def salvar_fila(f, sha, msg):
    d.gravar(ARQ, json.dumps(f, ensure_ascii=False, indent=1).encode(), sha, f"painel: {msg} por {d.EMAIL}")
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


# ------------------------------------------------------------------ pagina
def pagina(H):
    st.html(CSS)
    wb, sha, df, aux = H.contexto()
    H.cabecalho("Instagram", "Veja como o post fica, aprove e agende. Só o que você aprovar vai ao ar.")
    ofertas = df[df["Status"].isin(["Aprovada", "Enviada"])]
    if ofertas.empty:
        with st.container(border=True): H.vazio("image", "Nenhuma oferta aprovada", "Aprove ofertas em “Revisar e enviar” para criar posts.")
        return
    fila, fsha = ler_fila()
    t1, t2, t3 = st.tabs(["Prévia e aprovação", f"Agenda do feed ({sum(1 for v in fila['feed'].values() if v.get('status') == 'aprovado' and not v.get('postado_em'))})",
                          f"Biblioteca de stories ({sum(1 for v in fila['stories'].values() if v.get('ativo'))} ativos)"])
    with t1:
        esc = st.selectbox("Produto", (ofertas["ID"] + " · " + ofertas["Produto"].str.slice(0, 70)).tolist()); oid = esc.split(" · ")[0]
        c = d.dict_da_linha(d.linha_da_oferta(wb, oid)); foto = d.foto(oid); campos = _campos(c)
        chave = hashlib.md5(repr((campos, bool(foto))).encode()).hexdigest()
        if not foto: st.warning("Esta oferta não tem foto: a arte sai sem imagem do produto.")
        link = st.toggle("Mostrar o link do produto na arte", value=True, help="O Instagram não deixa o link clicável no feed nem nos stories postados pela rotina: ele aparece escrito, para a pessoa copiar ou digitar. O link clicável é o da bio.")
        feed_jpg = _arte(oid, "feed", chave, foto, campos, link); st_jpg = _arte(oid, "stories", chave, foto, campos, link)
        a, b = st.columns([1, 1], gap="large")
        with a:
            H.secao("Feed (4:5)", "Como aparece no perfil e no feed dos seguidores")
            st.html(previa_feed(feed_jpg, arte.legenda(c)))
            with st.expander("Legenda completa"): st.text(arte.legenda(c))
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
                fila["feed"][oid] = {"status": "aprovado", "agendado_para": f"{dia:%Y-%m-%d}T{hora:%H:%M}", "por": d.EMAIL, "postado_em": None}
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
                fila["stories"][oid] = {"ativo": bool(ativo), "horarios": hs, "por": d.EMAIL}
                salvar_fila(fila, fsha, f"stories {oid} {'ativo' if ativo else 'desligado'} {','.join(hs)}"); st.toast("Stories salvos"); st.rerun()
        st.caption("A rotina confere a agenda de 15 em 15 minutos, então o post sai até 15 minutos depois do horário marcado.")
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
        itens = sorted((o, v) for o, v in fila["stories"].items() if v.get("ativo"))
        if not itens:
            with st.container(border=True): H.vazio("pending_actions", "Nenhum story ativo", "Na aba Prévia, ligue “Postar este story todos os dias” e escolha os horários.")
        for o, v in itens:
            with st.container(border=True):
                x, y, z = st.columns([5, 2, 1.4], vertical_alignment="center")
                x.markdown(f"**{o}** · {str(nome(o))[:70]}"); y.caption("Todo dia às " + ", ".join(v.get("horarios", [])))
                if z.button("Desmarcar", key=f"dm_{o}"):
                    fila["stories"][o]["ativo"] = False; salvar_fila(fila, fsha, f"stories {o} desligado"); st.rerun()
