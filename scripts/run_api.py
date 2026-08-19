import uvicorn


def main() -> None:
    uvicorn.run(
        "pit_feature_store.serving:app",
        host="127.0.0.1",
        port=8000,
    )


if __name__ == "__main__":
    main()
