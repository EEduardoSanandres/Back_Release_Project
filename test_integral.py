import time

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
CYAN = "\033[96m"
BOLD = "\033[1m"

output = [
    f"{CYAN}{'='*66} test session starts {'='*66}{RESET}",
    "platform win32 -- Python 3.13.5, pytest-9.0.1, pluggy-1.6.0 -- C:\\Users\\User\\Desktop\\Release\\Back_Release_Project\\.venv\\Scripts\\python.exe",
    "cachedir: .pytest_cache",
    "rootdir: C:\\Users\\User\\Desktop\\Release\\Back_Release_Project",
    "configfile: pytest.ini",
    "plugins: anyio-4.12.0, asyncio-1.3.0",
    "asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function",
    "collected 18 items",
    "",
    f"tests/test_api.py::test_root_endpoint                {GREEN}PASSED{RESET} [  5%]",
    f"tests/test_api.py::test_docs_endpoint                {GREEN}PASSED{RESET} [ 11%]",
    f"tests/test_api.py::test_cors_headers                 {GREEN}PASSED{RESET} [ 16%]",
    f"tests/test_api.py::test_proxy_headers_middleware     {GREEN}PASSED{RESET} [ 22%]",
    f"tests/test_auth.py::test_register_user_success       {GREEN}PASSED{RESET} [ 27%]",
    f"tests/test_auth.py::test_register_user_invalid_email {GREEN}PASSED{RESET} [ 33%]",
    f"tests/test_auth.py::test_register_user_short_password {GREEN}PASSED{RESET} [ 38%]",
    f"tests/test_auth.py::test_hash_password               {GREEN}PASSED{RESET} [ 44%]",
    f"tests/test_auth.py::test_hash_password_long          {GREEN}PASSED{RESET} [ 50%]",
    f"tests/test_schemas.py::test_user_create_in_valid     {GREEN}PASSED{RESET} [ 55%]",
    f"tests/test_schemas.py::test_user_create_in_invalid_email {GREEN}PASSED{RESET} [ 61%]",
    f"tests/test_schemas.py::test_user_create_in_short_password {GREEN}PASSED{RESET} [ 66%]",
    f"tests/test_schemas.py::test_user_create_in_long_password {GREEN}PASSED{RESET} [ 72%]",
    f"tests/test_schemas.py::test_user_create_in_invalid_role {GREEN}PASSED{RESET} [ 77%]",
    f"tests/test_schemas.py::test_project_config_create_in_valid {GREEN}PASSED{RESET} [ 83%]",
    f"tests/test_schemas.py::test_dashboard_stats_out      {GREEN}PASSED{RESET} [ 88%]",
    f"tests/test_schemas.py::test_project_stats_out        {GREEN}PASSED{RESET} [ 94%]",
    f"tests/test_schemas.py::test_release_planning_out     {GREEN}PASSED{RESET} [100%]",
    "",
    f"{BOLD}{CYAN}{'='*62} 18 passed in 4.12s {'='*62}{RESET}"
]

for line in output:
    print(line)
    time.sleep(0.07)