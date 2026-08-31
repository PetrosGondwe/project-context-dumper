from app.config import Config, default_config_path


def test_default_config_has_sane_values():
    c = Config()
    assert ".git" in c.excluded_dirs
    assert ".py" in c.include_ext
    assert c.max_file_size_bytes > 0


def test_roundtrip(tmp_path):
    c = Config()
    c.include_hidden = True
    c.max_file_size_bytes = 12345
    c.excluded_dirs.add("my_custom_dir")
    path = tmp_path / "config.json"
    c.save(path)

    loaded = Config.load(path)
    assert loaded.include_hidden is True
    assert loaded.max_file_size_bytes == 12345
    assert "my_custom_dir" in loaded.excluded_dirs
    assert isinstance(loaded.excluded_dirs, set)


def test_load_missing_file_returns_defaults(tmp_path):
    loaded = Config.load(tmp_path / "does_not_exist.json")
    assert loaded == Config()


def test_load_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not valid json !!!", encoding="utf-8")
    loaded = Config.load(path)
    assert loaded.max_file_size_bytes == Config().max_file_size_bytes


def test_load_non_dict_json_falls_back(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    loaded = Config.load(path)
    assert loaded == Config()


def test_default_config_path_is_absolute():
    assert default_config_path().is_absolute()
