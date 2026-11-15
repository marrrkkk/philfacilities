import uvicorn

from .config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "philfacilities_api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.env == "local",
    )


if __name__ == "__main__":
    main()
