"""Checks for the new stage; an unfinished G task is SKIPPED, not passed.

Clocks are injected in unit checks, so a simulated 50-second test is instantaneous.
A short integration check uses actual waiting; see VALIDATION.md for the separate
full 10 x 5 second runtime verification. No third-party test runner is needed.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
from itertools import islice
import io
import json
from pathlib import Path
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from recording import append_reading, create_session, write_snapshot
from records import parse_record
from run_configuration import load_run_config, validate_simulation
from simulation import sensor_values, simulate_sensors, wait_until
from streaming import build_snapshot, iter_jsonl, rolling_windows, select_calibrated

ROOT = Path(__file__).resolve().parents[1]


def example_config():
    return json.loads((ROOT / 'config/simulation_10_readings.json').read_text())


def sensor(**changes):
    return {**example_config()['simulation']['sensors'][0], **changes}


def record(value=21.0, **changes):
    return parse_record({'time': '2026-01-01T12:00:00+00:00', 'room': 'laboratory',
                         'sensor_id': 'station-01', 'metric': 'temperature',
                         'value': value, 'unit': 'C', **changes})


class Clock:
    """A deterministic elapsed clock plus matching UTC clock for tests only."""
    def __init__(self):
        self.value = 0.0
        self.waits = []

    def __call__(self):
        return self.value

    def sleep(self, delay):
        if delay < 0:
            raise AssertionError('Never sleep for a negative interval.')
        self.waits.append(delay)
        self.value += delay

    def now(self):
        return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self.value)


def exercise(test):
    """A placeholder is visible as skipped; all other exceptions still fail."""
    @wraps(test)
    def wrapped(self, *args, **kwargs):
        try:
            return test(self, *args, **kwargs)
        except NotImplementedError as error:
            self.skipTest(str(error))
    return wrapped


class GeneratorTasks(unittest.TestCase):
    @exercise
    def test_G1_lazy_and_reproducible(self):
        with patch('simulation.random.Random', wraps=random.Random) as factory:
            stream = sensor_values(sensor())
            factory.assert_not_called()
            first = list(islice(stream, 6))
            factory.assert_called_once_with(42)
            stream.close()
        again = list(islice(sensor_values(sensor()), 6))
        self.assertEqual(first, again)
        self.assertGreater(len(set(first)), 1)

    @exercise
    def test_G1_independent_random_streams(self):
        global_state = random.getstate()
        a = sensor_values(sensor(seed=10))
        b = sensor_values(sensor(seed=11))
        first = [next(a), next(b), next(a), next(b)]
        expected_a = list(islice(sensor_values(sensor(seed=10)), 2))
        expected_b = list(islice(sensor_values(sensor(seed=11)), 2))
        self.assertEqual(first, [expected_a[0], expected_b[0], expected_a[1], expected_b[1]])
        self.assertEqual(random.getstate(), global_state)
        a.close(); b.close()

    @exercise
    def test_G1_zero_noise_and_supported_ranges(self):
        self.assertEqual(list(islice(sensor_values(sensor(noise_std=0)), 3)), [21.0]*3)
        humidity = sensor_values(sensor(metric='humidity', mean=50, noise_std=1000))
        self.assertTrue(all(0 <= x <= 100 for x in islice(humidity, 100)))
        pressure = sensor_values(sensor(metric='pressure', mean=1, noise_std=1000))
        self.assertTrue(all(x >= 0 for x in islice(pressure, 100)))
        humidity.close(); pressure.close()

    @exercise
    def test_G2_wait_until_and_already_due(self):
        clock = Clock()
        wait_until(5, clock, clock.sleep)
        self.assertEqual(clock.value, 5)
        self.assertEqual(clock.waits, [5])
        wait_until(2, clock, clock.sleep)
        self.assertEqual(clock.waits, [5])

    @exercise
    def test_G2_rechecks_after_early_wakeup(self):
        clock = Clock()
        def early(delay):
            clock.sleep(min(1.0, delay))
        wait_until(5, clock, early)
        self.assertEqual(clock.value, 5)
        self.assertEqual(len(clock.waits), 5)

    @exercise
    def test_first_measurement_is_at_5_not_0(self):
        clock = Clock()
        stream = simulate_sensors([sensor()], clock=clock, sleep=clock.sleep, now=clock.now)
        self.assertEqual(clock.value, 0)
        rows = list(islice(stream, 10))
        self.assertEqual(clock.value, 50)
        offsets = [(datetime.fromisoformat(r['time']) - datetime(2026,1,1,tzinfo=timezone.utc)).total_seconds() for r in rows]
        self.assertEqual(offsets, list(range(5, 51, 5)))
        stream.close()

    @exercise
    def test_independent_intervals_and_stable_ties(self):
        clock = Clock()
        stream = simulate_sensors([sensor(interval_seconds=2), sensor(metric='humidity',
            interval_seconds=5, mean=40, seed=43)], clock=clock, sleep=clock.sleep, now=clock.now)
        events = []
        for row in islice(stream, 7):
            events.append((clock.value, row['metric']))
        self.assertEqual(events, [(2,'temperature'), (4,'temperature'), (5,'humidity'),
                                 (6,'temperature'), (8,'temperature'),
                                 (10,'temperature'), (10,'humidity')])
        stream.close()

    @exercise
    def test_slow_consumer_does_not_create_synthetic_backlog(self):
        clock = Clock()
        stream = simulate_sensors([sensor()], clock=clock, sleep=clock.sleep, now=clock.now)
        next(stream)
        clock.value = 100  # Consumer took 95 seconds to do its work.
        late = next(stream)
        self.assertEqual(clock.value, 100)
        next(stream)
        self.assertEqual(clock.value, 105)
        self.assertEqual(datetime.fromisoformat(late['time']).second, 40)
        stream.close()

    @exercise
    def test_no_unused_eleventh_measurement(self):
        clock = Clock()
        with patch('simulation.sensor_values', wraps=sensor_values) as values:
            stream = simulate_sensors([sensor()], clock=clock, sleep=clock.sleep, now=clock.now)
            rows = list(islice(stream, 10))
            self.assertEqual(len(rows), 10)
            self.assertEqual(len(clock.waits), 10)
            stream.close()
            values.assert_called_once()

    @exercise
    def test_G3_line_reader_lazy_and_strict(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'data.jsonl'
            path.write_text(json.dumps(record())+'\n\ninvalid\n')
            stream = iter_jsonl(path)
            self.assertEqual(next(stream), record())
            with self.assertRaisesRegex(ValueError, 'line 3'):
                next(stream)

    @exercise
    def test_G3_close_releases_open_file(self):
        handle = io.StringIO(json.dumps(record())+'\n'+json.dumps(record(22))+'\n')
        with patch('pathlib.Path.open', return_value=handle):
            stream = iter_jsonl(Path('unused.jsonl'))
            next(stream)
            self.assertFalse(handle.closed)
            stream.close()
            self.assertTrue(handle.closed)

    @exercise
    def test_G3_missing_file_is_opened_only_when_consumed(self):
        with tempfile.TemporaryDirectory() as temp:
            stream = iter_jsonl(Path(temp)/'missing.jsonl')
            with self.assertRaises(OSError):
                next(stream)

    @exercise
    def test_G3_empty_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'empty.jsonl';path.write_text('\n\n')
            self.assertEqual(list(iter_jsonl(path)), [])

    @exercise
    def test_G4_selects_before_calibrating_and_preserves_input(self):
        rows = [record(), record(40, metric='humidity', unit='%'), record(22)]
        original = deepcopy(rows)
        config = example_config()
        result = list(select_calibrated(iter(rows), config['selection'],
                                       {'enabled':True,'scale':2,'offset':-1}))
        self.assertEqual([r['value'] for r in result], [41,43])
        self.assertEqual(rows, original)
        self.assertIsNot(result[0], rows[0])

    @exercise
    def test_G4_is_lazy_and_does_not_read_ahead(self):
        config = example_config()
        consumed = []
        def source():
            for i in range(5):
                consumed.append(i);yield record(i)
        stream = select_calibrated(source(), config['selection'],
                                   {'enabled':False,'scale':1,'offset':0})
        self.assertEqual(consumed, [])
        self.assertEqual(next(stream)['value'], 0)
        self.assertEqual(consumed, [0])
        stream.close()

    @exercise
    def test_G4_disabled_calibration_still_copies(self):
        config = example_config();row=record()
        output = list(select_calibrated([row], config['selection'],
                                       {'enabled':False,'scale':999,'offset':999}))
        self.assertEqual(output, [row]);self.assertIsNot(output[0],row)

    @exercise
    def test_G5_bounded_window_and_warmup(self):
        last = None
        for i,window in enumerate(rolling_windows((record(i) for i in range(3000)), 3)):
            self.assertEqual(len(window), min(i+1, 3))
            self.assertEqual(window[-1]['value'], i)
            last=window
        self.assertEqual([r['value'] for r in last], [2997,2998,2999])

    @exercise
    def test_G5_snapshot_copies_are_independent(self):
        rows = [record(1),record(2),record(3)]
        windows = rolling_windows(rows, 2)
        first=next(windows);first[0]['value']=1000
        second=next(windows)
        self.assertEqual(second[0]['value'],1)
        rows[1]['value']=2000
        third=next(windows)
        self.assertEqual(third[0]['value'],2)

    @exercise
    def test_G5_rejects_invalid_window_size(self):
        # Probe outside subTest: subTest records errors before our skip wrapper sees them.
        list(rolling_windows([], 1))
        for size in [0,-1,True,2.5,'3']:
            with self.subTest(size=size), self.assertRaises(ValueError):
                list(rolling_windows([],size))

    @exercise
    def test_G5_rejects_mixed_series(self):
        with self.assertRaisesRegex(ValueError,'one series'):
            list(rolling_windows([record(),record(40,metric='humidity',unit='%')],3))

    @exercise
    def test_G6_serialise_before_write(self):
        stream=io.StringIO('previous\n');stream.seek(0,2)
        with self.assertRaises(ValueError):
            append_reading(stream, record(value=21)|{'value':float('nan')})
        self.assertEqual(stream.getvalue(),'previous\n')

    @exercise
    def test_G6_flushes_one_line_at_a_time(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw.jsonl'
            with path.open('x',encoding='utf-8') as stream:
                append_reading(stream,record())
                # A separate handle can see the record before writer.close().
                self.assertEqual(json.loads(path.read_text()),record())
                append_reading(stream,record(22))
                self.assertEqual(len(path.read_text().splitlines()),2)

    @exercise
    def test_G6_optional_fsync_and_write_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            with (Path(temp)/'raw.jsonl').open('x') as stream:
                with patch('recording.os.fsync') as sync:
                    append_reading(stream,record(),True)
                    sync.assert_called_once_with(stream.fileno())
        stream=io.StringIO();stream.close()
        with self.assertRaises(ValueError):
            append_reading(stream,record())

    def test_snapshot_empty_and_one_sample(self):
        config=example_config()
        empty=build_snapshot([],config['selection'],config['calibration'],5)
        self.assertEqual(empty['points'],[])
        self.assertIsNone(empty['summary']['mean'])
        one=build_snapshot([record()],config['selection'],config['calibration'],5)
        self.assertEqual(one['summary']['mean'],21)
        self.assertIsNone(one['summary']['sample_sd'])
        self.assertEqual(one['series']['unit'],'C')

    def test_atomic_snapshot_replaces_only_complete_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'latest.json'
            write_snapshot(path,{'mean':21})
            with self.assertRaises(ValueError):
                write_snapshot(path,{'mean':float('inf')})
            self.assertEqual(json.loads(path.read_text()),{'mean':21})
            self.assertFalse(path.with_name('latest.json.tmp').exists())


class ConfigurationChecks(unittest.TestCase):
    def test_all_supplied_configs(self):
        for path in (ROOT/'config').glob('*.json'):
            with self.subTest(path=path.name):
                result=load_run_config(path)
                self.assertIn(result['mode'], {'files','simulation'})

    def test_old_default_and_new_files_mode_match(self):
        self.assertEqual(load_run_config(ROOT/'config/example.json'),
                         load_run_config(ROOT/'config/files.json'))

    def test_validation_does_not_mutate_and_paths_use_config_dir(self):
        config=example_config();before=deepcopy(config)
        validate_simulation(config)
        self.assertEqual(config,before)
        loaded=load_run_config(ROOT/'config/simulation_10_readings.json')
        self.assertEqual(loaded['recording']['directory'], ROOT/'output/sessions')

    def test_invalid_modes_and_non_object(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json'
            for config in [[],{'mode':'simluation'},{'mode':None}]:
                path.write_text(json.dumps(config))
                with self.assertRaises(ValueError):load_run_config(path)

    def test_strict_sensor_schema_and_duplicates(self):
        for change in ['empty','duplicate','misspelling','unknown_metric']:
            config=example_config();s=config['simulation']['sensors']
            if change=='empty':s.clear()
            elif change=='duplicate':s.append(deepcopy(s[0]))
            elif change=='misspelling':s[0]['frequence']=5
            else:s[0]['metric']='temp'
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_simulation(config)

    def test_invalid_numerical_settings(self):
        cases=[('interval_seconds',0),('interval_seconds',-1),('interval_seconds',True),
               ('interval_seconds',float('nan')),('mean',float('inf')),
               ('noise_std',-1),('seed',2.5),('seed',True),('room','  ')]
        for key,value in cases:
            config=example_config();config['simulation']['sensors'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                validate_simulation(config)

    def test_invalid_counts_and_window_sizes(self):
        for section,key in [('simulation','max_readings'),('stream','window_size')]:
            for value in [0,-1,True,2.5,'10']:
                config=example_config();config[section][key]=value
                with self.subTest(section=section,value=value),self.assertRaises(ValueError):
                    validate_simulation(config)
        config=example_config();config['simulation']['max_readings']=None
        validate_simulation(config)

    def test_selection_must_exist_and_identifiers_are_exact(self):
        for section in ['selection','sensor']:
            config=example_config()
            target=config['selection'] if section=='selection' else config['simulation']['sensors'][0]
            target['room']='laboratory '
            with self.assertRaises(ValueError):validate_simulation(config)

    def test_humidity_and_pressure_means(self):
        for metric,mean in [('humidity',101),('humidity',-1),('pressure',0)]:
            config=example_config();config['simulation']['sensors'][0].update(metric=metric,mean=mean)
            config['selection']['metric']=metric
            with self.assertRaises(ValueError):validate_simulation(config)

    def test_config_and_log_collision_prevents_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json';config=example_config()
            config['logging']['path']='config.json'
            path.write_text(json.dumps(config));before=path.read_bytes()
            with self.assertRaisesRegex(ValueError,'configuration'):load_run_config(path)
            self.assertEqual(path.read_bytes(),before)

    def test_recording_directory_cannot_be_log_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json';config=example_config()
            config['logging']['path']=config['recording']['directory']='same'
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError,'collision'):load_run_config(path)

    def test_new_session_never_overwrites_previous(self):
        with tempfile.TemporaryDirectory() as temp:
            config=example_config();config['recording']['directory']=Path(temp)/'sessions'
            one=create_session(config);two=create_session(config)
            self.assertNotEqual(one,two)
            for path in [one,two]:
                offline=load_run_config(path/'offline_config.json')
                self.assertEqual(offline['input']['path'],path/'raw.jsonl')
                self.assertEqual(offline['mode'],'files')


class IntegrationChecks(unittest.TestCase):
    @exercise
    def setUp(self):
        # Probe the actual task implementations, not a manually toggled 'done' flag.
        next(sensor_values(sensor()))
        clock=Clock();wait_until(0,clock,clock.sleep)
        config=example_config()
        list(select_calibrated([record()],config['selection'],config['calibration']))
        list(rolling_windows([record()],2))
        append_reading(io.StringIO(),record())
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.project=self.base/'project';self.project.mkdir()
        for path in ROOT.glob('*.py'):shutil.copy2(path,self.project/path.name)
        shutil.copytree(ROOT/'config',self.project/'config')
        shutil.copytree(ROOT/'data',self.project/'data')
        self.path=self.project/'config/test.json'

    def run_config(self,config):
        self.path.write_text(json.dumps(config))
        started=time.monotonic()
        result=subprocess.run([sys.executable,'-B',str(self.project/'run.py'),str(self.path)],
                              cwd=self.base,text=True,capture_output=True,timeout=10)
        return result,time.monotonic()-started

    def session(self):
        return next((self.project/'output/sessions').iterdir())

    def test_short_real_time_run_archive_and_offline_analysis(self):
        config=example_config();config['simulation']['sensors'][0]['interval_seconds']=0.03
        result,elapsed=self.run_config(config)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertGreaterEqual(elapsed,0.30)
        session=self.session()
        rows=[json.loads(line) for line in (session/'raw.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),10)
        latest=json.loads((session/'latest.json').read_text())
        self.assertEqual(len(latest['points']),5)
        self.assertEqual(latest['summary']['count'],5)
        self.assertAlmostEqual(latest['points'][-1]['value'], rows[-1]['value']*1.02-0.4)
        self.assertEqual(latest['status'],'completed')
        metadata=json.loads((session/'session.json').read_text())
        self.assertEqual(metadata['records_saved'],10)
        self.assertEqual(metadata['selected_records'],10)
        offline=subprocess.run([sys.executable,'-B',str(self.project/'run.py'),str(session/'offline_config.json')],
                               cwd=self.base,text=True,capture_output=True,timeout=10)
        self.assertEqual(offline.returncode,0,offline.stderr)
        report=json.loads((session/'offline/summary.json').read_text())
        self.assertEqual(report['summary']['count'],10)
        self.assertAlmostEqual(report['summary']['mean'],sum(r['value'] for r in rows)/10*1.02-0.4)
        self.assertEqual(len((session/'raw.jsonl').read_text().splitlines()),10)

    def test_archive_includes_unselected_series_and_limit_is_total(self):
        config=example_config();config['simulation']['max_readings']=12
        config['simulation']['sensors'][0]['interval_seconds']=0.02
        config['simulation']['sensors'].append(sensor(metric='humidity',mean=45,interval_seconds=0.01))
        result,_=self.run_config(config);self.assertEqual(result.returncode,0,result.stderr)
        session=self.session()
        rows=[json.loads(x) for x in (session/'raw.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),12)
        self.assertEqual({r['metric'] for r in rows},{'temperature','humidity'})
        latest=json.loads((session/'latest.json').read_text())
        self.assertEqual(latest['selected_records'],sum(r['metric']=='temperature' for r in rows))
        self.assertEqual(latest['records_saved'],12)

    def test_limit_can_end_before_first_selected_record(self):
        config=example_config();config['simulation']['max_readings']=1
        config['simulation']['sensors'].append(sensor(metric='humidity',mean=45,interval_seconds=0.01))
        result,_=self.run_config(config);self.assertEqual(result.returncode,0,result.stderr)
        latest=json.loads((self.session()/'latest.json').read_text())
        self.assertEqual(latest['selected_records'],0)
        self.assertEqual(latest['points'],[])
        self.assertIsNone(latest['summary']['mean'])
        self.assertEqual(latest['records_saved'],1)

    @unittest.skipUnless(sys.platform!='win32','This automated signal check uses POSIX SIGINT.')
    def test_ctrl_c_flushes_recording_and_final_metadata(self):
        config=example_config();config['simulation']['max_readings']=None
        config['simulation']['sensors'][0]['interval_seconds']=0.05
        self.path.write_text(json.dumps(config))
        process=subprocess.Popen([sys.executable,'-B','-u',str(self.project/'run.py'),str(self.path)],
                                 cwd=self.base,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                paths=list((self.project/'output/sessions').glob('*/raw.jsonl'))
                if paths and len(paths[0].read_text().splitlines())>=3:break
                if process.poll() is not None:self.fail(process.communicate())
                time.sleep(0.01)
            else:self.fail('No measurements arrived.')
            process.send_signal(signal.SIGINT)
            out,err=process.communicate(timeout=5)
            self.assertEqual(process.returncode,0,out+err)
            session=self.session();meta=json.loads((session/'session.json').read_text())
            rows=[json.loads(x) for x in (session/'raw.jsonl').read_text().splitlines()]
            self.assertEqual(meta['status'],'interrupted')
            self.assertEqual(meta['records_saved'],len(rows))
            self.assertGreaterEqual(len(rows),3)
        finally:
            if process.poll() is None:process.kill();process.communicate()

    def test_storage_failure_is_not_a_success(self):
        # Inject a write error in this process and verify earlier data remains.
        from run_stream import run_simulation
        config=example_config();config['simulation']['max_readings']=3
        config['simulation']['sensors'][0]['interval_seconds']=0.001
        self.path.write_text(json.dumps(config));loaded=load_run_config(self.path)
        real_append=append_reading;calls=[]
        def fail_second(stream,row,fsync):
            calls.append(row)
            if len(calls)==2:raise OSError('simulated full disk')
            real_append(stream,row,fsync)
        with patch('run_stream.append_reading',side_effect=fail_second),patch('builtins.print'):
            with self.assertRaisesRegex(OSError,'full disk'):run_simulation(loaded)
        session=self.session()
        self.assertEqual(len((session/'raw.jsonl').read_text().splitlines()),1)
        self.assertEqual(json.loads((session/'session.json').read_text())['status'],'failed')


if __name__=='__main__':unittest.main()
