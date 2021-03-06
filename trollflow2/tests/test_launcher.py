#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2019 Pytroll developers
#
# Author(s):
#
#   Martin Raspaud <martin.raspaud@smhi.se>
#   Panu Lahtinen <pnuu+git@iki.fi>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
"""Test the launcher module."""

import sys
import time
import pytest
import unittest
import datetime
import logging
import queue

import yaml

try:
    from yaml import UnsafeLoader
except ImportError:
    from yaml import Loader as UnsafeLoader
from unittest import mock
from trollflow2.tests.utils import TestCase

yaml_test1 = """
product_list:
  something: foo
  min_coverage: 5.0
  subscribe_topics:
    - /topic1
    - /topic2
  areas:
      euron1:
        areaname: euron1
        min_coverage: 20.0
        priority: 1
        products:
          ctth:
            productname: cloud_top_height
            output_dir: /tmp/satdmz/pps/www/latest_2018/
            formats:
              - format: png
                writer: simple_image
              - format: jpg
                writer: simple_image
                fill_value: 0
            fname_pattern: "{platform_name:s}_{start_time:%Y%m%d_%H%M}_{areaname:s}_ctth.{format}"

      germ:
        areaname: germ
        fname_pattern: "{start_time:%Y%m%d_%H%M}_{areaname:s}_{productname}.{format}"
        products:
          cloudtype:
            productname: cloudtype
            output_dir: /tmp/satdmz/pps/www/latest_2018/
            formats:
              - format: png
                writer: simple_image

      omerc_bb:
        areaname: omerc_bb
        output_dir: /tmp
        products:
          ct:
            productname: ct
            formats:
              - format: nc
                writer: cf
          cloud_top_height:
            productname: cloud_top_height
            formats:
              - format: tif
                writer: geotiff
"""

yaml_test_minimal = """
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

# workers:
#   - fun: !!python/name:trollflow2.create_scene
#   - fun: !!python/name:trollflow2.load_composites
#   - fun: !!python/name:trollflow2.resample
#   - fun: !!python/name:trollflow2.save_datasets
#   - fun: !!python/object:trollflow2.FilePublisher {}
"""


class TestGetAreaPriorities(TestCase):
    """Test case for area priorities."""

    def test_get_area_priorities(self):
        """Test getting the area priorities."""
        from trollflow2.launcher import get_area_priorities
        prodlist = yaml.load(yaml_test1, Loader=UnsafeLoader)

        priorities = get_area_priorities(prodlist)
        self.assertTrue(1 in priorities)
        self.assertTrue(isinstance(priorities[1], list))
        self.assertTrue('euron1' in priorities[1])
        self.assertTrue(999 in priorities)
        self.assertTrue(isinstance(priorities[999], list))
        self.assertTrue('omerc_bb' in priorities[999])
        self.assertTrue('germ' in priorities[999])


