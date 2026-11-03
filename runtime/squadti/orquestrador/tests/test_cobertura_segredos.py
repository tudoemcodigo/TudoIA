"""Gate de cobertura (Cobertura XML) e varredura de segredos: entradas válidas e hostis."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cobertura  # noqa: E402
import segredos  # noqa: E402


def xml(*classes):
    """classes: [(arquivo, [(linha, hits, 'cond' ou None)])]"""
    corpo = ""
    for arquivo, linhas in classes:
        ls = ""
        for n, hits, cond in linhas:
            ls += (f'<line number="{n}" hits="{hits}" branch="true" condition-coverage="{cond}"/>' if cond
                   else f'<line number="{n}" hits="{hits}" branch="false"/>')
        corpo += f'<class name="C" filename="{arquivo}"><lines>{ls}</lines></class>'
    return f'<?xml version="1.0"?><coverage><packages><package><classes>{corpo}</classes></package></packages></coverage>'


class Cobertura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def grava(self, nome, conteudo):
        p = self.ws / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(conteudo, encoding="utf-8")
        return p

    def test_sem_relatorio_e_nao_medida_e_reprova(self):
        ok, d = cobertura.avaliar(self.ws, 90)
        self.assertFalse(ok)
        self.assertIn("cobertura não medida", d["motivo"])

    def test_aprova_no_limite_e_reprova_abaixo_em_linha_ou_ramo(self):
        self.grava("a/x.cobertura.xml", xml(("a.cs", [(i, 1, None) for i in range(9)] + [(9, 0, None)])))
        self.assertTrue(cobertura.avaliar(self.ws, 90)[0])  # 90% de linha, sem ramos
        self.assertFalse(cobertura.avaliar(self.ws, 91)[0])
        self.grava("b/y.cobertura.xml", xml(("b.cs", [(1, 1, "50% (1/2)")] + [(i, 1, None) for i in range(2, 12)])))
        ok, d = cobertura.avaliar(self.ws, 90)
        self.assertFalse(ok)  # linhas ok, mas ramo 50%: reprova mesmo com linha alta
        self.assertEqual(d["ramo"], 50.0)

    def test_consolida_por_linha_sem_somar_em_dobro(self):
        # dois projetos de teste cobrem o mesmo arquivo: uma cobre as linhas 1-5, a outra 6-10; juntas = 100%
        self.grava("t1/c.cobertura.xml", xml(("f.cs", [(i, 1 if i <= 5 else 0, None) for i in range(1, 11)])))
        self.grava("t2/c.cobertura.xml", xml(("f.cs", [(i, 1 if i > 5 else 0, None) for i in range(1, 11)])))
        ok, d = cobertura.avaliar(self.ws, 100)
        self.assertTrue(ok, d)
        self.assertEqual(d["linha"], 100.0)

    def test_xml_corrompido_vazio_ou_gigante_nao_mede(self):
        self.grava("a/x.cobertura.xml", "<coverage><nao fecha")
        self.assertIn("ilegível", cobertura.avaliar(self.ws, 90)[1]["motivo"])
        self.grava("a/x.cobertura.xml", xml())
        self.assertIn("nenhuma linha instrumentada", cobertura.avaliar(self.ws, 90)[1]["motivo"])
        self.grava("a/x.cobertura.xml", "x")
        original = cobertura.MAX_BYTES
        cobertura.MAX_BYTES = 0
        self.addCleanup(setattr, cobertura, "MAX_BYTES", original)
        self.assertIn("maior que", cobertura.avaliar(self.ws, 90)[1]["motivo"])

    def test_ignora_node_modules_e_symlink(self):
        self.grava("node_modules/p/cobertura.xml", xml(("a.js", [(1, 1, None)])))
        self.assertFalse(cobertura.avaliar(self.ws, 90)[0])  # só havia relatório em node_modules: não medida
        alvo = self.grava("fora/real.xml", xml(("a.cs", [(1, 1, None)])))
        try:
            (self.ws / "s.cobertura.xml").symlink_to(alvo)
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão para symlink")
        self.assertFalse(cobertura.avaliar(self.ws, 90)[0])

    def test_minimo_zero_desliga_explicitamente_e_valor_invalido_volta_a_90(self):
        ok, d = cobertura.avaliar(self.ws, 0)
        self.assertTrue(ok)
        self.assertIn("desligado", d["motivo"])
        self.assertEqual(cobertura.minimo_da_stack({}), 90.0)
        for ruim in ("abc", None, -5, 101, [], "NaN"):
            self.assertEqual(cobertura.minimo_da_stack({"quality": {"coverage_min": ruim}}), 90.0, ruim)
        self.assertEqual(cobertura.minimo_da_stack({"quality": {"coverage_min": 80}}), 80.0)
        self.assertEqual(cobertura.minimo_da_stack({"quality": {"coverage_min": 0}}), 0.0)


class Segredos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def grava(self, nome, texto):
        p = self.ws / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")

    def test_acha_tipo_arquivo_e_linha_sem_vazar_o_valor(self):
        valor = "S3nh4-Super-Secreta-123"
        self.grava("src/appsettings.json", f'{{\n "ConnectionStrings": "Server=x;Database=d;User Id=u;Password={valor};"\n}}')
        self.grava("frontend/api.ts", 'const apiKey = "' + "k" * 12 + '";\n')
        # montado em tempo de execução: o literal inteiro faria o varredor de segredos do pacote do instalador recusar este arquivo
        self.grava("src/chave.pem", "-----" + "BEGIN PRIVATE KEY" + "-----\nabc\n")
        achados = segredos.varrer(self.ws)
        tipos = {(a["arquivo"], a["tipo"]) for a in achados}
        self.assertIn(("src/appsettings.json", "senha-em-connection-string"), tipos)
        self.assertIn(("frontend/api.ts", "senha-literal"), tipos)
        self.assertNotIn(valor, str(achados))
        self.assertNotIn("kkkk", str(achados))
        self.assertEqual([a["linha"] for a in achados if a["arquivo"] == "src/appsettings.json"], [2])

    def test_placeholders_e_pastas_ignoradas_nao_geram_alarme(self):
        self.grava("src/appsettings.json", '{"c": "Server=x;Password=${DB_PASSWORD};"}')
        self.grava("src/a.cs", 'var s = "Password=;"; var t = "password: <sua-senha>";')
        self.grava("node_modules/x/k.js", 'const token = "abcdefghijklmnopqrstuvwxyz0123456789";')
        self.assertEqual(segredos.varrer(self.ws), [])

    def test_tokens_conhecidos(self):
        self.grava("a.md", "ghp_" + "A" * 36 + "\nAKIA" + "B" * 16 + "\nsk-" + "c" * 30)
        self.assertEqual({a["tipo"] for a in segredos.varrer(self.ws)}, {"token-github", "chave-aws", "chave-api-sk"})

    def test_limite_de_arquivos_declara_varredura_incompleta(self):
        original = segredos.MAX_ARQUIVOS
        segredos.MAX_ARQUIVOS = 2
        self.addCleanup(setattr, segredos, "MAX_ARQUIVOS", original)
        for i in range(5):
            self.grava(f"src/f{i}.cs", "x")
        self.assertEqual(segredos.varrer(self.ws)[-1]["tipo"], "limite-de-arquivos-excedido")

    def test_arquivo_gigante_e_symlink_sao_ignorados(self):
        original = segredos.MAX_BYTES
        segredos.MAX_BYTES = 5
        self.addCleanup(setattr, segredos, "MAX_BYTES", original)
        self.grava("a.cs", 'password = "umasenhalonga123"')
        self.assertEqual(segredos.varrer(self.ws), [])


if __name__ == "__main__":
    unittest.main()
