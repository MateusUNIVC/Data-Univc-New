#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Converte relatórios XLSX do SEI/UNIVC ("Notas e Frequências por Turma")
em dois JSONs por curso/arquivo:

1) *_disciplinas.json
   - lista todas as disciplinas encontradas no relatório
   - agrega turmas e indicadores por disciplina

2) *_alunos.json
   - agrupa cada aluno pela matrícula
   - lista disciplina, turma, média final e situação oficial do SEI

O script usa a situação que vem do próprio relatório (Aprovado, Reprovado,
Reprovado Falta, Cursando etc.). Ele NÃO recalcula aprovação pela média.

Dependência:
    pip install openpyxl

Exemplos:
    python excel_notas_para_json.py Administracao_2026_1.xlsx

    # Processa todos os .xlsx de uma pasta:
    python excel_notas_para_json.py notas_DTNH_2026_1

    # Define outra pasta de saída:
    python excel_notas_para_json.py notas_DTNH_2026_1 --saida json_saida
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from openpyxl import load_workbook


def limpar_texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).replace("\xa0", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto or None


def parse_media(valor: Any) -> float | None:
    """Converte '8,50' em 8.5 e '--'/vazio em None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = limpar_texto(valor)
    if not texto or texto in {"--", "-", "—"}:
        return None

    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def classificacao_aprovacao(situacao: str | None) -> bool | None:
    """
    True  -> aprovado
    False -> reprovado (inclusive reprovado por falta)
    None  -> ainda sem resultado final, por exemplo Cursando
    """
    if not situacao:
        return None

    s = situacao.casefold()
    if s == "aprovado" or s.startswith("aprovado "):
        return True
    if s.startswith("reprovado"):
        return False
    return None


def motivo_reprovacao(situacao: str | None) -> str | None:
    """
    Retorna o motivo da reprovação conforme a situação oficial do SEI:

    - "falta" -> situações como "Reprovado Falta"
    - "nota"  -> "Reprovado" ou outra reprovação sem indicação de falta
    - None      -> aprovado, cursando ou situação sem reprovação

    A regra não recalcula resultado com base na média.
    """
    if not situacao:
        return None

    s = situacao.casefold().strip()
    if not s.startswith("reprovado"):
        return None

    if "falta" in s or "frequência" in s or "frequencia" in s:
        return "falta"

    return "nota"


def proximo_valor_na_linha(ws, row: int, col_label: int) -> Any:
    """Retorna o primeiro valor não vazio à direita de um rótulo."""
    for col in range(col_label + 1, ws.max_column + 1):
        valor = ws.cell(row, col).value
        if valor not in (None, ""):
            return valor
    return None


def encontrar_valor_por_rotulo(ws, rotulo: str) -> Any:
    alvo = rotulo.casefold().strip()
    for row in range(1, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            valor = limpar_texto(ws.cell(row, col).value)
            if valor and valor.casefold() == alvo:
                return proximo_valor_na_linha(ws, row, col)
    return None


def parse_ano_semestre(ws) -> tuple[int | None, int | None]:
    bruto = limpar_texto(encontrar_valor_por_rotulo(ws, "Ano/Semestre:"))
    if not bruto:
        return None, None

    m = re.search(r"(\d{4})\s*[/\-]\s*([12])", bruto)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def ler_registros(caminho: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    wb = load_workbook(caminho, data_only=True, read_only=False)
    ws = wb[wb.sheetnames[0]]

    ano, semestre = parse_ano_semestre(ws)
    warnings: list[str] = []
    registros: list[dict[str, Any]] = []

    # Cada bloco do relatório começa por "Unidade Ensino:".
    inicios = [
        row
        for row in range(1, ws.max_row + 1)
        if limpar_texto(ws.cell(row, 1).value) == "Unidade Ensino:"
    ]

    if not inicios:
        raise ValueError(
            "Não encontrei blocos iniciados por 'Unidade Ensino:'. "
            "O arquivo não parece seguir o modelo esperado do SEI."
        )

    cursos_encontrados: list[str] = []

    for idx, inicio in enumerate(inicios):
        fim = inicios[idx + 1] - 1 if idx + 1 < len(inicios) else ws.max_row

        curso = None
        disciplina = None
        turma = None
        periodo = None
        header_row = None
        qtd_declarada = None

        for row in range(inicio, fim + 1):
            a = limpar_texto(ws.cell(row, 1).value)

            if a == "Curso:":
                curso = limpar_texto(ws.cell(row, 3).value)
            elif a == "Disciplina:":
                disciplina = limpar_texto(ws.cell(row, 3).value)
            elif a == "Turma:":
                turma = limpar_texto(ws.cell(row, 3).value)
                # Neste layout "Período:" fica na coluna K e valor na N.
                periodo = limpar_texto(ws.cell(row, 14).value)
            elif a == "Matrícula":
                header_row = row
            elif a == "Qtd de alunos:":
                qtd_declarada = ws.cell(row, 3).value

        if curso:
            cursos_encontrados.append(curso)

        if not header_row:
            warnings.append(f"Bloco na linha {inicio}: cabeçalho de alunos não encontrado.")
            continue

        if not disciplina:
            warnings.append(f"Bloco na linha {inicio}: disciplina não identificada.")
            continue

        alunos_bloco = 0

        for row in range(header_row + 1, fim + 1):
            matricula_raw = ws.cell(row, 1).value
            nome_raw = ws.cell(row, 3).value

            if limpar_texto(matricula_raw) == "Qtd de alunos:":
                break

            matricula = limpar_texto(matricula_raw)
            nome = limpar_texto(nome_raw)

            # Linhas de aluno possuem matrícula + nome.
            if not matricula or not nome:
                continue

            media = parse_media(ws.cell(row, 11).value)
            situacao = limpar_texto(ws.cell(row, 18).value)

            registros.append(
                {
                    "matricula": matricula,
                    "nome": nome,
                    "curso": curso,
                    "ano": ano,
                    "semestre": semestre,
                    "disciplina": disciplina,
                    "turma": turma,
                    "periodo": periodo,
                    "media": media,
                    "situacao": situacao,
                    "aprovado": classificacao_aprovacao(situacao),
                    "motivo_reprovacao": motivo_reprovacao(situacao),
                }
            )
            alunos_bloco += 1

        # Conferência simples do total declarado por bloco, quando possível.
        if qtd_declarada not in (None, ""):
            try:
                qtd = int(float(str(qtd_declarada).replace(",", ".")))
                if qtd != alunos_bloco:
                    warnings.append(
                        f"Bloco linha {inicio} ({disciplina} / {turma}): "
                        f"relatório declara {qtd} aluno(s), parser encontrou {alunos_bloco}."
                    )
            except ValueError:
                pass

    if not registros:
        raise ValueError("Nenhum registro de aluno foi encontrado no arquivo.")

    curso_principal = Counter(cursos_encontrados).most_common(1)[0][0] if cursos_encontrados else None

    metadados = {
        "arquivo_origem": caminho.name,
        "curso": curso_principal,
        "ano": ano,
        "semestre": semestre,
        "aba": ws.title,
        "total_registros_aluno_disciplina": len(registros),
        "total_alunos_unicos": len({r["matricula"] for r in registros}),
        "total_disciplinas": len({r["disciplina"] for r in registros}),
        "total_turmas": len({(r["disciplina"], r["turma"]) for r in registros}),
    }

    return metadados, registros, warnings


def resumo_reprovacoes(registros: list[dict[str, Any]]) -> dict[str, int]:
    por_nota = sum(1 for r in registros if r.get("motivo_reprovacao") == "nota")
    por_falta = sum(1 for r in registros if r.get("motivo_reprovacao") == "falta")
    return {
        "total": por_nota + por_falta,
        "por_nota": por_nota,
        "por_falta": por_falta,
    }


def gerar_json_disciplinas(metadados: dict[str, Any], registros: list[dict[str, Any]]) -> dict[str, Any]:
    por_disciplina: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in registros:
        por_disciplina[r["disciplina"]].append(r)

    disciplinas_saida = []

    for disciplina in sorted(por_disciplina, key=str.casefold):
        regs = por_disciplina[disciplina]
        por_turma: dict[tuple[str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
        for r in regs:
            por_turma[(r["turma"], r["periodo"])].append(r)

        turmas_saida = []
        for (turma, periodo), turma_regs in sorted(
            por_turma.items(), key=lambda x: ((x[0][0] or "").casefold(), (x[0][1] or "").casefold())
        ):
            notas = [r["media"] for r in turma_regs if r["media"] is not None]
            situacoes = Counter(r["situacao"] or "Sem situação" for r in turma_regs)

            turmas_saida.append(
                {
                    "turma": turma,
                    "periodo": periodo,
                    "alunos": len({r["matricula"] for r in turma_regs}),
                    "registros": len(turma_regs),
                    "media_das_notas_disponiveis": round(mean(notas), 2) if notas else None,
                    "situacoes": dict(sorted(situacoes.items())),
                    "reprovacoes": resumo_reprovacoes(turma_regs),
                }
            )

        notas_disc = [r["media"] for r in regs if r["media"] is not None]
        situacoes_disc = Counter(r["situacao"] or "Sem situação" for r in regs)

        disciplinas_saida.append(
            {
                "disciplina": disciplina,
                "alunos_unicos": len({r["matricula"] for r in regs}),
                "registros": len(regs),
                "media_das_notas_disponiveis": round(mean(notas_disc), 2) if notas_disc else None,
                "situacoes": dict(sorted(situacoes_disc.items())),
                "reprovacoes": resumo_reprovacoes(regs),
                "turmas": turmas_saida,
            }
        )

    return {
        "curso": metadados["curso"],
        "ano": metadados["ano"],
        "semestre": metadados["semestre"],
        "total_disciplinas": len(disciplinas_saida),
        "disciplinas": disciplinas_saida,
    }


def gerar_json_alunos(metadados: dict[str, Any], registros: list[dict[str, Any]]) -> dict[str, Any]:
    por_aluno: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in registros:
        por_aluno[r["matricula"]].append(r)

    alunos_saida = []

    for matricula, regs in sorted(
        por_aluno.items(),
        key=lambda item: ((item[1][0]["nome"] or "").casefold(), item[0]),
    ):
        nome = regs[0]["nome"]
        disciplinas = []

        for r in sorted(
            regs,
            key=lambda x: (
                (x["disciplina"] or "").casefold(),
                (x["turma"] or "").casefold(),
            ),
        ):
            disciplinas.append(
                {
                    "disciplina": r["disciplina"],
                    "turma": r["turma"],
                    "periodo": r["periodo"],
                    "media": r["media"],
                    "situacao": r["situacao"],
                    "aprovado": r["aprovado"],
                    "motivo_reprovacao": r["motivo_reprovacao"],
                }
            )

        alunos_saida.append(
            {
                "matricula": matricula,
                "nome": nome,
                "disciplinas": disciplinas,
            }
        )

    return {
        "curso": metadados["curso"],
        "ano": metadados["ano"],
        "semestre": metadados["semestre"],
        "total_alunos": len(alunos_saida),
        "alunos": alunos_saida,
    }


def nome_base_seguro(caminho: Path) -> str:
    nome = unicodedata.normalize("NFKD", caminho.stem)
    nome = "".join(ch for ch in nome if not unicodedata.combining(ch))
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", nome).strip("_")
    return nome or "relatorio"


def salvar_json(obj: dict[str, Any], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def processar_arquivo(caminho: Path, pasta_saida: Path) -> tuple[Path, Path, dict[str, Any], list[str]]:
    metadados, registros, warnings = ler_registros(caminho)
    disciplinas = gerar_json_disciplinas(metadados, registros)
    alunos = gerar_json_alunos(metadados, registros)

    base = nome_base_seguro(caminho)
    arquivo_disciplinas = pasta_saida / f"{base}_disciplinas.json"
    arquivo_alunos = pasta_saida / f"{base}_alunos.json"

    salvar_json(disciplinas, arquivo_disciplinas)
    salvar_json(alunos, arquivo_alunos)

    return arquivo_disciplinas, arquivo_alunos, metadados, warnings


def listar_xlsx(entrada: Path) -> list[Path]:
    if entrada.is_file():
        if entrada.suffix.lower() != ".xlsx":
            raise ValueError("O arquivo de entrada precisa ser .xlsx")
        return [entrada]

    if entrada.is_dir():
        arquivos = sorted(
            p for p in entrada.glob("*.xlsx")
            if not p.name.startswith("~$")
        )
        if not arquivos:
            raise ValueError(f"Nenhum .xlsx encontrado em {entrada}")
        return arquivos

    raise FileNotFoundError(f"Entrada não encontrada: {entrada}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Converte relatórios de notas do SEI/UNIVC em JSON."
    )
    parser.add_argument(
        "entrada",
        type=Path,
        help="Arquivo .xlsx ou pasta contendo os relatórios .xlsx.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Pasta dos JSONs. Padrão: pasta 'json' ao lado da entrada.",
    )
    args = parser.parse_args()

    entrada = args.entrada.expanduser().resolve()
    arquivos = listar_xlsx(entrada)

    if args.saida:
        pasta_saida = args.saida.expanduser().resolve()
    elif entrada.is_file():
        pasta_saida = entrada.parent / "json"
    else:
        pasta_saida = entrada / "json"

    print(f"Arquivos encontrados: {len(arquivos)}")
    print(f"Saída: {pasta_saida}")

    falhas = []

    for i, arquivo in enumerate(arquivos, start=1):
        print(f"\n[{i}/{len(arquivos)}] {arquivo.name}")
        try:
            disc_path, alunos_path, meta, warnings = processar_arquivo(arquivo, pasta_saida)
            print(
                f"  OK: {meta['total_alunos_unicos']} alunos, "
                f"{meta['total_disciplinas']} disciplinas, "
                f"{meta['total_registros_aluno_disciplina']} registros"
            )
            print(f"  -> {disc_path.name}")
            print(f"  -> {alunos_path.name}")
            for aviso in warnings[:10]:
                print(f"  AVISO: {aviso}")
            if len(warnings) > 10:
                print(f"  AVISO: ... e mais {len(warnings) - 10} aviso(s)")
        except Exception as exc:
            falhas.append((arquivo.name, str(exc)))
            print(f"  ERRO: {exc}")

    if falhas:
        print("\nFalhas:")
        for nome, erro in falhas:
            print(f"- {nome}: {erro}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
