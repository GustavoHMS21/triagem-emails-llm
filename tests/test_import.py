"""Importar os módulos do projeto não lê arquivo nenhum do projeto.

Configuração (.env), prompt e CSVs são carregados quando usados, não no
import. O teste roda um Python novo (módulos ainda não carregados), registra
um audit hook que anota todo arquivo aberto e importa os módulos.
"""

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

VIGIA = """
import os, sys
abertos = []
def vigia(evento, args):
    if evento == "open" and isinstance(args[0], str):
        abertos.append(os.path.abspath(args[0]))
sys.addaudithook(vigia)
import triagem.avaliacao, triagem.classificador, triagem.config, triagem.pipeline
print("\\n".join(abertos))
"""


def test_importar_os_modulos_nao_le_arquivos_do_projeto():
    # Roda na raiz do projeto, onde existe .env: se não for lido, é porque o import não lê
    saida = subprocess.run([sys.executable, "-c", VIGIA], cwd=RAIZ, capture_output=True, text=True, check=True)
    abertos = [Path(linha) for linha in saida.stdout.splitlines() if linha]
    do_projeto = [
        p for p in abertos if p.is_relative_to(RAIZ) and ".venv" not in p.parts and p.suffix not in {".py", ".pyc"}
    ]
    assert do_projeto == []
