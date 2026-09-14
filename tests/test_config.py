import tempfile
import unittest
from pathlib import Path

from dualsense_companion.core.config import ConfigRepository, default_config, validate_config
from dualsense_companion.domain.errors import ConfigValidationError


class ConfigTests(unittest.TestCase):
    def make_repo(self, root: Path) -> ConfigRepository:
        return ConfigRepository(
            config_path=root / "config.json",
            bundled_config_path=Path("source/dualsense_companion/resources/default_config.json"),
            bundled_profiles_dir=Path("source/dualsense_companion/resources/profiles"),
            user_profiles_dir=root / "profiles",
        )

    def test_defaults_are_versioned_and_safe(self):
        value = validate_config(default_config())
        self.assertEqual(value["schema_version"], 1)
        with self.assertRaises(ConfigValidationError):
            validate_config({"rumble": {"gate": float("nan")}})

    def test_atomic_save_and_malformed_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            self.assertFalse((root / "config.json").exists())
            self.assertEqual(repo.load()["schema_version"], 1)
            self.assertTrue((root / "config.json").exists())
            saved = repo.save(default_config())
            self.assertEqual(saved["schema_version"], 1)
            self.assertEqual(repo.load()["theme"], "Light")
            (root / "config.json").write_text("{broken", encoding="utf-8")
            fallback = repo.load()
            self.assertEqual(fallback["rumble"]["gate"], 0.05)
            self.assertIsNotNone(repo.last_error)

    def test_bundled_profiles_are_not_written_to_user_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            names = repo.list_profiles()
            self.assertTrue(any(item["name"] == "Default" and item["source"] == "bundled" for item in names))
            self.assertFalse((root / "profiles" / "Default.json").exists())
            repo.save_profile("My Profile", default_config()["rumble"])
            self.assertTrue((root / "profiles" / "My Profile.json").exists())
            self.assertEqual(repo.load_profile("My Profile")["gate"], 0.05)

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            with self.assertRaises(ConfigValidationError):
                repo.save_profile("../escape", default_config()["rumble"])

    def test_bundled_profile_name_cannot_be_shadowed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            with self.assertRaises(ConfigValidationError):
                repo.save_profile("Default", {"gate": 0.2})

            user_profiles = root / "profiles"
            user_profiles.mkdir(parents=True, exist_ok=True)
            (user_profiles / "Default.json").write_text('{"gate": 0.2}', encoding="utf-8")

            self.assertEqual(repo.load_profile("Default")["gate"], 0.05)
            default_entry = next(item for item in repo.list_profiles() if item["name"] == "Default")
            self.assertEqual(default_entry["source"], "bundled")
            self.assertFalse(default_entry["editable"])

            (user_profiles / "default.json").write_text('{"gate": 0.3}', encoding="utf-8")
            defaults = [item for item in repo.list_profiles() if item["name"].casefold() == "default"]
            self.assertEqual(defaults, [{"name": "Default", "source": "bundled", "editable": False}])


if __name__ == "__main__":
    unittest.main()
