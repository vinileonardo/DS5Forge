import json
import tempfile
import unittest
from pathlib import Path

from dualsense_companion.core.config import (
    MAX_PROFILE_IMPORT_BYTES,
    ConfigRepository,
    default_config,
    default_controller_profile,
    validate_config,
)
from dualsense_companion.domain.errors import ConfigValidationError, DS5ForgeError, ErrorCode, ProfileInvalidError


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

    def test_rumble_only_bundled_profile_migrates_to_full_schema_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))

            profile = repo.load_controller_profile("Heavy Impacts")

            self.assertEqual(profile["schema_version"], 2)
            self.assertEqual(profile["name"], "Heavy Impacts")
            self.assertEqual(profile["rumble"]["min_rumble"], 40)
            self.assertEqual(profile["triggers"]["left"]["mode"], "off")
            self.assertEqual(profile["touchpad"]["swipe_threshold"], 40.0)

    def test_full_profile_roundtrip_requires_explicit_overwrite_and_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            profile = default_controller_profile("Lab")
            repo.save_controller_profile("Lab", profile)

            with self.assertRaises(DS5ForgeError) as raised:
                repo.save_controller_profile("lab", profile)
            self.assertEqual(raised.exception.code, ErrorCode.PROFILE_OVERWRITE_REQUIRED)

            saved = repo.save_controller_profile("LAB", profile, overwrite=True)
            self.assertEqual(saved["name"], "LAB")
            self.assertEqual(len(list((root / "profiles").glob("*.json"))), 1)
            self.assertEqual(repo.load_controller_profile("lAb")["schema_version"], 2)
            self.assertEqual(list((root / "profiles").glob("*.tmp")), [])

    def test_import_rejects_bad_content_without_changing_existing_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            original = default_controller_profile("Imported")
            repo.save_controller_profile("Imported", original)
            path = root / "profiles" / "Imported.json"
            before = path.read_text(encoding="utf-8")

            for content, expected in (
                ("{broken", ErrorCode.PROFILE_INVALID),
                ('{"schema_version": 99}', ErrorCode.PROFILE_INVALID),
                ('{"schema_version": 2, "name": "Imported", "rumble": {"gate": NaN}}', ErrorCode.PROFILE_INVALID),
            ):
                with self.assertRaises(DS5ForgeError) as raised:
                    repo.import_controller_profile(content, overwrite=True)
                self.assertEqual(raised.exception.code, expected)
                self.assertEqual(path.read_text(encoding="utf-8"), before)

            with self.assertRaises(DS5ForgeError) as raised:
                repo.import_controller_profile("x" * (MAX_PROFILE_IMPORT_BYTES + 1))
            self.assertEqual(raised.exception.code, ErrorCode.PROFILE_IMPORT_TOO_LARGE)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_import_validates_all_sections_before_atomic_save(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = self.make_repo(root)
            profile = default_controller_profile("Valid")
            profile["lightbar"]["r"] = 255

            imported = repo.import_controller_profile(json.dumps(profile))

            self.assertEqual(imported["name"], "Valid")
            self.assertEqual(imported["lightbar"]["r"], 255)
            self.assertEqual(repo.load_controller_profile("Valid"), imported)

            profile["triggers"]["left"]["force"] = "80"
            with self.assertRaises(ProfileInvalidError):
                repo.import_controller_profile(json.dumps(profile), overwrite=True)

            incomplete = default_controller_profile("Incomplete")
            del incomplete["rumble"]["gate"]
            with self.assertRaises(ProfileInvalidError):
                repo.import_controller_profile(json.dumps(incomplete))


if __name__ == "__main__":
    unittest.main()
