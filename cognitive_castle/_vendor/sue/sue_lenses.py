"""Source-annotated examination policies, not philosopher personas.

Paths and software questions are SUE adaptations. References establish the
inspiration, not the validity of an algorithm. See docs/sue-socratic-lenses.md.
Every path establishes a claim before examining its consequences.
"""

LENSES = {
    "euthyphro": {
        "reference": "Plato, Euthyphro 6d–e, 10a–11b",
        "source": "https://classics.mit.edu/Plato/euthyfro.html",
        "path": (
            "DEFINE",
            "DISTINGUISH",
            "CAUSE_OR_CRITERION",
            "DIVIDE",
            "COUNTEREXAMPLE",
            "FOLLOW_CONSEQUENCE",
            "TEST_OPPOSITE",
        ),
        "guidance": "Seek a general definition, not just examples. Distinguish "
        "what makes the property hold from a symptom or a label. "
        "Check whether the definition presupposes its own conclusion.",
    },
    "meno": {
        "reference": "Plato, Meno 71b, 80d–86c, 97a–98a",
        "source": "https://classics.mit.edu/Plato/meno.html",
        "path": (
            "DEFINE",
            "CAUSE_OR_CRITERION",
            "DISTINGUISH",
            "COUNTEREXAMPLE",
            "DIVIDE",
            "FOLLOW_CONSEQUENCE",
            "TEST_OPPOSITE",
        ),
        "guidance": "Ask how a correct instance would be recognized without "
        "assuming the answer. Distinguish a fortunate example from "
        "a reusable account. Identify which assumptions remain open; "
        "do not import recollection as a mechanism of software knowledge.",
    },
    "parmenides": {
        "reference": "Plato, Parmenides 135c–136c",
        "source": "https://classics.mit.edu/Plato/parmenides.html",
        "path": (
            "DEFINE",
            "FOLLOW_CONSEQUENCE",
            "TEST_OPPOSITE",
            "DIVIDE",
            "DISTINGUISH",
            "CAUSE_OR_CRITERION",
            "COUNTEREXAMPLE",
        ),
        "guidance": "Examine consequences both if the hypothesis holds and if "
        "it does not, for the subject and related actors or objects. "
        "A tolerated opposite reveals underdetermination; failure "
        "to refute a hypothesis does not prove it.",
    },
    "cratylus": {
        "reference": "Plato, Cratylus 383a–384e, 438d–439b",
        "source": "https://classics.mit.edu/Plato/cratylus.html",
        "path": (
            "DEFINE",
            "DISTINGUISH",
            "TEST_OPPOSITE",
            "CAUSE_OR_CRITERION",
            "DIVIDE",
            "COUNTEREXAMPLE",
            "FOLLOW_CONSEQUENCE",
        ),
        "guidance": "Distinguish names from the behaviours or entities they "
        "denote. Test alleged synonyms by their specified referents "
        "and consequences, not spelling. Preserve unresolved "
        "polysemy instead of forcing an alias.",
    },
    "theaetetus": {
        "reference": "Plato, Theaetetus 149a–151d, 201c–210b",
        "source": "https://bookstacks.org/en/authors/plato/theaetetus/section-210",
        "path": (
            "DEFINE",
            "CAUSE_OR_CRITERION",
            "FOLLOW_CONSEQUENCE",
            "DISTINGUISH",
            "COUNTEREXAMPLE",
            "DIVIDE",
            "TEST_OPPOSITE",
        ),
        "guidance": "Test the proposed account itself: does it explain why the "
        "claim follows, or merely repeat it? Separate assertion, "
        "inference and assumption. An account plus agreement is "
        "not a certificate of knowledge; unresolved questions remain.",
    },
    "sophist": {
        "reference": "Plato, Sophist 218b–221c, 235d–236c, 253d–e",
        "source": "https://classics.mit.edu/Plato/sophist.html",
        "path": (
            "DEFINE",
            "DIVIDE",
            "DISTINGUISH",
            "TEST_OPPOSITE",
            "CAUSE_OR_CRITERION",
            "COUNTEREXAMPLE",
            "FOLLOW_CONSEQUENCE",
        ),
        "guidance": "Divide the relevant domain by stated distinguishing "
        "criteria. Examine look-alike cases, overlaps, exclusions "
        "and uncovered cases. Do not pretend an arbitrary list "
        "exhausts the domain or invent missing boundaries.",
    },
    "gorgias": {
        "reference": "Plato, Gorgias 454c–455a, 471e–472c",
        "source": "https://classics.mit.edu/Plato/gorgias.html",
        "path": (
            "DEFINE",
            "FOLLOW_CONSEQUENCE",
            "CAUSE_OR_CRITERION",
            "COUNTEREXAMPLE",
            "DIVIDE",
            "DISTINGUISH",
            "TEST_OPPOSITE",
        ),
        "guidance": "Distinguish persuasive assurances from justified "
        "commitments. Ask what observable behaviour would follow "
        "and how it would be checked. Popularity, confidence and "
        "repetition do not supply evidence or the author's assent.",
    },
    "republic": {
        "reference": "Plato, Republic IV 433a–434c; VII 533b–d",
        "source": "https://classics.mit.edu/Plato/republic.5.iv.html",
        "path": (
            "DEFINE",
            "DISTINGUISH",
            "DIVIDE",
            "CAUSE_OR_CRITERION",
            "COUNTEREXAMPLE",
            "FOLLOW_CONSEQUENCE",
            "TEST_OPPOSITE",
        ),
        "guidance": "Examine how parts, roles and responsibilities fit the "
        "whole. Distinguish capability, permission and obligation; "
        "test role combinations and dependencies. Treat initial "
        "hypotheses as examinable. This software adaptation does "
        "not import Plato's political hierarchy as a requirement.",
    },
    "philebus": {
        "reference": "Plato, Philebus 16c–17a, 23c–27c",
        "source": "https://classics.mit.edu/Plato/philebus.html",
        "path": (
            "DEFINE",
            "CAUSE_OR_CRITERION",
            "DIVIDE",
            "TEST_OPPOSITE",
            "DISTINGUISH",
            "COUNTEREXAMPLE",
            "FOLLOW_CONSEQUENCE",
        ),
        "guidance": "Examine limits, proportions and interacting constraints. "
        "Ask how the text distinguishes acceptable from excessive "
        "or deficient, including context, units and trade-offs. "
        "An explicit qualitative criterion can suffice; never "
        "invent a number merely because none is supplied.",
    },
}

for _lens in LENSES.values():
    _lens["start"] = _lens["path"][0]
