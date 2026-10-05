"""Legacy launch command, sharing the Suite workspace and migration lifecycle."""
from civillab_suite.app import main as suite_main


def main() -> int:
    return suite_main(initial_module_id="prefabricados")


if __name__ == "__main__":
    raise SystemExit(main())
