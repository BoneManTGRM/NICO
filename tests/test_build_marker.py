from nico.build_marker import BUILD_COMMIT, BUILD_MARKER


def test_build_marker_values_exist():
    assert BUILD_MARKER
    assert len(BUILD_COMMIT) == 40
