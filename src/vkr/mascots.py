from __future__ import annotations

import random

Mascot = tuple[str, ...]


def _art(text: str) -> Mascot:
    return tuple(line.rstrip() for line in text.strip("\n").split("\n"))


STRETCHING = _art(r"""
  ,-.       _,---._ __  / \
 /  )    .-'       `./ /   \
(  (   ,'            `/    /|
 \  `-"             \'\   / |
  `.              ,  \ \ /  |
   /`.          ,'-`----Y   |
  (            ;        |   '
  |  ,-.    ,-'         |  /
  |  | (   |      [vkr] | /
  )  |  \  `.___________|/
  `--'   `--'
""")

REACHING = _art(r"""
                        _
                       | \
                       | |
                       | |
  |\                   | |
 /, ~\                / /
X     `-.....-------./ /
 ~-. ~  ~              |
    \             /    |
     \  /_     ___\   /
     | /\ ~~~~~   \ |
     | | \        || |
     | |\ \       || )
    (_/ (_/      ((_/
""")

CURLED = _art(r"""
       _
       \`*-.
        )  _`-.
       .  : `. .
       : _   '  \
       ; *` _.   `*-._
       `-.-'          `-.
         ;       `       `.
         :.       .        \
         . \  .   :   .-'   .
         '  `+.;  ;  '      :
         :  '  |    ;       ;-.
         ; '   : :`-:     _.`* ;
[vkr] .*' /  .*' ; .*`- +'  `*'
      `*-*   `*-*  `*-*'
""")

PEEKING = _art(r"""
  _._     _,-'""`-._
 (,-.`._,'(       |\`-/|
     `-.-' \ )-`( , o o)
           `-    \`_`"'-
""")

ROOMY: tuple[Mascot, ...] = (STRETCHING, REACHING, CURLED)


def roomy(rng: random.Random | None = None) -> Mascot:
    return (rng or random).choice(ROOMY)
