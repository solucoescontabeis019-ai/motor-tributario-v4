import os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).parent
sys.path[:0]=[str(ROOT),os.environ.get('MOTOR_TEST_LIBS',str(ROOT)),os.environ.get('MOTOR_PROJECT',str(ROOT))]
os.environ.update(DATABASE_URL='sqlite:///:memory:',REQUIRE_AUTH='false',APP_ENV='development')
from io import BytesIO
from unittest.mock import patch
from pypdf import PdfReader
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import app_v4 as api
from models_v4 import Base,Client,Customer,Supplier

class TestCadastros(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.db=sessionmaker(bind=self.engine)()
        self.db.add_all([Client(id=1,cnpj='11111111000111',razao_social='Empresa Alfa & Cia'),Client(id=2,cnpj='22222222000122',razao_social='Empresa Beta')])
        self.db.add_all([Customer(cliente_id=1,cnpj='33333333000133',razao_social='Comprador regular',total_faturamento=1000,regime='REGULAR',regime_validacao_status='validado',periodo='2026-01-a-08'),
            Customer(cliente_id=1,cnpj='44444444000144',razao_social='Comprador pendente sem movimento',total_faturamento=0,regime='NAO_VALIDADO',regime_validacao_status='não_validado'),
            Supplier(cliente_id=1,cnpj='55555555000155',razao_social='Fornecedor Simples',total_compras=500,regime='SIMPLES_NACIONAL',regime_validacao_status='validado',periodo='2026'),
            Supplier(cliente_id=2,cnpj='66666666000166',razao_social='SIGILO BETA',total_compras=999)])
        self.db.commit();api.app.dependency_overrides[api.get_db]=lambda:self.db
        self.client=TestClient(api.app);self.url='/api/v4/clientes/1/classificacoes/relatorio.pdf'
    def tearDown(self):api.app.dependency_overrides.clear();self.db.close();self.engine.dispose()
    def test_complete_pdf_isolated_readonly(self):
        before={t.name:self.db.execute(t.select()).all() for t in Base.metadata.sorted_tables}
        r=self.client.get(self.url);self.assertEqual(r.status_code,200)
        reader=PdfReader(BytesIO(r.content));self.assertEqual(len(reader.pages),2)
        texto=' '.join(' '.join(p.extract_text().split()) for p in reader.pages)
        for s in ['Empresa Alfa & Cia','Comprador regular','Comprador pendente sem movimento','Fornecedor Simples','89,00','2026-01-a-08','Não apurado automaticamente']:
            self.assertIn(s,texto)
        self.assertNotIn('SIGILO BETA',texto);self.assertEqual(r.headers['cache-control'],'no-store')
        self.assertEqual(before,{t.name:self.db.execute(t.select()).all() for t in Base.metadata.sorted_tables})
        if os.environ.get('PDF_TEST_OUTPUT'):
            (Path(os.environ['PDF_TEST_OUTPUT'])/'sample.pdf').write_bytes(r.content)
    def test_auth_missing_and_rates(self):
        with patch.object(api.CONFIG,'require_auth',True):self.assertEqual(self.client.get(self.url).status_code,401)
        self.assertEqual(self.client.get(self.url.replace('/1/','/999/')).status_code,404)
        self.assertEqual(self.client.get(self.url+'?cbs_aliquota=-1').status_code,422)
        r=self.client.get(self.url+'?cbs_aliquota=0.07');texto=''.join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages);self.assertIn('71,00',texto)
    def test_empty(self):
        self.db.query(Supplier).filter_by(cliente_id=2).delete();self.db.commit()
        self.assertEqual(self.client.get(self.url.replace('/1/','/2/')).status_code,422)
    def test_pagination(self):
        for i in range(65):self.db.add(Supplier(cliente_id=1,cnpj=f'{i:014}',razao_social=f'Fornecedor {i:03d} '+('nome comprido < > & '*10),total_compras=i,regime='REGULAR',regime_validacao_status='validado',periodo='2026'))
        self.db.commit();r=self.client.get(self.url);self.assertEqual(r.status_code,200)
        reader=PdfReader(BytesIO(r.content));self.assertGreater(len(reader.pages),3)
        texto='\n'.join(p.extract_text() for p in reader.pages)
        for i in range(65):self.assertIn(f'Fornecedor {i:03d}',texto)
        if os.environ.get('PDF_TEST_OUTPUT'):
            (Path(os.environ['PDF_TEST_OUTPUT'])/'sample_long.pdf').write_bytes(r.content)

if __name__=='__main__':unittest.main()