class TestMessageToJobs(TestCase):
    """Test case for converting a message to jobs."""

    def test_message_to_jobs(self):
        """Test converting message to jobs."""
        from trollflow2.launcher import message_to_jobs
        prodlist = yaml.load(yaml_test1, Loader=UnsafeLoader)
        msg = mock.MagicMock()
        msg.data = {'uri': 'foo'}

        jobs = message_to_jobs(msg, prodlist)
        self.assertEqual(set(jobs.keys()), {1, 999})
        for i in jobs.keys():
            self.assertEqual(set(jobs[i].keys()),
                             {'input_filenames', 'input_mda', 'product_list'})
            self.assertEqual(jobs[i]['input_filenames'], ['foo'])
            self.assertEqual(jobs[i]['input_mda'], msg.data)
            self.assertEqual(set(jobs[i]['product_list'].keys()),
                             {'product_list'})
        self.assertEqual(set(jobs[1]['product_list']['product_list']['areas'].keys()),
                         set(['euron1']))
        self.assertEqual(set(jobs[999]['product_list']['product_list']['areas'].keys()),
                         set(['germ', 'omerc_bb']))

        prodlist['product_list']['areas']['germ']['priority'] = None
        jobs = message_to_jobs(msg, prodlist)
        self.assertTrue('germ' in jobs[999]['product_list']['product_list']['areas'])

    def test_message_to_jobs_minimal(self):
        """Test converting a message to minimal jobs."""
        from trollflow2.launcher import message_to_jobs
        prodlist = yaml.load(yaml_test_minimal, Loader=UnsafeLoader)
        msg = mock.MagicMock()
        msg.data = {'uri': 'foo'}
        jobs = message_to_jobs(msg, prodlist)

        expected = dict([('euro4',
                          {'areaname': 'euro4',
                           'products': {'airmass': {'formats': [{'format': 'tif',
                                                                 'writer': 'geotiff'}],
                                                    'productname': 'airmass'},
                                        'natural_color': {'formats': [{'format': 'tif',
                                                                       'writer': 'geotiff'}],
                                                          'productname': 'natural_color'},
                                        'night_fog': {'formats': [{'format': 'tif',
                                                                   'writer': 'geotiff'}],
                                                      'productname': 'night_fog'},
                                        'overview': {'formats': [{'format': 'tif',
                                                                  'writer': 'geotiff'}],
                                                     'productname': 'overview'}}})])
        self.assertDictEqual(jobs[999]['product_list']['product_list']['areas'], expected)
        self.assertIn('output_dir', jobs[999]['product_list']['product_list'])
        # Test that the formats are not the same object
        prods = jobs[999]['product_list']['product_list']['areas']['euro4']['products']
        self.assertFalse(prods['overview']['formats'][0] is
                         prods['natural_color']['formats'][0])
        prods['overview']['formats'][0]['foo'] = 'bar'
        self.assertFalse('foo' in prods['natural_color']['formats'][0])

    def test_message_to_jobs_fsspec(self):
        """Test transforming a message containing filesystem specification."""
        with mock.patch.dict('sys.modules', {'fsspec': mock.MagicMock(),
                                             'fsspec.spec': mock.MagicMock(),
                                             'satpy': mock.MagicMock(),
                                             'satpy.readers': mock.MagicMock(),
                                             'satpy.resample': mock.MagicMock(),
                                             'satpy.writers': mock.MagicMock(),
                                             'satpy.dataset': mock.MagicMock(),
                                             'satpy.version': mock.MagicMock()}):
            from fsspec.spec import AbstractFileSystem as abs_fs
            from satpy.readers import FSFile as fsfile
            from trollflow2.launcher import message_to_jobs
            import json

            filename = "/S3A_OL_2_WFR____20201210T080758_20201210T080936_20201210T103707_0097_066_078_1980_MAR_O_NR_002.SEN3/Oa01_reflectance.nc"  # noqa
            fs = {"cls": "fsspec.implementations.zip.ZipFileSystem",
                  "protocol": "abstract",
                  "args": ["sentinel-s3-ol2wfr-zips/2020/12/10/S3A_OL_2_WFR____20201210T080758_20201210T080936_20201210T103707_0097_066_078_1980_MAR_O_NR_002.zip"],  # noqa
                  "target_protocol": "s3",
                  "target_options": {"anon": False,
                                     "client_kwargs": {"endpoint_url": "https://my.dismi.se"}}}
            msg_data = {"dataset": [{"filesystem": fs,
                                     "uid": "zip:///S3A_OL_2_WFR____20201210T080758_20201210T080936_20201210T103707_0097_066_078_1980_MAR_O_NR_002.SEN3/Oa01_reflectance.nc::s3:///sentinel-s3-ol2wfr-zips/2020/12/10/S3A_OL_2_WFR____20201210T080758_20201210T080936_20201210T103707_0097_066_078_1980_MAR_O_NR_002.zip",  # noqa
                                     "uri": "zip://" + filename
                                     }]
                        }

            msg = mock.MagicMock()
            msg.data = msg_data

            prodlist = yaml.load(yaml_test_minimal, Loader=UnsafeLoader)
            jobs = message_to_jobs(msg, prodlist)
            filesystemfile = jobs[999]['input_filenames'][0]

            assert filesystemfile == fsfile.return_value
            fsfile.assert_called_once_with(filename, abs_fs.from_json.return_value)
            abs_fs.from_json.assert_called_once_with(json.dumps(fs))


