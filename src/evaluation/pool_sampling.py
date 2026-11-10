"""Amostragem estratificada para o pooling de julgamento (determinística).

Núcleo estatístico e de estratificação do gerador de pools, isolado para ser
testável sem rede e sem os recuperadores. Implementa a política aprovada:

- nível de confiança 95% (z=1,96), proporção conservadora p=0,5, margem e=0,10;
- correção de população finita (FPC);
- amostragem aleatória simples sem reposição, por formulação, com sementes
  determinísticas derivadas da seed da execução e dos identificadores.

Decisões implementadas (ver
`docs/experimento/proposta_operacional_avaliacao_e_gold.md`, §4):

- `n0 = z²·p(1−p)/e²` preservado com precisão numérica até o arredondamento final;
- `s_R = min(N_R, ceil(n0 / (1 + (n0−1)/N_R)))`;
- `N_R = 0` ⇒ nenhuma amostra (estrato restante vazio);
- o estrato de inclusão certa (I) de uma formulação é a interseção do conjunto
  com a base determinística J0; o estrato restante (R) é o conjunto fora de J0;
- sorteios de uma formulação NÃO tornam documentos "inclusão certa" de outra
  formulação: cada formulação tem seu próprio estrato I (= interseção com J0) e
  sua própria amostra planejada.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

# Parâmetros estatísticos aprovados (fixos nesta política).
Z_95 = 1.96
P_CONSERVATIVE = 0.5
MARGIN_E = 0.10


def n0_base(z: float = Z_95, p: float = P_CONSERVATIVE, e: float = MARGIN_E) -> float:
    """Tamanho base de amostra (sem correção de população finita).

    Retorna o valor em ponto flutuante, preservando a precisão numérica; o
    arredondamento ocorre apenas em `sample_size`.
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p deve estar em (0,1)")
    if e <= 0.0:
        raise ValueError("e (margem) deve ser > 0")
    return (z * z * p * (1.0 - p)) / (e * e)


def sample_size(n_r: int, z: float = Z_95, p: float = P_CONSERVATIVE, e: float = MARGIN_E) -> int:
    """Tamanho da amostra do estrato restante com correção de população finita.

    `s_R = min(N_R, ceil(n0 / (1 + (n0−1)/N_R)))`. `N_R = 0` ⇒ 0 (sem sorteio).
    """
    if n_r < 0:
        raise ValueError("n_r deve ser >= 0")
    if n_r == 0:
        return 0
    n0 = n0_base(z, p, e)
    s = n0 / (1.0 + (n0 - 1.0) / n_r)
    return min(n_r, math.ceil(s))


def _derive_seed(run_seed: int, *parts: str) -> int:
    """Semente determinística derivada da seed da execução e de identificadores.

    Usa SHA-256 sobre a concatenação (run_seed, parts...) e reduz a 64 bits.
    Determinística e estável entre processos (ao contrário de hash()).
    """
    h = hashlib.sha256()
    h.update(str(run_seed).encode("utf-8"))
    for part in parts:
        h.update(b"\x1f")
        h.update(str(part).encode("utf-8"))
    return int.from_bytes(h.digest()[:8], "big", signed=False)


def sample_without_replacement(
    population: list[str], k: int, run_seed: int, *seed_parts: str
) -> list[str]:
    """Amostra aleatória simples SEM reposição, determinística.

    - `population` é ordenada antes do sorteio para garantir reprodutibilidade
      independente da ordem de entrada;
    - a semente deriva de `run_seed` + `seed_parts` (ex.: need_id, formulation);
    - `k >= len(population)` retorna toda a população (ordenada);
    - usa `random.Random` local (não afeta o estado global).
    """
    import random

    if k <= 0:
        return []
    pool = sorted(set(population))
    if k >= len(pool):
        return pool
    rng = random.Random(_derive_seed(run_seed, *seed_parts))
    return sorted(rng.sample(pool, k))


@dataclass
class StratumPlan:
    """Plano de estratificação de UM conjunto (estruturado ou complemento) para
    UMA formulação. Preserva população, estratos, amostra e probabilidades."""

    population: list[str]                 # C (conjunto completo), ordenado
    n_total: int                          # N = |C|
    stratum_I: list[str]                  # inclusão certa = C ∩ J0 (prob = 1)
    n_I: int                              # |estrato I|
    stratum_R_population: list[str]       # restante elegível = C \ J0
    n_R: int                              # |estrato R|
    s_R: int                              # tamanho sorteado do estrato R
    sampled_R: list[str]                  # documentos efetivamente sorteados do R
    inclusion_prob_R: float               # s_R / n_R (0.0 se n_R == 0)
    seed_parts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def to_judge(self) -> list[str]:
        """Documentos deste plano que vão para julgamento (I ∪ amostra de R)."""
        return sorted(set(self.stratum_I) | set(self.sampled_R))


def plan_stratified(
    conjunto: list[str],
    j0: set[str],
    run_seed: int,
    seed_parts: tuple[str, ...],
    teto: int,
    z: float = Z_95,
    p: float = P_CONSERVATIVE,
    e: float = MARGIN_E,
) -> StratumPlan:
    """Planeja a estratificação de um conjunto em relação à base determinística J0.

    - Se `|conjunto| <= teto`: censo — todo o conjunto é inclusão certa (já estará
      em J0 por construção), sem estrato R a sortear.
    - Se `|conjunto| > teto`: estrato I = conjunto ∩ J0 (prob = 1); estrato R =
      conjunto \\ J0; `s_R` dimensionado por `sample_size`; amostra determinística.
    """
    C = sorted(set(str(x) for x in conjunto))
    N = len(C)
    I = sorted(x for x in C if x in j0)
    if N <= teto:
        # Censo: tudo em J0; nenhum estrato R.
        return StratumPlan(
            population=C, n_total=N, stratum_I=C, n_I=N,
            stratum_R_population=[], n_R=0, s_R=0, sampled_R=[],
            inclusion_prob_R=0.0, seed_parts=seed_parts,
        )
    R_pop = sorted(x for x in C if x not in j0)
    n_R = len(R_pop)
    s_R = sample_size(n_R, z, p, e)
    sampled = sample_without_replacement(R_pop, s_R, run_seed, *seed_parts)
    prob = (s_R / n_R) if n_R > 0 else 0.0
    return StratumPlan(
        population=C, n_total=N, stratum_I=I, n_I=len(I),
        stratum_R_population=R_pop, n_R=n_R, s_R=s_R, sampled_R=sampled,
        inclusion_prob_R=prob, seed_parts=seed_parts,
    )
