import base64
import streamlit as st
import pandas as pd
import numpy as np
import cv2
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# 🔎 CONSULTA DE PRODUTO POR CÓDIGO DE BARRA (leitura via câmera)
# Mesmo padrão do app de Pedidos: conexão "banco_erp" (st.connection), view
# python_estoque, chave ERP_ATIVO no secrets. Cores abaixo aproximam a
# identidade visual do painel-pedidos (banner navy + botão vermelho #ff4b4b,
# que é o valor exato usado lá). Se você tiver o config.toml/CSS exato do
# painel-pedidos, me manda que eu ajusto certinho.
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Check Produtos - Molicenter", page_icon="🔍", layout="wide")

LOJAS_NOMES = ["Loja 01", "Loja 02", "Loja 03", "Loja 04", "Loja 05", "Loja 06", "Loja 07", "Loja 08"]
LOJAS_CODIGOS = [f"{i:03d}" for i in range(1, len(LOJAS_NOMES) + 1)]

# Senha fixa de acesso — gate simples (não é autenticação forte), conforme pedido.
SENHA_ACESSO = "moli1234"

COR_BANNER = "#122C43"          # navy do topo (telas internas)
COR_SIDEBAR = "#132A41"         # navy da sidebar
COR_BOTAO_SIDEBAR = "#ff4b4b"   # vermelho — confirmado no CSS do app de Pedidos (só botões da sidebar)
COR_PRIMARIA = "#D6218C"        # rosa/magenta — cor de destaque global (ex.: "Entrar no Sistema")
COR_TITULO_LOGIN = "#1B3A5C"    # navy do título "Portal de Pedidos"
COR_SUBTITULO_LOGIN = "#2C6E8C"
COR_LABEL_USUARIO = "#6C3FC5"   # roxo do rótulo "Usuário de acesso"
COR_LABEL_SENHA = "#C77D02"     # âmbar do rótulo "Senha de acesso"

# ─────────────────────────────────────────────────────────────────────────────
# 🎨 CSS GLOBAL (sidebar navy + botão primário rosa/magenta, padrão do painel-pedidos)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
    <style>
    div.stButton > button[kind="primary"] {{
        background-color: {COR_PRIMARIA} !important;
        border-color: {COR_PRIMARIA} !important;
        color: white !important;
    }}
    [data-testid="stSidebar"] {{
        background-color: {COR_SIDEBAR} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: #ffffff !important;
    }}
    [data-testid="stSidebar"] button {{
        background-color: {COR_BOTAO_SIDEBAR} !important;
        color: white !important;
        border-color: {COR_BOTAO_SIDEBAR} !important;
    }}
    </style>
""", unsafe_allow_html=True)


def _logo_base64() -> str:
    # Espera "passaro_logo.png" na raiz do repositório, junto do app.py.
    try:
        with open("passaro_logo.png", "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def desenhar_banner(subtitulo: str = ""):
    logo_b64 = _logo_base64()
    logo_tag = (
        f'<img src="data:image/png;base64,{logo_b64}" style="height:38px;border-radius:4px;">'
        if logo_b64 else '<span style="font-size:28px;">🦜</span>'
    )
    extra = f'<span style="font-size:14px;font-weight:400;opacity:.85;"> ---&gt; {subtitulo}</span>' if subtitulo else ""
    st.markdown(f"""
        <div style="background-color:{COR_BANNER};padding:14px 22px;border-radius:6px;
                    display:flex;align-items:center;gap:14px;margin-bottom:20px;">
            {logo_tag}
            <div style="color:#ffffff;">
                <span style="font-size:20px;font-weight:700;">🔍 Check Produtos - Molicenter</span>
                {extra}
            </div>
        </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# 🔌 CHAVE GERAL DO ERP (mesmo mecanismo do app de Pedidos)
# ─────────────────────────────────────────────────────────────────────────────
ERP_ATIVO_PADRAO = True


