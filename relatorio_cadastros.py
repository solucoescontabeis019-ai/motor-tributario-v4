"""Exportação dos cadastros analisados, sem consultas externas ou escrita no banco."""
from decimal import Decimal
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape


def gerar_pdf_cadastros(empresa, grupos, ibs, cbs):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
    from relatorio_cliente import dinheiro, percentual
    saida = BytesIO()
    tamanho = landscape(A4)
    largura = tamanho[0] - 80
    azul = colors.HexColor('#142746')
    estilos = {nome: ParagraphStyle(nome, fontName='Helvetica-Bold' if nome=='titulo' else 'Helvetica',fontSize=fs,leading=ld,textColor=azul,spaceAfter=7)
               for nome,fs,ld in [('titulo',17,21),('texto',9,13),('celula',8,11)]}
    def p(v, estilo='texto'):
        return Paragraph(escape(str(v)).replace('\n','<br/>'),estilos[estilo])
    def cnpj(v):
        s=''.join(x for x in str(v) if x.isdigit())
        return f'{s[:2]}.{s[2:5]}.{s[5:8]}/{s[8:12]}-{s[12:]}' if len(s)==14 else str(v or 'Não informado')
    regimes={'REGULAR':'Regular','SIMPLES_NACIONAL':'Simples Nacional','MEI':'MEI','NAO_VALIDADO':'Não validado','Não Validado':'Não validado'}
    situacoes={'validado':'Validado no sistema','presumido':'Presumido','não_validado':'Pendente','nao_validado':'Pendente'}
    elementos=[]
    for index,(titulo,itens) in enumerate(grupos):
        if index: elementos.append(PageBreak())
        elementos.extend([p(titulo,'titulo'),p(empresa['razao_social']+' | CNPJ '+cnpj(empresa['cnpj'])),
                          p('Base consolidada do cadastro analisado. O período registrado consta em cada linha; não há filtro mensal neste relatório.')])
        total=sum((Decimal(str(x['valor'])) for x in itens),Decimal('0'))
        validados=sum(x['status']=='validado' for x in itens)
        elementos.append(p(f'{len(itens)} registros | Total movimentado: {dinheiro(total)} | Validados no sistema: {validados} | Demais situações: {len(itens)-validados}'))
        elementos.append(p(f'Crédito estimado do cenário: IBS {percentual(ibs)} + CBS {percentual(cbs)}. Classificação cadastral não comprova, isoladamente, direito ao crédito.'))
        if not itens:
            elementos.append(p('Nenhum cadastro analisado disponível para esta empresa nesta seção.'))
            continue
        cabecalho=['Razão social / CNPJ','Período registrado','Valor movimentado','Regime identificado','Validação','Crédito estimado']
        linhas=[list(map(lambda x:p(x,'celula'),cabecalho))]
        for x in itens:
            credito=x.get('credito')
            linhas.append([p(x['razao_social']+'\n'+cnpj(x['cnpj']),'celula'),p(x.get('periodo') or 'Não informado','celula'),
                           p(dinheiro(x['valor']),'celula'),p(regimes.get(x['regime'],x['regime'] or 'Não informado'),'celula'),
                           p(situacoes.get(x['status'],x['status'] or 'Pendente'),'celula'),
                           p(dinheiro(credito) if credito is not None else 'Não apurado automaticamente','celula')])
        tabela=LongTable(linhas,colWidths=[largura*f for f in [.29,.12,.15,.15,.14,.15]],repeatRows=1,hAlign='LEFT')
        tabela.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EDF1F6')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F7F9FC')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#D8E0EA')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        elementos.extend([tabela,Spacer(1,10),p('Valores reproduzidos do cadastro consolidado do sistema. Registros pendentes e presumidos estão identificados. Ausência de cálculo automático não significa ausência de direito ao crédito.')])
        if index==0:
            elementos.append(p('Clientes: o crédito indicado é potencial para o comprador; não reduz o imposto da empresa analisada.'))
        else:
            elementos.append(p('Fornecedores: a apropriação depende da operação e dos documentos fiscais correspondentes.'))
    emitido=datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    def rodape(canvas,doc):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(azul)
        canvas.drawString(40,22,'Motor Tributário | Emitido em '+emitido)
        canvas.drawRightString(tamanho[0]-40,22,f'Página {doc.page}');canvas.restoreState()
    SimpleDocTemplate(saida,pagesize=tamanho,leftMargin=40,rightMargin=40,topMargin=35,bottomMargin=42,title='Clientes e fornecedores analisados',author='Motor Tributário').build(elementos,onFirstPage=rodape,onLaterPages=rodape)
    return saida.getvalue()
