"""Tests for the CLI."""

import json
import os
from unittest import mock

import pytest

from trollflow2.cli import cli, parse_args
from trollflow2.tests.test_launcher import pnuus_log_config

yaml_test_noop = """
product_list:
  output_dir: &output_dir
    /mnt/output/
  publish_topic: /MSG_0deg/L3
  reader: seviri_l1b_hrit
  fname_pattern:
    "{start_time:%Y%m%d_%H%M}_{platform_name}_{areaname}_{productname}.{format}"
  formats:
    - format: tif
      writer: geotiff
  areas:
      euro4:
        areaname: euro4
        products:
          overview:
            productname: overview
          airmass:
            productname: airmass
          natural_color:
            productname: natural_color
          night_fog:
            productname: night_fog

workers: []
"""


@pytest.fixture
def product_list_filename(tmp_path):
    """Filename for a test product list, with contents."""
    product_list = "my_product_list.yaml"
    filename = os.fspath(tmp_path / product_list)
    with open(filename, "w") as fd:
        fd.write(yaml_test_noop)
    return filename


def test_arg_parsing():
    """Test parsing args."""
    product_list = "my_product_list.yaml"
    log_config = "my_log_config.yaml"
    files = ["file1", "file2"]
    res = parse_args(["-p", product_list, *files, "-c", log_config])
    assert res.product_list == product_list
    assert res.files == files
    assert res.log_config == log_config


def test_arg_parsing_fails_without_product_list():
    """Test args parsing fails without a product list."""
    log_config = "my_log_config.yaml"
    files = ["file1", "file2"]
    with pytest.raises(SystemExit):
        parse_args([*files, "-c", log_config])


def test_cli_logs_starting(tmp_path, caplog, empty_product_list):
    """Test that the cli logs satpy starting."""
    product_list = empty_product_list
    log_config = "my_log_config.yaml"
    log_config_filename = os.fspath(tmp_path / log_config)
    with open(log_config_filename, mode="w") as fd:
        fd.write(pnuus_log_config)
    files = ["file1", "file2"]
    with pytest.raises(IOError):
        cli(["-p", os.fspath(product_list), *files, "-c", log_config_filename])
    assert "Starting Satpy." in caplog.text


@pytest.fixture
def empty_product_list(tmp_path):
    """Create an empty product list."""
    product_list = "my_product_list.yaml"
    product_file = tmp_path / product_list
    with open(product_file, "w"):
        pass
    return product_file


def test_cli_raises_an_error_when_product_list_is_empty(tmp_path, caplog, empty_product_list):
    """Test that the cli raises an error when the product list is empty."""
    product_list = empty_product_list
    files = ["file1", "file2"]
    product_list_filename = os.fspath(tmp_path / product_list)
    with open(product_list_filename, "w"):
        pass
    with pytest.raises(IOError):
        cli(["-p", os.fspath(product_list), *files])
    assert "check YAML file" in caplog.text


def test_cli_starts_processing_when_files_are_provided(tmp_path, product_list_filename):
    """Test that the cli start processing when files are provided."""
    files = ["file1", "file2"]
    from trollflow2.launcher import process_files
    new_process = mock.Mock(wraps=process_files)
    mda = {"dish": "pizza"}
    with mock.patch("trollflow2.cli.process_files", new=new_process):
        with mock.patch("trollflow2.cli.Queue") as q_mock:
            cli(["-p", os.fspath(product_list_filename), "-m", json.dumps(mda), *files])
    new_process.assert_called_once_with(files, mda, product_list_filename, q_mock.return_value)


def test_cli_dask_profiler(product_list_filename, tmp_path):
    """Test that dask profiles are written."""
    from trollflow2.launcher import process_files
    new_process = mock.Mock(wraps=process_files)
    proffile = tmp_path / "dask-prof.html"
    with (mock.patch("trollflow2.cli.process_files", new=new_process),
          mock.patch("trollflow2.cli.Queue")):
        cli(["-p", os.fspath(product_list_filename), "--dask-profiler",
             os.fspath(proffile), "--dask-resource-profiler", "0.1",
             "-m", json.dumps({"food": "soy"}), "aquafaba", "tempeh"])
    assert proffile.exists()
