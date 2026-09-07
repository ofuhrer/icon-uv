"""Consumer contract checks, including malformed-but-valid JSON payloads."""
from copy import deepcopy
from importlib.resources import files
import json

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest

from test_daily import AnalyticTable, catalog, export_daily, grid


def validator():
    schema = json.loads(files('icon_uv').joinpath('data/daily-uv.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def payload():
    table = AnalyticTable(); table.sha256 = 'a'*64
    ds = grid(); ds.attrs['radiation_table_sha256'] = table.sha256
    return export_daily(ds, catalog(), '2026-09-06T06:00:00Z', table=table)


def test_valid_and_unavailable_records_satisfy_schema():
    p = payload()
    assert {e['status'] for e in p['entries']} == {'ok', 'unavailable'}
    validator().validate(p)


@pytest.mark.parametrize('field,value', [('category','low'), ('display_uvi',-1),
                                       ('source_cells',[1.5]), ('quality_flag',65536)])
def test_malformed_valid_record_is_rejected(field, value):
    p = payload(); p['entries'][0][field] = value
    with pytest.raises(ValidationError): validator().validate(p)


def test_null_cannot_become_zero_or_normal_forecast():
    p = payload()
    for changes in [{'uvi':0}, {'status':'ok'}, {'reasons':[]}]:
        modified = deepcopy(p); modified['entries'][2].update(changes)
        with pytest.raises(ValidationError): validator().validate(modified)