def erp_ativo() -> bool:
    v = None
    try:
        v = st.secrets.get("ERP_ATIVO", None)
    except Exception:
        v = None
    if v is None:
        try:
            v = st.secrets["connections"]["banco_erp"].get("ERP_ATIVO", None)
        except Exception:
            v = None
    if v is None:
        v = ERP_ATIVO_PADRAO
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in ("false", "0", "nao", "não", "off", "no", "n")


def data_hora_brasilia() -> str:
    agora = datetime.now(timezone.utc) - timedelta(hours=3)
    return agora.strftime("%d/%m/%Y %H:%M:%S")


conn_pg = st.connection(
    "banco_erp",
    type="sql",
    connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
)

# ─────────────────────────────────────────────────────────────────────────────
# 📷 LEITURA DO CÓDIGO DE BARRA NA FOTO (pyzbar, com fallback no OpenCV)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from pyzbar.pyzbar import decode as _zbar_decode
    _TEM_PYZBAR = True
except Exception:
    _TEM_PYZBAR = False


def decodificar_codigo_barra(imagem_bytes: bytes) -> list:
    arr = np.frombuffer(imagem_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    codigos = []
    if _TEM_PYZBAR:
        try:
            for obj in _zbar_decode(img):
                texto = obj.data.decode("utf-8", errors="ignore").strip()
                if texto:
                    codigos.append(texto)
        except Exception:
            pass

    if not codigos:
        try:
            detector = cv2.barcode.BarcodeDetector()
            ok, decoded_info, _tipos, _pts = detector.detectAndDecodeWithType(img)
            if ok:
                codigos.extend([c.strip() for c in decoded_info if c and c.strip()])
        except Exception:
            pass

    vistos, unicos = set(), []
    for c in codigos:
        if c not in vistos:
            vistos.add(c)
            unicos.append(c)
    return unicos


def preco_para_texto(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    try:
        return f"R$ {float(v):.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "-"


# ─────────────────────────────────────────────────────────────────────────────
# 🔍 CONSULTA NO BANCO — agora em TODAS as lojas de uma vez (sem seletor de loja)
# ─────────────────────────────────────────────────────────────────────────────
_PLACEHOLDERS_LOJAS = ", ".join(f"'{c}'" for c in LOJAS_CODIGOS)  # constantes fixas, não é input do usuário


@st.cache_data(ttl=15, show_spinner=False)
def buscar_produto_todas_lojas(codigo_barra: str):
    query = f"""
        SELECT cade_codempresa   AS "Loja",
               cade_codigo       AS "Codigo",
               cadp_descricao    AS "Produto",
               cadp_codigobarra  AS "CodBarra",
               estoque           AS "Estoque",
               prvenda           AS "Preco"
        FROM python_estoque
        WHERE cadp_codigobarra = :barra
          AND cade_codempresa IN ({_PLACEHOLDERS_LOJAS})
    """
    df = conn_pg.query(query, params={"barra": codigo_barra}, ttl=15)
    if df is None or df.empty:
        return None

    def _primeiro_nao_nulo(col):
        serie = df[col].dropna()
        return serie.iloc[0] if not serie.empty else None

    codigo_prod = _primeiro_nao_nulo("Codigo")
    info = {
        "Produto": _primeiro_nao_nulo("Produto") or "-",
        "Codigo": int(codigo_prod) if codigo_prod is not None else None,
        "CodBarra": _primeiro_nao_nulo("CodBarra") or codigo_barra,
    }
    estoque_por_loja = {}
    preco_por_loja = {}
    for nome, cod in zip(LOJAS_NOMES, LOJAS_CODIGOS):
        linha = df[df["Loja"] == cod]
        valor_estoque = linha["Estoque"].iloc[0] if not linha.empty else None
        valor_preco = linha["Preco"].iloc[0] if not linha.empty else None
        estoque_por_loja[nome] = float(valor_estoque) if pd.notna(valor_estoque) else 0.0
        preco_por_loja[nome] = valor_preco if pd.notna(valor_preco) else None
    info["EstoquePorLoja"] = estoque_por_loja
    info["EstoqueTotal"] = sum(estoque_por_loja.values())
    info["PrecoPorLoja"] = preco_por_loja
    return info


def buscar_produtos_parecidos(codigo_barra: str) -> pd.DataFrame:
    query = f"""
        SELECT DISTINCT cade_codigo AS "Código", cadp_descricao AS "Produto",
               cadp_codigobarra AS "Cód. Barra", prvenda AS "Preço"
        FROM python_estoque
        WHERE cadp_codigobarra ILIKE :busca
          AND cade_codempresa IN ({_PLACEHOLDERS_LOJAS})
        LIMIT 10
    """
    busca = f"%{codigo_barra.strip().lstrip('0')}%" if codigo_barra.strip() else "%"
    try:
        return conn_pg.query(query, params={"busca": busca}, ttl=15)
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 🔒 LOGIN (gate simples — usuário livre + senha fixa)
# ─────────────────────────────────────────────────────────────────────────────
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = ""
if "historico_scans" not in st.session_state:
    st.session_state.historico_scans = []

if not st.session_state.autenticado:
    st.write("")  # respiro no topo, igual ao Portal de Pedidos
    st.write("")
    col_esq, col_meio, col_dir = st.columns([1, 2, 1])
    with col_meio:
        with st.container(border=True):
            col_titulo, col_logo = st.columns([4, 1])
            with col_titulo:
                st.markdown(
                    f"<h2 style='color:{COR_TITULO_LOGIN};margin-bottom:2px;'>Check Produtos</h2>"
                    f"<p style='color:{COR_SUBTITULO_LOGIN};margin-top:0;font-size:14px;'>"
                    f"Consulta por Código de Barra — Molicenter</p>",
                    unsafe_allow_html=True,
                )
            with col_logo:
                logo_b64 = _logo_base64()
                if logo_b64:
                    st.markdown(
                        f'<div style="text-align:right;"><img src="data:image/png;base64,{logo_b64}" '
                        f'style="height:46px;"></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown("<div style='text-align:right;font-size:34px;'>🦜</div>", unsafe_allow_html=True)

            st.divider()

            st.markdown(
                f"<span style='color:{COR_LABEL_USUARIO};font-weight:600;'>👤 Usuário de acesso:</span>",
                unsafe_allow_html=True,
            )
            usuario = st.text_input("Usuário de acesso", label_visibility="collapsed", placeholder="Digite seu nome")

            st.markdown(
                f"<span style='color:{COR_LABEL_SENHA};font-weight:600;'>🔑 Senha de acesso:</span>",
                unsafe_allow_html=True,
            )
            senha = st.text_input("Senha de acesso", type="password", label_visibility="collapsed")

            st.write("")
            if st.button("Entrar no Sistema", type="primary", use_container_width=True):
                if not usuario.strip():
                    st.error("Informe o usuário.")
                elif senha != SENHA_ACESSO:
                    st.error("Senha incorreta.")
                else:
                    st.session_state.autenticado = True
                    st.session_state.usuario_logado = usuario.strip()
                    st.rerun()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ INTERFACE (já autenticado)
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.usuario_logado}")
    if st.button("🚪 Sair", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.usuario_logado = ""
        st.rerun()
    st.divider()
    if st.session_state.historico_scans:
        st.caption(f"📋 {len(st.session_state.historico_scans)} produto(s) consultado(s) nesta sessão")
        if st.button("🧹 Limpar histórico", use_container_width=True):
            st.session_state.historico_scans = []
            st.rerun()

desenhar_banner(subtitulo=f"Usuário: {st.session_state.usuario_logado}")
st.caption("Fotografe o código de barras do produto para ver o estoque em todas as lojas e o preço na hora.")

if not erp_ativo():
    st.warning(
        "🔌 A conexão com o ERP está temporariamente desligada "
        "(ERP_ATIVO = false no secrets). Não é possível consultar produtos agora."
    )
    st.stop()

if "codigo_barra_atual" not in st.session_state:
    st.session_state.codigo_barra_atual = ""

# Câmera/entrada ficam numa coluna central estreita — só as tabelas de resultado
# usam a largura toda da tela (é o vídeo da câmera que fica gigante em layout wide).
col_busca_esq, col_busca_meio, col_busca_dir = st.columns([1, 2, 1])
with col_busca_meio:
    foto = st.camera_input("📷 Fotografar o código de barras")
    if foto is not None:
        codigos_encontrados = decodificar_codigo_barra(foto.getvalue())
        if codigos_encontrados:
            st.session_state.codigo_barra_atual = codigos_encontrados[0]
            st.success(f"✅ Código lido: **{codigos_encontrados[0]}**")
            if len(codigos_encontrados) > 1:
                st.caption("Outros códigos detectados na mesma foto: " + ", ".join(codigos_encontrados[1:]))
        else:
            st.warning(
                "⚠️ Não consegui ler nenhum código de barras nessa foto. "
                "Tente de novo com mais luz e foco, ou digite o código abaixo."
            )

    codigo_manual = st.text_input(
        "Ou digite o código manualmente",
        value=st.session_state.codigo_barra_atual,
        placeholder="Ex: 7891149200504",
    )

    buscar = st.button("🔎 Buscar produto", type="primary", use_container_width=True)

if buscar:
    codigo_busca = codigo_manual.strip()
    if not codigo_busca:
        st.error("Digite ou fotografe um código de barra antes de buscar.")
    else:
        st.session_state.codigo_barra_atual = codigo_busca
        try:
            with st.spinner("Consultando em todas as lojas..."):
                info = buscar_produto_todas_lojas(codigo_busca)
        except Exception as e:
            st.error(f"Erro ao consultar o produto: {e}")
            info = None

        if info is not None:
            st.divider()
            st.markdown(f"### {info['Produto']}")
            col1, col2, col3 = st.columns(3)
            col1.metric("Código do Produto", info["Codigo"] if info["Codigo"] is not None else "-")
            col2.metric("Cód. Barra", info["CodBarra"])
            col3.metric("Estoque Total (todas as lojas)", f"{info['EstoqueTotal']:.0f}")

            st.markdown("**📦 Estoque:**")
            tabela_estoque = dict(info["EstoquePorLoja"])
            tabela_estoque["Total"] = info["EstoqueTotal"]
            st.dataframe(pd.DataFrame([tabela_estoque]), use_container_width=True, hide_index=True)

            st.markdown("**💰 Preço:**")
            tabela_preco = {loja: preco_para_texto(v) for loja, v in info["PrecoPorLoja"].items()}
            st.dataframe(pd.DataFrame([tabela_preco]), use_container_width=True, hide_index=True)

            linha_hist = {
                "Hora": data_hora_brasilia(),
                "Usuário": st.session_state.usuario_logado,
                "Produto": info["Produto"],
                "Código": info["Codigo"],
                "Cód. Barra": info["CodBarra"],
            }
            linha_hist.update({f"{loja} (Estoque)": v for loja, v in info["EstoquePorLoja"].items()})
            linha_hist["Total (Estoque)"] = info["EstoqueTotal"]
            linha_hist.update({f"{loja} (Preço)": preco_para_texto(v) for loja, v in info["PrecoPorLoja"].items()})
            st.session_state.historico_scans.insert(0, linha_hist)
        else:
            st.error(f"❌ Nenhum produto encontrado com o código **{codigo_busca}**.")
            sugestoes = buscar_produtos_parecidos(codigo_busca)
            if sugestoes is not None and not sugestoes.empty:
                st.caption("Produtos com código de barra parecido:")
                st.dataframe(sugestoes, use_container_width=True, hide_index=True)

if st.session_state.historico_scans:
    st.divider()
    st.subheader("📋 Histórico desta sessão")
    st.dataframe(pd.DataFrame(st.session_state.historico_scans), use_container_width=True, hide_index=True)
