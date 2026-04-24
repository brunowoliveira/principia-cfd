"""
Calculadora de Parcelamento — Principia Crédito PJ
Streamlit web app para o time comercial calcular propostas de renegociação.

Instalar:  pip install streamlit reportlab pillow python-dateutil
Rodar:     streamlit run app_cfd.py
"""
import io, os, base64
from datetime import date
from dateutil.relativedelta import relativedelta

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage,
)

# ── Configuração da página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Calculadora de Parcelamento — Principia",
    page_icon="💙",
    layout="centered",
)

# ── Identidade visual (CSS) ────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* Header */
    .main-header {
        background: linear-gradient(135deg, #0B4FA0 0%, #0273FF 60%, #29A3D4 100%);
        border-radius: 12px;
        padding: 28px 32px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(2,115,255,0.25);
    }
    .main-header h1 { color: white; font-size: 1.6rem; font-weight: 700; margin: 0 0 4px 0; }
    .main-header p  { color: #A8D4FF; font-size: 0.85rem; margin: 0; }

    /* Cards de plano */
    .plan-card {
        background: #F0F7FF;
        border: 2px solid #0273FF;
        border-radius: 10px;
        padding: 18px 22px;
        margin: 12px 0;
    }
    .plan-card h3 { color: #0B4FA0; font-size: 1rem; font-weight: 700; margin: 0 0 8px 0; }
    .plan-card .pmt-value { color: #0273FF; font-size: 1.8rem; font-weight: 700; }
    .plan-card .pmt-label { color: #546E7A; font-size: 0.78rem; }
    .plan-card .approved  { color: #1B5E20; background: #E8F5E9;
                             border-radius: 4px; padding: 2px 8px;
                             font-size: 0.75rem; font-weight: 600; display: inline-block; }
    .plan-card .rejected  { color: #B71C1C; background: #FFEBEE;
                             border-radius: 4px; padding: 2px 8px;
                             font-size: 0.75rem; font-weight: 600; display: inline-block; }

    /* Card rejeitado */
    .plan-rejected {
        background: #FFF8E1;
        border: 2px solid #F57C00;
        border-radius: 10px;
        padding: 18px 22px;
        margin: 12px 0;
    }
    .plan-rejected h3 { color: #E65100; font-size: 1rem; font-weight: 700; margin: 0 0 8px 0; }

    /* Tabela de parcelas */
    .parcelas-table th { background: #0273FF; color: white; padding: 8px 12px; font-size: 0.82rem; }
    .parcelas-table td { padding: 7px 12px; font-size: 0.82rem; border-bottom: 1px solid #E0E0E0; }
    .parcelas-table tr:nth-child(even) td { background: #F4F7FB; }

    /* Inputs */
    .stNumberInput label, .stDateInput label, .stTextInput label { font-weight: 500; color: #2C3E50; }

    /* Botão PDF */
    .stDownloadButton button {
        background: linear-gradient(135deg, #0B4FA0, #0273FF) !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        border: none !important;
        font-size: 0.9rem !important;
    }

    /* Aviso de contato */
    .contact-warning {
        background: #FFF3E0;
        border-left: 5px solid #F57C00;
        border-radius: 6px;
        padding: 16px 20px;
        margin: 16px 0;
    }
    .contact-warning b { color: #E65100; }

    /* Divider */
    hr.styled { border: none; border-top: 2px solid #E8F1FF; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)

# ── Constantes ─────────────────────────────────────────────────────────────────
P_BLUE    = colors.HexColor("#0273FF")
P_BLUE_DK = colors.HexColor("#0B4FA0")
P_BLUE_LT = colors.HexColor("#E8F1FF")
P_SLATE   = colors.HexColor("#2C3E50")
P_GREY    = colors.HexColor("#F4F7FB")
P_GREY_BD = colors.HexColor("#CBD5E0")
P_WHITE   = colors.white

# Logo: tenta mesma pasta do app (deploy Cloud), depois sobe um nível (local)
_dir = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = (
    os.path.join(_dir, "principia_branco.png")
    if os.path.exists(os.path.join(_dir, "principia_branco.png"))
    else os.path.join(_dir, "..", "logos", "principia_branco.png")
)

TAXA_A  = 3.5 / 100   # 3x
TAXA_B  = 5.0 / 100   # 6x
N_A, N_B = 3, 6
LIMITE_A = 0.15        # PMT ≤ 15% garantido médio
LIMITE_B = 0.10        # PMT ≤ 10% garantido médio

MESES_PT = ["","Janeiro","Fevereiro","Março","Abril","Maio","Junho",
            "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]


# ── Gerador de PDF (definido ANTES do código de UI para evitar NameError) ──────
def gerar_pdf_cfd(ies_nome, saldo_devedor, n, pmt, parcelas):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=10*mm,  bottomMargin=15*mm,
    )
    W = A4[0] - 40*mm

    def sty(font="Helvetica", size=10, color=P_SLATE, bold=False, align=TA_LEFT,
            leading=None, space_before=0, space_after=0):
        fn = "Helvetica-Bold" if bold else font
        return ParagraphStyle("_", fontName=fn, fontSize=size,
                               textColor=color, alignment=align,
                               leading=leading or size*1.4,
                               spaceBefore=space_before, spaceAfter=space_after)

    def P(txt, **kw): return Paragraph(txt, sty(**kw))

    story = []

    logo_cell = RLImage(LOGO_PATH, width=40*mm, height=13*mm) \
        if os.path.exists(LOGO_PATH) \
        else P("<b>principia</b>", size=16, color=P_WHITE, bold=True)

    hdr = Table([[
        logo_cell,
        P("PROPOSTA DE PARCELAMENTO<br/>"
          "<font size='9' color='#A8C8FF'>Crédito PJ — Principia Educação</font>",
          size=14, color=P_WHITE, bold=True),
        P(f"Emitida em:<br/><b>{date.today().strftime('%d/%m/%Y')}</b>",
          size=8, color=colors.HexColor("#A8C8FF"), align=TA_RIGHT),
    ]], colWidths=[45*mm, W-90*mm, 40*mm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), P_BLUE_DK),
        ("TOPPADDING",    (0,0),(-1,-1), 12),
        ("BOTTOMPADDING", (0,0),(-1,-1), 12),
        ("LEFTPADDING",   (0,0),(0,-1),  10),
        ("RIGHTPADDING",  (-1,0),(-1,-1),10),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 8*mm))

    story.append(P("IDENTIFICAÇÃO DA INSTITUIÇÃO", size=8,
                   color=colors.HexColor("#78909C"), bold=True, space_after=2))
    story.append(P(ies_nome, size=16, bold=True, color=P_BLUE_DK, space_after=1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=P_BLUE))
    story.append(Spacer(1, 6*mm))

    conf_tbl = Table([[
        P("SALDO DEVEDOR A RENEGOCIAR", size=8, color=colors.HexColor("#546E7A"), bold=True, align=TA_CENTER),
    ],[
        P(fmt_brl(saldo_devedor), size=26, bold=True, color=P_BLUE, align=TA_CENTER),
    ],[
        P(f"{n} parcelas mensais", size=9, color=colors.HexColor("#546E7A"), align=TA_CENTER),
    ]], colWidths=[W])
    conf_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), P_BLUE_LT),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("BOX",           (0,0),(-1,-1), 1.5, P_BLUE),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [6,6,6,6]),
    ]))
    story.append(conf_tbl)
    story.append(Spacer(1, 8*mm))

    story.append(P("PLANO DE PAGAMENTO", size=8, color=colors.HexColor("#78909C"),
                   bold=True, space_after=3))
    col_w = [W*0.15, W*0.45, W*0.40]
    rows = [[
        P("#", size=9, color=P_WHITE, bold=True, align=TA_CENTER),
        P("Data de Vencimento", size=9, color=P_WHITE, bold=True, align=TA_CENTER),
        P("Valor da Parcela", size=9, color=P_WHITE, bold=True, align=TA_RIGHT),
    ]]
    for num, dt, val in parcelas:
        rows.append([
            P(str(num), size=9, align=TA_CENTER),
            P(dt.strftime("%d/%m/%Y"), size=9, align=TA_CENTER),
            P(f"<b>{fmt_brl(val)}</b>", size=9, align=TA_RIGHT),
        ])
    tbl = Table(rows, colWidths=col_w)
    ts  = TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  P_BLUE),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("GRID",          (0,0),(-1,-1), 0.5, P_GREY_BD),
        ("LINEBELOW",     (0,0),(-1,0),  1.0, P_BLUE_DK),
    ])
    for i in range(1, len(rows)):
        if i % 2 == 0:
            ts.add("BACKGROUND", (0,i), (-1,i), P_GREY)
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

    cond_text = (
        "O abatimento das parcelas será realizado mensalmente por meio de dedução dos repasses "
        "devidos pela Principia à instituição. Na hipótese de o repasse ser insuficiente para "
        "cobrir o valor da parcela, a instituição deverá complementar o valor restante em até "
        "1 (um) dia útil após notificação. O atraso sujeitará a devedora a multa de 15% e "
        "juros de mora de 1% a.m. Este documento é uma proposta comercial — "
        "o Termo de Confissão de Dívida formal será providenciado pelo jurídico da Principia."
    )
    story.append(Table([[P(cond_text, size=7.5, color=colors.HexColor("#546E7A"))]],
                       colWidths=[W],
                       style=[("BACKGROUND",(0,0),(-1,-1),P_GREY),
                               ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
                               ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
                               ("BOX",(0,0),(-1,-1),0.5,P_GREY_BD)]))
    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=P_GREY_BD))
    story.append(Spacer(1, 2*mm))
    rod = Table([[
        P("Principia Educação  —  Crédito PJ / DCM", size=7.5,
          color=colors.HexColor("#546E7A")),
        P("bruno.oliveira@principia.net", size=7.5,
          color=colors.HexColor("#546E7A"), align=TA_RIGHT),
    ]], colWidths=[W*0.5, W*0.5])
    story.append(rod)
    doc.build(story)
    return buffer.getvalue()


