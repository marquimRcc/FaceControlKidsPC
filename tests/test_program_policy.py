import json
from pathlib import Path
import tempfile
import unittest

from safepckids.program_policy import (
    default_programs_config,
    discover_installed_programs,
    extract_executable_names,
    enforce_child_process_restrictions,
    get_allowed_programs_for_child,
    get_blocked_programs_for_child,
    is_program_allowed_for_child,
    load_programs_config,
    normalize_program_entry,
    save_programs_config,
    set_program_allowed_for_child,
)


class TestProgramPolicy(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "programas_teste.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config_creation(self):
        cfg = load_programs_config(self.config_path)
        self.assertTrue(cfg.get("enabled"))
        self.assertEqual(len(cfg.get("programs", [])), 1)
        self.assertEqual(cfg["programs"][0]["name"], "Brave")
        self.assertEqual(cfg["programs"][0]["blocked_child_ids"], [])
        self.assertTrue(self.config_path.exists())

    def test_normalize_program_entry(self):
        entry = {
            "name": " Roblox ",
            "executable": "C:\\Games\\Roblox.exe",
            "blocked_child_ids": ["1", 2, "invalid", 1],
        }
        normalized = normalize_program_entry(entry)
        self.assertEqual(normalized["name"], "Roblox")
        self.assertEqual(normalized["blocked_child_ids"], [1, 2])
        self.assertTrue(normalized["enabled"])

    def test_is_program_allowed_for_child(self):
        prog = {
            "name": "Roblox",
            "executable": "RobloxPlayerBeta.exe",
            "enabled": True,
            "blocked_child_ids": [1],  # 1 = Miguel
        }
        # Miguel is blocked (ID 1)
        self.assertFalse(is_program_allowed_for_child(prog, 1))
        self.assertFalse(is_program_allowed_for_child(prog, "1"))

        # Ana Luisa is allowed (ID 4)
        self.assertTrue(is_program_allowed_for_child(prog, 4))
        self.assertTrue(is_program_allowed_for_child(prog, "4"))

    def test_set_program_allowed_for_child(self):
        prog = {
            "name": "Minecraft",
            "executable": "minecraft.exe",
            "enabled": True,
            "blocked_child_ids": [],
        }
        # Bloquear para Miguel (ID 1)
        set_program_allowed_for_child(prog, 1, allowed=False)
        self.assertIn(1, prog["blocked_child_ids"])
        self.assertFalse(is_program_allowed_for_child(prog, 1))

        # Desbloquear para Miguel
        set_program_allowed_for_child(prog, 1, allowed=True)
        self.assertNotIn(1, prog["blocked_child_ids"])
        self.assertTrue(is_program_allowed_for_child(prog, 1))

    def test_get_allowed_and_blocked_programs_for_child(self):
        cfg = {
            "enabled": True,
            "programs": [
                {
                    "name": "Brave",
                    "executable": "brave.exe",
                    "enabled": True,
                    "blocked_child_ids": [],
                },
                {
                    "name": "Roblox",
                    "executable": "RobloxPlayerBeta.exe",
                    "enabled": True,
                    "blocked_child_ids": [1],  # Bloqueado apenas para Miguel
                },
                {
                    "name": "Desativado",
                    "executable": "offline.exe",
                    "enabled": False,
                    "blocked_child_ids": [],
                },
            ],
        }
        # Miguel (ID 1): apenas Brave liberado, Roblox bloqueado
        miguel_allowed = [p["name"] for p in get_allowed_programs_for_child(cfg, 1)]
        miguel_blocked = [p["name"] for p in get_blocked_programs_for_child(cfg, 1)]
        self.assertEqual(miguel_allowed, ["Brave"])
        self.assertEqual(miguel_blocked, ["Roblox"])

        # Ana Luisa (ID 4): ambos liberados
        ana_allowed = [p["name"] for p in get_allowed_programs_for_child(cfg, 4)]
        ana_blocked = [p["name"] for p in get_blocked_programs_for_child(cfg, 4)]
        self.assertEqual(ana_allowed, ["Brave", "Roblox"])
        self.assertEqual(ana_blocked, [])

    def test_extract_executable_names(self):
        prog = {
            "name": "Roblox",
            "executable": r"C:\Users\Filhos\AppData\Local\Roblox\Versions\RobloxPlayerBeta.exe",
            "process_names": ["custom_roblox.exe"],
        }
        names = extract_executable_names(prog)
        self.assertIn("robloxplayerbeta.exe", names)
        self.assertIn("custom_roblox.exe", names)
        self.assertIn("robloxplayerlauncher.exe", names)

    def test_save_and_reload_programs_config(self):
        cfg = default_programs_config()
        cfg["programs"].append({
            "name": "Roblox",
            "executable": "RobloxPlayerBeta.exe",
            "arguments": "",
            "enabled": True,
            "blocked_child_ids": [1],
        })
        ok = save_programs_config(cfg, self.config_path)
        self.assertTrue(ok)

        reloaded = load_programs_config(self.config_path)
        self.assertEqual(len(reloaded["programs"]), 2)
        self.assertEqual(reloaded["programs"][1]["name"], "Roblox")
        self.assertEqual(reloaded["programs"][1]["blocked_child_ids"], [1])

    def test_enforce_child_process_restrictions(self):
        from unittest.mock import patch

        cfg = {
            "enabled": True,
            "programs": [
                {
                    "name": "Roblox",
                    "executable": "RobloxPlayerBeta.exe",
                    "enabled": True,
                    "blocked_child_ids": [1],  # Bloqueado para Miguel (1)
                },
                {
                    "name": "Brave",
                    "executable": "brave.exe",
                    "enabled": True,
                    "blocked_child_ids": [],
                },
            ],
        }
        save_programs_config(cfg, self.config_path)

        with patch("safepckids.program_policy.find_and_terminate_blocked_processes") as mock_term:
            mock_term.return_value = ["robloxplayerbeta.exe"]

            # Para Miguel (1): deve checar e retornar Roblox encerrado
            terminated = enforce_child_process_restrictions(1, "Miguel", self.config_path)
            self.assertEqual(terminated, ["Roblox"])
            mock_term.assert_called_once()
            targets = mock_term.call_args[0][0]
            self.assertIn("robloxplayerbeta.exe", targets)

            # Para Ana Luisa (4): nao tem nada bloqueado, find_and_terminate nao deve nem ser chamado
            mock_term.reset_mock()
            terminated_ana = enforce_child_process_restrictions(4, "Ana Luisa", self.config_path)
            self.assertEqual(terminated_ana, [])
            mock_term.assert_not_called()

    def test_discover_installed_programs(self):
        discovered = discover_installed_programs()
        self.assertIsInstance(discovered, list)
        for item in discovered:
            self.assertIn("name", item)
            self.assertIn("executable", item)
            self.assertTrue(item["name"])
            self.assertTrue(item["executable"])




if __name__ == "__main__":
    unittest.main()
