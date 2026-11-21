"""Production image wiring must apply the pinned repair and exercise owned CTU records and allocation fallbacks."""
from pathlib import Path
import yaml

DOCKER = Path('docker/assessment-full-project-fuzz.Dockerfile')


def test_repair_is_composed_after_existing_overlays_before_the_only_build():
    text = DOCKER.read_text()
    commands = [
        'python3 /opt/repair_cppcheck_placement_ast.py',
        'python3 /opt/repair_cppcheck_header_grammar.py',
        'python3 /opt/patch_cppcheck_header_evidence.py',
        'python3 /opt/repair_cppcheck_replacement_index.py',
        'python3 /opt/repair_cppcheck_ctu_first_use.py',
        'timeout 180s make -C /opt/tool-src',
    ]
    positions = [text.index(command) for command in commands]
    assert positions == sorted(positions)
    assert text.count('make -C /opt/tool-src') == 1
    assert 'COPY repair_cppcheck_ctu_first_use.py /opt/repair_cppcheck_ctu_first_use.py' in text
    assert 'COPY cppcheck-ctu-first-use /opt/cppcheck-ctu-first-use' in text
    assert '> /opt/nico-cppcheck-ctu-first-use.json' in text


def test_real_mutation_controls_run_before_source_cleanup_with_assertions_enabled():
    text = DOCKER.read_text()
    compile_line = next(line for line in text.splitlines() if 'g++ -std=c++11' in line and 'cppcheck-ctu-first-use' in line)
    assert 'timeout 30s g++' in compile_line and '-DNDEBUG' not in compile_line
    assert 'native-controls.cpp build/*.o' in compile_line
    assert 'externals/simplecpp/simplecpp.o externals/tinyxml2/tinyxml2.o' in compile_line
    execution = 'timeout 30s /opt/ctu-first-use-control > /opt/nico-cppcheck-ctu-first-use-control.txt'
    assert text.index(compile_line) < text.index(execution) < text.index('rm -rf /opt/tool-src')
    assert '&& ' + execution in text


def test_every_production_image_builder_stages_and_retains_the_new_binding():
    builders = 0
    names = ['cpp-full-project-integration.yml', 'cpp-full-project-release.yml']
    diagnostic = Path('.github/workflows/native-timeout-diagnostic.yml')
    if diagnostic.exists() and 'assessment-full-project-fuzz.Dockerfile' in diagnostic.read_text():
        names.append('native-timeout-diagnostic.yml')
    for name in names:
        workflow = yaml.safe_load((Path('.github/workflows') / name).read_text())
        for job in workflow['jobs'].values():
            for step in job.get('steps', []):
                run = step.get('run', '')
                if 'docker build' not in run or 'assessment-full-project-fuzz.Dockerfile' not in run:
                    continue
                builders += 1
                assert 'cp scripts/repair_cppcheck_ctu_first_use.py toolchain/full-project/' in run
                assert 'cp -R scripts/cppcheck-ctu-first-use toolchain/full-project/' in run
                assert '--network=none' in run
                assert '/opt/nico-cppcheck-ctu-first-use.json' in run
                assert '/opt/nico-cppcheck-ctu-first-use-control.txt' in run
        if name == 'native-timeout-diagnostic.yml':
            # Fresh diagnostic bindings are captured locally, without archives.
            continue
        retained = '\n'.join(step.get('with', {}).get('path', '')
                             for job in workflow['jobs'].values()
                             for step in job.get('steps', []) if 'upload-artifact@' in step.get('uses', ''))
        assert 'cppcheck-ctu-first-use.json' in retained
        assert 'cppcheck-ctu-first-use-control.txt' in retained
    assert builders == 3 + int(len(names) == 3)


def test_integrity_and_wiring_controls_are_part_of_full_production_contracts():
    text = Path('.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_ctu_first_use_repair.py' in text
    assert 'tests/test_cpp_ctu_first_use_wiring.py' in text
    assert 'timeout --kill-after=10s 300s docker build --network=none' in text
    assert 'timeout 210s docker build --network=none' in Path('.github/workflows/cpp-full-project-release.yml').read_text()
