from pathlib import Path
from app.importers.generic_bank_xlsx import parse_generic_bank_xlsx

FIXTURE = Path(__file__).parent / "fixtures" / "openpyxl-sample.xlsx"


def test_parses_real_sample_file_correctly():
    data = FIXTURE.read_bytes()
    result = parse_generic_bank_xlsx(data, account_id=1)

    assert len(result["transactions"]) == 3

    t0 = result["transactions"][0]
    assert t0.type == "expense"
    assert t0.amount == 15015000
    assert t0.description == "خرید کالا از اینترنت"
    assert t0.document_number == "14052732973246"
    assert len(t0.transaction_date.split("-")) == 3  # ISO date format

    t1 = result["transactions"][1]
    assert t1.type == "income"
    assert t1.amount == 1525000

    t2 = result["transactions"][2]
    assert t2.type == "adjustment"
    assert t2.document_number == "S14052418626971"
