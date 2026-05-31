from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "boms"


@pytest.fixture(scope="session", autouse=True)
def create_xlsx_fixture() -> None:
    """Generate the xlsx fixture from the csv fixture programmatically."""
    xlsx_path = FIXTURES_DIR / "iot_board.xlsx"
    if xlsx_path.exists():
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM"
    rows = [
        ["Ref", "MPN", "Manufacturer", "Description", "Qty", "Unit"],
        ["U1", "STM32F103C8T6", "STMicroelectronics", "ARM Cortex-M3 MCU", 1, "pcs"],
        ["U2", "ESP8266EX", "Espressif", "WiFi SoC", 1, "pcs"],
        ["C1", "GRM188R61A106KE69D", "Murata", "100uF 10V MLCC", 10, "pcs"],
        ["R1", "RC0402FR-0710KL", "Yageo", "10K Ohm 1% 1/16W", 20, "pcs"],
        ["L1", "SRR1260-100Y", "Bourns", "10uH Power Inductor", 2, "pcs"],
        ["PCB1", None, "Custom", "4-layer PCB 100x80mm", 1, "pcs"],
    ]
    for row in rows:
        ws.append(row)
    wb.save(xlsx_path)


def load_fixture(name: str) -> bytes:
    path = FIXTURES_DIR / name
    return path.read_bytes()