def pmt_price(pv, r, n):
    """PMT sistema PRICE: pv em R$, r decimal, n meses."""
    if r == 0: return pv / n
    return round(pv * r / (1 - (1 + r) ** (-n)), 2)


def fmt_brl(v):
    s = f"{v:,.2f}".replace(",","X").replace(".",",").replace("X",".")
    return f"R$ {s}"


def parcelas_plano(pmt, n, data_primeiro):
    """Gera lista [(parcela, data, valor)] para o plano."""
    parcelas = []
    for i in range(n):
        dt = data_primeiro + relativedelta(months=i)
        parcelas.append((i+1, dt, pmt))
    return parcelas


# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>Calculadora de Parcelamento</h1>
    <p>Principia Crédito PJ — Proposta de Renegociação para IES</p>
</div>
""", unsafe_allow_html=True)

# ── Formulário de entrada ──────────────────────────────────────────────────────
with st.form("form_cfd"):
    st.markdown("#### 📋 Dados da Operação")

    col1, col2 = st.columns(2)
    with col1:
        nome_ies = st.text_input(
            "Nome da Instituição (IES)",
            placeholder="Ex: Instituto Florence de Ensino Superior",
        )
        saldo_devedor = st.number_input(
            "Saldo Devedor a Renegociar (R$)",
            min_value=0.01, value=100_000.00, step=1_000.00, format="%.2f",
        )
    with col2:
        garantido_medio = st.number_input(
            "Garantido Médio — Últimos 3 Meses (R$)",
            min_value=0.01, value=80_000.00, step=1_000.00, format="%.2f",
        )
        data_repasse = st.date_input(
            "Data do Repasse em Aberto",
            value=date.today(),
            help="Data do repasse que o parceiro deixaria de receber. "
                 "O 1º vencimento do parcelamento será o repasse seguinte (+ 1 mês).",
        )

    st.markdown("<small style='color:#546E7A'>O primeiro vencimento será o repasse imediatamente posterior à data informada.</small>",
                unsafe_allow_html=True)
    submitted = st.form_submit_button("🔢  Calcular Planos de Parcelamento", use_container_width=True)

# ── Cálculo e resultado ────────────────────────────────────────────────────────
if submitted:
    if not nome_ies.strip():
        st.error("Por favor, informe o nome da IES.")
        st.stop()
    if saldo_devedor <= 0 or garantido_medio <= 0:
        st.error("Os valores de saldo devedor e garantido médio devem ser positivos.")
        st.stop()

    data_repasse_dt = date.fromisoformat(str(data_repasse))
    primeiro_venc  = data_repasse_dt + relativedelta(months=1)
    pmt_a = pmt_price(saldo_devedor, TAXA_A, N_A)
    pmt_b = pmt_price(saldo_devedor, TAXA_B, N_B)

    st.session_state["cfd"] = {
        "nome_ies":       nome_ies.strip(),
        "saldo_devedor":  saldo_devedor,
        "garantido_medio":garantido_medio,
        "primeiro_venc":  primeiro_venc,
        "pmt_a":          pmt_a,
        "pmt_b":          pmt_b,
        "ok_a":           pmt_a <= LIMITE_A * garantido_medio,
        "ok_b":           pmt_b <= LIMITE_B * garantido_medio,
    }

if "cfd" in st.session_state:
    _r             = st.session_state["cfd"]
    nome_ies       = _r["nome_ies"]
    saldo_devedor  = _r["saldo_devedor"]
    garantido_medio= _r["garantido_medio"]
    primeiro_venc  = _r["primeiro_venc"]
    pmt_a          = _r["pmt_a"]
    pmt_b          = _r["pmt_b"]
    ok_a           = _r["ok_a"]
    ok_b           = _r["ok_b"]

    st.markdown("---")
    st.markdown(f"#### 📊 Resultados para **{nome_ies.strip()}**")
    st.markdown(
        f"<div style='color:#546E7A;font-size:0.85rem;margin-bottom:12px;'>"
        f"Saldo devedor: <b>{fmt_brl(saldo_devedor)}</b>  |  "
        f"Garantido médio: <b>{fmt_brl(garantido_medio)}</b>  |  "
        f"1º vencimento: <b>{primeiro_venc.strftime('%d/%m/%Y')}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

    plano_selecionado = None
    plano_n = None
    plano_pmt = None

    # ── Plano A: 3× ───────────────────────────────────────────────────────────
    if ok_a:
        limite_a_val = LIMITE_A * garantido_medio
        badge = '<span class="approved">✓ DISPONÍVEL</span>'
        parcelas_a = parcelas_plano(pmt_a, N_A, primeiro_venc)

        tbl_html = """<table class='parcelas-table' style='width:100%;border-collapse:collapse;'>
        <tr><th>#</th><th>Vencimento</th><th>Valor da Parcela</th></tr>"""
        for num, dt, val in parcelas_a:
            tbl_html += f"<tr><td>{num}</td><td>{dt.strftime('%d/%m/%Y')}</td><td><b>{fmt_brl(val)}</b></td></tr>"
        tbl_html += f"<tr><td colspan='2' style='text-align:right;font-weight:600;background:#E8F1FF;'>Total pago</td><td style='font-weight:700;background:#E8F1FF;'>{fmt_brl(pmt_a*N_A)}</td></tr>"
        tbl_html += "</table>"

        st.markdown(f"""
        <div class="plan-card">
            <h3>Plano A — {N_A}× parcelas mensais  {badge}</h3>
            <div class="pmt-value">{fmt_brl(pmt_a)}</div>
            <div class="pmt-label">por mês  ·  limite: {LIMITE_A*100:.0f}% do garantido ({fmt_brl(limite_a_val)})</div>
            <br/>
            {tbl_html}
        </div>
        """, unsafe_allow_html=True)

        plano_selecionado = "A"
        plano_n = N_A
        plano_pmt = pmt_a
        parcelas_export = parcelas_a

    else:
        excesso = pmt_a - LIMITE_A * garantido_medio
        st.markdown(f"""
        <div class="plan-rejected">
            <h3>Plano A — {N_A}× parcelas  <span class="rejected" style="background:#FFEBEE;color:#B71C1C;border-radius:4px;padding:2px 8px;font-size:0.75rem;">INDISPONÍVEL</span></h3>
            <p style='color:#546E7A;margin:4px 0;'>
                PMT calculado: <b>{fmt_brl(pmt_a)}</b>  ·
                Limite (15% garantido): <b>{fmt_brl(LIMITE_A * garantido_medio)}</b>  ·
                Excesso: <b style='color:#C62828'>{fmt_brl(excesso)}</b>
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ── Plano B: 6× ───────────────────────────────────────────────────────────
    if ok_b:
        limite_b_val = LIMITE_B * garantido_medio
        badge = '<span class="approved">✓ DISPONÍVEL</span>'
        parcelas_b = parcelas_plano(pmt_b, N_B, primeiro_venc)

        tbl_html = """<table class='parcelas-table' style='width:100%;border-collapse:collapse;'>
        <tr><th>#</th><th>Vencimento</th><th>Valor da Parcela</th></tr>"""
        for num, dt, val in parcelas_b:
            tbl_html += f"<tr><td>{num}</td><td>{dt.strftime('%d/%m/%Y')}</td><td><b>{fmt_brl(val)}</b></td></tr>"
        tbl_html += f"<tr><td colspan='2' style='text-align:right;font-weight:600;background:#E8F1FF;'>Total pago</td><td style='font-weight:700;background:#E8F1FF;'>{fmt_brl(pmt_b*N_B)}</td></tr>"
        tbl_html += "</table>"

        st.markdown(f"""
        <div class="plan-card">
            <h3>Plano B — {N_B}× parcelas mensais  {badge}</h3>
            <div class="pmt-value">{fmt_brl(pmt_b)}</div>
            <div class="pmt-label">por mês  ·  limite: {LIMITE_B*100:.0f}% do garantido ({fmt_brl(limite_b_val)})</div>
            <br/>
            {tbl_html}
        </div>
        """, unsafe_allow_html=True)

        if plano_selecionado is None:
            plano_selecionado = "B"
            plano_n = N_B
            plano_pmt = pmt_b
            parcelas_export = parcelas_b

    else:
        excesso = pmt_b - LIMITE_B * garantido_medio
        st.markdown(f"""
        <div class="plan-rejected">
            <h3>Plano B — {N_B}× parcelas  <span class="rejected" style="background:#FFEBEE;color:#B71C1C;border-radius:4px;padding:2px 8px;font-size:0.75rem;">INDISPONÍVEL</span></h3>
            <p style='color:#546E7A;margin:4px 0;'>
                PMT calculado: <b>{fmt_brl(pmt_b)}</b>  ·
                Limite (10% garantido): <b>{fmt_brl(LIMITE_B * garantido_medio)}</b>  ·
                Excesso: <b style='color:#C62828'>{fmt_brl(excesso)}</b>
            </p>
        </div>
        """, unsafe_allow_html=True)

    # ── Nenhum plano disponível ────────────────────────────────────────────────
    if not ok_a and not ok_b:
        st.markdown("""
        <div class="contact-warning">
            <b>⚠ Nenhum plano de parcelamento disponível para esta operação.</b><br/><br/>
            As parcelas calculadas excedem os limites mínimos de cobertura pelo garantido médio
            da instituição para os dois planos padrão.<br/><br/>
            👉 Por favor, entre em contato com <b>Bruno Oliveira (DCM)</b>
            para análise de condições especiais:<br/>
            <a href='mailto:bruno.oliveira@principia.net' style='color:#0273FF;'>
                bruno.oliveira@principia.net
            </a>
        </div>
        """, unsafe_allow_html=True)

    # ── Botão de exportação PDF ────────────────────────────────────────────────
    elif plano_selecionado is not None:
        st.markdown("---")
        st.markdown("#### 📄 Exportar Proposta")

        # Escolha do plano para PDF
        planos_disponiveis = []
        if ok_a: planos_disponiveis.append(f"Plano A — {N_A}× de {fmt_brl(pmt_a)}")
        if ok_b: planos_disponiveis.append(f"Plano B — {N_B}× de {fmt_brl(pmt_b)}")

        plano_escolhido = st.radio(
            "Selecione o plano para a proposta PDF:",
            planos_disponiveis, horizontal=True,
        )

        # Determinar parâmetros do plano escolhido
        if "Plano A" in plano_escolhido:
            exp_n, exp_pmt = N_A, pmt_a
            exp_parcelas = parcelas_plano(pmt_a, N_A, primeiro_venc)
        else:
            exp_n, exp_pmt = N_B, pmt_b
            exp_parcelas = parcelas_plano(pmt_b, N_B, primeiro_venc)

        # Gerar PDF
        pdf_bytes = gerar_pdf_cfd(
            ies_nome=nome_ies.strip(),
            saldo_devedor=saldo_devedor,
            n=exp_n,
            pmt=exp_pmt,
            parcelas=exp_parcelas,
        )

        st.download_button(
            label="⬇  Baixar Proposta em PDF",
            data=pdf_bytes,
            file_name=f"Proposta_Parcelamento_{nome_ies.strip().replace(' ','_')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
