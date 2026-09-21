"""
Motor Tributário v4.0 - Database Connection
Schema multicliente com Client → Analysis → Document
Sem hardcodes de WASHINGTON ou dados de teste.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from models_v4 import Base
from config_v4 import get_config
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE CONNECTION
# ============================================================================

config = get_config()

engine_options = {"echo": False, "poolclass": NullPool}
if config.database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(config.database_url, **engine_options)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db() -> Session:
    """Dependency para injetar sessão do banco em endpoints FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Cria todas as tabelas no banco de dados.

    Tabelas criadas:
    - clients: Clientes da plataforma
    - analyses: Análises realizadas
    - documents: Documentos carregados
    - suppliers: Fornecedores consolidados por cliente
    - customers: Clientes (no sentido de vendas) consolidados por cliente
    - tax_rules: Regras tributárias versionadas
    - credits: Créditos calculados
    - debits: Débitos calculados
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Banco de dados inicializado com sucesso")
        logger.info(f"  Tabelas criadas: {len(Base.metadata.tables)} tabelas")
        return True
    except Exception as e:
        logger.error(f"✗ Erro ao inicializar banco de dados: {str(e)}")
        return False


def seed_db():
    """
    NÃO INSERE DADOS DE TESTE.

    MOTIVO: v4.0 é multicliente genérico.
    - Sem WASHINGTON hardcoded
    - Sem dados de teste padrão
    - Usuário cria clientes via API

    Se precisar de fixture para testes, será criado via:
    POST /api/v4/clientes/novo com dados de teste
    """
    logger.info("✓ Sem dados de seed (v4.0 é multicliente genérico)")


def reset_db():
    """
    CUIDADO: Apaga TODOS os dados.
    Use apenas em desenvolvimento.
    """
    logger.warning("⚠️ Deletando TODAS as tabelas...")
    Base.metadata.drop_all(bind=engine)
    logger.warning("✓ Tabelas deletadas")

    logger.info("Recriando schema...")
    init_db()
    logger.info("✓ Schema recriado")


def health_check() -> bool:
    """Verifica se banco de dados está acessível"""
    try:
        db = SessionLocal()
        # Tentar uma query simples
        db.execute(text("SELECT 1"))
        db.close()
        return True
    except Exception as e:
        logger.error(f"✗ Banco de dados indisponível: {str(e)}")
        return False


# ============================================================================
# UTILITIES
# ============================================================================

def create_test_client(db: Session, cnpj: str, razao_social: str):
    """
    Cria cliente de teste para desenvolvimento.

    Uso:
    from database_v4 import SessionLocal, create_test_client
    db = SessionLocal()
    create_test_client(db, "04.286.335/0001-79", "WASHINGTON L LOPES COSMOPOLIS")
    """
    from models_v4 import Client
    from normalizer_v4 import DataNormalizer
    from datetime import date

    cnpj_norm = DataNormalizer.normalize_cnpj(cnpj)

    existing = db.query(Client).filter_by(cnpj=cnpj_norm).first()
    if existing:
        logger.warning(f"Cliente {cnpj_norm} já existe")
        return existing

    novo = Client(
        cnpj=cnpj_norm,
        razao_social=razao_social,
        created_at=date.today()
    )
    db.add(novo)
    db.commit()

    logger.info(f"✓ Cliente de teste criado: {razao_social}")
    return novo


if __name__ == "__main__":
    # Inicializar banco quando executado diretamente
    print("Inicializando banco de dados v4.0...")

    if health_check():
        print("✓ Banco de dados está acessível")
    else:
        print("✗ Banco de dados NÃO está acessível")

    print("\nIniciando setup...")
    init_db()
    seed_db()

    print("\n✓ Setup completo!")
