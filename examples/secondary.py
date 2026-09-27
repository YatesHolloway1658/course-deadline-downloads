# A second, smaller way to use what this repo already does.
# Kept separate from src/edtech_downloads/__init__.py so the main path stays as short as it was.
# Reads INFRAI_API_KEY from the environment, same as the main example.
import os


def main() -> None:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise SystemExit("set INFRAI_API_KEY first")
    print("key loaded; reuse the helper from the main example here")


if __name__ == "__main__":
    main()
