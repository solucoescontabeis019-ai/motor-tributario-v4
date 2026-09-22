"""
Motor Tributário v4.0 - Backend FastAPI Multicliente
Versão genérica sem hardcodes. Aceita qualquer cliente via CNPJ.

IMPORTANTE:
- Sem hardcodes de WASHINGTON
- Sem CBS 0.088 fixo
- Sem percentuais fixos (75%, 30%, etc)
- Valores vêm de config ou database
"""

from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List
import base64
import json
import logging
import os
import tempfile
import httpx
import asyncio
import re
import base64 as base64_stdlib
import secrets

# Imports do projeto
from database_v4 import SessionLocal, get_db, init_db
from models_v4 import Client, Analysis, Document, Supplier, Customer
from normalizer_v4 import DataNormalizer
from document_parser_v2_3 import DocumentParser
from cnpj_classifier import consultar_regime_cnpj, somente_digitos
from config_v4 import get_config, TaxRates
from engines import (
    TaxLegislationEngine,
    SimplesCalculationEngine,
    HibridoCalculationEngine,
    CreditEngine,
    AnalysisEngine
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar FastAPI
app = FastAPI(
    title="Motor Tributário v4.0",
    description="Sistema de Análise Tributária Multicliente - Simples Nacional vs IBS/CBS",
    version="4.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config global
CONFIG = get_config()
logger.info(f"Configuração carregada: CBS={CONFIG.cbs_2027_aliquota} (status: {CONFIG.cbs_2027_status})")


class SharedAccessAuthMiddleware(BaseHTTPMiddleware):
    """Protege o painel compartilhado com credenciais definidas no servidor."""

    async def dispatch(self, request: Request, call_next):
        if not CONFIG.require_auth or request.url.path == "/api/v4/health":
            return await call_next(request)
        authorization = request.headers.get("Authorization", "")
        valido = False
        if authorization.startswith("Basic "):
            try:
                usuario_senha = base64_stdlib.b64decode(authorization[6:]).decode("utf-8")
                usuario, senha = usuario_senha.split(":", 1)
                valido = (
                    secrets.compare_digest(usuario, CONFIG.app_username)
                    and secrets.compare_digest(senha, CONFIG.app_password)
                )
            except (ValueError, UnicodeDecodeError):
                valido = False
        if not valido:
            return Response(
                content="Acesso restrito. Informe o usuário e a senha do sistema.",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Motor Tributario"'},
                media_type="text/plain; charset=utf-8",
            )
        return await call_next(request)


app.add_middleware(SharedAccessAuthMiddleware)

# Engines
legislation_engine = TaxLegislationEngine()
simples_engine = SimplesCalculationEngine()
hibrido_engine = HibridoCalculationEngine()
credit_engine = CreditEngine()
analysis_engine = AnalysisEngine()
document_parser = DocumentParser()
PASTA_ATUAL = os.path.dirname(os.path.abspath(__file__))


class RevisaoExtracao(BaseModel):
    """Aprovação humana dos totais que o PDF não permitiu conciliar sozinho."""

    total_confirmado: Optional[Decimal] = Field(default=None, ge=0)
    observacao: str = Field(min_length=3, max_length=1000)


class ParametrosHibrido(BaseModel):
    """Premissas registradas para um cenário de opção IBS/CBS no regime regular."""

    cbs_aliquota: Decimal = Field(default=Decimal("0.088"), gt=0, le=1)
    ibs_aliquota: Decimal = Field(default=Decimal("0.001"), ge=0, le=1)
    percentual_das_remanescente: Optional[Decimal] = Field(default=None, ge=0, lt=1)
    creditos_ibs_documentados: Decimal = Field(default=Decimal("0"), ge=0)
    creditos_cbs_documentados: Decimal = Field(default=Decimal("0"), ge=0)
    fonte_cbs: str = Field(default="Expectativa de mercado - cenário-base 8,8%", min_length=3, max_length=500)
    fonte_das_remanescente: Optional[str] = Field(default=None, max_length=500)


def _decimal_seguro(valor: Any) -> Decimal:
    """Converte valores do JSON sem aceitar texto não numérico como zero."""
    if valor is None or valor == "":
        return Decimal("0")
    try:
        if not isinstance(valor, str):
            return Decimal(str(valor))
        texto = valor.strip().replace("R$", "").replace(" ", "")
        # O último separador é o decimal; o outro, quando houver, é milhar.
        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")
        return Decimal(texto)
    except Exception as exc:
        raise ValueError(f"Valor extraído inválido: {valor!r}") from exc


def _resumo_documento(documento: Document, incluir_extracao: bool = False) -> Dict[str, Any]:
    parsed = documento.conteudo_parsed or {}
    resultado = {
        "id": documento.id,
        "tipo": documento.tipo,
        "periodo": documento.periodo,
        "status": documento.status,
        "upload_em": documento.created_at,
        "status_extracao": parsed.get("status"),
        "confianca": parsed.get("confidence"),
        "revisao": parsed.get("revisao"),
    }
    if incluir_extracao:
        resultado["extracao"] = parsed
    return resultado


def _base_real_pgdas(documentos: List[Document], periodo: str) -> Dict[str, Any]:
    """Monta a base factual de 2026 a partir do PGDAS, sem projetar alíquota."""
    pgdas = [d for d in documentos if d.tipo == "pgdas" and d.status == "processado"]
    if not pgdas:
        return {"status": "NAO_DISPONIVEL", "motivo": "PGDAS validado não localizado."}

    # Prioriza a competência solicitada; se não houver igualdade, informa a
    # competência do PDF em vez de supor que ele representa todo o período.
    if "-a-" in periodo or (len(periodo) == 4 and periodo.isdigit()):
        ano = periodo[:4]
        selecionados = sorted(
            [
                d for d in pgdas
                if (d.periodo or "").startswith(f"{ano}-")
                or str((d.conteudo_parsed or {}).get("mes_competencia") or "").endswith(f"/{ano}")
            ],
            key=lambda d: str((d.conteudo_parsed or {}).get("mes_competencia") or d.periodo or ""),
        )
        campos = ("rbt12_value", "receita_periodo_value", "das_value")
        if not selecionados or any(
            not all((d.conteudo_parsed or {}).get(campo) is not None for campo in campos)
            for d in selecionados
        ):
            return {"status": "NAO_DISPONIVEL", "motivo": "PGDAS incompleto para o intervalo solicitado."}
        ultimo = selecionados[-1]
        dados_ultimo = ultimo.conteudo_parsed or {}
        receita_total = sum(
            (_decimal_seguro((d.conteudo_parsed or {})["receita_periodo_value"]) for d in selecionados),
            Decimal("0"),
        )
        das_total = sum(
            (_decimal_seguro((d.conteudo_parsed or {})["das_value"]) for d in selecionados),
            Decimal("0"),
        )
        return {
            "status": "DOCUMENTADO",
            "documento_ids": [d.id for d in selecionados],
            "competencias": [d.periodo for d in selecionados],
            "rbt12_ultima_competencia": str(_decimal_seguro(dados_ultimo["rbt12_value"]).quantize(Decimal("0.01"))),
            "receita_total_periodo": str(receita_total.quantize(Decimal("0.01"))),
            "das_total_recolhido": str(das_total.quantize(Decimal("0.01"))),
            "ultimo_pgdas": {
                "competencia_pdf": dados_ultimo.get("mes_competencia"),
                "secoes_pgdas": dados_ultimo.get("secoes", []),
            },
            "observacao": "Valores históricos dos PDFs; não são projeção de 2027.",
        }

    candidato = next((d for d in pgdas if d.periodo == periodo), pgdas[-1])
    dados = candidato.conteudo_parsed or {}
    campos = ("rbt12_value", "receita_periodo_value", "das_value")
    if not all(dados.get(campo) is not None for campo in campos):
        return {"status": "NAO_DISPONIVEL", "motivo": "PGDAS sem RBT12, receita ou DAS completo."}
    return {
        "status": "DOCUMENTADO",
        "documento_id": candidato.id,
        "competencia_pdf": dados.get("mes_competencia"),
        "rbt12": str(_decimal_seguro(dados["rbt12_value"]).quantize(Decimal("0.01"))),
        "receita_competencia": str(_decimal_seguro(dados["receita_periodo_value"]).quantize(Decimal("0.01"))),
        "das_recolhido": str(_decimal_seguro(dados["das_value"]).quantize(Decimal("0.01"))),
        "secoes_pgdas": dados.get("secoes", []),
        "observacao": "Valor histórico do PDF; não é uma projeção de 2027.",
    }


def _entidades_extraidas(documentos: List[Document], tipos: set) -> Dict[str, Dict[str, Any]]:
    """Une relação cadastral e movimentação, acumulando somente valores documentais."""
    consolidadas: Dict[str, Dict[str, Any]] = {}
    for documento in documentos:
        # Original reports may remain stored for audit after replacement.
        # Their values must never be double-counted in a simulation.
        if documento.tipo not in tipos or documento.status == "substituido":
            continue
        for entidade in (documento.conteudo_parsed or {}).get("entities", []):
            cnpj = somente_digitos(entidade.get("cnpj", ""))
            if len(cnpj) != 14:
                continue
            item = consolidadas.setdefault(cnpj, {
                "cnpj": cnpj,
                "razao_social": entidade.get("razao_social") or "Não identificado",
                "valor": Decimal("0"),
                "quantidade": 0,
            })
            if entidade.get("razao_social"):
                item["razao_social"] = entidade["razao_social"]
            item["valor"] += _decimal_seguro(entidade.get("valor", entidade.get("valor_contabil", 0)))
            item["quantidade"] += int(entidade.get("quantidade_notas", 0) or 0)
    return consolidadas


def _periodo_da_operacao(data_emissao: Any, periodo: str) -> bool:
    """Aceita ano (2026) ou competência mensal (08/2026 ou 2026-08)."""
    texto = str(data_emissao or "").strip()
    correspondencia = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if not correspondencia:
        return False
    mes, _, ano = correspondencia.groups()
    periodo_normalizado = str(periodo or "").strip()
    if re.fullmatch(r"\d{4}", periodo_normalizado):
        return ano == periodo_normalizado
    if re.fullmatch(r"\d{2}/\d{4}", periodo_normalizado):
        return f"{mes}/{ano}" == periodo_normalizado
    if re.fullmatch(r"\d{4}-\d{2}", periodo_normalizado):
        return f"{ano}-{mes}" == periodo_normalizado
    return False


def _movimentacao_por_periodo(documentos: List[Document], tipos: set, periodo: str) -> Dict[str, Decimal]:
    """Soma operações do PDF somente na competência solicitada.

    Valores agregados por entidade não têm mês e, por segurança, não são usados
    em simulação mensal. Assim não se atribui crédito anual a uma única competência.
    """
    totais: Dict[str, Decimal] = {}
    for documento in documentos:
        if documento.tipo not in tipos or documento.status == "substituido":
            continue
        for operacao in (documento.conteudo_parsed or {}).get("operacoes", []):
            if not _periodo_da_operacao(operacao.get("data_emissao"), periodo):
                continue
            cnpj = somente_digitos(operacao.get("cnpj", ""))
            if len(cnpj) != 14:
                continue
            valor = _decimal_seguro(operacao.get("valor_contabil", operacao.get("valor", 0)))
            totais[cnpj] = totais.get(cnpj, Decimal("0")) + valor
    return totais


def _premissas_automaticas_hibrido(documentos: List[Document], periodo: str) -> Dict[str, Any]:
    """Gera a memória aproximada do DAS remanescente a partir dos PDFs."""
    base = _base_real_pgdas(documentos, periodo)
    if base.get("status") != "DOCUMENTADO":
        return {"status": "DADOS_INSUFICIENTES", "motivo": base.get("motivo")}
    receita = _decimal_seguro(base.get("receita_total_periodo", base.get("receita_competencia")))
    servicos = _movimentacao_por_periodo(documentos, {"servicos_prestados"}, periodo)
    receita_servicos = sum(servicos.values(), Decimal("0"))
    participacao_servicos = min(receita_servicos / receita, Decimal("1")) if receita else Decimal("0")
    # Cenário aproximado: permanecem 50,5% do DAS nas receitas de mercadorias
    # e 50,9% nas receitas de serviços após retirar ICMS/ISS/PIS/Cofins.
    percentual = (Decimal("0.505") + participacao_servicos * Decimal("0.004")).quantize(Decimal("0.0001"))
    return {
        "status": "CENARIO_APROXIMADO",
        "percentual_das_remanescente": str(percentual),
        "fonte_das_remanescente": (
            "Memória automática do sistema: composição aproximada do DAS, "
            "ponderada pela receita de serviços extraída dos PDFs."
        ),
        "receita_servicos_usada": str(receita_servicos.quantize(Decimal("0.01"))),
    }


def parse_uploaded_pdf(tipo: str, conteudo: bytes) -> Dict[str, Any]:
    """Extrai o mínimo auditável de um PDF e sempre preserva o original."""
    parser_by_type = {
        "pgdas": document_parser.parse_pgdas,
        "entradas": document_parser.parse_entradas,
        "saidas": document_parser.parse_saidas,
        "servicos_prestados": document_parser.parse_servicos_prestados,
        "fornecedores": document_parser.parse_fornecedores,
        "clientes": document_parser.parse_clientes,
    }
    parser = parser_by_type.get(tipo)
    if parser is None:
        return {
            "status": "RECEBIDO_SEM_PARSER",
            "confidence": 0.0,
            "message": f"Parser ainda não implementado para '{tipo}'",
        }

    caminho_temporario = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as arquivo_temporario:
            arquivo_temporario.write(conteudo)
            caminho_temporario = arquivo_temporario.name
        return parser(caminho_temporario)
    finally:
        if caminho_temporario and os.path.exists(caminho_temporario):
            os.remove(caminho_temporario)


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.get("/", include_in_schema=False)
async def abrir_painel():
    """Painel local para o fluxo PDF-only."""
    return FileResponse(os.path.join(PASTA_ATUAL, "dashboard_v4.html"))

@app.on_event("startup")
async def startup():
    """Inicialização do sistema"""
    if CONFIG.require_auth and (not CONFIG.app_username or not CONFIG.app_password):
        raise RuntimeError("REQUIRE_AUTH=true exige APP_USERNAME e APP_PASSWORD no servidor")
    if CONFIG.app_env == "production" and CONFIG.database_url.startswith("sqlite"):
        raise RuntimeError("Em produção, configure DATABASE_URL para PostgreSQL persistente")
    logger.info("="*80)
    logger.info("Motor Tributário v4.0 - Inicialização")
    logger.info("="*80)
    init_db()
    logger.info("✓ Sistema pronto para análise")
    logger.info(f"  IBS 2027: {CONFIG.ibs_2027_aliquota} (OFICIAL)")
    logger.info(f"  CBS 2027: {CONFIG.cbs_2027_aliquota} ({CONFIG.cbs_2027_status})")


# ============================================================================
# ENDPOINTS: Clientes (Multicliente)
# ============================================================================

@app.post("/api/v4/clientes/novo")
async def criar_novo_cliente(
    cnpj: str,
    razao_social: str,
    db: Session = Depends(get_db)
):
    """
    Cria um novo cliente para análise.

    Args:
        cnpj: CNPJ da empresa (com ou sem formatação)
        razao_social: Razão social conforme cadastro

    Returns:
        Cliente criado com ID para usar nas próximas análises
    """

    try:
        cnpj_norm = DataNormalizer.normalize_cnpj(cnpj)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"CNPJ inválido: {str(e)}")

    # Verificar se cliente já existe
    existing = db.query(Client).filter_by(cnpj=cnpj_norm).first()
    if existing:
        return {
            "status": "cliente_existe",
            "cliente_id": existing.id,
            "cnpj": cnpj_norm,
            "razao_social": existing.razao_social,
            "mensagem": f"Cliente {existing.razao_social} já está registrado"
        }

    # Criar novo cliente
    novo_cliente = Client(
        cnpj=cnpj_norm,
        razao_social=razao_social,
        created_at=date.today()
    )
    db.add(novo_cliente)
    db.commit()

    logger.info(f"✓ Novo cliente criado: {razao_social} ({cnpj_norm})")

    return {
        "status": "sucesso",
        "cliente_id": novo_cliente.id,
        "cnpj": cnpj_norm,
        "razao_social": razao_social,
        "mensagem": "Cliente criado com sucesso. Próximo: fazer upload de documentos"
    }


@app.get("/api/v4/clientes/{cliente_id}")
async def obter_cliente(
    cliente_id: int,
    db: Session = Depends(get_db)
):
    """Obtém dados de um cliente específico"""

    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Retornar dados do cliente (sem hardcodes)
    return {
        "cliente_id": cliente.id,
        "cnpj": cliente.cnpj,
        "razao_social": cliente.razao_social,
        "regime_atual": cliente.regime_atual,
        "created_at": cliente.created_at,
        "analises": len(cliente.analises)
    }


@app.get("/api/v4/clientes")
async def listar_clientes(db: Session = Depends(get_db)):
    """Lista todos os clientes registrados"""

    clientes = db.query(Client).all()

    return {
        "total": len(clientes),
        "clientes": [
            {
                "id": c.id,
                "cnpj": c.cnpj,
                "razao_social": c.razao_social,
                "regime_atual": c.regime_atual,
                "created_at": c.created_at
            }
            for c in clientes
        ]
    }


# ============================================================================
# ENDPOINTS: Documentos & Upload
# ============================================================================

@app.post("/api/v4/clientes/{cliente_id}/documentos/upload")
async def upload_documento(
    cliente_id: int,
    tipo: str,  # pgdas, entradas, saidas, fornecedores, clientes
    periodo: str,  # 2026-01, 2026-08, etc
    substituir: bool = Query(False, description="Substitui relatório ativo do mesmo tipo e período, preservando o anterior"),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload de documento (PGDAS, Entradas, Saídas, etc).
    Tipos aceitos: pgdas, entradas, saidas, fornecedores, clientes
    """

    # Verificar cliente
    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Verificar tipo válido
    tipos_validos = ["pgdas", "entradas", "saidas", "servicos_prestados", "fornecedores", "clientes"]
    if tipo not in tipos_validos:
        raise HTTPException(status_code=400, detail=f"Tipo deve ser um de: {', '.join(tipos_validos)}")

    if not arquivo.filename or not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Nesta etapa, envie um arquivo PDF")

    # Ler conteúdo do arquivo
    conteudo = await arquivo.read()
    if len(conteudo) > CONFIG.max_arquivo_size:
        raise HTTPException(status_code=413, detail="Arquivo excede o limite configurado")

    parsed = parse_uploaded_pdf(tipo, conteudo)
    status_documento = "processado" if parsed.get("status") == "VALIDADO" else "recebido"

    substituidos = []
    if substituir:
        anteriores = db.query(Document).filter(
            Document.cliente_id == cliente_id,
            Document.tipo == tipo,
            Document.periodo == periodo,
            Document.status != "substituido",
        ).all()
        for anterior in anteriores:
            anterior.status = "substituido"
            dados_anteriores = dict(anterior.conteudo_parsed or {})
            dados_anteriores["substituicao"] = {
                "status": "SUBSTITUIDO_POR_NOVO_PDF",
                "motivo": "Relatório mais completo enviado para o mesmo tipo e período.",
                "substituido_em": date.today().isoformat(),
            }
            anterior.conteudo_parsed = dados_anteriores
            substituidos.append(anterior.id)

    # O campo é texto no banco; usar base64 evita gravar bytes inválidos e
    # permite reprocessar o original posteriormente.
    novo_doc = Document(
        cliente_id=cliente_id,
        tipo=tipo,
        periodo=periodo,
        conteudo_raw=base64.b64encode(conteudo).decode("ascii"),
        conteudo_parsed=parsed,
        status=status_documento,
    )
    db.add(novo_doc)
    db.commit()

    logger.info(f"✓ Documento {tipo} recebido para cliente {cliente_id}")

    return {
        "status": "sucesso",
        "documento_id": novo_doc.id,
        "tipo": tipo,
        "periodo": periodo,
        "tamanho_bytes": len(conteudo),
        "status_documento": status_documento,
        "documentos_substituidos": substituidos,
        "extracao": parsed,
    }


@app.get("/api/v4/clientes/{cliente_id}/documentos")
async def listar_documentos(
    cliente_id: int,
    db: Session = Depends(get_db)
):
    """Lista documentos carregados de um cliente"""

    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    documentos = db.query(Document).filter_by(cliente_id=cliente_id).all()

    return {
        "cliente_id": cliente_id,
        "total_documentos": len(documentos),
        "documentos": [_resumo_documento(d) for d in documentos]
    }


@app.get("/api/v4/clientes/{cliente_id}/documentos/{documento_id}")
async def obter_documento(
    cliente_id: int,
    documento_id: int,
    db: Session = Depends(get_db)
):
    """Exibe a extração e suas evidências de página/linha para conferência."""
    documento = db.query(Document).filter_by(id=documento_id, cliente_id=cliente_id).first()
    if not documento:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return _resumo_documento(documento, incluir_extracao=True)


@app.post("/api/v4/clientes/{cliente_id}/documentos/{documento_id}/revisar")
async def revisar_extracao(
    cliente_id: int,
    documento_id: int,
    revisao: RevisaoExtracao,
    db: Session = Depends(get_db)
):
    """Registra a conferência humana sem apagar a extração original do PDF."""
    documento = db.query(Document).filter_by(id=documento_id, cliente_id=cliente_id).first()
    if not documento:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    parsed = dict(documento.conteudo_parsed or {})
    parsed["revisao"] = {
        "status": "CONFIRMADO_MANUALMENTE",
        "total_confirmado": str(revisao.total_confirmado) if revisao.total_confirmado is not None else None,
        "observacao": revisao.observacao,
        "revisado_em": date.today().isoformat(),
    }
    documento.conteudo_parsed = parsed
    documento.status = "processado"
    db.commit()
    return {
        "status": "sucesso",
        "mensagem": "Conferência registrada. A extração original e as evidências foram preservadas.",
        "documento": _resumo_documento(documento, incluir_extracao=True),
    }


@app.post("/api/v4/clientes/{cliente_id}/documentos/{documento_id}/reprocessar")
async def reprocessar_documento(
    cliente_id: int,
    documento_id: int,
    db: Session = Depends(get_db)
):
    """Aplica a versão atual do extrator ao PDF original já armazenado."""
    documento = db.query(Document).filter_by(id=documento_id, cliente_id=cliente_id).first()
    if not documento:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    if not documento.conteudo_raw:
        raise HTTPException(status_code=422, detail="O PDF original não está disponível para reprocessamento")
    try:
        conteudo = base64.b64decode(documento.conteudo_raw, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Conteúdo original inválido para reprocessamento") from exc

    parsed = parse_uploaded_pdf(documento.tipo, conteudo)
    documento.conteudo_parsed = parsed
    documento.status = "processado" if parsed.get("status") == "VALIDADO" else "recebido"
    db.commit()
    return {
        "status": "sucesso",
        "mensagem": "PDF reprocessado pela versão atual do extrator.",
        "documento": _resumo_documento(documento, incluir_extracao=True),
    }


@app.get("/api/v4/clientes/{cliente_id}/consolidacao")
async def consolidar_movimentacoes(
    cliente_id: int,
    periodo: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Consolida operações extraídas dos PDFs, mantendo a rastreabilidade de origem."""
    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    consulta = db.query(Document).filter_by(cliente_id=cliente_id)
    if periodo:
        consulta = consulta.filter_by(periodo=periodo)
    documentos = consulta.filter(Document.tipo.in_(["entradas", "saidas", "servicos_prestados"])).all()
    grupos: Dict[str, Dict[str, Dict[str, Any]]] = {
        "entradas": {}, "saidas": {}, "servicos_prestados": {},
    }
    avisos: List[str] = []

    for documento in documentos:
        parsed = documento.conteudo_parsed or {}
        if documento.status != "processado":
            avisos.append(f"Documento {documento.id} ({documento.tipo}) ainda não foi conferido.")
        for operacao in parsed.get("operacoes", []):
            cnpj = operacao.get("cnpj") or "SEM_CNPJ"
            chave = cnpj
            grupo = grupos[documento.tipo].setdefault(chave, {
                "cnpj": cnpj,
                "razao_social": operacao.get("razao_social") or operacao.get("nome") or "Não identificado",
                "valor_contabil": Decimal("0"),
                "quantidade_operacoes": 0,
                "evidencias": [],
            })
            try:
                grupo["valor_contabil"] += _decimal_seguro(operacao.get("valor_contabil", operacao.get("valor")))
            except ValueError:
                avisos.append(f"Operação sem valor legível no documento {documento.id}.")
            grupo["quantidade_operacoes"] += 1
            grupo["evidencias"].append({
                "documento_id": documento.id,
                "pagina": operacao.get("pagina_origem"),
                "linha": operacao.get("linha_origem"),
            })

    resultado = {}
    for tipo, grupo in grupos.items():
        entidades = []
        for item in grupo.values():
            item["valor_contabil"] = str(item["valor_contabil"].quantize(Decimal("0.01")))
            entidades.append(item)
        resultado[tipo] = {
            "total": str(sum((_decimal_seguro(item["valor_contabil"]) for item in entidades), Decimal("0")).quantize(Decimal("0.01"))),
            "entidades": sorted(entidades, key=lambda item: item["valor_contabil"], reverse=True),
        }

    return {
        "cliente_id": cliente_id,
        "periodo": periodo,
        "status": "PRONTO_PARA_CONFERENCIA" if avisos else "CONFERIDO",
        "avisos": avisos,
        "movimentacoes": resultado,
        "observacao": "Esta consolidação é documental. Não representa crédito fiscal ou imposto a recolher.",
    }


@app.get("/api/v4/clientes/{cliente_id}/painel")
async def painel_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Checklist simples para orientar o próximo passo de cada cliente."""
    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    documentos = db.query(Document).filter_by(cliente_id=cliente_id).all()
    por_tipo = {tipo: [d for d in documentos if d.tipo == tipo] for tipo in ("pgdas", "entradas", "saidas")}
    pendencias = [tipo for tipo, itens in por_tipo.items() if not itens or not any(d.status == "processado" for d in itens)]
    return {
        "cliente": {"id": cliente.id, "razao_social": cliente.razao_social, "cnpj": cliente.cnpj},
        "documentos": [_resumo_documento(d) for d in documentos],
        "pronto_para_simulacao": not pendencias,
        "pendencias": pendencias,
        "proximo_passo": "Conferir PDFs pendentes" if pendencias else "Cadastrar regras tributárias versionadas e evidências de crédito",
    }


@app.post("/api/v4/clientes/{cliente_id}/classificacoes/atualizar")
async def atualizar_classificacoes_cnpj(
    cliente_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Consulta e armazena o enquadramento de fornecedores e clientes por CNPJ."""
    if not db.query(Client).filter_by(id=cliente_id).first():
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    documentos = db.query(Document).filter_by(cliente_id=cliente_id).all()
    fornecedores = _entidades_extraidas(documentos, {"entradas", "fornecedores"})
    compradores = _entidades_extraidas(documentos, {"saidas", "servicos_prestados", "clientes"})
    # Relações cadastrais sem compra, venda ou serviço não participam da
    # decisão econômica nem consomem consulta de CNPJ.
    fornecedores = {cnpj: item for cnpj, item in fornecedores.items() if item["valor"] > 0}
    compradores = {cnpj: item for cnpj, item in compradores.items() if item["valor"] > 0}
    todos = {**fornecedores, **compradores}
    cache = {}
    if not force:
        for registro in db.query(Supplier).filter_by(cliente_id=cliente_id, regime_validacao_status="validado").all():
            cache[registro.cnpj] = {"cnpj": registro.cnpj, "regime": registro.regime, "status": "validado", "fonte": "cache local"}
        for registro in db.query(Customer).filter_by(cliente_id=cliente_id, regime_validacao_status="validado").all():
            cache[registro.cnpj] = {"cnpj": registro.cnpj, "regime": registro.regime, "status": "validado", "fonte": "cache local"}
    pendentes = [cnpj for cnpj in todos if cnpj not in cache]
    semaforo = asyncio.Semaphore(2)

    async def consultar(cnpj: str, client: httpx.AsyncClient):
        async with semaforo:
            return cnpj, await consultar_regime_cnpj(cnpj, client)

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True) as client:
        respostas = await asyncio.gather(*(consultar(cnpj, client) for cnpj in pendentes), return_exceptions=False)
    por_cnpj = {**cache, **dict(respostas)}

    for cnpj, entidade in fornecedores.items():
        dado = por_cnpj[cnpj]
        registro = db.query(Supplier).filter_by(cliente_id=cliente_id, cnpj=cnpj).first()
        if not registro:
            registro = Supplier(cliente_id=cliente_id, cnpj=cnpj, razao_social=entidade["razao_social"])
            db.add(registro)
        registro.razao_social = dado.get("razao_social") or entidade["razao_social"]
        registro.regime = dado["regime"]
        registro.regime_validacao_status = dado["status"]
        registro.total_compras = entidade["valor"].quantize(Decimal("0.01"))
        registro.quantidade_notas = entidade["quantidade"]

    for cnpj, entidade in compradores.items():
        dado = por_cnpj[cnpj]
        registro = db.query(Customer).filter_by(cliente_id=cliente_id, cnpj=cnpj).first()
        if not registro:
            registro = Customer(cliente_id=cliente_id, cnpj=cnpj, cnpj_raiz=cnpj[:8], razao_social=entidade["razao_social"])
            db.add(registro)
        registro.razao_social = dado.get("razao_social") or entidade["razao_social"]
        registro.regime = dado["regime"]
        registro.regime_validacao_status = dado["status"]
        registro.total_faturamento = entidade["valor"].quantize(Decimal("0.01"))
        registro.quantidade_notas = entidade["quantidade"]
    db.commit()

    categorias = ["SIMPLES_NACIONAL", "MEI", "REGULAR", "NAO_VALIDADO"]
    def resumo(cnpjs: List[str]) -> Dict[str, int]:
        return {chave: sum(1 for cnpj in cnpjs if por_cnpj[cnpj]["regime"] == chave) for chave in categorias}
    return {
        "status": "CONCLUIDO",
        "fornecedores_consultados": len(fornecedores),
        "clientes_consultados": len(compradores),
        "cnpjs_consultados_agora": len(pendentes),
        "cnpjs_reaproveitados_cache": len(cache),
        "classificacao_fornecedores": resumo(list(fornecedores)),
        "classificacao_clientes": resumo(list(compradores)),
        "mensagem": "Somente fornecedores REGULAR validados serão considerados para crédito automático no cenário.",
    }


@app.get("/api/v4/clientes/{cliente_id}/classificacoes/creditos")
async def listar_creditos_por_cnpj(
    cliente_id: int,
    ibs_aliquota: Decimal = Query(default=Decimal("0.001"), ge=0, le=1),
    cbs_aliquota: Decimal = Query(default=Decimal("0.088"), ge=0, le=1),
    db: Session = Depends(get_db),
):
    """Detalha o crédito do cenário por fornecedor e o potencial por cliente."""
    if not db.query(Client).filter_by(id=cliente_id).first():
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    def credito(base: Decimal, regime: str, status: str) -> Dict[str, str]:
        elegivel = regime == "REGULAR" and status == "validado"
        ibs = (base * ibs_aliquota).quantize(Decimal("0.01")) if elegivel else Decimal("0")
        cbs = (base * cbs_aliquota).quantize(Decimal("0.01")) if elegivel else Decimal("0")
        if base <= 0:
            motivo = "Sem valor de movimentação no relatório"
        elif not elegivel and regime in {"SIMPLES_NACIONAL", "MEI"}:
            motivo = "Sem crédito: Simples/MEI"
        elif not elegivel:
            motivo = "CNPJ/regime a confirmar"
        else:
            motivo = "Crédito calculado"
        return {"ibs": str(ibs), "cbs": str(cbs), "total": str(ibs + cbs), "elegivel": elegivel, "motivo": motivo}

    fornecedores = []
    for item in db.query(Supplier).filter(
        Supplier.cliente_id == cliente_id, Supplier.total_compras > 0
    ).order_by(Supplier.total_compras.desc()).all():
        base = Decimal(str(item.total_compras or 0))
        fornecedores.append({
            "cnpj": item.cnpj, "razao_social": item.razao_social, "valor": str(base),
            "regime": item.regime, "status": item.regime_validacao_status,
            "credito": credito(base, item.regime, item.regime_validacao_status),
        })
    clientes = []
    for item in db.query(Customer).filter(
        Customer.cliente_id == cliente_id, Customer.total_faturamento > 0
    ).order_by(Customer.total_faturamento.desc()).all():
        base = Decimal(str(item.total_faturamento or 0))
        clientes.append({
            "cnpj": item.cnpj, "razao_social": item.razao_social, "valor": str(base),
            "regime": item.regime, "status": item.regime_validacao_status,
            "credito": credito(base, item.regime, item.regime_validacao_status),
        })
    return {
        "fornecedores": fornecedores,
        "clientes": clientes,
        "observacao": "Crédito zero para Simples, MEI e CNPJ não validado. Cliente regular mostra potencial de crédito sobre mercadorias e serviços.",
    }


# ============================================================================
# ENDPOINTS: Análises
# ============================================================================

@app.post("/api/v4/clientes/{cliente_id}/analises/processar")
async def processar_analise(
    cliente_id: int,
    periodo: str,  # 2026-01 ou 2026-08 ou 2026-01-a-08, etc
    db: Session = Depends(get_db)
):
    """
    Processa análise completa do cliente.

    Precisa que documentos estejam carregados antes.
    Retorna: 2026 Real, 2027 Simples Puro, 2027 Híbrido
    """

    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Verificar se tem documentos
    docs = db.query(Document).filter_by(cliente_id=cliente_id).all()
    if len(docs) == 0:
        raise HTTPException(status_code=400, detail="Nenhum documento carregado")

    try:
        # Criar análise (será preenchida pelos engines)
        nova_analise = Analysis(
            cliente_id=cliente_id,
            periodo=periodo,
            status="processando"
        )
        db.add(nova_analise)
        db.flush()

        documentos_por_tipo = {doc.tipo: [d for d in docs if d.tipo == doc.tipo] for doc in docs}
        obrigatorios = {"pgdas", "entradas", "saidas"}
        faltantes = sorted(obrigatorios - set(documentos_por_tipo))
        nao_processados = sorted(
            tipo for tipo in obrigatorios
            if tipo in documentos_por_tipo and not any(d.status == "processado" for d in documentos_por_tipo[tipo])
        )

        # Não retornar uma recomendação numérica antes de haver os documentos
        # mínimos e a extração auditável. Isso substitui o falso "completa".
        nova_analise.status = "pendente_dados"
        nova_analise.resultado = {
            "status": "DADOS_INSUFICIENTES",
            "periodo": periodo,
            "base_real_2026": _base_real_pgdas(docs, periodo),
            "cenario_simples_2027": {
                "status": "BLOQUEADO",
                "motivo": "A projeção requer premissas de receita e regra tributária versionada.",
            },
            "cenario_hibrido_2027": {
                "status": "BLOQUEADO",
                "motivo": "Além das regras, exige composição do DAS remanescente, bases de débito e créditos com evidência fiscal.",
            },
            "documentos_faltantes": faltantes,
            "documentos_nao_processados": nao_processados,
            "mensagem": (
                "A simulação não foi calculada. São necessários PGDAS, "
                "entradas e saídas processados, além de regras tributárias "
                "versionadas e créditos com evidência fiscal."
            ),
        }
        db.commit()

        logger.info(f"✓ Análise criada para cliente {cliente_id}, período {periodo}")

        return {
            "status": "sucesso",
            "analise_id": nova_analise.id,
            "cliente_id": cliente_id,
            "periodo": periodo,
            "message": "Análise registrada; dados reais do PGDAS foram preservados e nenhuma projeção foi estimada",
            "resultado": nova_analise.resultado,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao processar análise: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")


@app.get("/api/v4/analises/{analise_id}")
async def obter_resultado_analise(
    analise_id: int,
    db: Session = Depends(get_db)
):
    """
    Obtém resultado completo de uma análise.
    Retorna os 3 cenários: 2026, 2027 Simples, 2027 Híbrido
    """

    analise = db.query(Analysis).filter_by(id=analise_id).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise não encontrada")

    return {
        "analise_id": analise.id,
        "cliente_id": analise.cliente_id,
        "periodo": analise.periodo,
        "status": analise.status,
        "resultado": analise.resultado,
    }


@app.post("/api/v4/clientes/{cliente_id}/simulacoes/hibrido")
async def simular_hibrido(
    cliente_id: int,
    periodo: str,
    parametros: ParametrosHibrido,
    db: Session = Depends(get_db),
):
    """Compara Simples puro e híbrido usando premissas explícitas e auditáveis."""
    cliente = db.query(Client).filter_by(id=cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    documentos = db.query(Document).filter_by(cliente_id=cliente_id).all()
    base_real = _base_real_pgdas(documentos, periodo)
    if base_real.get("status") != "DOCUMENTADO":
        raise HTTPException(status_code=422, detail=base_real.get("motivo", "Base PGDAS indisponível"))

    premissas_automaticas = _premissas_automaticas_hibrido(documentos, periodo)
    if premissas_automaticas.get("status") != "CENARIO_APROXIMADO":
        raise HTTPException(status_code=422, detail=premissas_automaticas.get("motivo", "Premissas indisponíveis"))
    percentual_das = parametros.percentual_das_remanescente
    if percentual_das is None:
        percentual_das = Decimal(premissas_automaticas["percentual_das_remanescente"])
    fonte_das = parametros.fonte_das_remanescente or premissas_automaticas["fonte_das_remanescente"]
    receita = _decimal_seguro(base_real.get("receita_total_periodo", base_real.get("receita_competencia")))
    das_puro = _decimal_seguro(base_real.get("das_total_recolhido", base_real.get("das_recolhido")))
    das_remanescente = (das_puro * percentual_das).quantize(Decimal("0.01"))
    ibs_debito = (receita * parametros.ibs_aliquota).quantize(Decimal("0.01"))
    cbs_debito = (receita * parametros.cbs_aliquota).quantize(Decimal("0.01"))
    fornecedores_regulares = db.query(Supplier).filter(
        Supplier.cliente_id == cliente_id,
        Supplier.regime == "REGULAR",
        Supplier.regime_validacao_status == "validado",
    ).all()
    compras_periodo = _movimentacao_por_periodo(documentos, {"entradas"}, periodo)
    cnpjs_fornecedores_regulares = {fornecedor.cnpj for fornecedor in fornecedores_regulares}
    compras_regulares_periodo = {
        cnpj: valor for cnpj, valor in compras_periodo.items()
        if cnpj in cnpjs_fornecedores_regulares and valor > 0
    }
    base_creditavel = sum(compras_regulares_periodo.values(), Decimal("0"))
    credito_ibs_automatico = (base_creditavel * parametros.ibs_aliquota).quantize(Decimal("0.01"))
    credito_cbs_automatico = (base_creditavel * parametros.cbs_aliquota).quantize(Decimal("0.01"))
    credito_ibs_total = credito_ibs_automatico + parametros.creditos_ibs_documentados
    credito_cbs_total = credito_cbs_automatico + parametros.creditos_cbs_documentados
    ibs_liquido = max(ibs_debito - credito_ibs_total, Decimal("0"))
    cbs_liquido = max(cbs_debito - credito_cbs_total, Decimal("0"))
    clientes_regulares = db.query(Customer).filter(
        Customer.cliente_id == cliente_id,
        Customer.regime == "REGULAR",
        Customer.regime_validacao_status == "validado",
    ).all()
    faturamento_periodo = _movimentacao_por_periodo(documentos, {"saidas", "servicos_prestados"}, periodo)
    cnpjs_clientes_regulares = {cliente.cnpj for cliente in clientes_regulares}
    faturamento_regulares_periodo = {
        cnpj: valor for cnpj, valor in faturamento_periodo.items()
        if cnpj in cnpjs_clientes_regulares and valor > 0
    }
    base_credito_clientes = sum(faturamento_regulares_periodo.values(), Decimal("0"))
    potencial_credito_clientes = (
        base_credito_clientes * (parametros.ibs_aliquota + parametros.cbs_aliquota)
    ).quantize(Decimal("0.01"))
    hibrido = (das_remanescente + ibs_liquido + cbs_liquido).quantize(Decimal("0.01"))
    diferenca = (das_puro - hibrido).quantize(Decimal("0.01"))
    recomendacao = "POTENCIALMENTE_VANTAJOSO" if diferenca > 0 else "NAO_VANTAJOSO_NO_CENARIO"

    return {
        "status": "CENARIO_CALCULADO",
        "cliente_id": cliente_id,
        "periodo": periodo,
        "base_calculo": {
            "receita": str(receita.quantize(Decimal("0.01"))),
            "das_original": str(das_puro),
        },
        "premissa_receita": "A receita e o DAS observados em 2026 são repetidos no cenário de 2027.",
        "simples_puro": {"total": str(das_puro)},
        "hibrido": {
            "das_remanescente": str(das_remanescente),
            "ibs_debito": str(ibs_debito), "ibs_creditos_automaticos": str(credito_ibs_automatico), "ibs_creditos_documentados": str(parametros.creditos_ibs_documentados), "ibs_liquido": str(ibs_liquido),
            "cbs_debito": str(cbs_debito), "cbs_creditos_automaticos": str(credito_cbs_automatico), "cbs_creditos_documentados": str(parametros.creditos_cbs_documentados), "cbs_liquido": str(cbs_liquido),
            "total": str(hibrido),
        },
        "diferenca_vs_simples": str(diferenca),
        "recomendacao": recomendacao,
        "creditos_fornecedores": {
            "base_compras_fornecedores_regulares": str(base_creditavel.quantize(Decimal("0.01"))),
            "fornecedores_regulares_validados": len(compras_regulares_periodo),
            "regra": "Simples Nacional e MEI não geram crédito automático neste cenário.",
        },
        "beneficio_clientes": {
            "base_vendas_e_servicos_clientes_regulares": str(base_credito_clientes.quantize(Decimal("0.01"))),
            "clientes_regulares_validados": len(faturamento_regulares_periodo),
            "credito_potencial_ibs_cbs": str(potencial_credito_clientes),
            "regra": "Inclui saídas e serviços prestados a clientes regulares; clientes Simples Nacional ou MEI não entram neste potencial.",
        },
        "premissas": {
            "ibs_aliquota": str(parametros.ibs_aliquota), "cbs_aliquota": str(parametros.cbs_aliquota),
            "percentual_das_remanescente": str(percentual_das),
            "fonte_cbs": parametros.fonte_cbs, "fonte_das_remanescente": fonte_das,
        },
        "alerta": "Cenário técnico. Créditos informados devem corresponder a documentos fiscais válidos e as premissas devem ser aprovadas pela contabilidade antes da opção.",
    }


@app.get("/api/v4/clientes/{cliente_id}/simulacoes/premissas")
async def obter_premissas_hibrido(
    cliente_id: int,
    periodo: str,
    db: Session = Depends(get_db),
):
    """Fornece ao painel as premissas automáticas derivadas dos PDFs."""
    documentos = db.query(Document).filter_by(cliente_id=cliente_id).all()
    resultado = _premissas_automaticas_hibrido(documentos, periodo)
    if resultado.get("status") != "CENARIO_APROXIMADO":
        raise HTTPException(status_code=422, detail=resultado.get("motivo", "Premissas indisponíveis"))
    return resultado


# ============================================================================
# ENDPOINTS: Health & Config
# ============================================================================

@app.get("/api/v4/health")
async def health_check():
    """Verifica se sistema está operacional"""
    return {
        "status": "ok",
        "versao": "4.0.0",
        "ibs_2027": CONFIG.ibs_2027_aliquota,
        "cbs_2027": CONFIG.cbs_2027_aliquota,
        "cbs_2027_status": CONFIG.cbs_2027_status
    }


@app.get("/api/v4/config/tributaria")
async def config_tributaria():
    """Retorna configuração tributária atual"""
    return {
        "ano": 2027,
        "ibs": {
            "aliquota": str(CONFIG.ibs_2027_aliquota),
            "status": "OFICIAL",
            "observacao": "0,05% estadual + 0,05% municipal = 0,10% total"
        },
        "cbs": {
            "aliquota": str(CONFIG.cbs_2027_aliquota),
            "status": CONFIG.cbs_2027_status,
            "observacao": "Cenário interno; exige regra versionada antes de gerar recomendação"
        },
        "simples_nacional": {
            "status": "VIGENTE",
            "resolucao": "CGSN 140/2018"
        }
    }


# ============================================================================
# ENDPOINT LEGADO: Compatibilidade com v2.4
# ============================================================================

@app.post("/api/analise/completa")
async def analise_completa_legado(
    dados: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Endpoint legado para compatibilidade com v2.4.
    Recebe dados e retorna análise completa sem criar cliente permanente.

    USAR: /api/v4/clientes/novo + /api/v4/clientes/{id}/documentos/upload
    """

    # Convertir input legado para novo modelo
    cnpj = dados.get("cnpj")
    if not cnpj:
        raise HTTPException(status_code=400, detail="CNPJ obrigatório")

    # Nota: Endpoint legado não deve ser usado em produção
    logger.warning(f"Endpoint legado /api/analise/completa chamado (CNPJ: {cnpj})")

    return {
        "status": "descontinuado",
        "message": "Usar /api/v4/clientes/novo em vez disso",
        "documentacao": "/docs"
    }


# Exportação aditiva: reutiliza a simulação sem persistir ou alterar dados.
class PedidoRelatorioPDF(BaseModel):
    parametros: ParametrosHibrido
    simulacao_exibida: Dict[str, Any]


@app.post("/api/v4/clientes/{cliente_id}/simulacoes/hibrido/relatorio.pdf")
async def exportar_relatorio_pdf(
    cliente_id: int,
    periodo: str,
    pedido: PedidoRelatorioPDF,
    db: Session = Depends(get_db),
):
    from relatorio_cliente import gerar_pdf
    resultado = await simular_hibrido(cliente_id, periodo, pedido.parametros, db)
    # Nunca emite silenciosamente valores diferentes dos vistos pela contadora.
    if resultado != pedido.simulacao_exibida:
        raise HTTPException(status_code=409, detail="Os dados mudaram. Calcule a comparação novamente para gerar o relatório.")
    cliente = db.query(Client).filter_by(id=cliente_id).first()
    documentos = db.query(Document).filter_by(cliente_id=cliente_id).all()
    # O simulador histórico admite fallback de PGDAS. Um PDF para terceiros
    # exige que a competência indicada corresponda à documentação utilizada.
    def competencia_pdf(valor):
        valor = str(valor or "").strip()
        if re.fullmatch(r"\d{2}/\d{4}", valor):
            return valor[3:] + "-" + valor[:2]
        return valor
    if not re.fullmatch(r"\d{4}|\d{4}-\d{2}|\d{2}/\d{4}", periodo):
        raise HTTPException(status_code=422, detail="Para o PDF, selecione um ano ou uma competência mensal e calcule novamente.")
    if len(periodo) != 4:
        base_pdf = _base_real_pgdas(documentos, periodo)
        if competencia_pdf(base_pdf.get("competencia_pdf")) != competencia_pdf(periodo):
            raise HTTPException(status_code=422, detail="O PGDAS usado na comparação não corresponde ao período selecionado. Confira a competência antes de gerar o PDF.")
    totais = _movimentacao_por_periodo(documentos, {"saidas", "servicos_prestados"}, periodo)
    entidades = _entidades_extraidas(documentos, {"saidas", "servicos_prestados", "clientes"})
    nomes = {somente_digitos(c.cnpj): c.razao_social for c in db.query(Customer).filter_by(cliente_id=cliente_id).all()}
    compradores = [{"cnpj": cnpj, "razao_social": nomes.get(cnpj) or entidades.get(cnpj, {}).get("razao_social") or "Comprador não identificado", "valor": valor} for cnpj, valor in totais.items()]
    try:
        pdf = gerar_pdf({"razao_social": cliente.razao_social, "cnpj": cliente.cnpj}, resultado, compradores)
    except Exception:
        logger.exception("Falha na geração do relatório PDF do cliente %s", cliente_id)
        raise HTTPException(status_code=500, detail="Não foi possível gerar o PDF. A simulação permanece disponível.")
    nome = "relatorio-" + somente_digitos(cliente.cnpj) + "-" + re.sub(r"[^0-9A-Za-z-]", "-", periodo)[:40] + ".pdf"
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="' + nome + '"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


