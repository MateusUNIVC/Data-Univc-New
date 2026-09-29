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


def _valor_coluna(row: tuple[Any, ...], index: int) -> Any:
    return row[index] if index < len(row) else None


def _parse_ano_semestre_linha(row: tuple[Any, ...]) -> tuple[int | None, int | None]:
    for index, value in enumerate(row):
        if limpar_texto(value) != "Ano/Semestre:":
            continue
        for candidate in row[index + 1:]:
            raw = limpar_texto(candidate)
            if not raw:
                continue
            match = re.search(r"(\d{4})\s*[/\-]\s*([12])", raw)
            if match:
                return int(match.group(1)), int(match.group(2))
            break
    return None, None


def _prepare_read_only_sheet(ws) -> None:
    """Ignora dimensões subestimadas gravadas por geradores externos de XLSX.

    Alguns relatórios do SEI declaram no XML uma dimensão menor que a área real
    da planilha. Em ``read_only=True`` o openpyxl pode confiar nesse metadado e
    parar de iterar antes de alcançar os blocos ``Unidade Ensino:``.

    ``reset_dimensions`` mantém o modo streaming, mas força o leitor a percorrer
    as células realmente presentes no XML. Isso evita voltar ao modo normal, que
    tem consumo de memória muito maior.
    """
    reset = getattr(ws, "reset_dimensions", None)
    if callable(reset):
        reset()


