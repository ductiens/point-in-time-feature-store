import sys

from pit_feature_store.warehouse import build_warehouse


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    database_path = build_warehouse()
    print(
        f"\nOK: Đã tạo warehouse tại "
        f"{database_path.resolve()}"
    )


if __name__ == "__main__":
    main()