class TestRun(TestCase):
    """Test case for running the plugins."""

    def setUp(self):
        """Set up the test case."""
        super().setUp()
        self.config = yaml.load(yaml_test1, Loader=UnsafeLoader)

    def test_run_does_not_call_process_directly(self):
        """Test that process is called through Process."""
        from trollflow2.launcher import run
        with mock.patch('trollflow2.launcher.yaml.load'),\
                mock.patch('trollflow2.launcher.open'),\
                mock.patch('trollflow2.launcher.generate_messages') as generate_messages,\
                mock.patch('trollflow2.launcher.process') as process,\
                mock.patch('trollflow2.launcher.check_results'),\
                mock.patch('multiprocessing.Process'):
            generate_messages.side_effect = ['foo', KeyboardInterrupt]
            prod_list = 'bar'
            try:
                run(prod_list)
            except KeyboardInterrupt:
                pass
            process.assert_not_called()

    def test_run_uses_process_via_multiprocessing(self):
        """Test that process is called through Process."""
        from trollflow2.launcher import run
        from threading import Thread
        with mock.patch('trollflow2.launcher.yaml.load'),\
                mock.patch('trollflow2.launcher.open'),\
                mock.patch('trollflow2.launcher.generate_messages') as generate_messages,\
                mock.patch('trollflow2.launcher.process') as process,\
                mock.patch('multiprocessing.Process') as Process:
            def gen_messages(*args):
                del args
                yield 'foo'
                raise KeyboardInterrupt
            generate_messages.side_effect = gen_messages
            Process.side_effect = Thread
            prod_list = 'bar'
            try:
                run(prod_list)
            except KeyboardInterrupt:
                pass
            process.assert_called_once()

    def test_run_relies_on_listener(self):
        """Test running relies on listener."""
        from trollflow2.launcher import run
        with mock.patch('trollflow2.launcher.yaml.load') as yaml_load,\
                mock.patch('trollflow2.launcher.open'),\
                mock.patch('multiprocessing.Process') as Process,\
                mock.patch('trollflow2.launcher.ListenerContainer') as lc_:
            listener = mock.MagicMock()
            listener.output_queue.get.return_value = 'foo'
            lc_.return_value = listener
            proc_ret = mock.MagicMock()
            Process.return_value = proc_ret
            # stop looping
            proc_ret.join.side_effect = KeyboardInterrupt
            yaml_load.return_value = self.config
            prod_list = 'bar'
            try:
                run(prod_list)
            except KeyboardInterrupt:
                pass
            listener.output_queue.called_once()
            lc_.assert_called_with(addresses=None, nameserver='localhost',
                                   topics=['/topic1', '/topic2'])
            # Subscriber topics are removed from config
            self.assertTrue('subscribe_topics' not in self.config['product_list'])
            # Topics are given as command line option
            lc_.reset_mock()
            try:
                run(prod_list, connection_parameters=dict(topic=['/topic3']))
            except KeyboardInterrupt:
                pass
            lc_.assert_called_with(addresses=None, nameserver='localhost',
                                   topics=['/topic3'])

    def test_run_starts_and_joins_process(self):
        """Test running."""
        from trollflow2.launcher import run
        with mock.patch('trollflow2.launcher.yaml.load') as yaml_load,\
                mock.patch('trollflow2.launcher.open'),\
                mock.patch('multiprocessing.Process') as Process,\
                mock.patch('trollflow2.launcher.ListenerContainer') as lc_:
            listener = mock.MagicMock()
            listener.output_queue.get.return_value = 'foo'
            lc_.return_value = listener
            proc_ret = mock.MagicMock()
            Process.return_value = proc_ret
            # stop looping
            proc_ret.join.side_effect = KeyboardInterrupt
            yaml_load.return_value = self.config
            prod_list = 'bar'
            try:
                run(prod_list)
            except KeyboardInterrupt:
                pass
            proc_ret.start.assert_called_once()
            proc_ret.join.assert_called_once()


class TestInterruptRun(TestCase):
    """Test case for running the plugins."""

    def setUp(self):
        """Set up the test case."""
        super().setUp()
        self.config = yaml.load(yaml_test1, Loader=UnsafeLoader)

    def test_run_keyboard_interrupt(self):
        """Test interrupting the run with a ctrl-C."""
        from trollflow2.launcher import run
        with mock.patch('trollflow2.launcher.yaml.load'),\
                mock.patch('trollflow2.launcher.open'),\
                mock.patch('trollflow2.launcher.ListenerContainer') as lc_:
            listener = mock.MagicMock()
            get = mock.Mock()
            get.side_effect = KeyboardInterrupt
            listener.output_queue.get = get
            lc_.return_value = listener
            run(0)
            listener.stop.assert_called_once()


