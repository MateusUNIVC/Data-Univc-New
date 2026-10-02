from __future__ import annotations

from datetime import datetime

from openpyxl import Workbook
from openpyxl.packaging.custom import DateTimeProperty, IntProperty, StringProperty

from .contract import WorkbookSpec

CUSTOM_PROPERTY_NAMES: tuple[str, ...] = (
    "DataUNIVC.ExportId",
    "DataUNIVC.GeneratedAt",
    "DataUNIVC.GeneratedBy",
    "DataUNIVC.DirectorateCode",
    "DataUNIVC.AuthorizationScope",
    "DataUNIVC.SystemVersion",
    "DataUNIVC.SchemaVersion",
    "DataUNIVC.ExcelContractVersion",
    "DataUNIVC.AdapterCode",
    "DataUNIVC.AdapterVersion",
    "DataUNIVC.PayloadHash",
)


def _set_custom_property(workbook: Workbook, prop) -> None:
    workbook.custom_doc_props.props[:] = [item for item in workbook.custom_doc_props.props if item.name != prop.name]
    workbook.custom_doc_props.append(prop)


def apply_workbook_metadata(workbook: Workbook, spec: WorkbookSpec) -> None:
    props = workbook.properties
    props.title = spec.identity.workbook_title
    props.subject = f"Excel Oficial - {spec.identity.directorate_label}"
    props.creator = spec.snapshot.generated_by or spec.identity.system_name
    props.lastModifiedBy = spec.identity.system_name
    props.keywords = "Data UNIVC; Excel Oficial; snapshot; governanca"
    props.description = (
        f"Snapshot offline do {spec.identity.system_name} para {spec.identity.directorate_label}. "
        f"Export ID: {spec.snapshot.export_id}."
    )
    props.created = spec.snapshot.generated_at.replace(tzinfo=None) if spec.snapshot.generated_at.tzinfo else spec.snapshot.generated_at
    props.modified = datetime.now().replace(microsecond=0)

    generated_at = spec.snapshot.generated_at.replace(tzinfo=None) if spec.snapshot.generated_at.tzinfo else spec.snapshot.generated_at
    values = (
        StringProperty(name="DataUNIVC.ExportId", value=spec.snapshot.export_id),
        DateTimeProperty(name="DataUNIVC.GeneratedAt", value=generated_at),
        StringProperty(name="DataUNIVC.GeneratedBy", value=spec.snapshot.generated_by or ""),
        StringProperty(name="DataUNIVC.DirectorateCode", value=spec.identity.directorate_code),
        StringProperty(name="DataUNIVC.AuthorizationScope", value=", ".join(spec.snapshot.authorization_scope)),
        StringProperty(name="DataUNIVC.SystemVersion", value=spec.snapshot.system_version),
        StringProperty(name="DataUNIVC.SchemaVersion", value=str(spec.snapshot.schema_version)),
        IntProperty(name="DataUNIVC.ExcelContractVersion", value=int(spec.snapshot.contract_version)),
        StringProperty(name="DataUNIVC.AdapterCode", value=spec.identity.adapter_code),
        IntProperty(name="DataUNIVC.AdapterVersion", value=int(spec.snapshot.adapter_version)),
        StringProperty(name="DataUNIVC.PayloadHash", value=spec.snapshot.payload_hash or ""),
    )
    for prop in values:
        _set_custom_property(workbook, prop)


__all__ = ["CUSTOM_PROPERTY_NAMES", "apply_workbook_metadata"]
