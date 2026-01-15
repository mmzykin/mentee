"""Code execution for Python and Go."""
import os
import sys
import shutil
import tempfile
import subprocess

from app.config import EXEC_TIMEOUT


def run_python_code_with_tests(code: str, test_code: str) -> tuple[bool, str]:
    """Run Python code with tests."""
    full_code = code + "\n\n" + test_code
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(full_code)
        temp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
            cwd=tempfile.gettempdir(),
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0 and "✅" in output
        return passed, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"⏰ Timeout: {EXEC_TIMEOUT} сек"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"
    finally:
        try:
            os.unlink(temp_path)
        except BaseException:
            pass


def run_go_code_with_tests(code: str, test_code: str) -> tuple[bool, str]:
    """Run Go code with tests."""
    # Create temp directory for Go module
    temp_dir = tempfile.mkdtemp()
    main_path = os.path.join(temp_dir, "main.go")
    test_path = os.path.join(temp_dir, "main_test.go")

    try:
        # Ensure user code has package main
        if "package main" not in code:
            code = "package main\n\n" + code

        # Write main code
        with open(main_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Ensure test code has proper package and imports
        if "package main" not in test_code:
            # Detect needed imports from test code
            imports = ["testing"]
            if "time." in test_code:
                imports.append("time")
            if "math." in test_code:
                imports.append("math")
            if "fmt." in test_code:
                imports.append("fmt")
            if "strings." in test_code:
                imports.append("strings")
            if "sync." in test_code:
                imports.append("sync")
            if "sync/atomic" in test_code or "atomic." in test_code:
                imports.append("sync/atomic")
            if "context." in test_code:
                imports.append("context")
            if "errors." in test_code:
                imports.append("errors")
            if "sort." in test_code:
                imports.append("sort")
            if "bytes." in test_code:
                imports.append("bytes")
            if "cmp." in test_code:
                imports.append("cmp")

            import_str = "\n".join(f'\t"{imp}"' for imp in imports)
            test_code = f"package main\n\nimport (\n{import_str}\n)\n\n{test_code}"

        # Write test code
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)

        # Initialize go module
        subprocess.run(
            ["go", "mod", "init", "solution"], cwd=temp_dir, capture_output=True, timeout=5
        )

        # Run tests
        result = subprocess.run(
            ["go", "test", "-v", "."],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT,
        )

        output = result.stdout + result.stderr
        # Go tests pass if return code is 0 and contains PASS
        passed = result.returncode == 0 and ("PASS" in output or "✅" in output)

        # Add checkmark for consistency
        if passed and "✅" not in output:
            output = "✅ Все тесты пройдены!\n\n" + output

        return passed, output.strip()
    except subprocess.TimeoutExpired:
        return False, f"⏰ Timeout: {EXEC_TIMEOUT} сек"
    except FileNotFoundError:
        return False, "❌ Go не установлен на сервере"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"
    finally:
        # Cleanup
        try:
            shutil.rmtree(temp_dir)
        except BaseException:
            pass


def run_code_with_tests(code: str, test_code: str, language: str = "python") -> tuple[bool, str]:
    """Universal runner - dispatches to language-specific runner."""
    if language == "go":
        return run_go_code_with_tests(code, test_code)
    else:
        return run_python_code_with_tests(code, test_code)
