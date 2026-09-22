"""PDF de apresentação. Recebe o resultado existente, sem alterar a simulação."""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape


def numero(valor):
    resultado = Decimal(str(valor))
    if not resultado.is_finite():
        raise ValueError("Valor não finito no relatório")
    return resultado


def dinheiro(valor):
    return "R$ " + f"{numero(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def percentual(valor):
    return f"{numero(valor) * 100:.2f}".replace(".", ",") + "%"


def gerar_pdf(cliente, simulacao, compradores):
    # Import tardio: uma falha na dependência de PDF não impede o painel de iniciar.
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    stream = BytesIO()
    azul = colors.HexColor("#142746")
    styles = {nome: ParagraphStyle(nome, fontName="Helvetica-Bold" if nome in ("titulo", "sub") else "Helvetica",
              fontSize=tamanho, leading=entrelinha, textColor=azul, spaceAfter=8, alignment=TA_LEFT)
              for nome, tamanho, entrelinha in [("titulo", 19, 23), ("sub", 12, 16), ("body", 10, 14), ("small", 8, 11)]}
    story = []
    width = A4[0] - 112
    def p(texto, estilo="body"):
        return Paragraph(texto, styles[estilo])
    def add(texto, estilo="body"):
        story.append(p(texto, estilo))
    def tabela(linhas, larguras):
        t = Table([[p(escape(str(c)).replace("\n", "<br/>"), "small") for c in linha] for linha in linhas], colWidths=larguras, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0), colors.HexColor("#EDF1F6")),
                              ("VALIGN",(0,0),(-1,-1),"TOP"), ("LINEBELOW",(0,0),(-1,-1),.4,colors.HexColor("#D8E0EA")),
                              ("TOPPADDING",(0,0),(-1,-1),7), ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.extend([t, Spacer(1,12)])
    s = simulacao
    h, prem = s["hibrido"], s["premissas"]
    delta = numero(s["diferenca_vs_simples"])
    receita = numero(s["base_calculo"]["receita"])
    ibs, cbs = numero(prem["ibs_aliquota"]), numero(prem["cbs_aliquota"])
    creditos = sum(numero(h[chave]) for chave in ("ibs_creditos_automaticos", "cbs_creditos_automaticos", "ibs_creditos_documentados", "cbs_creditos_documentados"))
    if delta > 0:
        sugestao = "considerar o híbrido, que apresenta economia neste cenário, desde que os créditos e as premissas sejam confirmados e os custos de implantação não eliminem o benefício."
    elif delta < 0:
        sugestao = "manter o Simples Nacional como referência do planejamento e considerar o híbrido se os benefícios comerciais compensarem o custo adicional indicado."
    else:
        sugestao = "comparar os custos operacionais e os efeitos comerciais antes de optar: os regimes apresentam o mesmo total neste cenário."
    add("Orientação tributária para 2027", "titulo")
    add(escape(cliente["razao_social"]), "sub")
    add(f'CNPJ {escape(cliente["cnpj"])} | Período-base: {escape(s["periodo"])}', "small")
    add("<b>Nossa recomendação:</b> " + sugestao)
    add("<b>A decisão final cabe ao empresário.</b>")
    add("Comparação da simulação", "sub")
    tabela([["Indicador", "Valor"], ["Receita utilizada", dinheiro(receita)],
            ["Simples: DAS histórico repetido", dinheiro(s["simples_puro"]["total"])],
            ["Híbrido: total do cenário", dinheiro(h["total"])],
            ["Economia potencial" if delta > 0 else "Custo adicional" if delta < 0 else "Diferença", dinheiro(abs(delta))]], [width*.65,width*.35])
    add("Composição do híbrido", "sub")
    tabela([["DAS remanescente", "IBS líquido", "CBS líquido"],
            [dinheiro(h["das_remanescente"]),dinheiro(h["ibs_liquido"]),dinheiro(h["cbs_liquido"])]],[width/3]*3)
    add(f'Premissas: IBS {percentual(ibs)}; CBS {percentual(cbs)}; parcela remanescente do DAS {percentual(prem["percentual_das_remanescente"])}; créditos utilizados {dinheiro(creditos)}.', "small")
    add("Cenário de planejamento: repete receita e DAS históricos. Alíquotas, composição do DAS e créditos dependem de conferência para a opção por 2027; não representam economia garantida.", "small")
    add("O que deve orientar a escolha", "sub")
    add("<b>Tributação:</b> carga efetiva e créditos admitidos.<br/><b>Clientes:</b> impacto do crédito nas cotações e renovações.<br/><b>Resultado:</b> preservar margem, caixa e capacidade de atendimento.")
    add("O crédito do comprador não reduz o imposto desta empresa. Uma vantagem comercial isolada não determina o melhor regime.", "small")

    story.append(PageBreak())
    add("Principais compradores e manutenção dos contratos", "titulo")
    add(f'Período-base: {escape(s["periodo"])} | Até três maiores CNPJs com movimento identificado.', "small")
    top = sorted([x for x in compradores if numero(x["valor"]) > 0], key=lambda x: (-numero(x["valor"]), x["cnpj"]))[:3]
    def credito(v):
        return (numero(v)*ibs).quantize(Decimal(".01"))+(numero(v)*cbs).quantize(Decimal(".01"))
    if top:
        linhas = [["Comprador / CNPJ", "Faturamento", "Crédito hipotético¹"]]
        for x in top:
            linhas.append([x["razao_social"] + "\n" + x["cnpj"], dinheiro(x["valor"]), dinheiro(credito(x["valor"]))])
        tabela(linhas, [width*.48,width*.26,width*.26])
        total = sum(numero(x["valor"]) for x in top)
        if receita > 0 and total <= receita:
            add(f'Esses compradores representam {percentual(total/receita)} da receita utilizada na simulação.', "small")
        else:
            add("A participação na receita não foi calculada: as bases de movimentação e de receita precisam ser conciliadas.", "small")
    else:
        add("Não há compradores com movimentação individual identificada para este período. A relação comercial poderá ser avaliada após a inclusão dos documentos correspondentes.")
    add("¹ Estimativa sobre volume equivalente ao histórico, aplicando as alíquotas do cenário separadamente. Depende do regime do adquirente e do crédito legalmente admitido; não é crédito efetivo, retroativo ou perda comprovada. Comprar do Simples não significa necessariamente crédito zero.", "small")
    add("Argumento principal: comparar o custo final", "sub")
    add('“Vamos comparar o preço total menos o crédito que vocês realmente podem aproveitar. Se nossa prestação custa menos, o crédito maior de outro fornecedor pode não compensar a diferença.”')
    if top:
        v = numero(top[0]["valor"]); c = credito(v)
        add("Exemplo ilustrativo do maior comprador", "sub")
        add(f'Um concorrente com preço-base de <b>{dinheiro(v)}</b>, mais <b>{dinheiro(c)}</b> de tributos, cobra {dinheiro(v+c)}. Se o comprador aproveitar integralmente esse crédito, seu custo volta a {dinheiro(v)}: empata com um fornecedor que cobre esse valor total, mesmo supondo crédito próprio zero.', "small")
    add("Como conduzir a negociação", "sub")
    add("Confirmar o crédito utilizável com o fiscal do comprador; comparar preço, prazo e qualidade; negociar descontos dentro da margem; registrar a escolha do empresário.")
    add('<a href="https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-normaatualizada-pl.html">Base legal: LC 214/2025, arts. 41 e 47, § 9º.</a> Fontes dos valores: simulação e movimentações disponíveis no sistema para o período. Sem garantia de manutenção de contratos.', "small")
    def rodape(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica",8); canvas.setFillColor(azul)
        canvas.drawString(56,30,"Motor Tributário | " + datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"))
        canvas.drawRightString(A4[0]-56,30,str(doc.page)); canvas.restoreState()
    SimpleDocTemplate(stream, pagesize=A4, leftMargin=56,rightMargin=56,topMargin=45,bottomMargin=48,
                      title="Orientação tributária - " + cliente["razao_social"], author="Motor Tributário").build(story,onFirstPage=rodape,onLaterPages=rodape)
    return stream.getvalue()
