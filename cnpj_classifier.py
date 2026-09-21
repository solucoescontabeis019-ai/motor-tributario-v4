"""Consulta cadastral de CNPJ para a triagem de crédito no cenário híbrido."""

import re
import asyncio
from typing import Any, Dict

import httpx


def somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


async def consultar_regime_cnpj(cnpj: str, client: httpx.AsyncClient) -> Dict[str, Any]:
    """Classifica pelo cadastro retornado pela BrasilAPI, sem inferir em falha."""
    cnpj_limpo = somente_digitos(cnpj)
    if len(cnpj_limpo) != 14:
        return {"cnpj": cnpj_limpo, "regime": "NAO_VALIDADO", "status": "invalidado", "fonte": "CNPJ inválido"}
    try:
        resposta = None
        for tentativa in range(3):
            resposta = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}")
            if resposta.status_code != 429:
                break
            await asyncio.sleep(0.8 * (tentativa + 1))
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        return {"cnpj": cnpj_limpo, "regime": "NAO_VALIDADO", "status": "nao_validado", "fonte": f"Consulta indisponível: {type(erro).__name__}"}

    # MEI também integra o Simples; manter a categoria própria permite a regra
    # de crédito explícita solicitada pelo usuário.
    if dados.get("opcao_pelo_mei"):
        regime = "MEI"
    elif dados.get("opcao_pelo_simples"):
        regime = "SIMPLES_NACIONAL"
    else:
        regime = "REGULAR"
    return {
        "cnpj": cnpj_limpo,
        "regime": regime,
        "status": "validado",
        "fonte": "BrasilAPI/CNPJ",
        "razao_social": dados.get("razao_social") or dados.get("nome_fantasia"),
    }
