# Testes do núcleo de amostragem estratificada do gerador de pools.
# Determinísticos, sem rede. Verificam a regra de dimensionamento (95%/p=0,5/
# e=0,10 + FPC), bordas (N_R=0, pequeno, grande), censo e reprodutibilidade.

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from evaluation.pool_sampling import (  # noqa: E402
    MARGIN_E,
    P_CONSERVATIVE,
    Z_95,
    n0_base,
    plan_stratified,
    sample_size,
    sample_without_replacement,
)


def test_n0_base_valor_conhecido():
    # z=1,96, p=0,5, e=0,10 -> n0 = 1,96^2*0,25/0,01 = 96,04
    assert abs(n0_base() - 96.04) < 1e-9


def test_n0_base_parametros_invalidos():
    with pytest.raises(ValueError):
        n0_base(p=0.0)
    with pytest.raises(ValueError):
        n0_base(e=0.0)


def test_sample_size_nr_zero():
    assert sample_size(0) == 0


def test_sample_size_populacao_pequena_vira_quase_censo():
    # N_R pequeno: FPC reduz s_R; nunca excede N_R.
    for n_r in (1, 5, 20, 50):
        s = sample_size(n_r)
        assert 0 < s <= n_r


def test_sample_size_populacao_grande_tende_a_n0():
    # N_R grande -> s_R ~ ceil(n0) = 97.
    s = sample_size(10_000_000)
    assert s == math.ceil(n0_base())  # 97


def test_sample_size_fpc_formula():
    n_r = 200
    n0 = n0_base()
    esperado = min(n_r, math.ceil(n0 / (1 + (n0 - 1) / n_r)))
    assert sample_size(n_r) == esperado


def test_sample_size_negativo():
    with pytest.raises(ValueError):
        sample_size(-1)


def test_sample_without_replacement_reprodutivel():
    pop = [f"d{i}" for i in range(100)]
    a = sample_without_replacement(pop, 10, 42, "NI-001", "direct")
    b = sample_without_replacement(pop, 10, 42, "NI-001", "direct")
    assert a == b
    assert len(a) == 10
    assert set(a) <= set(pop)


def test_sample_muda_com_seed():
    pop = [f"d{i}" for i in range(100)]
    a = sample_without_replacement(pop, 10, 1, "NI-001", "direct")
    b = sample_without_replacement(pop, 10, 2, "NI-001", "direct")
    assert a != b  # alta probabilidade; seeds distintas


def test_sample_muda_com_formulacao():
    pop = [f"d{i}" for i in range(100)]
    a = sample_without_replacement(pop, 10, 1, "NI-001", "direct")
    b = sample_without_replacement(pop, 10, 1, "NI-001", "verbose")
    assert a != b


def test_sample_k_maior_que_populacao_retorna_tudo():
    pop = ["d1", "d2", "d3"]
    assert sample_without_replacement(pop, 10, run_seed=1) == sorted(pop)


# --------------------------------------------------------------------------- #
# plan_stratified
# --------------------------------------------------------------------------- #

def test_plan_censo_quando_conjunto_pequeno():
    C = [f"d{i}" for i in range(50)]
    j0 = set()  # irrelevante no censo
    plan = plan_stratified(C, j0, run_seed=1, seed_parts=("NI-001", "direct", "struct"), teto=100)
    assert plan.n_total == 50
    assert plan.n_I == 50 and plan.stratum_I == sorted(C)
    assert plan.n_R == 0 and plan.s_R == 0 and plan.sampled_R == []
    assert plan.inclusion_prob_R == 0.0
    assert set(plan.to_judge) == set(C)


def test_plan_estratifica_quando_grande():
    C = [f"d{i}" for i in range(300)]        # > teto
    j0 = {f"d{i}" for i in range(0, 40)}     # 40 já no pool -> estrato I
    plan = plan_stratified(C, j0, run_seed=7, seed_parts=("NI-001", "direct", "struct"), teto=100)
    assert plan.n_total == 300
    assert plan.n_I == 40
    assert plan.n_R == 260
    assert plan.s_R == sample_size(260)
    assert len(plan.sampled_R) == plan.s_R
    assert set(plan.sampled_R).issubset(set(C) - j0)       # amostra só do restante
    assert plan.inclusion_prob_R == plan.s_R / plan.n_R
    # a julgar = estrato I + amostra do R
    assert set(plan.to_judge) == set(plan.stratum_I) | set(plan.sampled_R)


def test_plan_estratos_disjuntos():
    C = [f"d{i}" for i in range(500)]
    j0 = {f"d{i}" for i in range(0, 100)}
    plan = plan_stratified(C, j0, run_seed=3, seed_parts=("NI-X", "direct", "struct"), teto=100)
    # estrato I e restante são disjuntos e cobrem C
    assert set(plan.stratum_I).isdisjoint(set(plan.stratum_R_population))
    assert set(plan.stratum_I) | set(plan.stratum_R_population) == set(C)
    # amostra vem só do restante
    assert set(plan.sampled_R).isdisjoint(set(plan.stratum_I))
