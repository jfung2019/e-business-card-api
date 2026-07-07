"""Live OpenRouter OCR parse smoke test. Run from e-business-card-api:
    python scripts/test_ocr_parse.py
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.services.openrouter import OpenRouterService

ENV = dotenv_values(Path(__file__).resolve().parents[1] / ".env")

# Simulated on-device OCR (front + back), based on Megaannum cards.
SAMPLE_OCR_FRONT_ONLY = """
Dr. Sam Shiu 邵錦頌博士
Chief Investment Officer
首席投資官
Megaannum Technology Limited
sam@megaannum.ai
+65 8778 0099
+852 6154 4240
www.megaannum.ai
Room 1705, 17/F, Harcourt House
39 Gloucester Road, Wan Chai, Hong Kong
香港灣仔告士打道39號夏慤大廈17樓1705室
""".strip()

SAMPLE_OCR_FRONT_BACK = """
Dr. QIAN Shogun
Chief Scientist
Megaannum Technology Limited
shogun@megaannum.ai
+86 177 4978 9261
www.megaannum.ai
Room 1705, 17/F, Harcourt House, 39 Gloucester Road, Wan Chai, Hong Kong
--- BACK ---
錢曉軍博士
香港灣仔告士打道39號夏慤大廈17樓1705室
""".strip()

# OCR that drops Chinese (common when address is only on back and back scan has poor OCR).
SAMPLE_OCR_ENGLISH_ONLY = """
Dr. Sam Shiu
Chief Investment Officer
Megaannum Technology Limited
sam@megaannum.ai
+65 8778 0099
www.megaannum.ai
Room 1705, 17/F, Harcourt House, 39 Gloucester Road, Wan Chai, Hong Kong
""".strip()


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def summarize(label: str, result) -> None:
    custom = dict(result.custom_fields)
    address_ch = custom.get("address_ch")
    print(f"\n=== {label} ===")
    print("name:", result.core_fields.name)
    print("custom_fields keys:", sorted(custom.keys()))
    print("address_en:", custom.get("address_en", custom.get("Address (English)", "(missing)")))
    print("address_ch:", address_ch or "(missing)")
    if address_ch:
        print("address_ch has Chinese chars:", has_chinese(address_ch))
    print("full custom_fields:", json.dumps(custom, ensure_ascii=False, indent=2))


async def main() -> None:
    settings = Settings(
        _env_file=None,
        openrouter_api_key=ENV.get("OPENROUTER_API_KEY") or "",
        openrouter_model=ENV.get("OPENROUTER_MODEL") or "google/gemini-2.5-flash",
    )
    print("Model:", settings.openrouter_model)
    service = OpenRouterService(settings)
    cases = [
        ("Front OCR with EN+ZH on same side", SAMPLE_OCR_FRONT_ONLY),
        ("Front+back OCR (--- BACK ---)", SAMPLE_OCR_FRONT_BACK),
        ("English-only OCR (no Chinese in input)", SAMPLE_OCR_ENGLISH_ONLY),
    ]
    for label, ocr_text in cases:
        print(f"\nInput has Chinese: {has_chinese(ocr_text)}")
        result = await service.parse_ocr_text(ocr_text)
        summarize(label, result)


if __name__ == "__main__":
    asyncio.run(main())
