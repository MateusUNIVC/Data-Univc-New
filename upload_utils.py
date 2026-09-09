from __future__ import annotations

import os
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException, UploadFile


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


MAX_UPLOAD_BYTES = _positive_int_env("MAX_UPLOAD_MB", 25) * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = _positive_int_env("MAX_XLSX_UNCOMPRESSED_MB", 250) * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024


async def save_validated_excel_upload(upload: UploadFile, destination: Path) -> int:
    """Stream an uploaded workbook to disk and validate its OOXML package.

    The function never loads the entire file in memory. It rejects oversized,
    corrupted or non-workbook ZIP packages before repository parsing begins.
    """
    total = 0
    try:
        with destination.open("wb") as target:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"A planilha excede o limite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                    )
                target.write(chunk)
    finally:
        await upload.close()

    if total == 0:
        raise HTTPException(status_code=400, detail="A planilha enviada está vazia.")

    try:
        with ZipFile(destination) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "xl/workbook.xml"}
            if not required.issubset(names):
                raise HTTPException(status_code=400, detail="O arquivo não é uma pasta de trabalho Excel válida.")
            uncompressed = sum(max(0, item.file_size) for item in archive.infolist())
            if uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="A planilha possui conteúdo descompactado acima do limite de segurança.",
                )
            broken = archive.testzip()
            if broken:
                raise HTTPException(status_code=400, detail="A planilha está corrompida e não pôde ser validada.")
    except HTTPException:
        raise
    except BadZipFile as exc:
        raise HTTPException(status_code=400, detail="O arquivo enviado não é um XLSX/XLSM válido.") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível validar a planilha enviada.") from exc

    return total