class TestRunLogging(TestCase):
    """Test case for checking the logging in `run`."""

    def setUp(self):
        """Set up the test case."""
        super().setUp()
        self.config = yaml.load(yaml_test1, Loader=UnsafeLoader)

    def test_target_fun_logs_to_existing_handlers(self):
        """Test that target_fun logs to existing handlers."""
        from trollflow2.launcher import run
        from trollflow2.launcher import LOG
        from threading import Thread
        with mock.patch('trollflow2.launcher.yaml.load'),\
                mock.patch('trollflow2.launcher.open'), \
                mock.patch('trollflow2.launcher.process') as process,\
                mock.patch('trollflow2.launcher.generate_messages') as generate_messages, \
                mock.patch('trollflow2.launcher.check_results'), \
                mock.patch('multiprocessing.Process') as Process:

            def fake_process(*args, **kwargs):
                LOG.error('hej')

            fake_handler = mock.MagicMock()
            fake_handler.level = 0
            Process.side_effect = Thread
            process.side_effect = fake_process
            generate_messages.return_value = ['bla']

            try:
                LOG.addHandler(fake_handler)
                run(0)
            finally:
                LOG.removeHandler(fake_handler)
            assert fake_handler.method_calls

    def test_target_fun_does_not_log_to_existing_handlers_directly(self):
        """Test that target_fun does not log to existing handlers directly."""
        from trollflow2.launcher import run
        from trollflow2.launcher import LOG
        from threading import Thread
        with mock.patch('trollflow2.launcher.yaml.load'),\
                mock.patch('trollflow2.launcher.open'), \
                mock.patch('trollflow2.launcher.process') as process,\
                mock.patch('trollflow2.launcher.generate_messages') as generate_messages, \
                mock.patch('trollflow2.launcher.check_results'), \
                mock.patch('multiprocessing.Process') as Process:

            def fake_process(*args, **kwargs):
                LOG.error('hej')

            fake_handler = mock.MagicMock()
            fake_handler.level = 0
            Process.side_effect = Thread
            process.side_effect = fake_process
            generate_messages.return_value = ['bla']

            try:
                LOG.addHandler(fake_handler)
                original_handlers = set(LOG.handlers.copy())
                run(0)
                assert len(LOG.handlers) >= 1
                new_handlers = set(LOG.handlers.copy())
                assert len(new_handlers & original_handlers) == 0
            finally:
                LOG.removeHandler(fake_handler)


class TestExpand(TestCase):
    """Test expanding the product list."""

    def test_expand(self):
        """Test expanding the product list."""
        from trollflow2.launcher import expand
        inside = {'a': 'b'}
        outside = {'c': inside, 'd': inside}
        expanded = expand(outside)
        self.assertIsNot(expanded['d'], expanded['c'])


class TestProcess(TestCase):
    """Test case for the subprocessing."""

    def test_process(self):
        """Test subprocessing."""
        from trollflow2.launcher import process
        with mock.patch('trollflow2.launcher.traceback') as traceback,\
                mock.patch('trollflow2.launcher.sendmail') as sendmail,\
                mock.patch('trollflow2.launcher.expand') as expand,\
                mock.patch('trollflow2.launcher.yaml') as yaml_,\
                mock.patch('trollflow2.launcher.message_to_jobs') as message_to_jobs,\
                mock.patch('trollflow2.launcher.open') as open_,\
                mock.patch('trollflow2.launcher.get_dask_client') as gdc:

            fid = mock.MagicMock()
            fid.read.return_value = yaml_test1
            open_.return_value.__enter__.return_value = fid
            mock_config = mock.MagicMock()
            yaml_.load.return_value = mock_config
            yaml_.YAMLError = yaml.YAMLError
            # Make a client that has no `.close()` method (for coverage)
            client = mock.MagicMock()
            client.close.side_effect = AttributeError
            gdc.return_value = client
            fun1 = mock.MagicMock()
            # Return something resembling a config
            expand.return_value = {"workers": [{"fun": fun1}]}

            message_to_jobs.return_value = {1: {"job1": dict([])}}
            the_queue = mock.MagicMock()
            fun1.stop.assert_not_called()
            process("msg", "prod_list", the_queue)
            fun1.stop.assert_called_once()

            open_.assert_called_with("prod_list")
            yaml_.load.assert_called_once()
            message_to_jobs.assert_called_with("msg", {"workers": [{"fun": fun1}]})
            fun1.assert_called_with({'job1': {}, 'processing_priority': 1, 'produced_files': the_queue})
            gdc.assert_called_once()
            client.close.assert_called_once()

            fun1.stop = mock.MagicMock(side_effect=AttributeError('boo'))
            process("msg", "prod_list", the_queue)

            # Test that errors are propagated
            fun1.side_effect = KeyboardInterrupt
            with self.assertRaises(KeyboardInterrupt):
                process("msg", "prod_list", the_queue)
            # Test crash hander call.  This will raise KeyError as there
            # are no configured workers in the config returned by expand()
            traceback.format_exc.return_value = 'baz'
            crash_handlers = {"crash_handlers": {"config": {"foo": "bar"},
                                                 "handlers": [{"fun": sendmail}]}}
            expand.return_value = crash_handlers
            with self.assertRaises(KeyError):
                process("msg", "prod_list", the_queue)
            config = crash_handlers['crash_handlers']['config']
            sendmail.assert_called_once_with(config, 'baz')

            # Test failure in open(), e.g. a missing file
            open_.side_effect = IOError
            with self.assertRaises(IOError):
                process("msg", "prod_list", the_queue)

            # Test failure in yaml.load(), e.g. bad formatting
            open_.side_effect = yaml.YAMLError
            with self.assertRaises(yaml.YAMLError):
                process("msg", "prod_list", the_queue)

            # Test timeout in running job
            @pytest.mark.skipIf(sys.platform != "linux",
                                "Timeout only supported on Linux")
            def wait(job):
                time.sleep(0.1)
            fun1.reset_mock(return_value=True, side_effect=True)
            open_.reset_mock(return_value=True, side_effect=True)
            expand.reset_mock(return_value=True, side_effect=True)
            expand.return_value = {"workers": [{"fun": fun1, "timeout": 0.05}]}
            fun1.side_effect = wait
            with pytest.raises(TimeoutError, match="Timeout for .* expired "
                                                   "after 0.1 seconds"):
                process("msg", "prod_list", the_queue)
            # wait a second to ensure alarm is not raised later
            time.sleep(0.11)


