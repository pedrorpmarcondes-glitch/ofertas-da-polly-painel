"""Painel administrativo da Ofertas da Polly (Streamlit).

A planilha continua sendo o banco e a automação segue igual. Oferta cadastrada ou editada aqui nunca é enviada
sozinha: só vai para o WhatsApp depois da aprovação explícita. Só mostra números que existem nas fontes atuais.
"""
import hashlib
import html
import json
import re
from datetime import datetime, date, timedelta
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import dados as d
from dados import eo

st.set_page_config(page_title="Ofertas da Polly", page_icon=":material/shopping_bag:", layout="wide", initial_sidebar_state="auto")

ICONES = {
    "sell": '<path d="M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.6-6.6a2.4 2.4 0 0 0 0-3.4z"/><circle cx="7.5" cy="7.5" r=".6"/>',
    "pending_actions": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "send": '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
    "forum": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "group": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
    "payments": '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
    "storefront": '<path d="M3 9l1.5-5h15L21 9"/><path d="M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/><path d="M5 12v8h14v-8"/><path d="M10 20v-4h4v4"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "search_off": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "warning": '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3z"/><path d="M12 9v4M12 17h.01"/>',
    "error": '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
    "bar_chart": '<path d="M3 3v18h18"/><path d="M8 17v-5M13 17V8M18 17v-3"/>',
    "receipt_long": '<path d="M5 2v20l3-2 2 2 2-2 2 2 2-2 3 2V2l-3 2-2-2-2 2-2-2-2 2z"/><path d="M9 9h6M9 13h6"/>',
    "task_alt": '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    "outbox": '<path d="M12 15V3M8 7l4-4 4 4"/><path d="M4 14v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/>',
    "shopping_cart": '<circle cx="9" cy="20" r="1.2"/><circle cx="18" cy="20" r="1.2"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.6L21 7H6"/>',
    "lock": '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "campaign": '<path d="m3 11 18-6v14L3 13z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    "ads_click": '<path d="m4 4 7 17 2.5-7.5L21 11z"/>',
    "shopping_bag": '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>',
    "insights": '<path d="M22 7 13.5 15.5l-5-5L2 17"/><path d="M16 7h6v6"/>',
    "account_circle": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3"/><path d="M6.2 18.5a7 7 0 0 1 11.6 0"/>',
    "table_chart": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
    "cloud_sync": '<path d="M17.5 19a4.5 4.5 0 0 0 0-9h-1.3A7 7 0 1 0 4 16.3"/><path d="M12 12v7M9 16l3 3 3-3"/>',
    "chat": '<path d="M21 11.5a8.4 8.4 0 0 1-12.2 7.5L3 21l2-5.8A8.4 8.4 0 1 1 21 11.5z"/>',
    "smartphone": '<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M11 18h2"/>',
    "dash": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "plus": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "check": '<rect x="5" y="4" width="14" height="18" rx="2"/><path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1"/><path d="m9 13 2 2 4-4"/>',
    "gear": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "plug": '<path d="M9 2v6M15 2v6"/><path d="M6 8h12v4a6 6 0 0 1-12 0z"/><path d="M12 18v4"/>',
}
NAV_ICONES = ["dash", "sell", "plus", "check", "forum", "group", "insights", "plug", "gear"]


def css_menu():
    """Ícones do menu lateral: o st.page_link só aceita fonte de ícones, então entram por CSS."""
    linhas = []
    for i, nome in enumerate(NAV_ICONES):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONES[nome]}</svg>'
        u = quote(svg)
        linhas.append(f'[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]>[data-testid="stElementContainer"]:nth-child({i + 2}) a::before{{-webkit-mask:url("data:image/svg+xml,{u}") center/contain no-repeat;mask:url("data:image/svg+xml,{u}") center/contain no-repeat}}')
    return "<style>" + "".join(linhas) + "</style>"


