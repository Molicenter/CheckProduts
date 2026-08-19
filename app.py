import base64
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import cv2
from io import BytesIO
from datetime import datetime, timezone, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from sqlalchemy import text

try:
    # Câmera traseira por padrão (facingMode "environment") — evita ter que
    # inverter manualmente toda hora. Se o pacote não estiver instalado
    # (esqueceu de subir o requirements.txt novo), cai de volta no
    # st.camera_input padrão do Streamlit (câmera frontal por padrão).
    from streamlit_back_camera_input import back_camera_input
    _TEM_CAMERA_TRASEIRA = True
except Exception:
    _TEM_CAMERA_TRASEIRA = False

# ─────────────────────────────────────────────────────────────────────────────
# 🔎 CONSULTA DE PRODUTO POR CÓDIGO DE BARRA (leitura via câmera)
# Mesmo padrão do app de Pedidos: conexão "banco_erp" (st.connection), view
# python_estoque, chave ERP_ATIVO no secrets. Cores abaixo aproximam a
# identidade visual do painel-pedidos (banner navy + botão vermelho #ff4b4b,
# que é o valor exato usado lá). Se você tiver o config.toml/CSS exato do
# painel-pedidos, me manda que eu ajusto certinho.
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Check Produtos - Molicenter",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",  # começa fechada — usuário abre pelo ">" se precisar
)

LOJAS_NOMES = ["Loja 01", "Loja 02", "Loja 03", "Loja 04", "Loja 05", "Loja 06", "Loja 07", "Loja 08", "Loja 30"]

