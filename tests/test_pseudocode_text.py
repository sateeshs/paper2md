r"""Pseudocode extraction must preserve the math inside algorithm bodies.

Drawn from the Q-learning style algorithm floats in 2412.05265, where every
symbol (\theta, \eta, \gets, \nabla) was deleted by the generic command
stripper, leaving orphaned "$ _0  0$" fragments the reader cannot decode.
"""
from lib.latex_parse import _pseudocode_to_text

ALGORITHM_BODY = r"""
\caption{Gradient ascent for $\theta$}
\begin{algorithmic}[1]
\Require learning rate $\eta > 0$, dataset $\mathcal{D}$
\State Initialize $\hat{\theta}_0 \leftarrow 0$
\For{$t = 1$ to $T$}
    \State $g_t \gets \nabla_\theta L(\theta_{t-1})$ \Comment{stochastic gradient}
    \State $\theta_t \leftarrow \theta_{t-1} + \eta g_t$
\EndFor
\State \Return $\hat{\theta}_T$
\end{algorithmic}
"""


def test_math_commands_survive_extraction():
    text = _pseudocode_to_text(ALGORITHM_BODY)
    for command in (r"\theta", r"\eta", r"\gets", r"\nabla", r"\hat"):
        assert command in text, f"{command} was stripped from:\n{text}"


def test_no_orphaned_dollar_fragments():
    """A '$ _0  0$' style fragment means the body was gutted but markers kept."""
    import re

    text = _pseudocode_to_text(ALGORITHM_BODY)
    for span in re.findall(r"\$([^$\n]*)\$", text):
        core = span.replace("_", "").replace("{", "").replace("}", "").strip()
        assert core, f"empty math span in:\n{text}"


def test_control_flow_keywords_are_readable():
    """\\For{...} must not collapse to a bare expression with no 'for'."""
    text = _pseudocode_to_text(ALGORITHM_BODY)
    lowered = text.lower()
    assert "for" in lowered
    assert "return" in lowered
    assert "require" in lowered


def test_environment_name_does_not_leak_as_text():
    text = _pseudocode_to_text(ALGORITHM_BODY)
    assert not text.startswith("algorithmic")
    assert "algorithmic[1]" not in text


def test_structural_keywords_are_kept_readable():
    text = _pseudocode_to_text(ALGORITHM_BODY)
    assert "Initialize" in text
    assert "stochastic gradient" in text


def test_caption_is_not_duplicated_into_the_body():
    text = _pseudocode_to_text(ALGORITHM_BODY)
    assert "Gradient ascent for" not in text


def test_block_end_does_not_swallow_the_next_line():
    """\\EndFor followed by \\Return must not render as 'end forreturn'."""
    text = _pseudocode_to_text(ALGORITHM_BODY)
    assert "end forreturn" not in text
    assert "end for" in text
    lines = [line.strip() for line in text.splitlines()]
    assert "end for" in lines


# Drawn verbatim from the Q-learning float in 2412.05265, which exposed three
# further defects once math spans were protected.
QLEARNING_BODY = r"""
\caption{Q-learning with $\epsilon$-greedy exploration}
\label{algo:Qlearning}
\begin{algorithmic}
\State Initialize value function parameters $\vw$ \\
\While{not converged}
    \State Sample action
    $a=\begin{cases}
        \argmax_b Q(s,b), & with probability $1-\epsilon$ \\
        \text{random action}, & with probability $\epsilon$
    \end{cases}$
\EndWhile
\end{algorithmic}
"""


def test_label_does_not_leak_into_the_body():
    """\\label{algo:Qlearning} must not surface as a bare 'algo:Qlearning' line."""
    text = _pseudocode_to_text(QLEARNING_BODY)
    assert "algo:Qlearning" not in text
    assert "\\label" not in text


def test_multiline_math_environment_is_preserved():
    """A \\begin{cases} spanning lines must keep its contents intact."""
    text = _pseudocode_to_text(QLEARNING_BODY)
    for command in (r"\argmax", "Q(s,b)", r"\epsilon"):
        assert command in text, f"{command} was stripped from:\n{text}"


def test_latex_line_break_is_not_literal_backslashes():
    """Outside math, "\\\\" is a line break. Inside \\begin{cases} it is a row
    separator KaTeX needs, so only the prose half is checked."""
    import re

    text = _pseudocode_to_text(QLEARNING_BODY)
    outside_math = re.sub(r"\$[^$]*\$", "", text, flags=re.DOTALL)
    assert "\\\\" not in outside_math


def test_caption_keeps_its_math():
    """"$\\epsilon$-greedy" must not collapse to "$$-greedy" in the caption."""
    from lib.latex_parse import _extract_algorithm_caption

    caption = _extract_algorithm_caption(QLEARNING_BODY)
    assert caption is not None
    assert "$$" not in caption
    assert r"\epsilon" in caption
    assert "greedy" in caption


# algorithm2e style, as used by the Q-learning float in 2412.05265.
ALGORITHM2E_BODY = r"""
\begin{algorithm}
\caption{Q-learning with $\epsilon$-greedy exploration}
\label{algo:Qlearning}
Initialize value function parameters ${\bm{w}}$ \\
\Repeat{converged}
       {
       Sample starting state $s$ of new episode \\
       \Repeat{state $s$ is terminal}
       {
       \lIf{$u < \epsilon$}{take random action}
       Update $Q$ \;
       }
       }
\end{algorithm}
"""


def test_algorithm2e_repeat_is_readable():
    """\\Repeat{converged} must not collapse to a bare 'converged'."""
    text = _pseudocode_to_text(ALGORITHM2E_BODY)
    lowered = text.lower()
    assert "repeat" in lowered, f"no 'repeat' in:\n{text}"
    assert "converged" in lowered
    # The condition must not be left standing alone as if it were a statement
    assert not any(line.strip() == "converged" for line in text.splitlines())


def test_algorithm2e_inline_if_is_readable():
    text = _pseudocode_to_text(ALGORITHM2E_BODY)
    assert "if" in text.lower()
    assert "take random action" in text


def test_adjacent_brace_groups_get_a_separator():
    """\\lIf{$cond$}{body} must not render as "$cond$body" with no gap."""
    text = _pseudocode_to_text(ALGORITHM2E_BODY)
    assert "$take random action" not in text
    assert "take random action" in text


def test_statement_terminator_is_dropped():
    r"""algorithm2e ends statements with "\;" — it typesets nothing."""
    text = _pseudocode_to_text(ALGORITHM2E_BODY)
    assert r"\;" not in text
    assert "Update $Q$" in text
