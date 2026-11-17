import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from friday import catalogo_apis, rede_autorizada, evolucao_auto

class RedeAutorizadaTests(unittest.TestCase):
    def test_rejeita_url_publica_http(self):
        with patch.dict(os.environ, {"FRIDAY_PEERS": json.dumps(["http://8.8.8.8:8765"])}):
            with self.assertRaises(ValueError):
                rede_autorizada.pares_configurados()

    def test_aceita_peer_lan_configurado(self):
        with patch.dict(os.environ, {"FRIDAY_PEERS": json.dumps(["http://192.168.1.22:8765/health"])}):
            self.assertEqual(rede_autorizada.pares_configurados(), ["http://192.168.1.22:8765"])

    def test_nao_varre_rede_sem_peers(self):
        with patch.dict(os.environ, {"FRIDAY_PEERS": "[]"}):
            self.assertEqual(rede_autorizada.descobrir(), [])

class CatalogoTests(unittest.TestCase):
    def test_parse_openapi_sem_executar_codigo(self):
        spec = {"openapi":"3.0.0","info":{"title":"Demo","version":"1"},"servers":[{"url":"https://api.example.com"}],"paths":{"/items":{"get":{"operationId":"listItems","summary":"List items"}}}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "openapi.json"
            p.write_text(json.dumps(spec), encoding="utf-8")
            got = catalogo_apis.analisar_openapi(p)
            self.assertEqual(got["endpoint_count"], 1)
            self.assertEqual(got["endpoints"][0]["operation_id"], "listItems")

    def test_rejeita_arquivo_grande(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "openapi.json"
            p.write_bytes(b" " * (catalogo_apis.MAX_SPEC_BYTES + 1))
            with self.assertRaises(ValueError):
                catalogo_apis.analisar_openapi(p)

class AutoPromotionTests(unittest.TestCase):
    def test_desativado_por_padrao(self):
        with patch.dict(os.environ, {}, clear=True):
            result = evolucao_auto.processar_fila()
            self.assertEqual(result[0]["status"], "desativado")

if __name__ == "__main__":
    unittest.main()
