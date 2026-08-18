import streamlit as st
import pandas as pd
import numpy as np
import cv2
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# 🔎 CONSULTA DE PRODUTO POR CÓDIGO DE BARRA (leitura via câmera)
# Segue o mesmo padrão do app de Pedidos: mesma conexão "banco_erp" (st.connection),
# mesma view python_estoque, mesmo esquema de LOJAS_NOMES e mesma chave ERP_ATIVO
# no secrets para desligar a consulta em modo degradado quando necessário.
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Consulta Produto - Cód. Barra", page_icon="🔍", layout="centered")

LOJAS_NOMES = ["Loja 01", "Loja 02", "Loja 03", "Loja 04", "Loja 05", "Loja 06", "Loja 07", "Loja 08"]

# ─────────────────────────────────────────────────────────────────────────────
# 🔌 CHAVE GERAL DO ERP (mesmo mecanismo do app de Pedidos)
# Com ERP_ATIVO = false no secrets, a consulta é desligada (não dá pra buscar
# produto sem o ERP, então aqui só exibimos um aviso e paramos a tela).
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
    # Servidor roda em UTC; Brasília é UTC-3 fixo (sem horário de verão desde 2019).
    agora = datetime.now(timezone.utc) - timedelta(hours=3)
    return agora.strftime("%d/%m/%Y %H:%M:%S")


# connect_timeout/statement_timeout: mesmo ajuste do app de Pedidos, pra não
# travar a tela se o ERP não responder.
conn_pg = st.connection(
    "banco_erp",
    type="sql",
    connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
)

# ─────────────────────────────────────────────────────────────────────────────
# 📷 LEITURA DO CÓDIGO DE BARRA NA FOTO
# Tenta primeiro com pyzbar (mais preciso; precisa da lib de sistema libzbar0,
# ver packages.txt). Se pyzbar não estiver disponível, cai no detector nativo
# do OpenCV (funciona só com pip, sem lib de sistema, porém menos robusto).
# Em qualquer caso, o campo de texto abaixo permite digitar o código manualmente.
# ─────────────────────────────────────────────────────────────────────────────
try:
    from pyzbar.pyzbar import decode as _zbar_decode
    _TEM_PYZBAR = True
except Exception:
    _TEM_PYZBAR = False


def decodificar_codigo_barra(imagem_bytes: bytes) -> list:
    """Recebe os bytes de uma foto e devolve a lista de códigos de barra achados
    (string), na ordem em que foram encontrados, sem repetição."""
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
    # Mesmo formato usado no app de Pedidos ("R$ 12,50").
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    try:
        return f"R$ {float(v):.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return "-"


# ─────────────────────────────────────────────────────────────────────────────
# 🔍 CONSULTA NO BANCO (view python_estoque — mesma usada em buscar_estoque_erp)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=15, show_spinner=False)
def buscar_produto_por_barra(loja_id_str: str, codigo_barra: str) -> pd.DataFrame:
    query = """
        SELECT cade_codigo      AS "Codigo",
               cadp_descricao    AS "Produto",
               cadp_codigobarra  AS "CodBarra",
               estoque           AS "Estoque",
               prvenda           AS "Preco"
        FROM python_estoque
        WHERE cade_codempresa = :loja
          AND cadp_codigobarra = :barra
    """
    return conn_pg.query(query, params={"loja": loja_id_str, "barra": codigo_barra}, ttl=15)


def buscar_produto_parecido(loja_id_str: str, codigo_barra: str) -> pd.DataFrame:
    # Fallback quando não acha o código exato: tenta um LIKE (ex.: dígito
    # verificador diferente / EAN-13 gravado como UPC-A de 12 dígitos etc.).
    query = """
        SELECT cade_codigo      AS "Codigo",
               cadp_descricao    AS "Produto",
               cadp_codigobarra  AS "CodBarra",
               estoque           AS "Estoque",
               prvenda           AS "Preco"
        FROM python_estoque
        WHERE cade_codempresa = :loja
          AND cadp_codigobarra ILIKE :busca
        LIMIT 10
    """
    busca = f"%{codigo_barra.strip().lstrip('0')}%" if codigo_barra.strip() else "%"
    try:
        return conn_pg.query(query, params={"loja": loja_id_str, "busca": busca}, ttl=15)
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# 🖥️ INTERFACE
# ─────────────────────────────────────────────────────────────────────────────
st.title("🔍 Consulta de Produto por Código de Barra")
st.caption("Uso em visita de loja: fotografe o código de barras do produto para ver estoque e preço na hora.")

with st.sidebar:
    st.header("⚙️ Loja")
    loja_nome = st.selectbox("Selecione a loja", LOJAS_NOMES)
    loja_id = int(loja_nome.split()[-1])
    loja_id_str = f"{loja_id:03d}"

    st.divider()
    if "historico_scans" not in st.session_state:
        st.session_state.historico_scans = []
    if st.session_state.historico_scans:
        st.caption(f"📋 {len(st.session_state.historico_scans)} produto(s) consultado(s) nesta sessão")
        if st.button("🧹 Limpar histórico", use_container_width=True):
            st.session_state.historico_scans = []
            st.rerun()

if not erp_ativo():
    st.warning(
        "🔌 A conexão com o ERP está temporariamente desligada "
        "(ERP_ATIVO = false no secrets). Não é possível consultar produtos agora."
    )
    st.stop()

# Estado do código já lido/digitado, para o campo de texto reaproveitar entre reruns.
if "codigo_barra_atual" not in st.session_state:
    st.session_state.codigo_barra_atual = ""

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
            with st.spinner("Consultando..."):
                df = buscar_produto_por_barra(loja_id_str, codigo_busca)
        except Exception as e:
            st.error(f"Erro ao consultar o produto: {e}")
            df = pd.DataFrame()

        if df is not None and not df.empty:
            row = df.iloc[0]
            st.divider()
            st.markdown(f"### {row['Produto']}")
            col1, col2 = st.columns(2)
            col1.metric("Código do Produto", int(row["Codigo"]))
            col2.metric("Cód. Barra", row["CodBarra"])
            col3, col4 = st.columns(2)
            estoque_val = row["Estoque"]
            col3.metric("Estoque", f"{estoque_val:.0f}" if pd.notna(estoque_val) else "0")
            col4.metric("Preço de Venda", preco_para_texto(row["Preco"]))

            st.session_state.historico_scans.insert(0, {
                "Hora": data_hora_brasilia(),
                "Loja": loja_nome,
                "Código": int(row["Codigo"]),
                "Produto": row["Produto"],
                "Cód. Barra": row["CodBarra"],
                "Estoque": estoque_val,
                "Preço": preco_para_texto(row["Preco"]),
            })
        else:
            st.error(f"❌ Nenhum produto encontrado com o código **{codigo_busca}** na {loja_nome}.")
            sugestoes = buscar_produto_parecido(loja_id_str, codigo_busca)
            if sugestoes is not None and not sugestoes.empty:
                st.caption("Produtos com código de barra parecido, encontrados nesta loja:")
                st.dataframe(
                    sugestoes.rename(columns={
                        "Codigo": "Código", "CodBarra": "Cód. Barra", "Preco": "Preço",
                    }),
                    use_container_width=True, hide_index=True,
                )

if st.session_state.historico_scans:
    st.divider()
    st.subheader("📋 Histórico desta sessão")
    st.dataframe(pd.DataFrame(st.session_state.historico_scans), use_container_width=True, hide_index=True)