class TestDistributed(TestCase):
    """Test functions for distributed processing."""

    def test_get_dask_client(self):
        """Test getting dask client."""
        from trollflow2.launcher import get_dask_client

        ncores = mock.MagicMock()
        ncores.return_value = {}
        client = mock.MagicMock(ncores=ncores)
        client_class = mock.MagicMock()
        client_class.return_value = client

        # No client configured
        config = {}
        res = get_dask_client(config)
        assert res is None

        # Config is valid, but no workers are available
        config = {"dask_distributed": {"class": client_class,
                                       "settings": {"foo": 1, "bar": 2}
                                       }
                  }
        res = get_dask_client(config)
        assert res is None
        ncores.assert_called_once()
        client.close.assert_called_once()

        # The scheduler had no workers, the client doesn't have `.close()`
        client.close.side_effect = AttributeError
        res = get_dask_client(config)
        assert res is None

        # Config is valid, scheduler has workers
        ncores.return_value = {'a': 1, 'b': 1}
        res = get_dask_client(config)
        assert res is client
        assert ncores.call_count == 3

        # Scheduler couldn't connect to workers
        client_class.side_effect = OSError
        res = get_dask_client(config)
        assert res is None
        assert ncores.call_count == 3


def test_check_results(tmp_path, caplog):
    """Test functionality for check_results."""
    from trollflow2.launcher import check_results

    class FakeQueue:
        def __init__(self, lo, hi, skip=[]):
            self._files = set()
            for i in range(lo, hi):
                f = (tmp_path / f"file{i:d}")
                self._files.add(str(f))
                if i not in skip:
                    with f.open(mode="wt") as fp:
                        fp.write("zucchini" * i)

        def get(self, block=None):
            try:
                return self._files.pop()
            except KeyError:
                raise queue.Empty

        def qsize(self):
            return len(self._files)

    produced_files = FakeQueue(0, 3)
    start_time = datetime.datetime(1900, 1, 1)
    exitcode = 0
    with caplog.at_level(logging.DEBUG):
        check_results(produced_files, start_time, exitcode)
    assert "Empty file detected" in caplog.text
    assert "files produced nominally" not in caplog.text

    produced_files = FakeQueue(5, 8, skip=[6])
    with caplog.at_level(logging.DEBUG):
        check_results(produced_files, start_time, exitcode)
    assert "Missing file" in caplog.text
    assert "files produced nominally" not in caplog.text

    produced_files = FakeQueue(10, 13)
    with caplog.at_level(logging.DEBUG), \
            mock.patch("trollflow2.launcher.datetime") as dd:
        dd.now.return_value = datetime.datetime(1927, 5, 20, 0, 0)
        check_results(produced_files, start_time, exitcode)
    assert "All 3 files produced nominally in 10000 days" in caplog.text

    with caplog.at_level(logging.DEBUG):
        check_results(produced_files, start_time, 1)
    assert "Process crashed with exit code 1" in caplog.text

    with caplog.at_level(logging.DEBUG):
        check_results(produced_files, start_time, -1)
    assert "Process killed with signal 1" in caplog.text


if __name__ == '__main__':
    unittest.main()