COL_LINHA = "minmax(0,2.3fr) minmax(0,1.05fr) minmax(0,.85fr) minmax(0,1.3fr) minmax(0,.62fr) minmax(0,.62fr) minmax(0,1.05fr)"
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{--fundo:#FFFFFF;--sup:#FFFFFF;--sup2:#F5F3FA;--borda:#E6E2F0;--texto:#1F2937;--suave:#667085;--roxo:#7C3AED;--roxo-claro:#6D28D9;--roxo-fundo:#F1ECFB;--verde:#15803D;--ambar:#B45309;--vermelho:#DC2626;--laranja:#C2410C;--linha:#F0EDF7}
.stApp, .stApp p, .stApp label, .stApp button, .stApp input, .stApp textarea, .stApp div{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif}
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"]{font-family:'Material Symbols Rounded'!important}
.mi{width:20px;height:20px;flex:none;display:inline-block;vertical-align:middle;background:currentColor}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]::before{content:"";flex:none;width:20px;height:20px;margin-right:.75rem;background:currentColor;opacity:.85}
.stApp{background:var(--fundo);color:var(--texto)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stToolbarActions"]{display:none!important}
.block-container{padding:2.1rem 2.2rem 4rem;max-width:1260px}
h1{font-size:1.5rem!important;font-weight:700!important;letter-spacing:-.02em;padding:0!important;margin:0!important}
h2,h3,h4{letter-spacing:-.01em;font-weight:600!important;padding:0!important}
/* barra lateral */
[data-testid="stSidebar"]{--sup:#14121B;--sup2:#1B1724;--borda:#272232;--texto:#ECE9F5;--suave:#A29DB3;--roxo:#8B5CF6;--roxo-claro:#C4B5FD;--roxo-fundo:#231B3A;background:#0F0D15;border-right:1px solid var(--borda)}
[data-testid="stSidebar"][aria-expanded="true"]{min-width:288px!important;max-width:288px!important}
[data-testid="stSidebarHeader"]{padding:.6rem .8rem 0;height:auto}
[data-testid="stSidebarUserContent"]{padding:0 1rem 1rem}
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]{gap:.45rem;min-height:calc(100vh - 4.6rem)}
[data-testid="stSidebarUserContent"] [data-testid="stElementContainer"]:last-child{margin-top:auto}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]{border-radius:9px;padding:.68rem .75rem;color:var(--suave);border-left:3px solid transparent;margin:0}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p{white-space:nowrap;font-size:.93rem;font-weight:500;overflow:visible}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]>span{overflow:visible;max-width:none}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover{background:var(--sup);color:var(--texto)}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"]{background:var(--roxo-fundo);border-left-color:var(--roxo);color:var(--texto)}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p{color:var(--texto);font-weight:600}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] [data-testid="stIconMaterial"]{color:var(--roxo-claro)}
.marca{display:flex;align-items:center;gap:.65rem;padding:.2rem .3rem 1.4rem}
.marca .logo{color:var(--roxo-claro);display:flex}.marca .logo .mi{width:26px;height:26px}
.marca b{display:block;font-size:1.05rem;line-height:1.15;color:var(--texto)}.marca span.t{font-size:.72rem;color:var(--suave)}
.perfil{border-top:1px solid var(--borda);padding:.7rem .3rem 0;font-size:.74rem;color:var(--suave);display:flex;gap:.5rem;align-items:center;overflow-wrap:anywhere}
.perfil b{display:block;color:var(--texto);font-weight:500;font-size:.78rem}
/* blocos */
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--sup);border:1px solid var(--borda)!important;border-radius:12px;box-shadow:0 1px 2px rgba(31,24,64,.04)}
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"]{background:transparent;border:none!important}
.sub{color:var(--suave);margin:.15rem 0 0;font-size:.9rem}
.tit-sec{font-size:.95rem;font-weight:600;color:var(--texto);margin:0 0 .15rem}.tit-sec small{display:block;color:var(--suave);font-weight:400;font-size:.8rem;margin-top:.1rem}
.faixa{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));background:var(--sup);border:1px solid var(--borda);border-radius:12px}
.faixa.tres{grid-template-columns:repeat(3,minmax(0,1fr))}
.cel{display:flex;align-items:center;gap:.7rem;padding:.85rem 1rem;border-right:1px solid var(--borda);min-width:0}
.cel:last-child{border-right:none}
.cel .ic{flex:none;color:var(--suave);display:flex}
.cel .ic .mi{width:22px;height:22px}
.cel .v{font-size:1.4rem;font-weight:700;line-height:1.1;color:var(--texto);white-space:nowrap}
.cel .r{font-size:.74rem;line-height:1.2;color:var(--suave)}
.cel.dest{background:linear-gradient(0deg,var(--roxo-fundo),var(--roxo-fundo));border-radius:11px 0 0 11px}
.badge{display:inline-flex;align-items:center;gap:.3rem;padding:.14rem .55rem;border-radius:999px;font-size:.72rem;font-weight:600;white-space:nowrap}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.vazio{display:flex;gap:.8rem;align-items:flex-start;padding:.9rem .2rem;color:var(--suave);font-size:.86rem;line-height:1.45}
.vazio .mi{color:var(--suave);width:22px;height:22px;margin-top:.1rem}.vazio b{display:block;color:var(--texto);font-size:.9rem;margin-bottom:.1rem}
.zap{background:#E7F8EE;border:1px solid #CDEBD8;border-radius:12px 12px 12px 3px;padding:.85rem 1rem;font-size:.9rem;line-height:1.5;color:#14301F;overflow-wrap:anywhere}
.alerta{display:flex;gap:.55rem;align-items:center;background:var(--sup);border:1px solid var(--borda);border-left:3px solid var(--ambar);border-radius:8px;padding:.5rem .8rem;margin-bottom:.4rem;font-size:.86rem}
.alerta.erro{border-left-color:var(--vermelho)}.alerta .mi{width:18px;height:18px;color:var(--ambar)}.alerta.erro .mi{color:var(--vermelho)}
/* linhas de tabela */
.th,.tr{display:grid;grid-template-columns:GRID;gap:.8rem;align-items:center;padding:.5rem .7rem;font-size:.84rem}
.th{color:var(--suave);font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--borda);padding-top:.2rem}
.tr{border-bottom:1px solid var(--linha);border-radius:6px}.tr:hover{background:var(--sup2)}
.tr .p{display:flex;align-items:center;gap:.6rem;min-width:0}
.tr .p img,.tr .p .sem{flex:none;width:36px;height:36px;border-radius:7px;object-fit:cover;background:var(--sup2)}
.tr .p .sem{display:flex;align-items:center;justify-content:center;color:var(--suave)}
.tr .n{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;color:var(--texto)}
.tr small{display:block;color:var(--suave);font-size:.72rem;font-weight:400}
.tr .c{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--suave)}.tr .pr{font-weight:600;color:var(--texto);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-testid="stHorizontalBlock"]:has(.tr){gap:0!important;flex-wrap:nowrap!important;align-items:center}
[data-testid="stHorizontalBlock"]:has(.tr) [data-testid="stColumn"]{min-width:0!important}
[data-testid="stHorizontalBlock"]:has(.tr):hover .tr{background:var(--sup2)}
[data-testid="stHorizontalBlock"]:has(.tr) button{border:none;background:transparent;color:var(--suave);padding:.2rem;min-height:30px}
[data-testid="stHorizontalBlock"]:has(.tr) button:hover{color:var(--roxo-claro);background:var(--roxo-fundo)}
.st-key-tabela_of{gap:0!important}.st-key-tabela_of [data-testid="stColumn"]>div{gap:0}
/* cartões de oferta */
.of{display:flex;flex-direction:column;gap:.35rem}
.of .capa{position:relative;height:170px;border-radius:9px;overflow:hidden;background:#fff}
.of .capa.sem{background:var(--sup2);display:flex;align-items:center;justify-content:center;color:var(--suave)}
.of .capa img{width:100%;height:100%;object-fit:contain;display:block}
.of .capa{border:1px solid var(--linha)}
.of .capa .badge{position:absolute;left:.5rem;top:.5rem;box-shadow:0 0 0 2px #fff}
.of b{font-size:.86rem;font-weight:600;line-height:1.3;height:2.6em;overflow:hidden;color:var(--texto)}
.of small{color:var(--suave);font-size:.74rem}.of .pr{font-weight:700;font-size:1rem;color:var(--texto)}
/* grupos */
.g{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1.5fr) .6fr .6fr .8fr;gap:.8rem;align-items:center;padding:.6rem .7rem;border-bottom:1px solid var(--linha);font-size:.86rem}
.g.h{color:var(--suave);font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid var(--borda)}
.g:last-child{border-bottom:none}.g b{font-weight:600}.g small{display:block;color:var(--suave);font-size:.72rem}
.barra{display:flex;align-items:center;gap:.5rem}.barra i{display:block;height:6px;border-radius:3px;background:var(--roxo);min-width:2px}.barra span{font-weight:600}
.int{display:flex;justify-content:space-between;align-items:center;gap:.8rem;padding:.6rem .2rem;border-bottom:1px solid var(--linha);font-size:.86rem}
.int:last-child{border-bottom:none}.int small{display:block;color:var(--suave);font-size:.76rem}.int>div{min-width:0}
.chip{display:inline-flex;align-items:center;gap:.35rem;background:var(--roxo-fundo);color:var(--roxo-claro);border-radius:7px;padding:.25rem .6rem;font-size:.8rem;font-weight:600}.chip .mi{width:15px;height:15px}
.ic-lista{color:var(--suave);display:flex}
.err-campo{color:var(--vermelho);font-size:.78rem;margin-top:-.4rem}
/* controles */
button:focus-visible,a:focus-visible,[role="radio"]:focus-visible{outline:2px solid var(--roxo-claro)!important;outline-offset:2px}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{background:#fff!important;border-color:var(--borda)!important;border-radius:8px!important}
[data-baseweb="base-input"],[data-baseweb="input"] input,[data-baseweb="textarea"] textarea{background:#fff!important}
[data-baseweb="input"]:focus-within,[data-baseweb="textarea"]:focus-within,[data-baseweb="select"]>div:focus-within{border-color:var(--roxo)!important;box-shadow:0 0 0 1px var(--roxo)}
[data-testid="stBaseButton-primary"]{background:var(--roxo);border-color:var(--roxo);color:#fff;font-weight:600;border-radius:8px}
[data-testid="stBaseButton-primary"]:hover{background:#6D28D9;border-color:#6D28D9}
[data-testid="stBaseButton-secondary"]{border-color:var(--borda);background:#fff;border-radius:8px}
[data-testid="stBaseButton-secondary"]:hover{border-color:var(--roxo);color:var(--roxo-claro)}
[data-testid="stExpander"] details{border-color:var(--borda);border-radius:10px;background:var(--sup)}
[data-testid="stFileUploaderDropzone"]{background:var(--sup2);border:1px dashed var(--borda)}
[data-testid="stTabs"] [data-baseweb="tab-border"]{background:var(--borda)}
@media (max-width:900px){.faixa{grid-template-columns:repeat(2,minmax(0,1fr))}.faixa.tres{grid-template-columns:repeat(3,minmax(0,1fr))}.cel{border-bottom:1px solid var(--borda)}.cel:nth-child(2n){border-right:none}.faixa.tres .cel{border-bottom:none;border-right:1px solid var(--borda)}.faixa.tres .cel:last-child{border-right:none}}
@media (max-width:640px){.block-container{padding:3.4rem 1rem 3rem}.th{display:none}
.tr{grid-template-columns:minmax(0,1fr) auto!important;row-gap:.2rem}.tr .cc,.tr .cl,.tr .cd{display:none}
.g{grid-template-columns:minmax(0,1fr) auto}.g .sm,.g.h{display:none}.faixa.tres{grid-template-columns:1fr}.faixa.tres .cel{border-right:none;border-bottom:1px solid var(--borda)}.faixa.tres .cel:last-child{border-bottom:none}.cel{padding:.7rem .75rem}.cel .v{font-size:1.2rem}}
</style>
""".replace("GRID", COL_LINHA)
st.markdown(CSS + css_menu(), unsafe_allow_html=True)

CORES = {"Rascunho": ("#EEF0F4", "#475467"), "Aguardando aprovação": ("#FEF3DC", "#92600A"), "Aprovada": ("#EDE7FB", "#5B35B0"),
         "Enviada": ("#E1F5E8", "#17653A"), "Erro": ("#FDE6E6", "#B42318"), "Expirada": ("#FFE9D9", "#B54708"), "Removida": ("#F2F4F7", "#667085")}
DIAS = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
ROXO = "#7C3AED"
TZ = ZoneInfo("America/Sao_Paulo")

# ------------------------------------------------------------------ acesso
# ------------------------------------------------------------------ componentes
def h(t): return html.escape(str(t if t is not None else ""))


def mi(nome):
    """Ícone de traço como máscara CSS: o st.html remove <svg>, mas mantém estilo em <span>."""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{ICONES.get(nome, "")}</svg>'
    u = quote(svg, safe="")
    return f"""<span class="mi" style="-webkit-mask:url('data:image/svg+xml,{u}') center/contain no-repeat;mask:url('data:image/svg+xml,{u}') center/contain no-repeat"></span>"""


def badge(s):
    bg, fg = CORES.get(s, ("#EEF0F4", "#475467"))
    return f'<span class="badge" style="background:{bg};color:{fg}">{h(s)}</span>'


def cabecalho(titulo, sub, botao=None):
    """Título, descrição e, se houver, a ação principal da página à direita."""
    if botao:
        a, b = st.columns([4, 1.25], vertical_alignment="center")
        a.html(f'<h1>{h(titulo)}</h1><p class="sub">{h(sub)}</p>')
        if b.button(botao[0], type="primary", width="stretch"): ir(botao[1], alvo=None)
    else:
        st.html(f'<h1>{h(titulo)}</h1><p class="sub">{h(sub)}</p>')


def faixa(celulas, classe=""):
    """celulas: (ícone, cor, valor, rótulo)."""
    corpo = "".join(f'<div class="cel"><div class="ic {cor}">{mi(ic)}</div><div style="min-width:0"><div class="v">{h(v)}</div><div class="r" title="{h(r)}">{h(r)}</div></div></div>' for ic, cor, v, r in celulas)
    st.html(f'<div class="faixa {classe}">{corpo}</div>')


def vazio(icone, titulo, texto):
    st.html(f'<div class="vazio">{mi(icone)}<div><b>{h(titulo)}</b>{h(texto)}</div></div>')


def alerta(texto, tipo=""):
    st.html(f'<div class="alerta {tipo}">{mi("error" if tipo else "warning")}<span>{h(texto)}</span></div>')


def balao(texto):
    st.html(f'<div class="zap">{h(texto).replace(chr(10), "<br>")}</div>')


def secao(titulo, sub=""):
    st.html(f'<div class="tit-sec">{h(titulo)}' + (f"<small>{h(sub)}</small>" if sub else "") + "</div>")


def barras(df, x, y, cor=None, titulo_x="", titulo_y="", horizontal=False, altura=230):
    """Gráfico de barras no padrão do painel (eixos nomeados, sem fundo)."""
    if horizontal:
        enc = {"y": alt.Y(f"{x}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=170)), "x": alt.X(f"{y}:Q", title=titulo_y, axis=alt.Axis(tickMinStep=1))}
    else:
        enc = {"x": alt.X(f"{x}:N", sort=None, title=titulo_x, axis=alt.Axis(labelAngle=0)), "y": alt.Y(f"{y}:Q", title=titulo_y, stack="zero", axis=alt.Axis(tickMinStep=1))}
    if cor: enc["color"] = alt.Color(f"{cor}:N", title=None, scale=alt.Scale(range=[ROXO, "#F59E0B", "#22C55E", "#3B82F6"]), legend=alt.Legend(orient="top", labelColor="#667085"))
    else: enc["color"] = alt.value(ROXO)
    marca = {"size": 14} if horizontal else {}
    ch = alt.Chart(df).mark_bar(cornerRadiusEnd=3, **marca).encode(**enc, tooltip=list(df.columns)).properties(height=altura, background="transparent")
    ch = ch.configure_view(strokeWidth=0).configure_axis(labelColor="#667085", titleColor="#667085", gridColor="#F0EDF7", domainColor="#E6E2F0", tickColor="#E6E2F0", labelFontSize=11, titleFontSize=11)
    st.altair_chart(ch, use_container_width=True, theme=None)


def ir(pagina, **estado):
    for k, v in estado.items(): st.session_state[k] = v
    st.switch_page(pagina)


def contexto():
    d.atualizar_local()
    wb, sha = d.carregar(); return wb, sha, d.tabela(wb), d.auxiliares()


def nome_grupo(k): return "Comunidade (Avisos)" if k == "__AVISOS__" else k


def data_curta(iso):
    return f"{str(iso)[8:10]}/{str(iso)[5:7]}" if iso else "—"


def mudar_situacao(wb, sha, oid, novo):
    d.linha_da_oferta(wb, oid)[11].value = novo
    d.salvar(wb, sha, f"painel: {oid} {novo} por {d.EMAIL}")


def data_br(iso):
    try: return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError: return ""


def thumb(oid):
    u = d.foto_mini(oid)
    return f'<img src="{u}" alt="">' if u else f'<span class="sem">{mi("image")}</span>'


def linha_oferta(o):
    return (f'<div class="tr"><div class="p">{thumb(o["ID"])}<div style="min-width:0"><div class="n" title="{h(o["Produto"])}">{h(o["Produto"])}</div><small>{h(o["ID"])}</small></div></div>'
            f'<div class="c cc">{h(o["Categoria"])}</div><div class="c cl">{h(o["Loja"])}</div><div class="pr" title="{h(o["Preço"])}">{h(o["Preço"])}</div><div class="c cd">{data_curta(o["Enviada em"])}</div><div class="c cd">{data_curta(o["Próximo envio"])}</div><div>{badge(o["Status"])}</div></div>')


CAB_OFERTAS = '<div class="th"><div>Produto</div><div>Categoria</div><div>Loja</div><div>Preço</div><div>Último</div><div>Próximo</div><div>Status</div></div>'


# ------------------------------------------------------------------ visão geral
def resumo_comissoes(v):
    por = v.groupby("loja")["comissao"].sum() if len(v) else {}
    faixa([("payments", "verde", eo.brl(v["comissao"].sum()) if len(v) else "—", "Comissão total"),
           ("storefront", "", eo.brl(por["Shopee"]) if "Shopee" in por else "—", "Shopee"),
           ("storefront", "ambar", eo.brl(por["Mercado Livre"]) if "Mercado Livre" in por else "—", "Mercado Livre")], "tres")


def secao_financeiro(df):
    a, b, c = st.columns([1.3, 2.4, 1.2], vertical_alignment="center")
    with a: secao("Financeiro")
    v = d.vendas_df(); hoje = datetime.now(TZ).date()
    periodo = b.radio("Período das comissões", ["Este mês", "Últimos 30 dias", "Tudo"], horizontal=True, label_visibility="collapsed")
    with c.popover("Registrar comissão", width="stretch"):
        st.caption("Copie os números do painel de afiliados de cada loja.")
        with st.form("form_comissao", clear_on_submit=True):
            dia = st.date_input("Data", value=hoje, format="DD/MM/YYYY", max_value=hoje)
            loja = st.selectbox("Loja", ["Shopee", "Mercado Livre"])
            x, y = st.columns(2)
            cli = x.number_input("Cliques", min_value=0, step=1); ped = y.number_input("Pedidos", min_value=0, step=1)
            com = st.number_input("Comissão (R$)", min_value=0.0, step=0.01, format="%.2f")
            prod = st.selectbox("Produto (opcional)", (df["ID"] + " · " + df["Produto"].str.slice(0, 45)).tolist(), index=None, placeholder="Comissão geral da loja")
            if st.form_submit_button("Salvar", type="primary", width="stretch"):
                try: d.registrar_venda(dia, loja, cli, ped, com, prod.split(" · ")[0] if prod else ""); st.toast("Comissão registrada"); st.rerun()
                except Exception as e: st.error(f"Não foi possível salvar: {e}")
    if len(v):
        if periodo == "Este mês": v = v[v["data"].dt.date >= hoje.replace(day=1)]
        elif periodo == "Últimos 30 dias": v = v[v["data"].dt.date >= hoje - timedelta(days=30)]
    resumo_comissoes(v)
    if len(v):
        g = v.groupby([v["data"].dt.strftime("%d/%m"), "loja"])["comissao"].sum().reset_index()
        g.columns = ["Dia", "Loja", "Comissão"]
        with st.container(border=True):
            secao("Comissão por dia"); barras(g, "Dia", "Comissão", "Loja", titulo_y="R$", altura=190)
        p = v[v["produto_id"].notna() & (v["produto_id"].astype(str).str.strip() != "")] if "produto_id" in v else v.iloc[0:0]
        if len(p):
            nomes = dict(zip(df["ID"], df["Produto"])); t = p.groupby(["produto_id", "loja"])["comissao"].sum().reset_index().sort_values("comissao", ascending=False).head(10)
            with st.container(border=True):
                secao("Comissão por produto")
                st.html("".join(f'<div class="int"><div><b style="font-weight:600">{h(str(nomes.get(x.produto_id, x.produto_id))[:70])}</b><small>{h(x.produto_id)} · {h(x.loja)}</small></div><b>{eo.brl(x.comissao)}</b></div>' for x in t.itertuples()))


def pg_visao():
    wb, sha, df, aux = contexto(); agora = datetime.now(TZ); mapa, metr = aux["grupos"], aux["metricas"]
    saud = "Bom dia" if agora.hour < 12 else "Boa tarde" if agora.hour < 18 else "Boa noite"
    cabecalho(saud, f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]} de {agora.year}", ("Cadastrar oferta", PG_CAD))
    hoje = agora.date().isoformat()
    ativas = int(df["Status"].isin(["Aprovada", "Enviada"]).sum()); aguard = int((df["Status"] == "Aguardando aprovação").sum())
    env_hoje = sum(1 for k, v in aux["enviados"].items() if v == hoje and k.startswith("P"))
    grupos = [k for k in mapa if not k.startswith("__")]
    membros = sum(v.get("membros", 0) for k, v in metr["grupos"].items() if not k.startswith("__")) if metr else "—"
    faixa([("sell", "", ativas, "Ofertas ativas"), ("pending_actions", "ambar", aguard, "Aguardando revisão"), ("send", "verde", env_hoje, "Enviadas hoje"),
           ("forum", "azul", len(grupos), "Grupos ativos"), ("group", "rosa", membros, "Membros nos grupos")])
    exp = int((df["Status"] == "Expirada").sum()); err = int((df["Status"] == "Erro").sum()); cfg = d.config(wb); inc = 0
    for r in wb["Ofertas"].iter_rows(min_row=2, max_col=18):
        c = d.dict_da_linha(r)
        if c.get("A") and c.get("L") == "Aprovado" and eo.validar(c, cfg, mapa): inc += 1
    if err: alerta(f"{err} oferta(s) com falha no último envio. Veja em Revisar e enviar.", "erro")
    if exp: alerta(f"{exp} oferta(s) expirada(s). Revise a validade ou remova.")
    if inc: alerta(f"{inc} oferta(s) aprovada(s) com informação incompleta; não serão enviadas.")
    if not metr: alerta("A contagem de membros ainda não foi coletada.")
    elif any(v.get("erro") for v in metr["grupos"].values()): alerta("Falha ao ler algum grupo no WhatsApp. Veja em Dados e integrações.", "erro")
    secao_financeiro(df)
    esq, dir_ = st.columns([3, 2])
    with esq.container(border=True):
        a, b = st.columns([1, 1.5], vertical_alignment="center")
        with a: secao("Mensagens enviadas", "Por dia e por loja")
        dias = b.radio("Período do gráfico", ["7 dias", "14 dias", "30 dias"], horizontal=True, label_visibility="collapsed")
        n = int(dias.split()[0]); ini = agora.date() - timedelta(days=n - 1); loja = dict(zip(df["ID"], df["Loja"]))
        linhas = [(l[0][:10], loja.get(l[1], "Outra")) for l in d.log_linhas() if l[3] == "enviada" and l[1].startswith("P") and l[0][:10] >= ini.isoformat()]
        if linhas:
            t = pd.DataFrame(linhas, columns=["d", "Loja"]).value_counts().rename("Mensagens").reset_index()
            eixo = pd.DataFrame({"d": [(ini + timedelta(days=i)).isoformat() for i in range(n)]})
            t = eixo.merge(t, on="d", how="left"); t["Loja"] = t["Loja"].fillna(t["Loja"].dropna().iloc[0]); t["Mensagens"] = t["Mensagens"].fillna(0)
            t["Dia"] = t["d"].str[8:] + "/" + t["d"].str[5:7]
            barras(t[["Dia", "Loja", "Mensagens"]], "Dia", "Mensagens", "Loja", titulo_y="Mensagens", altura=215)
        else: vazio("bar_chart", "Sem envios neste período", "Quando as ofertas saírem, o gráfico aparece aqui.")
    with dir_.container(border=True):
        secao("Vendas por categoria")
        v = d.vendas_df()
        if len(v) and "produto_id" in v and v["produto_id"].notna().any():
            g = v.assign(Categoria=v["produto_id"].map(dict(zip(df["ID"], df["Categoria"])))).groupby("Categoria")["pedidos"].sum().reset_index().rename(columns={"pedidos": "Pedidos"})
            barras(g, "Categoria", "Pedidos", horizontal=True, altura=215, titulo_y="Pedidos")
        else: vazio("receipt_long", "Sem dados de compra por produto", "As lojas não entregam esse dado automaticamente. Importe o relatório de afiliados em dados-painel/vendas.csv, com o ID de cada produto.")
    with st.container(border=True):
        secao("Ofertas recentes")
        st.html(CAB_OFERTAS + "".join(linha_oferta(o) for _, o in df.sort_values("Conferido em", ascending=False, na_position="last").head(6).iterrows()))


# ------------------------------------------------------------------ ofertas
def pg_ofertas():
    wb, sha, df, aux = contexto()
    cabecalho("Ofertas", "Produtos cadastrados, o que está rodando e quando sai cada um.", ("Cadastrar oferta", PG_CAD))
    rodando = df[df["Status"].isin(["Aprovada", "Enviada", "Erro"])]; hoje_iso = date.today().isoformat(); ciclo = int(d.config(wb).get("CICLO_DIAS") or 1)
    faixa([("send", "", len(rodando), "Rodando"), ("pending_actions", "", int((rodando["Próximo envio"] == hoje_iso).sum()), "Saem hoje"),
           ("task_alt", "", int((df["Enviada em"] == hoje_iso).sum()), "Enviadas hoje"), ("inbox", "", int((df["Status"] == "Removida").sum()), "Removidas"),
           ("gear", "", "Todo dia" if ciclo == 1 else f"{ciclo} dias", "Rotação")])
    st.html('<div style="display:flex;flex-wrap:wrap;gap:.4rem">' + "".join(f'<span class="chip">{h(c)}: {n}</span>' for c, n in rodando["Categoria"].value_counts().items()) + "</div>")
    a, b, c, e, f_ = st.columns([2.2, 1.25, 1.1, 1.1, 1.35], vertical_alignment="center")
    busca = a.text_input("Buscar oferta", placeholder="Buscar por produto ou ID", label_visibility="collapsed")
    cat = b.selectbox("Categoria", sorted(df["Categoria"].dropna().unique()), index=None, placeholder="Categoria", label_visibility="collapsed")
    loja = c.selectbox("Loja", sorted(df["Loja"].dropna().unique()), index=None, placeholder="Loja", label_visibility="collapsed")
    stat = e.selectbox("Status", ["Rodando"] + d.STATUS_ORDEM, index=None, placeholder="Status", label_visibility="collapsed")
    with f_.popover("Período", width="stretch"):
        de = st.date_input("Conferida a partir de", value=None, format="DD/MM/YYYY"); ate = st.date_input("Conferida até", value=None, format="DD/MM/YYYY")
    f = df
    if busca: f = f[f["Produto"].str.contains(busca, case=False, na=False, regex=False) | f["ID"].str.contains(busca, case=False, na=False, regex=False)]
    if cat: f = f[f["Categoria"] == cat]
    if loja: f = f[f["Loja"] == loja]
    if stat == "Rodando": f = f[f["Status"].isin(["Aprovada", "Enviada", "Erro"])]
    elif stat: f = f[f["Status"] == stat]
    if de: f = f[f["Conferido em"].apply(lambda x: x is not None and x >= de)]
    if ate: f = f[f["Conferido em"].apply(lambda x: x is not None and x <= ate)]
    chave = hashlib.md5(repr((busca, cat, loja, stat, de, ate)).encode()).hexdigest()
    if st.session_state.get("filtro") != chave: st.session_state["filtro"] = chave; st.session_state["pagina"] = 0
    l, r = st.columns([3, 1.4], vertical_alignment="center")
    l.caption(f"{len(f)} de {len(df)} ofertas")
    modo = r.radio("Visualização", ["Tabela", "Cartões"], horizontal=True, label_visibility="collapsed")
    if f.empty: vazio("search_off", "Nenhuma oferta encontrada", "Tente limpar a busca ou os filtros."); return
    por = 20 if modo == "Tabela" else 12; total = max(1, (len(f) - 1) // por + 1); pag = min(st.session_state.get("pagina", 0), total - 1)
    fatia = f.iloc[pag * por:(pag + 1) * por]
    if modo == "Tabela":
        with st.container(border=True, key="tabela_of"):
            x, _ = st.columns([10, 2]); x.html(CAB_OFERTAS)
            for _, o in fatia.iterrows():
                x, y, z = st.columns([10, 1, 1], vertical_alignment="center")
                x.html(linha_oferta(o))
                if y.button("Abrir", key=f"ab{o['ID']}", help=f"Abrir {o['ID']}"): detalhes(o["ID"], wb)
                if o["Status"] == "Removida":
                    if z.button("Voltar", key=f"vo{o['ID']}", help="Volta para a rotação"): mudar_situacao(wb, sha, o["ID"], "Aprovado"); st.toast(f"{o['ID']} voltou para a rotação"); st.rerun()
                elif z.button("Tirar", key=f"ti{o['ID']}", help="Tira da rotação. Dá para voltar depois"): mudar_situacao(wb, sha, o["ID"], "Removido (painel)"); st.toast(f"{o['ID']} saiu da rotação"); st.rerun()
    else:
        cols = st.columns(4)
        for i, (_, o) in enumerate(fatia.iterrows()):
            with cols[i % 4].container(border=True):
                u = d.foto_mini(o["ID"], 360)
                capa = f'<div class="capa"><img src="{u}" alt="">{badge(o["Status"])}</div>' if u else f'<div class="capa sem">{mi("image")}{badge(o["Status"])}</div>'
                val = f" · até {h(o['Validade'])}" if o["Validade"] else ""
                st.html(f'<div class="of">{capa}<b title="{h(o["Produto"])}">{h(o["Produto"])}</b><small>{h(o["Categoria"])} · {h(o["Loja"])}{val}</small><div class="pr">{h(o["Preço"])}</div></div>')
                p, q = st.columns(2)
                if p.button("Ver", key=f"det{o['ID']}", width="stretch"): detalhes(o["ID"], wb)
                if q.button("Editar", key=f"ed{o['ID']}", width="stretch"): ir(PG_CAD, alvo=("editar", o["ID"]))
    if total > 1:
        a, b, c = st.columns([1, 2, 1], vertical_alignment="center")
        if a.button("Anterior", disabled=pag == 0, width="stretch"): st.session_state["pagina"] = pag - 1; st.rerun()
        b.html(f'<p class="sub" style="text-align:center;margin:0">Página {pag + 1} de {total}</p>')
        if c.button("Próxima", disabled=pag >= total - 1, width="stretch"): st.session_state["pagina"] = pag + 1; st.rerun()


@st.dialog("Detalhes da oferta", width="large")
def detalhes(oid, wb):
    wb_sha = d.ler("ofertas-polly.xlsx", binario=True)[1]
    c = d.dict_da_linha(d.linha_da_oferta(wb, oid)); linha = d.tabela(wb).set_index("ID").loc[oid]; status = linha["Status"]
    st.html(f'<div class="tit-sec" style="font-size:1.05rem">{h(c["B"])}</div><div style="margin-top:.3rem">{badge(status)} <span class="chip">{mi("forum")}{h(c["C"])}</span></div>')
    a, b = st.columns([2, 3], gap="medium")
    with a:
        img = d.foto(oid)
        if img: st.image(img, width="stretch")
        st.html(f'<div class="int"><div><small>Preço atual</small>{h(d.preco_bonito(c["E"]))}</div></div><div class="int"><div><small>Preço anterior</small>{h(d.preco_bonito(c.get("F")) or "—")}</div></div>'
                f'<div class="int"><div><small>Último envio</small>{h(data_br(linha["Enviada em"]) or "—")}</div></div><div class="int"><div><small>Próximo envio</small>{h(data_br(linha["Próximo envio"]) or "—")}</div></div>'
                f'<div class="int"><div><small>Loja</small>{h(c["D"])}</div></div><div class="int"><div><small>Cupom</small>{h(c.get("G") or "—")}</div></div><div class="int"><div><small>Validade</small>{h(c.get("H") or "Indeterminada")}</div></div>')
    with b:
        secao("Mensagem que será enviada"); c2 = dict(c); c2["L"] = "Aprovado"
        try: balao(eo.mensagem(c2, d.config(wb)))
        except Exception: st.caption("Mensagem indisponível: faltam campos.")
    x, y, z = st.columns(3)
    if x.button("Editar", width="stretch"): ir(PG_CAD, alvo=("editar", oid))
    if y.button("Duplicar", width="stretch"): ir(PG_CAD, alvo=("duplicar", oid))
    if status == "Removida":
        if z.button("Voltar para a rotação", width="stretch"): mudar_situacao(wb, wb_sha, oid, "Aprovado"); st.rerun()
    elif z.button("Tirar da rotação", width="stretch"): mudar_situacao(wb, wb_sha, oid, "Removido (painel)"); st.rerun()


# ------------------------------------------------------------------ cadastro
def erro_de(chave):
    m = st.session_state.get("erros_tela", {}).get(chave)
    if m: st.html(f'<div class="err-campo">{h(m)}</div>')


def pg_cadastro():
    wb, sha, df, aux = contexto(); cfg = d.config(wb); mapa = aux["grupos"]
    alvo = st.session_state.get("alvo"); modo, fonte = (alvo if alvo else (None, None))
    salvo = st.session_state.pop("salvo", None); st.session_state["erros_tela"] = st.session_state.pop("erros", {})
    cabecalho({"editar": f"Editar oferta {fonte}", "duplicar": f"Duplicar oferta {fonte}"}.get(modo, "Cadastrar oferta"), "Nada é enviado daqui. Campos com * são obrigatórios.")
    if salvo:
        st.success(f"Oferta {salvo[0]} salva como “{salvo[1]}”. Nada foi enviado.")
        st.page_link(PG_REV, label="Ir para Revisar e enviar")
    a = d.dict_da_linha(d.linha_da_oferta(wb, fonte)) if fonte else {}
    cats = d.categorias(wb); tok = f"{modo}-{fonte}-{st.session_state.get('form_n', 0)}"; k = lambda n: f"{n}_{tok}"
    esq, dir_ = st.columns([3, 2], gap="medium")
    with esq:
        with st.container(border=True):
            secao("Produto")
            produto = st.text_input("Nome do produto *", a.get("B") or "", key=k("prod"), placeholder="Ex.: Kit 3 Toalhas de Banho 100% Algodão"); erro_de("produto")
            foto = st.file_uploader("Foto do produto", type=["jpg", "jpeg", "png"], key=k("foto"))
        with st.container(border=True):
            secao("Preço e cupom")
            x, y, z = st.columns(3)
            preco = x.text_input("Preço atual (R$) *", str(a.get("E") or ""), key=k("preco"), placeholder="49,90", help="Número, faixa (20-40) ou ap: para “a partir de”.")
            antes = y.text_input("Preço anterior (R$)", str(a.get("F") or ""), key=k("antes"), placeholder="79,90")
            cupom = z.text_input("Cupom", a.get("G") or "", key=k("cupom"), placeholder="Se houver"); erro_de("preco")
        with st.container(border=True):
            secao("Loja e link")
            x, y = st.columns(2)
            loja = x.text_input("Loja *", a.get("D") or "", key=k("loja"), placeholder="Shopee, Mercado Livre"); fonte_txt = y.text_input("Fonte da informação *", a.get("J") or "Painel", key=k("fonte"))
            erro_de("loja"); erro_de("fonte")
            link = st.text_input("Link de afiliado *", a.get("I") or "", key=k("link"), placeholder="https://s.shopee.com.br/…"); erro_de("link")
        with st.container(border=True):
            secao("Destino e mensagem")
            x, y = st.columns(2)
            cat = x.selectbox("Grupo de destino *", cats, index=cats.index(a["C"]) if a.get("C") in cats else 0, key=k("cat"), help="A oferta vai para o grupo desta categoria.")
            v0 = eo.como_data(a.get("H"))
            validade = y.text_input("Validade", v0.strftime("%d/%m/%Y %H:%M") if v0 else "", key=k("val"), placeholder="dd/mm/aaaa hh:mm · vazio = indeterminada"); erro_de("validade")
            if cat not in mapa: st.warning("Ainda não há grupo de WhatsApp para esta categoria.")
            chamada = st.text_area("Chamada de venda", a.get("R") or "", key=k("cham"), placeholder="Ex.: 40% OFF! Corre que o estoque é curto.", height=90)
        x, y, _ = st.columns([1.2, 1.5, 1])
        rasc = x.button("Salvar rascunho", width="stretch")
        apr = y.button("Enviar para aprovação", type="primary", width="stretch")
    with dir_.container(border=True):
        secao("Prévia da mensagem", "Atualiza ao sair de cada campo")
        c = {"A": "novo", "B": produto, "C": cat, "D": loja, "E": None, "F": None, "G": cupom, "H": validade or None, "I": link, "R": chamada, "J": fonte_txt, "K": datetime.now(), "L": "Aprovado"}
        try:
            c["E"], c["F"] = d.preco_num(preco), d.preco_num(antes)
            if not (produto and c["E"] and link and loja): raise ValueError
            balao(eo.mensagem(c, cfg))
        except Exception: vazio("chat", "Prévia ainda indisponível", "Preencha produto, preço, loja e link.")
    if not (rasc or apr): return
    destino = "Aguardando aprovação" if apr else "Rascunho"; erros = {}
    if not produto.strip(): erros["produto"] = "Informe o nome do produto."
    if not loja.strip(): erros["loja"] = "Informe a loja."
    if not fonte_txt.strip(): erros["fonte"] = "Informe a fonte da informação."
    if not link.startswith("https://"): erros["link"] = "O link deve começar com https://"
    p = ant = None
    try:
        p, ant = d.preco_num(preco), d.preco_num(antes)
        if p is None: erros["preco"] = "Informe o preço atual."
        elif isinstance(p, float) and isinstance(ant, float) and ant <= p: erros["preco"] = "O preço anterior deve ser maior que o atual."
    except ValueError: erros["preco"] = "Preço inválido. Use números, por exemplo 49,90."
    if validade.strip() and not eo.como_data(validade): erros["validade"] = "Validade inválida. Use dd/mm/aaaa hh:mm."
    st.session_state["erros"] = erros
    if erros: st.rerun()
    ws = wb["Ofertas"]
    if modo == "editar": oid = fonte; r = d.linha_da_oferta(wb, oid)[0].row
    else:
        oid = f"P{max(int(str(x)[1:]) for x in df['ID']) + 1:03d}"; r = max(i for i in range(2, ws.max_row + 1) if ws.cell(i, 1).value) + 1
    vals = {1: oid, 2: produto.strip(), 3: cat, 4: loja.strip(), 5: p, 6: ant, 7: cupom or None, 8: validade or None, 9: link.strip(),
            10: fonte_txt.strip(), 11: datetime.now(), 12: destino, 13: None, 18: chamada or None}
    for col, v in vals.items(): ws.cell(r, col).value = v
    try:
        d.salvar(wb, sha, f"painel: {oid} salvo como {destino} por {d.EMAIL}")
        if foto: d.gravar(f"imagens/oferta-{oid}.jpg", foto.getvalue(), d.ler(f"imagens/oferta-{oid}.jpg", binario=True)[1], f"painel: foto {oid}")
    except Exception as e:
        st.error(f"Não foi possível salvar: {e}"); return
    st.session_state["salvo"] = (oid, destino); st.session_state["alvo"] = None; st.session_state["form_n"] = st.session_state.get("form_n", 0) + 1
    st.rerun()


# ------------------------------------------------------------------ revisão
def pg_revisao():
    wb, sha, df, aux = contexto(); mapa, cfg = aux["grupos"], d.config(wb)
    cabecalho("Revisar e enviar", "Nada é enviado sem a sua aprovação. Aprovada, a oferta entra também na fila automática de 3 dias.")
    pend = df[df["Status"].isin(["Rascunho", "Aguardando aprovação"])]; prontas = df[df["Status"] == "Aprovada"]
    t1, t2, t3 = st.tabs([f"Aguardando revisão ({len(pend)})", f"Aprovadas ({len(prontas)})", "Resultado dos envios"])
    with t1:
        if pend.empty:
            with st.container(border=True): vazio("task_alt", "Fila vazia", "Nenhuma oferta aguardando revisão.")
        else:
            esc = st.selectbox("Oferta para revisar", (pend["ID"] + " · " + pend["Produto"].str.slice(0, 60)).tolist()); oid = esc.split(" · ")[0]
            c = d.dict_da_linha(d.linha_da_oferta(wb, oid)); c2 = dict(c); c2["L"] = "Aprovado"; motivo = eo.validar(c2, cfg, mapa)
            with st.container(border=True):
                x, y = st.columns([2, 3], gap="medium")
                with x:
                    img = d.foto(oid)
                    if img: st.image(img, width="stretch")
                    st.html(f'<div class="tit-sec">{h(c["B"])}</div><div style="margin:.35rem 0">{badge(df.set_index("ID").loc[oid, "Status"])}</div><div class="chip">{mi("forum")}Grupo: {h(c["C"])}</div>')
                    st.caption(f"{oid} · {c['D']} · {d.preco_bonito(c['E'])}")
                with y:
                    secao("Mensagem completa")
                    try: balao(eo.mensagem(c2, cfg))
                    except Exception: st.caption("Faltam campos obrigatórios.")
                    if motivo: st.error(f"Ainda não pode ser enviada: {motivo}")
                    else: st.success("Todas as regras de envio foram atendidas.")
            b1, b2, b3 = st.columns(3)
            if b1.button("Aprovar", type="primary", disabled=bool(motivo), width="stretch"):
                lin = d.linha_da_oferta(wb, oid); lin[11].value = "Aprovado"; lin[12].value = d.EMAIL
                d.salvar(wb, sha, f"painel: {oid} aprovado por {d.EMAIL}"); st.toast("Oferta aprovada"); st.rerun()
            if b2.button("Editar", width="stretch"): ir(PG_CAD, alvo=("editar", oid))
            if b3.button("Devolver para rascunho", width="stretch"):
                d.linha_da_oferta(wb, oid)[11].value = "Rascunho"; d.salvar(wb, sha, f"painel: {oid} devolvido a rascunho por {d.EMAIL}"); st.rerun()
    with t2:
        if prontas.empty:
            with st.container(border=True): vazio("inbox", "Nenhuma oferta aprovada aguardando", "As já enviadas aparecem em Resultado dos envios.")
        else:
            st.caption("“Enviar agora” manda uma vez, imediatamente, só para o grupo da categoria.")
            esc = st.selectbox("Oferta aprovada", (prontas["ID"] + " · " + prontas["Produto"].str.slice(0, 60)).tolist(), key="sel_apr"); oid = esc.split(" · ")[0]
            c = d.dict_da_linha(d.linha_da_oferta(wb, oid))
            with st.container(border=True):
                st.html(f'<div class="chip">{mi("forum")}Grupo: {h(c["C"])}</div>'); balao(eo.mensagem(c, cfg))
                conf = st.checkbox("Confirmo o envio desta oferta agora para o grupo", key="conf_env")
                if st.button("Enviar agora", type="primary", disabled=not conf):
                    ok, msg = d.disparar_envio(oid); (st.success if ok else st.warning)(msg)
    with t3:
        rev = {v: k for k, v in mapa.items()}; linhas = []
        for l in reversed(d.log_linhas()):
            if l[1].startswith("P") and l[3] in ("enviada", "erro"):
                linhas.append({"Quando": l[0].replace("T", " "), "Oferta": l[1], "Grupo": nome_grupo(rev.get(l[2], "—")), "Resultado": "Enviada" if l[3] == "enviada" else "Erro", "Detalhe": "" if l[3] == "enviada" else l[4][:120]})
            if len(linhas) >= 25: break
        if linhas:
            with st.container(border=True):
                st.html('<div class="g h" style="grid-template-columns:1.2fr .6fr 1.2fr .8fr 1.6fr"><div>Quando</div><div>Oferta</div><div>Grupo</div><div>Resultado</div><div>Detalhe</div></div>' + "".join(
                    f'<div class="g" style="grid-template-columns:1.2fr .6fr 1.2fr .8fr 1.6fr"><div>{h(x["Quando"])}</div><div>{h(x["Oferta"])}</div><div>{h(x["Grupo"])}</div><div>{badge(x["Resultado"])}</div><div style="color:var(--suave)">{h(x["Detalhe"])}</div></div>' for x in linhas))
            st.button("Atualizar", on_click=st.cache_data.clear)
        else:
            with st.container(border=True): vazio("outbox", "Sem envios registrados", "Depois do primeiro envio, o resultado e qualquer falha aparecem aqui.")


# ------------------------------------------------------------------ grupos, clientes, desempenho, dados
def pg_grupos():
    wb, sha, df, aux = contexto(); mapa, metr = aux["grupos"], aux["metricas"]
    cabecalho("Comunidades e grupos", "Cada categoria tem um grupo. Links de convite e identificadores não aparecem aqui.")
    st.write("")
    rev = {v: k for k, v in mapa.items()}; sete = (date.today() - timedelta(days=7)).isoformat(); gr = (metr or {}).get("grupos", {})
    maior = max([v.get("membros", 0) for k, v in gr.items() if not k.startswith("__")] or [1]) or 1
    linhas = ['<div class="g h"><div>Grupo</div><div>Membros</div><div class="sm">Ofertas</div><div class="sm">Ativas</div><div class="sm">Mensagens em 7 dias</div></div>']
    for k in [k for k in mapa if not k.startswith("__")]:
        sub = df[df["Categoria"] == k]; m = gr.get(k, {}); n = m.get("membros")
        env = sum(1 for l in d.log_linhas() if l[3] == "enviada" and rev.get(l[2]) == k and l[0][:10] >= sete and l[1].startswith("P"))
        mem = f'<div class="barra"><i style="width:{max(2, int(n / maior * 110))}px"></i><span>{n}</span></div>' if n is not None else '<span style="color:var(--suave)">Sem leitura</span>'
        linhas.append(f'<div class="g"><div><b>{h(k)}</b></div><div>{mem}</div><div class="sm">{len(sub)}</div><div class="sm">{int(sub["Status"].isin(["Aprovada", "Enviada"]).sum())}</div><div class="sm">{env}</div></div>')
    if "__AVISOS__" in gr:
        st.html(f'<div class="faixa tres" style="grid-template-columns:1fr"><div class="cel"><div class="ic">{mi("campaign")}</div><div><div class="v">{gr["__AVISOS__"].get("membros", "—")}</div><div class="r">Comunidade (Avisos): boas-vindas, destaque do dia e enquetes</div></div></div></div>')
    with st.container(border=True): st.html("".join(linhas))
    if metr: st.caption(f"Contagem atualizada em {data_br(metr['atualizado_em'])} às {metr['atualizado_em'][11:16]}.")


def pg_clientes():
    wb, sha, df, aux = contexto(); metr = aux["metricas"]
    cabecalho("Clientes", "O que dá para saber sobre os seus grupos, sem expor dados pessoais.")
    st.write("")
    with st.container(border=True):
        secao("Membros por grupo", "A mesma pessoa pode estar em vários grupos; a soma não é o total de clientes únicos")
        if metr:
            g = pd.DataFrame([{"Grupo": nome_grupo(k), "Membros": v["membros"]} for k, v in metr["grupos"].items() if "membros" in v])
            barras(g, "Grupo", "Membros", horizontal=True, altura=260, titulo_y="Membros")
        else: vazio("group", "Contagem ainda não coletada", "Rode a ação Metricas dos grupos no GitHub.")
    a, b = st.columns(2)
    with a.container(border=True): vazio("shopping_cart", "Compradores e principais compradores", "Indisponível: as lojas não informam quem comprou. Só seria possível com um cadastro próprio de clientes.")
    with b.container(border=True): vazio("lock", "Privacidade", "O painel mostra só totais. Nenhum telefone ou nome de membro é lido ou exibido.")


def pg_desempenho():
    wb, sha, df, aux = contexto(); v = d.vendas_df()
    cabecalho("Desempenho", "Cliques, compras e comissões, quando houver dados. Nada é estimado.")
    st.write("")
    if len(v):
        faixa([("ads_click", "azul", int(v["cliques"].sum()), "Cliques"), ("shopping_bag", "ambar", int(v["pedidos"].sum()), "Pedidos"), ("payments", "verde", eo.brl(v["comissao"].sum()), "Comissão")], "tres")
        g = v.groupby("loja")[["cliques", "pedidos"]].sum().reset_index().melt("loja", var_name="Tipo", value_name="Total").rename(columns={"loja": "Loja"})
        with st.container(border=True): secao("Cliques e pedidos por loja"); barras(g, "Loja", "Total", "Tipo", titulo_y="Total", altura=210)
    else:
        with st.container(border=True): vazio("insights", "Sem dados de cliques, compras e comissões", "Registre os números na Visão geral ou importe o relatório de afiliados em dados-painel/vendas.csv.")
    linhas = [l for l in d.log_linhas() if l[3] == "enviada" and l[1].startswith("P")]
    if linhas:
        cat = dict(zip(df["ID"], df["Categoria"])); loja = dict(zip(df["ID"], df["Loja"]))
        a, b = st.columns(2)
        with a.container(border=True):
            secao("Mensagens por categoria"); t = pd.Series([cat.get(l[1], "?") for l in linhas]).value_counts().rename_axis("Categoria").reset_index(name="Mensagens"); barras(t, "Categoria", "Mensagens", horizontal=True, titulo_y="Mensagens")
        with b.container(border=True):
            secao("Mensagens por loja"); t = pd.Series([loja.get(l[1], "?") for l in linhas]).value_counts().rename_axis("Loja").reset_index(name="Mensagens"); barras(t, "Loja", "Mensagens", horizontal=True, titulo_y="Mensagens")
    else:
        with st.container(border=True): vazio("bar_chart", "Sem envios registrados", "Depois dos primeiros envios, os gráficos aparecem aqui.")


def pg_dados():
    wb, sha, df, aux = contexto(); metr = aux["metricas"]
    cabecalho("Dados e integrações", "De onde vêm os números e o que falta conectar. Nenhuma senha ou token é exibido.")
    st.write("")
    lojas_v = set(d.vendas_df()["loja"]); st_loja = lambda n: "Registro manual" if n in lojas_v else "Não conectado"
    quando = f"atualizado em {data_br(metr['atualizado_em'])} às {metr['atualizado_em'][11:16]}" if metr else "ainda não coletado"
    linhas = [("table_chart", "Planilha de ofertas (Excel)", "Banco de dados principal", "Conectado"),
              ("cloud_sync", "GitHub (automação e agenda)", "Envio diário às 9h e “enviar agora”", "Conectado" if d.NUVEM else "Modo local"),
              ("chat", "WhatsApp (Z-API)", f"Membros por grupo: {quando}", "Conectado" if metr else "Pendente"),
              ("storefront", "Shopee: cliques, pedidos e comissão", "A API exige pedir acesso à Shopee. Sem ela, registre na Visão geral", st_loja("Shopee")),
              ("storefront", "Mercado Livre: cliques, pedidos e comissão", "Sem conexão automática. Registre na Visão geral", st_loja("Mercado Livre")),
              ("smartphone", "TikTok Shop", "Só existe no app do celular", "Sem fonte"),
              ("shopping_cart", "Compradores", "As lojas não informam; exigiria cadastro próprio", "Indisponível")]
    cores = {"Conectado": "Enviada", "Modo local": "Aprovada", "Registro manual": "Aprovada", "Pendente": "Aguardando aprovação", "Não conectado": "Aguardando aprovação", "Sem fonte": "Removida", "Indisponível": "Removida"}
    with st.container(border=True):
        corpo = ""
        for ic, n, de, s in linhas:
            bg, fg = CORES[cores[s]]
            corpo += f'<div class="int"><div style="display:flex;gap:.7rem;align-items:center"><span class="ic-lista">{mi(ic)}</span><div><b style="font-weight:600">{h(n)}</b><small>{h(de)}</small></div></div><span class="badge" style="background:{bg};color:{fg}">{h(s)}</span></div>'
        st.html(corpo)
    with st.container(border=True):
        secao("Importar relatório"); st.markdown("Salve como `dados-painel/vendas.csv` com as colunas **data, loja, produto_id, cliques, pedidos, comissao**. O painel passa a mostrar sozinho, sem estimar nada.")


def pg_config():
    wb, sha, df, aux = contexto(); cfg = d.config(wb)
    cabecalho("Configurações", "Rotação, horários e textos da automação. Tudo vale a partir da próxima rodada.")
    st.write("")
    rodando = int(df["Status"].isin(["Aprovada", "Enviada", "Erro"]).sum()); atual = int(cfg.get("CICLO_DIAS") or 1)
    with st.container(border=True):
        secao("Rotação de produtos", "Em quantos dias a rede inteira é enviada antes de recomeçar")
        ops = {1: "Todos os produtos, todo dia"} | {n: f"Rodízio em {n} dias" for n in range(2, 8)}
        a, b = st.columns([2, 3], vertical_alignment="bottom")
        esc = a.selectbox("Rotação", list(ops), index=list(ops).index(atual) if atual in ops else 2, format_func=ops.get)
        b.caption(f"{rodando} produtos rodando: cerca de {round(rodando / esc)} mensagens por dia.")
        if esc == 1: st.warning("Enviar tudo todo dia aumenta o risco de bloqueio do WhatsApp e cansa os grupos.")
        if st.button("Salvar rotação", type="primary", disabled=esc == atual):
            try: d.salvar_config(wb, sha, "CICLO_DIAS", esc, "A rede inteira sai em N dias e recomeça"); st.toast("Rotação salva"); st.rerun()
            except Exception as e: st.error(f"Não foi possível salvar: {e}")
    with st.container(border=True):
        secao("Horários (Brasília)", "Cada rotina tem um segundo disparo de reserva 30 minutos depois")
        hor = d.ler_horarios()
        a, b, c = st.columns(3)
        env = a.text_input("Ofertas e boas-vindas", hor["envio"][0], placeholder="09:07", help="Formato hh:mm")
        des = b.text_input("Destaque do dia", hor["destaque"][0], placeholder="12:17", help="Formato hh:mm")
        enq = c.text_input("Enquete", hor["enquete"][0], placeholder="20:17", help="Formato hh:mm")
        dias = st.multiselect("Dias da enquete", list(d.DIAS_CRON), default=hor["enquete"][1])
        novo = tuple(x.strip() for x in (env, des, enq))
        valido = all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", x) for x in novo)
        if not valido: st.error("Use o formato hh:mm, por exemplo 09:07.")
        elif any(x.endswith(":00") for x in novo): st.warning("Em hora cheia o GitHub costuma atrasar ou pular o disparo. Prefira um minuto como 07 ou 17.")
        mudou = novo != (hor["envio"][0], hor["destaque"][0], hor["enquete"][0]) or set(dias) != set(hor["enquete"][1])
        if st.button("Salvar horários", type="primary", disabled=not mudou or not dias or not valido):
            try: d.salvar_horarios(*novo, dias); st.toast("Horários salvos"); st.rerun()
            except Exception as e: st.error(f"Não foi possível salvar: {e}")
    with st.container(border=True):
        secao("Templates", "Os textos usados nas mensagens")
        nome = st.selectbox("Template", list(d.TEMPLATES), format_func=lambda n: d.TEMPLATES[n][0])
        original = d.ler(nome)[0] or ""; permitidos = sorted(d.TEMPLATES[nome][1])
        a, b = st.columns(2, gap="medium")
        txt = a.text_area("Texto", original, key=f"tpl_{nome}", height=300)
        if permitidos: a.caption("Campos: " + ", ".join("{" + x + "}" for x in permitidos) + ". Linha com campo vazio não sai.")
        with b:
            secao("Prévia", "Com dados de exemplo")
            erro = d.validar_template(nome, txt)
            if erro: st.error(erro)
            else: balao(d.previa_template(nome, txt))
        if st.button("Salvar template", type="primary", disabled=bool(erro) or txt == original):
            try: d.gravar(nome, (txt if txt.endswith("\n") else txt + "\n").encode(), d.ler(nome)[1], f"painel: template {nome} por {d.EMAIL}"); st.toast("Template salvo"); st.rerun()
            except Exception as e: st.error(f"Não foi possível salvar: {e}")


# ------------------------------------------------------------------ login
def gravar_cookie(valor, dias):
    """O Streamlit não grava cookie sozinho: isso mantém a sessão ao recarregar a página."""
    html_c = f"""<script>document.cookie = {json.dumps(d.COOKIE + "=" + quote(valor))} + "; path=/; max-age={dias * 86400}; SameSite=Lax; Secure";
    try {{ window.parent.document.cookie = {json.dumps(d.COOKIE + "=" + quote(valor))} + "; path=/; max-age={dias * 86400}; SameSite=Lax; Secure"; }} catch (e) {{}}</script>"""
    components.html(html_c, height=0)


def tela_login():
    st.markdown("<style>[data-testid='stSidebar'],[data-testid='stExpandSidebarButton'],[data-testid='stSidebarCollapsedControl']{display:none!important}.block-container{max-width:420px;padding-top:12vh}</style>", unsafe_allow_html=True)
    st.html(f'<div class="marca" style="justify-content:center;--texto:#1F2937;padding-bottom:.4rem"><div class="logo" style="color:var(--roxo)">{mi("shopping_bag")}</div><div><b style="font-size:1.25rem">Ofertas da Polly</b></div></div>')
    st.html('<p class="sub" style="text-align:center;margin-bottom:1rem">Entre para acessar o painel</p>')
    try: pronto = bool(d._acessos())
    except Exception: pronto = False
    if not pronto: st.error("Login indisponível: o painel não conseguiu ler os acessos.")
    with st.container(border=True):
        with st.form("login"):
            email = st.text_input("E-mail", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            ok = st.form_submit_button("Entrar", type="primary", width="stretch")
        if ok:
            e = email.strip().lower()
            if d.bloqueado(e): st.error("Muitas tentativas. Aguarde 15 minutos.")
            elif d.conferir_senha(e, senha):
                st.session_state.pop("saiu", None); st.session_state["usuario"] = e; st.session_state["cookie_novo"] = d.criar_sessao(e); st.rerun()
            else: st.error("E-mail ou senha incorretos.")


if st.session_state.pop("sair", False):
    gravar_cookie("", 0); st.session_state["saiu"] = True
if d.login_ativo() and not d.usuario():
    salvo = None if st.session_state.get("saiu") else d.ler_sessao(unquote(st.context.cookies.get(d.COOKIE, "") or ""))
    if salvo: st.session_state["usuario"] = salvo
    else:
        st.navigation([st.Page(tela_login, title="Entrar", default=True)], position="hidden").run(); st.stop()
if st.session_state.get("cookie_novo"): gravar_cookie(st.session_state.pop("cookie_novo"), d.DIAS_SESSAO)


# ------------------------------------------------------------------ navegação (menu próprio, responsivo)
PG_VISAO = st.Page(pg_visao, title="Visão geral", default=True)
PG_OFER = st.Page(pg_ofertas, title="Ofertas", url_path="ofertas")
PG_CAD = st.Page(pg_cadastro, title="Cadastrar oferta", url_path="cadastrar")
PG_REV = st.Page(pg_revisao, title="Revisar e enviar", url_path="revisar")
PG_GRU = st.Page(pg_grupos, title="Comunidades e grupos", url_path="grupos")
PG_CLI = st.Page(pg_clientes, title="Clientes", url_path="clientes")
PG_DES = st.Page(pg_desempenho, title="Desempenho", url_path="desempenho")
PG_DAD = st.Page(pg_dados, title="Dados e integrações", url_path="dados")
PG_CFG = st.Page(pg_config, title="Configurações", url_path="configuracoes")
PAGINAS = [PG_VISAO, PG_OFER, PG_CAD, PG_REV, PG_GRU, PG_CLI, PG_DES, PG_DAD, PG_CFG]
nav = st.navigation(PAGINAS, position="hidden")
with st.sidebar:
    st.html(f'<div class="marca"><div class="logo">{mi("shopping_bag")}</div><div><b>Ofertas da Polly</b><span class="t">Painel de gestão</span></div></div>')
    for p in PAGINAS: st.page_link(p)
    st.html(f'<div class="perfil">{mi("account_circle")}<div><b>{h(d.usuario() or d.EMAIL)}</b>{"Online" if d.NUVEM else "Só neste computador"}</div></div>')
    if d.login_ativo() and st.button("Sair", width="stretch"):
        st.session_state.clear(); st.session_state["sair"] = True; st.rerun()
nav.run()