# Código da empresa/loja = número escrito no NOME (não a posição na lista!). Assim,
# se você adicionar/reordenar lojas com números fora da sequência 01..08 (ex.: "Loja 30"),
# o código consultado no banco continua batendo certo.
LOJAS_CODIGOS = [f"{int(''.join(ch for ch in nome if ch.isdigit())):03d}" for nome in LOJAS_NOMES]

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
    /* Selectbox na sidebar (ex.: "Loja desta ronda"): a caixinha em si tem
       fundo claro (não navy), então força fundo branco + texto escuro nela —
       tanto fechada (valor escolhido) quanto aberta (campo de busca/filtro).
       -webkit-text-fill-color é necessário além de color: em campos <input>,
       o Chrome pode ignorar só o "color" e continuar pintando a letra em
       branco (é o que estava acontecendo aqui). */
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] input {{
        background-color: #ffffff !important;
        border-color: #cccccc !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] *,
    [data-testid="stSidebar"] input {{
        color: #1A1A1A !important;
        -webkit-text-fill-color: #1A1A1A !important;
    }}
    /* Lista suspensa (as opções "Loja 01", "Loja 02"...) abre com fundo
       branco, mas herdava o texto branco da sidebar e ficava ilegível — força
       preto só dentro da lista de opções, sem mexer no resto. */
    [data-baseweb="popover"] *,
    [data-baseweb="menu"] *,
    ul[role="listbox"] * {{
        color: #1A1A1A !important;
        -webkit-text-fill-color: #1A1A1A !important;
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
# 💾 RONDA DE PREÇOS — gravado direto no Postgres (não em session_state), pra
# não perder nada se a internet oscilar/recarregar a página no meio da ronda,
# e pra várias lojas registrarem ao mesmo tempo no mesmo lugar.
# ─────────────────────────────────────────────────────────────────────────────
TABELA_RONDA = "ronda_precos_erros"


@st.cache_resource(show_spinner=False)
def _garantir_tabela_ronda() -> bool:
    try:
        with conn_pg.session as s:
            s.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {TABELA_RONDA} (
                    id SERIAL PRIMARY KEY,
                    criado_em TIMESTAMP NOT NULL DEFAULT NOW(),
                    hora_texto VARCHAR(20),
                    usuario VARCHAR(100),
                    loja VARCHAR(50),
                    produto VARCHAR(255),
                    codigo VARCHAR(50),
                    codigo_barra VARCHAR(50),
                    preco_sistema VARCHAR(30),
                    observacao TEXT,
                    resolvido BOOLEAN NOT NULL DEFAULT FALSE
                )
            """))
            s.commit()
        return True
    except Exception:
        return False


def salvar_erro_ronda(loja, usuario, produto, codigo, codigo_barra, preco_sistema_txt, observacao):
    with conn_pg.session as s:
        s.execute(text(f"""
            INSERT INTO {TABELA_RONDA}
                (hora_texto, usuario, loja, produto, codigo, codigo_barra, preco_sistema, observacao)
            VALUES
                (:hora_texto, :usuario, :loja, :produto, :codigo, :codigo_barra, :preco_sistema, :observacao)
        """), {
            "hora_texto": data_hora_brasilia(),
            "usuario": usuario,
            "loja": loja,
            "produto": produto,
            "codigo": str(codigo) if codigo is not None else None,
            "codigo_barra": codigo_barra,
            "preco_sistema": preco_sistema_txt,
            "observacao": observacao or "",
        })
        s.commit()


@st.cache_data(ttl=10)
def buscar_erros_ronda(loja: str) -> pd.DataFrame:
    try:
        return conn_pg.query(
            f"SELECT id, hora_texto, usuario, loja, produto, codigo, codigo_barra, "
            f"preco_sistema, observacao FROM {TABELA_RONDA} "
            f"WHERE loja = :loja AND resolvido = FALSE ORDER BY criado_em DESC",
            params={"loja": loja},
            ttl=10,
        )
    except Exception:
        return pd.DataFrame()


def marcar_erros_resolvidos(loja: str):
    with conn_pg.session as s:
        s.execute(
            text(f"UPDATE {TABELA_RONDA} SET resolvido = TRUE WHERE loja = :loja AND resolvido = FALSE"),
            {"loja": loja},
        )
        s.commit()
    buscar_erros_ronda.clear()

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
# 🖨️ IMPRESSÃO NA ZEBRA ZQ630 PLUS (via app "Zebra Browser Print" no Android)
#
# COMO FUNCIONA: o app roda na nuvem, então quem manda o comando pra impressora
# é o NAVEGADOR do celular — não o Python. O app Android "Zebra Browser Print"
# roda em segundo plano, conectado à impressora por Bluetooth, e expõe uma API
# local que o JavaScript da página consegue chamar (padrão oficial da Zebra
# pra isso, não funciona em iPhone).
#
# CONFIGURAÇÃO NECESSÁRIA (uma vez só, por celular):
#   1. Instalar o app "Zebra Browser Print" no Android (baixar em zebra.com,
#      seção de suporte/downloads do ZQ630 Plus).
#   2. Parear a impressora ZQ630 Plus por Bluetooth no próprio Android
#      (Configurações > Bluetooth) e depois abrir o app Zebra Browser Print
#      pra ele descobrir/registrar a impressora e marcar como "padrão".
#   3. Baixar o arquivo BrowserPrint-3.x.x.min.js (SDK oficial, mesmo site de
#      suporte da Zebra) e salvar como "browserprint.js" na raiz deste
#      repositório, junto do app.py — o app lê e injeta esse arquivo sozinho.
#   4. Na primeira vez que a tela de impressão for aberta no celular, o app
#      Zebra Browser Print vai pedir permissão pra esse site — precisa aceitar.
# ─────────────────────────────────────────────────────────────────────────────
def _browserprint_js() -> str:
    try:
        with open("browserprint.js", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def gerar_zpl_etiqueta(info: dict) -> str:
    """Monta o ZPL de uma etiqueta de preço simples: produto, código de barras
    e preço. Ajuste as posições/tamanhos (^FO, ^A0) se a etiqueta sair cortada
    ou desalinhada na sua impressora/rolo de etiqueta específico.
    info precisa ter: Produto, CodBarra, PrecoTxt (preço já formatado como texto,
    já que o preço varia por loja — veja PrecoPorLoja)."""
    produto = str(info.get("Produto", "") or "")[:40].replace("^", "").replace("~", "")
    codigo_barra = str(info.get("CodBarra", "") or "").strip()
    preco_txt = str(info.get("PrecoTxt", "") or "-")
    return (
        "^XA\n"
        "^PW600\n"
        "^CF0,28\n"
        f"^FO20,20^FB560,2,0,L^FD{produto}^FS\n"
        "^BY2,2,80\n"
        f"^FO20,90^BCN,80,Y,N,N^FD{codigo_barra}^FS\n"
        "^CF0,55\n"
        f"^FO20,190^FD{preco_txt}^FS\n"
        "^XZ\n"
    )


def botao_imprimir_zebra(info: dict):
    js_sdk = _browserprint_js()
    if not js_sdk:
        st.caption(
            "🖨️ Impressão Zebra indisponível: falta o arquivo `browserprint.js` "
            "(SDK oficial da Zebra) na raiz do repositório — ver LEIA-ME."
        )
        return

    zpl = gerar_zpl_etiqueta(info)
    zpl_js = json.dumps(zpl)  # string já escapada e segura pra colar dentro do JS

    html = f"""
    <script>{js_sdk}</script>
    <button id="btnImprimirZebra" style="
        width:100%; padding:10px; border-radius:8px; border:none;
        background-color:{COR_PRIMARIA}; color:white; font-weight:600;
        font-size:15px; cursor:pointer;">
        🖨️ Imprimir Etiqueta (Zebra)
    </button>
    <div id="statusImpressaoZebra" style="margin-top:8px; font-family:sans-serif; font-size:13px;"></div>
    <script>
    (function() {{
        var status = document.getElementById('statusImpressaoZebra');
        document.getElementById('btnImprimirZebra').addEventListener('click', function() {{
            status.innerText = '🔎 Procurando impressora...';
            try {{
                BrowserPrint.getDefaultDevice('printer', function(printer) {{
                    if (!printer) {{
                        status.innerText = '❌ Nenhuma impressora encontrada. Abra o app Zebra Browser Print e confira se a ZQ630 Plus está pareada e definida como padrão.';
                        return;
                    }}
                    status.innerText = '📤 Enviando pra ' + printer.name + '...';
                    printer.send({zpl_js}, function() {{
                        status.innerText = '✅ Etiqueta enviada pra impressora!';
                    }}, function(err) {{
                        status.innerText = '❌ Erro ao enviar: ' + err;
                    }});
                }}, function(err) {{
                    status.innerText = '❌ Erro ao localizar impressora (o app Zebra Browser Print está aberto/instalado?): ' + err;
                }});
            }} catch (e) {{
                status.innerText = '❌ Erro: ' + e;
            }}
        }});
    }})();
    </script>
    """
    components.html(html, height=110)


def gerar_pdf_ronda(df_erros: pd.DataFrame, loja_ronda: str) -> bytes:
    """Gera um PDF-checklist (não etiquetas prontas) com os produtos marcados
    como 'preço errado na gôndola' durante a ronda, pra quem está na frente
    da máquina revisar e reimprimir as etiquetas certas. df_erros vem direto
    da tabela no Postgres (buscar_erros_ronda)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    estilos = getSampleStyleSheet()
    historia = []

    historia.append(Paragraph("Ronda de Preços — Produtos com Erro", estilos["Title"]))
    historia.append(Paragraph(f"Loja: {loja_ronda}", estilos["Heading2"]))
    historia.append(Paragraph(f"Gerado em: {data_hora_brasilia()}", estilos["Normal"]))
    historia.append(Spacer(1, 0.6 * cm))

    cabecalho = ["Hora", "Produto", "Código", "Cód. Barra", "Preço no sistema", "Observação"]
    linhas = [cabecalho]
    for _, e in df_erros.iterrows():
        linhas.append([
            Paragraph(str(e.get("hora_texto", "-") or "-"), estilos["Normal"]),
            Paragraph(str(e.get("produto", "-") or "-"), estilos["Normal"]),
            Paragraph(str(e.get("codigo", "-") or "-"), estilos["Normal"]),
            Paragraph(str(e.get("codigo_barra", "-") or "-"), estilos["Normal"]),
            Paragraph(str(e.get("preco_sistema", "-") or "-"), estilos["Normal"]),
            Paragraph(str(e.get("observacao", "") or "-"), estilos["Normal"]),
        ])

    tabela = Table(
        linhas,
        colWidths=[2.0 * cm, 5.5 * cm, 2.0 * cm, 3.0 * cm, 3.0 * cm, 4.0 * cm],
        repeatRows=1,
    )
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D6218C")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F2F6")]),
    ]))
    historia.append(tabela)
    historia.append(Spacer(1, 0.6 * cm))
    historia.append(Paragraph(f"Total de itens: {len(df_erros)}", estilos["Normal"]))

    doc.build(historia)
    buffer.seek(0)
    return buffer.getvalue()


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
if "loja_ronda" not in st.session_state:
    st.session_state.loja_ronda = LOJAS_NOMES[0]

