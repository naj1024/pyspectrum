import pytest

from dataSources import DataSource_file
from misc import FileMetaData


def test_file_not_present():
    with pytest.raises(Exception):
        _ = DataSource_file.Input("no_file", 1024, "16tr", 1.0, 1.0, 1.0)


def test_illegal_type():
    with pytest.raises(Exception):
        _ = DataSource_file.Input("./test_file_input.py", 1024, "128g", 1.0, 1.0, 1.0)


def test_parse_filename():
    assert FileMetaData.parse_filename("test.cplx.1000.16tle") == (True, "16tle", True, 1000.0, 0.0)


def test_parse_filename_with_cf():
    assert FileMetaData.parse_filename("test.cf433.5.cplx.1000.16tle") == (True, "16tle", True, 1000.0, 433500000.0)


def test_parse_filename_with_bad_cf_number():
    assert FileMetaData.parse_filename("test.cf433.a.cplx.1000.16tle") == (True, "16tle", True, 1000.0, 0.0)


def test_parse_filename_centre_frequency():
    assert FileMetaData.parse_filename("test.cf1234.1.cplx.2000.16tle") == (True, "16tle", True, 2000.0, 1234.1e6)


def test_parse_filename_centre_frequency_no_decimal_point():
    assert FileMetaData.parse_filename("test.cf1234.cplx.2000.16tbe") == (True, "16tbe", True, 2000.0, 1234e6)


def test_parse_filename_ignore_too_many_cf_in_filename():
    assert FileMetaData.parse_filename("test.cf.zero.cf1234.cplx.2000.16tbe") == (True, "16tbe", True, 2000.0, 0.0)


def test_parse_filename_not_enough_fields():
    ok, _, _, _, _ = FileMetaData.parse_filename("test.cplx.1000")
    assert not ok


def test_parse_filename_unsupported_real():
    ok, _, _, _, _ = FileMetaData.parse_filename("test.real.1000.16tle")
    assert not ok


def test_parse_filename_illegal_real_complex_type():
    ok, _, _, _, _ = FileMetaData.parse_filename("test.imag.1000.16tle")
    assert not ok


def test_parse_filename_illegal_data_type():
    ok, _, _, _, _ = FileMetaData.parse_filename("test.imag.1000.7f")
    assert not ok


def test_parse_filename_illegal_sample_rate():
    ok, _, _, _, _ = FileMetaData.parse_filename("test.cplx.twoMhz.8t")
    assert not ok
