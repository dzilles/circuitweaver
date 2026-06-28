from types import SimpleNamespace

from circuitweaver.library.search import search_parts


def test_builtin_power_symbols_use_installed_kicad_power_library_name(monkeypatch):
    monkeypatch.setattr(
        "circuitweaver.library.search.get_library_paths",
        lambda: SimpleNamespace(symbols=None),
    )

    results = search_parts("pwr flag")

    assert results[0].library_id == "power:PWR_FLAG"
