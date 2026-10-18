"""PDF objetivo da apuração IBS/CBS. Recebe o resultado existente, sem alterar a simulação."""
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


def cnpj_fmt(cnpj):
    d = "".join(c for c in str(cnpj) if c.isdigit())
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else str(cnpj)


def _ordem_data(texto):
    partes = str(texto or "").split("/")
    return (partes[2], partes[1], partes[0]) if len(partes) == 3 else ("", "", str(texto))


def gerar_pdf(cliente, simulacao, compradores, notas_entrada=None, observacoes=None):
    # Import tardio: uma falha na dependência de PDF não impede o painel de iniciar.
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    stream = BytesIO()
    azul = colors.HexColor("#142746")
    cinza = colors.HexColor("#EDF1F6")
    styles = {nome: ParagraphStyle(nome, fontName="Helvetica-Bold" if nome in ("titulo", "sub", "smallb", "smallbr") else "Helvetica",
              fontSize=tamanho, leading=entrelinha, textColor=azul, spaceAfter=6,
              alignment=TA_RIGHT if nome.endswith("r") and nome not in ("titulo",) else TA_LEFT)
              for nome, tamanho, entrelinha in [("titulo", 16, 20), ("sub", 11.5, 15), ("body", 9.5, 13),
                                               ("small", 8, 10.5), ("smallr", 8, 10.5), ("smallb", 8, 10.5), ("smallbr", 8, 10.5)]}
    story = []
    width = A4[0] - 96

    def p(texto, estilo="body"):
        return Paragraph(texto, styles[estilo])

    def add(texto, estilo="body"):
        story.append(p(texto, estilo))

    def tabela(linhas, larguras, direita=(), total=False):
        """linhas: listas de texto; colunas em `direita` alinham à direita; última linha em negrito se total."""
        corpo = []
        for i, linha in enumerate(linhas):
            negrito = i == 0 or (total and i == len(linhas) - 1)
            corpo.append([p(escape(str(c)).replace("\n", "<br/>"),
                            ("smallb" if negrito else "small") + ("r" if j in direita else ""))
                          for j, c in enumerate(linha)])
        t = Table(corpo, colWidths=larguras, repeatRows=1)
        estilo = [("BACKGROUND", (0, 0), (-1, 0), cinza), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LINEBELOW", (0, 0), (-1, -1), .4, colors.HexColor("#D8E0EA")),
                  ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if total:
            estilo.append(("BACKGROUND", (0, -1), (-1, -1), cinza))
        t.setStyle(TableStyle(estilo))
        story.extend([t, Spacer(1, 10)])

    s = simulacao
    h, prem = s["hibrido"], s["premissas"]
    delta = numero(s["diferenca_vs_simples"])
    receita = numero(s["base_calculo"]["receita"])
    das = numero(s["base_calculo"]["das_original"])
    ibs, cbs = numero(prem["ibs_aliquota"]), numero(prem["cbs_aliquota"])
    pct_das = numero(prem["percentual_das_remanescente"])
    base_credito = numero(s.get("creditos_fornecedores", {}).get("base_compras_fornecedores_regulares", 0))
    cred_ibs_doc, cred_cbs_doc = numero(h["ibs_creditos_documentados"]), numero(h["cbs_creditos_documentados"])
    cred_ibs = numero(h["ibs_creditos_automaticos"]) + cred_ibs_doc
    cred_cbs = numero(h["cbs_creditos_automaticos"]) + cred_cbs_doc
    periodo = escape(s["periodo"])

    if delta > 0:
        sugestao = "considerar o híbrido, que apresenta economia neste cenário, desde que os créditos e as premissas sejam confirmados e os custos de implantação não eliminem o benefício."
    elif delta < 0:
        sugestao = "manter o Simples Nacional como referência do planejamento e considerar o híbrido se os benefícios comerciais compensarem o custo adicional indicado."
    else:
        sugestao = "comparar os custos operacionais e os efeitos comerciais antes de optar: os regimes apresentam o mesmo total neste cenário."

    # ---------------------------------------------------------------- resumo
    anexo_v = prem.get("anexo_simples") == "V"
    add(f"Apuração IBS/CBS — {periodo} — Simples pelo " + ("Anexo V" if anexo_v else "Anexo III (declarado)"), "titulo")
    add(f'<b>{escape(cliente["razao_social"])}</b> | CNPJ {escape(cnpj_fmt(cliente["cnpj"]))}', "small")
    add(f"<b>Resultado:</b> {'economia' if delta > 0 else 'custo adicional' if delta < 0 else 'diferença'} de "
        f"<b>{dinheiro(abs(delta))}</b> no híbrido em relação ao Simples. Recomendação: {sugestao} "
        "<b>A decisão final cabe ao empresário.</b>")

    add("1. Resumo: como se chega ao imposto", "sub")
    ibs_debito, cbs_debito = numero(h["ibs_debito"]), numero(h["cbs_debito"])
    linhas = [
        ["", "Cálculo", "Valor"],
        *([["   Receita total do período", "PGDAS", dinheiro(s["base_calculo"]["receita_total"])],
           ["   (−) Exportação de serviços", "imune a IBS/CBS", dinheiro(s["base_calculo"]["receita_exportacao"])]]
          if numero(s["base_calculo"].get("receita_exportacao", 0)) > 0 else []),
        ["A  Receita do período (base do débito)", "PGDAS" + (" − exportação" if numero(s["base_calculo"].get("receita_exportacao", 0)) > 0 else ""), dinheiro(receita)],
        ["B  Débito de IBS", f"A × {percentual(ibs)}", dinheiro(ibs_debito)],
        ["C  Débito de CBS", f"A × {percentual(cbs)}", dinheiro(cbs_debito)],
        ["D  Compras e serviços tomados com crédito", "Quadro 2", dinheiro(base_credito)],
        ["E  Crédito de IBS", f"D × {percentual(ibs)}" + (" + documentados" if cred_ibs_doc else ""), dinheiro(cred_ibs)],
        ["F  Crédito de CBS", f"D × {percentual(cbs)}" + (" + documentados" if cred_cbs_doc else ""), dinheiro(cred_cbs)],
        ["G  IBS a recolher", "B − E", dinheiro(h["ibs_liquido"])],
        ["H  CBS a recolher", "C − F", dinheiro(h["cbs_liquido"])],
        *([["   DAS declarado no PGDAS (Anexo III)", "PGDAS", dinheiro(s["base_calculo"]["das_declarado"])],
           ["   (+) Diferença para o Anexo V", "fator r < 28% (seção 5)", dinheiro(s["base_calculo"]["ajuste_anexo_v"])]]
          if anexo_v else []),
        ["I  DAS remanescente", f"DAS {dinheiro(das)} × {percentual(pct_das)}", dinheiro(h["das_remanescente"])],
        ["J  Total no híbrido", "G + H + I", dinheiro(h["total"])],
        ["K  Total no Simples Nacional", "DAS pelo Anexo V" if anexo_v else "DAS declarado (Anexo III)", dinheiro(s["simples_puro"]["total"])],
        ["L  " + ("Economia no híbrido" if delta > 0 else "Custo adicional no híbrido" if delta < 0 else "Diferença"), "K − J", dinheiro(delta)],
    ]
    tabela(linhas, [width * .46, width * .30, width * .24], direita=(2,), total=True)

    # ---------------------------------------------------------- notas de entrada
    notas = sorted(notas_entrada or [], key=lambda n: (_ordem_data(n["data"]), n["razao_social"]))
    com = [n for n in notas if n["com_credito"]]
    sem = [n for n in notas if not n["com_credito"]]

    add("2. Compras e serviços tomados COM crédito", "sub")
    if com:
        linhas = [["Data", "Fornecedor / CNPJ", "CFOP", "Valor", "Crédito IBS", "Crédito CBS"]]
        for n in com:
            v = numero(n["valor"])
            linhas.append([n["data"], f'{n["razao_social"]}\n{cnpj_fmt(n["cnpj"])}', n.get("cfop", ""), dinheiro(v),
                           dinheiro((v * ibs).quantize(Decimal(".01"))), dinheiro((v * cbs).quantize(Decimal(".01")))])
        soma = sum((numero(n["valor"]) for n in com), Decimal("0"))
        linhas.append(["Total", f"{len(com)} nota(s)", "", dinheiro(soma),
                       dinheiro(numero(h["ibs_creditos_automaticos"])), dinheiro(numero(h["cbs_creditos_automaticos"]))])
        tabela(linhas, [width * .12, width * .38, width * .08, width * .14, width * .14, width * .14], direita=(3, 4, 5), total=True)
        if soma.quantize(Decimal(".01")) != base_credito.quantize(Decimal(".01")):
            add("Atenção: a soma das notas não confere com a base usada na simulação. Calcule a comparação novamente.", "smallb")
        else:
            add("Crédito total = soma das notas × alíquota (pode haver diferença de centavos em relação à soma linha a linha).", "small")
    else:
        add("Nenhuma nota com crédito no período.", "small")

    add("3. Compras e serviços tomados SEM crédito", "sub")
    if sem:
        linhas = [["Data", "Fornecedor / CNPJ", "CFOP", "Motivo", "Valor"]]
        for n in sem:
            linhas.append([n["data"], f'{n["razao_social"]}\n{cnpj_fmt(n["cnpj"])}', n.get("cfop", ""), n["motivo"], dinheiro(n["valor"])])
        soma_sem = sum((numero(n["valor"]) for n in sem), Decimal("0"))
        linhas.append(["Total", f"{len(sem)} nota(s)", "", "", dinheiro(soma_sem)])
        tabela(linhas, [width * .12, width * .40, width * .08, width * .22, width * .18], direita=(4,), total=True)
    else:
        add("Nenhuma nota sem crédito no período.", "small")

    if notas:
        soma_com = sum((numero(n["valor"]) for n in com), Decimal("0"))
        soma_sem = sum((numero(n["valor"]) for n in sem), Decimal("0"))
        tabela([["Conferência das entradas do período", "Valor"],
                ["Com crédito (quadro 2)", dinheiro(soma_com)],
                ["Sem crédito (quadro 3)", dinheiro(soma_sem)],
                ["Total de compras e serviços tomados", dinheiro(soma_com + soma_sem)]],
               [width * .70, width * .30], direita=(1,), total=True)

    # ----------------------------------------------------------- compradores
    add("4. Principais clientes (crédito que o comprador pode aproveitar)", "sub")
    top = sorted([x for x in compradores if numero(x["valor"]) > 0], key=lambda x: (-numero(x["valor"]), x["cnpj"]))[:3]
    if top:
        linhas = [["Cliente / CNPJ", "Faturamento", "Crédito do cliente¹"]]
        for x in top:
            v = numero(x["valor"])
            linhas.append([f'{x["razao_social"]}\n{cnpj_fmt(x["cnpj"])}', dinheiro(v),
                           dinheiro((v * ibs).quantize(Decimal(".01")) + (v * cbs).quantize(Decimal(".01")))])
        tabela(linhas, [width * .56, width * .22, width * .22], direita=(1, 2))
        total = sum(numero(x["valor"]) for x in top)
        if receita > 0 and total <= receita:
            add(f"Esses clientes representam {percentual(total / receita)} da receita do período.", "small")
        else:
            add("A participação na receita não foi calculada: as bases de movimentação e de receita precisam ser conciliadas.", "small")
        add("¹ Só existe se o cliente for do regime regular; não reduz o imposto desta empresa.", "small")
    else:
        add("Não há compradores com movimentação individual identificada para este período.", "small")

    # ------------------------------------------------- observações e riscos
    obs = observacoes or {}
    fr = obs.get("fator_r")
    if fr or obs.get("servicos_como_revenda") or obs.get("texto"):
        add("5. Observações e riscos encontrados na análise", "sub")
        n = 0
        if fr:
            n += 1
            fator = numero(fr["fator_r"])
            add(f"<b>{n}. Apuração do DAS: atividade sujeita ao fator r.</b> A atividade de testes e análises técnicas "
                "(LC 123/2006, art. 18, §§ 5º-I e 5º-J) é tributada pelo Anexo V, e só passa ao Anexo III quando a folha "
                f"dos últimos 12 meses é de pelo menos 28% da receita bruta. Folha informada: {dinheiro(fr['folha_12_meses'])}; "
                f"RBT12: {dinheiro(fr['rbt12_total'])}; fator r: <b>{percentual(fator)}</b>. "
                + ("O PGDAS foi apurado pelo Anexo III. " if "III" in (fr.get("anexos_declarados") or []) else "")
                + (f"Para usar o Anexo III seria necessária folha de {dinheiro(fr['folha_minima_28'])} em 12 meses."
                   if fator < Decimal("0.28") else "O fator r atinge 28%: o Anexo III está correto."))
            if fator < Decimal("0.28"):
                linhas = [["Mês", "Receita interna", "RBT12 interno", "DAS Anexo III", "DAS Anexo V", "Diferença"]]
                for l in fr["linhas"]:
                    linhas.append([l["competencia"] + (" *" if l["exportacao"] else ""), dinheiro(l["receita_interna"]),
                                   dinheiro(l["rbt12_interno"]),
                                   f'{dinheiro(l["das_iii"])}\n({l["aliquota_iii"].replace(".", ",")}%)',
                                   f'{dinheiro(l["das_v"])}\n({l["aliquota_v"].replace(".", ",")}%)',
                                   dinheiro(l["diferenca"])])
                linhas.append(["Total", "", "", dinheiro(fr["total_iii"]), dinheiro(fr["total_v"]), dinheiro(fr["total_diferenca"])])
                tabela(linhas, [width * .11, width * .18, width * .19, width * .17, width * .17, width * .18],
                       direita=(1, 2, 3, 4, 5), total=True)
                if any(l["exportacao"] for l in fr["linhas"]):
                    add("* Mês com exportação: a tabela considera só a receita do mercado interno; a exportação tem cálculo próprio.", "small")
                add(f"<b>Risco:</b> diferença estimada de <b>{dinheiro(fr['total_diferenca'])}</b> de DAS recolhido a menor no período, "
                    "sujeita a cobrança com multa e juros (inclusive de períodos anteriores ainda não prescritos, em até 5 anos), "
                    "além do risco de exclusão do Simples em fiscalização. Recomenda-se revisar o enquadramento, avaliar a "
                    "retificação dos PGDAS e, se for o caso, ajustar a folha/pró-labore para atingir 28%.", "small")
        if obs.get("servicos_como_revenda"):
            n += 1
            revenda = [x for x in notas if str(x.get("cfop", "")).endswith("102")]
            add(f"<b>{n}. Escrituração das notas.</b> A empresa apenas presta serviços, mas há compras escrituradas como "
                "mercadoria para revenda (CFOP 1.102/2.102 — compra para comercialização). <b>Risco:</b> divergência entre a "
                "escrituração e o PGDAS (somente serviços), cruzamentos da fiscalização de ICMS (estoque e saídas de mercadoria "
                "inexistentes) e classificação errada das entradas para crédito de IBS/CBS. Recomenda-se reescriturar como "
                "material de uso e consumo ou insumo da prestação de serviço (ex.: CFOP 1.556/2.556), conforme o caso.", "small")
            if revenda:
                linhas = [["Data", "Fornecedor / CNPJ", "CFOP", "Valor"]]
                for x in revenda:
                    linhas.append([x["data"], f'{x["razao_social"]}\n{cnpj_fmt(x["cnpj"])}', x.get("cfop", ""), dinheiro(x["valor"])])
                linhas.append(["Total", f"{len(revenda)} nota(s)", "", dinheiro(sum((numero(x["valor"]) for x in revenda), Decimal("0")))])
                tabela(linhas, [width * .14, width * .52, width * .12, width * .22], direita=(3,), total=True)
        if obs.get("texto"):
            n += 1
            add(f"<b>{n}. Outras observações.</b> " + escape(obs["texto"]).replace("\n", "<br/>"), "small")
        add("Valores estimados a partir dos PGDAS e relatórios enviados; a confirmação cabe à contabilidade responsável.", "small")

    add(f'Premissas: IBS {percentual(ibs)}; CBS {percentual(cbs)} ({escape(str(prem.get("fonte_cbs") or ""))}); '
        f"DAS remanescente {percentual(pct_das)} ({escape(str(prem.get('fonte_das_remanescente') or ''))}). Fornecedores do Simples Nacional e MEI não geram crédito automático neste cenário. "
        "Valores conforme os PDFs enviados ao sistema; cenário de planejamento, sem garantia de economia. "
        '<a href="https://www2.camara.leg.br/legin/fed/leicom/2025/leicomplementar-214-16-janeiro-2025-796905-normaatualizada-pl.html">Base legal: LC 214/2025.</a>', "small")

    from marca import desenhar_marca
    emitido = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    def rodape(canvas, doc):
        desenhar_marca(canvas, A4[0], A4[1], 48, "Motor Tributário | " + emitido, f"Página {doc.page}", azul)
    SimpleDocTemplate(stream, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=76, bottomMargin=58,
                      title="Apuração IBS/CBS - " + cliente["razao_social"], author="Motor Tributário").build(story, onFirstPage=rodape, onLaterPages=rodape)
    return stream.getvalue()