def inspecionar_relatorio(caminho: Path) -> tuple[dict[str, Any], list[str]]:
    """Lê somente o necessário para validar e resumir um relatório do SEI.

    A leitura usa ``read_only=True`` e não materializa os registros em memória.
    É a primeira passagem usada pela importação robusta antes de qualquer gravação.
    """
    wb = load_workbook(caminho, data_only=True, read_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        _prepare_read_only_sheet(ws)
        ano: int | None = None
        semestre: int | None = None
        warnings: list[str] = []
        cursos_de_blocos: list[str] = []
        cursos_com_registros: list[str] = []
        alunos_unicos: set[str] = set()
        disciplinas: set[str] = set()
        turmas: set[tuple[str | None, str | None]] = set()
        total_registros = 0
        encontrou_bloco = False

        curso: str | None = None
        disciplina: str | None = None
        turma: str | None = None
        periodo: str | None = None
        lendo_alunos = False
        qtd_declarada: int | None = None
        alunos_bloco = 0
        bloco_inicio = 0
        curso_registrado_no_bloco = False

        def conferir_bloco() -> None:
            nonlocal qtd_declarada, alunos_bloco
            if qtd_declarada is not None and qtd_declarada != alunos_bloco:
                warnings.append(
                    f"Bloco linha {bloco_inicio} ({disciplina or 'disciplina não identificada'} / {turma or 'sem turma'}): "
                    f"relatório declara {qtd_declarada} aluno(s), parser encontrou {alunos_bloco}."
                )
            qtd_declarada = None
            alunos_bloco = 0

        for row_number, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if ano is None or semestre is None:
                parsed_year, parsed_semester = _parse_ano_semestre_linha(row)
                ano = ano or parsed_year
                semestre = semestre or parsed_semester

            first = limpar_texto(_valor_coluna(row, 0))
            if first == "Unidade Ensino:":
                if encontrou_bloco:
                    conferir_bloco()
                encontrou_bloco = True
                bloco_inicio = row_number
                curso = disciplina = turma = periodo = None
                lendo_alunos = False
                curso_registrado_no_bloco = False
                continue

            if not encontrou_bloco:
                continue

            if first == "Curso:":
                curso = limpar_texto(_valor_coluna(row, 2))
                if curso:
                    cursos_de_blocos.append(curso)
            elif first == "Disciplina:":
                disciplina = limpar_texto(_valor_coluna(row, 2))
                if disciplina:
                    disciplinas.add(disciplina)
            elif first == "Turma:":
                turma = limpar_texto(_valor_coluna(row, 2))
                periodo = limpar_texto(_valor_coluna(row, 13))
                if disciplina:
                    turmas.add((disciplina, turma))
            elif first == "Matrícula":
                lendo_alunos = True
            elif first == "Qtd de alunos:":
                raw = _valor_coluna(row, 2)
                try:
                    qtd_declarada = int(float(str(raw).replace(",", "."))) if raw not in (None, "") else None
                except (TypeError, ValueError):
                    qtd_declarada = None
                conferir_bloco()
                lendo_alunos = False
            elif lendo_alunos:
                matricula = limpar_texto(_valor_coluna(row, 0))
                nome = limpar_texto(_valor_coluna(row, 2))
                if matricula and nome:
                    if curso and not curso_registrado_no_bloco:
                        cursos_com_registros.append(curso)
                        curso_registrado_no_bloco = True
                    total_registros += 1
                    alunos_bloco += 1
                    alunos_unicos.add(matricula)

        if encontrou_bloco:
            conferir_bloco()
        if not encontrou_bloco:
            raise ValueError(
                "Não encontrei blocos iniciados por 'Unidade Ensino:'. "
                "O arquivo não parece seguir o modelo esperado do SEI."
            )
        if not total_registros:
            raise ValueError("Nenhum registro de aluno foi encontrado no arquivo.")

        curso_principal = Counter(cursos_de_blocos).most_common(1)[0][0] if cursos_de_blocos else None
        metadata = {
            "arquivo_origem": caminho.name,
            "curso": curso_principal,
            # Compatibilidade com a validação anterior ao parser streaming: somente
            # cursos de blocos que efetivamente produziram registros entram na
            # verificação de identidade. Blocos vazios/auxiliares do SEI não podem
            # bloquear uma importação válida de Bacharelado/Licenciatura.
            "cursos_encontrados": sorted(set(cursos_com_registros), key=str.casefold),
            "cursos_de_blocos": sorted(set(cursos_de_blocos), key=str.casefold),
            "ano": ano,
            "semestre": semestre,
            "aba": ws.title,
            "total_registros_aluno_disciplina": total_registros,
            "total_alunos_unicos": len(alunos_unicos),
            "total_disciplinas": len(disciplinas),
            "total_turmas": len(turmas),
            "parser_mode": "read_only_streaming",
        }
        return metadata, warnings
    finally:
        wb.close()


def iterar_registros(caminho: Path):
    """Produz registros aluno-disciplina sem manter o relatório inteiro em RAM."""
    wb = load_workbook(caminho, data_only=True, read_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        _prepare_read_only_sheet(ws)
        ano: int | None = None
        semestre: int | None = None
        curso: str | None = None
        disciplina: str | None = None
        turma: str | None = None
        periodo: str | None = None
        lendo_alunos = False

        for row in ws.iter_rows(values_only=True):
            if ano is None or semestre is None:
                parsed_year, parsed_semester = _parse_ano_semestre_linha(row)
                ano = ano or parsed_year
                semestre = semestre or parsed_semester

            first = limpar_texto(_valor_coluna(row, 0))
            if first == "Unidade Ensino:":
                curso = disciplina = turma = periodo = None
                lendo_alunos = False
                continue
            if first == "Curso:":
                curso = limpar_texto(_valor_coluna(row, 2))
                continue
            if first == "Disciplina:":
                disciplina = limpar_texto(_valor_coluna(row, 2))
                continue
            if first == "Turma:":
                turma = limpar_texto(_valor_coluna(row, 2))
                periodo = limpar_texto(_valor_coluna(row, 13))
                continue
            if first == "Matrícula":
                lendo_alunos = True
                continue
            if first == "Qtd de alunos:":
                lendo_alunos = False
                continue
            if not lendo_alunos or not disciplina:
                continue

            matricula = limpar_texto(_valor_coluna(row, 0))
            nome = limpar_texto(_valor_coluna(row, 2))
            if not matricula or not nome:
                continue
            situacao = limpar_texto(_valor_coluna(row, 17))
            yield {
                "matricula": matricula,
                "nome": nome,
                "curso": curso,
                "ano": ano,
                "semestre": semestre,
                "disciplina": disciplina,
                "turma": turma,
                "periodo": periodo,
                "media": parse_media(_valor_coluna(row, 10)),
                "situacao": situacao,
                "aprovado": classificacao_aprovacao(situacao),
                "motivo_reprovacao": motivo_reprovacao(situacao),
            }
    finally:
        wb.close()


def ler_registros(caminho: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Compatibilidade com consumidores legados.

    Novas importações devem preferir ``inspecionar_relatorio`` + ``iterar_registros``
    para manter o uso de memória limitado.
    """
    metadata, warnings = inspecionar_relatorio(caminho)
    registros = list(iterar_registros(caminho))
    return metadata, registros, warnings

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
