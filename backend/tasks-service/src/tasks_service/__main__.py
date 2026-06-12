import uvicorn


def main() -> None:
    uvicorn.run(
        "tasks_service.main:app",
        host="0.0.0.0",  # noqa: S104 — bind all внутри контейнера за nginx
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