if erp_ativo():
    _garantir_tabela_ronda()

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

            # st.form: captura todos os campos juntos no clique do botão, sem
            # depender do usuário apertar Enter em cada campo antes (era essa a
            # causa do "Senha incorreta" — o clique lia o valor antigo/vazio).
            with st.form("form_login", clear_on_submit=False):
                st.markdown(
                    f"<span style='color:{COR_LABEL_USUARIO};font-weight:600;'>👤 Usuário de acesso:</span>",
                    unsafe_allow_html=True,
                )
                usuario = st.text_input(
                    "Usuário de acesso", label_visibility="collapsed", placeholder="Digite seu nome",
                    autocomplete="username",
                )

                st.markdown(
                    f"<span style='color:{COR_LABEL_SENHA};font-weight:600;'>🔑 Senha de acesso:</span>",
                    unsafe_allow_html=True,
                )
                # autocomplete="current-password" avisa o navegador que é login
                # (não cadastro) — sem isso, o Chrome sugere "criar senha forte"
                # a cada acesso, porque o padrão do Streamlit pra campo de senha
                # é "new-password".
                senha = st.text_input(
                    "Senha de acesso", type="password", label_visibility="collapsed",
                    autocomplete="current-password",
                )

                st.write("")
                entrar = st.form_submit_button(
                    "Entrar no Sistema", type="primary", use_container_width=True
                )

            if entrar:
                if not usuario.strip():
                    st.error("Informe o usuário.")
                elif senha.strip() != SENHA_ACESSO:
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

    st.divider()
    st.markdown("**🚩 Ronda de preços**")
    st.session_state.loja_ronda = st.selectbox(
        "Loja desta ronda:", LOJAS_NOMES,
        index=LOJAS_NOMES.index(st.session_state.loja_ronda),
        key="select_loja_ronda",
    )
    # Vem direto do banco (não de session_state) — não some se a página recarregar.
    df_erros_loja = buscar_erros_ronda(st.session_state.loja_ronda) if erp_ativo() else pd.DataFrame()
    if df_erros_loja is not None and not df_erros_loja.empty:
        st.caption(f"🚩 {len(df_erros_loja)} produto(s) marcado(s) com erro de preço nesta loja")
        pdf_bytes = gerar_pdf_ronda(df_erros_loja, st.session_state.loja_ronda)
        st.download_button(
            "📄 Gerar PDF da ronda",
            data=pdf_bytes,
            file_name=f"ronda_precos_{st.session_state.loja_ronda.replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        if st.button("✅ Marcar como resolvidos (já impressos)", use_container_width=True):
            marcar_erros_resolvidos(st.session_state.loja_ronda)
            st.rerun()
    else:
        st.caption("Nenhum produto marcado com erro de preço nesta loja.")

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
if "ultimo_codigo_auto" not in st.session_state:
    # guarda o último código já buscado automaticamente pela câmera, pra não
    # repetir a busca (e duplicar o histórico) a cada rerun sem uma foto nova.
    st.session_state.ultimo_codigo_auto = None

# Câmera/entrada ficam numa coluna central estreita — só as tabelas de resultado
# usam a largura toda da tela (é o vídeo da câmera que fica gigante em layout wide).
codigo_auto = None              # só tem valor quando é um código NOVO (pra gravar no histórico)
codigo_lido_nesta_rodada = None  # tem valor sempre que a foto decodificou algo, novo ou repetido
col_busca_esq, col_busca_meio, col_busca_dir = st.columns([1, 2, 1])
with col_busca_meio:
    st.markdown("**📷 Fotografar o código de barras**")
    if _TEM_CAMERA_TRASEIRA:
        st.caption("Toque no vídeo pra capturar (já abre na câmera traseira).")
        foto = back_camera_input(key="camera_barra")
    else:
        foto = st.camera_input("Fotografar o código de barras", label_visibility="collapsed")

    if foto is not None:
        codigos_encontrados = decodificar_codigo_barra(foto.getvalue())
        if codigos_encontrados:
            codigo_lido = codigos_encontrados[0]
            codigo_lido_nesta_rodada = codigo_lido
            st.session_state.codigo_barra_atual = codigo_lido
            st.success(f"✅ Código lido: **{codigo_lido}**")
            if len(codigos_encontrados) > 1:
                st.caption("Outros códigos detectados na mesma foto: " + ", ".join(codigos_encontrados[1:]))
            if codigo_lido != st.session_state.ultimo_codigo_auto:
                # código novo (foto nova ou primeira leitura) — só isso conta pro histórico
                st.session_state.ultimo_codigo_auto = codigo_lido
                codigo_auto = codigo_lido
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

    buscar_manual = st.button("🔎 Buscar produto", type="primary", use_container_width=True)

def mostrar_resultado(codigo_busca: str, registrar_historico: bool):
    # Função única pra exibir o resultado — chamada tanto pela leitura automática
    # da câmera quanto pelo botão manual. registrar_historico=False evita duplicar
    # linha no histórico quando a MESMA foto é reprocessada em reruns seguidos
    # (o resultado sempre aparece na tela; só o histórico não duplica).
    st.session_state.codigo_barra_atual = codigo_busca
    try:
        with st.spinner("Consultando em todas as lojas..."):
            info = buscar_produto_todas_lojas(codigo_busca)
    except Exception as e:
        st.error(f"Erro ao consultar o produto: {e}")
        return

    if info is not None:
        st.divider()
        st.markdown(f"### {info['Produto']}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Código do Produto", info["Codigo"] if info["Codigo"] is not None else "-")
        col2.metric("Cód. Barra", info["CodBarra"])
        col3.metric("Estoque Total (todas as lojas)", f"{info['EstoqueTotal']:.0f}")

        # Lojas em LINHA e Estoque/Preço em COLUNA — cabe na tela do celular sem
        # rolar pros lados (o formato anterior, loja por coluna, ficava cortado
        # no mobile com só 4 das 8 lojas visíveis).
        linhas_tabela = [
            {"Loja": loja, "📦 Estoque": info["EstoquePorLoja"][loja], "💰 Preço": preco_para_texto(info["PrecoPorLoja"][loja])}
            for loja in LOJAS_NOMES
        ]
        linhas_tabela.append({"Loja": "Total", "📦 Estoque": info["EstoqueTotal"], "💰 Preço": ""})
        tabela_combinada = pd.DataFrame(linhas_tabela).set_index("Loja")
        st.dataframe(tabela_combinada, use_container_width=True)

        # Preço varia por loja — escolhe de qual loja sai o preço impresso na etiqueta.
        st.markdown("**🖨️ Imprimir etiqueta de preço (Zebra ZQ630 Plus)**")
        loja_etiqueta = st.selectbox(
            "Preço da loja para a etiqueta:", LOJAS_NOMES, key="loja_etiqueta_impressao"
        )
        botao_imprimir_zebra({
            "Produto": info["Produto"],
            "CodBarra": info["CodBarra"],
            "PrecoTxt": preco_para_texto(info["PrecoPorLoja"][loja_etiqueta]),
        })

        # ── Ronda: marcar preço errado na gôndola ─────────────────────────
        st.markdown("**🚩 Preço errado na gôndola?**")
        st.caption(
            f"Loja da ronda: **{st.session_state.loja_ronda}** "
            "(troque no menu lateral se precisar)"
        )
        with st.form(key=f"form_erro_ronda_{codigo_busca}", clear_on_submit=True):
            observacao = st.text_area(
                "Observação (opcional):", placeholder="Ex: etiqueta mostra R$ 5,99, sistema tem R$ 7,49",
                height=70,
            )
            marcar_erro = st.form_submit_button(
                "🚩 Registrar erro nesta loja", use_container_width=True
            )
        if marcar_erro:
            preco_sistema = info["PrecoPorLoja"].get(st.session_state.loja_ronda)
            try:
                salvar_erro_ronda(
                    loja=st.session_state.loja_ronda,
                    usuario=st.session_state.usuario_logado,
                    produto=info["Produto"],
                    codigo=info["Codigo"],
                    codigo_barra=info["CodBarra"],
                    preco_sistema_txt=preco_para_texto(preco_sistema),
                    observacao=observacao.strip(),
                )
                buscar_erros_ronda.clear()
                st.success("🚩 Marcado e salvo no banco! Vai aparecer no PDF da ronda (menu lateral).")
            except Exception as e:
                st.error(f"❌ Não deu pra salvar no banco agora: {e}")

        if registrar_historico:
            base_hist = {
                "Hora": data_hora_brasilia(),
                "Usuário": st.session_state.usuario_logado,
                "Produto": info["Produto"],
                "Código": info["Codigo"],
                "Cód. Barra": info["CodBarra"],
            }
            linha_hist = {
                **base_hist,
                "Estoque": {**info["EstoquePorLoja"], "Total": info["EstoqueTotal"]},
                "Preco": {loja: preco_para_texto(v) for loja, v in info["PrecoPorLoja"].items()},
            }
            st.session_state.historico_scans.insert(0, linha_hist)
    else:
        st.error(f"❌ Nenhum produto encontrado com o código **{codigo_busca}**.")
        sugestoes = buscar_produtos_parecidos(codigo_busca)
        if sugestoes is not None and not sugestoes.empty:
            st.caption("Produtos com código de barra parecido:")
            st.dataframe(sugestoes, use_container_width=True, hide_index=True)


if buscar_manual and not codigo_manual.strip():
    st.error("Digite ou fotografe um código de barra antes de buscar.")
elif codigo_lido_nesta_rodada:
    # Câmera leu um código nesta mesma execução — mostra o resultado NA HORA,
    # sem esperar clique nenhum. Só grava no histórico se for código novo.
    mostrar_resultado(codigo_lido_nesta_rodada, registrar_historico=bool(codigo_auto))
elif buscar_manual:
    mostrar_resultado(codigo_manual.strip(), registrar_historico=True)

if st.session_state.historico_scans:
    st.divider()
    st.subheader("📋 Histórico desta sessão")

    # Cada consulta vira um cartão dobrável, com loja em LINHA (não em coluna) —
    # mesmo motivo do resultado principal: no celular, 8 lojas em coluna cortam a tela.
    for h in st.session_state.historico_scans:
        titulo = f"{h.get('Hora', '')} — {h.get('Produto', '-')} (Cód. {h.get('Código', '-')})"
        with st.expander(titulo):
            st.caption(f"Usuário: {h.get('Usuário', '-')} · Cód. Barra: {h.get('Cód. Barra', '-')}")
            estoque_h = h.get("Estoque", {})
            preco_h = h.get("Preco", {})
            linhas = [
                {"Loja": loja, "📦 Estoque": estoque_h.get(loja, ""), "💰 Preço": preco_h.get(loja, "")}
                for loja in LOJAS_NOMES
            ]
            linhas.append({"Loja": "Total", "📦 Estoque": estoque_h.get("Total", ""), "💰 Preço": ""})
            st.dataframe(pd.DataFrame(linhas).set_index("Loja"), use_container_width=True)
