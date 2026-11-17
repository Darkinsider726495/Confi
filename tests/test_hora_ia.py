"""A IA recebe a data e a hora de agora em cada pedido (antes ela chutava: «boa tarde» às 19h no celular do criador)."""
import datetime as dt, unittest
from unittest import mock
import _ambiente  # noqa: F401
import cerebro as C


def as_(h, m=0):
    class F(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 17, h, m)
    return mock.patch.object(dt, "datetime", F)


class HoraNaIA(unittest.TestCase):
    def test_o_sistema_leva_a_hora_e_o_periodo_certo(self):
        for h, periodo in ((3, "boa madrugada"), (9, "bom dia"), (15, "boa tarde"), (19, "boa noite")):
            with self.subTest(h), as_(h, 8):
                s = C._system()
            self.assertIn(f"{h:02d}:08", s)
            self.assertIn(f"«{periodo}»", s)
            self.assertIn("terça-feira, 17/11/2026", s)

    def test_cada_pedido_recalcula_a_hora(self):
        with as_(9):
            manha = C._system()
        with as_(21):
            noite = C._system()
        self.assertNotEqual(manha, noite)


if __name__ == "__main__":
    unittest.main()
