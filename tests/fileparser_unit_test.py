import json
import unittest, sys, os
from unittest.mock import patch, MagicMock, mock_open
import tempfile

parent_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(parent_dir)

from modules.fileparser import (
    handle_module,
    iterative_parse,
    _default_max_module_depth,
    _load_terraform_modules_json,
)


class TestHandleModule(unittest.TestCase):
    def test_handle_module_local_source(self):
        modules_list = [{"test_module": {"source": "./local/path"}}]
        tf_file_paths = []
        filename = "main.tf"
        result = handle_module(modules_list, tf_file_paths, filename)
        self.assertIn("tf_file_paths", result)
        self.assertIn("module_source_dict", result)
        self.assertIn("test_module", result["module_source_dict"])

    def test_handle_module_remote_source(self):
        modules_list = [{"test_module": {"source": "terraform-aws-modules/vpc/aws"}}]
        tf_file_paths = []
        filename = "main.tf"
        result = handle_module(modules_list, tf_file_paths, filename)
        self.assertIn("test_module", result["module_source_dict"])
        self.assertIn("cache_path", result["module_source_dict"]["test_module"])

    def test_handle_module_empty_list(self):
        modules_list = []
        tf_file_paths = []
        filename = "main.tf"
        result = handle_module(modules_list, tf_file_paths, filename)
        self.assertEqual(len(result["module_source_dict"]), 0)

    def test_handle_module_multiple_modules(self):
        modules_list = [
            {"module1": {"source": "./path1"}},
            {"module2": {"source": "./path2"}},
        ]
        tf_file_paths = []
        filename = "main.tf"
        result = handle_module(modules_list, tf_file_paths, filename)
        self.assertEqual(len(result["module_source_dict"]), 2)


