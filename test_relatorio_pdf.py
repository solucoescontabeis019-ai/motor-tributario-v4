"""Testes com banco temporário e empresas fictícias; não acessa a base real."""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
if ROOT.name == 'tests':
    ROOT = ROOT.parent
PROJECT = Path(os.environ.get('MOTOR_PROJECT', str(ROOT)))
sys.path[:0] = [str(ROOT / 'test_libs'), str(ROOT), str(PROJECT)]
os.environ.update(DATABASE_URL='sqlite:///:memory:', APP_ENV='development', REQUIRE_AUTH='false')
import unittest
from io import BytesIO
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from pypdf import PdfReader
import app_v4 as api
from models_v4 import Base, Client, Document, Customer
from relatorio_cliente import gerar_pdf


class RelatorioTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.session=sessionmaker(bind=self.engine)()
        self.session.add_all([Client(id=1,cnpj='11111111000111',razao_social='Alfa Serviços & Logística'),Client(id=2,cnpj='22222222000122',razao_social='Empresa Beta')])
        self.session.add(Document(cliente_id=1,tipo='pgdas',periodo='08/2026',status='processado',conteudo_parsed={'mes_competencia':'08/2026','rbt12_value':'2200000','receita_periodo_value':'146272.86','das_value':'18607.42'}))
        ops=[]
        for i,v in enumerate(['70000','30000','10000','5000'],1):
            cnpj=f'{i:014d}'
            self.session.add(Customer(cliente_id=1,cnpj=cnpj,razao_social=f'Comprador {i}',regime='REGULAR',regime_validacao_status='validado'))
            ops.append({'cnpj':cnpj,'data_emissao':'08/15/2026','valor_contabil':v})
        ops.append({'cnpj':'00000000000005','data_emissao':'07/15/2026','valor_contabil':'999999'})
        self.session.add(Document(cliente_id=1,tipo='saidas',periodo='2026',status='processado',conteudo_parsed={'operacoes':ops}))
        self.session.add(Document(cliente_id=1,tipo='saidas',periodo='2026',status='substituido',conteudo_parsed={'operacoes':[{'cnpj':'00000000000006','data_emissao':'08/15/2026','valor_contabil':'999999'}]}))
        self.session.add(Customer(cliente_id=2,cnpj='00000000000001',razao_social='SIGILO OUTRO CLIENTE'))
        self.session.commit()
        api.app.dependency_overrides[api.get_db]=lambda:self.session
        self.client=TestClient(api.app)
        self.params={'ibs_aliquota':'0.001','cbs_aliquota':'0.088','percentual_das_remanescente':'0.5058'}
        self.url='/api/v4/clientes/1/simulacoes/hibrido'
        self.result=self.client.post(self.url+'?periodo=08/2026',json=self.params).json()
    def tearDown(self):
        api.app.dependency_overrides.clear();self.session.close();self.engine.dispose()
    def export(self, result=None, client=1,params=None):
        return self.client.post(f'/api/v4/clientes/{client}/simulacoes/hibrido/relatorio.pdf?periodo=08/2026',json={'parametros':params or self.params,'simulacao_exibida':result or self.result})
    def test_pdf_matches_and_scopes_clients_period(self):
        before={t.name:self.session.execute(t.select()).all() for t in Base.metadata.sorted_tables}
        r=self.export();self.assertEqual(r.status_code,200,r.text[:200] if r.status_code!=200 else '')
        self.assertEqual(r.headers['cache-control'],'no-store');self.assertIn('11111111000111',r.headers['content-disposition'])
        pdf=PdfReader(BytesIO(r.content));self.assertEqual(len(pdf.pages),2)
        text='\n'.join(p.extract_text() for p in pdf.pages)
        for value in ['Alfa Serviços & Logística','18.607,42','Comprador 1','Comprador 2','Comprador 3','decisão final']:
            self.assertIn(value,text)
        for value in ['SIGILO OUTRO CLIENTE','Comprador 4','999.999','NaN']:
            self.assertNotIn(value,text)
        after={t.name:self.session.execute(t.select()).all() for t in Base.metadata.sorted_tables};self.assertEqual(before,after)
        if os.environ.get('PDF_TEST_OUTPUT'):
            (Path(os.environ['PDF_TEST_OUTPUT'])/'sample.pdf').write_bytes(r.content)
    def test_changed_simulation_rejected(self):
        edited=deepcopy(self.result);edited['hibrido']['total']='1.00'
        self.assertEqual(self.export(edited).status_code,409)
    def test_missing_client_and_missing_base(self):
        self.assertEqual(self.export(client=999).status_code,404)
        self.assertEqual(self.export(client=2).status_code,422)
    def test_period_fallback_is_not_exported_as_selected_month(self):
        result=self.client.post(self.url+'?periodo=09/2026',json=self.params).json()
        response=self.client.post(self.url+'/relatorio.pdf?periodo=09/2026',json={'parametros':self.params,'simulacao_exibida':result})
        self.assertEqual(response.status_code,422)
    def test_rates_and_annual_period(self):
        params={**self.params,'cbs_aliquota':'0.07'}
        result=self.client.post(self.url+'?periodo=2026',json=params).json()
        response=self.client.post(self.url+'/relatorio.pdf?periodo=2026',json={'parametros':params,'simulacao_exibida':result})
        self.assertEqual(response.status_code,200)
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
        self.assertIn('7,00%',text)
        self.assertIn('999.999,00',text)
        self.assertIn('precisam ser conciliadas',text)
    def test_auth_protects_export(self):
        with patch.object(api.CONFIG,'require_auth',True):
            self.assertEqual(self.export().status_code,401)
    def test_pdf_failure_does_not_break_simulation(self):
        with patch('relatorio_cliente.gerar_pdf',side_effect=RuntimeError('test')):
            self.assertEqual(self.export().status_code,500)
            self.assertEqual(self.client.post(self.url+'?periodo=08/2026',json=self.params).json(),self.result)
    def test_dynamic_recommendations_and_empty_clients(self):
        for delta,phrase in [('100','considerar o híbrido'),('-100','manter o Simples'),('0','mesmo total')]:
            s=deepcopy(self.result);s['diferenca_vs_simples']=delta
            pdf=PdfReader(BytesIO(gerar_pdf({'cnpj':'123','razao_social':'Teste <Empresa> & Cia'},s,[])))
            self.assertEqual(len(pdf.pages),2)
            text='\n'.join(p.extract_text() for p in pdf.pages)
            self.assertIn(phrase,text);self.assertIn('Não há compradores',text)
    def test_long_names(self):
        rows=[{'cnpj':str(i)*14,'razao_social':('Nome extenso de comprador com caracteres & < > '*6)[:255],'valor':str(i*100)} for i in [1,2,3]]
        data=gerar_pdf({'cnpj':'1'*14,'razao_social':('Empresa muito extensa '*15)[:255]},self.result,rows)
        self.assertEqual(len(PdfReader(BytesIO(data)).pages),2)
        if os.environ.get('PDF_TEST_OUTPUT'):
            (Path(os.environ['PDF_TEST_OUTPUT'])/'sample_long.pdf').write_bytes(data)

if __name__=='__main__':unittest.main()
