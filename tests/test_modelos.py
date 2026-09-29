"""Pruebas de recuperación de parámetros y de consistencia. Ejecutar:
    python -m unittest discover -s tests -v      (o pytest)
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from afp import econometria as eco  # noqa: E402
from afp import etl_valores_cuota as etl  # noqa: E402


class TestHMM(unittest.TestCase):
    def test_recupera_parametros_dos_estados(self):
        rng = np.random.default_rng(1)
        A = np.array([[0.95, 0.05], [0.15, 0.85]])
        mu = np.array([[0.01, 0.005], [-0.02, -0.004]])
        cov = [np.diag([0.02, 0.008]) ** 2, np.diag([0.06, 0.02]) ** 2]
        s, X = 0, []
        for _ in range(1500):
            X.append(rng.multivariate_normal(mu[s], cov[s]))
            s = rng.choice(2, p=A[s])
        m = eco.ajustar_hmm(np.array(X), K=2, n_inicios=8, semilla=3)
        np.testing.assert_allclose(np.diag(m["A"]), np.diag(A), atol=0.04)
        np.testing.assert_allclose(np.sqrt(np.diag(m["cov"][1])), [0.06, 0.02], rtol=0.15)
        np.testing.assert_allclose(m["mu"][0], mu[0], atol=0.004)

    def test_bic_prefiere_un_estado_si_no_hay_regimenes(self):
        X = np.random.default_rng(2).normal(0, 0.02, (400, 2))
        mejor, _ = eco.seleccionar_hmm(X, Ks=(1, 2), n_inicios=4)
        self.assertEqual(mejor["K"], 1)


class TestGARCH(unittest.TestCase):
    def test_recupera_parametros(self):
        rng = np.random.default_rng(7)
        w, a, b, n = 2e-6, 0.08, 0.90, 6000
        r = np.empty(n); s2 = w / (1 - a - b)
        for t in range(n):
            r[t] = rng.normal() * np.sqrt(s2)
            s2 = w + a * r[t] ** 2 + b * s2
        g = eco.ajustar_garch(r)
        self.assertAlmostEqual(g["alpha"], a, delta=0.025)
        self.assertAlmostEqual(g["beta"], b, delta=0.03)
        self.assertLess(g["persistencia"], 1)


class TestETL(unittest.TestCase):
    def test_numero_formato_chileno(self):
        self.assertEqual(etl._num("95.178,58"), 95178.58)
        self.assertEqual(etl._num("8848328831207"), 8848328831207.0)
        self.assertTrue(np.isnan(etl._num("")))

    def test_normaliza_tildes(self):
        self.assertEqual(etl._norm("Santa María "), "SANTA MARIA")



class TestPension(unittest.TestCase):
    def setUp(self):
        from afp import mortalidad
        self.mo = mortalidad

    def test_cnu_valor_de_referencia(self):
        # Validado contra el simulador Excel 100% en fórmulas (hoja Simulador_Pension)
        self.assertAlmostEqual(self.mo.cnu(65, "H", 2026), 176.966, places=2)

    def test_mujer_vive_mas_y_cnu_mayor(self):
        self.assertGreater(self.mo.esperanza_vida(65, "M", 2026), self.mo.esperanza_vida(65, "H", 2026))
        self.assertGreater(self.mo.cnu(65, "M", 2026), self.mo.cnu(65, "H", 2026))

    def test_mejoramiento_de_mortalidad(self):
        self.assertLess(self.mo.qx(70, 2050, "H"), self.mo.qx(70, 2026, "H"))

    def test_mayor_tasa_menor_cnu(self):
        self.assertLess(self.mo.cnu(65, "H", 2026, 0.05), self.mo.cnu(65, "H", 2026, 0.02))


class TestSimulacion(unittest.TestCase):
    def setUp(self):
        from afp import simulacion
        self.sim = simulacion
        self.edades = 25 + np.arange(480) // 12

    def test_pesos_suman_uno(self):
        for W in (self.sim.pesos_defecto(self.edades, "H"), self.sim.pesos_ciclo_vida(self.edades)):
            np.testing.assert_allclose(W.sum(1), 1.0)

    def test_glidepath_oficial_tope_y_piso(self):
        g = self.sim.crecimiento_glidepath(np.arange(18, 76))
        np.testing.assert_allclose(g[:21], 0.95)                   # 18-38: tope definitivo (Res. Ex. 1195)
        self.assertAlmostEqual(g[63 - 18], 0.29)                   # piso a los 63
        self.assertTrue(np.all(np.diff(g[:63 - 18 + 1]) <= 1e-12))  # nunca sube antes del piso

    def test_glidepath_con_tope_90_reproduce_la_consulta(self):
        from afp import config
        gp = dict(config.GLIDEPATH, tope_inicial=0.90)
        np.testing.assert_allclose(self.sim.crecimiento_glidepath(np.arange(18, 76), gp),
                                   config.GLIDEPATH["curva_consulta"]["crecimiento"])

    def test_pesos_replican_la_exposicion_de_crecimiento(self):
        from afp import config
        gm = np.array([config.GLIDEPATH["crecimiento_multifondos"][f] for f in config.FONDOS])
        g = np.array([0.95, 0.824, 0.70, 0.50, 0.29, 0.10, 0.082])
        W = self.sim.pesos_desde_crecimiento(g)
        np.testing.assert_allclose(W @ gm, g, atol=1e-12)
        np.testing.assert_allclose(W.sum(1), 1.0)
        self.assertTrue((np.count_nonzero(np.abs(W) > 1e-12, axis=1) <= 2).all())
        W_tope = self.sim.pesos_desde_crecimiento(g, dict(config.GLIDEPATH, extrapolar=False))
        self.assertTrue((W_tope >= 0).all())
        np.testing.assert_allclose(W_tope[0], [1, 0, 0, 0, 0])

    def test_fondo_por_defecto_segun_ley(self):
        W = self.sim.pesos_defecto(np.array([30, 40, 52, 60]), "M")
        self.assertEqual([int(i) for i in W.argmax(1)], [1, 2, 3, 3])     # B, C, D, D (mujer: D desde 51)

    def test_retorno_cero_devuelve_aportes(self):
        R = np.zeros((2, 12, 5)); aporte = np.full(12, 1.0)
        W = self.sim.pesos_fijo("C", np.arange(12))
        np.testing.assert_allclose(self.sim.acumular(R, W, aporte), 12.0)

    def test_reactivo_sin_senales_iguala_al_defecto(self):
        # Con un umbral imposible (-100%) la regla nunca se activa: debe replicar al fondo por defecto.
        from afp import config
        R = np.random.default_rng(5).normal(0.004, 0.03, (200, 480, 5))
        reg = dict(config.REACTIVO, umbral_caida_3m=-1.0)
        tab, pens = self.sim.simular_estrategias(R, "H", reactivo=reg)
        np.testing.assert_allclose(pens["Reactivo (market timing)"], pens["Por defecto (ley)"], rtol=1e-12)
        self.assertEqual(tab.attrs["cambios_reactivo_mediana"], 0)


class TestIncertidumbre(unittest.TestCase):
    def setUp(self):
        from afp import incertidumbre
        self.inc = incertidumbre
        rng = np.random.default_rng(4)
        self.modelo = {"K": 3, "pi": np.array([0.5, 0.3, 0.2]),
                       "A": np.array([[0.90, 0.07, 0.03], [0.05, 0.90, 0.05], [0.10, 0.10, 0.80]]),
                       "mu": rng.normal(0, 0.01, (3, 2)),
                       "cov": np.array([np.diag([0.01, 0.005]) ** 2, np.diag([0.03, 0.02]) ** 2,
                                        np.diag([0.08, 0.04]) ** 2])}
        self.modelo["gamma"] = np.eye(3)[rng.integers(0, 3, 50)]

    def test_alinear_estados_deshace_una_permutacion(self):
        perm = [2, 0, 1]
        mod = {k: (v[perm] if k in ("mu", "cov", "pi") else v) for k, v in self.modelo.items()}
        mod["A"] = self.modelo["A"][np.ix_(perm, perm)]; mod["gamma"] = self.modelo["gamma"][:, perm]
        al = self.inc.alinear_estados(mod, self.modelo)
        for k in ("mu", "cov", "A", "pi", "gamma"):
            np.testing.assert_allclose(al[k], self.modelo[k])

    def test_posterior_consistente_con_el_ajuste(self):
        from afp import econometria as eco
        X = eco.simular_hmm(self.modelo, 400, np.random.default_rng(8))
        m = eco.ajustar_hmm(X, 3, n_inicios=1, inicial=self.modelo)
        np.testing.assert_allclose(eco.posterior_hmm(X, m), m["gamma"], atol=1e-10)

    def test_bootstrap_estacionario(self):
        rng = np.random.default_rng(0)
        idx = self.inc.indices_bootstrap_estacionario(100_000, 12, rng)
        self.assertTrue(((idx >= 0) & (idx < 100_000)).all())
        cortes = (np.diff(idx) != 1) & (np.diff(idx) != -(100_000 - 1))
        self.assertAlmostEqual(len(idx) / (cortes.sum() + 1), 12, delta=0.5)   # largo medio de bloque

    def test_paralelo_igual_a_secuencial(self):
        # semillas por réplica: el resultado no depende del número de procesos
        from afp import econometria as eco
        X = eco.simular_hmm(self.modelo, 150, np.random.default_rng(3))
        a = self.inc.bootstrap_hmm(X, self.modelo, ["x", "y"], None, 4, 9, procesos=1)
        b = self.inc.bootstrap_hmm(X, self.modelo, ["x", "y"], None, 4, 9, procesos=2)
        np.testing.assert_allclose(a.values, b.values)

    def test_escenarios_recentrados_en_el_objetivo(self):
        import pandas as pd
        from afp import escenarios
        rng = np.random.default_rng(1)
        m = pd.DataFrame(rng.normal(0.005, 0.03, (50, 2)), columns=["A", "E"])
        R = escenarios.simular(m, dict(self.modelo, K=1, A=np.ones((1, 1)), gamma=np.ones((50, 1))),
                               meses=120, n=300, semilla=2, objetivo={"A": 0.04, "E": 0.02})
        geo = np.exp(np.log1p(R).mean(axis=(0, 1))) ** 12 - 1
        np.testing.assert_allclose(geo, [0.04, 0.02], atol=1e-10)

    def test_ic_correlacion(self):
        lo, hi = self.inc.ic_correlacion(0.81, 36)
        self.assertLess(lo, 0.81); self.assertGreater(hi, 0.81); self.assertLess(hi, 1)


class TestReforma(unittest.TestCase):
    def setUp(self):
        from afp import reforma, config
        self.rf, self.cfg = reforma, config

    def test_calendario_cotizacion_empleador(self):
        cal = self.cfg.REFORMA["empleador_cci"]
        f = np.array([2025.0, 2025 + 7 / 12, 2030.0, 2033 + 7 / 12, 2040.0, 2054 + 8 / 12, 2070.0])
        np.testing.assert_allclose(self.rf.tasa_vigente(cal, f), [0, 0.001, 0.017, 0.045, 0.045, 0.06, 0.06])

    def test_crp_se_extingue_en_2054(self):
        cal = self.cfg.REFORMA["crp"]
        np.testing.assert_allclose(self.rf.tasa_vigente(cal, np.array([2030.0, 2050.0, 2060.0])), [0.015, 0.0075, 0.0])

    def test_pgu_focalizada(self):
        u = self.rf.parametros_uf()
        v = self.rf.pgu(np.array([0.0, u["inferior"], (u["inferior"] + u["superior"]) / 2, u["superior"], 99]))
        np.testing.assert_allclose(v, [u["pgu"], u["pgu"], u["pgu"] / 2, 0, 0])

    def test_capas_suman_el_total(self):
        R = np.random.default_rng(3).normal(0.003, 0.02, (50, 480, 5))
        pt = self.rf.pension_total(R, "H")
        np.testing.assert_allclose(pt[["autofinanciada_10", "empleador_cci", "crp", "pgu"]].sum(1), pt.total)
        self.assertTrue((pt.empleador_cci > 0).all() and (pt.pgu >= 0).all())


class TestOptimo(unittest.TestCase):
    def test_equivalente_cierto(self):
        from afp import optimo
        self.assertAlmostEqual(optimo.equivalente_cierto(np.full(10, 7.0), 3), 7.0)
        x = np.random.default_rng(1).lognormal(2, 0.4, 5000)
        ec2, ec5 = optimo.equivalente_cierto(x, 2), optimo.equivalente_cierto(x, 5)
        self.assertLess(ec5, ec2); self.assertLess(ec2, x.mean())        # más aversión, menor equivalente cierto

    def test_familia_parametrica(self):
        from afp import optimo
        g = optimo.crecimiento_parametrico(np.array([25, 40, 52.5, 65]), 0.9, 40, 0.3, 65)
        np.testing.assert_allclose(g, [0.9, 0.9, 0.6, 0.3])


class TestMicrosimulacion(unittest.TestCase):
    def setUp(self):
        from afp import microsimulacion, config
        self.ms, self.cfg = microsimulacion, config

    def test_calibracion_ingreso_y_densidad(self):
        c = dict(self.cfg.MICROSIM, tope_imponible_uf=1e9, piso_ingreso_uf=0)
        pob = self.ms.generar_poblacion(200_000, np.random.default_rng(1), c)
        for s in ("H", "M"):
            x = pob[pob.sexo == s]
            self.assertAlmostEqual(x.sueldo_ref_uf.median(), c["ingreso"][s]["mediana"] / c["uf_ingresos"], delta=0.3)
            self.assertAlmostEqual(x.sueldo_ref_uf.mean(), c["ingreso"][s]["media"] / c["uf_ingresos"], delta=0.5)
            self.assertAlmostEqual(x.densidad.mean(), c["densidad"][s], delta=0.01)
        self.assertGreater(np.corrcoef(np.log(pob.sueldo_ref_uf), pob.densidad)[0, 1], 0.15)

    def test_rachas_respetan_densidad_y_duracion(self):
        f = self.ms.rachas_formales(np.full(4000, 0.6), 480, 36, np.random.default_rng(2))
        self.assertAlmostEqual(f.mean(), 0.6, delta=0.01)
        salidas = (f[:, :-1] & ~f[:, 1:]).sum()
        self.assertAlmostEqual(f[:, :-1].sum() / salidas, 36, delta=1.5)            # duración media de la racha

    def test_matmul_igual_a_acumular(self):
        from afp import simulacion
        rng = np.random.default_rng(4)
        R = rng.normal(0.004, 0.03, (30, 120, 5)); W = simulacion.pesos_fijo("B", np.arange(120))
        A = rng.random((7, 120))
        G = self.ms.factores_crecimiento(R, W)
        esperado = np.column_stack([simulacion.acumular(R, W, A[i]) for i in range(7)])   # (S, n)
        np.testing.assert_allclose(A @ G.T, esperado.T, rtol=1e-10)

    def test_shapley_reparte_toda_la_brecha(self):
        from afp import escenarios
        R = np.random.default_rng(5).normal(0.003, 0.02, (40, 480, 5))
        b = self.ms.brecha_genero(R, n=400, semilla=3)
        np.testing.assert_allclose(b.aporte_uf.sum(), b.attrs["hombre"] - b.attrs["mujer"], rtol=1e-9)


class TestRegimenesMacro(unittest.TestCase):
    def setUp(self):
        from afp import regimenes_macro
        self.rm = regimenes_macro

    def test_transiciones_suman_uno_y_w0_es_constante(self):
        rng = np.random.default_rng(0)
        b = rng.normal(0, 1, (3, 3)); np.fill_diagonal(b, 0); W = np.zeros((3, 3, 4))
        A = self.rm.matrices_transicion(b, W, rng.normal(0, 1, (10, 4)))
        np.testing.assert_allclose(A.sum(2), 1.0)
        np.testing.assert_allclose(A[0], A[-1])                    # sin pesos, no depende de z

    def test_forward_backward_tv_igual_al_constante(self):
        from afp import econometria as eco
        rng = np.random.default_rng(1)
        logB = rng.normal(0, 3, (60, 3)); A = rng.dirichlet(np.ones(3), 3); pi = np.array([.2, .3, .5])
        ll_c, g_c, xi_c = eco._forward_backward(logB, np.log(pi), np.log(A))
        ll_t, g_t, xi_t, _ = self.rm._forward_backward_tv(logB, pi, np.repeat(A[None], 59, 0))
        self.assertAlmostEqual(ll_c, ll_t, places=8)
        np.testing.assert_allclose(g_c, g_t, atol=1e-10); np.testing.assert_allclose(xi_c, xi_t.sum(0), atol=1e-9)

    def test_variables_sin_mirar_al_futuro(self):
        import pandas as pd
        idx = pd.date_range("2010-01-31", periods=30, freq="ME")
        macro = pd.DataFrame({"ipc": np.r_[np.zeros(20), 10.0, np.zeros(9)], "tpm": 1.0, "dolar": 800.0, "imacec": 2.0},
                             index=idx)
        z = self.rm.construir_variables(macro, idx)
        self.assertEqual(z.inflacion_12m.iloc[20], 0)              # el shock de IPC del mes 20 se ve recién en el 21
        self.assertGreater(z.inflacion_12m.iloc[21], 0.09)

    def test_diebold_mariano(self):
        d = np.random.default_rng(2).normal(0.5, 1, 400)
        t, p = self.rm.diebold_mariano(d)
        self.assertGreater(t, 3); self.assertLess(p, 0.01)


class TestBandas(unittest.TestCase):
    def test_bandas_oficiales_en_config(self):
        from afp import config
        self.assertEqual(config.BANDAS["permanente"], (0.024, 0.029))
        self.assertEqual(config.BANDAS["transicion"], 0.040)
        self.assertEqual(config.BANDAS["ventana_meses"], 36)


if __name__ == "__main__":
    unittest.main()