class TestLoadTerraformModulesJson(unittest.TestCase):
    """Tests for _load_terraform_modules_json()."""

    SAMPLE_MODULES_JSON = json.dumps(
        {
            "Modules": [
                {"Key": "", "Source": "", "Dir": "."},
                {
                    "Key": "registry_vpc",
                    "Source": "registry.terraform.io/terraform-aws-modules/vpc/aws",
                    "Version": "5.1.0",
                    "Dir": ".terraform/modules/registry_vpc",
                },
                {
                    "Key": "git_https_iam_account_ref",
                    "Source": "git::https://github.com/terraform-aws-modules/terraform-aws-iam.git//modules/iam-account?ref=v5.30.0",
                    "Dir": ".terraform/modules/git_https_iam_account_ref/modules/iam-account",
                },
                {
                    "Key": "local_vpc",
                    "Source": "./modules/local_vpc",
                    "Dir": "modules/local_vpc",
                },
            ]
        }
    )

    def setUp(self):
        self._orig_tf_data_dir = os.environ.pop("TF_DATA_DIR", None)
        self._tmpdir = tempfile.TemporaryDirectory()
        modules_dir = os.path.join(self._tmpdir.name, ".terraform", "modules")
        os.makedirs(modules_dir)
        with open(os.path.join(modules_dir, "modules.json"), "w") as f:
            f.write(self.SAMPLE_MODULES_JSON)

    def tearDown(self):
        self._tmpdir.cleanup()
        if self._orig_tf_data_dir is not None:
            os.environ["TF_DATA_DIR"] = self._orig_tf_data_dir

    def test_valid_modules_json(self):
        """Test loading modules.json returns expected modules."""
        result = _load_terraform_modules_json(self._tmpdir.name)
        self.assertGreater(len(result), 0)
        self.assertIn("registry_vpc", result)
        self.assertTrue(os.path.isabs(result["registry_vpc"]))
        self.assertTrue(
            result["registry_vpc"].endswith(".terraform/modules/registry_vpc")
        )

    def test_modules_json_resolves_relative_paths(self):
        """Test that relative Dir paths are resolved to absolute paths."""
        result = _load_terraform_modules_json(self._tmpdir.name)
        for key, path in result.items():
            self.assertTrue(
                os.path.isabs(path), f"Module '{key}' path is not absolute: {path}"
            )

    def test_missing_modules_json(self):
        """Test with a directory that has no .terraform/modules/modules.json."""
        result = _load_terraform_modules_json("/tmp/nonexistent_dir_12345")
        self.assertEqual(result, {})

    def test_malformed_json(self):
        """Test with malformed JSON content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            modules_dir = os.path.join(tmpdir, ".terraform", "modules")
            os.makedirs(modules_dir)
            with open(os.path.join(modules_dir, "modules.json"), "w") as f:
                f.write("not valid json{{{")
            result = _load_terraform_modules_json(tmpdir)
            self.assertEqual(result, {})

    def test_empty_key_excluded(self):
        """Test that the root module (empty Key) is excluded."""
        result = _load_terraform_modules_json(self._tmpdir.name)
        self.assertNotIn("", result)

    def test_subfolder_modules_resolved(self):
        """Test modules with subfolder paths (e.g., .terraform/modules/X/modules/Y)."""
        result = _load_terraform_modules_json(self._tmpdir.name)
        self.assertIn("git_https_iam_account_ref", result)
        self.assertTrue(
            result["git_https_iam_account_ref"].endswith("modules/iam-account")
        )


class TestModuleDepthCap(unittest.TestCase):
    """Tests for the transitive module-resolution depth cap (CLO-5901)."""

    EXTRACT = ["module", "resource"]

    def setUp(self):
        # Build a tree of nested local modules: root -> a -> b -> c.
        # Each level declares the next and has its own resource so we can
        # detect which depths were actually parsed.
        self._tmpdir = tempfile.TemporaryDirectory()
        root = self._tmpdir.name
        self.root_tf = os.path.join(root, "main.tf")
        with open(self.root_tf, "w") as f:
            f.write(
                'module "a" {\n  source = "./a"\n}\n'
                'resource "null_resource" "root" {}\n'
            )
        levels = ["a", "b", "c"]
        cur = root
        for i, name in enumerate(levels):
            cur = os.path.join(cur, name)
            os.makedirs(cur)
            child = levels[i + 1] if i + 1 < len(levels) else None
            body = f'resource "null_resource" "{name}" {{}}\n'
            if child:
                body = f'module "{child}" {{\n  source = "./{child}"\n}}\n' + body
            with open(os.path.join(cur, "main.tf"), "w") as f:
                f.write(body)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _parse(self, max_depth):
        tf_file_paths = [self.root_tf]
        tfdata = iterative_parse(
            tf_file_paths,
            {},
            self.EXTRACT,
            {},
            tf_mod_dir=os.path.join(self._tmpdir.name, ".terraform", "modules"),
            source_dir=self._tmpdir.name,
            max_module_depth=max_depth,
        )
        parsed = {os.path.basename(os.path.dirname(p)) for p in tf_file_paths}
        return tfdata, parsed

    def test_depth_zero_skips_all_modules(self):
        """max_module_depth=0 parses only the root, never descending."""
        _, parsed = self._parse(0)
        self.assertNotIn("a", parsed)

    def test_default_depth_caps_transitive_resolution(self):
        """max_module_depth=2 resolves a and b but stops before c."""
        _, parsed = self._parse(2)
        self.assertIn("a", parsed)
        self.assertIn("b", parsed)
        self.assertNotIn("c", parsed)

    def test_depth_one_resolves_only_direct_modules(self):
        """max_module_depth=1 resolves direct modules but not nested ones."""
        _, parsed = self._parse(1)
        self.assertIn("a", parsed)
        self.assertNotIn("b", parsed)

    def test_no_regression_when_tree_within_cap(self):
        """A tree shallower than the cap is fully resolved (no behavior change)."""
        _, parsed = self._parse(10)
        self.assertIn("a", parsed)
        self.assertIn("b", parsed)
        self.assertIn("c", parsed)


class TestDefaultMaxModuleDepth(unittest.TestCase):
    """Tests for _default_max_module_depth() env resolution."""

    def setUp(self):
        self._orig = os.environ.pop("TERRAVISION_MAX_MODULE_DEPTH", None)

    def tearDown(self):
        os.environ.pop("TERRAVISION_MAX_MODULE_DEPTH", None)
        if self._orig is not None:
            os.environ["TERRAVISION_MAX_MODULE_DEPTH"] = self._orig

    def test_default_is_two(self):
        self.assertEqual(_default_max_module_depth(), 2)

    def test_env_override(self):
        os.environ["TERRAVISION_MAX_MODULE_DEPTH"] = "5"
        self.assertEqual(_default_max_module_depth(), 5)

    def test_invalid_env_falls_back_to_two(self):
        os.environ["TERRAVISION_MAX_MODULE_DEPTH"] = "not-a-number"
        self.assertEqual(_default_max_module_depth(), 2)

    def test_negative_env_falls_back_to_two(self):
        os.environ["TERRAVISION_MAX_MODULE_DEPTH"] = "-3"
        self.assertEqual(_default_max_module_depth(), 2)


if __name__ == "__main__":
    unittest.main(exit=False)
